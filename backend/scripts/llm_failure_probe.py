"""Read-only probe for LLM value, failures, latency, and gate decisions.

The corpus is opened through SQLite's ``mode=ro`` URI. The probe never imports
ingestion routes, starts a server, fetches articles, or opens a write-capable DB
connection. It evaluates a fixed ID-sorted slice of eligible corpus articles:

    .venv/Scripts/python.exe scripts/llm_failure_probe.py --limit 60 --max-calls 60

JSON is written to stdout so a before/after result can be captured by CI or a
human without changing the corpus.

Bounded evaluation of a hosted model (#262, docs/HOSTING_PLAN.md section 10.4).
Plan first (no provider is built, no request is sent), then the stage-0 smoke:

    python scripts/llm_failure_probe.py --ids-file ../docs/qa/census2_sample.json --limit 30 --max-calls 30 --dry-run --price-in-per-m 0.075 --price-out-per-m 0.30
    python scripts/llm_failure_probe.py --ids-file ../docs/qa/census2_sample.json --limit 30 --max-calls 30 --price-in-per-m 0.075 --price-out-per-m 0.30

- ``--max-calls`` is a hard ceiling on provider calls (default 30, never above
  500); the report says whether it cut the sample.
- ``--dry-run`` reads the DB read-only to size the sample and prints the plan
  with token and cost ESTIMATES. It never constructs the provider.
- ``mode`` in the report is ``dry_run``, ``live`` (a networked provider:
  gemini, ollama, openai_compat) or ``offline`` (disabled, fake, a test stub),
  so mocked numbers can never pass for a live evaluation.
- Prices are the operator's assumptions (USD per 1M tokens), echoed in the
  report. Measured cost uses only the token counts the provider reported.
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
MAX_CALLS_CEILING = 500
NETWORKED_PROVIDERS = frozenset({"gemini", "ollama", "openai_compat"})
# Dry-run estimate per call (HOSTING_PLAN F4: ~1,300 tokens a call, ~1,100 of
# them the system prompt). Reasoning tokens are unknown until measured.
ASSUMED_PROMPT_TOKENS = 1200
ASSUMED_OUTPUT_TOKENS = 150


def load_ids(path: Path) -> list[str]:
    """Article ids from a JSON file: a list of ids, a list of {"id": ...}, or a
    census sample ({"profiles": {name: {"items": [{"id": ...}]}}})."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("profiles"), dict):
        rows = [item for profile in data["profiles"].values()
                for item in (profile.get("items") or [])]
    elif isinstance(data, list):
        rows = data
    else:
        raise ValueError(f"{path}: expected a list or a census sample")
    ids: list[str] = []
    for row in rows:
        value = row.get("id") if isinstance(row, dict) else row
        if isinstance(value, str) and value not in ids:
            ids.append(value)
    return ids


def _provider_settings() -> dict[str, Any]:
    """What the env would configure, without the key and without a client."""
    import os
    from urllib.parse import urlparse

    base = os.environ.get("CLASSIFICATION_BASE_URL", "")
    return {
        "provider": os.environ.get("CLASSIFICATION_PROVIDER", "disabled").strip().lower(),
        "model": os.environ.get("CLASSIFICATION_MODEL") or None,
        "base_url_host": urlparse(base).hostname if base else None,
        "api_key_set": bool(os.environ.get("CLASSIFICATION_API_KEY", "").strip()),
    }


def _cost(prompt_tokens: int, output_tokens: int,
          price_in: float | None, price_out: float | None) -> float | None:
    if price_in is None or price_out is None:
        return None
    return round(prompt_tokens / 1e6 * price_in + output_tokens / 1e6 * price_out, 6)


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


