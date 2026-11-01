"""Census #3 targeted checks and per-classification-path metrics (#241). Read-only.

Run against a COPY of the corpus (the app engine opens DATABASE_URL; nothing is written):

    set DATABASE_URL=sqlite:///C:/path/to/copy.db
    python scripts/census_checks.py --since 2026-10-11 \\
        --sample ../docs/qa/census3_sample.json --ratings ../docs/qa/census3_ratings.json \\
        [--out checks.json] [--snapshot-out stored.json] [--final-heldout-eval]

The four checks #241 asks for run over the WHOLE cohort. Each lists rows for the owner to
read; none of them is a verdict on its own (a rating, or the owner's reading, decides):

1. ``club_governance`` pushes (#229): does every push report a concrete step?
2. Executives (``exec:*``, #229): every title/subtitle the current rules resolve to a
   club executive. A TITLE mention implies Maccabi Tel Aviv; check it is that person.
3. Israeli basketball cups (#230): are Winner Cup / Super Cup stories visible?
4. ``schedule`` (#224): is a story whose only "לקראת" is in the subtitle still a
   ``schedule`` row, or hidden?

With ``--ratings``, every census metric (exact, shown precision, feed+ recall, push
precision and recall; definitions from corpus_rerun_diff.census_metrics) is reported for
the rated SAMPLE rows: all of them, then per classification path (LLM success, rules only,
rules after an LLM failure, rules after a low-confidence LLM answer).

Guards (#241):
- Metrics and ``--snapshot-out`` cover sample rows only. A rating for an id outside the
  sample is refused: out-of-sample rows are checked separately and never scored here.
- Held-out ratings (a sealed census) are excluded unless ``--final-heldout-eval``.

Decisions are the current engine's on stored facts, scored exactly as
``rate_census.py build`` scores them. ``--snapshot-out`` writes them in corpus_rerun_diff's
snapshot shape, for ``eval_stats.py census`` and ``rate_census.py review --snapshot``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable

_BACKEND = Path(__file__).resolve().parents[1]

try:  # run as a script (scripts/ on sys.path) or imported as scripts.census_checks (tests)
    from corpus_rerun_diff import census_metrics
except ImportError:  # pragma: no cover - import style depends on the caller
    from scripts.corpus_rerun_diff import census_metrics

# Israeli basketball cups registered by #230, plus their spellings, so a cup story the
# classifier did not tag still surfaces here.
CUP_COMPETITIONS = frozenset({"comp:winner_cup", "comp:il_super_cup"})
CUP_WORDS = ("גביע ווינר", "גביע וינר", "סופרקאפ", "סופר קאפ")
AHEAD = "לקראת"

# Stored ``classified_by`` → classification path (ingestion_service.py). "rules" means the
# LLM was not called (gated out, or no provider); the stored row does not say which.
PATHS = {
    "llm": "llm_success",
    "llm+rules_guardrail": "llm_success",
    "rules": "rules_only",
    "rules_fallback_after_llm_failure": "fallback_llm_failure",
    "rules_fallback_low_confidence": "fallback_low_confidence",
}
PATH_ORDER = ("llm_success", "rules_only", "fallback_llm_failure", "fallback_low_confidence", "other")


def classification_path(classified_by: str | None) -> str:
    return PATHS.get(classified_by or "rules", "other")


def row_from_scored(scored) -> dict:
    a = scored.article
    return {
        "id": a.id,
        "title": a.translated_title or a.title,
        "subtitle": a.subtitle or "",
        "source": a.source,
        "sport": a.sport,
        "event_type": a.event_type,
        "decision": scored.decision,
        "matched_event_rule": scored.matched_event_rule,
        "entity_ids": list(a.entity_ids or []),
        "competitions": [c for c in [a.primary_competition, *(a.article_competitions or [])] if c],
        "path": classification_path(a.classified_by),
    }


def club_governance_check(rows: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    """(all club_governance rows, the pushes among them)."""
    rows = [r for r in rows if r["event_type"] == "club_governance"]
    return rows, [r for r in rows if r["decision"] == "push"]


def cup_check(rows: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    """(cup rows, the hidden ones). A cup row is tagged with a cup competition or names one."""
    def is_cup(r):
        text = f"{r['title']} {r['subtitle']}"
        return bool(CUP_COMPETITIONS & set(r["competitions"])) or any(w in text for w in CUP_WORDS)

    rows = [r for r in rows if is_cup(r)]
    return rows, [r for r in rows if r["decision"] == "hidden"]


def subtitle_ahead_check(rows: Iterable[dict]) -> tuple[list[dict], list[dict]]:
    """(rows whose only "לקראת" is in the subtitle, those still typed ``schedule``)."""
    rows = [r for r in rows if AHEAD in r["subtitle"] and AHEAD not in r["title"]]
    return rows, [r for r in rows if r["event_type"] == "schedule"]


def exec_check(rows: Iterable[dict], resolve: Callable[[str, str], list[str]]) -> list[dict]:
    """Rows where ``resolve(text, source)`` finds an executive, with where it was found.
    Title mentions imply the club; subtitle-only mentions are sport evidence only."""
    out = []
    for r in rows:
        in_title = resolve(r["title"], r["source"])
        in_subtitle = resolve(r["subtitle"], r["source"]) if r["subtitle"] else []
        if in_title or in_subtitle:
            out.append({**r, "exec_in_title": in_title, "exec_in_subtitle": in_subtitle})
    return out


def resolve_executives(text: str, source: str) -> list[str]:
    """The executive ids the classifier's own resolver finds in ``text``."""
    from app.ingestion.classifier import _resolve_text_entities

    resolution = _resolve_text_entities(text.lower(), source)
    return sorted({e.id for e in resolution.resolved if e.kind == "executive"})


