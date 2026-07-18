"""Results domain models (issue #178).

- ``NormalizedGame`` — the provider-agnostic shape a ``ResultsProvider`` emits
  and the repository persists. Providers are responsible for producing this;
  API routes and the UI never see raw provider payloads.
- ``GameResult`` / ``TeamSide`` — the API response shape, enriched with
  taxonomy display names, a computed winner, and the relevance reason.
"""
from __future__ import annotations

import hashlib
from typing import Optional

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
