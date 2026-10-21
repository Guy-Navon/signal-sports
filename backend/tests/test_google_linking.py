"""Connect and disconnect Google from the Account page (#330).

The explicit path — the only one for admin accounts (automatic linking is for
role=user only). Connecting needs the current password and binds the Google
attempt to this user AND this session; the callback links and never signs in
or registers. Disconnecting needs the password and is refused for accounts
without one, so no account is left without a way to sign in.

ID tokens go through google-auth's real validation (local key + fake cert
transport from test_google_auth); only the token-endpoint POST is replaced.
"""

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


def _password_user(client, email="owner@example.com", role="user"):
    with SessionLocal() as session:
        user = auth_service.create_user_with_profile(session, email=email, password=PASSWORD, role=role)
        uid = user.id
    c = TestClient(client.app)
    assert c.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    return c, uid


def _start_link(c, password=PASSWORD):
    return c.post("/api/me/google/link", json={"current_password": password})


def _state_of(response):
    return parse_qs(urlparse(response.json()["url"]).query)["state"][0]


def _callback(c, state, **params):
    return c.get("/api/auth/google/callback", params={"code": "c", "state": state, **params},
                 follow_redirects=False)


def _link(c, monkeypatch, sub="sub-link", email="owner.google@gmail.com", **claims):
    response = _start_link(c)
    assert response.status_code == 200, response.text
    state = _state_of(response)
    _remember(state)
    Google(monkeypatch, sub, email, **claims)
    return _callback(c, state)


def _identities():
    with SessionLocal() as session:
        return sorted((i.subject, i.user_id, i.email) for i in session.query(UserIdentityRow))


# ── Connect ───────────────────────────────────────────────────────────────────

def test_connect_needs_a_session(client):
    assert client.post("/api/me/google/link", json={"current_password": PASSWORD}).status_code == 401


def test_connect_needs_the_current_password(client):
    c, _ = _password_user(client)
    assert _start_link(c, "wrong password").status_code == 403
    with SessionLocal() as session:
        assert session.query(OAuthPendingRow).count() == 0


def test_connect_is_404_when_google_is_off(client, monkeypatch):
    c, _ = _password_user(client)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET")
    assert _start_link(c).status_code == 404


def test_connect_binds_the_attempt_to_the_user_and_this_session(client):
    c, uid = _password_user(client)
    row = _remember(_state_of(_start_link(c)))
    assert row.intent == "link"
    assert row.user_id == uid
    assert row.session_hash == auth_service.token_hash(c.cookies.get(settings.auth_cookie_name))


def test_connecting_links_and_reports_back_without_a_new_session(client, monkeypatch):
    c, uid = _password_user(client)
    before = c.cookies.get(settings.auth_cookie_name)
    response = _link(c, monkeypatch)
    assert response.headers["location"] == "/account?google=linked"
    assert settings.auth_cookie_name not in response.cookies
    assert c.cookies.get(settings.auth_cookie_name) == before
    assert _identities() == [("sub-link", uid, "owner.google@gmail.com")]
    assert c.get("/api/auth/session").json()["user"]["google_email"] == "owner.google@gmail.com"


def test_the_admin_can_connect_explicitly(client, monkeypatch):
    c, uid = _password_user(client, email="boss@example.com", role="admin")
    assert _link(c, monkeypatch, sub="sub-boss").headers["location"] == "/account?google=linked"
    assert _identities() == [("sub-boss", uid, "owner.google@gmail.com")]
    # …and then signs in with Google.
    d = TestClient(client.app)
    state = _state_of(d.post("/api/auth/google/start"))
    _remember(state)
    Google(monkeypatch, "sub-boss", "owner.google@gmail.com")
    assert _callback(d, state).headers["location"] == "/"
    assert d.get("/api/auth/session").json()["user"]["role"] == "admin"


def test_any_google_address_can_be_connected_explicitly(client, monkeypatch):
    """The password proves the account; Google proves the Google account. The
    email-authority rule governs registration and automatic linking only."""
    c, uid = _password_user(client)
    response = _link(c, monkeypatch, sub="sub-yahoo", email="someone@yahoo.com")
    assert response.headers["location"] == "/account?google=linked"
    assert _identities() == [("sub-yahoo", uid, "someone@yahoo.com")]


def test_a_google_account_linked_elsewhere_is_refused(client, monkeypatch):
    a, a_id = _password_user(client, email="a@example.com")
    _link(a, monkeypatch, sub="sub-shared")
    b, _ = _password_user(client, email="b@example.com")
    response = _link(b, monkeypatch, sub="sub-shared")
    assert response.headers["location"] == "/account?google=link_taken"
    assert _identities() == [("sub-shared", a_id, "owner.google@gmail.com")]


