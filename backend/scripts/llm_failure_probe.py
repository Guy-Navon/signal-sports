"""Read-only probe for LLM value, failures, latency, and gate decisions.

The corpus is opened through SQLite's ``mode=ro`` URI. The probe never imports
ingestion routes, starts a server, fetches articles, or opens a write-capable DB
connection. It evaluates a fixed ID-sorted slice of eligible corpus articles:

    .venv/Scripts/python.exe scripts/llm_failure_probe.py --limit 60

JSON is written to stdout so a before/after result can be captured by CI or a
human without changing the corpus.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env", override=False)

from app.classification.gating import should_call_llm_for_article
from app.classification.merge import merge_with_guardrails, normalize_league_sport_compatibility
from app.classification.service import get_llm_provider
from app.classification.source_hints import extract_source_sport_hint
from app.classification.validation import LLM_MIN_CONFIDENCE
from app.ingestion.classifier import classify, _has_football_maccabi_context


ELIGIBLE_SOURCES = frozenset(
    {
        "walla_sport",
        "israel_hayom_sport",
        "ynet_sport",
        "one_sport",
        "sport5_sport",
    }
)
COMPARE_FIELDS = ("sport", "league", "event_type", "entities")


def _read_articles(db_path: Path) -> list[dict[str, Any]]:
    """Load the minimum replay fields through a physically read-only connection."""
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, source, url, title, translated_title, subtitle
            FROM articles
            WHERE id GLOB 'rss_*'
            ORDER BY id
            """
        ).fetchall()
    return [dict(row) for row in rows]


def _rules_and_gate(article: dict[str, Any]):
    title = article["translated_title"] or article["title"] or ""
    subtitle = article["subtitle"]
    source = article["source"] or ""
    url = article["url"] or ""
    hint = extract_source_sport_hint(source, url)
    rules = classify(
        title,
        source_id=source,
        language="he",
        url=url,
        subtitle=subtitle,
        source_sport_hint=hint,
    )
    gate = should_call_llm_for_article(
        source_id=source,
        title=title,
        subtitle=subtitle,
        rules_result=rules,
        source_sport_hint=hint,
    )
    return title, subtitle, hint, rules, gate


def _field_values(result) -> dict[str, Any]:
    return {
        "sport": result.sport,
        "league": result.league,
        "event_type": result.event_type,
        "entities": list(result.entities),
    }


def _round_latency(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "average_ms": None, "median_ms": None, "p90_ms": None}
    ordered = sorted(values)
    p90_index = min(len(ordered) - 1, max(0, int(0.9 * len(ordered) + 0.9999) - 1))
    return {
        "count": len(values),
        "average_ms": round(sum(values) / len(values), 1),
        "median_ms": round(statistics.median(values), 1),
        "p90_ms": round(ordered[p90_index], 1),
    }


