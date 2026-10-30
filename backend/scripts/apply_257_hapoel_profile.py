"""Add Guy's owner-approved Hapoel Tel Aviv basketball entries (#257) via the validated profile API.

Owner decision (2026-10-26): for Guy's profile, feed is the baseline for Hapoel Tel Aviv
basketball coverage, high where justified; profile-specific, not a global rule. The seed
carries the entries below, but seed backfill never touches an existing profile:
  - scope  team:hapoel_tlv_bb level 0 (medium)
  - events team:hapoel_tlv_bb × news +2, match_result / interview / analysis / opinion /
    club_governance +1

Dry-run by default; refuses to overwrite an existing explicit entry with a different value;
idempotent. Touches Guy only. Back up first.
"""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TEAM = "team:hapoel_tlv_bb"
SCOPE_LEVEL = 0
EVENTS = (
    ("news", 2),
    ("match_result", 1),
    ("interview", 1),
    ("analysis", 1),
    ("opinion", 1),
    ("club_governance", 1),
)


class Conflict(ValueError):
    pass


def plan_changes(v2) -> list[str]:
    """Add the #257 entries to ``v2`` in place; return what was added.

    Raises Conflict when an explicit entry for the same target already holds a
    different value — that is an owner edit this script must not overwrite.
    """
    from app.models.profile_v2 import EventAffinity, ScopeAffinity

    added = []
    scopes = [a for a in v2.scope_affinities
              if a.scope == "team" and a.target_id == TEAM and a.source == "explicit"]
    if scopes:
        if scopes[0].level != SCOPE_LEVEL:
            raise Conflict(f"{TEAM} already explicit at level {scopes[0].level}; refusing to overwrite")
    else:
        v2.scope_affinities.append(ScopeAffinity(scope="team", target_id=TEAM, level=SCOPE_LEVEL))
        added.append(f"scope {TEAM} level {SCOPE_LEVEL}")
    for event_type, delta in EVENTS:
        existing = [e for e in v2.event_affinities
                    if e.scope_ref == TEAM and e.event_type == event_type and e.source == "explicit"]
        if existing:
            if existing[0].delta != delta:
                raise Conflict(f"{TEAM} × {event_type} already explicit with delta "
                               f"{existing[0].delta}; refusing to overwrite")
            continue
        v2.event_affinities.append(EventAffinity(scope_ref=TEAM, event_type=event_type, delta=delta))
        added.append(f"{TEAM} × {event_type} {delta:+d}")
    return added


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
        try:
            added = plan_changes(profile.profile_v2)
        except Conflict as exc:
            parser.error(str(exc))
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
