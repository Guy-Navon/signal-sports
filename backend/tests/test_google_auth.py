"""Google sign-in (Slice B1): login and registration for Gmail and Workspace.

Two layers:

* **Verification layer** — the REAL ``google.oauth2.id_token`` validation runs
  against tokens signed with a locally generated RSA key and served through a
  fake certificate transport. Nothing about signature, audience, issuer or
  expiry checking is mocked.
* **Route layer** — the real start/callback routes. Only the two network seams
  are replaced: the token-endpoint POST (returns a token signed with the test
  key) and the certificate fetch (serves the test certificate).
"""

import datetime as dt
import json
import threading
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from google.auth import crypt
from google.auth import jwt as google_jwt

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.orm_models import (
    AuthSessionRow,
    OAuthPendingRow,
    PendingRegistrationRow,
    ProfileRow,
    UserIdentityRow,
    UserRow,
)
from app.services import auth_service, google_oauth

CLIENT_ID = "test-client.apps.googleusercontent.com"
CLIENT_SECRET = "test-client-secret-value"
REDIRECT_URI = "http://localhost:5173/api/auth/google/callback"
KID = "test-kid"


# ── Keys, certificates and tokens ─────────────────────────────────────────────

def _rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _pem_private(key):
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )


def _pem_cert(key):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


GOOGLE_KEY = _rsa_key()
FOREIGN_KEY = _rsa_key()
CERTS = {KID: _pem_cert(GOOGLE_KEY)}


class _CertResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self.data = json.dumps(payload).encode()
        self.headers = {}


class FakeCertsTransport:
    """Stands in for google.auth.transport.requests.Request: serves our cert."""

    def __init__(self, certs=CERTS, status=200):
        self.certs = certs
        self.status = status
        self.calls = 0

    def __call__(self, url, method="GET", **kwargs):
        self.calls += 1
        return _CertResponse(self.certs, self.status)


def make_token(nonce="nonce-1", key=GOOGLE_KEY, kid=KID, **overrides):
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "google-sub-1",
        "email": "friend@gmail.com",
        "email_verified": True,
        "name": "Friend",
        "iat": now,
        "exp": now + 600,
        "nonce": nonce,
    }
    claims.update(overrides)
    for k in [k for k, v in claims.items() if v is None]:
        del claims[k]
    signer = crypt.RSASigner.from_string(_pem_private(key), key_id=kid)
    return google_jwt.encode(signer, claims).decode()


CFG = google_oauth.GoogleConfig(CLIENT_ID, CLIENT_SECRET, REDIRECT_URI)
# The real transport factory, captured before the route fixture fakes it.
REAL_CERTS_TRANSPORT = google_oauth.certs_transport


# ── Verification layer: real google-auth validation ─────────────────────────

def _verify(token, nonce="nonce-1"):
    return google_oauth.verify_id_token(token, CFG, nonce=nonce, request=FakeCertsTransport())


def test_a_valid_token_yields_its_claims():
    claims = _verify(make_token())
    assert claims["sub"] == "google-sub-1"
    assert claims["email"] == "friend@gmail.com"


@pytest.mark.parametrize("token, why", [
    (lambda: make_token(key=FOREIGN_KEY), "signed by a key Google never published"),
    (lambda: make_token(aud="someone-else.apps.googleusercontent.com"), "wrong audience"),
    (lambda: make_token(iss="https://evil.example.com"), "wrong issuer"),
    (lambda: make_token(iat=int(time.time()) - 7200, exp=int(time.time()) - 3600), "expired"),
    (lambda: make_token(iat=int(time.time()) + 3600, exp=int(time.time()) + 7200), "issued in the future"),
    (lambda: make_token(sub=None), "no subject"),
    (lambda: make_token(nonce="replayed-nonce"), "nonce mismatch"),
    (lambda: make_token(kid="unknown-kid"), "unknown key id"),
])
def test_invalid_tokens_are_rejected(token, why):
    with pytest.raises(google_oauth.GoogleAuthError) as info:
        _verify(token())
    assert info.value.code == "invalid", why


