"""Login rate limiting is per client, not one process-wide bucket (AUDIT_REPORT H1).

One client posting bad logins must not lock every other client out of password
login. The per-account limiter and a much higher global circuit breaker stay.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.orm_models import ProfileRow, UserRow
from app.services import auth_service, email_verification
from tests.conftest import signup_and_verify

PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    auth_service.reset_rate_limiters()
    email_verification.reset_rate_limiters()
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    _cleanup()
    yield
    auth_service.reset_rate_limiters()
    email_verification.reset_rate_limiters()
    _cleanup()


def _cleanup():
    with SessionLocal() as session:
        session.query(UserRow).filter(UserRow.role != "demo").delete(synchronize_session=False)
        session.query(ProfileRow).filter(
            ~ProfileRow.user_id.in_(["guy", "casual_deni_fan"])
        ).delete(synchronize_session=False)
        session.commit()


def _client_at(app, ip):
    return TestClient(app, client=(ip, 50000))


def _tight_client_limiter(monkeypatch, limit):
    monkeypatch.setattr(
        auth_service, "_client_login_limiter",
        auth_service.FixedWindowLimiter(limit, auth_service.LOGIN_WINDOW_SECONDS),
    )


def test_one_noisy_client_does_not_block_another_clients_valid_login(
        client, _application, monkeypatch):
    assert signup_and_verify(client, "victim@example.com", PASSWORD,
                             display_name="Victim").status_code == 200
    _tight_client_limiter(monkeypatch, 3)

    attacker = _client_at(_application, "203.0.113.7")
    for n in range(3):
        r = attacker.post("/api/auth/login",
                          json={"email": f"random{n}@example.com", "password": "wrong"})
        assert r.status_code == 401
    r = attacker.post("/api/auth/login",
                      json={"email": "random9@example.com", "password": "wrong"})
    assert r.status_code == 429  # the noisy client is throttled ...

    victim = _client_at(_application, "198.51.100.20")
    r = victim.post("/api/auth/login",
                    json={"email": "victim@example.com", "password": PASSWORD})
    assert r.status_code == 200  # ... but nobody else is
    assert r.json()["user"]["email"] == "victim@example.com"


def test_client_bucket_is_keyed_by_ip_at_the_service_layer(monkeypatch):
    _tight_client_limiter(monkeypatch, 1)
    with SessionLocal() as session:
        with pytest.raises(auth_service.InvalidCredentialsError):
            auth_service.login(session, email="a@example.com", password="x",
                               client_ip="10.0.0.1")
        with pytest.raises(auth_service.RateLimitExceeded):
            auth_service.login(session, email="b@example.com", password="x",
                               client_ip="10.0.0.1")
        with pytest.raises(auth_service.InvalidCredentialsError):
            auth_service.login(session, email="c@example.com", password="x",
                               client_ip="10.0.0.2")


def test_global_ceiling_is_a_circuit_breaker_well_above_the_per_client_limit():
    assert auth_service.LOGIN_GLOBAL_LIMIT >= 5 * auth_service.LOGIN_CLIENT_LIMIT
    assert auth_service.LOGIN_CLIENT_LIMIT > auth_service.LOGIN_ACCOUNT_LIMIT


def test_resend_shares_the_per_client_budget(_application, monkeypatch):
    """Resend verifies a password, so it spends the same per-client budget."""
    _tight_client_limiter(monkeypatch, 1)
    noisy = _client_at(_application, "203.0.113.8")
    r = noisy.post("/api/auth/login", json={"email": "x@example.com", "password": "wrong"})
    assert r.status_code == 401
    r = noisy.post("/api/auth/verification/resend",
                   json={"email": "y@example.com", "password": "wrong password"})
    assert r.status_code == 429
