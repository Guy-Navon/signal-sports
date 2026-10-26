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
    _hosted_mail_checks(errors, warnings)
    _hosted_google_checks(errors, warnings)
    _hosted_llm_checks(errors)
    return errors, warnings


def _hosted_llm_checks(errors: list[str]) -> None:
    """A NAMED LLM provider that falls back to disabled is an accident, not a choice.

    CLASSIFICATION_PROVIDER=disabled is the intentional rules-only start. Naming a provider
    whose settings are incomplete (no base URL, model or key) also ends in the disabled
    provider, with only a log warning, so a host would quietly classify rules-only. Refuse
    that on a host. The message names variables only; the provider factory never logs a
    value it treats as secret."""
    name = os.environ.get("CLASSIFICATION_PROVIDER", "disabled").strip().lower()
    if name in ("", "disabled", "fake"):
        return
    from app.classification.providers import DisabledLLMProvider
    from app.classification.service import get_llm_provider

    if isinstance(get_llm_provider(), DisabledLLMProvider):
        errors.append(
            f"CLASSIFICATION_PROVIDER={name} is set but its configuration is incomplete, so the "
            "feed would run rules-only; set the missing CLASSIFICATION_* keys (the log names "
            "them) or CLASSIFICATION_PROVIDER=disabled for an intentional rules-only start")


def _hosted_google_checks(errors: list[str], warnings: list[str]) -> None:
    """Google sign-in on a host: the redirect URI must be https, a partial
    configuration (which leaves Google silently disabled) is called out, and
    the redirect's origin should be the origin the browser uses (the start
    POST is CSRF-checked against CSRF_ALLOWED_ORIGINS)."""
    from urllib.parse import urlparse

    from app.services import google_oauth

    redirect = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    if redirect and not redirect.lower().startswith("https://"):
        errors.append("GOOGLE_OAUTH_REDIRECT_URI must be https://")
    if google_oauth.partially_configured():
        warnings.append(
            "Google sign-in is partially configured (set GOOGLE_OAUTH_CLIENT_ID, "
            "GOOGLE_OAUTH_CLIENT_SECRET and GOOGLE_OAUTH_REDIRECT_URI, or none); it stays disabled")
    if redirect:
        parsed = urlparse(redirect)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        allowed = {o.strip() for o in os.environ.get("CSRF_ALLOWED_ORIGINS", "").split(",") if o.strip()}
        if origin not in allowed:
            warnings.append(f"GOOGLE_OAUTH_REDIRECT_URI's origin {origin} is not in CSRF_ALLOWED_ORIGINS")


def _hosted_mail_checks(errors: list[str], warnings: list[str]) -> None:
    """Verification email on a host: never a dev mailer, never an http link,
    and a loud note when signup can start but nothing can deliver the link
    (signup then answers 503 rather than skipping verification)."""
    from app.services import mailer

    backend = os.environ.get("MAIL_BACKEND", "").strip().lower()
    if backend in ("console", "memory"):
        errors.append(f"MAIL_BACKEND={backend} is a development mailer")
    if not mailer.smtp_starttls():
        errors.append("SMTP_STARTTLS=false sends SMTP credentials and verification links in clear")
    public_url = os.environ.get("APP_PUBLIC_URL", "").strip()
    if public_url and not public_url.lower().startswith("https://"):
        errors.append("APP_PUBLIC_URL must be https:// (verification links carry a secret)")
    signup_open = os.environ.get("AUTH_SIGNUP_ENABLED", "true").strip().lower() not in {
        "0", "false", "no", "off",
    }
    signup_possible = signup_open or bool(os.environ.get("AUTH_SIGNUP_ALLOWED_EMAILS", "").strip())
    if signup_possible and backend not in ("console", "memory"):
        if mailer.get_mailer() is None:
            warnings.append("signup is possible but no mailer is configured; password signup answers 503")
        elif not public_url:
            warnings.append("APP_PUBLIC_URL is unset; verification links would point at localhost")


def _dev_checks() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if _truthy("TELEGRAM_NOTIFICATIONS_ENABLED"):
        errors.append("TELEGRAM_NOTIFICATIONS_ENABLED=true would message a real chat from dev")
    for secret in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        if os.environ.get(secret, "").strip():
            # Name only: never echo a secret value.
            errors.append(f"{secret} is set; dev must not hold the production bot credentials")
    for name in ("MONITOR_CYCLE_URL", "MONITOR_SOURCES_URL", "MONITOR_FRESH_URL", "MONITOR_BACKUP_URL"):
        if os.environ.get(name, "").strip():
            errors.append(f"{name} is set; dev must not ping production's monitor")
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
