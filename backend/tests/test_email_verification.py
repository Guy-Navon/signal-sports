"""Email verification for password registration (Slice A).

A password signup creates a pending registration only: no user, no profile, no
session. The emailed link plus the password activates it. These tests drive the
real HTTP routes with the in-memory mailer the suite pins (conftest
MAIL_BACKEND=memory) and read the link out of the captured message.
"""

import re
import threading
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.orm_models import (
    AuthSessionRow,
    PendingRegistrationRow,
    ProfileRow,
    UserRow,
)
from app.services import auth_service, email_verification, mailer

PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def _clean(client, monkeypatch):  # client: the app lifespan creates the tables
    auth_service.reset_rate_limiters()
    email_verification.reset_rate_limiters()
    mailer.MEMORY_OUTBOX.clear()
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    _cleanup()
    yield
    _cleanup()
    mailer.MEMORY_OUTBOX.clear()


def _cleanup():
    with SessionLocal() as session:
        session.query(PendingRegistrationRow).delete(synchronize_session=False)
        session.query(AuthSessionRow).delete(synchronize_session=False)
        session.query(UserRow).filter(UserRow.role != "demo").delete(synchronize_session=False)
        session.query(ProfileRow).filter(
            ~ProfileRow.user_id.in_(["guy", "casual_deni_fan"])
        ).delete(synchronize_session=False)
        session.commit()


def _signup(client, email="New@Example.com", password=PASSWORD):
    return client.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "display_name": "New User"},
    )


def _last_token(to=None):
    messages = [m for m in mailer.MEMORY_OUTBOX if to is None or m.to == to]
    assert messages, "no verification email was sent"
    match = re.search(r"/verify-email#t=([A-Za-z0-9_\-]+)", messages[-1].text)
    assert match, messages[-1].text
    return match.group(1)


def _confirm(client, token, password=PASSWORD):
    return client.post(
        "/api/auth/verification/confirm", json={"token": token, "password": password}
    )


def _counts():
    with SessionLocal() as session:
        return (
            session.query(UserRow).filter(UserRow.role != "demo").count(),
            session.query(PendingRegistrationRow).count(),
        )


# ── Signup creates a pending registration only ───────────────────────────────

def test_signup_creates_no_user_no_session_and_sends_one_email(client):
    response = _signup(client)
    assert response.status_code == 202
    assert response.json() == {"status": "verification_sent", "email": "new@example.com"}
    assert "set-cookie" not in response.headers
    assert _counts() == (0, 1)
    assert len(mailer.MEMORY_OUTBOX) == 1
    message = mailer.MEMORY_OUTBOX[0]
    assert message.to == "new@example.com"
    assert "http://localhost:5173/verify-email#t=" in message.text
    assert 'dir="rtl"' in message.html


def test_pending_registration_stores_only_hashes(client):
    _signup(client)
    token = _last_token()
    with SessionLocal() as session:
        row = session.query(PendingRegistrationRow).one()
        assert row.password_hash.startswith("$argon2")
        assert row.token_hash == auth_service.token_hash(token)
        assert token not in (row.token_hash, row.password_hash)


def test_signup_for_an_existing_account_is_409_and_sends_nothing(client):
    with SessionLocal() as session:
        auth_service.create_user_with_profile(session, email="taken@example.com", password=PASSWORD)
    response = _signup(client, "Taken@Example.com")
    assert response.status_code == 409
    assert mailer.MEMORY_OUTBOX == []


def test_a_squatted_pending_registration_does_not_block_the_real_owner(client):
    assert _signup(client, "victim@example.com", password="attacker password").status_code == 202
    attacker_token = _last_token()
    assert _signup(client, "victim@example.com", password=PASSWORD).status_code == 202
    owner_token = _last_token()
    assert owner_token != attacker_token

    response = _confirm(client, owner_token)
    assert response.status_code == 200
    # Activation discards every other pending row for the address, so the
    # attacker's link (and password) can never produce a second path in.
    assert _counts() == (1, 0)
    assert _confirm(client, attacker_token, "attacker password").status_code == 400


