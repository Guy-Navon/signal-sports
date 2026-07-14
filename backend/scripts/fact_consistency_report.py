"""Cross-source fact-consistency oracle report (#113) — READ-ONLY.

    python scripts/fact_consistency_report.py --db data/qa_snapshot_102.db

Surfaces near-identical cross-source article pairs whose FACTS disagree. Diagnostic only:
it never rewrites facts, never merges stories, never creates cluster membership. Similarity
means "probably the same event" — it does NOT prove either article is correct.
"""
import argparse, io, json, os, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _dt(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()

    db = Path(args.db).resolve()
    os.environ["DATABASE_URL"] = f"sqlite:///{db.as_posix()}"

    from app.db.database import SessionLocal
    from app.db.orm_models import ArticleRow
    from app.qa.fact_consistency import ArticleFactsView, find_disagreements

    s = SessionLocal()
    views = [
        ArticleFactsView(
            id=a.id, source=a.source, title=a.title or "", subtitle=a.subtitle or "",
            published_at=_dt(a.published_at), sport=a.sport or "unknown",
            event_type=a.event_type or "news",
            entity_ids=tuple(a.entity_ids or ()),
            primary_competition=a.primary_competition,
        )
        for a in s.query(ArticleRow).all()
    ]
    found = find_disagreements(views)
    s.close()

    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    print(f"\n=== cross-source fact disagreements [{db.name}] ===", file=out)
    print(f"articles audited: {len(views)}   disagreements: {len(found)}\n", file=out)
    for d in found:
        print(f"J={d.similarity:.2f} {d.hours_apart}h  {', '.join(d.kinds)}", file=out)
        print(f"  [{d.source_a}] {d.detail['title_a'][:76]}", file=out)
        print(f"  [{d.source_b}] {d.detail['title_b'][:76]}", file=out)
        print(f"  sport={d.detail['sport']} event={d.detail['event_type']}", file=out)
        print("", file=out)
    out.flush()

    if args.out:
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump([d.__dict__ | {"kinds": list(d.kinds)} for d in found],
                      fh, ensure_ascii=False, indent=1, default=str)
        print(f"report -> {args.out}", file=out)
        out.flush()


if __name__ == "__main__":
    main()
