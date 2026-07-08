"""
ProfileV2 — affinity-based preference model (issue #32).

Replaces the mode/event-rule topic approximations with three explicit layers:

- ``scope_affinities`` — graded interest in a scope (sport / competition /
  team / player), level -2 (exclude) … +2 (very_high), with provenance
  (explicit | calibration | learned).
- ``event_affinities`` — per-scope or global event-type deltas (-2..+2) that
  move ranking *within* legitimate visibility.
- ``overrides`` — absolute rules: mute / never_show (always hidden) and
  always_push (the ONLY path to push in the v2 scorer).

Provenance contract: learned entries never override explicit ones — the
scorer resolves duplicate targets by source authority (explicit >
calibration > learned) before levels are compared.

Stored as JSON on the profiles row (``profile_v2`` column, soft migration),
coexisting with legacy ``topics`` during the migration window. Python-only:
the JS engine is frozen at its current feature set and receives no port.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

PROFILE_V2_VERSION = 2

ScopeKind = Literal["sport", "competition", "team", "player"]
AffinitySource = Literal["explicit", "calibration", "learned"]

# level -2..+2 → human name (used in traces and the Preferences UI)
AFFINITY_LEVEL_NAMES = {
    -2: "exclude",
    -1: "low",
    0: "medium",
    1: "high",
    2: "very_high",
}

# Source authority for duplicate-target resolution: learned never overrides
# explicit (architecture contract).
SOURCE_AUTHORITY = {"explicit": 3, "calibration": 2, "learned": 1}


def _validate_scope_target(kind: str, target_id: str) -> None:
    if kind == "competition" and not target_id.startswith("comp:"):
        raise ValueError(f"competition target must be a comp:* id, got {target_id!r}")
    if kind == "team" and not target_id.startswith("team:"):
        raise ValueError(f"team target must be a team:* id, got {target_id!r}")
    if kind == "player" and not target_id.startswith(("player:", "coach:")):
        raise ValueError(f"player target must be a player:*/coach:* id, got {target_id!r}")
    if kind == "sport" and ":" in target_id:
        raise ValueError(f"sport target must be a bare sport name, got {target_id!r}")


class ScopeAffinity(BaseModel):
    scope: ScopeKind
    target_id: str                     # sport name | comp:* | team:* | player:*/coach:*
    level: int = Field(ge=-2, le=2)    # exclude(-2) … very_high(+2)
    source: AffinitySource = "explicit"
    evidence_count: int = 0
    updated_at: Optional[datetime] = None

    @field_validator("target_id")
    @classmethod
    def _target_matches_scope(cls, v, info):
        kind = info.data.get("scope")
        if kind:
            _validate_scope_target(kind, v)
        return v


class EventAffinity(BaseModel):
    # None = global delta for this event type; otherwise the target_id of a
    # scope affinity this delta is scoped to.
    scope_ref: Optional[str] = None
    event_type: str
    delta: int = Field(ge=-2, le=2)
    source: AffinitySource = "explicit"
    evidence_count: int = 0
    updated_at: Optional[datetime] = None


class OverrideRule(BaseModel):
    kind: Literal["mute", "never_show", "always_push"]
    scope: ScopeKind
    target_id: str
    # always_push may be narrowed to one event type; mute/never_show may too
    # (None = any event on the target).
    event_type: Optional[str] = None
    source: Literal["explicit"] = "explicit"   # overrides are explicit-only

    @field_validator("target_id")
    @classmethod
    def _target_matches_scope(cls, v, info):
        kind = info.data.get("scope")
        if kind:
            _validate_scope_target(kind, v)
        return v


class ProfileV2(BaseModel):
    version: int = PROFILE_V2_VERSION
    scope_affinities: List[ScopeAffinity] = Field(default_factory=list)
    event_affinities: List[EventAffinity] = Field(default_factory=list)
    overrides: List[OverrideRule] = Field(default_factory=list)

    def effective_scope_affinities(self) -> List[ScopeAffinity]:
        """Duplicate-target resolution by source authority: for the same
        (scope, target_id), an explicit entry beats calibration beats learned;
        equal-authority duplicates keep the last one (latest write wins)."""
        by_target: dict[tuple[str, str], ScopeAffinity] = {}
        for aff in self.scope_affinities:
            key = (aff.scope, aff.target_id)
            existing = by_target.get(key)
            if existing is None or (
                SOURCE_AUTHORITY[aff.source] >= SOURCE_AUTHORITY[existing.source]
            ):
                by_target[key] = aff
        return list(by_target.values())