def run_probe(
    db_path: Path,
    limit: int,
    *,
    max_calls: int = 30,
    dry_run: bool = False,
    ids: list[str] | None = None,
    price_in_per_m: float | None = None,
    price_out_per_m: float | None = None,
) -> dict[str, Any]:
    if not 0 < max_calls <= MAX_CALLS_CEILING:
        raise ValueError(f"max_calls must be 1..{MAX_CALLS_CEILING}")
    articles = _read_articles(db_path)
    if ids is not None:
        wanted = set(ids)
        articles = [a for a in articles if a["id"] in wanted]
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
    planned = sample[:max_calls]
    bounds = {
        "max_calls": max_calls,
        "calls_planned": len(planned),
        "cut_by_max_calls": len(sample) > len(planned),
        "ids_requested": len(ids) if ids is not None else None,
        "ids_found_eligible": len(eligible) if ids is not None else None,
    }
    prices = {"usd_per_1m_input": price_in_per_m, "usd_per_1m_output": price_out_per_m,
              "source": "operator-supplied assumption"}

    if dry_run:
        est_in = len(planned) * ASSUMED_PROMPT_TOKENS
        est_out = len(planned) * ASSUMED_OUTPUT_TOKENS
        return {
            "probe_version": 2,
            "mode": "dry_run",
            "requests_sent": 0,
            "database": db_path.name,
            "provider_settings": _provider_settings(),
            "bounds": bounds,
            "sample_ids": [article["id"] for article, _ in planned],
            "estimate": {
                "assumed_prompt_tokens_per_call": ASSUMED_PROMPT_TOKENS,
                "assumed_output_tokens_per_call": ASSUMED_OUTPUT_TOKENS,
                "note": "reasoning/thinking tokens are not estimated; stage 0 measures them",
                "input_tokens": est_in,
                "output_tokens": est_out,
                "prices": prices,
                "estimated_cost_usd": _cost(est_in, est_out, price_in_per_m, price_out_per_m),
            },
        }

    sample = planned
    provider = get_llm_provider()
    if not provider.can_classify:
        raise RuntimeError("Configured LLM provider is disabled")
    provider_kind = provider.provider_id.split(":", 1)[0]
    mode = "live" if provider_kind in NETWORKED_PROVIDERS else "offline"
    usage_totals: Counter[str] = Counter()

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
        usage = getattr(provider, "last_usage", None)
        if isinstance(usage, dict):
            usage_totals["calls_with_usage"] += 1
            for key in ("prompt_tokens", "completion_tokens", "reasoning_tokens"):
                if isinstance(usage.get(key), int):
                    usage_totals[key] += usage[key]
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
    # Gemini reports thinking apart from the candidates; OpenAI-style APIs count
    # reasoning inside completion_tokens. Bill the output as each one reports it.
    output_tokens = usage_totals["completion_tokens"] + (
        usage_totals["reasoning_tokens"] if provider_kind == "gemini" else 0
    )
    return {
        "probe_version": 2,
        "mode": mode,
        "provider_id": provider.provider_id,
        "requests_sent": len(sample),
        "bounds": bounds,
        "usage": {
            **dict(usage_totals),
            "prices": prices,
            "measured_cost_usd": _cost(
                usage_totals["prompt_tokens"], output_tokens, price_in_per_m, price_out_per_m
            ) if usage_totals["calls_with_usage"] else None,
        },
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
    parser.add_argument("--max-calls", type=int, default=30,
                        help=f"hard ceiling on provider calls (1..{MAX_CALLS_CEILING})")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan and estimate only; build no provider, send nothing")
    parser.add_argument("--ids-file", type=Path,
                        help="restrict to these article ids (a list, or a census sample JSON)")
    parser.add_argument("--price-in-per-m", type=float, help="USD per 1M input tokens (assumption)")
    parser.add_argument("--price-out-per-m", type=float, help="USD per 1M output tokens (assumption)")
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
    if not 0 < args.max_calls <= MAX_CALLS_CEILING:
        parser.error(f"--max-calls must be 1..{MAX_CALLS_CEILING}")
    report = run_probe(
        args.db, args.limit, max_calls=args.max_calls, dry_run=args.dry_run,
        ids=load_ids(args.ids_file) if args.ids_file else None,
        price_in_per_m=args.price_in_per_m, price_out_per_m=args.price_out_per_m,
    )
    if not args.include_details:
        report.pop("articles", None)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
