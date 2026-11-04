"""Remove always_push:injury from the persisted profiles (owner decision 2026-11-04, #423).

Injuries are not a push for now. The seed no longer carries these rules, but seed backfill
never touches an existing profile. Dry-run by default; idempotent. Back up first.
"""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def plan_changes(v2) -> list[str]:
    """Drop every always_push injury rule from ``v2`` in place; return what was removed."""
    gone = [r for r in v2.overrides if r.kind == "always_push" and r.event_type == "injury"]
    v2.overrides = [r for r in v2.overrides if r not in gone]
    return [f"{r.scope} {r.target_id}" for r in gone]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--i-know-this-is-the-live-corpus", action="store_true")
    args = parser.parse_args()
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(args.db).resolve().as_posix()}"
    from app.api.routes_profiles import put_profile
    from app.db.corpus_protection import is_protected_corpus_db
    from app.db.database import SessionLocal
    from app.models.profile import UserProfile
    from app.repositories.profile_repository import get_all
    if args.apply and is_protected_corpus_db() and not args.i_know_this_is_the_live_corpus:
        parser.error("Back up first and acknowledge the protected corpus")
    with SessionLocal() as session:
        for profile in get_all(session):
            if profile.profile_v2 is None:
                continue
            removed = plan_changes(profile.profile_v2)
            if not removed:
                continue
            if args.apply:
                put_profile(profile.user_id, UserProfile.model_validate(profile.model_dump()),
                            session=session, acting_admin=None)
            print(f"{profile.user_id}: {'removed' if args.apply else 'would remove'} {removed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
