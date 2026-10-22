"""Password reset by email (#200: "Password reset ... journeys exist with tests").

``POST /api/auth/password/forgot`` answers the same way whether or not an
account exists and whether or not it was throttled (no enumeration, no
throttle leak); the email goes out after the response. The emailed link is a
single-use, one-hour token stored only as a hash. Setting the new password
revokes every session; the person then signs in normally.
"""

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.orm_models import AuthSessionRow, PasswordResetTokenRow, ProfileRow, UserIdentityRow, UserRow
from app.services import auth_service, email_verification, mailer, password_reset

OLD = "correct horse battery"
NEW = "a brand new passphrase"


@pytest.fixture(autouse=True)
def _clean(client):
    auth_service.reset_rate_limiters()
    email_verification.reset_rate_limiters()
    password_reset.reset_rate_limiters()
    mailer.MEMORY_OUTBOX.clear()
    _cleanup()
    yield
    _cleanup()
    mailer.MEMORY_OUTBOX.clear()


def _cleanup():
    with SessionLocal() as session:
        for model in (PasswordResetTokenRow, UserIdentityRow, AuthSessionRow):
            session.query(model).delete(synchronize_session=False)
        session.query(UserRow).filter(UserRow.role != "demo").delete(synchronize_session=False)
        session.query(ProfileRow).filter(
            ~ProfileRow.user_id.in_(["guy", "casual_deni_fan"])
        ).delete(synchronize_session=False)
        session.commit()


def _account(email="owner@example.com", password=OLD):
    with SessionLocal() as session:
        return auth_service.create_user_with_profile(session, email=email, password=password).id


def _forgot(client, email="owner@example.com"):
    return client.post("/api/auth/password/forgot", json={"email": email})


def _token(to="owner@example.com"):
    sent = [m for m in mailer.MEMORY_OUTBOX if m.to == to]
    assert sent, "no reset email was sent"
    match = re.search(r"/reset-password#t=([A-Za-z0-9_\-]+)", sent[-1].text)
    assert match, sent[-1].text
    return match.group(1)


def _reset(client, token, password=NEW):
    return client.post("/api/auth/password/reset", json={"token": token, "new_password": password})


