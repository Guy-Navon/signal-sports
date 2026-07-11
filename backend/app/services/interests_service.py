"""
Interests service (issue #77) — the explicit preference-acquisition layer.

Contract: docs/INTERESTS.md. Explicit interests are ordinary ProfileV2
entries (source="explicit"); this service is a WRITER of the existing model,
never a scoring participant. The scoring engine is frozen (#79 locks).

Managed explicit subset (replaced on every PUT, everything else preserved):
- ScopeAffinity entries with source="explicit" and level >= 0
- EventAffinity entries with source="explicit" and scope_ref=None

Explicitly NOT managed (must survive a PUT byte-for-byte): calibration and
learned entries, scoped explicit event deltas, negative-level explicit scope
affinities (seed nuance like Guy's comp:acb -1), overrides of any kind,
legacy mutes/topics.
"""
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.profile import UserProfile
from app.models.profile_v2 import EventAffinity, ProfileV2, ScopeAffinity, ScopeKind
from app.repositories import profile_repository
from app.taxonomy.policy import scope_target_selectable

# ── Tier → level mapping (checkpoint 1 decision: sport Follow = 0) ────────────

TIER_LEVELS: dict[str, dict[str, int]] = {
    "sport":       {"follow": 0, "star": 1},
    "competition": {"follow": 1, "star": 2},
    "team":        {"follow": 1, "star": 2},
    "player":      {"follow": 1, "star": 2},
}

# ── Event-preference presets (product groups → canonical event types) ─────────
# Groups expand into existing EventAffinity entries over the canonical event
# taxonomy — they are NOT new event types (docs/INTERESTS.md). The engine's
# alias map extends coverage to variants at match time.

EVENT_PRESET_GROUPS: dict[str, tuple[str, ...]] = {
    "transfers_rumors": ("signing", "negotiation", "candidate", "release",
                          "major_trade"),
    "injuries": ("injury",),
    "results": ("match_result", "playoff_result", "finals_result",
                 "title_win", "grand_slam_winner"),
    "interviews_features": ("interview",),
    "schedules_previews": ("schedule", "pre_match", "generic_preview"),
}

PresetState = Literal["less", "normal", "more"]
_PRESET_DELTAS: dict[str, int] = {"less": -1, "more": 1}


# ── API models ────────────────────────────────────────────────────────────────

class InterestFollow(BaseModel):
    model_config = {"extra": "forbid"}
    scope: ScopeKind
    target_id: str
    starred: bool = False


class InterestsPutRequest(BaseModel):
    """Identity-free by construction (extra="forbid": injected user_id → 422)."""
    model_config = {"extra": "forbid"}
    follows: List[InterestFollow] = Field(default_factory=list)
    event_preferences: Dict[str, PresetState] = Field(default_factory=dict)


class InterestsDocument(BaseModel):
    follows: List[InterestFollow]
    event_preferences: Dict[str, PresetState]
    completed: bool
    selected: int


class InterestsValidationError(ValueError):
    """Raised for unknown/non-selectable targets or unknown preset groups."""


# ── Managed-subset predicates ─────────────────────────────────────────────────

def _is_managed_scope(aff: ScopeAffinity) -> bool:
    return aff.source == "explicit" and aff.level >= 0


def _is_managed_event(ev: EventAffinity) -> bool:
    return ev.source == "explicit" and ev.scope_ref is None


def _tier_for_level(scope: str, level: int) -> Optional[bool]:
    """Reverse mapping: level → starred flag, None if not in the tier space."""
    tiers = TIER_LEVELS[scope]
    if level == tiers["follow"]:
        return False
    if level == tiers["star"]:
        return True
    return None


# ── Read: profile → interests document ────────────────────────────────────────

