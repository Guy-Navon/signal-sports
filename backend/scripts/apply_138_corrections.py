"""Apply ONLY the #138 corrections, isolated by construction (#113 discipline).

#138 aligned the event proposal lists with the validation tables:
  * departure forms ("נפרד מ", "נפרדו מ", "עוזב את", "עוזבת את", "פרידה") now PROPOSE
    release — validation had learned them under #113 but proposals never offered them;
  * anticipated-completion forms ("צפוי/ה לצרף", "צפוי/ה להצטרף") are negotiation
    evidence, so a secondary clause's completed-transaction keyword cannot promote the
    article to signing.

Scope is EXACTLY the rows whose title/subtitle contains one of the change's patterns —
recomputing anything else would fold unrelated staleness into this delta and launder it
as a correction. "נפרדה מ" (feminine) predates #138 in both tables and is deliberately
NOT a scoping pattern.

DRY RUN BY DEFAULT. `--apply` writes; the protected live corpus (#106) additionally
requires `--i-know-this-is-the-live-corpus`.
"""
import argparse
import io
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The change's patterns, and ONLY the change's patterns (scoping, not classification —
# the actual decision is recomputed through the real classifier below).
_CHANGE_PATTERNS = (
    "נפרד מ", "נפרדו מ", "עוזב את", "עוזבת את", "פרידה",
    "צפוי לצרף", "צפויה לצרף", "צפוי להצטרף", "צפויה להצטרף",
)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--i-know-this-is-the-live-corpus", action="store_true")
    ap.add_argument("--out", help="write the row-by-row JSON log here")
    args = ap.parse_args()
    db = Path(args.db).resolve()

    os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"
    from app.db.corpus_protection import is_protected_corpus_db
    if args.apply and is_protected_corpus_db() and not args.i_know_this_is_the_live_corpus:
        raise SystemExit(
            f"REFUSED: {db} is the protected live corpus (#106).\n"
            "Re-run with --i-know-this-is-the-live-corpus to write to it."
        )

    from app.classification.source_hints import extract_source_sport_hint
    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow
    from app.ingestion.classifier import classify

    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    s = SessionLocal()
    log = []
    scoped = 0
    for a in s.query(ArticleRow).all():
        text = f"{a.title or ''} {a.subtitle or ''}"
        if not any(p in text for p in _CHANGE_PATTERNS):
            continue
        scoped += 1
        hint = extract_source_sport_hint(a.source or "", a.url or "")
        r = classify(a.title or "", source_id=a.source or "",
                     language=a.language or "he", url=a.url or "",
                     subtitle=a.subtitle, source_sport_hint=hint)
        before = (a.event_type, a.event_certainty)
        after = (r.event_type, r.event_certainty)
        if before == after:
            continue
        log.append({"id": a.id, "source": a.source, "title": a.title,
                    "before": list(before), "after": list(after)})
        if args.apply:
            a.event_type, a.event_certainty = after
    if args.apply:
        s.commit()
    s.close()

    mode = "APPLIED" if args.apply else "DRY RUN — nothing written"
    print(f"#138 corrections ({mode}) on {db.name}: "
          f"{scoped} rows in scope, {len(log)} changed", file=out)
    for e in log:
        print(f"  [{e['source']:20}] {e['before']} -> {e['after']}  {e['title'][:58]}",
              file=out)
    out.flush()
    if args.out:
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(log, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