def test_a_tampered_payload_is_rejected():
    header, payload, signature = make_token().split(".")
    import base64

    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["sub"] = "someone-else"
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    with pytest.raises(google_oauth.GoogleAuthError):
        _verify(".".join([header, forged, signature]))


def test_an_unsigned_token_is_rejected():
    import base64

    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    now = int(time.time())
    unsigned = ".".join([
        b64({"alg": "none", "kid": KID}),
        b64({"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "x",
             "iat": now, "exp": now + 600, "nonce": "nonce-1"}),
        "",
    ])
    with pytest.raises(google_oauth.GoogleAuthError):
        _verify(unsigned)


def test_certificate_fetch_failure_is_unavailable_not_invalid():
    with pytest.raises(google_oauth.GoogleAuthError) as info:
        google_oauth.verify_id_token(
            make_token(), CFG, nonce="nonce-1", request=FakeCertsTransport(status=503))
    assert info.value.code == "unavailable"


# ── Email-authority policy ────────────────────────────────────────────────────

@pytest.mark.parametrize("claims, expected", [
    ({"email": "Friend@Gmail.com", "email_verified": True}, "authoritative"),
    ({"email": "a@team.example", "email_verified": True, "hd": "team.example"}, "authoritative"),
    # hd names a different domain than the address: Google is not vouching for this mailbox.
    ({"email": "a@other.example", "email_verified": True, "hd": "team.example"}, "third_party"),
    ({"email": "a@yahoo.com", "email_verified": True}, "third_party"),
    ({"email": "a@googlemail.com", "email_verified": True}, "third_party"),
    ({"email": "friend@gmail.com", "email_verified": False}, "unverified"),
    ({"email": "friend@gmail.com", "email_verified": "true"}, "unverified"),
    ({"email": "friend@gmail.com"}, "unverified"),
    ({"email_verified": True}, "unverified"),
])
def test_email_authority(claims, expected):
    assert google_oauth.email_authority(claims).kind == expected


# ── Route layer ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _google_env(client, monkeypatch):
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
        session.query(OAuthPendingRow).delete(synchronize_session=False)
        session.query(UserIdentityRow).delete(synchronize_session=False)
        session.query(PendingRegistrationRow).delete(synchronize_session=False)
        session.query(AuthSessionRow).delete(synchronize_session=False)
        session.query(UserRow).filter(UserRow.role != "demo").delete(synchronize_session=False)
        session.query(ProfileRow).filter(
            ~ProfileRow.user_id.in_(["guy", "casual_deni_fan"])
        ).delete(synchronize_session=False)
        session.commit()


class GoogleReturns:
    """Token-endpoint seam: answers the code exchange with a token whose
    nonce is the one the start step stored for this attempt."""

    def __init__(self, monkeypatch, **claims):
        self.claims = claims
        self.calls = []
        monkeypatch.setattr(google_oauth, "exchange_code", self)

    def __call__(self, cfg, code, code_verifier):
        self.calls.append((code, code_verifier))
        return make_token(nonce=_VERIFIER_NONCES[code_verifier], **self.claims)


# code_verifier -> nonce of each started attempt (filled by _start).
_VERIFIER_NONCES = {}


def _start(c):
    response = c.post("/api/auth/google/start")
    assert response.status_code == 200, response.text
    url = response.json()["url"]
    query = parse_qs(urlparse(url).query)
    state = query["state"][0]
    with SessionLocal() as session:
        row = session.get(OAuthPendingRow, auth_service.token_hash(state))
        _VERIFIER_NONCES[row.code_verifier] = row.nonce
    return state, query


def _callback(c, state, **params):
    query = {"code": "auth-code", "state": state, **params}
    return c.get("/api/auth/google/callback", params=query, follow_redirects=False)


def _users(email=None):
    with SessionLocal() as session:
        q = session.query(UserRow).filter(UserRow.role != "demo")
        if email:
            q = q.filter(UserRow.email == email)
        return q.all()


def _fresh_client(client):
    return TestClient(client.app)


def test_google_is_disabled_until_fully_configured(client, monkeypatch):
    assert client.get("/api/auth/session").json()["google_enabled"] is True
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET")
    assert client.get("/api/auth/session").json()["google_enabled"] is False
    assert client.post("/api/auth/google/start").status_code == 404
    assert client.get("/api/auth/google/callback", params={"state": "x", "code": "y"},
                      follow_redirects=False).status_code == 404


