"""Personalized results API (issue #178).

Authorization mirrors the feed surface: ``/results/{user_id}`` is the admin/ops
(view-as) route; the consumer product calls ``/me/results`` (session identity,
in routes_me). Relevance and isolation are enforced SERVER-SIDE — the client
never supplies a profile to filter by. The manual sync endpoint is admin-only;
the read path never touches the provider.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security_deps import require_admin
from app.db.database import get_session
from app.models.profile import UserProfile
from app.repositories import profile_repository
from app.results import settings
from app.results.models import GameResult
from app.results.service import personalized_results
from app.results.sync_service import get_sync_state, sync_results

router = APIRouter()

_MAX_LIMIT = 200


class ResultsResponse(BaseModel):
    # False = the profile follows no team/competition, so the UI shows the
    # distinct "no preferences" state instead of "no relevant results".
    has_preferences: bool
    games: List[GameResult]


def get_results_for_profile(
    profile: UserProfile, session: Session, limit: Optional[int]
) -> ResultsResponse:
    if not settings.results_enabled():
        raise HTTPException(status_code=404, detail="Results feature is disabled")
    result = personalized_results(session, profile, limit=limit)
    return ResultsResponse(has_preferences=result.has_preferences, games=result.games)


def get_results_for_user(user_id: str, session: Session, limit: Optional[int]) -> ResultsResponse:
    profile = profile_repository.get_by_id(session, user_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Profile '{user_id}' not found")
    return get_results_for_profile(profile, session, limit)


@router.get("/results/sync/state", dependencies=[Depends(require_admin)])
def results_sync_state(session: Session = Depends(get_session)):
    """Last results-sync outcome (ops observability)."""
    return get_sync_state(session)


@router.post("/results/sync", dependencies=[Depends(require_admin)])
def results_sync(session: Session = Depends(get_session)):
    """Manually trigger a results sync (bypasses the throttle)."""
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