# ── Confirmation ─────────────────────────────────────────────────────────────

def test_confirm_with_password_activates_verifies_and_signs_in(client):
    _signup(client)
    response = _confirm(TestClient(client.app), _last_token())
    assert response.status_code == 200, response.text
    user = response.json()["user"]
    assert user["email"] == "new@example.com"
    assert user["email_verified_at"] is not None
    assert response.cookies.get(settings.auth_cookie_name)
    with SessionLocal() as session:
        row = session.get(UserRow, user["id"])
        assert row.email_verified_method == "link"
        assert row.password_hash.startswith("$argon2")
        assert session.get(ProfileRow, user["id"]).display_name == "New User"
    assert _counts() == (1, 0)


def test_opening_the_link_alone_activates_nothing(client):
    """A mail scanner GETs the link (and may run the page's script); the page
    only peeks, which is read-only."""
    _signup(client)
    token = _last_token()
    client.get(f"/verify-email#t={token}")
    peek = client.post("/api/auth/verification/peek", json={"token": token})
    assert peek.status_code == 200
    assert peek.json() == {"email": "n**@example.com"}
    assert _counts() == (0, 1)


def test_wrong_password_is_refused_and_keeps_the_link_usable(client):
    _signup(client)
    token = _last_token()
    wrong = _confirm(client, token, "not the password")
    assert wrong.status_code == 403
    assert "set-cookie" not in wrong.headers
    assert _counts() == (0, 1)
    assert _confirm(client, token).status_code == 200


def test_a_link_is_single_use(client):
    _signup(client)
    token = _last_token()
    assert _confirm(client, token).status_code == 200
    replay = _confirm(TestClient(client.app), token)
    assert replay.status_code == 400
    assert replay.json()["detail"] == "Verification link is invalid or expired"


def test_an_expired_link_is_refused(client):
    _signup(client)
    token = _last_token()
    with SessionLocal() as session:
        row = session.query(PendingRegistrationRow).one()
        row.token_expires_at = auth_service.iso(auth_service.utc_now() - timedelta(seconds=1))
        session.commit()
    assert _confirm(client, token).status_code == 400
    assert client.post("/api/auth/verification/peek", json={"token": token}).status_code == 404
    assert _counts() == (0, 1)


def test_an_unknown_token_is_refused(client):
    assert _confirm(client, "not-a-real-token").status_code == 400


def test_confirm_races_on_one_token_create_exactly_one_user(client):
    _signup(client)
    token = _last_token()
    barrier = threading.Barrier(2)
    statuses = []

    def attempt():
        with SessionLocal() as session:
            barrier.wait()
            try:
                email_verification.confirm_registration(session, token=token, password=PASSWORD)
                statuses.append("ok")
            except email_verification.InvalidVerificationToken:
                statuses.append("invalid")

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(statuses) == ["invalid", "ok"]
    assert _counts() == (1, 0)


