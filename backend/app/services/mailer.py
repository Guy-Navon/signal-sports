"""Outgoing email for account verification (and nothing else).

The smallest integration that works with any transactional provider: stdlib
SMTP with STARTTLS on port 587 (Hetzner Cloud blocks outbound 25 and 465).
``MAIL_BACKEND`` picks the implementation and is read at call time:

  smtp     SMTP_HOST / SMTP_PORT / SMTP_USERNAME / SMTP_PASSWORD / MAIL_FROM
           (SMTP_STARTTLS=false only for a local sink; refused when hosted)
  console  development only, and only when set explicitly: logs the message,
           link included (refused at hosted startup, inert at request time)
  memory   tests: appends to MEMORY_OUTBOX (same hosted rules)

Unset (or anything else) means *no mailer* in every mode: password signup then
fails closed with 503. A missing mail configuration never logs a link and
never skips verification.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional, Protocol

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 10


class MailDeliveryError(Exception):
    """The message could not be handed to the mail server."""


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str
    html: str


class Mailer(Protocol):
    def send(self, message: OutgoingEmail) -> None: ...


MEMORY_OUTBOX: list[OutgoingEmail] = []


class MemoryMailer:
    def send(self, message: OutgoingEmail) -> None:
        MEMORY_OUTBOX.append(message)


class ConsoleMailer:
    def send(self, message: OutgoingEmail) -> None:
        # Dev only (refused when hosted): the link is the whole point here.
        logger.warning("DEV MAIL to %s: %s\n%s", message.to, message.subject, message.text)


class SmtpMailer:
    def __init__(
        self, host: str, port: int, username: str, password: str, sender: str,
        starttls: bool = True,
    ) -> None:
        self.starttls = starttls
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender

    def send(self, message: OutgoingEmail) -> None:
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = message.to
        msg["Subject"] = message.subject
        msg.set_content(message.text)
        msg.add_alternative(message.html, subtype="html")
        try:
            with smtplib.SMTP(self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
                if self.starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if self.username:
                    smtp.login(self.username, self.password)
                smtp.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            # The exception type only: SMTP errors can echo the recipient.
            raise MailDeliveryError(type(exc).__name__) from exc


def mail_backend() -> str:
    return os.environ.get("MAIL_BACKEND", "").strip().lower()


def _hosted() -> bool:
    from app.core.deploy_mode import HOSTED, deploy_env

    return deploy_env() == HOSTED


def smtp_settings_missing() -> list[str]:
    return [
        name for name in ("SMTP_HOST", "MAIL_FROM")
        if not os.environ.get(name, "").strip()
    ]


def smtp_starttls() -> bool:
    """SMTP_STARTTLS=false exists only for a local plain SMTP sink such as
    Mailpit; a hosted deployment refuses it (credentials and links would
    travel in clear)."""
    return os.environ.get("SMTP_STARTTLS", "true").strip().lower() not in {
        "0", "false", "no", "off",
    }


def get_mailer() -> Optional[Mailer]:
    """The configured mailer, or None when email cannot be sent."""
    backend = mail_backend()
    if backend in ("memory", "console"):
        # Development mailers are never live on a host, even if startup's
        # refusal was somehow bypassed.
        if _hosted():
            return None
        return MemoryMailer() if backend == "memory" else ConsoleMailer()
    if backend == "smtp":
        if smtp_settings_missing():
            return None
        return SmtpMailer(
            host=os.environ["SMTP_HOST"].strip(),
            port=int(os.environ.get("SMTP_PORT", "").strip() or 587),
            username=os.environ.get("SMTP_USERNAME", "").strip(),
            password=os.environ.get("SMTP_PASSWORD", ""),
            sender=os.environ["MAIL_FROM"].strip(),
            starttls=smtp_starttls(),
        )
    return None


def app_public_url() -> str:
    """Base URL for links in emails. Never derived from the request's Host."""
    return (os.environ.get("APP_PUBLIC_URL", "").strip() or "http://localhost:5173").rstrip("/")
