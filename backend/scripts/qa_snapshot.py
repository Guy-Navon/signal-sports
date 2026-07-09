"""Snapshot per-article facts + per-profile feed decisions for reliability QA.

Created for issue #59 (baseline) and consumed by issue #63 (corpus replay diff).

Usage (from backend/):
    .venv\\Scripts\\python.exe scripts/qa_snapshot.py --out ../docs/qa/reliability_baseline.json

Notes:
- Read-only: never mutates the corpus DB.
- Scores both demo profiles with the raw persisted profile via
  ``score_article_v2`` (no learned-adjustment augmentation), so snapshots are
  deterministic and comparable across runs regardless of feedback activity.
- Only RSS articles (``id`` starting with ``rss_``) are included — the same
  population the product feed serves.
"""

import argparse
import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import SessionLocal  # noqa: E402
from app.repositories import article_repository, profile_repository  # noqa: E402
from app.services.preference_engine import score_article_v2  # noqa: E402

PROFILE_IDS = ("guy", "casual_deni_fan")


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def build_snapshot() -> dict:
    session = SessionLocal()
    profiles = {uid: profile_repository.get_by_id(session, uid) for uid in PROFILE_IDS}
    for uid, prof in profiles.items():
        assert prof is not None, f"profile {uid} missing — is this the corpus DB?"

    articles = [a for a in article_repository.get_all(session) if a.id.startswith("rss_")]
    articles.sort(key=lambda a: a.id)

    rows = []
    for art in articles:
        row = {
            "id": art.id,
            "source": art.source,
            "title": art.title,
            "sport": art.sport,
            "league": art.league,
            "event_type": art.event_type,
            "event_certainty": art.event_certainty,
            "importance": art.importance,
            "entities": list(art.entities or []),
            "entity_ids": list(art.entity_ids or []),
            "primary_competition": art.primary_competition,
            "article_competitions": list(art.article_competitions or []),
            "classified_by": art.classified_by,
            "taxonomy_version": art.taxonomy_version,
        }
        for uid in PROFILE_IDS:
            result = score_article_v2(art, profiles[uid])
            key = "guy" if uid == "guy" else "deni"
            row[key] = result.decision
            row[f"{key}_rule"] = result.matched_event_rule
            row[f"{key}_topic"] = result.matched_topic
        rows.append(row)

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "article_count": len(rows),
        "profiles": list(PROFILE_IDS),
        "articles": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="output JSON path")
    args = parser.parse_args()

    snapshot = build_snapshot()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(snapshot, fh, ensure_ascii=False, indent=1)
    print(f"wrote {snapshot['article_count']} articles -> {out_path}")


if __name__ == "__main__":
    main()
