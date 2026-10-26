"""Score the #256 week sample, the focused #345 set and the #345 regression rows
against the owner's ratings, stage by stage (docs/qa/WEEK_SAMPLE_2026-10_DEV_RESULTS.md).

Every row is replayed through the production ``_normalise`` (rules, gate, LLM merge,
facts) with the provider swapped, then scored with Guy's live profile
(``score_article_v2``), like ``llm_bakeoff.py``. Two providers: rules only, and
Groq ``openai/gpt-oss-20b`` with the bake-off candidate's settings (the production
configuration since 2026-10-25). The Groq answers come from
``docs/qa/week_sample_responses/``; a missing answer is a live call only with
``--live`` (otherwise the run stops), so a re-run costs nothing.

A third run repeats the Groq replay with the cross-sport entity guard
(``cross_sport_entity_requires_explicit_sport``) switched off IN MEMORY. It is a
counterfactual that shows what the guard actually changes; nothing is written.

The week sample's ``test`` rows (the sealed holdout) are never read: only
``split == "dev"`` rows are loaded, and ``--include-holdout`` exists for the day the
candidate change is frozen.

    python scripts/analyze_week_sample.py --out ../docs/qa/week_sample_2026-10_dev_analysis.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
QA = REPO / "docs" / "qa"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

import llm_bakeoff as b  # noqa: E402

TIERS = ("hidden", "low_feed", "feed", "high_feed", "push")
WANTED = ("feed", "high_feed", "push")
CANDIDATE = "groq-gpt-oss-20b"


def _row(it: dict, rating: str) -> "b.Row":
    pub = datetime.fromisoformat(it["published_at"].replace("Z", "+00:00"))
    pub = pub if pub.tzinfo else pub.replace(tzinfo=timezone.utc)
    return b.Row(it["id"], it["source"], it["url"], it["title"], it.get("subtitle"), pub,
                 b.RATING_TO_TIER[rating])


def load_sets(session, include_holdout: bool) -> dict[str, list]:
    from sqlalchemy import text

    def sample(name: str, splits: tuple[str, ...] | None) -> list:
        items = json.loads((QA / f"{name}.json").read_text(encoding="utf-8"))["profiles"]["guy"]["items"]
        rated = json.loads((QA / f"{name}_ratings.json").read_text(encoding="utf-8"))["ratings"]["guy"]
        return [_row(it, rated[it["id"]]) for it in items if splits is None or it.get("split") in splits]

    census2 = json.loads((QA / "census2_ratings.json").read_text(encoding="utf-8"))["ratings"]["guy"]
    reg_ids = json.loads((QA / "focused_345_2026-10.json").read_text(encoding="utf-8"))["meta"]["regression_rows"]
    regression = []
    for aid in reg_ids:
        r = session.execute(text("SELECT source, url, title, subtitle, published_at FROM articles WHERE id=:i"),
                            {"i": aid}).fetchone()
        regression.append(_row({"id": aid, "source": r[0], "url": r[1], "title": r[2], "subtitle": r[3],
                                "published_at": r[4]}, census2[aid]))
    sets = {"dev": sample("week_sample_2026-10", ("dev",)),
            "focused": sample("focused_345_2026-10", None),
            "regression": regression}
    if include_holdout:
        sets["holdout"] = sample("week_sample_2026-10", ("test",))
    return sets


@contextmanager
def guard_off():
    """Counterfactual only: treat no entity as cross-sport ambiguous in the facts stage."""
    from app.classification import facts
    original = facts.is_cross_sport_ambiguous
    facts.is_cross_sport_ambiguous = lambda entity: False
    try:
        yield
    finally:
        facts.is_cross_sport_ambiguous = original


def llm_outcome(article, entry: dict | None) -> str:
    """Technical failure vs fallback vs a used answer, from the call record and the trace."""
    trace = article.classification_trace or {}
    gate = (trace.get("llm") or {}).get("gate_should_call")
    if not gate:
        return "not_called(gate)"
    if entry is None:
        return "no_record"
    if entry["failure_reason"] != "none":
        return f"technical_failure:{entry['failure_reason']}"
    try:
        conf = json.loads(entry["raw"]).get("confidence", 0)
    except (TypeError, ValueError):
        return "technical_failure:unparseable"
    from app.classification.validation import LLM_MIN_CONFIDENCE
    if conf < LLM_MIN_CONFIDENCE:
        return "fallback:low_confidence"
    return "used" if (article.classified_by or "").startswith("llm") else "fallback:merge_kept_rules"


def view(article, decision, row, entry) -> dict:
    trace = article.classification_trace or {}
    conflicts = trace.get("conflicts") if isinstance(trace.get("conflicts"), list) else []
    llm = trace.get("llm") or {}
    return {
        "id": row.id, "source": row.source, "title": row.title, "owner": row.rating,
        "decision": decision.decision, "matched_topic": decision.matched_topic,
        "sport": article.sport, "primary_competition": article.primary_competition,
        "entities": list(article.entities or []), "event_type": article.event_type,
        "gate": f"{'call' if llm.get('gate_should_call') else 'skip'}:{llm.get('gate_reason')}",
        "classified_by": article.classified_by,
        "llm_outcome": llm_outcome(article, entry),
        "llm_proposal": {k: (llm.get("proposal") or {}).get(k) for k in ("sport", "entities", "event_type")}
        if llm.get("proposal") else None,
        "conflict_rules": [c.get("rule") for c in conflicts],
    }


def stage(v: dict) -> str:
    wanted, shown = v["owner"] in WANTED, v["decision"] != "hidden"
    if wanted and not shown:
        if any("cross_sport" in (r or "") for r in v["conflict_rules"]):
            return "miss:facts_dropped_cross_sport_entity"
        if v["sport"] in (None, "unknown"):
            return "miss:no_sport"
        if not v["entities"] and not v["primary_competition"]:
            return "miss:no_entity_or_competition"
        return "miss:facts_resolved_profile_hides"
    if v["owner"] == "hidden" and shown:
        return "false_show"
    return "ok"


def metrics(rows: list[dict]) -> dict:
    wanted = [r for r in rows if r["owner"] in WANTED]
    shown = [r for r in rows if r["decision"] != "hidden"]
    confusion = {o: {d: 0 for d in TIERS} for o in TIERS}
    for r in rows:
        confusion[r["owner"]][r["decision"]] += 1
    return {
        "n": len(rows),
        "wanted": len(wanted),
        "wanted_shown": sum(r["decision"] != "hidden" for r in wanted),
        "shown": len(shown),
        "shown_rated_hidden": sum(r["owner"] == "hidden" for r in shown),
        "shown_rated_low_or_better": sum(r["owner"] != "hidden" for r in shown),
        "exact_tier": sum(r["owner"] == r["decision"] for r in rows),
        "decision_below_owner": sum(TIERS.index(r["decision"]) < TIERS.index(r["owner"]) for r in rows),
        "decision_above_owner": sum(TIERS.index(r["decision"]) > TIERS.index(r["owner"]) for r in rows),
        "high_or_push_rated_assigned_lower": [
            {"id": r["id"], "owner": r["owner"], "decision": r["decision"], "title": r["title"]}
            for r in rows if r["owner"] in ("high_feed", "push")
            and TIERS.index(r["decision"]) < TIERS.index(r["owner"])],
        "pushes": sum(r["decision"] == "push" for r in rows),
        "owner_push": sum(r["owner"] == "push" for r in rows),
        "confusion_owner_by_decision": confusion,
        "stages": dict(Counter(r["stage"] for r in rows if r["stage"] != "ok")),
        "llm_outcomes": dict(Counter(r["llm_outcome"] for r in rows)),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=BACKEND / "data" / "signal_sports.db")
    ap.add_argument("--cache-dir", type=Path, default=QA / "week_sample_responses")
    ap.add_argument("--live", action="store_true", help="allow Groq calls for answers missing from the cache")
    ap.add_argument("--include-holdout", action="store_true", help="ONLY after the candidate is frozen")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    from app.classification.prompt import CLASSIFICATION_SYSTEM_PROMPT
    from app.classification.providers import DisabledLLMProvider
    from app.repositories import profile_repository
    from app.services.preference_engine import score_article_v2

    engine, session = b.open_readonly(args.db)
    profile = profile_repository.get_by_id(session, "guy")
    sets = load_sets(session, args.include_holdout)
    session.close()

    cand = b.CANDIDATES[CANDIDATE]
    cache = b.ResponseCache(args.cache_dir / f"{cand.name}.jsonl")
    inner = None
    if args.live:
        from dotenv import dotenv_values
        inner = b.build_provider(cand, (dotenv_values(BACKEND / ".env").get(cand.key_env) or "").strip())
    recorder = b.Recorder(cand, inner, cache, budget=200 if args.live else 0)
    providers = {"rules": DisabledLLMProvider(), "groq20b": recorder}

    runs: dict[str, list[dict]] = {}
    for run_name, provider_name, cf in (("rules", "rules", False), ("groq20b", "groq20b", False),
                                        ("groq20b_guard_off", "groq20b", True)):
        rows_out = []
        for set_name, rows in sets.items():
            if cf:
                with guard_off():
                    arts = b.replay(rows, providers[provider_name])
            else:
                arts = b.replay(rows, providers[provider_name])
            for row in rows:
                a = arts[row.id]
                entry = cache.get(b.prompt_key(cand, row.title, row.subtitle)) if provider_name == "groq20b" else None
                v = view(a, score_article_v2(a, profile, set()), row, entry)
                v["set"], v["stage"] = set_name, stage(v)
                rows_out.append(v)
        runs[run_name] = rows_out

    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    report = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "git_sha": sha,
            "profile": "guy (live profile, read-only)",
            "llm": {"candidate": cand.name, "model": cand.model, "response_format": cand.response_format,
                    "reasoning_effort": cand.reasoning_effort, "max_output_tokens": cand.max_output_tokens,
                    "system_prompt_sha256": hashlib.sha256(CLASSIFICATION_SYSTEM_PROMPT.encode()).hexdigest()},
            "gate": "production gate (CLASSIFICATION_LLM_GATING=enabled)",
            "sets": {k: len(v) for k, v in sets.items()},
            "holdout_read": args.include_holdout,
            "llm_calls": {"live": recorder.live_calls, "cached": recorder.cached_calls},
        },
        "metrics": {run: {s: metrics([r for r in rows if r["set"] == s]) for s in sets} for run, rows in runs.items()},
        "rows": runs,
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for run in runs:
        for s in sets:
            m = report["metrics"][run][s]
            print(f"{run:18s} {s:10s} n={m['n']:3d} wanted {m['wanted_shown']}/{m['wanted']} "
                  f"shown {m['shown']} (rated hidden {m['shown_rated_hidden']}) exact {m['exact_tier']} "
                  f"stages {m['stages']} llm {m['llm_outcomes']}")


if __name__ == "__main__":
    main()
