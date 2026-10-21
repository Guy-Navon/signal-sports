import hmac

from pydantic import BaseModel, Field, field_validator
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security_deps import (
    auth_enforced_for_legacy_surface,
    signup_allowed_for,
    signup_enabled,
)
from app.db.database import get_session
from app.db.orm_models import UserRow
from app.services import auth_service, email_verification, google_oauth

router = APIRouter(prefix="/auth")


def _valid_email(value: str) -> str:
    normalized = auth_service.normalize_email(value)
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("invalid email")
    # The address becomes an email header: no whitespace or control
    # characters inside it (header injection, and smtplib would refuse).
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in normalized):
        raise ValueError("invalid email")
    return normalized


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str | None = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def _email_shape(cls, value: str) -> str:
        return _valid_email(value)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email_shape(cls, value: str) -> str:
        return _valid_email(value)


class AuthUser(BaseModel):
    id: str
    email: str | None
    role: str
    created_at: str
    onboarding_completed_at: str | None
    interests_completed_at: str | None = None
    last_login_at: str | None
    # NULL for accounts created before verification existed (never proven).
    email_verified_at: str | None = None
    # False for accounts created through Google (no password to change).
    has_password: bool = True
    # The connected Google account's email (#330); reported by
    # GET /api/auth/session, null when not connected.
    google_email: str | None = None


class SignupPendingResponse(BaseModel):
    # "verification_sent" | "verification_send_failed" (resend from the UI)
    status: str
    email: str


class VerificationTokenRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class VerificationConfirmRequest(VerificationTokenRequest):
    password: str


class VerificationPeekResponse(BaseModel):
    email: str


class ResendResponse(BaseModel):
    status: str


class AuthResponse(BaseModel):
    user: AuthUser


class LogoutResponse(BaseModel):
    ok: bool


class CalibrationBootstrap(BaseModel):
    answered: int
    total: int


class InterestsBootstrap(BaseModel):
    completed: bool
    selected: int


class OnboardingBootstrap(BaseModel):
    completed: bool
    calibration: CalibrationBootstrap
    # Explicit interest stage (issue #77). Legacy users (onboarding done
    # before the stage existed) read as completed — never re-funneled.
    interests: InterestsBootstrap


class SessionBootstrap(BaseModel):
    auth_enforced: bool
    # AUTH_SIGNUP_ENABLED (#265): lets the UI hide signup when it is closed.
    signup_enabled: bool
    # Closed signup that still admits AUTH_SIGNUP_ALLOWED_EMAILS addresses.
    signup_by_invitation: bool = False
    # All three GOOGLE_OAUTH_* values are set: the UI shows "המשך עם Google".
    google_enabled: bool = False
    user: AuthUser | None
    onboarding: OnboardingBootstrap | None


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=auth_service.SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _user_out(user: UserRow) -> AuthUser:
    return AuthUser(**auth_service.public_user_payload(user), has_password=bool(user.password_hash))


def _calibration_answer_count(session: Session, user_id: str) -> int:
    from app.db.orm_models import CalibrationResponseRow
    from app.calibration_v2 import CALIBRATION_ITEMS

    answered = (
        session.query(CalibrationResponseRow)
        .filter(CalibrationResponseRow.user_id == user_id)
        .count()
    )
    return min(answered, len(CALIBRATION_ITEMS))


def _interests_selected_count(session: Session, user_id: str) -> int:
    from app.repositories import profile_repository
    from app.services.interests_service import interests_document

    profile = profile_repository.get_by_id(session, user_id)
    if profile is None:
        return 0
    return interests_document(profile, completed=False).selected


