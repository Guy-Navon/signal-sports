"""
Deployment mode and the startup checks it turns on (issue #265).

``DEPLOY_ENV`` says where this process runs, and therefore which mistakes must
be impossible there:

  unset, "" or "local"
      The owner's PC and the test suite. **No new checks**: behaviour is
      exactly what it was before #265, so nothing about the running local
      installation changes.
  "dev"
      A remote development environment (a codespace, or the ``dev`` user on a
      shared host). It must never open the production corpus and never deliver
      a real notification.
  "hosted"
      The production host. Development escape hatches refuse startup.

Any other value refuses startup: a typo such as ``DEPLOY_ENV=prod`` must not
silently fall back to the unguarded local mode.

The checks read ``os.environ`` at call time (not at import), so tests can
monkeypatch them and a process that loads ``backend/.env`` late still sees it.
``validate_deploy_startup_config()`` raises on a refusal and returns the
warnings it logged; the API lifespan and the worker call it before touching
the database. ``assert_database_allowed()`` also runs when the engine is
created, so every script that opens the DB through ``app.db.database`` is
covered in dev mode, not only the API and the worker.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

LOCAL = "local"
DEV = "dev"
HOSTED = "hosted"
_MODES = (LOCAL, DEV, HOSTED)

# The production data directory on a host (docs/DEPLOYMENT.md). Extra paths can
# be added with SIGNAL_PROD_DATA_DIRS (comma-separated), e.g. on a shared host
# whose layout differs.
DEFAULT_PROD_DATA_DIRS = ("/srv/signal/prod",)

# Flags that exist only for local development. Each one is refused on a host.
HOSTED_FORBIDDEN_FLAGS = (
    "ALLOW_DEV_RESET",
    "ALLOW_CORPUS_DB_RESET",
    "ALLOW_INSECURE_AUTH_BYPASS",
)


class UnsafeDeployConfig(RuntimeError):
    """Startup refused: the configuration is unsafe for this DEPLOY_ENV."""


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def deploy_env() -> str:
    """The validated deployment mode. Raises on an unknown value."""
    raw = os.environ.get("DEPLOY_ENV", "").strip().lower()
    if raw in ("", LOCAL):
        return LOCAL
    if raw in _MODES:
        return raw
    raise UnsafeDeployConfig(
        f"Unknown DEPLOY_ENV={raw!r}. Use one of: local (or unset), dev, hosted."
    )


def is_dev() -> bool:
    return deploy_env() == DEV


def prod_data_dirs() -> tuple[Path, ...]:
    extra = tuple(
        p.strip() for p in os.environ.get("SIGNAL_PROD_DATA_DIRS", "").split(",") if p.strip()
    )
    return tuple(Path(p) for p in DEFAULT_PROD_DATA_DIRS + extra)


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        pass
    # Compare resolved forms too, so a symlinked data dir cannot slip past.
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def production_database_reason(url: str) -> Optional[str]:
    """Why ``url`` counts as a production database in dev mode, or None.

    Two rules: the canonical corpus filename (``backend/data/signal_sports.db``,
    the live corpus on the PC until the cutover) and anything under a
    production data directory. Dev uses its own file, e.g.
    ``sqlite:///./data/dev/signal_dev.db``.
    """
    from app.db.corpus_protection import _sqlite_path_from_url, is_protected_corpus_db

    if is_protected_corpus_db(url):
        return "it is the canonical corpus file backend/data/signal_sports.db"
    path = _sqlite_path_from_url(url)
    if path is None:
        return None
    for parent in prod_data_dirs():
        if _is_under(path, parent):
            return f"it is under the production data directory {parent}"
    return None


def assert_database_allowed(url: str) -> None:
    """Refuse a production database in dev mode. No-op in every other mode."""
    if deploy_env() != DEV:
        return
    reason = production_database_reason(url)
    if reason:
        raise UnsafeDeployConfig(
            f"DEPLOY_ENV=dev refuses DATABASE_URL={url!r}: {reason}. "
            "Point DATABASE_URL at a dev database, e.g. "
            "sqlite:///./data/dev/signal_dev.db."
        )


def telegram_delivery_forbidden() -> bool:
    """True when no code path may deliver a real Telegram message (dev mode)."""
    return deploy_env() == DEV


def _hosted_checks() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for flag in HOSTED_FORBIDDEN_FLAGS:
        if _truthy(flag):
            errors.append(f"{flag}=true is a local-development flag")
    if os.environ.get("CLASSIFICATION_PROVIDER", "").strip().lower() == "fake":
        errors.append("CLASSIFICATION_PROVIDER=fake writes canned classifications into the corpus")
    if not _truthy("AUTH_COOKIE_SECURE"):
        warnings.append("AUTH_COOKIE_SECURE is not true; the session cookie can travel over plain HTTP")
    if os.environ.get("AUTH_SIGNUP_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}:
        warnings.append("AUTH_SIGNUP_ENABLED is not false; anyone who reaches the app can create an account")
    if not os.environ.get("CSRF_ALLOWED_ORIGINS", "").strip():
        warnings.append("CSRF_ALLOWED_ORIGINS is unset; only the localhost defaults are accepted")
    if _truthy("RETENTION_CLEANUP_ENABLED"):
        warnings.append("RETENTION_CLEANUP_ENABLED=true deletes old articles, including rated ones (#255)")
    return errors, warnings


def _dev_checks() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if _truthy("TELEGRAM_NOTIFICATIONS_ENABLED"):
        errors.append("TELEGRAM_NOTIFICATIONS_ENABLED=true would message a real chat from dev")
    for secret in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        if os.environ.get(secret, "").strip():
            # Name only: never echo a secret value.
            errors.append(f"{secret} is set; dev must not hold the production bot credentials")
    url = os.environ.get("DATABASE_URL", "sqlite:///./data/signal_sports.db")
    reason = production_database_reason(url)
    if reason:
        errors.append(f"DATABASE_URL points at a production database: {reason}")
    if _truthy("SCHEDULER_ENABLED"):
        warnings.append("SCHEDULER_ENABLED=true: a dev worker polls live sources and may call the LLM")
    return errors, warnings


def validate_deploy_startup_config() -> list[str]:
    """Refuse unsafe settings for the current DEPLOY_ENV; return the warnings.

    Local mode returns ``[]`` without checking anything.
    """
    mode = deploy_env()
    if mode == LOCAL:
        return []
    errors, warnings = _hosted_checks() if mode == HOSTED else _dev_checks()
    if errors:
        raise UnsafeDeployConfig(
            f"Refusing to start with DEPLOY_ENV={mode}:\n  - " + "\n  - ".join(errors)
        )
    for message in warnings:
        logger.warning("DEPLOY_ENV=%s: %s", mode, message)
    return warnings