def test_start_builds_a_pkce_oidc_request_and_sets_the_state_cookie(client):
    c = _fresh_client(client)
    response = c.post("/api/auth/google/start")
    assert response.status_code == 200
    url = urlparse(response.json()["url"])
    assert (url.scheme, url.netloc, url.path) == ("https", "accounts.google.com", "/o/oauth2/v2/auth")
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert q["client_id"] == CLIENT_ID
    assert q["redirect_uri"] == REDIRECT_URI
    assert q["response_type"] == "code"
    assert set(q["scope"].split()) == {"openid", "email", "profile"}
    assert q["code_challenge_method"] == "S256"
    assert len(q["state"]) >= 40 and len(q["nonce"]) >= 40 and len(q["code_challenge"]) == 43
    assert "client_secret" not in url.query and CLIENT_SECRET not in url.query
    set_cookie = response.headers["set-cookie"].lower()
    assert f"{settings.auth_cookie_name}_oauth=".lower() in set_cookie
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie
    assert "path=/api/auth/google" in set_cookie and "max-age=600" in set_cookie
    with SessionLocal() as session:
        row = session.get(OAuthPendingRow, auth_service.token_hash(q["state"]))
        assert row is not None and row.intent == "login"
        assert q["state"] not in (row.state_hash,)  # only the hash is stored


