"""Results domain models (issue #178).

- ``NormalizedGame`` — the provider-agnostic shape a ``ResultsProvider`` emits
  and the repository persists. Providers are responsible for producing this;
  API routes and the UI never see raw provider payloads.
- ``GameResult`` / ``TeamSide`` — the API response shape, enriched with
  taxonomy display names, a computed winner, and the relevance reason.
- ``NormalizedGameDetail`` / ``TeamLeader`` / ``PlayerLine`` — per-game detail
  for a finished game (issue #517): leaders, optional box-score lines, team
  stats, venue, attendance. Same identity as the game it belongs to.
"""
from __future__ import annotations

import hashlib
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.results import status as status_vocab


def game_id(provider: str, external_id: str) -> str:
    """Stable primary key from provider identity — the idempotency anchor."""
    digest = hashlib.sha1(f"{provider}|{external_id}".encode("utf-8")).hexdigest()
    return f"game_{digest[:24]}"


class NormalizedGame(BaseModel):
    """Provider-agnostic normalized game. Immutable value object."""
    model_config = {"frozen": True}

    provider: str
    external_id: str
    competition_id: str
    sport: str
    season: Optional[str] = None
    stage: Optional[str] = None
    status: str = status_vocab.UNKNOWN
    start_time: Optional[str] = None            # ISO-8601 UTC
    home_team_name: str
    away_team_name: str
    home_team_id: Optional[str] = None          # taxonomy team:* or None
    away_team_id: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None

    @property
    def id(self) -> str:
        return game_id(self.provider, self.external_id)


class TeamSide(BaseModel):
    id: Optional[str] = None                    # taxonomy team:* when resolved
    name: str                                   # display name (Hebrew when resolved)
    name_provider: str                          # raw provider name (audit / fallback)
    score: Optional[int] = None
    is_winner: bool = False
    rank: Optional[int] = None


class ResultLeader(BaseModel):
    side: Literal["home", "away"]
    name: Optional[str] = None
    entity_id: Optional[str] = None
    stat: str
    value: int


class ResultPlayerLine(BaseModel):
    side: Literal["home", "away"]
    name: Optional[str] = None
    entity_id: Optional[str] = None
    source_player_id: Optional[str] = None
    minutes: Optional[float] = None
    stats: dict = Field(default_factory=dict)


class GameDetailResponse(BaseModel):
    game_id: str
    players: list[ResultPlayerLine]
    team_stats: dict = Field(default_factory=dict)
    venue: Optional[str] = None
    attendance: Optional[int] = None


class GameResult(BaseModel):
    """The personalized API row for one game."""
    id: str
    competition_id: str
    competition_he: str
    competition_en: str
    sport: str
    season: Optional[str] = None
    stage: Optional[str] = None
    status: str
    start_time: Optional[str] = None            # ISO-8601 UTC
    home: TeamSide
    away: TeamSide
    winner: Optional[str] = None                # "home" | "away" | "draw" | None
    # Why this game is relevant to the requesting profile (server-side proof).
    relevance_reason: str = Field(default="")
    local_date: Optional[str] = None            # Asia/Jerusalem calendar day
    leaders: list[ResultLeader] = Field(default_factory=list)
    chosen_player_lines: list[ResultPlayerLine] = Field(default_factory=list)
    venue: Optional[str] = None
    attendance: Optional[int] = None
    detail_available: bool = False


# ── Per-game detail (issue #517) ──────────────────────────────────────────────

Side = Literal["home", "away"]

# Stat kinds a leader is ranked by. A ``PlayerLine.stats`` blob may carry any
# other keys; these two are the ones the results page needs.
STAT_POINTS = "points"      # basketball
STAT_GOALS = "goals"        # football


class TeamLeader(BaseModel):
    """One team's leader in one stat (at least the top scorer). Ties produce
    one leader per tied player. ``name`` can be missing when the source has the
    player id but no name record: the value is kept rather than dropped."""
    model_config = {"frozen": True}

    side: Side
    stat: str
    value: int
    source_player_id: Optional[str] = None
    name: Optional[str] = None                  # source name (usually English)
    name_he: Optional[str] = None               # when the source carries Hebrew
    entity_id: Optional[str] = None             # read-side results mapping (#525)
    display_name: Optional[str] = None


class PlayerLine(BaseModel):
    """One player's box-score line. ``stats`` holds the source's own fields
    (points, rebounds, goals, cards, ...), which differ by sport and source."""
    model_config = {"frozen": True}

    side: Side
    source_player_id: Optional[str] = None
    name: Optional[str] = None
    name_he: Optional[str] = None
    entity_id: Optional[str] = None
    display_name: Optional[str] = None
    minutes: Optional[float] = None
    stats: dict = Field(default_factory=dict)


class NormalizedGameDetail(BaseModel):
    """Detail for one finished game, as a detail-capable provider returns it.
    Identity is the game's ``(provider, external_id)``, so ``game_id`` is the
    ``game_results`` primary key."""
    model_config = {"frozen": True}

    provider: str
    external_id: str
    leaders: list[TeamLeader] = Field(default_factory=list)
    players: list[PlayerLine] = Field(default_factory=list)
    # {"home": {...}, "away": {...}}; free-form per sport and source.
    team_stats: dict = Field(default_factory=dict)
    venue: Optional[str] = None
    attendance: Optional[int] = None

    @property
    def game_id(self) -> str:
        return game_id(self.provider, self.external_id)


class StoredGameDetail(NormalizedGameDetail):
    """The read model: a stored detail plus when it was fetched."""
    fetched_at: str


def leaders_from_lines(lines: list[PlayerLine], stat: str) -> list[TeamLeader]:
    """Per-side leaders in ``stat`` from box-score lines, for sources that give
    a box score but no leaders. Ties yield every tied player; a side whose best
    value is not positive (a football team that did not score) has no leader.
    Only integer values count: providers convert string stats when normalizing."""
    leaders: list[TeamLeader] = []
    for side in ("home", "away"):
        scored = [
            (line, line.stats[stat]) for line in lines
            if line.side == side and type(line.stats.get(stat)) is int
        ]
        best = max((value for _, value in scored), default=0)
        if best <= 0:
            continue
        leaders.extend(
            TeamLeader(side=side, stat=stat, value=value,
                       source_player_id=line.source_player_id,
                       name=line.name, name_he=line.name_he)
            for line, value in scored if value == best
        )
    return leaders