def test_an_account_already_connected_cannot_start_another(client, monkeypatch):
    c, _ = _password_user(client)
    _link(c, monkeypatch)
    assert _start_link(c).status_code == 409


def test_a_connect_finished_in_another_session_is_refused(client, monkeypatch):
    c, _ = _password_user(client)
    state = _state_of(_start_link(c))
    _remember(state)
    other = TestClient(client.app)
    other.post("/api/auth/login", json={"email": "owner@example.com", "password": PASSWORD})
    other.cookies.set(f"{settings.auth_cookie_name}_oauth", state, path="/api/auth/google")
    Google(monkeypatch, "sub-link", "owner.google@gmail.com")
    assert _callback(other, state).headers["location"] == "/account?google=link_failed"
    assert _identities() == []


def test_a_signed_out_callback_links_nothing(client, monkeypatch):
    c, _ = _password_user(client)
    state = _state_of(_start_link(c))
    _remember(state)
    c.post("/api/auth/logout")
    Google(monkeypatch, "sub-link", "owner.google@gmail.com")
    assert _callback(c, state).headers["location"] == "/account?google=link_failed"
    assert _identities() == []


def test_cancelling_the_connect_reports_back_to_the_account_page(client):
    c, _ = _password_user(client)
    state = _state_of(_start_link(c))
    response = c.get("/api/auth/google/callback", params={"state": state, "error": "access_denied"},
                     follow_redirects=False)
    assert response.headers["location"] == "/account?google=link_cancelled"
    assert _identities() == []


def test_losing_a_connect_race_does_not_create_a_second_identity(client, monkeypatch):
    """Deterministic interleaving: another session of the same user links a
    different Google account after this callback's checks but before its
    insert. The (user, provider) constraint must refuse the second one."""
    c, uid = _password_user(client)
    state = _state_of(_start_link(c))
    pending = _remember(state)
    Google(monkeypatch, "sub-late", "late@gmail.com")
    real_exchange = google_oauth.exchange_code

    def exchange_after_a_competitor_links(cfg, code, verifier):
        with SessionLocal() as other:
            other.add(UserIdentityRow(provider="google", subject="sub-first", user_id=uid,
                                      email="first@gmail.com", created_at="2026-10-21T00:00:00+00:00"))
            other.commit()
        return real_exchange(cfg, code, verifier)

    monkeypatch.setattr(google_oauth, "exchange_code", exchange_after_a_competitor_links)
    assert pending.intent == "link"
    assert _callback(c, state).headers["location"] == "/account?google=link_already"
    assert _identities() == [("sub-first", uid, "first@gmail.com")]


# ── Disconnect ────────────────────────────────────────────────────────────────

def _unlink(c, password=PASSWORD):
    return c.request("DELETE", "/api/me/google", json={"current_password": password})


def test_disconnect_needs_the_password(client, monkeypatch):
    c, _ = _password_user(client)
    _link(c, monkeypatch)
    assert _unlink(c, "wrong password").status_code == 403
    assert len(_identities()) == 1
    assert _unlink(c).status_code == 200
    assert _identities() == []
    assert c.get("/api/auth/session").json()["user"]["google_email"] is None


def test_disconnect_without_a_link_is_404(client):
    c, _ = _password_user(client)
    assert _unlink(c).status_code == 404


def test_an_account_without_a_password_cannot_disconnect(client, monkeypatch):
    """It would be left with no way to sign in."""
    d = TestClient(client.app)
    state = _state_of(d.post("/api/auth/google/start"))
    _remember(state)
    Google(monkeypatch, "sub-only", "only@gmail.com")
    assert _callback(d, state).headers["location"] == "/"
    response = d.request("DELETE", "/api/me/google", json={"current_password": "anything"})
    assert response.status_code == 409
    assert len(_identities()) == 1


def test_password_guessing_through_link_and_unlink_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(auth_service, "_account_login_limiter",
                        auth_service.FixedWindowLimiter(2, auth_service.LOGIN_WINDOW_SECONDS))
    c, _ = _password_user(client)  # the login itself spends one attempt
    assert _start_link(c, "guess").status_code == 403
    assert _start_link(c, "guess").status_code == 429
    assert _unlink(c, "guess").status_code == 429


# ── Schema ───────────────────────────────────────────────────────────────────

def test_google_email_is_null_for_unlinked_accounts(client):
    c, _ = _password_user(client)
    assert c.get("/api/auth/session").json()["user"]["google_email"] is None