def _login(client, password, email="owner@example.com"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ── Asking for a reset ───────────────────────────────────────────────────────

def test_a_reset_link_is_emailed_and_only_its_hash_is_stored(client):
    uid = _account()
    response = _forgot(client, "Owner@Example.com")
    assert response.status_code == 202
    token = _token()
    message = [m for m in mailer.MEMORY_OUTBOX if m.to == "owner@example.com"][-1]
    assert 'dir="rtl"' in message.html and "http://localhost:5173/reset-password#t=" in message.text
    with SessionLocal() as session:
        row = session.query(PasswordResetTokenRow).one()
        assert row.user_id == uid and row.token_hash == auth_service.token_hash(token)


def test_the_answer_is_identical_for_unknown_addresses_and_google_only_accounts(client):
    _account()
    with SessionLocal() as session:
        user, profile = auth_service.new_user_rows(
            email="google-only@gmail.com", password_hash=None, email_verified_method="google_authoritative")
        session.add(user)
        session.add(profile)
        session.commit()
    known = _forgot(client)
    unknown = _forgot(client, "nobody@example.com")
    google_only = _forgot(client, "google-only@gmail.com")
    assert known.status_code == unknown.status_code == google_only.status_code == 202
    assert known.json() == unknown.json() == google_only.json()
    assert [m.to for m in mailer.MEMORY_OUTBOX] == ["owner@example.com"]


def test_throttling_is_silent(client, monkeypatch):
    """Throttled requests answer exactly like accepted ones; they just send nothing."""
    _account()
    monkeypatch.setattr(password_reset, "_reset_email_limiter", auth_service.FixedWindowLimiter(1, 3600))
    first = _forgot(client)
    with SessionLocal() as session:  # past the per-account cooldown: only the limiter can stop it
        for row in session.query(PasswordResetTokenRow):
            row.created_at = auth_service.iso(auth_service.utc_now() - dt.timedelta(minutes=2))
        session.commit()
    second = _forgot(client)
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert len(mailer.MEMORY_OUTBOX) == 1


def test_a_second_request_within_a_minute_sends_nothing(client):
    _account()
    _forgot(client)
    _forgot(client)
    assert len(mailer.MEMORY_OUTBOX) == 1


def test_without_a_mailer_the_request_is_refused_for_everyone(client, monkeypatch):
    _account()
    monkeypatch.setenv("MAIL_BACKEND", "")
    assert _forgot(client).status_code == 503
    assert _forgot(client, "nobody@example.com").status_code == 503


# ── Using the link ───────────────────────────────────────────────────────────

def test_peek_shows_the_masked_address(client):
    _account()
    _forgot(client)
    assert client.post("/api/auth/password/reset/peek", json={"token": _token()}).json() == \
        {"email": "o**@example.com"}
    assert client.post("/api/auth/password/reset/peek", json={"token": "nope"}).status_code == 404


def test_reset_sets_the_password_and_signs_out_everywhere(client):
    uid = _account()
    signed_in = TestClient(client.app)
    assert _login(signed_in, OLD).status_code == 200
    _forgot(client)
    response = _reset(client, _token())
    assert response.status_code == 200
    assert "set-cookie" not in response.headers  # no automatic sign-in
    with SessionLocal() as session:
        assert session.query(AuthSessionRow).filter(AuthSessionRow.user_id == uid).count() == 0
    assert signed_in.get("/api/auth/session").json()["user"] is None
    assert _login(TestClient(client.app), OLD).status_code == 401
    assert _login(TestClient(client.app), NEW).status_code == 200


def test_a_link_is_single_use_and_older_links_die(client, monkeypatch):
    _account()
    _forgot(client)
    first = _token()
    with SessionLocal() as session:  # let a second request through the cooldown
        for row in session.query(PasswordResetTokenRow):
            row.created_at = auth_service.iso(auth_service.utc_now() - dt.timedelta(minutes=2))
        session.commit()
    _forgot(client)
    second = _token()
    assert second != first
    assert _reset(client, second).status_code == 200
    assert _reset(client, second, "yet another passphrase").status_code == 400
    assert _reset(client, first, "yet another passphrase").status_code == 400


def test_an_expired_link_is_refused(client):
    _account()
    _forgot(client)
    token = _token()
    with SessionLocal() as session:
        row = session.query(PasswordResetTokenRow).one()
        row.expires_at = auth_service.iso(auth_service.utc_now() - dt.timedelta(seconds=1))
        session.commit()
    assert _reset(client, token).status_code == 400
    assert _login(TestClient(client.app), OLD).status_code == 200


def test_the_new_password_must_be_long_enough(client):
    _account()
    _forgot(client)
    assert _reset(client, _token(), "short").status_code == 422


def test_a_reset_proves_the_address(client):
    uid = _account()
    _forgot(client)
    _reset(client, _token())
    with SessionLocal() as session:
        user = session.get(UserRow, uid)
        assert user.email_verified_at is not None and user.email_verified_method == "link"


def test_an_earlier_verification_is_kept(client):
    uid = _account()
    with SessionLocal() as session:
        user = session.get(UserRow, uid)
        user.email_verified_at, user.email_verified_method = "2026-10-01T00:00:00+00:00", "google_authoritative"
        session.commit()
    _forgot(client)
    _reset(client, _token())
    with SessionLocal() as session:
        user = session.get(UserRow, uid)
        assert (user.email_verified_at, user.email_verified_method) == (
            "2026-10-01T00:00:00+00:00", "google_authoritative")


def test_a_token_consumed_between_read_and_update_is_refused(client):
    """Deterministic interleaving: a concurrent reset consumes the token after
    this one read it; only the rowcount-checked update notices."""
    _account()
    _forgot(client)
    token = _token()
    with SessionLocal() as session:
        real_expunge = session.expunge

        def expunge_then_lose(obj):
            real_expunge(obj)
            with SessionLocal() as other:
                row = other.query(PasswordResetTokenRow).one()
                row.consumed_at = auth_service.iso(auth_service.utc_now())
                other.commit()

        session.expunge = expunge_then_lose
        with pytest.raises(password_reset.InvalidResetToken):
            password_reset.complete_reset(session, raw_token=token, new_password=NEW)
    assert _login(TestClient(client.app), OLD).status_code == 200


def test_tokens_never_reach_the_log(client, caplog):
    caplog.set_level("DEBUG")
    _account()
    _forgot(client)
    token = _token()
    _reset(client, token)
    server_logs = " | ".join(r.getMessage() for r in caplog.records if not r.name.startswith("httpx"))
    assert token not in server_logs
