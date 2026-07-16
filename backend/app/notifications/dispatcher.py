"""
Notification dispatcher (M7-7, #153) — claims eligible outbox events and
delivers them through the ``NotificationSender`` boundary.

INDEPENDENCE FROM INGESTION. The dispatcher runs as its own orchestration
stage AFTER planning; its failures degrade the cycle to
``succeeded_with_warnings`` and can never roll back or fail ingestion — and a
Telegram outage never marks the ingestion system dead (health keeps the two
apart, M7-8).

CLAIM-THEN-SEND. Each event is durably marked ``claimed`` (with timestamp and
attempt count) and COMMITTED *before* the network attempt. A process crash
during delivery therefore leaves a diagnosable ``claimed`` row — which is
deliberately NOT reset to pending on restart: the send may have gone out, so
resending is exactly the duplicate the product policy forbids. Stale claims
surface for manual review (M7-8).

RETRY SEMANTICS (bounded, conservative):
  - ``failed_retryable`` → eligible again after an exponential backoff
    (TELEGRAM_RETRY_BACKOFF_SECONDS * 2^(attempts-1)), up to
    TELEGRAM_MAX_ATTEMPTS, then ``failed_final``.
  - ``failed_final`` and ``unknown`` are terminal for automation. No code path
    resends an ``unknown`` — a rare missed notification is preferred over a
    duplicate one.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.db.orm_models import NotificationEventRow
from app.notifications import telegram as tg
from app.notifications.outbox import (
    CLAIMED,
    FAILED_FINAL,
    FAILED_RETRYABLE,
    PENDING,
    SENT,
    UNKNOWN,
)
from app.notifications.planner import telegram_enabled

logger = logging.getLogger(__name__)

_DISPATCH_BATCH = 10


def max_attempts() -> int:
    try:
        v = int(os.getenv("TELEGRAM_MAX_ATTEMPTS", "5"))
        return v if v >= 1 else 5
    except ValueError:
        return 5


def backoff_base_seconds() -> int:
    try:
        v = int(os.getenv("TELEGRAM_RETRY_BACKOFF_SECONDS", "60"))
        return v if v >= 1 else 60
    except ValueError:
        return 60


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _retry_eligible(event: NotificationEventRow) -> bool:
    """A failed_retryable event may be retried only after its backoff window."""
    if event.status == PENDING:
        return True
    if event.status != FAILED_RETRYABLE:
        return False
    if event.attempt_count >= max_attempts():
        return False
    if not event.last_attempt_at:
        return True
    wait = backoff_base_seconds() * (2 ** max(0, event.attempt_count - 1))
    next_allowed = datetime.fromisoformat(event.last_attempt_at) + timedelta(seconds=wait)
    return _now() >= next_allowed


def dispatch_pending(session: Session,
                     sender: Optional[tg.NotificationSender] = None) -> dict:
    """Deliver eligible outbox events. Returns the cycle dispatch summary."""
    if not telegram_enabled():
        return {"skipped": "telegram_disabled"}

    if sender is None:
        sender = tg.TelegramSender()
    if not sender.configured():
        # Delivery unavailable ≠ ingestion failure. Visible, not fatal.
        logger.warning("notification delivery unavailable: Telegram not configured")
        return {"skipped": "not_configured"}

    candidates = (
        session.query(NotificationEventRow)
        .filter(NotificationEventRow.status.in_([PENDING, FAILED_RETRYABLE]))
        .order_by(NotificationEventRow.created_at)
        .limit(_DISPATCH_BATCH)
        .all()
    )

    summary = {"attempted": 0, "sent": 0, "failed_retryable": 0,
               "failed_final": 0, "unknown": 0, "waiting_backoff": 0}

    for event in candidates:
        if not _retry_eligible(event):
            if event.status == FAILED_RETRYABLE and event.attempt_count >= max_attempts():
                event.status = FAILED_FINAL
                event.final_at = _now().isoformat()
                event.last_error_class = (event.last_error_class or "") + "|attempts_exhausted"
                session.commit()
                summary["failed_final"] += 1
            else:
                summary["waiting_backoff"] += 1
            continue

        # Durable claim BEFORE the network attempt (crash-after-claim is
        # diagnosable and never auto-reset).
        event.status = CLAIMED
        event.claimed_at = _now().isoformat()
        event.attempt_count += 1
        event.last_attempt_at = event.claimed_at
        event.provider = getattr(sender, "provider", "telegram")
        session.commit()

        text = tg.build_message(event.canonical_headline, event.source, event.url)
        result = sender.send(text)
        summary["attempted"] += 1

        if result.status == tg.SENT:
            event.status = SENT
            event.provider_message_id = result.message_id
            event.final_at = _now().isoformat()
            summary["sent"] += 1
            logger.info("notification sent: %s (message_id=%s)",
                        event.id, result.message_id)
        elif result.status == tg.FAILED_RETRYABLE:
            if event.attempt_count >= max_attempts():
                event.status = FAILED_FINAL
                event.final_at = _now().isoformat()
                summary["failed_final"] += 1
            else:
                event.status = FAILED_RETRYABLE
                summary["failed_retryable"] += 1
            event.last_error_class = result.error_class
        elif result.status == tg.FAILED_FINAL:
            event.status = FAILED_FINAL
            event.final_at = _now().isoformat()
            event.last_error_class = result.error_class
            summary["failed_final"] += 1
        else:                                     # UNKNOWN — terminal for automation
            event.status = UNKNOWN
            event.last_error_class = result.error_class
            summary["unknown"] += 1
            logger.warning("notification %s outcome UNKNOWN (%s) — will NOT be "
                           "resent automatically; manual review required",
                           event.id, result.error_class)
        session.commit()

    return summary