def interests_document(profile: UserProfile, completed: bool) -> InterestsDocument:
    v2 = profile.profile_v2 or ProfileV2()

    follows: List[InterestFollow] = []
    for aff in v2.scope_affinities:
        if not _is_managed_scope(aff):
            continue
        starred = _tier_for_level(aff.scope, aff.level)
        if starred is None:
            # Managed level outside the Follow/Star space (e.g. a sport at
            # +2 written by an older tool) — surface at the nearest tier.
            starred = aff.level >= TIER_LEVELS[aff.scope]["star"]
        follows.append(InterestFollow(
            scope=aff.scope, target_id=aff.target_id, starred=starred,
        ))

    # Reconstruct preset states from the stored global explicit deltas: a
    # group reads as less/more only if EVERY event type in its expansion
    # carries that delta (the PUT writes them atomically).
    global_deltas = {
        ev.event_type: ev.delta for ev in v2.event_affinities if _is_managed_event(ev)
    }
    event_preferences: Dict[str, PresetState] = {}
    for group, event_types in EVENT_PRESET_GROUPS.items():
        deltas = {global_deltas.get(et) for et in event_types}
        if deltas == {-1}:
            event_preferences[group] = "less"
        elif deltas == {1}:
            event_preferences[group] = "more"

    return InterestsDocument(
        follows=follows,
        event_preferences=event_preferences,
        completed=completed,
        selected=len(follows),
    )


# ── Write: validate + replace the managed subset ──────────────────────────────

def _validate(payload: InterestsPutRequest) -> None:
    seen: set[tuple[str, str]] = set()
    for follow in payload.follows:
        key = (follow.scope, follow.target_id)
        if key in seen:
            raise InterestsValidationError(
                f"duplicate follow target: {follow.scope}:{follow.target_id}"
            )
        seen.add(key)
        if not scope_target_selectable(follow.scope, follow.target_id):
            raise InterestsValidationError(
                f"unknown or non-selectable target: {follow.scope}:{follow.target_id}"
            )
    for group in payload.event_preferences:
        if group not in EVENT_PRESET_GROUPS:
            raise InterestsValidationError(f"unknown event preset group: {group}")


def _build_managed_entries(
    payload: InterestsPutRequest, now: datetime
) -> tuple[List[ScopeAffinity], List[EventAffinity]]:
    scopes = [
        ScopeAffinity(
            scope=f.scope,
            target_id=f.target_id,
            level=TIER_LEVELS[f.scope]["star" if f.starred else "follow"],
            source="explicit",
            updated_at=now,
        )
        for f in payload.follows
    ]
    events: List[EventAffinity] = []
    for group, state in payload.event_preferences.items():
        delta = _PRESET_DELTAS.get(state)
        if delta is None:  # "normal" → no entry
            continue
        for event_type in EVENT_PRESET_GROUPS[group]:
            events.append(EventAffinity(
                scope_ref=None, event_type=event_type, delta=delta,
                source="explicit", updated_at=now,
            ))
    return scopes, events


def replace_managed_interests(
    session: Session, profile: UserProfile, payload: InterestsPutRequest
) -> UserProfile:
    """Full replace of the managed explicit subset; raises
    InterestsValidationError on bad targets. Persists the profile row."""
    _validate(payload)
    now = datetime.now(tz=timezone.utc)
    new_scopes, new_events = _build_managed_entries(payload, now)

    v2 = profile.profile_v2 or ProfileV2()
    kept_scopes = [a for a in v2.scope_affinities if not _is_managed_scope(a)]
    kept_events = [e for e in v2.event_affinities if not _is_managed_event(e)]
    profile.profile_v2 = ProfileV2(
        scope_affinities=[*kept_scopes, *new_scopes],
        event_affinities=[*kept_events, *new_events],
        overrides=list(v2.overrides),
    )
    profile_repository.update(session, profile)
    return profile


# ── Interest-stage completion (process state, separate from preferences) ──────

def interests_completed(user) -> bool:
    """Effective completion. Legacy users (onboarding done before the
    interests stage existed) are treated as complete — never re-funneled."""
    return (
        getattr(user, "interests_completed_at", None) is not None
        or user.onboarding_completed_at is not None
    )


def complete_interests(session: Session, user) -> None:
    """Stamp interests_completed_at exactly once (idempotent). Never cleared:
    a user who later removes all selections stays completed (empty-feed CTA,
    no re-funnel)."""
    if user.interests_completed_at is None:
        user.interests_completed_at = datetime.now(tz=timezone.utc).isoformat()
        session.commit()
        session.refresh(user)
