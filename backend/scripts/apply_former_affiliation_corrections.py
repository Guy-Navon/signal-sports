"""Apply ONLY the former-affiliation entity corrections (#113 discipline).

The resolver change: an alias occurrence touching a former-affiliation marker
("אקס ", " לשעבר", "ex-", "former ") names a club without making it a subject of
the story, so it no longer resolves to an entity. Found by the N05 ground-truth
pass — "אקס מכבי תל אביב חתם בקבוצה חדשה" resolved to Maccabi Tel Aviv and rode
that club's always_push override to a phone notification.

The rule only affects NEW classification; stored rows keep the old attribution.
This corrects exactly those stored rows.

Scope is EXACTLY the rows whose text contains one of the markers AND whose
re-resolved entity set actually loses an entity because of it. Recomputing
anything else would fold unrelated staleness into this delta and launder it as
a correction — and it would be actively harmful here: a rules-only pass loses
the LLM-assisted sport detection that 15 of 34 sampled rows depend on (N05
finding F-N05-6). So this script NEVER rewrites sport, event_type, importance
or any other fact. It rewrites entity attribution and nothing else.

DRY RUN BY DEFAULT. `--apply` writes; the protected live corpus (#106)
additionally requires `--i-know-this-is-the-live-corpus`.

Usage:
    .venv\\Scripts\\python.exe scripts/apply_former_affiliation_corrections.py \\
        --db data/signal_sports.db --out ../docs/qa/n05_former_affiliation_log.json
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The change's markers, and ONLY the change's markers. Scoping, not deciding —
# the actual attribution is recomputed through the real resolver below.
_MARKERS = ("אקס ", " לשעבר", " לעבר", "ex-", "ex ", "former ")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--i-know-this-is-the-live-corpus", action="store_true")
    ap.add_argument("--out", help="write the row-by-row JSON log here")
    args = ap.parse_args()

    db = Path(args.db).resolve()
    os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

    from app.db.corpus_protection import is_protected_corpus_db
    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow
    from app.taxonomy.entities import ENTITIES
    from app.taxonomy.resolver import resolve_entities

    protected = is_protected_corpus_db()
    if args.apply and protected and not args.i_know_this_is_the_live_corpus:
        print("Refusing: that is the live corpus. Re-run with "
              "--i-know-this-is-the-live-corpus once a backup exists.")
        return 2

    changes = []
    with SessionLocal() as session:
        rows = session.query(ArticleRow).filter(
            ArticleRow.id.startswith("rss_", autoescape=True)
        ).all()

        for row in rows:
            text = f"{row.translated_title or row.title} {row.subtitle or ''}".lower()
            if not any(m in text for m in _MARKERS):
                continue
            if not row.entity_ids:
                continue

            sport = row.sport if row.sport in ("basketball", "football") else None
            resolution = resolve_entities(text, sport_context=sport)
            if not resolution.former_affiliations:
                continue

            keep = [e.id for e in resolution.resolved]
            dropped = [eid for eid in row.entity_ids if eid not in keep]
            if not dropped:
                continue

            # Keep only the entities the fixed resolver still finds, preserving
            # the stored order so unrelated rows read the same as before.
            new_ids = [eid for eid in row.entity_ids if eid in keep]
            new_names = [ENTITIES[eid].legacy_name for eid in new_ids if eid in ENTITIES]
            changes.append({
                "id": row.id,
                "title": row.translated_title or row.title,
                "former_affiliations": resolution.former_affiliations,
                "entity_ids_before": list(row.entity_ids),
                "entity_ids_after": new_ids,
                "dropped": dropped,
            })
            if args.apply:
                row.entity_ids = new_ids
                row.entities = new_names

        if args.apply:
            session.commit()

    verb = "corrected" if args.apply else "would correct"
    print(f"db={db}  protected={protected}")
    print(f"{verb} {len(changes)} rows (facts other than entity attribution untouched)")
    for c in changes:
        print(f"  -{c['dropped']}  {c['title'][:58]}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "applied": bool(args.apply),
            "database": str(db),
            "rows": changes,
        }, ensure_ascii=False, indent=2), encoding="utf-8", newline="")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
