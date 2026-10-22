"""Password reset by email (#200).

  forgot  -> the same answer whatever the address: no account, a Google-only
             account (it signs in with Google), a throttled request and a
             real one all look alike. For a password account a single-use,
             one-hour token is stored as a hash and the link is emailed after
             the response is sent, so timing does not tell them apart either.
  reset   -> token + new password: consumed atomically, the password set,
             every session revoked, every other reset link killed. No
             automatic sign-in; the person signs in with the new password.

A reset proves control of the mailbox, so an address never proven before is
marked verified (method "link"); an earlier verification is kept.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from html import escape
from typing import Optional

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.db.orm_models import AuthSessionRow, PasswordResetTokenRow, UserRow
from app.services import auth_service, email_verification, mailer
from app.services.auth_service import FixedWindowLimiter, iso, normalize_email, token_hash, utc_now

logger = logging.getLogger(__name__)

RESET_TTL = timedelta(hours=1)
RESET_COOLDOWN = timedelta(seconds=60)
RESETS_PER_EMAIL_LIMIT = 3
RESETS_PER_EMAIL_WINDOW_SECONDS = 3600

_reset_email_limiter = FixedWindowLimiter(RESETS_PER_EMAIL_LIMIT, RESETS_PER_EMAIL_WINDOW_SECONDS)


class InvalidResetToken(Exception):
    pass


@dataclass(frozen=True)
class PendingResetEmail:
    """What the route sends after responding (FastAPI BackgroundTasks)."""
    message: mailer.OutgoingEmail
    send_with: mailer.Mailer


def reset_rate_limiters() -> None:
    _reset_email_limiter.reset()


def _reset_email(to: str, token: str) -> mailer.OutgoingEmail:
    link = f"{mailer.app_public_url()}/reset-password#t={token}"
    minutes = int(RESET_TTL.total_seconds() // 60)
    subject = "איפוס הסיסמה שלך ב-Signal Sports"
    text = (
        "שלום,\n\n"
        "ביקשתם לאפס את הסיסמה לחשבון ב-Signal Sports. לבחירת סיסמה חדשה, פתחו את הקישור:\n"
        f"{link}\n\n"
        f"הקישור תקף ל-{minutes} דקות ולשימוש אחד.\n\n"
        "לא ביקשתם? אפשר להתעלם מההודעה הזאת. הסיסמה הנוכחית לא משתנה בלי הקישור.\n"
    )
    safe_link = escape(link, quote=True)
    html = (
        '<!doctype html><html lang="he" dir="rtl"><body dir="rtl" '
        'style="font-family:Arial,sans-serif;line-height:1.6;color:#111;">'
        "<p>שלום,</p>"
        "<p>ביקשתם לאפס את הסיסמה לחשבון ב-Signal Sports. לבחירת סיסמה חדשה:</p>"
        f'<p><a href="{safe_link}" style="display:inline-block;padding:10px 18px;'
        'background:#111;color:#fff;text-decoration:none;border-radius:6px;">'
        "בחירת סיסמה חדשה</a></p>"
        f"<p>הקישור תקף ל-{minutes} דקות ולשימוש אחד.</p>"
        "<p>לא ביקשתם? אפשר להתעלם מההודעה הזאת. הסיסמה הנוכחית לא משתנה בלי הקישור.</p>"
        "</body></html>"
    )
    return mailer.OutgoingEmail(to=to, subject=subject, text=text, html=html)


def request_reset(session: Session, *, email: str) -> Optional[PendingResetEmail]:
    """Return the email to send after responding, or None. The caller answers
    identically either way. Raises email_verification.MailNotConfigured when
    no mailer exists (the same for every address)."""
    send_with = mailer.get_mailer()
    if send_with is None:
        raise email_verification.MailNotConfigured("no mailer is configured")
    normalized = normalize_email(email)
    user = auth_service.get_user_by_email(session, normalized)
    if user is None or not user.password_hash or user.role == "demo":
        return None
    now = utc_now()
    latest = (
        session.query(PasswordResetTokenRow)
        .filter(PasswordResetTokenRow.user_id == user.id)
        .order_by(PasswordResetTokenRow.created_at.desc())
        .first()
    )
    if latest is not None and auth_service.parse_iso(latest.created_at) + RESET_COOLDOWN > now:
        return None
    if not _reset_email_limiter.check(normalized):
        return None
    try:
        email_verification.check_global_send_budget()
    except auth_service.RateLimitExceeded:
        return None
    token = secrets.token_urlsafe(auth_service.SESSION_TOKEN_BYTES)
    session.add(PasswordResetTokenRow(
        token_hash=token_hash(token),
        user_id=user.id,
        created_at=iso(now),
        expires_at=iso(now + RESET_TTL),
        consumed_at=None,
    ))
    session.commit()
    return PendingResetEmail(message=_reset_email(user.email, token), send_with=send_with)


def send_reset_email(pending: PendingResetEmail) -> None:
    email_verification.deliver(pending.message, pending.send_with)


def _live_token(session: Session, raw_token: str) -> Optional[PasswordResetTokenRow]:
    row = session.get(PasswordResetTokenRow, token_hash(raw_token))
    if row is None or row.consumed_at is not None:
        return None
    if auth_service.parse_iso(row.expires_at) <= utc_now():
        return None
    return row


def peek(session: Session, raw_token: str) -> Optional[str]:
    """Read-only: the masked address a live link belongs to."""
    row = _live_token(session, raw_token)
    if row is None:
        return None
    user = session.get(UserRow, row.user_id)
    return email_verification.mask_email(user.email) if user is not None and user.email else None


def complete_reset(session: Session, *, raw_token: str, new_password: str) -> UserRow:
    row = _live_token(session, raw_token)
    if row is None:
        raise InvalidResetToken("invalid or expired")
    hashed, user_id = row.token_hash, row.user_id
    session.expunge(row)
    now = iso(utc_now())
    # Atomic single use: of concurrent resets with one link, exactly one wins.
    consumed = session.execute(
        update(PasswordResetTokenRow)
        .where(PasswordResetTokenRow.token_hash == hashed)
        .where(PasswordResetTokenRow.consumed_at.is_(None))
        .where(PasswordResetTokenRow.expires_at > now)
        .values(consumed_at=now)
    ).rowcount
    if consumed != 1:
        session.rollback()
        raise InvalidResetToken("invalid or expired")
    user = session.get(UserRow, user_id)
    if user is None or user.role == "demo":
        session.rollback()
        raise InvalidResetToken("invalid or expired")
    user.password_hash = auth_service.hash_password(new_password)
    if user.email_verified_at is None:
        user.email_verified_at = now
        user.email_verified_method = "link"
    # Every other link dies; every session ends.
    session.execute(
        delete(PasswordResetTokenRow)
        .where(PasswordResetTokenRow.user_id == user_id)
        .where(PasswordResetTokenRow.token_hash != hashed)
    )
    session.execute(delete(AuthSessionRow).where(AuthSessionRow.user_id == user_id))
    session.commit()
    session.refresh(user)
    logger.info("Password reset completed for account %s", user_id)
    return user
