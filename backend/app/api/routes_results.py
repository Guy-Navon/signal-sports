"""Personalized results API (issue #178).

Authorization mirrors the feed surface: ``/results/{user_id}`` is the admin/ops
(view-as) route; the consumer product calls ``/me/results`` (session identity,
in routes_me). Relevance and isolation are enforced SERVER-SIDE — the client
never supplies a profile to filter by. The manual sync endpoint is admin-only;
the read path never touches the provider.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deploy_mode import provider_call_refusal
from app.core.security_deps import require_admin
from app.db.database import get_session
from app.models.profile import UserProfile
from app.repositories import profile_repository
from app.results import health as results_health, settings
from app.results.models import GameResult, GameDetailResponse
from app.results.service import personalized_results, personalized_detail
from app.results.sync_service import get_sync_state, sync_results

logger = logging.getLogger(__name__)

router = APIRouter()

_MAX_LIMIT = 200


class ResultsResponse(BaseModel):
    # False = the profile follows no team/competition, so the UI shows the
    # distinct "no preferences" state instead of "no relevant results".
    has_preferences: bool
    games: List[GameResult]
    team_games: List[GameResult] = Field(default_factory=list)
    followed_team_ids: List[str] = Field(default_factory=list)


def get_results_for_profile(
    profile: UserProfile, session: Session, limit: Optional[int]
) -> ResultsResponse:
    if not settings.results_enabled():
        raise HTTPException(status_code=404, detail="Results feature is disabled")
    result = personalized_results(session, profile, limit=limit)
    return ResultsResponse(has_preferences=result.has_preferences, games=result.games,
                           team_games=result.team_games, followed_team_ids=result.followed_team_ids)


def get_results_for_user(user_id: str, session: Session, limit: Optional[int]) -> ResultsResponse:
    profile = profile_repository.get_by_id(session, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    return get_results_for_profile(profile, session, limit)


def get_detail_for_user(user_id: str, game_id: str, session: Session) -> GameDetailResponse:
    profile = profile_repository.get_by_id(session, user_id)
    if not settings.results_enabled() or profile is None:
        raise HTTPException(status_code=404, detail="Game detail not found")
    result = personalized_detail(session, profile, game_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Game detail not found")
    return result


@router.get("/results/{user_id}/games/{game_id}/detail", response_model=GameDetailResponse,
            dependencies=[Depends(require_admin)])
def results_game_detail(user_id: str, game_id: str, session: Session = Depends(get_session)):
    return get_detail_for_user(user_id, game_id, session)


@router.get("/results/sync/state", dependencies=[Depends(require_admin)])
def results_sync_state(session: Session = Depends(get_session)):
    """Last results-sync outcome plus per-provider health and, per competition,
    the provider serving it and its freshness (#522). Read-only."""
    state = get_sync_state(session)
    try:
        state["health"] = results_health.ops_view(session)
    except Exception as exc:  # the sync state must stay readable
        logger.exception("results health view failed")
        session.rollback()
        state["health"] = {"error": type(exc).__name__}
    return state


@router.post("/results/sync", dependencies=[Depends(require_admin)])
def results_sync(session: Session = Depends(get_session)):
    """Manually trigger a results sync (bypasses the throttle). 503 when provider calls are
    disabled (a preview)."""
    if (refusal := provider_call_refusal("results_sync")) is not None:
        raise HTTPException(status_code=503, detail=refusal)
    if not settings.results_enabled():
        raise HTTPException(status_code=404, detail="Results feature is disabled")
    return sync_results(session, force=True)


@router.get(
    "/results/{user_id}",
    response_model=ResultsResponse,
    dependencies=[Depends(require_admin)],
)
def get_results(
    user_id: str,
    session: Session = Depends(get_session),
    limit: int = Query(default=_MAX_LIMIT, ge=1, le=_MAX_LIMIT),
):
    return get_results_for_user(user_id, session, limit)