def test_confirm_races_on_two_registrations_of_one_email_create_one_user(client):
    _signup(client, "race@example.com")
    first = _last_token()
    _signup(client, "race@example.com")
    second = _last_token()
    barrier = threading.Barrier(2)
    outcomes = []

    def attempt(token):
        with SessionLocal() as session:
            barrier.wait()
            try:
                email_verification.confirm_registration(session, token=token, password=PASSWORD)
                outcomes.append("ok")
            except (email_verification.InvalidVerificationToken,
                    auth_service.DuplicateEmailError):
                outcomes.append("refused")

    threads = [threading.Thread(target=attempt, args=(t,)) for t in (first, second)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["ok", "refused"]
    with SessionLocal() as session:
        assert session.query(UserRow).filter(UserRow.email == "race@example.com").count() == 1


# ── Login before verification; ordinary login unchanged ──────────────────────

def test_login_before_verifying_says_so_only_with_the_right_password(client):
    _signup(client)
    right = client.post("/api/auth/login", json={"email": "new@example.com", "password": PASSWORD})
    assert right.status_code == 403
    assert right.json()["detail"] == "Email not verified"
    assert "set-cookie" not in right.headers
    wrong = client.post("/api/auth/login", json={"email": "new@example.com", "password": "nope"})
    assert wrong.status_code == 401
    assert wrong.json() == {"detail": "Invalid email or password"}


def test_verified_login_sends_no_email(client):
    _signup(client)
    _confirm(client, _last_token())
    mailer.MEMORY_OUTBOX.clear()
    response = TestClient(client.app).post(
        "/api/auth/login", json={"email": "new@example.com", "password": PASSWORD})
    assert response.status_code == 200
    assert mailer.MEMORY_OUTBOX == []


def test_legacy_and_admin_accounts_log_in_unverified(client):
    """Historical rows keep NULL: access is preserved without claiming the
    address was ever proven."""
    with SessionLocal() as session:
        auth_service.create_user_with_profile(session, email="legacy@example.com", password=PASSWORD)
        admin = auth_service.bootstrap_admin(session, email="boot@example.com", password=PASSWORD)
        assert admin.email_verified_at is None and admin.email_verified_method is None
    response = client.post("/api/auth/login", json={"email": "legacy@example.com", "password": PASSWORD})
    assert response.status_code == 200
    assert response.json()["user"]["email_verified_at"] is None


# ── Resend ───────────────────────────────────────────────────────────────────

def _resend(client, email="new@example.com", password=PASSWORD):
    return client.post("/api/auth/verification/resend", json={"email": email, "password": password})


def _age_last_send(seconds):
    with SessionLocal() as session:
        for row in session.query(PendingRegistrationRow):
            row.last_sent_at = auth_service.iso(auth_service.utc_now() - timedelta(seconds=seconds))
        session.commit()


def test_resend_rotates_the_link(client):
    _signup(client)
    old = _last_token()
    _age_last_send(61)
    response = _resend(client)
    assert response.status_code == 200
    assert response.json() == {"status": "verification_sent"}
    new = _last_token()
    assert new != old
    assert _confirm(client, old).status_code == 400
    assert _confirm(client, new).status_code == 200


def test_resend_has_a_cooldown_that_lives_in_the_database(client):
    _signup(client)
    email_verification.reset_rate_limiters()  # an API restart forgets in-memory limits
    response = _resend(client)
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


def test_resend_is_capped_per_registration(client):
    _signup(client)
    for _ in range(email_verification.MAX_SENDS - 1):
        _age_last_send(61)
        assert _resend(client).status_code == 200
    _age_last_send(61)
    assert _resend(client).status_code == 429


def test_resend_requires_the_password(client):
    _signup(client)
    _age_last_send(61)
    assert _resend(client, password="wrong password").status_code == 401
    assert _resend(client, email="nobody@example.com").status_code == 401
    assert len(mailer.MEMORY_OUTBOX) == 1


# ── Delivery failure, closed signup, pruning ─────────────────────────────────

def test_delivery_failure_keeps_the_registration_for_resend(client, monkeypatch, caplog):
    def boom(message):
        raise mailer.MailDeliveryError("smtp down")

    monkeypatch.setattr(mailer.MemoryMailer, "send", lambda self, message: boom(message))
    response = _signup(client)
    assert response.status_code == 202
    assert response.json()["status"] == "verification_send_failed"
    assert _counts() == (0, 1)
    assert "new@example.com" not in caplog.text


def test_tokens_never_reach_the_log(client, caplog):
    caplog.set_level("DEBUG")
    _signup(client)
    assert _last_token() not in caplog.text


def test_closed_signup_admits_only_allowlisted_addresses(client, monkeypatch):
    monkeypatch.setenv("AUTH_SIGNUP_ENABLED", "false")
    monkeypatch.setenv("AUTH_SIGNUP_ALLOWED_EMAILS", " Friend@Example.com , other@example.com")
    refused = _signup(client, "stranger@example.com")
    assert refused.status_code == 403
    assert _counts() == (0, 0)
    allowed = _signup(client, "friend@example.com")
    assert allowed.status_code == 202
    # Allowlisted still means "proven by the link": nothing is active yet.
    assert _counts() == (0, 1)
    assert _confirm(client, _last_token()).status_code == 200


def test_signup_fails_closed_without_a_mailer(client, monkeypatch):
    monkeypatch.setenv("MAIL_BACKEND", "")
    monkeypatch.setenv("DEPLOY_ENV", "hosted")
    response = _signup(client)
    assert response.status_code == 503
    assert _counts() == (0, 0)


def test_abandoned_registrations_are_pruned(client):
    _signup(client, "old@example.com")
    with SessionLocal() as session:
        row = session.query(PendingRegistrationRow).one()
        row.created_at = auth_service.iso(
            auth_service.utc_now() - email_verification.PENDING_MAX_AGE - timedelta(minutes=1))
        session.commit()
    _signup(client, "fresh@example.com")
    with SessionLocal() as session:
        emails = [r.email for r in session.query(PendingRegistrationRow)]
    assert emails == ["fresh@example.com"]


def test_signups_per_address_are_rate_limited(client):
    for _ in range(email_verification.SIGNUPS_PER_EMAIL_LIMIT):
        assert _signup(client, "spam@example.com").status_code == 202
    assert _signup(client, "spam@example.com").status_code == 429


# ── Schema: the new users columns reach a legacy database ────────────────────

def test_verification_columns_reach_a_legacy_users_table(tmp_path):
    """create_all never ALTERs an existing table; the soft migration must add
    the nullable columns, leaving historical rows NULL (not verified)."""
    import sqlite3

    from sqlalchemy import create_engine, inspect, text

    from app.db import database as db_module
    from app.db.orm_models import Base

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT UNIQUE, password_hash TEXT, "
        "role TEXT NOT NULL, created_at TEXT NOT NULL, onboarding_completed_at TEXT, "
        "interests_completed_at TEXT, last_login_at TEXT)")
    conn.execute("INSERT INTO users (id, email, role, created_at) "
                 "VALUES ('usr_old', 'old@example.com', 'user', '2026-01-01')")
    conn.commit()
    conn.close()

    eng = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(bind=eng)
    db_module._apply_migrations(eng)
    on_disk = {c["name"] for c in inspect(eng).get_columns("users")}
    assert {c.name for c in Base.metadata.tables["users"].columns} <= on_disk
    with eng.connect() as c:
        row = c.execute(text(
            "SELECT email_verified_at, email_verified_method FROM users WHERE id='usr_old'")).one()
    assert tuple(row) == (None, None)
    assert "pending_registrations" in inspect(eng).get_table_names()
    eng.dispose()


