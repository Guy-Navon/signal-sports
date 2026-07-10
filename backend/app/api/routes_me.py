"""Consumer self-service surface — /api/me/* (User Platform PR 2, issue #50).

Contract (docs/USER_PLATFORM.md, authorization boundary):
- Identity comes ONLY from the authenticated session (``require_user``). No
  route here ever reads a caller-supplied user id; request bodies that could
  carry one are declared with ``extra="forbid"`` so an injected ``user_id``
  is rejected (422), never silently ignored.
- ``/me`` routes are THIN wrappers: they resolve ``current_user.id`` and then
  delegate to the exact same handlers the legacy ``{user_id}`` routes use, so
  consumer payloads are parity-identical by construction. Services stay
  user-agnostic; no business logic is duplicated here.
- This surface is session-gated in EVERY configuration — the
  ``ALLOW_INSECURE_AUTH_BYPASS`` flag applies to the legacy/ops surface only
  and has no effect here (``require_user`` has no bypass branch).
"""

from typing import Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import routes_auth
from app.api.routes_calibration import (
    CalibrationApplyRequest,
    CalibrationApplyResponse,
    apply_calibration,
    list_calibration_responses,
)
from app.api.routes_feed import get_feed
from app.api.routes_feedback import get_feedback_for_user, submit_feedback
from app.api.routes_learning import (
    LearningResetRequest,
    LearningStateResponse,
    NeverShowRequest,
    get_learning_state,
    never_show,
    reset_learning,
)
from app.api.routes_profiles import get_profile, put_profile
from app.core.security_deps import require_user
from app.db.database import get_session
from app.db.orm_models import UserRow
from app.models.feedback import FeedbackEvent, FeedbackRequest
from app.models.profile import UserProfile
from app.models.scoring import ScoredArticle
from app.services import auth_service

router = APIRouter(prefix="/me")


# ── Request bodies (identity-free by construction) ────────────────────────────

class MeFeedbackRequest(BaseModel):
    """Feedback body WITHOUT identity — the server sets user_id from the
    session. extra="forbid" makes an injected user_id a 422, per contract."""
    model_config = {"extra": "forbid"}
    article_id: str
    action: str


class MeCalibrationApplyRequest(BaseModel):
    model_config = {"extra": "forbid"}
    ratings: Dict[str, str] = Field(default_factory=dict)


class MeNeverShowRequest(BaseModel):
    model_config = {"extra": "forbid"}
    article_id: str


class MeLearningResetRequest(BaseModel):
    model_config = {"extra": "forbid"}
    kind: str | None = None
    target_id: str | None = None
    scope_ref: str | None = None
    event_type: str | None = None


class OnboardingStateResponse(BaseModel):
    onboarding: routes_auth.OnboardingBootstrap


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/profile", response_model=UserProfile)
def me_get_profile(
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    return get_profile(user_id=user.id, session=session)


@router.put("/profile", response_model=UserProfile)
def me_put_profile(
    payload: UserProfile,
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    # Delegation enforces payload.user_id == session identity (422 on any
    # mismatch) — a /me PUT can never rename or write another user's profile.
    return put_profile(user_id=user.id, payload=payload, session=session)


# ── Feed ──────────────────────────────────────────────────────────────────────

@router.get("/feed", response_model=List[ScoredArticle])
def me_get_feed(
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    return get_feed(user_id=user.id, session=session)


# ── Feedback ──────────────────────────────────────────────────────────────────

@router.post("/feedback", response_model=FeedbackEvent, status_code=201)
def me_submit_feedback(
    payload: MeFeedbackRequest,
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    request = FeedbackRequest(
        user_id=user.id, article_id=payload.article_id, action=payload.action
    )
    return submit_feedback(request=request, session=session)


@router.get("/feedback", response_model=List[FeedbackEvent])
def me_get_feedback(
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    return get_feedback_for_user(user_id=user.id, session=session)


# ── Learning ──────────────────────────────────────────────────────────────────

@router.get("/learning", response_model=LearningStateResponse)
def me_get_learning(
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    return get_learning_state(user_id=user.id, session=session)


@router.post("/learning/reset")
def me_reset_learning(
    payload: MeLearningResetRequest,
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    return reset_learning(
        user_id=user.id,
        payload=LearningResetRequest(**payload.model_dump()),
        session=session,
    )


@router.post("/never_show")
def me_never_show(
    payload: MeNeverShowRequest,
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    return never_show(
        user_id=user.id,
        payload=NeverShowRequest(article_id=payload.article_id),
        session=session,
    )


# ── Calibration / onboarding ─────────────────────────────────────────────────

@router.get("/calibration/responses")
def me_calibration_responses(
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    return list_calibration_responses(user_id=user.id, session=session)


@router.post("/calibration/apply", response_model=CalibrationApplyResponse)
def me_calibration_apply(
    payload: MeCalibrationApplyRequest,
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    """Apply calibration to the session user's profile AND stamp
    ``onboarding_completed_at`` (once, if not already set) — applying
    calibration completes onboarding per the state machine."""
    response = apply_calibration(
        payload=CalibrationApplyRequest(user_id=user.id, ratings=payload.ratings),
        session=session,
    )
    auth_service.complete_onboarding(session, user)
    return response


@router.post("/onboarding/complete", response_model=OnboardingStateResponse)
def me_complete_onboarding(
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    """The explicit skip path: stamp onboarding completion (idempotent) without
    applying calibration — the user reaches ACTIVE with an intentionally empty
    feed and a persistent calibrate CTA (product decision, docs/USER_PLATFORM.md)."""
    user = auth_service.complete_onboarding(session, user)
    bootstrap = routes_auth._session_bootstrap(session, user)
    return OnboardingStateResponse(onboarding=bootstrap.onboarding)
