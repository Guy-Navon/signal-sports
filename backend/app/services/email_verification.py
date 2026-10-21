"""Email ownership verification for password registration (Slice A).

Lifecycle (docs/USER_PLATFORM.md):
  signup   -> a pending_registrations row + one emailed link; no user, no session
  link     -> the SPA page; opening it changes nothing (scanner-safe)
  confirm  -> token + password, consumed atomically -> users row + profile +
              session, email_verified_method="link"
  resend   -> email + password; rotates the token (old links stop working)

Requiring the password at confirmation binds mailbox control (the token) to
knowledge of the credential: a mail scanner cannot activate anything, the
registering device is never signed in by someone else's click, and a squatter
who registered a victim's address still needs the victim to know the
squatter's password.
"""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass
from datetime import timedelta
from html import escape
from typing import Optional

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.orm_models import AuthSessionRow, PendingRegistrationRow, UserRow
from app.services import auth_service, mailer
from app.services.auth_service import (
    FixedWindowLimiter,
    get_user_by_email,
    iso,
    normalize_email,
    parse_iso,
    token_hash,
    utc_now,
)

logger = logging.getLogger(__name__)

TOKEN_TTL = timedelta(hours=24)
PENDING_MAX_AGE = timedelta(days=7)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_SENDS = 5
SIGNUPS_PER_EMAIL_LIMIT = 3
SIGNUPS_PER_EMAIL_WINDOW_SECONDS = 3600
GLOBAL_SEND_LIMIT = 30
GLOBAL_SEND_WINDOW_SECONDS = 600
# Login on an address with only pending rows verifies against at most this
# many (newest first), bounding the argon2 work an unknown caller can trigger.
PENDING_LOGIN_CHECK_LIMIT = 3

_signup_email_limiter = FixedWindowLimiter(SIGNUPS_PER_EMAIL_LIMIT, SIGNUPS_PER_EMAIL_WINDOW_SECONDS)
_global_send_limiter = FixedWindowLimiter(GLOBAL_SEND_LIMIT, GLOBAL_SEND_WINDOW_SECONDS)
# Password attempts at confirmation, per pending registration. Separate from
# the login limiter: confirming a fresh signup must not spend login budget.
_confirm_limiter = FixedWindowLimiter(auth_service.LOGIN_ACCOUNT_LIMIT, auth_service.LOGIN_WINDOW_SECONDS)


class VerificationError(Exception):
    pass


class MailNotConfigured(VerificationError):
    pass


class InvalidVerificationToken(VerificationError):
    pass


class ResendCooldown(VerificationError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("resend cooldown")
        self.retry_after = retry_after


@dataclass(frozen=True)
class SendOutcome:
    email: str
    delivered: bool


def reset_rate_limiters() -> None:
    _signup_email_limiter.reset()
    _global_send_limiter.reset()
    _confirm_limiter.reset()


def allowed_signup_emails() -> frozenset[str]:
    raw = os.environ.get("AUTH_SIGNUP_ALLOWED_EMAILS", "")
    return frozenset(normalize_email(e) for e in raw.split(",") if e.strip())


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}**@{domain}"


def _new_token() -> str:
    return secrets.token_urlsafe(auth_service.SESSION_TOKEN_BYTES)


def prune_abandoned(session: Session) -> int:
    cutoff = iso(utc_now() - PENDING_MAX_AGE)
    result = session.execute(
        delete(PendingRegistrationRow).where(PendingRegistrationRow.created_at <= cutoff)
    )
    session.commit()
    return result.rowcount or 0


