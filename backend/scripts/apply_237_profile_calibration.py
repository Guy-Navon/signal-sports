"""Add Guy's two owner-approved calibration entries (#237) via the validated profile API.

Census #2, after the owner's blind review of the 58 largest disagreements, showed two
consistent biases that held on a held-out half:
  - team:maccabi_tlv_bb × candidate  → -1  (speculation around Maccabi: high_feed → feed)
  - comp:euroleague × news           → +1  (general EuroLeague stories: low_feed → feed)
The seed carries both, but seed backfill never touches an existing profile.

Dry-run by default; refuses to overwrite an existing entry with a different delta;
idempotent. Back up first.
"""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ENTRIES = (
    ("team:maccabi_tlv_bb", "candidate", -1),
    ("comp:euroleague", "news", 1),
)


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
    from app.models.profile_v2 import EventAffinity
    from app.repositories.profile_repository import get_by_id
    if args.apply and is_protected_corpus_db() and not args.i_know_this_is_the_live_corpus:
        parser.error("Back up first and acknowledge the protected corpus")
    with SessionLocal() as session:
        profile = get_by_id(session, "guy")
        if profile is None or profile.profile_v2 is None:
            parser.error("Persisted Guy v2 profile is required")
        affinities = profile.profile_v2.event_affinities
        added = []
        for scope_ref, event_type, delta in ENTRIES:
            existing = [e for e in affinities
                        if e.scope_ref == scope_ref and e.event_type == event_type and e.source == "explicit"]
            if existing:
                if existing[0].delta != delta:
                    parser.error(f"{scope_ref} × {event_type} already explicit with delta "
                                 f"{existing[0].delta}; refusing to overwrite")
                continue
            affinities.append(EventAffinity(scope_ref=scope_ref, event_type=event_type, delta=delta))
            added.append(f"{scope_ref} × {event_type} {delta:+d}")
        if not added:
            print("Already present; 0 changes")
            return 0
        payload = UserProfile.model_validate(profile.model_dump())
        if args.apply:
            put_profile(profile.user_id, payload, session=session, acting_admin=None)
        print(f"{'Applied' if args.apply else 'Would add'} {len(added)}: {'; '.join(added)}; Deni unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