def test_password_guessing_at_confirmation_is_rate_limited(client):
    _signup(client)
    token = _last_token()
    for _ in range(auth_service.LOGIN_ACCOUNT_LIMIT):
        assert _confirm(client, token, "guess").status_code == 403
    assert _confirm(client, token).status_code == 429


# ── Hosted-mode guards for mail ──────────────────────────────────────────────

from app.core.deploy_mode import UnsafeDeployConfig, validate_deploy_startup_config  # noqa: E402


@pytest.fixture
def hosted(monkeypatch):
    for name in ("MAIL_BACKEND", "APP_PUBLIC_URL", "SMTP_HOST", "MAIL_FROM", "SMTP_STARTTLS",
                 "AUTH_SIGNUP_ALLOWED_EMAILS", "ALLOW_DEV_RESET", "ALLOW_CORPUS_DB_RESET",
                 "ALLOW_INSECURE_AUTH_BYPASS", "CLASSIFICATION_PROVIDER", "RETENTION_CLEANUP_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEPLOY_ENV", "hosted")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("AUTH_SIGNUP_ENABLED", "false")
    monkeypatch.setenv("CSRF_ALLOWED_ORIGINS", "https://signal.example.ts.net")
    return monkeypatch


@pytest.mark.parametrize("backend", ["console", "memory"])
def test_hosted_refuses_dev_mailers(hosted, backend):
    hosted.setenv("MAIL_BACKEND", backend)
    with pytest.raises(UnsafeDeployConfig, match="MAIL_BACKEND"):
        validate_deploy_startup_config()