SNAPSHOT_FIELD = {"guy": "guy", "casual_deni_fan": "deni"}  # corpus_rerun_diff's keys


def stored_snapshot(rows: Iterable[dict], sample_ids: set[str], profile: str = "guy") -> dict:
    """The SAMPLE rows' decisions on stored facts, in ``corpus_rerun_diff`` snapshot shape, so
    ``eval_stats.py census`` and ``rate_census.py review --snapshot`` can read them. Sample
    rows only: a rating for any other row can never meet a decision through this file.
    (A corpus_rerun_diff snapshot is a rules-only replay; this is what production stored.)"""
    field = SNAPSHOT_FIELD[profile]
    return {
        r["id"]: {field: r["decision"], "sport": r["sport"], "event": r["event_type"], "path": r["path"]}
        for r in rows if r["id"] in sample_ids
    }


def usable_ratings(ratings: dict[str, str], sample_ids: set[str], sealed: set[str],
                   final_heldout_eval: bool = False) -> tuple[dict[str, str], int]:
    """The ratings this run may read: refuses out-of-sample ids, drops held-out ones unless
    this is the final evaluation. Returns ``(ratings, held-out ratings dropped)``."""
    outside = [k for k in ratings if k not in sample_ids]
    if outside:
        raise ValueError(
            f"{len(outside)} ratings are for rows outside the sample (e.g. {outside[0]}); "
            "out-of-sample rows are rated and checked separately, never in the census score")
    if final_heldout_eval:
        return dict(ratings), 0
    kept = {k: v for k, v in ratings.items() if k not in sealed}
    return kept, len(ratings) - len(kept)


def metrics_by_path(snapshot: dict, ratings: dict[str, str], profile: str = "guy") -> dict:
    """``census_metrics`` for every rated row, then per classification path."""
    field = SNAPSHOT_FIELD[profile]
    out = {"all": census_metrics(snapshot, ratings, field)}
    for path in PATH_ORDER:
        sub = {k: v for k, v in ratings.items() if k in snapshot and snapshot[k]["path"] == path}
        if sub:
            out[path] = census_metrics(snapshot, sub, field)
    return out


def annotate(rows: list[dict], sample_ids: set[str], ratings: dict[str, str]) -> list[dict]:
    return [{**r, "in_sample": r["id"] in sample_ids, "owner": ratings.get(r["id"])} for r in rows]


def summarize(rows: list[dict]) -> dict:
    return {
        "n": len(rows),
        "decisions": dict(Counter(r["decision"] for r in rows)),
        "owner": dict(Counter(r["owner"] for r in rows if r.get("owner"))),
    }


def run_checks(rows: list[dict], sample_ids: set[str], ratings: dict[str, str],
               resolve: Callable[[str, str], list[str]]) -> dict:
    rows = annotate(rows, sample_ids, ratings)
    governance, governance_push = club_governance_check(rows)
    cups, cups_hidden = cup_check(rows)
    ahead, ahead_schedule = subtitle_ahead_check(rows)
    execs = exec_check(rows, resolve)
    return {
        "cohort": len(rows),
        "club_governance": {**summarize(governance), "pushes": governance_push},
        "executives": {**summarize(execs), "rows": execs},
        "cups": {**summarize(cups), "hidden": cups_hidden, "rows": cups},
        "subtitle_only_ahead": {
            **summarize(ahead),
            "by_event": dict(Counter(f"{r['event_type']}/{r['decision']}" for r in ahead)),
            "still_schedule": ahead_schedule,
            "hidden": [r for r in ahead if r["decision"] == "hidden"],
        },
    }


