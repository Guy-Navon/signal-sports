"""Remove guy's −1 on Maccabi game results (#585) via the validated profile API.

Owner decision 2026-11-18: a Maccabi Tel Aviv game result is high (4+), not feed.
The seed no longer carries these three entries, but seed backfill never touches an
existing profile, so the live one is updated here:
  - team:maccabi_tlv_bb × match_result          −1  → removed
  - team:maccabi_tlv_bb × regular_season_result −1  → removed
  - team:maccabi_tlv_bb × match_summary         −1  → removed
News, interview, analysis and opinion keep their −1.

Dry-run by default; refuses when an entry carries a delta other than −1 (someone
changed it on purpose); idempotent. Back up first.
"""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCOPE = "team:maccabi_tlv_bb"
EVENT_TYPES = ("match_result", "regular_season_result", "match_summary")
EXPECTED_DELTA = -1


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
    from app.repositories.profile_repository import get_by_id
    if args.apply and is_protected_corpus_db() and not args.i_know_this_is_the_live_corpus:
        parser.error("Back up first and acknowledge the protected corpus")
    with SessionLocal() as session:
        profile = get_by_id(session, "guy")
        if profile is None or profile.profile_v2 is None:
            parser.error("Persisted Guy v2 profile is required")
        v2 = profile.profile_v2
        targets = [e for e in v2.event_affinities
                   if e.scope_ref == SCOPE and e.event_type in EVENT_TYPES
                   and e.source == "explicit"]
        for e in targets:
            if e.delta != EXPECTED_DELTA:
                parser.error(f"{SCOPE} × {e.event_type} is explicit with delta {e.delta:+d}, "
                             f"not {EXPECTED_DELTA:+d}; refusing to change it")
        if not targets:
            print("Already removed; 0 changes")
            return 0
        v2.event_affinities = [e for e in v2.event_affinities if e not in targets]
        payload = UserProfile.model_validate(profile.model_dump())
        if args.apply:
            put_profile(profile.user_id, payload, session=session, acting_admin=None)
        removed = "; ".join(f"{SCOPE} × {e.event_type} {e.delta:+d}" for e in targets)
        print(f"{'Removed' if args.apply else 'Would remove'} {len(targets)}: {removed}; "
              "Deni unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
