"""Google accounts with third-party addresses register through an emailed link (#329).

Google is authoritative only for @gmail.com and Workspace (hd) addresses; for
a Google account on e.g. @yahoo.com, ``email_verified`` is not current proof
of the mailbox. Such a sign-up creates a pending Google registration bound to
the Google subject and the exact address, and emails a single-use link.
Activation needs BOTH proofs: the link (mailbox) and a new Google sign-in as
the same subject with the same address (Google account), consumed atomically;
the session is created only in the browser that completes it.

ID tokens go through google-auth's real validation (local key + fake cert
transport); only the token-endpoint POST is replaced. Mail uses the suite's
in-memory outbox.
"""

import datetime as dt
import re
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.orm_models import (
    AuthSessionRow,
    OAuthPendingRow,
    PendingGoogleRegistrationRow,
    PendingRegistrationRow,
    ProfileRow,
    ReauthGrantRow,
    UserIdentityRow,
    UserRow,
)
from app.services import auth_service, email_verification, google_oauth, mailer
from tests.test_google_auth import (
    CLIENT_ID,
    CLIENT_SECRET,
    REDIRECT_URI,
    FakeCertsTransport,
    make_token,
)

YAHOO = "someone@yahoo.com"


@pytest.fixture(autouse=True)
def _env(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", REDIRECT_URI)
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    monkeypatch.setattr(google_oauth, "certs_transport", lambda: FakeCertsTransport())
    auth_service.reset_rate_limiters()
    google_oauth.reset_rate_limiters()
    email_verification.reset_rate_limiters()
    mailer.MEMORY_OUTBOX.clear()
    _cleanup()
    yield
    _cleanup()
    mailer.MEMORY_OUTBOX.clear()


def _cleanup():
    with SessionLocal() as session:
        for model in (ReauthGrantRow, OAuthPendingRow, UserIdentityRow, PendingRegistrationRow,
                      PendingGoogleRegistrationRow, AuthSessionRow):
            session.query(model).delete(synchronize_session=False)
        session.query(UserRow).filter(UserRow.role != "demo").delete(synchronize_session=False)
        session.query(ProfileRow).filter(
            ~ProfileRow.user_id.in_(["guy", "casual_deni_fan"])
        ).delete(synchronize_session=False)
        session.commit()


NONCES = {}


class Google:
    def __init__(self, monkeypatch, sub, email, **claims):
        self.sub, self.email, self.claims = sub, email, claims
        monkeypatch.setattr(google_oauth, "exchange_code", self)

    def __call__(self, cfg, code, code_verifier):
        return make_token(nonce=NONCES[code_verifier], sub=self.sub, email=self.email, **self.claims)


def _remember(state):
    with SessionLocal() as session:
        row = session.get(OAuthPendingRow, auth_service.token_hash(state))
        NONCES[row.code_verifier] = row.nonce
        return row


def _state(response):
    return parse_qs(urlparse(response.json()["url"]).query)["state"][0]


def _callback(c, state, **params):
    return c.get("/api/auth/google/callback", params={"code": "c", "state": state, **params},
                 follow_redirects=False)


def _google_login(c, monkeypatch, sub="sub-y", email=YAHOO):
    """The ordinary 'Continue with Google' trip, as a browser would do it."""
    state = _state(c.post("/api/auth/google/start"))
    _remember(state)
    Google(monkeypatch, sub, email)
    return _callback(c, state)


def _last_link_token(to=YAHOO):
    sent = [m for m in mailer.MEMORY_OUTBOX if m.to == to]
    assert sent, "no verification email was sent"
    match = re.search(r"/verify-email#g=([A-Za-z0-9_\-]+)", sent[-1].text)
    assert match, sent[-1].text
    return match.group(1)


def _activate(c, monkeypatch, token, sub="sub-y", email=YAHOO):
    """Open the link in browser ``c``: start the Google step, finish it."""
    start = c.post("/api/auth/verification/google/start", json={"token": token})
    assert start.status_code == 200, start.text
    state = _state(start)
    _remember(state)
    Google(monkeypatch, sub, email)
    return _callback(c, state)


def _pending():
    with SessionLocal() as session:
        return [(r.subject, r.email) for r in session.query(PendingGoogleRegistrationRow)]


def _users(email=YAHOO):
    with SessionLocal() as session:
        return session.query(UserRow).filter(UserRow.email == email).all()


def _age_last_send(seconds):
    with SessionLocal() as session:
        for row in session.query(PendingGoogleRegistrationRow):
            row.last_sent_at = auth_service.iso(auth_service.utc_now() - dt.timedelta(seconds=seconds))
        session.commit()


# ── Sign-up step: a pending registration and an email, nothing else ──────────

def test_a_third_party_sign_up_creates_only_a_pending_registration_and_an_email(client, monkeypatch):
    c = TestClient(client.app)
    response = _google_login(c, monkeypatch)
    assert response.headers["location"] == "/login?google=check_email"
    assert settings.auth_cookie_name not in response.cookies
    assert _pending() == [("sub-y", YAHOO)]
    assert _users() == []
    token = _last_link_token()
    with SessionLocal() as session:
        row = session.query(PendingGoogleRegistrationRow).one()
        assert row.token_hash == auth_service.token_hash(token)
    message = [m for m in mailer.MEMORY_OUTBOX if m.to == YAHOO][-1]
    assert 'dir="rtl"' in message.html and "Google" in message.text


def test_an_address_held_by_an_account_is_never_linked_or_pended(client, monkeypatch):
    with SessionLocal() as session:
        auth_service.create_user_with_profile(session, email=YAHOO, password="correct horse battery")
    response = _google_login(TestClient(client.app), monkeypatch)
    assert response.headers["location"] == "/login?google=account_exists"
    assert _pending() == [] and mailer.MEMORY_OUTBOX == []
    with SessionLocal() as session:
        assert session.query(UserIdentityRow).count() == 0


def test_closed_signup_refuses_unless_the_address_is_invited(client, monkeypatch):
    monkeypatch.setenv("AUTH_SIGNUP_ENABLED", "false")
    assert _google_login(TestClient(client.app), monkeypatch).headers["location"] == \
        "/login?google=signup_closed"
    assert _pending() == []
    monkeypatch.setenv("AUTH_SIGNUP_ALLOWED_EMAILS", YAHOO)
    assert _google_login(TestClient(client.app), monkeypatch).headers["location"] == \
        "/login?google=check_email"


def test_an_unverified_google_address_is_still_refused(client, monkeypatch):
    c = TestClient(client.app)
    state = _state(c.post("/api/auth/google/start"))
    _remember(state)
    Google(monkeypatch, "sub-u", YAHOO, email_verified=False)
    assert _callback(c, state).headers["location"] == "/login?google=unverified_email"
    assert _pending() == []


def test_without_a_mailer_nothing_is_stored(client, monkeypatch):
    monkeypatch.setenv("MAIL_BACKEND", "")
    response = _google_login(TestClient(client.app), monkeypatch)
    assert response.headers["location"] == "/login?google=mail_unavailable"
    assert _pending() == []


# ── Resend is another Google sign-in ─────────────────────────────────────────

def test_signing_in_again_soon_does_not_send_another_email(client, monkeypatch):
    _google_login(TestClient(client.app), monkeypatch)
    response = _google_login(TestClient(client.app), monkeypatch)
    assert response.headers["location"] == "/login?google=check_email_recent"
    assert len([m for m in mailer.MEMORY_OUTBOX if m.to == YAHOO]) == 1


def test_signing_in_again_later_rotates_the_link(client, monkeypatch):
    _google_login(TestClient(client.app), monkeypatch)
    old = _last_link_token()
    _age_last_send(61)
    assert _google_login(TestClient(client.app), monkeypatch).headers["location"] == \
        "/login?google=check_email"
    new = _last_link_token()
    assert new != old
    assert TestClient(client.app).post(
        "/api/auth/verification/google/peek", json={"token": old}).status_code == 404
    assert _pending() == [("sub-y", YAHOO)]


def test_resends_are_capped(client, monkeypatch):
    _google_login(TestClient(client.app), monkeypatch)
    for _ in range(email_verification.MAX_SENDS - 1):
        _age_last_send(61)
        _google_login(TestClient(client.app), monkeypatch)
    _age_last_send(61)
    assert _google_login(TestClient(client.app), monkeypatch).headers["location"] == \
        "/login?google=too_many"


def test_a_changed_google_address_replaces_the_pending_one(client, monkeypatch):
    _google_login(TestClient(client.app), monkeypatch)
    _google_login(TestClient(client.app), monkeypatch, email="moved@outlook.com")
    assert _pending() == [("sub-y", "moved@outlook.com")]


# ── The link: peek, start, activate ──────────────────────────────────────────

def test_peek_shows_the_masked_address_and_changes_nothing(client, monkeypatch):
    _google_login(TestClient(client.app), monkeypatch)
    token = _last_link_token()
    response = client.post("/api/auth/verification/google/peek", json={"token": token})
    assert response.json() == {"email": "s**@yahoo.com"}
    assert client.post("/api/auth/verification/google/peek",
                       json={"token": "nope"}).status_code == 404
    assert _pending() == [("sub-y", YAHOO)] and _users() == []


def test_activation_needs_the_link_and_the_same_google_account(client, monkeypatch):
    registering = TestClient(client.app)
    _google_login(registering, monkeypatch)
    token = _last_link_token()
    other_browser = TestClient(client.app)
    response = _activate(other_browser, monkeypatch, token)
    assert response.headers["location"] == "/"
    assert response.cookies.get(settings.auth_cookie_name)
    [user] = _users()
    assert user.password_hash is None and user.email_verified_method == "link"
    with SessionLocal() as session:
        assert session.get(UserIdentityRow, ("google", "sub-y")).user_id == user.id
        assert session.get(ProfileRow, user.id) is not None
    assert _pending() == []
    # The session exists only in the browser that completed the flow.
    assert other_browser.get("/api/auth/session").json()["user"]["id"] == user.id
    assert registering.get("/api/auth/session").json()["user"] is None


def test_the_link_alone_activates_nothing(client, monkeypatch):
    _google_login(TestClient(client.app), monkeypatch)
    token = _last_link_token()
    c = TestClient(client.app)
    c.post("/api/auth/verification/google/peek", json={"token": token})
    start = c.post("/api/auth/verification/google/start", json={"token": token})
    assert start.status_code == 200
    assert _users() == [] and _pending() == [("sub-y", YAHOO)]


def test_a_different_google_account_cannot_activate(client, monkeypatch):
    _google_login(TestClient(client.app), monkeypatch)
    token = _last_link_token()
    response = _activate(TestClient(client.app), monkeypatch, token, sub="sub-intruder")
    assert response.headers["location"] == "/login?google=verify_wrong_account"
    assert _users() == []
    assert _pending() == [("sub-y", YAHOO)]  # the rightful owner can still finish


def test_the_same_google_account_with_a_changed_address_cannot_activate(client, monkeypatch):
    _google_login(TestClient(client.app), monkeypatch)
    token = _last_link_token()
    response = _activate(TestClient(client.app), monkeypatch, token, email="moved@outlook.com")
    assert response.headers["location"] == "/login?google=verify_email_changed"
    assert _users() == [] and _users("moved@outlook.com") == []


def test_a_link_rotated_after_the_start_cannot_finish(client, monkeypatch):
    _google_login(TestClient(client.app), monkeypatch)
    token = _last_link_token()
    c = TestClient(client.app)
    state = _state(c.post("/api/auth/verification/google/start", json={"token": token}))
    _remember(state)
    _age_last_send(61)
    _google_login(TestClient(client.app), monkeypatch)  # resend: the old link dies
    Google(monkeypatch, "sub-y", YAHOO)
    assert _callback(c, state).headers["location"] == "/login?google=verify_expired"
    assert _users() == []


def test_an_expired_link_cannot_start(client, monkeypatch):
    _google_login(TestClient(client.app), monkeypatch)
    token = _last_link_token()
    with SessionLocal() as session:
        row = session.query(PendingGoogleRegistrationRow).one()
        row.token_expires_at = auth_service.iso(auth_service.utc_now() - dt.timedelta(seconds=1))
        session.commit()
    assert client.post("/api/auth/verification/google/start", json={"token": token}).status_code == 404


def test_signup_closed_before_activation_refuses(client, monkeypatch):
    _google_login(TestClient(client.app), monkeypatch)
    token = _last_link_token()
    monkeypatch.setenv("AUTH_SIGNUP_ENABLED", "false")
    assert _activate(TestClient(client.app), monkeypatch, token).headers["location"] == \
        "/login?google=signup_closed"
    assert _users() == []


def test_an_account_created_meanwhile_is_not_linked(client, monkeypatch):
    _google_login(TestClient(client.app), monkeypatch)
    token = _last_link_token()
    with SessionLocal() as session:
        auth_service.create_user_with_profile(session, email=YAHOO, password="correct horse battery")
    assert _activate(TestClient(client.app), monkeypatch, token).headers["location"] == \
        "/login?google=account_exists"
    with SessionLocal() as session:
        assert session.query(UserIdentityRow).count() == 0


def test_activation_discards_password_signups_for_the_address(client, monkeypatch):
    assert client.post("/api/auth/signup", json={"email": YAHOO, "password": "squatter pass"}
                       ).status_code == 202
    _google_login(TestClient(client.app), monkeypatch)
    token = _last_link_token()
    assert _activate(TestClient(client.app), monkeypatch, token).headers["location"] == "/"
    with SessionLocal() as session:
        assert session.query(PendingRegistrationRow).count() == 0


def test_a_registration_consumed_between_read_and_delete_is_refused(client, monkeypatch):
    """Deterministic interleaving: a concurrent activation deletes the pending
    row after this one read it; only the rowcount-checked delete notices."""
    _google_login(TestClient(client.app), monkeypatch)
    token = _last_link_token()
    claims = {"sub": "sub-y", "email": YAHOO, "email_verified": True}
    with SessionLocal() as session:
        real_expunge = session.expunge

        def expunge_then_lose(obj):
            real_expunge(obj)
            with SessionLocal() as other:
                other.query(PendingGoogleRegistrationRow).delete()
                other.commit()

        session.expunge = expunge_then_lose
        with pytest.raises(google_oauth.GoogleAuthError) as info:
            google_oauth.activate_google_registration(
                session, claims, registration_token_hash=auth_service.token_hash(token),
                user_agent=None)
    assert info.value.code == "verify_expired"
    assert _users() == []


def test_tokens_never_reach_the_server_log(client, monkeypatch, caplog):
    caplog.set_level("DEBUG")
    _google_login(TestClient(client.app), monkeypatch)
    token = _last_link_token()
    _activate(TestClient(client.app), monkeypatch, token)
    server_logs = " | ".join(r.getMessage() for r in caplog.records if not r.name.startswith("httpx"))
    assert token not in server_logs


# ── Schema ───────────────────────────────────────────────────────────────────

def test_the_new_column_and_table_reach_a_legacy_database(tmp_path):
    import sqlite3

    from sqlalchemy import create_engine, inspect

    from app.db import database as db_module
    from app.db.orm_models import Base

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE oauth_pending (state_hash TEXT PRIMARY KEY, intent TEXT NOT NULL, "
                 "nonce TEXT NOT NULL, code_verifier TEXT NOT NULL, created_at TEXT NOT NULL, "
                 "expires_at TEXT NOT NULL, user_id TEXT, session_hash TEXT)")
    conn.commit()
    conn.close()
    eng = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(bind=eng)
    db_module._apply_migrations(eng)
    on_disk = {c["name"] for c in inspect(eng).get_columns("oauth_pending")}
    assert {c.name for c in Base.metadata.tables["oauth_pending"].columns} <= on_disk
    assert "pending_google_registrations" in inspect(eng).get_table_names()
    eng.dispose()
