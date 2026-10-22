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
Google's ``sub``.

Email authority (docs/USER_PLATFORM.md, "Google sign-in"): registering, or
linking to an existing account, needs ``email_verified`` exactly true AND an
address Google is authoritative for: ``@gmail.com`` without ``hd``, or a
Workspace address whose domain equals ``hd``. Anything else is a third-party
address: never linked; it registers only through an emailed link plus a second
Google sign-in (#329). Linking by an authoritative address is automatic for the
roles in AUTO_LINK_ROLES (user and admin).
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

from app.db.orm_models import (
    AuthSessionRow,
    OAuthPendingRow,
    PendingGoogleRegistrationRow,
    PendingRegistrationRow,
    UserIdentityRow,
    UserRow,
)
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
    return _start_attempt(session, cfg, intent="login")


def start_delete_confirmation(
    session: Session, cfg: GoogleConfig, *, user_id: str, session_hash: str, login_hint: str,
) -> tuple[str, str]:
    """Record a deletion-confirmation attempt bound to this user and session
    (#331). Its callback can only ever produce a deletion grant."""
    return _start_attempt(
        session, cfg, intent="delete", user_id=user_id, session_hash=session_hash,
        login_hint=login_hint,
    )


def start_link(session: Session, cfg: GoogleConfig, *, user_id: str, session_hash: str) -> tuple[str, str]:
    """Record an explicit connect-Google attempt bound to this user and
    session (#330). Its callback links, never signs in or registers."""
    return _start_attempt(session, cfg, intent="link", user_id=user_id, session_hash=session_hash)


def _start_attempt(
    session: Session,
    cfg: GoogleConfig,
    *,
    intent: str,
    user_id: Optional[str] = None,
    session_hash: Optional[str] = None,
    login_hint: Optional[str] = None,
    registration_token_hash: Optional[str] = None,
) -> tuple[str, str]:
    if not _start_limiter.check("global"):
        raise auth_service.RateLimitExceeded("too many sign-in attempts")
    now = utc_now()
    session.execute(delete(OAuthPendingRow).where(OAuthPendingRow.expires_at <= iso(now)))
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    session.add(OAuthPendingRow(
        state_hash=token_hash(state),
        intent=intent,
        nonce=nonce,
        code_verifier=verifier,
        created_at=iso(now),
        expires_at=iso(now + PENDING_TTL),
        user_id=user_id,
        session_hash=session_hash,
        registration_token_hash=registration_token_hash,
    ))
    session.commit()
    params = {
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
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}", state


def consume_pending(session: Session, state: str) -> OAuthPendingRow:
    """Single use: of concurrent callbacks with one state, exactly one wins."""
    hashed = token_hash(state)
    row = session.get(OAuthPendingRow, hashed)
    if row is None or auth_service.parse_iso(row.expires_at) <= utc_now():
        raise GoogleAuthError("expired")
    snapshot = OAuthPendingRow(
        state_hash=row.state_hash, intent=row.intent, nonce=row.nonce,
        code_verifier=row.code_verifier, created_at=row.created_at, expires_at=row.expires_at,
        user_id=row.user_id, session_hash=row.session_hash,
        registration_token_hash=row.registration_token_hash,
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


# Roles whose existing account a Google-authoritative address may link to
# automatically: role=user from 2026-10-21, admin added by the owner on
# 2026-10-22 (#332). Demo rows have no email and can never match.
AUTO_LINK_ROLES = frozenset({"user", "admin"})


def _link_existing(
    session: Session, user: UserRow, subject: str, email: str, claims: dict, user_agent,
) -> tuple[UserRow, str]:
    """Attach this Google subject to the account that holds the address.

    Only for an authoritative address (the caller checked), only for
    AUTO_LINK_ROLES, and never when the account already has a different Google
    identity. Signup state does not apply: no account is created.
    """
    if user.role not in AUTO_LINK_ROLES:
        raise GoogleAuthError("account_exists")
    if has_google_identity(session, user.id):
        # Linked meanwhile by a concurrent sign-in with this same subject →
        # sign in; linked to a different Google account → refuse.
        identity = _identity(session, subject)
        if identity is not None and identity.user_id == user.id:
            return _login_existing(session, identity, claims, user_agent)
        raise GoogleAuthError("account_exists")
    now = iso(utc_now())
    session.add(UserIdentityRow(
        provider=PROVIDER, subject=subject, user_id=user.id, email=email,
        created_at=now, last_login_at=now,
    ))
    if user.email_verified_at is None:
        # Google just proved the address this account was registered with.
        user.email_verified_at = now
        user.email_verified_method = "google_authoritative"
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        # A concurrent sign-in linked the same subject first: use it.
        identity = _identity(session, subject)
        if identity is not None and identity.user_id == user.id:
            return _login_existing(session, identity, claims, user_agent)
        raise GoogleAuthError("account_exists")
    logger.info("Linked a Google identity to existing account %s", user.id)
    session.refresh(user)
    raw_token, _ = auth_service.create_session(session, user, user_agent=user_agent)
    return user, raw_token


def sign_in(session: Session, claims: dict, *, user_agent: Optional[str]) -> tuple[UserRow, str]:
    """Resolve verified claims to an account and open a session.

    Returning user (known ``sub``) → sign in, whatever the signup state.
    Unknown ``sub`` with a Google-authoritative address:
      an account already holds it → link it (role=user only) and sign in;
      no account → register, only where signup admits the address.
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
        # A third-party address: prove the mailbox with an emailed link (#329).
        # Always ends in a GoogleAuthError whose code tells /login what happened.
        _pend_google_registration(session, claims, authority.email)
    email = authority.email
    existing = auth_service.get_user_by_email(session, email)
    if existing is not None:
        return _link_existing(session, existing, subject, email, claims, user_agent)
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


def pending_intent(session: Session, state: str) -> Optional[str]:
    """Read-only: which kind of attempt ``state`` names (to route failures to
    the right page). Changes nothing; an unknown state yields None."""
    row = session.get(OAuthPendingRow, token_hash(state)) if state else None
    return row.intent if row is not None else None


def complete_delete_confirmation(
    session: Session, cfg: GoogleConfig, *, state: str, code: str, current_session_hash: Optional[str],
) -> None:
    """The callback of a deletion attempt (#331): it only ever issues a grant.

    Requires the session that started the attempt (same user, same session,
    still valid) and a Google sign-in as the SAME linked subject. Never signs
    in, never registers, never deletes. Not fresh re-authentication: a live
    Google session in this browser satisfies it (documented limitation).
    """
    pending = _consume_bound_attempt(
        session, state, intent="delete", current_session_hash=current_session_hash,
        failure="delete_failed",
    )
    raw = exchange_code(cfg, code, pending.code_verifier)
    claims = verify_id_token(raw, cfg, nonce=pending.nonce)
    identity = _identity(session, claims["sub"])
    if identity is None or identity.user_id != pending.user_id:
        raise GoogleAuthError("delete_wrong_account")
    auth_service.issue_reauth_grant(
        session, pending.user_id, session_hash=current_session_hash, purpose="delete_account",
    )


def linked_identity(session: Session, user_id: str) -> Optional[UserIdentityRow]:
    return session.execute(
        select(UserIdentityRow)
        .where(UserIdentityRow.user_id == user_id, UserIdentityRow.provider == PROVIDER)
        .limit(1)
    ).scalar_one_or_none()


def _consume_bound_attempt(
    session: Session, state: str, *, intent: str, current_session_hash: Optional[str], failure: str,
) -> OAuthPendingRow:
    """Consume an account-bound attempt (delete, link) and require that the
    browser completing it holds the very session that started it, still valid
    and still the same user."""
    pending = consume_pending(session, state)
    if pending.intent != intent or not pending.user_id or not pending.session_hash:
        raise GoogleAuthError(failure)
    if not current_session_hash or not hmac.compare_digest(pending.session_hash, current_session_hash):
        raise GoogleAuthError(failure)
    auth_session = session.get(AuthSessionRow, current_session_hash)
    if (auth_session is None or auth_session.user_id != pending.user_id
            or auth_service.parse_iso(auth_session.expires_at) <= utc_now()):
        raise GoogleAuthError(failure)
    return pending


def complete_link(
    session: Session, cfg: GoogleConfig, *, state: str, code: str, current_session_hash: Optional[str],
) -> None:
    """The callback of an explicit connect (#330). Any Google account may be
    connected (the password proved the Signal account; Google proves the
    Google account), but a subject already linked to another account is
    refused, and an account holds at most one Google identity."""
    pending = _consume_bound_attempt(
        session, state, intent="link", current_session_hash=current_session_hash,
        failure="failed",
    )
    raw = exchange_code(cfg, code, pending.code_verifier)
    claims = verify_id_token(raw, cfg, nonce=pending.nonce)
    subject, user_id = claims["sub"], pending.user_id
    existing = _identity(session, subject)
    if existing is not None:
        if existing.user_id == user_id:
            return  # already connected to this very account
        raise GoogleAuthError("taken")
    if has_google_identity(session, user_id):
        raise GoogleAuthError("already")
    email = claims.get("email")
    now = iso(utc_now())
    session.add(UserIdentityRow(
        provider=PROVIDER, subject=subject, user_id=user_id,
        email=normalize_email(email) if isinstance(email, str) else None,
        created_at=now, last_login_at=None,
    ))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = _identity(session, subject)
        if existing is not None and existing.user_id == user_id:
            return
        raise GoogleAuthError("taken" if existing is not None else "already")
    logger.info("Connected a Google identity to account %s", user_id)


# ── Third-party addresses: register through an emailed link (#329) ──────────
#
# Google is not authoritative for, e.g., a Google account on @yahoo.com, so
# its email_verified is not current proof of the mailbox. Such a sign-up
# becomes a pending_google_registrations row bound to the subject and the
# exact address, plus an emailed single-use link. Activation needs the link
# (mailbox) AND a new Google sign-in as the same subject with the same address
# (Google account); both are consumed together and the session goes only to
# the browser completing it. A third-party address never links to an
# existing account. "Resend" is simply signing in with Google again.


def _registration_expired(row: PendingGoogleRegistrationRow) -> bool:
    return auth_service.parse_iso(row.token_expires_at) <= utc_now()


def _pend_google_registration(session: Session, claims: dict, email: str) -> None:
    """Create or refresh the pending registration and email its link. Always
    raises GoogleAuthError: check_email, check_email_recent,
    check_email_send_failed, too_many, mail_unavailable, account_exists or
    signup_closed."""
    from app.core.security_deps import signup_allowed_for
    from app.services import email_verification, mailer

    if auth_service.get_user_by_email(session, email) is not None:
        raise GoogleAuthError("account_exists")
    if not signup_allowed_for(email):
        raise GoogleAuthError("signup_closed")
    send_with = mailer.get_mailer()
    if send_with is None:
        raise GoogleAuthError("mail_unavailable")

    subject = claims["sub"]
    now = utc_now()
    cutoff = iso(now - email_verification.PENDING_MAX_AGE)
    session.execute(
        delete(PendingGoogleRegistrationRow).where(PendingGoogleRegistrationRow.created_at <= cutoff))
    session.commit()
    row = session.execute(
        select(PendingGoogleRegistrationRow).where(PendingGoogleRegistrationRow.subject == subject)
    ).scalar_one_or_none()
    if row is not None and row.email != email:
        # The Google account's address changed: start over for the new one.
        session.delete(row)
        session.commit()
        row = None
    try:
        if row is not None:
            if row.last_sent_at:
                due = auth_service.parse_iso(row.last_sent_at) + email_verification.RESEND_COOLDOWN
                if due > now:
                    raise GoogleAuthError("check_email_recent")
            if row.send_count >= email_verification.MAX_SENDS:
                raise GoogleAuthError("too_many")
            email_verification.check_global_send_budget()
        else:
            email_verification.check_signup_email_budget(email)
            email_verification.check_global_send_budget()
    except auth_service.RateLimitExceeded as exc:
        raise GoogleAuthError("too_many") from exc

    token = secrets.token_urlsafe(auth_service.SESSION_TOKEN_BYTES)
    name = claims.get("name") if isinstance(claims.get("name"), str) else None
    if row is None:
        row = PendingGoogleRegistrationRow(
            id="pg_" + auth_service.generate_user_id().removeprefix("usr_"),
            subject=subject,
            email=email,
            display_name=(name or "").strip()[:DISPLAY_NAME_MAX] or None,
            created_at=iso(now),
            send_count=0,
        )
        session.add(row)
    row.token_hash = token_hash(token)
    row.token_expires_at = iso(now + email_verification.TOKEN_TTL)
    row.last_sent_at = iso(now)
    row.send_count = (row.send_count or 0) + 1
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        # A concurrent sign-in for the same subject created it first.
        raise GoogleAuthError("check_email_recent") from exc
    delivered = email_verification.deliver(
        email_verification.google_verification_email(email, token), send_with)
    raise GoogleAuthError("check_email" if delivered else "check_email_send_failed")


def _live_registration(session: Session, raw_token: str) -> Optional[PendingGoogleRegistrationRow]:
    row = session.execute(
        select(PendingGoogleRegistrationRow)
        .where(PendingGoogleRegistrationRow.token_hash == token_hash(raw_token))
    ).scalar_one_or_none()
    if row is None or _registration_expired(row):
        return None
    return row


def peek_google_registration(session: Session, raw_token: str) -> Optional[str]:
    """Read-only: the masked address a live link belongs to."""
    from app.services.email_verification import mask_email

    row = _live_registration(session, raw_token)
    return mask_email(row.email) if row is not None else None


def start_registration_verification(
    session: Session, cfg: GoogleConfig, *, raw_token: str,
) -> tuple[str, str]:
    """Open the emailed link: begin the second proof, a Google sign-in bound
    to this registration's current token. Raises GoogleAuthError("verify_expired")
    for an unknown, rotated or expired link."""
    row = _live_registration(session, raw_token)
    if row is None:
        raise GoogleAuthError("verify_expired")
    return _start_attempt(
        session, cfg, intent="verify_registration",
        registration_token_hash=row.token_hash, login_hint=row.email,
    )


def activate_google_registration(
    session: Session, claims: dict, *, registration_token_hash: str, user_agent: Optional[str],
) -> tuple[UserRow, str]:
    """Second proof complete: the same subject, the same address. Consumes the
    pending registration atomically and creates the account and its session."""
    from app.core.security_deps import signup_allowed_for

    row = session.execute(
        select(PendingGoogleRegistrationRow)
        .where(PendingGoogleRegistrationRow.token_hash == registration_token_hash)
    ).scalar_one_or_none()
    if row is None or _registration_expired(row):
        raise GoogleAuthError("verify_expired")
    if claims.get("sub") != row.subject:
        raise GoogleAuthError("verify_wrong_account")
    authority = email_authority(claims)
    if authority.kind == "unverified":
        raise GoogleAuthError("unverified_email")
    if authority.email != row.email:
        raise GoogleAuthError("verify_email_changed")
    email = row.email
    if auth_service.get_user_by_email(session, email) is not None:
        raise GoogleAuthError("account_exists")
    if not signup_allowed_for(email):
        raise GoogleAuthError("signup_closed")

    row_id, subject, display_name = row.id, row.subject, row.display_name
    session.expunge(row)
    # Atomic single use: of concurrent activations, exactly one deletes it.
    consumed = session.execute(
        delete(PendingGoogleRegistrationRow)
        .where(PendingGoogleRegistrationRow.id == row_id)
        .where(PendingGoogleRegistrationRow.token_hash == registration_token_hash)
        .where(PendingGoogleRegistrationRow.token_expires_at > iso(utc_now()))
    ).rowcount
    if consumed != 1:
        session.rollback()
        raise GoogleAuthError("verify_expired")
    user, profile = auth_service.new_user_rows(
        email=email, password_hash=None, display_name=display_name,
        email_verified_method="link",
    )
    now = iso(utc_now())
    try:
        session.add(user)
        session.add(profile)
        session.flush()
        session.add(UserIdentityRow(
            provider=PROVIDER, subject=subject, user_id=user.id, email=email,
            created_at=now, last_login_at=now,
        ))
        # The mailbox is now proven: other pending sign-ups for it never carry over.
        session.execute(delete(PendingRegistrationRow).where(PendingRegistrationRow.email == email))
        session.execute(
            delete(PendingGoogleRegistrationRow).where(PendingGoogleRegistrationRow.email == email))
        session.commit()
    except IntegrityError:
        session.rollback()
        identity = _identity(session, subject)
        if identity is not None:
            return _login_existing(session, identity, claims, user_agent)
        raise GoogleAuthError("account_exists")
    session.refresh(user)
    raw_session, _ = auth_service.create_session(session, user, user_agent=user_agent)
    return user, raw_session


def complete_registration_callback(
    session: Session, cfg: GoogleConfig, *, state: str, code: str, user_agent: Optional[str],
) -> tuple[UserRow, str]:
    pending = consume_pending(session, state)
    if pending.intent != "verify_registration" or not pending.registration_token_hash:
        raise GoogleAuthError("failed")
    raw = exchange_code(cfg, code, pending.code_verifier)
    claims = verify_id_token(raw, cfg, nonce=pending.nonce)
    return activate_google_registration(
        session, claims, registration_token_hash=pending.registration_token_hash,
        user_agent=user_agent,
    )