def test_start_is_csrf_protected(client):
    response = client.post("/api/auth/google/start",
                           headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403


def test_new_gmail_user_is_registered_and_signed_in(client, monkeypatch):
    GoogleReturns(monkeypatch, sub="sub-new", email="New.Friend@gmail.com", name="New Friend")
    c = _fresh_client(client)
    state, _ = _start(c)
    response = _callback(c, state)
    assert response.status_code == 302
    assert response.headers["location"] == "/"
    assert response.cookies.get(settings.auth_cookie_name)
    session_body = c.get("/api/auth/session").json()
    assert session_body["user"]["email"] == "new.friend@gmail.com"
    assert session_body["user"]["has_password"] is False
    assert session_body["onboarding"]["completed"] is False
    with SessionLocal() as session:
        user = session.query(UserRow).filter(UserRow.email == "new.friend@gmail.com").one()
        assert user.password_hash is None
        assert user.email_verified_method == "google_authoritative"
        assert user.email_verified_at is not None
        identity = session.get(UserIdentityRow, ("google", "sub-new"))
        assert identity.user_id == user.id
        assert session.get(ProfileRow, user.id).display_name == "New Friend"
        assert session.query(OAuthPendingRow).count() == 0


def test_the_state_cookie_is_cleared_after_the_callback(client, monkeypatch):
    GoogleReturns(monkeypatch)
    c = _fresh_client(client)
    state, _ = _start(c)
    response = _callback(c, state)
    cleared = [h for h in response.headers.get_list("set-cookie")
               if h.lower().startswith(f"{settings.auth_cookie_name}_oauth=".lower())]
    assert cleared and ("max-age=0" in cleared[0].lower() or "expires=" in cleared[0].lower())


def test_workspace_user_is_registered(client, monkeypatch):
    GoogleReturns(monkeypatch, sub="sub-ws", email="dana@club.example", hd="club.example")
    c = _fresh_client(client)
    state, _ = _start(c)
    assert _callback(c, state).headers["location"] == "/"
    assert len(_users("dana@club.example")) == 1


def test_returning_user_is_found_by_subject_even_after_an_email_change(client, monkeypatch):
    GoogleReturns(monkeypatch, sub="sub-ret", email="first@gmail.com")
    c = _fresh_client(client)
    state, _ = _start(c)
    _callback(c, state)
    [user] = _users("first@gmail.com")

    monkeypatch.setenv("AUTH_SIGNUP_ENABLED", "false")  # closed signup never blocks a returning user
    GoogleReturns(monkeypatch, sub="sub-ret", email="renamed@gmail.com")
    d = _fresh_client(client)
    state, _ = _start(d)
    response = _callback(d, state)
    assert response.headers["location"] == "/"
    assert d.get("/api/auth/session").json()["user"]["id"] == user.id
    assert len(_users()) == 1
    with SessionLocal() as session:
        assert session.get(UserIdentityRow, ("google", "sub-ret")).email == "renamed@gmail.com"


def test_closed_signup_refuses_unknown_google_users(client, monkeypatch):
    monkeypatch.setenv("AUTH_SIGNUP_ENABLED", "false")
    GoogleReturns(monkeypatch, sub="sub-closed", email="stranger@gmail.com")
    c = _fresh_client(client)
    state, _ = _start(c)
    response = _callback(c, state)
    assert response.headers["location"] == "/login?google=signup_closed"
    assert settings.auth_cookie_name not in response.cookies
    assert _users() == []


def test_closed_signup_admits_an_allowlisted_authoritative_address(client, monkeypatch):
    monkeypatch.setenv("AUTH_SIGNUP_ENABLED", "false")
    monkeypatch.setenv("AUTH_SIGNUP_ALLOWED_EMAILS", "invited@gmail.com")
    GoogleReturns(monkeypatch, sub="sub-inv", email="Invited@gmail.com")
    c = _fresh_client(client)
    state, _ = _start(c)
    assert _callback(c, state).headers["location"] == "/"
    assert len(_users("invited@gmail.com")) == 1


def _existing(email, role="user", password="correct horse battery"):
    with SessionLocal() as session:
        user = auth_service.create_user_with_profile(
            session, email=email, password=password, role=role)
        return user.id, user.password_hash


def _identities():
    with SessionLocal() as session:
        return [(i.subject, i.user_id) for i in session.query(UserIdentityRow)]


def test_an_existing_user_account_is_linked_and_signed_in(client, monkeypatch):
    """Guy's 2026-10-21 decision: a Google-authoritative address proves the
    mailbox, so a role=user account holding it is linked automatically."""
    owner_id, owner_hash = _existing("taken@gmail.com")
    GoogleReturns(monkeypatch, sub="sub-link", email="Taken@gmail.com")
    c = _fresh_client(client)
    state, _ = _start(c)
    response = _callback(c, state)
    assert response.headers["location"] == "/"
    assert c.get("/api/auth/session").json()["user"]["id"] == owner_id
    assert _identities() == [("sub-link", owner_id)]
    with SessionLocal() as session:
        owner = session.get(UserRow, owner_id)
        assert owner.password_hash == owner_hash  # the password keeps working
        # The address was never proven before; Google just proved it.
        assert owner.email_verified_method == "google_authoritative"
        assert owner.email_verified_at is not None
    assert len(_users()) == 1
    login = client.post("/api/auth/login",
                        json={"email": "taken@gmail.com", "password": "correct horse battery"})
    assert login.status_code == 200


def test_linking_keeps_an_earlier_verification(client, monkeypatch):
    owner_id, _ = _existing("proven@gmail.com")
    with SessionLocal() as session:
        owner = session.get(UserRow, owner_id)
        owner.email_verified_at, owner.email_verified_method = "2026-10-01T00:00:00+00:00", "link"
        session.commit()
    GoogleReturns(monkeypatch, sub="sub-proven", email="proven@gmail.com")
    c = _fresh_client(client)
    state, _ = _start(c)
    assert _callback(c, state).headers["location"] == "/"
    with SessionLocal() as session:
        owner = session.get(UserRow, owner_id)
        assert (owner.email_verified_at, owner.email_verified_method) == (
            "2026-10-01T00:00:00+00:00", "link")


def test_linking_an_existing_account_ignores_closed_signup(client, monkeypatch):
    owner_id, _ = _existing("member@gmail.com")
    monkeypatch.setenv("AUTH_SIGNUP_ENABLED", "false")
    GoogleReturns(monkeypatch, sub="sub-member", email="member@gmail.com")
    c = _fresh_client(client)
    state, _ = _start(c)
    assert _callback(c, state).headers["location"] == "/"
    assert _identities() == [("sub-member", owner_id)]


def test_an_admin_account_is_linked_automatically(client, monkeypatch):
    """Owner decision (#332): the admin joins automatic linking, like
    role=user. Accepted cost: the Google account becomes a second key to the
    admin console."""
    admin_id, admin_hash = _existing("boss@gmail.com", role="admin")
    GoogleReturns(monkeypatch, sub="sub-boss", email="boss@gmail.com")
    c = _fresh_client(client)
    state, _ = _start(c)
    response = _callback(c, state)
    assert response.headers["location"] == "/"
    session_user = c.get("/api/auth/session").json()["user"]
    assert session_user["id"] == admin_id and session_user["role"] == "admin"
    assert _identities() == [("sub-boss", admin_id)]
    with SessionLocal() as session:
        admin = session.get(UserRow, admin_id)
        assert admin.password_hash == admin_hash  # the password keeps working
        assert admin.email_verified_method == "google_authoritative"


def test_an_admin_linked_to_another_google_account_is_not_relinked(client, monkeypatch):
    admin_id, _ = _existing("boss@gmail.com", role="admin")
    with SessionLocal() as session:
        session.add(UserIdentityRow(provider="google", subject="sub-original", user_id=admin_id,
                                    email="boss@gmail.com", created_at="2026-10-01T00:00:00+00:00"))
        session.commit()
    GoogleReturns(monkeypatch, sub="sub-other", email="boss@gmail.com")
    c = _fresh_client(client)
    state, _ = _start(c)
    assert _callback(c, state).headers["location"] == "/login?google=account_exists"
    assert _identities() == [("sub-original", admin_id)]


def test_a_third_party_address_never_links(client, monkeypatch):
    _existing("someone@yahoo.com")
    GoogleReturns(monkeypatch, sub="sub-yahoo", email="someone@yahoo.com")
    c = _fresh_client(client)
    state, _ = _start(c)
    # Not authoritative, so never linked (#329 registers such addresses only
    # through an emailed link, and never onto an existing account).
    assert _callback(c, state).headers["location"] == "/login?google=account_exists"
    assert _identities() == []


def test_an_account_linked_to_another_google_account_is_not_relinked(client, monkeypatch):
    owner_id, _ = _existing("moved@gmail.com")
    with SessionLocal() as session:
        session.add(UserIdentityRow(provider="google", subject="sub-original", user_id=owner_id,
                                    email="moved@gmail.com", created_at="2026-10-01T00:00:00+00:00"))
        session.commit()
    GoogleReturns(monkeypatch, sub="sub-other", email="moved@gmail.com")
    c = _fresh_client(client)
    state, _ = _start(c)
    assert _callback(c, state).headers["location"] == "/login?google=account_exists"
    assert _identities() == [("sub-original", owner_id)]


def test_losing_a_link_race_signs_into_the_same_account(client, monkeypatch):
    """Deterministic interleaving: a concurrent sign-in links the account
    after this one found it but before this one's insert."""
    owner_id, _ = _existing("racer@gmail.com")
    claims = {"sub": "sub-racer", "email": "racer@gmail.com", "email_verified": True}
    real_lookup = auth_service.get_user_by_email

    def lookup_then_lose(session, email):
        found = real_lookup(session, email)
        monkeypatch.setattr(auth_service, "get_user_by_email", real_lookup)
        with SessionLocal() as other:
            google_oauth.sign_in(other, dict(claims), user_agent=None)
        return found

    monkeypatch.setattr(auth_service, "get_user_by_email", lookup_then_lose)
    with SessionLocal() as session:
        user, token = google_oauth.sign_in(session, dict(claims), user_agent=None)
        assert user.id == owner_id and token
    assert _identities() == [("sub-racer", owner_id)]


def test_pending_password_registrations_for_the_address_are_discarded(client, monkeypatch):
    signup = client.post("/api/auth/signup",
                         json={"email": "squat@gmail.com", "password": "attacker password"})
    assert signup.status_code == 202
    GoogleReturns(monkeypatch, sub="sub-squat", email="squat@gmail.com")
    c = _fresh_client(client)
    state, _ = _start(c)
    assert _callback(c, state).headers["location"] == "/"
    with SessionLocal() as session:
        assert session.query(PendingRegistrationRow).count() == 0
        user = session.query(UserRow).filter(UserRow.email == "squat@gmail.com").one()
        assert user.password_hash is None  # the squatter's password never carries over
    login = client.post("/api/auth/login",
                        json={"email": "squat@gmail.com", "password": "attacker password"})
    assert login.status_code == 401


def test_an_unverified_google_address_cannot_register(client, monkeypatch):
    # Third-party (verified) addresses register through an emailed link:
    # tests/test_google_third_party.py (#329).
    GoogleReturns(monkeypatch, sub="sub-x", email="friend@gmail.com", email_verified=False)
    c = _fresh_client(client)
    state, _ = _start(c)
    response = _callback(c, state)
    assert response.headers["location"] == "/login?google=unverified_email"
    assert _users() == []


def test_a_google_only_account_cannot_password_login(client, monkeypatch):
    GoogleReturns(monkeypatch, sub="sub-nopw", email="nopw@gmail.com")
    c = _fresh_client(client)
    state, _ = _start(c)
    _callback(c, state)
    response = client.post("/api/auth/login", json={"email": "nopw@gmail.com", "password": "anything at all"})
    assert response.status_code == 401


# ── State binding, replay, expiry, cancellation, outages ─────────────────────

def test_callback_without_the_state_cookie_is_refused(client, monkeypatch):
    """Login CSRF: a callback URL from the attacker's own flow, opened in the
    victim's browser, has no matching state cookie."""
    GoogleReturns(monkeypatch)
    attacker = _fresh_client(client)
    state, _ = _start(attacker)
    victim = _fresh_client(client)
    response = _callback(victim, state)
    assert response.headers["location"] == "/login?google=expired"
    assert settings.auth_cookie_name not in response.cookies
    assert _users() == []


def test_a_mismatched_state_cookie_is_refused(client, monkeypatch):
    GoogleReturns(monkeypatch)
    c = _fresh_client(client)
    first, _ = _start(c)
    _start(c)  # the cookie now holds the second attempt's state
    assert _callback(c, first).headers["location"] == "/login?google=expired"


def test_a_callback_is_single_use(client, monkeypatch):
    GoogleReturns(monkeypatch)
    c = _fresh_client(client)
    state, _ = _start(c)
    assert _callback(c, state).headers["location"] == "/"
    c.cookies.set(f"{settings.auth_cookie_name}_oauth", state, path="/api/auth/google")
    assert _callback(c, state).headers["location"] == "/login?google=expired"


def test_an_expired_attempt_is_refused(client, monkeypatch):
    GoogleReturns(monkeypatch)
    c = _fresh_client(client)
    state, _ = _start(c)
    with SessionLocal() as session:
        row = session.get(OAuthPendingRow, auth_service.token_hash(state))
        row.expires_at = auth_service.iso(auth_service.utc_now() - dt.timedelta(seconds=1))
        session.commit()
    assert _callback(c, state).headers["location"] == "/login?google=expired"
    assert _users() == []


def test_cancelling_on_google_consumes_the_attempt(client, monkeypatch):
    exchange = GoogleReturns(monkeypatch)
    c = _fresh_client(client)
    state, _ = _start(c)
    response = c.get("/api/auth/google/callback", params={"state": state, "error": "access_denied"},
                     follow_redirects=False)
    assert response.headers["location"] == "/login?google=cancelled"
    assert exchange.calls == []
    with SessionLocal() as session:
        assert session.query(OAuthPendingRow).count() == 0


@pytest.mark.parametrize("failure", [
    httpx.TimeoutException("timed out"),
    httpx.ConnectError("no route"),
])
def test_token_endpoint_outage_is_reported_as_unavailable(client, monkeypatch, failure):
    def boom(*a, **k):
        raise failure

    monkeypatch.setattr(google_oauth.httpx, "post", boom)
    c = _fresh_client(client)
    state, _ = _start(c)
    assert _callback(c, state).headers["location"] == "/login?google=unavailable"


@pytest.mark.parametrize("status, code", [(500, "unavailable"), (400, "failed")])
def test_token_endpoint_errors_map_to_fixed_notices(client, monkeypatch, status, code):
    monkeypatch.setattr(google_oauth.httpx, "post",
                        lambda *a, **k: httpx.Response(status, json={"error": "x"}))
    c = _fresh_client(client)
    state, _ = _start(c)
    assert _callback(c, state).headers["location"] == f"/login?google={code}"


def test_the_code_exchange_sends_the_verifier_and_secret_to_googles_token_endpoint(monkeypatch):
    sent = {}

    def fake_post(url, data, timeout):
        sent.update(url=url, data=data, timeout=timeout)
        return httpx.Response(200, json={"id_token": "tok"})

    monkeypatch.setattr(google_oauth.httpx, "post", fake_post)
    assert google_oauth.exchange_code(CFG, "the-code", "the-verifier") == "tok"
    assert sent["url"] == "https://oauth2.googleapis.com/token"
    assert sent["data"] == {
        "code": "the-code", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code",
        "code_verifier": "the-verifier",
    }
    assert sent["timeout"] == google_oauth.TOKEN_TIMEOUT_SECONDS


def test_secrets_and_tokens_never_reach_the_log(client, monkeypatch, caplog):
    caplog.set_level("DEBUG")
    monkeypatch.setattr(google_oauth.httpx, "post",
                        lambda *a, **k: httpx.Response(500, json={"error": "x"}))
    c = _fresh_client(client)
    state, _ = _start(c)
    _callback(c, state)
    GoogleReturns(monkeypatch)
    state2, _ = _start(c)
    _callback(c, state2)
    # The TestClient's own httpx client logs the URLs it requests; that is the
    # test harness, not the server, so its records are excluded.
    server_logs = " | ".join(
        r.getMessage() for r in caplog.records if not r.name.startswith("httpx"))
    for secret in (CLIENT_SECRET, state, state2):
        assert secret not in server_logs


def test_the_access_log_redacts_the_callbacks_code_and_state():
    import logging

    from app.core.log_redaction import SecretRedactingFilter

    line = '127.0.0.1:5 - "GET /api/auth/google/callback?code=4/0AbCdEf&state=S3cr3tState HTTP/1.1" 302'
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, "%s", (line,), None)
    SecretRedactingFilter().filter(record)
    rendered = record.getMessage()
    assert "4/0AbCdEf" not in rendered and "S3cr3tState" not in rendered
    assert "/api/auth/google/callback?code=[redacted]&state=[redacted]" in rendered