def _line(r: dict) -> str:
    owner = r.get("owner") or ("unrated" if r.get("in_sample") else "-")
    return f"    {r['decision']:9} {r['event_type'] or '-':16} owner={owner:7} {r['id']}  {r['title'][:70]}"


def _print(report: dict) -> None:
    print(f"cohort: {report['cohort']} articles")
    sections = (
        ("1. club_governance", "club_governance", "pushes"),
        ("2. executives (exec:*)", "executives", "rows"),
        ("3. Israeli basketball cups", "cups", "hidden"),
        ("4. subtitle-only 'לקראת'", "subtitle_only_ahead", "still_schedule"),
    )
    for title, key, listed in sections:
        block = report[key]
        print(f"\n{title}: n={block['n']} decisions={block['decisions']} owner={block['owner']}")
        if "by_event" in block:
            print(f"  event/decision: {block['by_event']}")
            print(f"  hidden: {len(block['hidden'])}")
        print(f"  {listed}: {len(block[listed])}")
        for r in block[listed]:
            print(_line(r))
            if key == "executives":
                print(f"      title={r['exec_in_title']} subtitle={r['exec_in_subtitle']}")


def _print_metrics(by_path: dict) -> None:
    print("\nmetrics by classification path (rated sample rows; k/n):")
    print(f"  {'path':24} {'rated':>5} {'exact':>9} {'shown prec':>11} {'feed+ recall':>13} "
          f"{'push prec':>10} {'push recall':>12}")
    for path, m in by_path.items():
        cells = [f"{k}/{n}" for k, n in (
            (m["exact"], m["rated"]), m["shown_precision"], m["feed_plus_recall"],
            m["push_precision"], m["push_recall"])]
        print(f"  {path:24} {m['rated']:5} {cells[0]:>9} {cells[1]:>11} {cells[2]:>13} "
              f"{cells[3]:>10} {cells[4]:>12}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--since", required=True, help="YYYY-MM-DD cutoff (inclusive)")
    parser.add_argument("--profile", default="guy")
    parser.add_argument("--sample", help="census sample (required with --ratings or --snapshot-out)")
    parser.add_argument("--ratings", action="append", default=[],
                        help="owner ratings for sample rows (repeatable)")
    parser.add_argument("--final-heldout-eval", action="store_true",
                        help="read a sealed held-out half's ratings (the one final evaluation only)")
    parser.add_argument("--out", help="write the full report as JSON")
    parser.add_argument("--snapshot-out",
                        help="write the sample rows' stored-fact decisions as a corpus_rerun_diff-"
                             "shaped snapshot (eval_stats.py census, rate_census.py review --snapshot)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if (args.ratings or args.snapshot_out) and not args.sample:
        parser.error("--ratings and --snapshot-out need --sample")

    sys.path.insert(0, str(_BACKEND))
    sys.path.insert(0, str(_BACKEND / "scripts"))
    from app.qa.census_rating import is_fresh, sealed_ids
    from rate_census import score_feeds

    sample_ids: set[str] = set()
    sealed: set[str] = set()
    if args.sample:
        sample = json.loads(Path(args.sample).read_text(encoding="utf-8"))
        sample_ids = {it["id"] for it in sample["profiles"][args.profile]["items"]}
        sealed = sealed_ids(sample, args.sample)
    ratings: dict[str, str] = {}
    for path in args.ratings:
        ratings.update(json.loads(Path(path).read_text(encoding="utf-8"))["ratings"].get(args.profile, {}))
    try:
        ratings, dropped = usable_ratings(ratings, sample_ids, sealed, args.final_heldout_eval)
    except ValueError as exc:
        raise SystemExit(f"refused: {exc}")
    if dropped:
        print(f"sealed held-out half: {dropped} ratings excluded (--final-heldout-eval reads them)")

    _, feeds = score_feeds([args.profile])
    rows = [row_from_scored(s) for s in feeds[args.profile] if is_fresh(s.article.published_at, args.since)]

    report = run_checks(rows, sample_ids, ratings, resolve_executives)
    _print(report)
    snapshot = stored_snapshot(rows, sample_ids, args.profile)
    if ratings:
        report["metrics_by_path"] = metrics_by_path(snapshot, ratings, args.profile)
        _print_metrics(report["metrics_by_path"])
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nwrote {args.out}")
    if args.snapshot_out:
        Path(args.snapshot_out).write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.snapshot_out} ({len(snapshot)} sample rows, stored-fact decisions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
