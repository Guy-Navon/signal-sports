"""Google sign-in: login and registration (Slice B1).

Server-side OAuth 2.0 authorization-code flow with PKCE (S256), ``state`` and
``nonce``, as a full-page redirect:

  POST /api/auth/google/start   (CSRF-checked) stores an oauth_pending row and
                                sets the state cookie; returns Google's URL
  GET  /api/auth/google/callback  state cookie == state, the pending row is
                                consumed atomically, the code is exchanged,
                                the ID token verified, the account resolved

ID-token validation (signature against Google's published certificates,
``aud``, ``iss``, ``exp``) is google-auth's ``verify_oauth2_token``; this module
adds the nonce, the subject, and the email-authority policy. The user key is
Google's ``sub``; an email never links accounts.

Email authority (docs/USER_PLATFORM.md, "Google sign-in"): registration needs
``email_verified`` exactly true AND an address Google is authoritative for:
``@gmail.com`` without ``hd``, or a Workspace address whose domain equals
``hd``. Anything else is a third-party address, not registrable here yet.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional
from urllib.parse import urlencode

import httpx
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.orm_models import OAuthPendingRow, PendingRegistrationRow, UserIdentityRow, UserRow
from app.services import auth_service
from app.services.auth_service import FixedWindowLimiter, iso, normalize_email, token_hash, utc_now

logger = logging.getLogger(__name__)

PROVIDER = "google"
AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
SCOPES = "openid email profile"
PENDING_TTL = timedelta(minutes=10)
TOKEN_TIMEOUT_SECONDS = 10
CLOCK_SKEW_SECONDS = 10
DISPLAY_NAME_MAX = 120

# Each start stores a row; bound how fast anonymous callers can add them.
START_LIMIT = 60
START_WINDOW_SECONDS = 60
_start_limiter = FixedWindowLimiter(START_LIMIT, START_WINDOW_SECONDS)


class GoogleAuthError(Exception):
    """A failed sign-in with a fixed, user-facing code (the /login notice)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class GoogleConfig:
    client_id: str
    client_secret: str
    redirect_uri: str


@dataclass(frozen=True)
class EmailAuthority:
    kind: str  # "authoritative" | "third_party" | "unverified"
    email: Optional[str]


_ENV = ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REDIRECT_URI")


def reset_rate_limiters() -> None:
    _start_limiter.reset()


def google_config() -> Optional[GoogleConfig]:
    """Read at request time. Enabled only when all three values are set."""
    values = [os.environ.get(name, "").strip() for name in _ENV]
    if not all(values):
        return None
    return GoogleConfig(*values)


def partially_configured() -> bool:
    present = [bool(os.environ.get(name, "").strip()) for name in _ENV]
    return any(present) and not all(present)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def start_login(session: Session, cfg: GoogleConfig) -> tuple[str, str]:
    """Record a login attempt; return (authorization URL, raw state)."""
    if not _start_limiter.check("global"):
        raise auth_service.RateLimitExceeded("too many sign-in attempts")
    now = utc_now()
    session.execute(delete(OAuthPendingRow).where(OAuthPendingRow.expires_at <= iso(now)))
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    session.add(OAuthPendingRow(
        state_hash=token_hash(state),
        intent="login",
        nonce=nonce,
        code_verifier=verifier,
        created_at=iso(now),
        expires_at=iso(now + PENDING_TTL),
    ))
    session.commit()
    query = urlencode({
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256",
        # Account choice only, for people with several Google accounts. It is
        # not re-authentication.
        "prompt": "select_account",
        "hl": "he",
    })
    return f"{AUTHORIZATION_ENDPOINT}?{query}", state


def consume_pending(session: Session, state: str) -> OAuthPendingRow:
    """Single use: of concurrent callbacks with one state, exactly one wins."""
    hashed = token_hash(state)
    row = session.get(OAuthPendingRow, hashed)
    if row is None or auth_service.parse_iso(row.expires_at) <= utc_now():
        raise GoogleAuthError("expired")
    snapshot = OAuthPendingRow(
        state_hash=row.state_hash, intent=row.intent, nonce=row.nonce,
        code_verifier=row.code_verifier, created_at=row.created_at, expires_at=row.expires_at,
    )
    session.expunge(row)
    consumed = session.execute(
        delete(OAuthPendingRow)
        .where(OAuthPendingRow.state_hash == hashed)
        .where(OAuthPendingRow.expires_at > iso(utc_now()))
    ).rowcount
    session.commit()
    if consumed != 1:
        raise GoogleAuthError("expired")
    return snapshot