def _session_bootstrap(session: Session, user: UserRow | None) -> SessionBootstrap:
    onboarding = None
    if user is not None:
        from app.calibration_v2 import CALIBRATION_ITEMS
        from app.services.interests_service import interests_completed

        onboarding = OnboardingBootstrap(
            completed=user.onboarding_completed_at is not None,
            calibration=CalibrationBootstrap(
                answered=_calibration_answer_count(session, user.id),
                total=len(CALIBRATION_ITEMS),
            ),
            interests=InterestsBootstrap(
                completed=interests_completed(user),
                selected=_interests_selected_count(session, user.id),
            ),
        )
    user_out = None
    if user is not None:
        identity = google_oauth.linked_identity(session, user.id)
        user_out = _user_out(user)
        user_out.google_email = identity.email if identity is not None else None
    return SessionBootstrap(
        auth_enforced=auth_enforced_for_legacy_surface(),
        signup_enabled=signup_enabled(),
        signup_by_invitation=(
            not signup_enabled() and bool(email_verification.allowed_signup_emails())
        ),
        google_enabled=google_oauth.google_config() is not None,
        user=user_out,
        onboarding=onboarding,
    )


@router.post("/signup", response_model=SignupPendingResponse, status_code=202)
def signup(
    payload: SignupRequest,
    session: Session = Depends(get_session),
):
    """Start a password registration: a pending row and one emailed link.
    No user, profile or session exists until the link is confirmed with the
    password (POST /verification/confirm)."""
    # Closed signup (#265) refuses before anything is created, unless the
    # address is allowlisted (it is then still only pending).
    if not signup_allowed_for(payload.email):
        raise HTTPException(status_code=403, detail="Signup is closed")
    try:
        outcome = email_verification.start_registration(
            session,
            email=str(payload.email),
            password=payload.password,
            display_name=payload.display_name,
        )
    except email_verification.MailNotConfigured:
        raise HTTPException(status_code=503, detail="Email delivery is not configured")
    except auth_service.DuplicateEmailError:
        raise HTTPException(status_code=409, detail="Email already in use")
    except auth_service.RateLimitExceeded:
        raise HTTPException(status_code=429, detail="Too many signup attempts")
    return SignupPendingResponse(
        status="verification_sent" if outcome.delivered else "verification_send_failed",
        email=outcome.email,
    )


_INVALID_LINK = "Verification link is invalid or expired"


@router.post("/verification/peek", response_model=VerificationPeekResponse)
def verification_peek(payload: VerificationTokenRequest, session: Session = Depends(get_session)):
    """Read-only: the masked address a live link belongs to."""
    masked = email_verification.peek(session, payload.token)
    if masked is None:
        raise HTTPException(status_code=404, detail=_INVALID_LINK)
    return VerificationPeekResponse(email=masked)