# ── Concurrency ──────────────────────────────────────────────────────────────

def test_concurrent_callbacks_with_one_state_create_one_session(client, monkeypatch):
    GoogleReturns(monkeypatch, sub="sub-race", email="race@gmail.com")
    c = _fresh_client(client)
    state, _ = _start(c)
    barrier = threading.Barrier(2)
    outcomes = []

    def attempt():
        with SessionLocal() as session:
            barrier.wait()
            try:
                google_oauth.consume_pending(session, state)
                outcomes.append("consumed")
            except google_oauth.GoogleAuthError as exc:
                outcomes.append(exc.code)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["consumed", "expired"]


def test_concurrent_first_logins_with_one_subject_create_one_account(client, monkeypatch):
    claims = {"sub": "sub-twice", "email": "twice@gmail.com", "email_verified": True, "name": "T"}
    barrier = threading.Barrier(2)
    results = []

    def attempt():
        with SessionLocal() as session:
            barrier.wait()
            user, _token = google_oauth.sign_in(session, claims, user_agent=None)
            results.append(user.id)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 2 and results[0] == results[1]
    with SessionLocal() as session:
        assert session.query(UserRow).filter(UserRow.email == "twice@gmail.com").count() == 1
        assert session.query(UserIdentityRow).count() == 1


