"""DEPLOY_ENV startup checks, dev guards and the signup switch (issue #265).

Local mode (the default) must behave exactly as before; dev and hosted refuse
the combinations listed in app/core/deploy_mode.py. Nothing here touches the
network or a real database: the refusals happen before any engine exists, and
the API tests use the suite's temp DB.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import deploy_mode
from app.core.deploy_mode import (
    UnsafeDeployConfig,
    assert_database_allowed,
    validate_deploy_startup_config,
)

BACKEND = Path(__file__).resolve().parents[1]

_GUARDED_ENV = (
    "DEPLOY_ENV", "ALLOW_DEV_RESET", "ALLOW_CORPUS_DB_RESET", "ALLOW_INSECURE_AUTH_BYPASS",
    "CLASSIFICATION_PROVIDER", "AUTH_COOKIE_SECURE", "AUTH_SIGNUP_ENABLED",
    "CSRF_ALLOWED_ORIGINS", "RETENTION_CLEANUP_ENABLED", "TELEGRAM_NOTIFICATIONS_ENABLED",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SCHEDULER_ENABLED", "SIGNAL_PROD_DATA_DIRS",
)


@pytest.fixture
def env(monkeypatch, tmp_path):
    """A clean slate for every variable the checks read, plus a scratch DB URL."""
    for name in _GUARDED_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'dev.db').as_posix()}")
    return monkeypatch


def _hosted_ok(env):
    env.setenv("DEPLOY_ENV", "hosted")
    env.setenv("AUTH_COOKIE_SECURE", "true")
    env.setenv("AUTH_SIGNUP_ENABLED", "false")
    env.setenv("CSRF_ALLOWED_ORIGINS", "https://signal.example.ts.net")


# ── Mode parsing ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", ["", "local", "LOCAL", " local "])
def test_local_mode_spellings(env, value):
    env.setenv("DEPLOY_ENV", value)
    assert deploy_mode.deploy_env() == "local"


@pytest.mark.parametrize("value", ["prod", "production", "staging", "hosted-ish"])
def test_unknown_mode_refuses_instead_of_falling_back_to_local(env, value):
    env.setenv("DEPLOY_ENV", value)
    with pytest.raises(UnsafeDeployConfig, match="Unknown DEPLOY_ENV"):
        validate_deploy_startup_config()


def test_local_mode_checks_nothing(env):
    # Local mode is today's PC: even the dev escape hatches pass untouched.
    for flag in deploy_mode.HOSTED_FORBIDDEN_FLAGS:
        env.setenv(flag, "true")
    env.setenv("TELEGRAM_NOTIFICATIONS_ENABLED", "true")
    env.setenv("DATABASE_URL", "sqlite:///./data/signal_sports.db")
    assert validate_deploy_startup_config() == []
    assert_database_allowed("sqlite:///./data/signal_sports.db")


# ── Hosted ────────────────────────────────────────────────────────────────────

def test_hosted_clean_config_starts_without_warnings(env):
    _hosted_ok(env)
    assert validate_deploy_startup_config() == []


@pytest.mark.parametrize("flag", deploy_mode.HOSTED_FORBIDDEN_FLAGS)
def test_hosted_refuses_each_dev_flag(env, flag):
    _hosted_ok(env)
    env.setenv(flag, "true")
    with pytest.raises(UnsafeDeployConfig, match=flag):
        validate_deploy_startup_config()


def test_hosted_refuses_fake_classifier(env):
    _hosted_ok(env)
    env.setenv("CLASSIFICATION_PROVIDER", "fake")
    with pytest.raises(UnsafeDeployConfig, match="CLASSIFICATION_PROVIDER=fake"):
        validate_deploy_startup_config()


def test_hosted_reports_every_refusal_at_once(env):
    _hosted_ok(env)
    env.setenv("ALLOW_DEV_RESET", "1")
    env.setenv("ALLOW_INSECURE_AUTH_BYPASS", "yes")
    with pytest.raises(UnsafeDeployConfig) as info:
        validate_deploy_startup_config()
    assert "ALLOW_DEV_RESET" in str(info.value)
    assert "ALLOW_INSECURE_AUTH_BYPASS" in str(info.value)


def test_hosted_warns_on_weak_settings(env):
    env.setenv("DEPLOY_ENV", "hosted")
    env.setenv("RETENTION_CLEANUP_ENABLED", "true")
    warnings = " | ".join(validate_deploy_startup_config())
    assert "AUTH_COOKIE_SECURE" in warnings
    assert "AUTH_SIGNUP_ENABLED" in warnings
    assert "CSRF_ALLOWED_ORIGINS" in warnings
    assert "RETENTION_CLEANUP_ENABLED" in warnings


def test_hosted_allows_the_corpus_path(env):
    # The host's own corpus is the production DB: hosted must be able to open it.
    _hosted_ok(env)
    env.setenv("DATABASE_URL", "sqlite:///./data/signal_sports.db")
    assert validate_deploy_startup_config() == []
    assert_database_allowed("sqlite:////srv/signal/prod/data/signal_sports.db")


# ── Dev ───────────────────────────────────────────────────────────────────────

def test_dev_clean_config_starts(env):
    env.setenv("DEPLOY_ENV", "dev")
    assert validate_deploy_startup_config() == []


def test_dev_refuses_telegram_flag(env):
    env.setenv("DEPLOY_ENV", "dev")
    env.setenv("TELEGRAM_NOTIFICATIONS_ENABLED", "true")
    with pytest.raises(UnsafeDeployConfig, match="TELEGRAM_NOTIFICATIONS_ENABLED"):
        validate_deploy_startup_config()


@pytest.mark.parametrize("secret", ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"])
def test_dev_refuses_telegram_secrets_without_echoing_them(env, secret):
    env.setenv("DEPLOY_ENV", "dev")
    env.setenv(secret, "value-that-must-not-be-logged")
    with pytest.raises(UnsafeDeployConfig) as info:
        validate_deploy_startup_config()
    assert secret in str(info.value)
    assert "value-that-must-not-be-logged" not in str(info.value)


@pytest.mark.parametrize("url", [
    "sqlite:///./data/signal_sports.db",
    f"sqlite:///{(BACKEND / 'data' / 'signal_sports.db').as_posix()}",
])
def test_dev_refuses_the_canonical_corpus(env, monkeypatch, url):
    monkeypatch.chdir(BACKEND)
    env.setenv("DEPLOY_ENV", "dev")
    env.setenv("DATABASE_URL", url)
    with pytest.raises(UnsafeDeployConfig, match="canonical corpus"):
        validate_deploy_startup_config()
    with pytest.raises(UnsafeDeployConfig, match="canonical corpus"):
        assert_database_allowed(url)


def test_dev_refuses_the_production_data_dir(env):
    env.setenv("DEPLOY_ENV", "dev")
    url = "sqlite:////srv/signal/prod/data/signal_sports.db"
    env.setenv("DATABASE_URL", url)
    with pytest.raises(UnsafeDeployConfig, match="production data directory"):
        validate_deploy_startup_config()


def test_dev_refuses_an_extra_configured_prod_dir(env, tmp_path):
    prod = tmp_path / "prod-data"
    env.setenv("DEPLOY_ENV", "dev")
    env.setenv("SIGNAL_PROD_DATA_DIRS", str(prod))
    with pytest.raises(UnsafeDeployConfig, match="production data directory"):
        assert_database_allowed(f"sqlite:///{(prod / 'copy.db').as_posix()}")
    # A sibling directory is not inside it.
    assert_database_allowed(f"sqlite:///{(tmp_path / 'prod-data-snap' / 'x.db').as_posix()}")


def test_dev_allows_a_dev_database(env, tmp_path):
    env.setenv("DEPLOY_ENV", "dev")
    assert_database_allowed(f"sqlite:///{(tmp_path / 'signal_dev.db').as_posix()}")
    assert_database_allowed("sqlite:///:memory:")


def test_dev_warns_about_a_worker(env):
    env.setenv("DEPLOY_ENV", "dev")
    env.setenv("SCHEDULER_ENABLED", "true")
    assert any("SCHEDULER_ENABLED" in w for w in validate_deploy_startup_config())


def test_dev_telegram_sender_is_never_configured(env):
    from app.notifications.telegram import TelegramSender

    env.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    env.setenv("TELEGRAM_CHAT_ID", "42")
    assert TelegramSender().configured() is True  # local mode: unchanged
    env.setenv("DEPLOY_ENV", "dev")
    sender = TelegramSender()
    assert sender.configured() is False
    result = sender.send("hello")  # refused before any request is built
    assert result.error_class == "not_configured"


# ── Engine-level guard, in a fresh interpreter ───────────────────────────────

def _python(code: str, **extra_env: str) -> subprocess.CompletedProcess:
    child_env = {k: v for k, v in os.environ.items() if k not in _GUARDED_ENV}
    child_env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND, env=child_env,
        capture_output=True, text=True, timeout=120,
    )


def test_dev_engine_refuses_corpus_for_any_script():
    # Any tool that imports app.db.database is covered, not just the API.
    proc = _python(
        "import app.db.database",
        DEPLOY_ENV="dev", DATABASE_URL="sqlite:///./data/signal_sports.db",
    )
    assert proc.returncode != 0
    assert "UnsafeDeployConfig" in proc.stderr


def test_dev_cookie_name_defaults_apart_from_production():
    code = "from app.core.config import settings; print(settings.auth_cookie_name)"
    assert _python(code, DEPLOY_ENV="dev").stdout.strip() == "signal_dev_session"
    assert _python(code).stdout.strip() == "signal_session"
    assert _python(code, DEPLOY_ENV="dev", AUTH_COOKIE_NAME="custom").stdout.strip() == "custom"


# ── Process entry points refuse ──────────────────────────────────────────────

def test_api_startup_refuses_in_hosted_with_a_dev_flag(env):
    from app.main import create_app

    _hosted_ok(env)
    env.setenv("ALLOW_DEV_RESET", "true")
    with pytest.raises(UnsafeDeployConfig, match="ALLOW_DEV_RESET"):
        with TestClient(create_app()):
            pass


def test_worker_refuses_in_dev_with_telegram(env):
    from app import worker

    env.setenv("DEPLOY_ENV", "dev")
    env.setenv("TELEGRAM_NOTIFICATIONS_ENABLED", "true")
    env.setenv("SCHEDULER_ENABLED", "true")
    assert worker.main() == 2


# ── Signup switch ─────────────────────────────────────────────────────────────

def _user_count() -> int:
    from app.db.database import SessionLocal
    from app.db.orm_models import ProfileRow, UserRow

    with SessionLocal() as session:
        return session.query(UserRow).count() + session.query(ProfileRow).count()


def test_signup_closed_returns_403_and_creates_nothing(client, monkeypatch):
    monkeypatch.setenv("AUTH_SIGNUP_ENABLED", "false")
    before = _user_count()
    response = client.post(
        "/api/auth/signup",
        json={"email": "closed@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Signup is closed"
    assert "set-cookie" not in response.headers
    assert _user_count() == before


def test_signup_default_is_open(client):
    response = client.post(
        "/api/auth/signup",
        json={"email": "open-265@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 201


def test_session_bootstrap_reports_signup_state(client, monkeypatch):
    assert client.get("/api/auth/session").json()["signup_enabled"] is True
    monkeypatch.setenv("AUTH_SIGNUP_ENABLED", "false")
    assert client.get("/api/auth/session").json()["signup_enabled"] is False


def test_closed_signup_leaves_login_working(admin_client, monkeypatch):
    monkeypatch.setenv("AUTH_SIGNUP_ENABLED", "false")
    assert admin_client.get("/api/auth/session").json()["user"] is not None