@router.post("/verification/confirm", response_model=AuthResponse)
def verification_confirm(
    payload: VerificationConfirmRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    try:
        user, token, _ = email_verification.confirm_registration(
            session,
            token=payload.token,
            password=payload.password,
            user_agent=request.headers.get("user-agent"),
        )
    except email_verification.InvalidVerificationToken:
        raise HTTPException(status_code=400, detail=_INVALID_LINK)
    except auth_service.InvalidPasswordError:
        raise HTTPException(status_code=403, detail="Password is incorrect")
    except auth_service.RateLimitExceeded:
        raise HTTPException(status_code=429, detail="Too many attempts")
    except auth_service.DuplicateEmailError:
        raise HTTPException(status_code=409, detail="Email already in use")
    _set_auth_cookie(response, token)
    return AuthResponse(user=_user_out(user))


@router.post("/verification/resend", response_model=ResendResponse)
def verification_resend(payload: LoginRequest, session: Session = Depends(get_session)):
    try:
        outcome = email_verification.resend(
            session, email=str(payload.email), password=payload.password,
        )
    except email_verification.MailNotConfigured:
        raise HTTPException(status_code=503, detail="Email delivery is not configured")
    except auth_service.InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    except email_verification.ResendCooldown as exc:
        raise HTTPException(
            status_code=429, detail="Please wait before resending",
            headers={"Retry-After": str(exc.retry_after)},
        )
    except auth_service.RateLimitExceeded:
        raise HTTPException(status_code=429, detail="Too many emails for this signup")
    return ResendResponse(
        status="verification_sent" if outcome.delivered else "verification_send_failed",
    )


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    try:
        user, token, _ = auth_service.login(
            session,
            email=str(payload.email),
            password=payload.password,
            user_agent=request.headers.get("user-agent"),
        )
    except auth_service.RateLimitExceeded:
        raise HTTPException(status_code=429, detail="Too many login attempts")
    except auth_service.InvalidCredentialsError:
        # An unverified signup is told so only once its password matched, so
        # this reveals nothing to someone who does not hold the credential.
        if auth_service.get_user_by_email(session, payload.email) is None and (
            email_verification.pending_password_matches(
                session, email=payload.email, password=payload.password)
        ):
            raise HTTPException(status_code=403, detail="Email not verified")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    _set_auth_cookie(response, token)
    return AuthResponse(user=_user_out(user))


@router.post("/logout", response_model=LogoutResponse)
def logout(request: Request, response: Response, session: Session = Depends(get_session)):
    auth_service.revoke_session(session, request.cookies.get(settings.auth_cookie_name))
    _clear_auth_cookie(response)
    return LogoutResponse(ok=True)


@router.get("/session", response_model=SessionBootstrap)
def get_auth_session(request: Request, session: Session = Depends(get_session)):
    user = auth_service.get_session_user(
        session,
        request.cookies.get(settings.auth_cookie_name),
    )
    return _session_bootstrap(session, user)


# ── Google sign-in (Slice B1) ────────────────────────────────────────────────

class GoogleStartResponse(BaseModel):
    url: str


_GOOGLE_COOKIE_PATH = "/api/auth/google"
_GOOGLE_STATE_SECONDS = int(google_oauth.PENDING_TTL.total_seconds())


def _google_state_cookie() -> str:
    # Derived from the session cookie name, so dev and prod stay apart.
    return f"{settings.auth_cookie_name}_oauth"


def _require_google() -> google_oauth.GoogleConfig:
    cfg = google_oauth.google_config()
    if cfg is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return cfg


@router.post("/google/start", response_model=GoogleStartResponse)
def google_start(response: Response, session: Session = Depends(get_session)):
    """Begin a Google sign-in. CSRF-checked (POST); the browser then navigates
    to the returned URL. The raw state goes into a short-lived HttpOnly
    cookie scoped to /api/auth/google; only its hash is stored."""
    cfg = _require_google()
    try:
        url, state = google_oauth.start_login(session, cfg)
    except auth_service.RateLimitExceeded:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts")
    set_google_state_cookie(response, state)
    return GoogleStartResponse(url=url)


def set_google_state_cookie(response: Response, state: str) -> None:
    response.set_cookie(
        key=_google_state_cookie(),
        value=state,
        max_age=_GOOGLE_STATE_SECONDS,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",  # sent on Google's top-level GET redirect back
        path=_GOOGLE_COOKIE_PATH,
    )


def _google_redirect(location: str) -> RedirectResponse:
    redirect = RedirectResponse(location, status_code=302)
    redirect.delete_cookie(
        key=_google_state_cookie(), path=_GOOGLE_COOKIE_PATH,
        secure=settings.auth_cookie_secure, httponly=True, samesite="lax",
    )
    return redirect


@router.get("/google/callback")
def google_callback(
    request: Request,
    state: str = "",
    code: str = "",
    error: str = "",
    session: Session = Depends(get_session),
):
    """Google's redirect back. A deliberate state-changing GET, protected by
    the state cookie (must equal ``state``), the single-use pending row, PKCE
    and the nonce. Redirects only to fixed paths (no return_to parameter)."""
    cfg = _require_google()
    # Account-bound attempts (delete #331, link #330) report back to the
    # Account page; the peek is read-only and only picks where failures show.
    intent = google_oauth.pending_intent(session, state)
    deleting, linking = intent == "delete", intent == "link"
    failed = {"delete": "/account?google=", "link": "/account?google=link_"}.get(
        intent, "/login?google=")
    cookie = request.cookies.get(_google_state_cookie(), "")
    if not state or not cookie or not hmac.compare_digest(cookie, state):
        return _google_redirect(f"{failed}expired")
    if error:
        try:
            google_oauth.consume_pending(session, state)
        except google_oauth.GoogleAuthError:
            pass
        code_name = "cancelled" if error == "access_denied" else "failed"
        return _google_redirect(f"{failed}{code_name}")
    if not code:
        return _google_redirect(f"{failed}failed")
    if intent == "verify_registration":
        # Third-party address, second proof (#329): same Google subject and
        # address as the emailed link's registration. The session goes to
        # this browser, which just completed both proofs.
        try:
            _user, token = google_oauth.complete_registration_callback(
                session, cfg, state=state, code=code,
                user_agent=request.headers.get("user-agent"),
            )
        except google_oauth.GoogleAuthError as exc:
            return _google_redirect(f"/login?google={exc.code}")
        redirect = _google_redirect("/")
        _set_auth_cookie(redirect, token)
        return redirect
    if linking:
        raw_session = request.cookies.get(settings.auth_cookie_name)
        try:
            google_oauth.complete_link(
                session, cfg, state=state, code=code,
                current_session_hash=auth_service.token_hash(raw_session) if raw_session else None,
            )
        except google_oauth.GoogleAuthError as exc:
            return _google_redirect(f"/account?google=link_{exc.code}")
        return _google_redirect("/account?google=linked")
    if deleting:
        raw_session = request.cookies.get(settings.auth_cookie_name)
        try:
            google_oauth.complete_delete_confirmation(
                session, cfg, state=state, code=code,
                current_session_hash=auth_service.token_hash(raw_session) if raw_session else None,
            )
        except google_oauth.GoogleAuthError as exc:
            return _google_redirect(f"/account?google={exc.code}")
        return _google_redirect("/account?delete=confirm")
    try:
        _user, token = google_oauth.complete_callback(
            session, cfg, state=state, code=code,
            user_agent=request.headers.get("user-agent"),
        )
    except google_oauth.GoogleAuthError as exc:
        return _google_redirect(f"/login?google={exc.code}")
    redirect = _google_redirect("/")
    _set_auth_cookie(redirect, token)
    return redirect


# ── Third-party Google sign-up: the emailed link (#329) ─────────────────────

@router.post("/verification/google/peek", response_model=VerificationPeekResponse)
def google_verification_peek(payload: VerificationTokenRequest, session: Session = Depends(get_session)):
    """Read-only: the masked address a live Google-registration link belongs to."""
    masked = google_oauth.peek_google_registration(session, payload.token)
    if masked is None:
        raise HTTPException(status_code=404, detail=_INVALID_LINK)
    return VerificationPeekResponse(email=masked)


@router.post("/verification/google/start", response_model=GoogleStartResponse)
def google_verification_start(
    payload: VerificationTokenRequest,
    response: Response,
    session: Session = Depends(get_session),
):
    """The link's second step: a Google sign-in bound to this registration's
    current token. Opening the link alone activates nothing; only the
    callback, as the same Google account with the same address, does."""
    cfg = _require_google()
    try:
        url, state = google_oauth.start_registration_verification(
            session, cfg, raw_token=payload.token)
    except google_oauth.GoogleAuthError:
        raise HTTPException(status_code=404, detail=_INVALID_LINK)
    except auth_service.RateLimitExceeded:
        raise HTTPException(status_code=429, detail="Too many sign-in attempts")
    set_google_state_cookie(response, state)
    return GoogleStartResponse(url=url)