def test_start_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(google_oauth, "_start_limiter", auth_service.FixedWindowLimiter(2, 60))
    c = _fresh_client(client)
    assert c.post("/api/auth/google/start").status_code == 200
    assert c.post("/api/auth/google/start").status_code == 200
    assert c.post("/api/auth/google/start").status_code == 429


def test_expired_attempts_are_pruned_on_start(client):
    c = _fresh_client(client)
    state, _ = _start(c)
    with SessionLocal() as session:
        row = session.get(OAuthPendingRow, auth_service.token_hash(state))
        row.expires_at = auth_service.iso(auth_service.utc_now() - dt.timedelta(seconds=1))
        session.commit()
    _start(c)
    with SessionLocal() as session:
        assert session.get(OAuthPendingRow, auth_service.token_hash(state)) is None
        assert session.query(OAuthPendingRow).count() == 1


# ── Hosted-mode guards ───────────────────────────────────────────────────────

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
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://signal.example.ts.net/api/auth/google/callback")
    return monkeypatch


def test_hosted_with_a_clean_google_config_starts(hosted):
    assert validate_deploy_startup_config() == []


def test_hosted_refuses_a_plain_http_redirect_uri(hosted):
    hosted.setenv("GOOGLE_OAUTH_REDIRECT_URI", "http://signal.example.ts.net/api/auth/google/callback")
    with pytest.raises(UnsafeDeployConfig, match="GOOGLE_OAUTH_REDIRECT_URI"):
        validate_deploy_startup_config()


