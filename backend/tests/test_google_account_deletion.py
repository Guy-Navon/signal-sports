"""Self-deletion for Google-only accounts (#331).

Owner-decided policy: a newly initiated, explicit Google round trip for the
SAME linked subject; the callback only records a short-lived, single-use,
session-bound deletion grant; deletion happens through a separate
CSRF-protected DELETE that consumes the grant. This is NOT guaranteed fresh
re-authentication (Google offers none): a live Google session in the same
browser satisfies the round trip — the documented unattended-device limit.

ID tokens go through google-auth's real validation (local key + fake cert
transport from test_google_auth); only the token-endpoint POST is replaced.
"""

import datetime as dt
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.orm_models import (
    AuthSessionRow,
    OAuthPendingRow,
    PendingRegistrationRow,
    ProfileRow,
    ReauthGrantRow,
    UserIdentityRow,
    UserRow,
)
from app.services import auth_service, google_oauth
from tests.test_google_auth import (
    CLIENT_ID,
    CLIENT_SECRET,
    REDIRECT_URI,
    FakeCertsTransport,
    make_token,
)

PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def _env(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", REDIRECT_URI)
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    monkeypatch.setattr(google_oauth, "certs_transport", lambda: FakeCertsTransport())
    auth_service.reset_rate_limiters()
    google_oauth.reset_rate_limiters()
    _cleanup()
    yield
    _cleanup()


def _cleanup():
    with SessionLocal() as session:
        for model in (ReauthGrantRow, OAuthPendingRow, UserIdentityRow, PendingRegistrationRow,
                      AuthSessionRow):
            session.query(model).delete(synchronize_session=False)
        session.query(UserRow).filter(UserRow.role != "demo").delete(synchronize_session=False)
        session.query(ProfileRow).filter(
            ~ProfileRow.user_id.in_(["guy", "casual_deni_fan"])
        ).delete(synchronize_session=False)
        session.commit()


class Google:
    """Token-endpoint seam: returns a token for ``sub`` carrying the nonce the
    start step stored for this attempt."""

    nonces = {}

    def __init__(self, monkeypatch, sub, email):
        self.sub, self.email = sub, email
        monkeypatch.setattr(google_oauth, "exchange_code", self)

    def __call__(self, cfg, code, code_verifier):
        return make_token(nonce=Google.nonces[code_verifier], sub=self.sub, email=self.email)


def _remember_nonce(state):
    with SessionLocal() as session:
        row = session.get(OAuthPendingRow, auth_service.token_hash(state))
        Google.nonces[row.code_verifier] = row.nonce
        return row


def _google_user(client, monkeypatch, sub="sub-del", email="leaver@gmail.com"):
    """A Google-only account signed in through the real start/callback."""
    Google(monkeypatch, sub, email)
    c = TestClient(client.app)
    start = c.post("/api/auth/google/start")
    state = parse_qs(urlparse(start.json()["url"]).query)["state"][0]
    _remember_nonce(state)
    landed = c.get("/api/auth/google/callback", params={"code": "c", "state": state},
                   follow_redirects=False)
    assert landed.headers["location"] == "/"
    return c


def _start_delete(c, confirm_email="leaver@gmail.com"):
    return c.post("/api/me/account/delete/google/start", json={"confirm_email": confirm_email})


def _callback(c, state, **params):
    return c.get("/api/auth/google/callback", params={"code": "c", "state": state, **params},
                 follow_redirects=False)


def _confirmed(c, monkeypatch, sub="sub-del", email="leaver@gmail.com"):
    """Run start + Google + callback for deletion; return the callback response.
    ``sub``/``email`` are what Google returns; the account's own address is
    always the one typed to confirm."""
    response = _start_delete(c, "leaver@gmail.com")
    assert response.status_code == 200, response.text
    state = parse_qs(urlparse(response.json()["url"]).query)["state"][0]
    _remember_nonce(state)
    Google(monkeypatch, sub, email)
    return _callback(c, state)


def _delete(c):
    return c.request("DELETE", "/api/me/account", json={"method": "reauth_grant"})


def _user_count(email="leaver@gmail.com"):
    with SessionLocal() as session:
        return session.query(UserRow).filter(UserRow.email == email).count()


def _grants():
    with SessionLocal() as session:
        return session.query(ReauthGrantRow).count()


# ── Start ─────────────────────────────────────────────────────────────────────

def test_start_needs_a_session(client):
    response = client.post("/api/me/account/delete/google/start",
                           json={"confirm_email": "x@gmail.com"})
    assert response.status_code == 401


def test_start_needs_the_accounts_own_email_typed(client, monkeypatch):
    c = _google_user(client, monkeypatch)
    assert _start_delete(c, "someone-else@gmail.com").status_code == 400
    assert _start_delete(c, "  Leaver@Gmail.com ").status_code == 200


def test_start_is_only_for_accounts_without_a_password(client, monkeypatch):
    with SessionLocal() as session:
        auth_service.create_user_with_profile(session, email="pw@gmail.com", password=PASSWORD)
    c = TestClient(client.app)
    c.post("/api/auth/login", json={"email": "pw@gmail.com", "password": PASSWORD})
    response = _start_delete(c, "pw@gmail.com")
    assert response.status_code == 409


def test_start_binds_the_attempt_to_the_user_and_this_session(client, monkeypatch):
    c = _google_user(client, monkeypatch)
    response = _start_delete(c)
    query = parse_qs(urlparse(response.json()["url"]).query)
    assert query["login_hint"] == ["leaver@gmail.com"]
    assert query["prompt"] == ["select_account"]
    row = _remember_nonce(query["state"][0])
    raw_session = c.cookies.get(settings.auth_cookie_name)
    with SessionLocal() as session:
        user = session.query(UserRow).filter(UserRow.email == "leaver@gmail.com").one()
    assert row.intent == "delete"
    assert row.user_id == user.id
    assert row.session_hash == auth_service.token_hash(raw_session)


# ── Callback: a grant, never a deletion ───────────────────────────────────────

def test_the_callback_only_records_a_grant(client, monkeypatch):
    c = _google_user(client, monkeypatch)
    before = c.cookies.get(settings.auth_cookie_name)
    response = _confirmed(c, monkeypatch)
    assert response.headers["location"] == "/account?delete=confirm"
    assert settings.auth_cookie_name not in response.cookies  # no new session
    assert c.cookies.get(settings.auth_cookie_name) == before
    assert _user_count() == 1
    assert _grants() == 1


def test_a_different_google_account_gets_no_grant(client, monkeypatch):
    c = _google_user(client, monkeypatch)
    response = _confirmed(c, monkeypatch, sub="sub-someone-else", email="leaver@gmail.com")
    assert response.headers["location"] == "/account?google=delete_wrong_account"
    assert _grants() == 0
    assert _user_count() == 1


def test_the_callback_in_another_session_gets_no_grant(client, monkeypatch):
    """The grant is bound to the session that started the deletion: the same
    user signed in elsewhere cannot complete it."""
    c = _google_user(client, monkeypatch)
    response = _start_delete(c)
    state = parse_qs(urlparse(response.json()["url"]).query)["state"][0]
    _remember_nonce(state)
    other = _google_user(client, monkeypatch)  # same account, another session
    other.cookies.set(f"{settings.auth_cookie_name}_oauth", state, path="/api/auth/google")
    Google(monkeypatch, "sub-del", "leaver@gmail.com")
    result = _callback(other, state)
    assert result.headers["location"] == "/account?google=delete_failed"
    assert _grants() == 0


def test_a_signed_out_callback_gets_no_grant(client, monkeypatch):
    c = _google_user(client, monkeypatch)
    response = _start_delete(c)
    state = parse_qs(urlparse(response.json()["url"]).query)["state"][0]
    _remember_nonce(state)
    c.post("/api/auth/logout")
    Google(monkeypatch, "sub-del", "leaver@gmail.com")
    assert _callback(c, state).headers["location"] == "/account?google=delete_failed"
    assert _grants() == 0


def test_cancelling_the_deletion_returns_to_the_account_page(client, monkeypatch):
    c = _google_user(client, monkeypatch)
    response = _start_delete(c)
    state = parse_qs(urlparse(response.json()["url"]).query)["state"][0]
    result = c.get("/api/auth/google/callback", params={"state": state, "error": "access_denied"},
                   follow_redirects=False)
    assert result.headers["location"] == "/account?google=cancelled"
    assert _grants() == 0 and _user_count() == 1


def test_a_deletion_callback_never_signs_in_or_registers(client, monkeypatch):
    """Even a valid token for an unknown subject, arriving on a deletion
    attempt, must not create an account or a session."""
    c = _google_user(client, monkeypatch)
    response = _confirmed(c, monkeypatch, sub="sub-brand-new", email="brand-new@gmail.com")
    assert response.headers["location"] == "/account?google=delete_wrong_account"
    assert _user_count("brand-new@gmail.com") == 0


# ── DELETE with the grant ─────────────────────────────────────────────────────

def test_confirming_deletes_the_account_and_everything_it_owns(client, monkeypatch):
    c = _google_user(client, monkeypatch)
    _confirmed(c, monkeypatch)
    with SessionLocal() as session:
        uid = session.query(UserRow).filter(UserRow.email == "leaver@gmail.com").one().id
    response = _delete(c)
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "deleted": True}
    with SessionLocal() as session:
        assert session.get(UserRow, uid) is None
        assert session.get(ProfileRow, uid) is None
        assert session.query(UserIdentityRow).filter(UserIdentityRow.user_id == uid).count() == 0
        assert session.query(AuthSessionRow).filter(AuthSessionRow.user_id == uid).count() == 0
        assert session.query(ReauthGrantRow).filter(ReauthGrantRow.user_id == uid).count() == 0
    assert c.get("/api/auth/session").json()["user"] is None


