"""Backfill ONLY the #125 title_win corrections onto stored rows.

Classification runs at INGESTION, so merging #125 fixes future articles while the false
`title_win` rows already in the corpus stay false — the aspirational Harry Kane quote keeps
sitting in the live feed at very_high importance. This script applies the new rules to the
rows that are already there.

DELIBERATELY THE NARROWEST POSSIBLE WRITE:
  * It reads ONLY rows whose stored event_type is a TITLE_LOCAL type (i.e. `title_win`).
    Nothing else in the corpus is even loaded, let alone touched.
  * It re-runs the SAME gate the ingestion pipeline runs (combined title+subtitle evidence,
    then the #125 title-locality check) — it does not invent a separate code path that could
    drift from production.
  * A demoted row's replacement event_type comes from the DETERMINISTIC classifier, exactly
    as `_apply_post_facts_event_validation` does. No LLM call. No reclassification run. The
    result is fully reproducible and every changed row is enumerated before anything is
    written.

DRY RUN BY DEFAULT. `--apply` is required to write, and writing to the protected live corpus
additionally requires `--i-know-this-is-the-live-corpus` (#106).
"""
import argparse
import io
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/signal_sports.db")
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--i-know-this-is-the-live-corpus", action="store_true")
    ap.add_argument("--out", help="write the change log as JSON")
    args = ap.parse_args()

    db = Path(args.db).resolve()
    os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

    from app.db.corpus_protection import is_protected_corpus_db

    protected = is_protected_corpus_db()
    if args.apply and protected and not args.i_know_this_is_the_live_corpus:
        raise SystemExit(
            f"REFUSED: {db} is the protected live corpus (#106).\n"
            "Re-run with --i-know-this-is-the-live-corpus to write to it."
        )

    from app.classification.event_evidence import (
        TITLE_LOCAL_EVENT_TYPES,
        validate_event_evidence,
    )
    from app.classification.source_hints import extract_source_sport_hint
    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow
    from app.ingestion.classifier import classify, compute_importance

    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    s = SessionLocal()

    rows = (
        s.query(ArticleRow)
        .filter(ArticleRow.event_type.in_(sorted(TITLE_LOCAL_EVENT_TYPES)))
        .order_by(ArticleRow.source, ArticleRow.published_at)
        .all()
    )
    print(f"db: {db}", file=out)
    print(f"scope: rows with a TITLE_LOCAL event_type ({', '.join(sorted(TITLE_LOCAL_EVENT_TYPES))})", file=out)
    print(f"candidates: {len(rows)}\n", file=out)

    log, kept = [], []
    for a in rows:
        title = (a.title or "").lower()
        subtitle = (a.subtitle or "").lower()
        combined = f"{title} {subtitle}".strip()
        src = "llm" if a.event_certainty == "weak" else "rules"

        # The production gate, in production's order.
        ev = validate_event_evidence(a.event_type, combined, source=src, sport=a.sport)
        demote = not ev.valid
        reason = "no_event_evidence"
        if not demote:
            title_ev = validate_event_evidence(a.event_type, title, source=src, sport=a.sport)
            if not title_ev.valid:
                demote = True
                reason = "title_local_subtitle_only"  # #125

        if not demote:
            kept.append(a)
            continue

        # Replacement type from the DETERMINISTIC classifier, as the pipeline does.
        hint = extract_source_sport_hint(a.source or "", a.url or "")
        r = classify(
            a.title or "", source_id=a.source or "", language=a.language or "he",
            url=a.url or "", subtitle=a.subtitle, source_sport_hint=hint,
        )
        new_event = r.event_type if r.event_type != a.event_type else "news"
        entities = json.loads(a.entities or "[]") if isinstance(a.entities, str) else (a.entities or [])
        new_importance = compute_importance(new_event, entities, a.league)

        log.append({
            "id": a.id, "source": a.source, "title": a.title,
            "before": {"event_type": a.event_type, "certainty": a.event_certainty,
                       "importance": a.importance},
            "after": {"event_type": new_event, "certainty": "confirmed",
                      "importance": new_importance},
            "reason": reason,
        })
        if args.apply:
            a.event_type = new_event
            a.event_certainty = "confirmed"
            a.importance = new_importance

    if args.apply:
        s.commit()
    s.close()

    print(f"── DEMOTE ({len(log)}) ─────────────────────────────────────────", file=out)
    for i, e in enumerate(log, 1):
        b, af = e["before"], e["after"]
        print(f"{i}. [{e['source']:18}] {b['event_type']}/{b['certainty']}/{b['importance']}"
              f"  ->  {af['event_type']}/{af['importance']}   ({e['reason']})", file=out)
        print(f"   {e['title'][:84]}", file=out)
    print(f"\n── KEEP ({len(kept)}) ───────────────────────────────────────────", file=out)
    for i, a in enumerate(kept, 1):
        print(f"{i}. [{a.source:18}] {a.event_type}/{a.event_certainty}/{a.importance}"
              f"  {(a.title or '')[:60]}", file=out)

    mode = "APPLIED" if args.apply else "DRY RUN — nothing written"
    print(f"\n{mode}: {len(log)} demoted, {len(kept)} kept", file=out)
    out.flush()

    if args.out:
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(log, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
