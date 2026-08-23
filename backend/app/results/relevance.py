"""Per-user results relevance (issue #178).

Relevance is derived ENTIRELY from the existing ProfileV2 affinity model — no
results-specific preference system. A game is relevant when:

  1. either team is an explicitly FOLLOWED team (team affinity, level >= 1), or
  2. either team is the current team of a FOLLOWED player/coach (so the casual
     Deni fan sees Portland without following the franchise), or
  3. the game's competition is a FOLLOWED competition (level >= 1).

Sport-level follows do NOT make results relevant — that is the guard against
turning the page into a generic scoreboard (a Follow on the sport is level 0).

Everything here is a pure function of (profile, game) so it is fully unit
tested and identical on every read.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.db.orm_models import GameResultRow
from app.models.profile import UserProfile
from app.taxonomy.entities import entity_by_id

# Follow threshold: team/competition/player "Follow" maps to level 1
# (Star = 2). Level 0 (sport Follow) and negatives do not qualify.
FOLLOW_THRESHOLD = 1


@dataclass(frozen=True)
class FollowedTargets:
    team_ids: frozenset[str] = field(default_factory=frozenset)
    competition_ids: frozenset[str] = field(default_factory=frozenset)
    # team_id -> the followed player/coach that put it in scope (for the reason)
    team_via_player: dict[str, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.team_ids and not self.competition_ids


def followed_targets(profile: UserProfile) -> FollowedTargets:
    v2 = getattr(profile, "profile_v2", None)
    if v2 is None:
        return FollowedTargets()

    teams: set[str] = set()
    comps: set[str] = set()
    via_player: dict[str, str] = {}

    direct_team_ids: set[str] = set()
    for aff in v2.effective_scope_affinities():
        if aff.level < FOLLOW_THRESHOLD:
            continue
        if aff.scope == "team":
            teams.add(aff.target_id)
            direct_team_ids.add(aff.target_id)
        elif aff.scope == "competition":
            comps.add(aff.target_id)
        elif aff.scope == "player":
            entity = entity_by_id(aff.target_id)
            if entity and entity.team_id:
                teams.add(entity.team_id)
                via_player.setdefault(entity.team_id, aff.target_id)

    # A directly-followed team is a stronger reason than a player-derived one.
    via_player = {t: p for t, p in via_player.items() if t not in direct_team_ids}

    return FollowedTargets(
        team_ids=frozenset(teams),
        competition_ids=frozenset(comps),
        team_via_player=via_player,
    )


def relevance_reason(row: GameResultRow, followed: FollowedTargets) -> Optional[str]:
    """The reason a game is relevant, or None if it is not. Team follows win
    over competition follows (more specific)."""
    for team_id in (row.home_team_id, row.away_team_id):
        if team_id and team_id in followed.team_ids:
            player = followed.team_via_player.get(team_id)
            if player:
                return f"followed_player_team:{player}:{team_id}"
            return f"followed_team:{team_id}"
    if row.competition_id in followed.competition_ids:
        return f"followed_competition:{row.competition_id}"
    return None


def is_relevant(row: GameResultRow, followed: FollowedTargets) -> bool:
    return relevance_reason(row, followed) is not None
