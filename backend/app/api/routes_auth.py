from pydantic import BaseModel, Field, field_validator
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security_deps import auth_enforced_for_legacy_surface
from app.db.database import get_session
from app.db.orm_models import UserRow
from app.services import auth_service

router = APIRouter(prefix="/auth")


class SignupRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    display_name: str | None = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def _email_shape(cls, value: str) -> str:
        normalized = auth_service.normalize_email(value)
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("invalid email")
        return normalized


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email_shape(cls, value: str) -> str:
        normalized = auth_service.normalize_email(value)
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("invalid email")
        return normalized


class AuthUser(BaseModel):
    id: str
    email: str | None
    role: str
    created_at: str
    onboarding_completed_at: str | None
    interests_completed_at: str | None = None
    last_login_at: str | None


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
    return AuthUser(**auth_service.public_user_payload(user))


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
    return SessionBootstrap(
        auth_enforced=auth_enforced_for_legacy_surface(),
        user=_user_out(user) if user is not None else None,
        onboarding=onboarding,
    )


@router.post("/signup", response_model=AuthResponse, status_code=201)
def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    try:
        user = auth_service.create_user_with_profile(
            session,
            email=str(payload.email),
            password=payload.password,
            display_name=payload.display_name,
        )
    except auth_service.DuplicateEmailError:
        raise HTTPException(status_code=409, detail="Email already in use")
    token, _ = auth_service.create_session(
        session,
        user,
        user_agent=request.headers.get("user-agent"),
    )
    _set_auth_cookie(response, token)
    return AuthResponse(user=_user_out(user))


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