def test_without_a_grant_nothing_is_deleted(client, monkeypatch):
    c = _google_user(client, monkeypatch)
    response = _delete(c)
    assert response.status_code == 403
    assert _user_count() == 1


def test_an_expired_grant_is_refused(client, monkeypatch):
    c = _google_user(client, monkeypatch)
    _confirmed(c, monkeypatch)
    with SessionLocal() as session:
        grant = session.query(ReauthGrantRow).one()
        grant.expires_at = auth_service.iso(auth_service.utc_now() - dt.timedelta(seconds=1))
        session.commit()
    assert _delete(c).status_code == 403
    assert _user_count() == 1


def test_a_grant_works_only_in_the_session_that_earned_it(client, monkeypatch):
    c = _google_user(client, monkeypatch)
    _confirmed(c, monkeypatch)
    other = _google_user(client, monkeypatch)  # same account, another session
    assert _delete(other).status_code == 403
    assert _user_count() == 1
    assert _delete(c).status_code == 200


def test_a_grant_is_single_use(client, monkeypatch):
    c = _google_user(client, monkeypatch)
    _confirmed(c, monkeypatch)
    with SessionLocal() as session:
        grant = session.query(ReauthGrantRow).one()
        user = session.get(UserRow, grant.user_id)
        session_hash = grant.session_hash
        assert auth_service.consume_reauth_grant(session, user, session_hash=session_hash) is True
        assert auth_service.consume_reauth_grant(session, user, session_hash=session_hash) is False


