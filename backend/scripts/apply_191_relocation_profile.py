"""Apply the authorized G4b relocation override via the validated profile API.

Dry-run by default; preserves all existing user settings. Back up first.
"""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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
    from app.models.profile_v2 import OverrideRule
    from app.repositories.profile_repository import get_by_id
    if args.apply and is_protected_corpus_db() and not args.i_know_this_is_the_live_corpus:
        parser.error("Back up first and acknowledge the protected corpus")
    rule = OverrideRule(kind="always_push", scope="player", target_id="player:deni_avdija", event_type="relocation")
    with SessionLocal() as session:
        profile = get_by_id(session, "casual_deni_fan")
        if profile is None or profile.profile_v2 is None:
            parser.error("Persisted Deni v2 profile is required")
        if rule in profile.profile_v2.overrides:
            print("Already present; 0 changes")
            return 0
        profile.profile_v2.overrides.append(rule)
        payload = UserProfile.model_validate(profile.model_dump())
        if args.apply:
            put_profile(profile.user_id, payload, session=session, acting_admin=None)
        print(f"{'Applied' if args.apply else 'Would add'} exactly one Deni player-scoped relocation override; Guy unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