def exchange_code(cfg: GoogleConfig, code: str, code_verifier: str) -> str:
    """The token-endpoint call (network seam). Returns the raw ID token."""
    try:
        response = httpx.post(
            TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret,
                "redirect_uri": cfg.redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
            timeout=TOKEN_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.warning("Google token endpoint unreachable: %s", type(exc).__name__)
        raise GoogleAuthError("unavailable") from exc
    if response.status_code >= 500:
        logger.warning("Google token endpoint answered %s", response.status_code)
        raise GoogleAuthError("unavailable")
    if response.status_code != 200:
        # A bad/expired code or a misconfigured client. The body can echo
        # request details, so only the status is logged.
        logger.warning("Google token exchange refused: %s", response.status_code)
        raise GoogleAuthError("failed")
    id_token = response.json().get("id_token")
    if not id_token:
        raise GoogleAuthError("failed")
    return id_token


def certs_transport():
    """The google-auth transport that fetches Google's certificates (seam).

    google-auth calls it without a timeout, and its requests transport then
    waits up to 120 s; bound it like the code exchange."""
    import google.auth.transport.requests

    request = google.auth.transport.requests.Request()

    def bounded(url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        return request(url, method=method, body=body, headers=headers,
                       timeout=timeout or TOKEN_TIMEOUT_SECONDS, **kwargs)

    return bounded


def verify_id_token(raw: str, cfg: GoogleConfig, *, nonce: str, request=None) -> dict:
    from google.auth import exceptions as google_exceptions
    from google.oauth2 import id_token

    try:
        claims = id_token.verify_oauth2_token(
            raw,
            request if request is not None else certs_transport(),
            audience=cfg.client_id,
            clock_skew_in_seconds=CLOCK_SKEW_SECONDS,
        )
    except google_exceptions.TransportError as exc:
        logger.warning("Google certificates unavailable: %s", type(exc).__name__)
        raise GoogleAuthError("unavailable") from exc
    except (ValueError, google_exceptions.GoogleAuthError) as exc:
        logger.warning("Google ID token rejected: %s", type(exc).__name__)
        raise GoogleAuthError("invalid") from exc
    if not isinstance(claims.get("nonce"), str) or not hmac.compare_digest(claims["nonce"], nonce):
        raise GoogleAuthError("invalid")
    if not isinstance(claims.get("sub"), str) or not claims["sub"]:
        raise GoogleAuthError("invalid")
    return claims


def email_authority(claims: dict) -> EmailAuthority:
    raw = claims.get("email")
    if claims.get("email_verified") is not True or not isinstance(raw, str) or "@" not in raw:
        return EmailAuthority("unverified", None)
    email = normalize_email(raw)
    domain = email.rpartition("@")[2]
    hd = claims.get("hd")
    if isinstance(hd, str) and hd:
        kind = "authoritative" if domain == hd.strip().lower() else "third_party"
    elif domain == "gmail.com":
        kind = "authoritative"
    else:
        kind = "third_party"
    return EmailAuthority(kind, email)


def _identity(session: Session, subject: str) -> Optional[UserIdentityRow]:
    return session.get(UserIdentityRow, (PROVIDER, subject))


def _login_existing(session: Session, identity: UserIdentityRow, claims: dict, user_agent):
    user = session.get(UserRow, identity.user_id)
    if user is None or user.role == "demo":
        raise GoogleAuthError("failed")
    identity.last_login_at = iso(utc_now())
    if isinstance(claims.get("email"), str):
        identity.email = normalize_email(claims["email"])
    session.commit()
    raw_token, _ = auth_service.create_session(session, user, user_agent=user_agent)
    return user, raw_token


def sign_in(session: Session, claims: dict, *, user_agent: Optional[str]) -> tuple[UserRow, str]:
    """Resolve verified claims to an account and open a session.

    Returning user (known ``sub``) → sign in, whatever the signup state.
    New user → only a Google-authoritative address, never one an account
    already holds (no implicit linking), and only where signup admits it.
    """
    from app.core.security_deps import signup_allowed_for

    subject = claims["sub"]
    identity = _identity(session, subject)
    if identity is not None:
        return _login_existing(session, identity, claims, user_agent)

    authority = email_authority(claims)
    if authority.kind == "unverified":
        raise GoogleAuthError("unverified_email")
    if authority.kind != "authoritative":
        raise GoogleAuthError("unsupported_email")
    email = authority.email
    if auth_service.get_user_by_email(session, email) is not None:
        raise GoogleAuthError("account_exists")
    if not signup_allowed_for(email):
        raise GoogleAuthError("signup_closed")

    name = claims.get("name") if isinstance(claims.get("name"), str) else None
    user, profile = auth_service.new_user_rows(
        email=email,
        password_hash=None,
        display_name=(name or "").strip()[:DISPLAY_NAME_MAX] or None,
        email_verified_method="google_authoritative",
    )
    now = iso(utc_now())
    try:
        session.add(user)
        session.add(profile)
        session.flush()  # the user row must exist before the identity's FK
        session.add(UserIdentityRow(
            provider=PROVIDER, subject=subject, user_id=user.id, email=email,
            created_at=now, last_login_at=now,
        ))
        # Google just proved ownership of the mailbox: unverified password
        # signups for it (a squatter's, or an abandoned one) die, and nothing
        # of theirs carries over.
        session.execute(delete(PendingRegistrationRow).where(PendingRegistrationRow.email == email))
        session.commit()
    except IntegrityError:
        session.rollback()
        # A concurrent first sign-in with the same subject won: use it.
        identity = _identity(session, subject)
        if identity is not None:
            return _login_existing(session, identity, claims, user_agent)
        raise GoogleAuthError("account_exists")
    session.refresh(user)
    raw_token, _ = auth_service.create_session(session, user, user_agent=user_agent)
    return user, raw_token


def complete_callback(
    session: Session, cfg: GoogleConfig, *, state: str, code: str, user_agent: Optional[str],
) -> tuple[UserRow, str]:
    pending = consume_pending(session, state)
    if pending.intent != "login":
        raise GoogleAuthError("failed")
    raw = exchange_code(cfg, code, pending.code_verifier)
    claims = verify_id_token(raw, cfg, nonce=pending.nonce)
    return sign_in(session, claims, user_agent=user_agent)


def has_google_identity(session: Session, user_id: str) -> bool:
    return session.execute(
        select(UserIdentityRow.subject)
        .where(UserIdentityRow.user_id == user_id, UserIdentityRow.provider == PROVIDER)
        .limit(1)
    ).first() is not None