def test_hosted_warns_on_a_partial_google_config(hosted):
    hosted.delenv("GOOGLE_OAUTH_CLIENT_SECRET")
    assert any("Google sign-in is partially configured" in w for w in validate_deploy_startup_config())


def test_hosted_warns_when_the_redirect_origin_is_not_a_csrf_origin(hosted):
    hosted.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://other.example.ts.net/api/auth/google/callback")
    assert any("not in CSRF_ALLOWED_ORIGINS" in w for w in validate_deploy_startup_config())


def test_a_state_consumed_between_read_and_delete_is_refused(client):
    """Deterministic interleaving for the race above: another request consumes
    the row after this one has read it but before its delete. Only the
    rowcount-checked delete can notice; the earlier read already succeeded."""
    c = _fresh_client(client)
    state, _ = _start(c)
    with SessionLocal() as session:
        real_expunge = session.expunge

        def expunge_then_lose_the_race(obj):
            real_expunge(obj)
            with SessionLocal() as other:
                other.query(OAuthPendingRow).filter(
                    OAuthPendingRow.state_hash == auth_service.token_hash(state)).delete()
                other.commit()

        session.expunge = expunge_then_lose_the_race
        with pytest.raises(google_oauth.GoogleAuthError) as info:
            google_oauth.consume_pending(session, state)
    assert info.value.code == "expired"