def test_hosted_refuses_a_plain_http_link_base(hosted):
    hosted.setenv("APP_PUBLIC_URL", "http://signal.example.ts.net")
    with pytest.raises(UnsafeDeployConfig, match="APP_PUBLIC_URL"):
        validate_deploy_startup_config()


def test_hosted_warns_when_signup_can_start_without_mail(hosted):
    hosted.setenv("AUTH_SIGNUP_ALLOWED_EMAILS", "friend@example.com")
    warnings = validate_deploy_startup_config()
    assert any("no mailer" in w for w in warnings)


def test_hosted_with_smtp_configured_starts_clean(hosted):
    hosted.setenv("MAIL_BACKEND", "smtp")
    hosted.setenv("SMTP_HOST", "smtp.example.com")
    hosted.setenv("MAIL_FROM", "Signal Sports <no-reply@example.com>")
    hosted.setenv("APP_PUBLIC_URL", "https://signal.example.ts.net")
    hosted.setenv("AUTH_SIGNUP_ALLOWED_EMAILS", "friend@example.com")
    assert validate_deploy_startup_config() == []


def test_session_bootstrap_reports_invitation_only_signup(client, monkeypatch):
    assert client.get("/api/auth/session").json()["signup_by_invitation"] is False
    monkeypatch.setenv("AUTH_SIGNUP_ENABLED", "false")
    assert client.get("/api/auth/session").json()["signup_by_invitation"] is False
    monkeypatch.setenv("AUTH_SIGNUP_ALLOWED_EMAILS", "friend@example.com")
    body = client.get("/api/auth/session").json()
    assert (body["signup_enabled"], body["signup_by_invitation"]) == (False, True)


# ── Security review follow-ups ───────────────────────────────────────────────

def test_resend_cannot_be_used_to_guess_passwords(client, monkeypatch):
    monkeypatch.setattr(
        auth_service, "_account_login_limiter",
        auth_service.FixedWindowLimiter(2, auth_service.LOGIN_WINDOW_SECONDS))
    _signup(client)
    _age_last_send(61)
    for _ in range(2):
        assert _resend(client, password="guess").status_code == 401
    assert _resend(client).status_code == 429


def test_global_send_limit_refuses_before_storing_anything(client, monkeypatch):
    monkeypatch.setattr(
        email_verification, "_global_send_limiter",
        auth_service.FixedWindowLimiter(1, 600))
    assert _signup(client, "first@example.com").status_code == 202
    assert _signup(client, "second@example.com").status_code == 429
    assert _counts() == (0, 1)


@pytest.mark.parametrize("email", ["a@b.com\r\nBcc: x@evil.com", "a b@example.com", "a@b.com\x00"])
def test_signup_rejects_addresses_with_whitespace_or_control_characters(client, email):
    response = _signup(client, email)
    assert response.status_code == 422
    assert _counts() == (0, 0)
    assert mailer.MEMORY_OUTBOX == []


def test_hosted_refuses_smtp_without_starttls(hosted):
    hosted.setenv("MAIL_BACKEND", "smtp")
    hosted.setenv("SMTP_HOST", "smtp.example.com")
    hosted.setenv("MAIL_FROM", "no-reply@example.com")
    hosted.setenv("SMTP_STARTTLS", "false")
    with pytest.raises(UnsafeDeployConfig, match="SMTP_STARTTLS"):
        validate_deploy_startup_config()


def test_smtp_mailer_honors_starttls_switch(monkeypatch):
    """Locally a plain SMTP sink (Mailpit) needs STARTTLS off; the default is on."""
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context):
            calls.append(("starttls",))

        def send_message(self, msg):
            calls.append(("send", msg["To"]))

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("MAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", "1025")
    monkeypatch.setenv("MAIL_FROM", "dev@localhost")
    message = mailer.OutgoingEmail(to="a@example.com", subject="s", text="t", html="<p>t</p>")

    mailer.get_mailer().send(message)
    assert ("starttls",) in calls
    calls.clear()
    monkeypatch.setenv("SMTP_STARTTLS", "false")
    mailer.get_mailer().send(message)
    assert calls == [("connect", "127.0.0.1", 1025), ("send", "a@example.com")]