def test_a_grant_consumed_between_read_and_update_is_refused(client, monkeypatch):
    """Deterministic interleaving: a concurrent DELETE consumes the grant after
    this one found it but before its update; only the rowcount-checked
    update can notice."""
    c = _google_user(client, monkeypatch)
    _confirmed(c, monkeypatch)
    with SessionLocal() as session:
        grant = session.query(ReauthGrantRow).one()
        user = session.get(UserRow, grant.user_id)
        session_hash, grant_id = grant.session_hash, grant.id
        real_expunge = session.expunge

        def expunge_then_lose(obj):
            real_expunge(obj)
            with SessionLocal() as other:
                row = other.get(ReauthGrantRow, grant_id)
                row.consumed_at = auth_service.iso(auth_service.utc_now())
                other.commit()

        session.expunge = expunge_then_lose
        assert auth_service.consume_reauth_grant(session, user, session_hash=session_hash) is False


def test_password_accounts_keep_the_password_path(client, monkeypatch):
    with SessionLocal() as session:
        auth_service.create_user_with_profile(session, email="pw@gmail.com", password=PASSWORD)
    c = TestClient(client.app)
    c.post("/api/auth/login", json={"email": "pw@gmail.com", "password": PASSWORD})
    assert _delete(c).status_code == 400  # the grant method is for password-less accounts
    ok = c.request("DELETE", "/api/me/account", json={"current_password": PASSWORD})
    assert ok.status_code == 200


def test_a_body_with_neither_method_is_rejected(client, monkeypatch):
    c = _google_user(client, monkeypatch)
    assert c.request("DELETE", "/api/me/account", json={}).status_code == 422


def test_the_last_admin_guard_still_applies(client, monkeypatch):
    c = _google_user(client, monkeypatch)
    with SessionLocal() as session:
        session.query(UserRow).filter(UserRow.role == "admin").delete(synchronize_session=False)
        user = session.query(UserRow).filter(UserRow.email == "leaver@gmail.com").one()
        user.role = "admin"
        session.commit()
    _confirmed(c, monkeypatch)
    assert _delete(c).status_code == 409
    assert _user_count() == 1


# ── Schema: the new columns reach a legacy oauth_pending table ───────────────

def test_binding_columns_reach_a_legacy_oauth_pending_table(tmp_path):
    import sqlite3

    from sqlalchemy import create_engine, inspect

    from app.db import database as db_module
    from app.db.orm_models import Base

    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE oauth_pending (state_hash TEXT PRIMARY KEY, intent TEXT NOT NULL, "
                 "nonce TEXT NOT NULL, code_verifier TEXT NOT NULL, created_at TEXT NOT NULL, "
                 "expires_at TEXT NOT NULL)")
    conn.commit()
    conn.close()
    eng = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(bind=eng)
    db_module._apply_migrations(eng)
    on_disk = {c["name"] for c in inspect(eng).get_columns("oauth_pending")}
    assert {c.name for c in Base.metadata.tables["oauth_pending"].columns} <= on_disk
    assert "reauth_grants" in inspect(eng).get_table_names()
    eng.dispose()
