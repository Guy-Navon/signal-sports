import logging
import os

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_session
from app.db.orm_models import UserRow
from app.services.auth_service import get_session_user

logger = logging.getLogger(__name__)


def allow_insecure_auth_bypass() -> bool:
    return os.environ.get("ALLOW_INSECURE_AUTH_BYPASS", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def validate_auth_startup_config() -> None:
    if allow_insecure_auth_bypass() and settings.auth_cookie_secure:
        raise RuntimeError(
            "Refusing to start with ALLOW_INSECURE_AUTH_BYPASS=true and "
            "AUTH_COOKIE_SECURE=true. The bypass is local/plain-HTTP only."
        )
    if allow_insecure_auth_bypass():
        logger.warning("")
        logger.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        logger.warning("!! ALLOW_INSECURE_AUTH_BYPASS=true is active.")
        logger.warning("!! Legacy/ops authorization dependencies will be bypassed.")
        logger.warning("!! /api/auth/* still requires real auth behavior.")
        logger.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        logger.warning("")


def auth_enforced_for_legacy_surface() -> bool:
    return not allow_insecure_auth_bypass()


def _cookie_token(request: Request) -> str | None:
    return request.cookies.get(settings.auth_cookie_name)


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> UserRow | None:
    return get_session_user(session, _cookie_token(request))


def require_user(current_user: UserRow | None = Depends(get_current_user)) -> UserRow:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return current_user


def require_admin(
    request: Request,
    current_user: UserRow | None = Depends(get_current_user),
) -> UserRow | None:
    if allow_insecure_auth_bypass():
        if request.url.path.startswith("/api/auth/"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Auth routes cannot use insecure bypass",
            )
        return current_user
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return current_user


def require_session(
    current_user: UserRow | None = Depends(get_current_user),
) -> UserRow | None:
    """Session-gated product surface, any role (User Platform PR 5, #53).

    Applies to product data that is not user-scoped (calibration items/preview,
    articles, feed-engine). Unlike require_user (the /me surface), this gate
    honors ALLOW_INSECURE_AUTH_BYPASS - the bypass restores the pre-auth open
    behavior on this surface only.
    """
    if allow_insecure_auth_bypass():
        return current_user
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return current_user
