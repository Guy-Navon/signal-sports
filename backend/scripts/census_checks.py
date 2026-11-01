"""Census #3 targeted checks (#241) over the WHOLE fresh cohort. Read-only.

Run against a COPY of the corpus (the app engine opens DATABASE_URL; nothing is written):

    set DATABASE_URL=sqlite:///C:/path/to/copy.db
    python scripts/census_checks.py --since 2026-10-11 \\
        --sample ../docs/qa/census3_sample.json --ratings ../docs/qa/census3_ratings.json \\
        [--out checks.json] [--snapshot-out stored.json]

``--snapshot-out`` writes the cohort's stored-fact decisions in corpus_rerun_diff's
snapshot shape, for ``eval_stats.py census`` (intervals) and ``rate_census.py review
--snapshot``.

The four checks #241 asks for. Each lists rows for the owner to read; none of them is a
verdict on its own (a rating, or the owner's reading of the headline, decides):

1. ``club_governance`` pushes (#229): does every push report a concrete step?
2. Executives (``exec:*``, #229): every title/subtitle the current rules resolve to a
   club executive. A TITLE mention implies Maccabi Tel Aviv; check it is that person.
3. Israeli basketball cups (#230): are Winner Cup / Super Cup stories visible?
4. ``schedule`` (#224): is a story whose only "לקראת" is in the subtitle still a
   ``schedule`` row, or hidden?

Decisions are the current engine's on stored facts, scored exactly as
``rate_census.py build`` scores them. ``--sample``/``--ratings`` only annotate rows with
"in sample" and the owner's rating when one exists.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable

_BACKEND = Path(__file__).resolve().parents[1]

# Israeli basketball cups registered by #230, plus their spellings, so a cup story the
# classifier did not tag still surfaces here.
CUP_COMPETITIONS = frozenset({"comp:winner_cup", "comp:il_super_cup"})
CUP_WORDS = ("גביע ווינר", "גביע וינר", "סופרקאפ", "סופר קאפ")
AHEAD = "לקראת"


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


def stored_snapshot(rows: Iterable[dict], profile: str = "guy") -> dict:
    """The cohort's decisions ON STORED FACTS in ``corpus_rerun_diff`` snapshot shape, so
    ``eval_stats.py census`` and ``rate_census.py review --snapshot`` can read them. A
    corpus_rerun_diff snapshot is a rules-only replay; this one is what production stored."""
    field = SNAPSHOT_FIELD[profile]
    return {r["id"]: {field: r["decision"], "sport": r["sport"], "event": r["event_type"]} for r in rows}


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--since", required=True, help="YYYY-MM-DD cutoff (inclusive)")
    parser.add_argument("--profile", default="guy")
    parser.add_argument("--sample", help="census sample (marks in-sample rows)")
    parser.add_argument("--ratings", help="owner ratings (annotates rated rows)")
    parser.add_argument("--out", help="write the full report as JSON")
    parser.add_argument("--snapshot-out",
                        help="write stored-fact decisions as a corpus_rerun_diff-shaped snapshot "
                             "(input for eval_stats.py census and rate_census.py review --snapshot)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    sys.path.insert(0, str(_BACKEND))
    sys.path.insert(0, str(_BACKEND / "scripts"))
    from app.qa.census_rating import is_fresh
    from rate_census import score_feeds

    _, feeds = score_feeds([args.profile])
    rows = [row_from_scored(s) for s in feeds[args.profile] if is_fresh(s.article.published_at, args.since)]
    sample_ids: set[str] = set()
    if args.sample:
        sample = json.loads(Path(args.sample).read_text(encoding="utf-8"))
        sample_ids = {it["id"] for it in sample["profiles"][args.profile]["items"]}
    ratings: dict[str, str] = {}
    if args.ratings and Path(args.ratings).exists():
        ratings = json.loads(Path(args.ratings).read_text(encoding="utf-8"))["ratings"].get(args.profile, {})

    report = run_checks(rows, sample_ids, ratings, resolve_executives)
    _print(report)
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nwrote {args.out}")
    if args.snapshot_out:
        snapshot = stored_snapshot(rows, args.profile)
        Path(args.snapshot_out).write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.snapshot_out} ({len(snapshot)} stored-fact decisions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
