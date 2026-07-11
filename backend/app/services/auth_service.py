import hashlib
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.orm_models import AuthSessionRow, ProfileRow, UserRow
from app.models.profile_v2 import ProfileV2

logger = logging.getLogger(__name__)

SESSION_TOKEN_BYTES = 32
SESSION_DAYS = 30
SESSION_LAST_SEEN_THROTTLE_SECONDS = 3600
LOGIN_ACCOUNT_LIMIT = 10
LOGIN_GLOBAL_LIMIT = 100
LOGIN_WINDOW_SECONDS = 300

_password_hasher = PasswordHasher()
_dummy_hash = _password_hasher.hash("signal-sports-dummy-password")


class AuthError(Exception):
    pass


class DuplicateEmailError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class InvalidPasswordError(AuthError):
    """Current-password verification failed for a lifecycle operation."""


class UndeletableAccountError(AuthError):
    """Demo accounts are permanent QA fixtures and can never be deleted."""


class LastAdminError(AuthError):
    """The last remaining admin cannot self-delete."""


class RateLimitExceeded(AuthError):
    pass


class FixedWindowLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._buckets: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            window_start, count = self._buckets.get(key, (now, 0))
            if now - window_start >= self.window_seconds:
                window_start, count = now, 0
            if count >= self.limit:
                self._buckets[key] = (window_start, count)
                return False
            self._buckets[key] = (window_start, count + 1)
            return True

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


_account_login_limiter = FixedWindowLimiter(LOGIN_ACCOUNT_LIMIT, LOGIN_WINDOW_SECONDS)
_global_login_limiter = FixedWindowLimiter(LOGIN_GLOBAL_LIMIT, LOGIN_WINDOW_SECONDS)


def reset_rate_limiters() -> None:
    _account_login_limiter.reset()
    _global_login_limiter.reset()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def verify_dummy_password(password: str) -> None:
    try:
        _password_hasher.verify(_dummy_hash, password)
    except Exception:
        pass


def generate_user_id() -> str:
    # ULID-compatible shape: 48-bit timestamp + 80 random bits in Crockford base32.
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    value = (int(time.time() * 1000) << 80) | secrets.randbits(80)
    chars = []
    for _ in range(26):
        chars.append(alphabet[value & 31])
        value >>= 5
    return "usr_" + "".join(reversed(chars))


def generate_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def empty_profile_row(user_id: str, display_name: str, profile_type: str = "self_serve") -> ProfileRow:
    profile_v2 = ProfileV2()
    return ProfileRow(
        user_id=user_id,
        display_name=display_name,
        language="he",
        profile_type=profile_type,
        topics=[],
        muted_topics=[],
        muted_sources=[],
        followed_entities=[],
        profile_v2=profile_v2.model_dump(mode="json"),
    )


def public_user_payload(user: UserRow) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "created_at": user.created_at,
        "onboarding_completed_at": user.onboarding_completed_at,
        "interests_completed_at": user.interests_completed_at,
        "last_login_at": user.last_login_at,
    }


def get_user_by_email(session: Session, email: str) -> Optional[UserRow]:
    normalized = normalize_email(email)
    return session.execute(
        select(UserRow).where(UserRow.email == normalized)
    ).scalar_one_or_none()


def create_user_with_profile(
    session: Session,
    *,
    email: str,
    password: str,
    role: str = "user",
    display_name: Optional[str] = None,
    onboarding_completed_at: Optional[datetime] = None,
) -> UserRow:
    normalized = normalize_email(email)
    now = utc_now()
    user_id = generate_user_id()
    user = UserRow(
        id=user_id,
        email=normalized,
        password_hash=hash_password(password),
        role=role,
        created_at=iso(now),
        onboarding_completed_at=iso(onboarding_completed_at) if onboarding_completed_at else None,
        last_login_at=None,
    )
    profile_name = display_name or normalized.split("@", 1)[0] or "User"
    session.add(user)
    session.add(empty_profile_row(user_id, profile_name))
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateEmailError("email already exists") from exc
    session.refresh(user)
    return user