def _verification_email(to: str, token: str) -> mailer.OutgoingEmail:
    link = f"{mailer.app_public_url()}/verify-email#t={token}"
    hours = int(TOKEN_TTL.total_seconds() // 3600)
    subject = "אימות כתובת האימייל שלך ב-Signal Sports"
    text = (
        "שלום,\n\n"
        "כדי להשלים את ההרשמה ל-Signal Sports, פתחו את הקישור הזה:\n"
        f"{link}\n\n"
        f"הקישור תקף ל-{hours} שעות. כדי להפעיל את החשבון תתבקשו להזין את הסיסמה שבחרתם.\n\n"
        "לא נרשמתם? אפשר להתעלם מההודעה הזאת. בלי הקישור והסיסמה אף חשבון לא יופעל.\n"
    )
    safe_link = escape(link, quote=True)
    html = (
        '<!doctype html><html lang="he" dir="rtl"><body dir="rtl" '
        'style="font-family:Arial,sans-serif;line-height:1.6;color:#111;">'
        "<p>שלום,</p>"
        "<p>כדי להשלים את ההרשמה ל-Signal Sports, לחצו על הקישור:</p>"
        f'<p><a href="{safe_link}" style="display:inline-block;padding:10px 18px;'
        'background:#111;color:#fff;text-decoration:none;border-radius:6px;">'
        "אימות כתובת האימייל</a></p>"
        f"<p>הקישור תקף ל-{hours} שעות. כדי להפעיל את החשבון תתבקשו להזין את הסיסמה שבחרתם.</p>"
        "<p>לא נרשמתם? אפשר להתעלם מההודעה הזאת. בלי הקישור והסיסמה אף חשבון לא יופעל.</p>"
        "</body></html>"
    )
    return mailer.OutgoingEmail(to=to, subject=subject, text=text, html=html)


def check_signup_email_budget(email: str) -> None:
    """Per-address signup limit, shared with password signups."""
    if not _signup_email_limiter.check(normalize_email(email)):
        raise auth_service.RateLimitExceeded("too many signups for this address")


def check_global_send_budget() -> None:
    _check_global_send_budget()


def _check_global_send_budget() -> None:
    # Checked BEFORE anything is stored or rotated, so a flood of signups
    # cannot pile up rows (each with an argon2 hash) past the send budget.
    if not _global_send_limiter.check("global"):
        logger.warning("Verification email refused: global send limit reached")
        raise auth_service.RateLimitExceeded("global send limit reached")


def google_verification_email(to: str, token: str) -> mailer.OutgoingEmail:
    """The link for a Google sign-up on a third-party address (#329): opening
    it leads to one more Google sign-in, not a password."""
    link = f"{mailer.app_public_url()}/verify-email#g={token}"
    hours = int(TOKEN_TTL.total_seconds() // 3600)
    subject = "אימות כתובת האימייל שלך ב-Signal Sports"
    text = (
        "שלום,\n\n"
        "כדי להשלים את ההרשמה ל-Signal Sports עם חשבון ה-Google שלכם, פתחו את הקישור הזה:\n"
        f"{link}\n\n"
        f"הקישור תקף ל-{hours} שעות. כדי להפעיל את החשבון תתבקשו להתחבר שוב עם אותו חשבון Google.\n\n"
        "לא נרשמתם? אפשר להתעלם מההודעה הזאת. בלי הקישור ובלי חשבון ה-Google אף חשבון לא יופעל.\n"
    )
    safe_link = escape(link, quote=True)
    html = (
        '<!doctype html><html lang="he" dir="rtl"><body dir="rtl" '
        'style="font-family:Arial,sans-serif;line-height:1.6;color:#111;">'
        "<p>שלום,</p>"
        "<p>כדי להשלים את ההרשמה ל-Signal Sports עם חשבון ה-Google שלכם, לחצו על הקישור:</p>"
        f'<p><a href="{safe_link}" style="display:inline-block;padding:10px 18px;'
        'background:#111;color:#fff;text-decoration:none;border-radius:6px;">'
        "אימות כתובת האימייל</a></p>"
        f"<p>הקישור תקף ל-{hours} שעות. כדי להפעיל את החשבון תתבקשו להתחבר שוב עם אותו חשבון Google.</p>"
        "<p>לא נרשמתם? אפשר להתעלם מההודעה הזאת. בלי הקישור ובלי חשבון ה-Google אף חשבון לא יופעל.</p>"
        "</body></html>"
    )
    return mailer.OutgoingEmail(to=to, subject=subject, text=text, html=html)


def deliver(message: mailer.OutgoingEmail, send_with: mailer.Mailer) -> bool:
    try:
        send_with.send(message)
        return True
    except mailer.MailDeliveryError as exc:
        # Domain only: never the token, never the full address.
        logger.warning(
            "Verification email delivery failed (domain %s): %s",
            message.to.partition("@")[2], exc,
        )
        return False


def _send(row: PendingRegistrationRow, token: str, send_with: mailer.Mailer) -> bool:
    return deliver(_verification_email(row.email, token), send_with)


def _require_mailer() -> mailer.Mailer:
    configured = mailer.get_mailer()
    if configured is None:
        raise MailNotConfigured("no mailer is configured")
    return configured


def start_registration(
    session: Session,
    *,
    email: str,
    password: str,
    display_name: Optional[str] = None,
) -> SendOutcome:
    """Record a pending registration and email its link. Raises
    DuplicateEmailError when an account already owns the address."""
    send_with = _require_mailer()
    normalized = normalize_email(email)
    if get_user_by_email(session, normalized) is not None:
        raise auth_service.DuplicateEmailError("email already exists")
    if not _signup_email_limiter.check(normalized):
        raise auth_service.RateLimitExceeded("too many signups for this address")
    _check_global_send_budget()
    prune_abandoned(session)

    token = _new_token()
    now = utc_now()
    row = PendingRegistrationRow(
        id="pr_" + auth_service.generate_user_id().removeprefix("usr_"),
        email=normalized,
        password_hash=auth_service.hash_password(password),
        display_name=display_name,
        token_hash=token_hash(token),
        token_expires_at=iso(now + TOKEN_TTL),
        created_at=iso(now),
        last_sent_at=iso(now),
        send_count=1,
    )
    session.add(row)
    session.commit()
    return SendOutcome(email=normalized, delivered=_send(row, token, send_with))


def _live_row(session: Session, token: str) -> Optional[PendingRegistrationRow]:
    row = session.query(PendingRegistrationRow).filter(
        PendingRegistrationRow.token_hash == token_hash(token)
    ).one_or_none()
    if row is None or parse_iso(row.token_expires_at) <= utc_now():
        return None
    return row


def peek(session: Session, token: str) -> Optional[str]:
    """The masked address a live token belongs to. Read-only."""
    row = _live_row(session, token)
    return mask_email(row.email) if row is not None else None


def confirm_registration(
    session: Session,
    *,
    token: str,
    password: str,
    user_agent: Optional[str] = None,
) -> tuple[UserRow, str, AuthSessionRow]:
    """Activate a pending registration. The token is consumed only when the
    password matches; consumption and account creation commit together."""
    row = _live_row(session, token)
    if row is None:
        raise InvalidVerificationToken("invalid or expired")
    if not _confirm_limiter.check(row.id):
        raise auth_service.RateLimitExceeded("too many attempts")
    if not auth_service.verify_password(row.password_hash, password):
        raise auth_service.InvalidPasswordError("password does not match")
    pending_id, email = row.id, row.email
    password_hash, display_name = row.password_hash, row.display_name
    session.expunge(row)

    # Atomic single use: of any concurrent confirmations, exactly one deletes
    # the row (SQLite serializes writers; the loser sees rowcount 0).
    consumed = session.execute(
        delete(PendingRegistrationRow)
        .where(PendingRegistrationRow.id == pending_id)
        .where(PendingRegistrationRow.token_hash == token_hash(token))
        .where(PendingRegistrationRow.token_expires_at > iso(utc_now()))
    ).rowcount
    if consumed != 1:
        session.rollback()
        raise InvalidVerificationToken("invalid or expired")
    user, profile = auth_service.new_user_rows(
        email=email,
        password_hash=password_hash,
        display_name=display_name,
        email_verified_method="link",
    )
    session.add(user)
    session.add(profile)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        # Another registration for this address won; this one can never
        # activate, so drop it.
        session.execute(delete(PendingRegistrationRow).where(PendingRegistrationRow.id == pending_id))
        session.commit()
        raise auth_service.DuplicateEmailError("email already exists") from exc
    # Every other pending row for the address (a squatter's, a duplicate) dies.
    session.execute(delete(PendingRegistrationRow).where(PendingRegistrationRow.email == email))
    session.commit()
    session.refresh(user)
    raw_token, auth_session = auth_service.create_session(session, user, user_agent=user_agent)
    return user, raw_token, auth_session


def _matching_pending(
    session: Session, email: str, password: str, *, dummy_when_absent: bool = True,
) -> Optional[PendingRegistrationRow]:
    rows = (
        session.query(PendingRegistrationRow)
        .filter(PendingRegistrationRow.email == normalize_email(email))
        .order_by(PendingRegistrationRow.created_at.desc())
        .limit(PENDING_LOGIN_CHECK_LIMIT)
        .all()
    )
    if not rows:
        if dummy_when_absent:
            auth_service.verify_dummy_password(password)
        return None
    for row in rows:
        if auth_service.verify_password(row.password_hash, password):
            return row
    return None


def pending_password_matches(session: Session, *, email: str, password: str) -> bool:
    """Login helper: does this email+password belong to an unverified signup?
    (login() already spent the dummy hash for an address with no account.)"""
    return _matching_pending(session, email, password, dummy_when_absent=False) is not None


def resend(session: Session, *, email: str, password: str) -> SendOutcome:
    """Rotate the link of the caller's own pending registration and resend.
    Cooldown and cap live on the row, so they survive restarts."""
    send_with = _require_mailer()
    # Resend verifies a password, so it shares login's guessing budget.
    normalized = normalize_email(email)
    if not auth_service._global_login_limiter.check("global"):
        raise auth_service.RateLimitExceeded("too many attempts")
    if not auth_service._account_login_limiter.check(normalized):
        raise auth_service.RateLimitExceeded("too many attempts")
    row = _matching_pending(session, normalized, password)
    if row is None:
        raise auth_service.InvalidCredentialsError("invalid email or password")
    now = utc_now()
    if row.last_sent_at:
        wait = parse_iso(row.last_sent_at) + RESEND_COOLDOWN - now
        if wait.total_seconds() > 0:
            raise ResendCooldown(retry_after=int(wait.total_seconds()) + 1)
    if row.send_count >= MAX_SENDS:
        raise auth_service.RateLimitExceeded("send cap reached")
    _check_global_send_budget()
    token = _new_token()
    row.token_hash = token_hash(token)
    row.token_expires_at = iso(now + TOKEN_TTL)
    row.last_sent_at = iso(now)
    row.send_count += 1
    session.commit()
    return SendOutcome(email=row.email, delivered=_send(row, token, send_with))
