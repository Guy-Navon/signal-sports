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

import logging
from typing import Dict, List, Literal

from fastapi import HTTPException, Request, Response

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.api import routes_auth
from app.api.routes_calibration import (
    CalibrationApplyRequest,
    CalibrationApplyResponse,
    _validate_ratings,
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
from app.api.routes_results import ResultsResponse, get_results_for_user
from app.core.security_deps import require_user
from app.db.database import get_session
from app.db.orm_models import UserRow
from app.models.feedback import FeedbackEvent, FeedbackRequest
from app.models.profile import UserProfile
from app.models.scoring import ScoredArticle
from app.repositories import usage_repository
from app.services import auth_service
from app.services import interests_service

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


class MeCalibrationResponsesRequest(BaseModel):
    """Partial per-item rating upsert (onboarding resumability, issue #52)."""
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


class MePasswordRequest(BaseModel):
    model_config = {"extra": "forbid"}
    current_password: str
    new_password: str = Field(min_length=8)


class MeDeleteAccountRequest(BaseModel):
    """Exactly one confirmation: the current password, or (for an account
    without one) the deletion grant earned through Google (#331)."""
    model_config = {"extra": "forbid"}
    current_password: str | None = None
    method: Literal["reauth_grant"] | None = None

    @model_validator(mode="after")
    def _exactly_one(self):
        if (self.current_password is None) == (self.method is None):
            raise ValueError("send current_password or method='reauth_grant'")
        return self


class MeGoogleDeleteStartRequest(BaseModel):
    model_config = {"extra": "forbid"}
    confirm_email: str = Field(max_length=320)


class MeGoogleDeleteStartResponse(BaseModel):
    url: str


class MeGooglePasswordRequest(BaseModel):
    model_config = {"extra": "forbid"}
    current_password: str


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
    return put_profile(user_id=user.id, payload=payload, session=session, acting_admin=None)


# ── Feed ──────────────────────────────────────────────────────────────────────

@router.get("/feed", response_model=List[ScoredArticle])
def me_get_feed(
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    feed = get_feed(user_id=user.id, session=session)
    # #250: one counter per user per day. Recorded after the feed is built and
    # never allowed to fail the request: usage is a measurement, not a feature.
    try:
        usage_repository.record_feed_view(session, user.id)
    except Exception:
        session.rollback()
        logging.getLogger(__name__).warning("feed view not recorded for %s", user.id, exc_info=True)
    return feed


# ── Results (issue #178) ──────────────────────────────────────────────────────

@router.get("/results", response_model=ResultsResponse)
def me_get_results(
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    """Personalized game results for the session user. Thin wrapper over the
    same handler the admin /results/{user_id} route uses — identical relevance
    and isolation, identity taken only from the session."""
    return get_results_for_user(user_id=user.id, session=session, limit=200)


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
    return submit_feedback(request=request, session=session, acting_admin=None)


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
        acting_admin=None,
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
        acting_admin=None,
    )


# ── Explicit interests (issue #77, docs/INTERESTS.md) ────────────────────────

@router.get("/interests", response_model=interests_service.InterestsDocument)
def me_get_interests(
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    profile = get_profile(user_id=user.id, session=session)
    return interests_service.interests_document(
        profile, completed=interests_service.interests_completed(user)
    )


@router.put("/interests", response_model=interests_service.InterestsDocument)
def me_put_interests(
    payload: interests_service.InterestsPutRequest,
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    """Full replace of the managed explicit subset (Follow/Star scope
    affinities + global event presets). Calibration/learned entries, scoped
    explicit deltas, negative explicit levels, overrides and mutes all
    survive (docs/INTERESTS.md). Declaring interests stamps the stage
    complete (idempotent)."""
    profile = get_profile(user_id=user.id, session=session)
    try:
        profile = interests_service.replace_managed_interests(session, profile, payload)
    except interests_service.InterestsValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    interests_service.complete_interests(session, user)
    return interests_service.interests_document(profile, completed=True)


@router.post("/interests/complete", response_model=interests_service.InterestsDocument)
def me_complete_interests(
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    """The explicit skip path: stamp interests_completed_at (idempotent)
    without writing any preference data."""
    interests_service.complete_interests(session, user)
    profile = get_profile(user_id=user.id, session=session)
    return interests_service.interests_document(profile, completed=True)


# ── Calibration / onboarding ─────────────────────────────────────────────────

@router.get("/calibration/items")
def me_calibration_items(
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    """Interest-aware calibration selection (issue #81): ~10-14 items scoped
    to the user's explicit interests + discovery probes, deterministic per
    (user, dataset version). The admin GET /api/calibration/items keeps
    serving the full dataset. Same response shape (items subset only)."""
    from app.api.routes_calibration import CalibrationItemOut, CalibrationItemsResponse
    from app.calibration_v2 import CALIBRATION_DATASET_VERSION, RATING_VALUES
    from app.calibration_v2.selection import select_items

    profile = get_profile(user_id=user.id, session=session)
    selected = select_items(profile.profile_v2, user_id=user.id)
    return CalibrationItemsResponse(
        version=CALIBRATION_DATASET_VERSION,
        rating_keys=list(RATING_VALUES),
        items=[
            CalibrationItemOut(
                id=i.id, title=i.title, sport=i.sport,
                competition_id=i.competition_id, entity_ids=list(i.entity_ids),
                event_type=i.event_type, importance=i.importance,
            )
            for i in selected
        ],
    )


@router.get("/calibration/responses")
def me_calibration_responses(
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    return list_calibration_responses(user_id=user.id, session=session)


@router.post("/calibration/responses")
def me_save_calibration_responses(
    payload: MeCalibrationResponsesRequest,
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    """Per-item rating persistence for the onboarding flow (issue #52).

    ``save_responses`` is an upsert keyed on (user, item) — partial saves are
    safe, mid-calibration abandonment loses nothing, and cross-device resume
    works because the rated state is server-side. Applying inference remains a
    separate explicit step (``/me/calibration/apply``)."""
    from app.services.calibration_service import get_responses, save_responses

    _validate_ratings(payload.ratings)
    save_responses(session, user.id, payload.ratings)
    return {"saved": len(payload.ratings), "answered": len(get_responses(session, user.id))}


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
        acting_admin=None,
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


# ── Account lifecycle (User Platform PR 7, issue #55) ────────────────────────

@router.post("/password")
def me_change_password(
    payload: MePasswordRequest,
    request: Request,
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    """Change the account password. Requires the current password; on success
    every OTHER session is revoked while the active one survives."""
    from app.core.config import settings

    raw_token = request.cookies.get(settings.auth_cookie_name)
    try:
        revoked = auth_service.change_password(
            session, user,
            current_password=payload.current_password,
            new_password=payload.new_password,
            keep_raw_token=raw_token or "",
        )
    except auth_service.InvalidPasswordError:
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    return {"ok": True, "revoked_other_sessions": revoked}


@router.delete("/account")
def me_delete_account(
    payload: MeDeleteAccountRequest,
    request: Request,
    response: Response,
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    """Delete the account and exactly its own personalization rows (hard
    delete, irreversible). Confirmed by the current password, or — for an
    account without a password — by the single-use deletion grant this same
    session earned through Google (#331). Demo fixtures are undeletable; the
    last remaining admin cannot self-delete."""
    from app.core.config import settings

    try:
        if payload.method == "reauth_grant":
            if user.password_hash:
                raise HTTPException(
                    status_code=400, detail="This account confirms deletion with its password")
            raw_token = request.cookies.get(settings.auth_cookie_name) or ""
            auth_service.delete_account_with_grant(
                session, user, session_hash=auth_service.token_hash(raw_token))
        else:
            auth_service.delete_account(
                session, user, current_password=payload.current_password
            )
    except auth_service.UndeletableAccountError:
        raise HTTPException(status_code=403, detail="Demo accounts cannot be deleted")
    except auth_service.LastAdminError:
        raise HTTPException(
            status_code=409, detail="The last remaining admin cannot self-delete"
        )
    except auth_service.InvalidPasswordError:
        raise HTTPException(status_code=403, detail="Current password is incorrect")
    except auth_service.InvalidReauthGrantError:
        raise HTTPException(
            status_code=403, detail="Deletion confirmation is missing or expired")
    response.delete_cookie(
        key=settings.auth_cookie_name, path="/",
        secure=settings.auth_cookie_secure, httponly=True, samesite="lax",
    )
    return {"ok": True, "deleted": True}


@router.post("/account/delete/google/start", response_model=MeGoogleDeleteStartResponse)
def me_delete_account_google_start(
    payload: MeGoogleDeleteStartRequest,
    request: Request,
    response: Response,
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    """Begin confirming the deletion of a Google-only account (#331): a newly
    initiated Google round trip for the same linked account, bound to this
    user and session. Its callback only records a short-lived, single-use
    grant; deletion itself is the separate DELETE /api/me/account."""
    from app.core.config import settings
    from app.services import google_oauth

    cfg = google_oauth.google_config()
    if cfg is None:
        raise HTTPException(status_code=404, detail="Not Found")
    identity = google_oauth.linked_identity(session, user.id)
    if user.password_hash or identity is None:
        raise HTTPException(
            status_code=409, detail="Only accounts without a password confirm deletion with Google")
    if auth_service.normalize_email(payload.confirm_email) != user.email:
        raise HTTPException(status_code=400, detail="The email does not match this account")
    raw_token = request.cookies.get(settings.auth_cookie_name) or ""
    try:
        url, state = google_oauth.start_delete_confirmation(
            session, cfg, user_id=user.id, session_hash=auth_service.token_hash(raw_token),
            login_hint=identity.email or user.email,
        )
    except auth_service.RateLimitExceeded:
        raise HTTPException(status_code=429, detail="Too many attempts")
    routes_auth.set_google_state_cookie(response, state)
    return MeGoogleDeleteStartResponse(url=url)


# ── Connect / disconnect Google (#330) ───────────────────────────────────────

def _verify_password_limited(user: UserRow, password: str) -> None:
    """Password re-entry for the Google endpoints, sharing login's per-account
    budget so they can't serve as a guessing oracle."""
    if not auth_service._account_login_limiter.check(user.email or user.id):
        raise HTTPException(status_code=429, detail="Too many attempts")
    if not user.password_hash or not auth_service.verify_password(user.password_hash, password):
        raise HTTPException(status_code=403, detail="Current password is incorrect")


@router.post("/google/link", response_model=MeGoogleDeleteStartResponse)
def me_google_link_start(
    payload: MeGooglePasswordRequest,
    request: Request,
    response: Response,
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    """Connect a Google account explicitly (#330): the current password, then
    a Google round trip bound to this user and session. The only way an admin
    gains Google sign-in (automatic linking is role=user only)."""
    from app.core.config import settings
    from app.services import google_oauth

    cfg = google_oauth.google_config()
    if cfg is None:
        raise HTTPException(status_code=404, detail="Not Found")
    if not user.password_hash:
        raise HTTPException(status_code=409, detail="This account has no password")
    _verify_password_limited(user, payload.current_password)
    if google_oauth.linked_identity(session, user.id) is not None:
        raise HTTPException(status_code=409, detail="Google is already connected")
    raw_token = request.cookies.get(settings.auth_cookie_name) or ""
    try:
        url, state = google_oauth.start_link(
            session, cfg, user_id=user.id, session_hash=auth_service.token_hash(raw_token))
    except auth_service.RateLimitExceeded:
        raise HTTPException(status_code=429, detail="Too many attempts")
    routes_auth.set_google_state_cookie(response, state)
    return MeGoogleDeleteStartResponse(url=url)


@router.delete("/google")
def me_google_unlink(
    payload: MeGooglePasswordRequest,
    user: UserRow = Depends(require_user),
    session: Session = Depends(get_session),
):
    """Disconnect Google (#330). Needs the password, and an account without
    one is refused (409): it would be left with no way to sign in."""
    from app.services import google_oauth

    if not user.password_hash:
        raise HTTPException(
            status_code=409, detail="An account without a password cannot disconnect Google")
    _verify_password_limited(user, payload.current_password)
    identity = google_oauth.linked_identity(session, user.id)
    if identity is None:
        raise HTTPException(status_code=404, detail="Google is not connected")
    session.delete(identity)
    session.commit()
    return {"ok": True}