def test_losing_a_first_sign_in_race_signs_into_the_winners_account(client, monkeypatch):
    """Deterministic interleaving: a competing first sign-in for the same
    subject commits after this one checked "no identity, no account" but
    before its insert. The insert must fail on the unique constraints and the
    request must sign into the winner's account, never create a second."""
    claims = {"sub": "sub-late", "email": "late@gmail.com", "email_verified": True}
    winner = {}
    real_new_user_rows = auth_service.new_user_rows

    def rows_after_the_competitor_commits(**kwargs):
        monkeypatch.setattr(auth_service, "new_user_rows", real_new_user_rows)
        with SessionLocal() as other:
            user, _token = google_oauth.sign_in(other, dict(claims), user_agent=None)
            winner["id"] = user.id
        return real_new_user_rows(**kwargs)

    monkeypatch.setattr(auth_service, "new_user_rows", rows_after_the_competitor_commits)
    with SessionLocal() as session:
        user, token = google_oauth.sign_in(session, dict(claims), user_agent=None)
        assert user.id == winner["id"] and token
    with SessionLocal() as session:
        assert session.query(UserRow).filter(UserRow.email == "late@gmail.com").count() == 1
        assert session.query(UserIdentityRow).filter(UserIdentityRow.subject == "sub-late").count() == 1


def test_the_certificate_fetch_has_a_bounded_timeout(monkeypatch):
    """google-auth's requests transport waits up to 120 s by default; a hung
    certificate fetch must not hold a request thread that long."""
    import google.auth.transport.requests as google_requests

    seen = {}

    def fake_call(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        seen["timeout"] = timeout
        return _CertResponse(CERTS)

    monkeypatch.setattr(google_requests.Request, "__call__", fake_call)
    transport = REAL_CERTS_TRANSPORT()
    google_oauth.verify_id_token(make_token(), CFG, nonce="nonce-1", request=transport)
    assert seen["timeout"] == google_oauth.TOKEN_TIMEOUT_SECONDS
