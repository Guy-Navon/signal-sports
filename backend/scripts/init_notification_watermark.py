"""M7-10 (#156) — guarded, one-time notification watermark initialization.

THE ACTIVATION RULE (docs/NOTIFICATIONS.md): enabling Telegram must not flood
Guy with every PUSH story already sitting in the feed. This script:

  1. enumerates the profile's CURRENT push-tier stories through the exact
     production planner path (`enumerate_push_stories` — the same single
     implementation the per-cycle planner uses; no second ruleset);
  2. sets the (profile, policy) watermark row — the planner refuses to plan
     anything until this exists (fail-closed);
  3. plants a `suppressed_watermark` event WITH full member lineage for each
     currently-eligible story — so the DB uniqueness that blocks duplicate
     notifications is exactly what blocks the historical flood, auditable
     forever, and structurally undeliverable (the dispatcher only claims
     pending/failed_retryable).

Ordering safety: this runs while `TELEGRAM_NOTIFICATIONS_ENABLED=false`. The
planner gates on the enable flag BEFORE the watermark, so cycles between this
initialization and the flag flip plan nothing.

Idempotent: `set_watermark` returns the existing row on re-run, and re-planting
routes to the already-notified path (no duplicate events, no status change).

DRY-RUN BY DEFAULT. Mutating the live corpus DB requires BOTH
`--apply` and `--i-know-this-is-the-live-corpus` (repository convention for
guarded corpus writers).

Run from backend/:  .venv\\Scripts\\python.exe scripts/init_notification_watermark.py
"""
from __future__ import annotations

import argparse
import pathlib
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="write the watermark + suppressed events")
    parser.add_argument("--i-know-this-is-the-live-corpus", action="store_true",
                        help="second opt-in required to mutate the live corpus DB")
    args = parser.parse_args()

    backend = pathlib.Path(__file__).resolve().parents[1]
    env_file = backend / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)

    sys.path.insert(0, str(backend))
    from app.db.database import SessionLocal, init_db
    from app.notifications.outbox import (
        SUPPRESSED_WATERMARK,
        already_notified,
        get_watermark,
        plan_story,
        set_watermark,
    )
    from app.notifications.planner import (
        enumerate_push_stories,
        pilot_profile_id,
        policy_version,
    )

    profile, policy = pilot_profile_id(), policy_version()
    init_db()

    with SessionLocal() as session:
        existing = get_watermark(session, profile, policy)
        if existing is not None:
            print(f"Watermark for ({profile}, {policy}) already exists — "
                  f"activated_at={existing.activated_at}, "
                  f"suppressed_story_count={existing.suppressed_story_count}. "
                  "Nothing to do (idempotent).")
            return 0

        enumerated = enumerate_push_stories(session, profile)
        if enumerated is None:
            print(f"ERROR: profile {profile!r} not found.")
            return 1
        snapshots, ignored = enumerated

        print(f"Profile {profile!r}, policy {policy!r}")
        print(f"Current PUSH stories that would be SUPPRESSED (never notified): "
              f"{len(snapshots)}   (non-push stories ignored: {ignored})")
        for s in snapshots:
            gov = already_notified(session, profile, policy, s.member_article_ids)
            marker = f"  [lineage already exists: {gov}]" if gov else ""
            print(f"  - {s.canonical_headline[:70]}  "
                  f"({s.source}, {len(s.member_article_ids)} member(s), "
                  f"cluster={s.cluster_id or '—'}){marker}")

        if not (args.apply and args.i_know_this_is_the_live_corpus):
            print("\nDRY RUN — nothing written. To apply:")
            print("  scripts/init_notification_watermark.py --apply "
                  "--i-know-this-is-the-live-corpus")
            return 0

        set_watermark(session, profile, policy)
        planted = 0
        for s in snapshots:
            out = plan_story(session, profile_id=profile, policy_version=policy,
                             story=s, initial_status=SUPPRESSED_WATERMARK)
            if out.outcome == "created":
                planted += 1
        row = get_watermark(session, profile, policy)
        row.suppressed_story_count = planted
        session.commit()
        print(f"\nAPPLIED: watermark set (activated_at={row.activated_at}); "
              f"{planted} historical PUSH stories suppressed with full lineage.")
        print("Telegram remains DISABLED until the flag flip — the planner "
              "gates on TELEGRAM_NOTIFICATIONS_ENABLED before the watermark.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