def complete_onboarding(session: Session, user: UserRow) -> UserRow:
    """Stamp onboarding_completed_at exactly once (idempotent).

    Called from the /me calibration-apply and onboarding-skip paths (issue #50).
    The timestamp is the single source of the derived onboarding state machine
    (docs/USER_PLATFORM.md) - it is never cleared or rewritten here.
    """
    if user.onboarding_completed_at is None:
        user.onboarding_completed_at = iso(utc_now())
        session.commit()
        session.refresh(user)
    return user


def create_session(
    session: Session,
    user: UserRow,
    *,
    user_agent: Optional[str] = None,
) -> tuple[str, AuthSessionRow]:
    now = utc_now()
    raw_token = generate_session_token()
    row = AuthSessionRow(
        token_hash=token_hash(raw_token),
        user_id=user.id,
        created_at=iso(now),
        expires_at=iso(now + timedelta(days=SESSION_DAYS)),
        last_seen_at=iso(now),
        user_agent=user_agent,
    )
    user.last_login_at = iso(now)
    session.add(row)
    session.commit()
    session.refresh(row)
    return raw_token, row


def login(
    session: Session,
    *,
    email: str,
    password: str,
    user_agent: Optional[str] = None,
) -> tuple[UserRow, str, AuthSessionRow]:
    normalized = normalize_email(email)
    if not _global_login_limiter.check("global"):
        verify_dummy_password(password)
        raise RateLimitExceeded("too many login attempts")
    if not _account_login_limiter.check(normalized):
        verify_dummy_password(password)
        raise RateLimitExceeded("too many login attempts")

    user = get_user_by_email(session, normalized)
    if user is None or not user.password_hash:
        verify_dummy_password(password)
        raise InvalidCredentialsError("invalid email or password")
    if not verify_password(user.password_hash, password):
        raise InvalidCredentialsError("invalid email or password")
    prune_expired_sessions(session)  # opportunistic cleanup (issue #55)
    raw_token, auth_session = create_session(session, user, user_agent=user_agent)
    return user, raw_token, auth_session


def get_session_user(session: Session, raw_token: Optional[str]) -> Optional[UserRow]:
    if not raw_token:
        return None
    hashed = token_hash(raw_token)
    auth_session = session.get(AuthSessionRow, hashed)
    if auth_session is None:
        return None
    now = utc_now()
    if parse_iso(auth_session.expires_at) <= now:
        session.delete(auth_session)
        session.commit()
        return None
    user = session.get(UserRow, auth_session.user_id)
    if user is None:
        return None
    last_seen = parse_iso(auth_session.last_seen_at) if auth_session.last_seen_at else None
    if last_seen is None or (now - last_seen).total_seconds() >= SESSION_LAST_SEEN_THROTTLE_SECONDS:
        auth_session.last_seen_at = iso(now)
        session.commit()
    return user


def revoke_session(session: Session, raw_token: Optional[str]) -> None:
    if not raw_token:
        return
    row = session.get(AuthSessionRow, token_hash(raw_token))
    if row is not None:
        session.delete(row)
        session.commit()


def prune_expired_sessions(session: Session) -> int:
    """Delete session rows past their expiry (opportunistic, on login — #55)."""
    now = iso(utc_now())
    pruned = (
        session.query(AuthSessionRow)
        .filter(AuthSessionRow.expires_at <= now)
        .delete(synchronize_session=False)
    )
    if pruned:
        session.commit()
    return pruned


def revoke_other_sessions(session: Session, user_id: str, keep_token_hash: str) -> int:
    """Revoke every session of ``user_id`` except the one identified by
    ``keep_token_hash`` (password change keeps the active session — #55)."""
    revoked = (
        session.query(AuthSessionRow)
        .filter(AuthSessionRow.user_id == user_id)
        .filter(AuthSessionRow.token_hash != keep_token_hash)
        .delete(synchronize_session=False)
    )
    session.commit()
    return revoked


def change_password(
    session: Session,
    user: UserRow,
    *,
    current_password: str,
    new_password: str,
    keep_raw_token: str,
) -> int:
    """Verify the current password, set the new one, and revoke all OTHER
    sessions (the active session survives). Returns the revoke count (#55)."""
    if not user.password_hash or not verify_password(user.password_hash, current_password):
        raise InvalidPasswordError("current password is incorrect")
    user.password_hash = hash_password(new_password)
    session.commit()
    return revoke_other_sessions(session, user.id, token_hash(keep_raw_token))


