"""Personalized results read path (issue #178).

Server-side relevance + isolation: given a profile, return only the games that
match its follows, enriched with taxonomy display names, a computed winner, and
the relevance reason. The provider is NEVER called here — this reads the DB only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db.orm_models import GameResultRow
from app.models.profile import UserProfile
from app.results import settings, status as st
from app.results.models import GameResult, TeamSide
from app.results.relevance import FollowedTargets, followed_targets, relevance_reason
from app.repositories import game_result_repository
from app.taxonomy.competitions import COMPETITIONS
from app.taxonomy.entities import entity_by_id


@dataclass
class PersonalizedResults:
    games: list[GameResult] = field(default_factory=list)
    has_preferences: bool = False


def _team_display(team_id: Optional[str], provider_name: str) -> str:
    if team_id:
        entity = entity_by_id(team_id)
        if entity:
            return entity.display_he
    return provider_name


def _to_result(row: GameResultRow, followed: FollowedTargets) -> GameResult:
    comp = COMPETITIONS.get(row.competition_id)
    winner = st.winner(row.status, row.home_score, row.away_score)
    reason = relevance_reason(row, followed) or ""
    return GameResult(
        id=row.id,
        competition_id=row.competition_id,
        competition_he=comp.display_he if comp else row.competition_id,
        competition_en=comp.display_en if comp else row.competition_id,
        sport=row.sport,
        season=row.season,
        stage=row.stage,
        status=row.status,
        start_time=row.start_time,
        home=TeamSide(
            id=row.home_team_id,
            name=_team_display(row.home_team_id, row.home_team_name),
            name_provider=row.home_team_name,
            score=row.home_score,
            is_winner=winner == "home",
        ),
        away=TeamSide(
            id=row.away_team_id,
            name=_team_display(row.away_team_id, row.away_team_name),
            name_provider=row.away_team_name,
            score=row.away_score,
            is_winner=winner == "away",
        ),
        winner=winner,
        relevance_reason=reason,
    )


def personalized_results(
    session: Session, profile: UserProfile, *, limit: Optional[int] = None
) -> PersonalizedResults:
    """Relevant games for a profile, newest-first."""
    followed = followed_targets(profile)
    if followed.is_empty:
        return PersonalizedResults(games=[], has_preferences=False)

    since = (
        datetime.now(tz=timezone.utc) - timedelta(days=settings.read_window_days())
    ).isoformat()
    rows = game_result_repository.list_games(session, since_iso=since)

    results: list[GameResult] = []
    for row in rows:
        reason = relevance_reason(row, followed)
        if reason is None:
            continue
        results.append(_to_result(row, followed))
        if limit is not None and len(results) >= limit:
            break

    return PersonalizedResults(games=results, has_preferences=True)
