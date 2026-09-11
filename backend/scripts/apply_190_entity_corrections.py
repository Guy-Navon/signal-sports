"""Targeted entity-attribution correction for issue #190 — NOT a backfill.

The ground truth (docs/qa/N05_FEED_GROUND_TRUTH.md) found 25 of Guy's 34
false-hides carrying no resolved competition. Diagnosis: 24 of the 25 had
`entities=[]` — no resolved entity at all. #190 fixed the causes in the
taxonomy and the resolver:

  - `team:maccabi_ashdod` and `team:hapoel_galil_elyon` were missing entirely
  - `team:hapoel_eilat` had no bare "אילת" alias
  - `team:hapoel_beer_sheva_bb` did not match the hyphenated "הפועל באר-שבע"
  - `team:ironi_ness_ziona` (guarded) could not resolve without sport evidence,
    while the sport was unknown *because* nothing resolved

Stored rows keep the facts they were written with, so this script re-attributes
the affected rows. Membership reach then derives `comp:ibl` at scoring time.

WHY THIS IS NOT A BLANKET BACKFILL
----------------------------------
F-N05-6 is explicit and this script obeys it: of 34 false-hides re-run through
fresh rules-only classification, **12 were degraded** (`basketball` → `unknown`)
because the stored rows carried LLM-assisted facts a rules-only pass cannot
reproduce. The stored row is usually better than what a backfill would write.

So the scope here is deliberately narrow:

  1. **Only the five entities above.** A row is a candidate only when the fixed
     resolver finds one of them that the row does not already carry. Re-running
     the resolver over the whole corpus would touch ~173 rows, most of them for
     reasons unrelated to #190 — measured, and rejected.
  2. **Only TITLE evidence.** A club named only in the subtitle is usually not
     the subject: measured on the candidates, subtitle-only matches were an
     opponent from last season ("נגד אשדוד"), a player's former club, a former
     coach ("המאמן לשעבר של עירוני נס ציונה"), and a misclassified football
     story. Every one of the 24 title matches was genuinely about the club.
     Mention-vs-subject is #193's job; until it lands, title evidence is the
     conservative proxy and subtitle-only rows are left alone.
  3. **Entity attribution ONLY** — `entity_ids` and `entities`. Not sport, not
     event type, not importance, not `primary_competition` (which stays
     explicit-evidence-only by contract, #28, so the RC-4 hazard of promoting a
     background mention is untouched).

Additive by construction: entities are added, never removed. A row that already
carries the entity is not a candidate, which is what makes re-runs idempotent.

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts/apply_190_entity_corrections.py --db data/signal_sports.db
    ... --apply --i-know-this-is-the-live-corpus --out ../docs/qa/n190_entity_corrections.json

Dry run by default. Writing to the protected live corpus additionally requires
`--i-know-this-is-the-live-corpus`, and a backup should exist first
(`scripts/backup_db.py`).
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The entities #190 added or unblocked, and ONLY those. Scoping, not deciding —
# the attribution itself is recomputed through the real resolver below.
IN_SCOPE_ENTITY_IDS = frozenset({
    "team:maccabi_ashdod",
    "team:hapoel_galil_elyon",
    "team:hapoel_eilat",
    "team:ironi_ness_ziona",
    "team:hapoel_beer_sheva_bb",
})


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
            # TITLE only — see the module docstring. The subtitle is deliberately
            # excluded, not overlooked.
            title = row.translated_title or row.title
            if not title:
                continue

            sport = row.sport if row.sport in ("basketball", "football") else None
            resolution = resolve_entities(title, sport_context=sport)

            existing = list(row.entity_ids or [])
            gained = [
                e.id for e in resolution.resolved
                if e.id in IN_SCOPE_ENTITY_IDS and e.id not in existing
            ]
            if not gained:
                continue

            new_ids = existing + gained
            new_names = [ENTITIES[eid].legacy_name for eid in new_ids if eid in ENTITIES]
            changes.append({
                "id": row.id,
                "title": title,
                "sport": row.sport,
                "event_type": row.event_type,
                "league_before": row.league,
                "gained": gained,
                "entity_ids_before": existing,
                "entity_ids_after": new_ids,
            })
            if args.apply:
                row.entity_ids = new_ids
                row.entities = new_names

        if args.apply:
            session.commit()

    verb = "corrected" if args.apply else "would correct"
    print(f"db={db}  protected={protected}")
    print(f"{verb} {len(changes)} rows — entity attribution only; sport, event "
          f"type, importance and primary_competition untouched")
    for c in changes:
        short = [g.replace("team:", "") for g in c["gained"]]
        print(f"  +{str(short):26} {c['title'][:58]}")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "issue": 190,
            "applied": bool(args.apply),
            "database": str(db),
            "in_scope_entity_ids": sorted(IN_SCOPE_ENTITY_IDS),
            "evidence_scope": "title only (subtitle-only mentions deliberately excluded — see #193)",
            "fields_written": ["entity_ids", "entities"],
            "rows": changes,
        }, ensure_ascii=False, indent=2), encoding="utf-8", newline="")
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
