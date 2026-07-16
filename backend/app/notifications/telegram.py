"""
Telegram delivery adapter (M7-7, #153) — the small ``NotificationSender``
boundary and its Telegram implementation. Nothing else in the system knows
Telegram exists.

HONESTY ABOUT THE PROVIDER. Telegram's ``sendMessage`` has no client-supplied
idempotency key, so exactly-once network delivery CANNOT be claimed and is
not. The product policy (documented in docs/NOTIFICATIONS.md):

    At most one attempted user-visible notification per story is more
    important than guaranteed eventual delivery.

So every network outcome is classified into exactly one of:

  - ``sent``             — Telegram confirmed (ok=true + message_id). Never resent.
  - ``failed_retryable`` — definite non-delivery with a transient cause
                           (connect error before the request was transmitted,
                           429, 5xx). Bounded backoff, capped attempts.
  - ``failed_final``     — definite non-delivery with a permanent cause
                           (400 bad request / 403 bot blocked / invalid config).
  - ``unknown``          — the request MAY have reached Telegram (timeout after
                           transmission may have begun, connection interrupted
                           mid-request). NEVER automatically resent; surfaced
                           for manual review.

SECRETS. The bot token appears in the request URL — therefore the URL is never
logged, exceptions are reduced to their class name, and no provider payload
that could echo configuration is persisted beyond a sanitized description.

MESSAGE CONTRACT (pilot): plain text — canonical headline, source name,
original-article link. Plain text deliberately: Markdown/HTML entity escaping
is a failure class with zero product value here.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional, Protocol

logger = logging.getLogger(__name__)

# httpx logs every request URL at INFO ("HTTP Request: POST https://api.
# telegram.org/bot<TOKEN>/sendMessage …") and the bot token is IN the URL path.
# The worker configures root logging at INFO, so without this cap the first
# real send would print the token to the console/log. Capped at import so the
# guarantee holds in every process that can send (worker, API manual run).
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

SENT = "sent"
FAILED_RETRYABLE = "failed_retryable"
FAILED_FINAL = "failed_final"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class SendResult:
    status: str                       # sent | failed_retryable | failed_final | unknown
    message_id: Optional[str] = None  # Telegram message id when confirmed
    error_class: Optional[str] = None # sanitized — an error CLASS, never a payload


class NotificationSender(Protocol):
    """The boundary. A fake implementation drives every test; the real one
    only ever runs in the controlled acceptance step and production."""

    def configured(self) -> bool: ...
    def send(self, text: str) -> SendResult: ...


def build_message(headline: str, source: str, url: str) -> str:
    """The pilot message: headline, source, link. Nothing else."""
    return f"{headline}\n{source}\n{url}"


class TelegramSender:
    """Telegram Bot API ``sendMessage`` over HTTPS. Plain text, bounded timeout."""

    provider = "telegram"

    def __init__(self) -> None:
        self._token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self._chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        try:
            self._timeout = float(os.getenv("TELEGRAM_REQUEST_TIMEOUT_SECONDS", "10"))
        except ValueError:
            self._timeout = 10.0

    def configured(self) -> bool:
        return bool(self._token and self._chat_id)

    def send(self, text: str) -> SendResult:
        if not self.configured():
            # Definite pre-request failure: nothing was ever transmitted.
            return SendResult(FAILED_FINAL, error_class="not_configured")

        import httpx

        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        try:
            r = httpx.post(
                url,
                json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "disable_web_page_preview": False,
                },
                timeout=self._timeout,
            )
        except httpx.ConnectError:
            # The connection was never established — definitely not delivered.
            return SendResult(FAILED_RETRYABLE, error_class="connect_error")
        except httpx.TimeoutException:
            # The request MAY have been transmitted. Ambiguous — never resend.
            return SendResult(UNKNOWN, error_class="timeout")
        except Exception as exc:                 # noqa: BLE001 - conservative catch
            # Anything we cannot prove was pre-transmission is ambiguous.
            return SendResult(UNKNOWN, error_class=type(exc).__name__)

        try:
            body = r.json()
        except ValueError:
            body = {}

        if r.status_code == 200 and body.get("ok"):
            mid = str(body.get("result", {}).get("message_id", "")) or None
            return SendResult(SENT, message_id=mid)

        # Explicit provider rejection — proven non-delivery.
        description = str(body.get("description", ""))[:120]
        if r.status_code in (400, 401, 403, 404):
            # bad request / bad token / bot blocked / bad chat: retrying cannot help.
            return SendResult(FAILED_FINAL,
                              error_class=f"http_{r.status_code}:{description}")
        if r.status_code == 429 or r.status_code >= 500:
            return SendResult(FAILED_RETRYABLE,
                              error_class=f"http_{r.status_code}:{description}")
        return SendResult(UNKNOWN, error_class=f"http_{r.status_code}")
