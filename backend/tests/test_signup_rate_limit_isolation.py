"""Signup attempts are limited per client, not by one process-wide bucket.

Same pattern as login (AUDIT_REPORT H1, test_login_rate_limit_isolation.py):
one client probing addresses through signup must not close signup for every
other client. A much higher global ceiling stays as a circuit breaker.
"""
import pytest
from fastapi.testclient import TestClient

from app.services import auth_service, email_verification, mailer


@pytest.fixture(autouse=True)
def _reset():
    auth_service.reset_rate_limiters()
    email_verification.reset_rate_limiters()
    mailer.MEMORY_OUTBOX.clear()
    yield
    auth_service.reset_rate_limiters()
    email_verification.reset_rate_limiters()
    mailer.MEMORY_OUTBOX.clear()


def _client_at(app, ip):
    return TestClient(app, client=(ip, 50000))


def _signup(client, email):
    return client.post("/api/auth/signup",
                       json={"email": email, "password": "correct horse battery"})


def test_one_noisy_client_does_not_close_signup_for_another_client(client, _application, monkeypatch):
    monkeypatch.setattr(email_verification, "_signup_attempt_limiter",
                        auth_service.FixedWindowLimiter(2, 300))
    prober = _client_at(_application, "203.0.113.7")
    assert _signup(prober, "probe1@example.com").status_code == 202
    assert _signup(prober, "probe2@example.com").status_code == 202
    assert _signup(prober, "probe3@example.com").status_code == 429

    other = _client_at(_application, "198.51.100.9")
    assert _signup(other, "newcomer@example.com").status_code == 202


def test_global_ceiling_still_caps_signup_across_clients(client, _application, monkeypatch):
    monkeypatch.setattr(email_verification, "_global_signup_attempt_limiter",
                        auth_service.FixedWindowLimiter(2, 300))
    assert _signup(_client_at(_application, "203.0.113.1"), "a@example.com").status_code == 202
    assert _signup(_client_at(_application, "203.0.113.2"), "b@example.com").status_code == 202
    assert _signup(_client_at(_application, "203.0.113.3"), "c@example.com").status_code == 429


def test_global_signup_ceiling_sits_far_above_one_clients_budget():
    assert (email_verification.SIGNUP_ATTEMPT_GLOBAL_LIMIT
            >= 5 * email_verification.SIGNUP_ATTEMPT_LIMIT)