def run_probe(db_path: Path, limit: int) -> dict[str, Any]:
    articles = _read_articles(db_path)
    eligible: list[tuple[dict[str, Any], tuple[Any, ...]]] = []
    corpus_call_reasons: Counter[str] = Counter()
    corpus_skip_reasons: Counter[str] = Counter()

    for article in articles:
        if article["source"] not in ELIGIBLE_SOURCES:
            continue
        replay = _rules_and_gate(article)
        eligible.append((article, replay))
        gate = replay[-1]
        target = corpus_call_reasons if gate.should_call_llm else corpus_skip_reasons
        target[gate.reason] += 1

    sample = eligible[:limit]
    provider = get_llm_provider()
    if not provider.can_classify:
        raise RuntimeError("Configured LLM provider is disabled")

    failure_reasons: Counter[str] = Counter()
    latencies: list[float] = []
    raw_failures: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    by_reason: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "attempts": 0,
            "usable": 0,
            "low_confidence": 0,
            "any_change": 0,
            "field_changes": Counter(),
        }
    )
    total_field_changes: Counter[str] = Counter()
    usable = 0
    any_change = 0

    for article, replay in sample:
        title, subtitle, hint, rules, gate = replay
        llm_result = provider.classify_title(title, "he", subtitle=subtitle)
        latency_ms = provider.last_call_latency_ms
        if latency_ms is not None:
            latencies.append(latency_ms)

        reason_stats = by_reason[gate.reason]
        reason_stats["attempts"] += 1
        item: dict[str, Any] = {
            "id": article["id"],
            "source": article["source"],
            "gate_should_call": gate.should_call_llm,
            "gate_reason": gate.reason,
            "latency_ms": round(latency_ms, 1) if latency_ms is not None else None,
            "rules": _field_values(rules),
        }

        if llm_result is None:
            failure_reason = provider.last_failure_reason
            failure_reasons[failure_reason] += 1
            raw = provider.last_raw_content
            item.update({"outcome": "failure", "failure_reason": failure_reason})
            raw_failures.append(
                {
                    "id": article["id"],
                    "failure_reason": failure_reason,
                    "raw_length": len(raw) if raw is not None else None,
                    "raw_content": raw,
                }
            )
            details.append(item)
            continue

        item["llm_raw"] = _field_values(llm_result)
        if llm_result.confidence < LLM_MIN_CONFIDENCE:
            reason_stats["low_confidence"] += 1
            item.update(
                {"outcome": "low_confidence", "llm_confidence": llm_result.confidence}
            )
            details.append(item)
            continue

        merged, classified_by = merge_with_guardrails(
            llm_result,
            rules,
            title.lower(),
            football_maccabi_detected=_has_football_maccabi_context(title.lower()),
            source_sport_hint=hint,
            subtitle_lower=subtitle.lower() if subtitle else None,
        )
        merged = normalize_league_sport_compatibility(merged)
        rules_values = _field_values(rules)
        final_values = _field_values(merged)
        changed_fields = [field for field in COMPARE_FIELDS if rules_values[field] != final_values[field]]
        usable += 1
        reason_stats["usable"] += 1
        if changed_fields:
            any_change += 1
            reason_stats["any_change"] += 1
        for field in changed_fields:
            total_field_changes[field] += 1
            reason_stats["field_changes"][field] += 1
        item.update(
            {
                "outcome": "usable",
                "llm_confidence": llm_result.confidence,
                "classified_by": classified_by,
                "final": final_values,
                "changed_fields": changed_fields,
            }
        )
        details.append(item)

    reason_report: dict[str, Any] = {}
    for reason, stats in sorted(by_reason.items()):
        usable_for_reason = stats["usable"]
        reason_report[reason] = {
            "attempts": stats["attempts"],
            "usable": usable_for_reason,
            "low_confidence": stats["low_confidence"],
            "any_change": stats["any_change"],
            "agreement_rate": (
                round(1 - stats["any_change"] / usable_for_reason, 4)
                if usable_for_reason
                else None
            ),
            "field_changes": dict(stats["field_changes"]),
        }

    current_calls = sum(corpus_call_reasons.values())
    return {
        "probe_version": 1,
        "database": db_path.name,
        "selection": "eligible RSS articles ordered by id, first N",
        "sample_limit": limit,
        "sample_ids": [article["id"] for article, _ in sample],
        "corpus": {
            "rss_articles": len(articles),
            "eligible_articles": len(eligible),
            "current_calls": current_calls,
            "current_call_rate_all_rss": (
                round(current_calls / len(articles), 4) if articles else None
            ),
            "call_reasons": dict(corpus_call_reasons),
            "skip_reasons": dict(corpus_skip_reasons),
        },
        "outcomes": {
            "attempts": len(sample),
            "usable": usable,
            "failures": sum(failure_reasons.values()),
            "low_confidence": len(sample) - usable - sum(failure_reasons.values()),
            "failure_reasons": dict(failure_reasons),
            "latency": _round_latency(latencies),
        },
        "value": {
            "any_change": any_change,
            "agreement_rate": round(1 - any_change / usable, 4) if usable else None,
            "field_changes": dict(total_field_changes),
            "by_gate_reason": reason_report,
        },
        "raw_failures": raw_failures,
        "articles": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument(
        "--include-details",
        action="store_true",
        help="include one comparison record per sampled article",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=BACKEND_ROOT / "data" / "signal_sports.db",
    )
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit must be positive")
    report = run_probe(args.db, args.limit)
    if not args.include_details:
        report.pop("articles")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