def delete_account(session: Session, user: UserRow, *, current_password: str) -> None:
    """Hard-delete the account and exactly its own personalization rows, in
    one transaction (#55): feedback_events → calibration_responses → profiles
    → users (auth_sessions cascade via the FK; deleted explicitly as well for
    belt-and-braces under SQLite pragma configurations).

    Guards: demo rows are permanent QA fixtures (undeletable — they also can
    never hold a session, so this is defense in depth); the last remaining
    admin cannot self-delete.
    """
    from app.db.orm_models import CalibrationResponseRow, FeedbackRow, ProfileRow

    if user.role == "demo":
        raise UndeletableAccountError("demo accounts are permanent QA fixtures")
    if not user.password_hash or not verify_password(user.password_hash, current_password):
        raise InvalidPasswordError("current password is incorrect")
    if user.role == "admin":
        admins = session.query(UserRow).filter(UserRow.role == "admin").count()
        if admins <= 1:
            raise LastAdminError("the last remaining admin cannot self-delete")

    uid = user.id
    session.query(FeedbackRow).filter(FeedbackRow.user_id == uid).delete(
        synchronize_session=False)
    session.query(CalibrationResponseRow).filter(
        CalibrationResponseRow.user_id == uid).delete(synchronize_session=False)
    session.query(ProfileRow).filter(ProfileRow.user_id == uid).delete(
        synchronize_session=False)
    session.query(AuthSessionRow).filter(AuthSessionRow.user_id == uid).delete(
        synchronize_session=False)
    session.query(UserRow).filter(UserRow.id == uid).delete(synchronize_session=False)
    session.commit()


def log_admin_mutation(admin: Optional[UserRow], target_user_id: str, action: str) -> None:
    """Ops-hardening breadcrumb (#55): an admin mutating a NON-demo user via
    the explicit {user_id} surface is unusual enough to leave a trace. Demo
    fixtures are the intended QA targets — no log for them. ``admin`` is None
    on the /me delegation path (self-mutation) and under the dev bypass."""
    if not isinstance(admin, UserRow) or target_user_id in ("guy", "casual_deni_fan"):
        # None on the /me delegation path and under the dev bypass; a Depends
        # sentinel when a legacy handler is invoked directly (delegation).
        return
    logger.warning(
        "ADMIN MUTATION: admin %s (%s) performed %r on non-demo user %r via the "
        "explicit {user_id} surface",
        admin.id, admin.email, action, target_user_id,
    )


def ensure_users_for_profiles(session: Session) -> int:
    created = 0
    profile_rows = session.execute(select(ProfileRow)).scalars().all()
    now = iso(utc_now())
    for profile in profile_rows:
        if session.get(UserRow, profile.user_id) is not None:
            continue
        session.add(UserRow(
            id=profile.user_id,
            email=None,
            password_hash=None,
            role="demo",
            created_at=now,
            onboarding_completed_at=None,
            last_login_at=None,
        ))
        created += 1
    if created:
        session.commit()
    return created


def bootstrap_admin(session: Session, *, email: Optional[str], password: Optional[str]) -> Optional[UserRow]:
    if bool(email) != bool(password):
        logger.warning(
            "Partial admin bootstrap configuration ignored: set both "
            "AUTH_ADMIN_EMAIL and AUTH_ADMIN_PASSWORD, or unset both."
        )
        return None

    existing_admin = session.execute(
        select(UserRow).where(UserRow.role == "admin")
    ).scalar_one_or_none()
    if existing_admin is not None:
        return None
    if not email or not password:
        return None
    existing_user = get_user_by_email(session, email)
    if existing_user is not None:
        raise RuntimeError(
            "AUTH_ADMIN_EMAIL is already registered to a non-admin account. "
            "Unset AUTH_ADMIN_EMAIL/AUTH_ADMIN_PASSWORD or explicitly resolve/promote "
            "that account through a supported admin path."
        )
    return create_user_with_profile(
        session,
        email=email,
        password=password,
        role="admin",
        display_name="Admin",
        onboarding_completed_at=utc_now(),
    )
