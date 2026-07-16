"""M7-7 (#153) — Telegram delivery: at-most-one semantics through a fake sender.

The policy under test: at most one attempted user-visible notification per
story beats guaranteed eventual delivery. `sent` never resends; definite
failures retry bounded; `unknown` is terminal for automation and survives
restarts; a crash after claim is diagnosable and never auto-reset.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.notifications import telegram as tg
from app.notifications.dispatcher import dispatch_pending, max_attempts
from app.notifications.outbox import (
    SENT,
    StorySnapshot,
    plan_story,
    set_watermark,
)

PROFILE = "guy"
POLICY = "v1"


class FakeSender:
    """Scripted NotificationSender: returns queued results, records calls."""

    provider = "fake"

    def __init__(self, results=None, is_configured=True):
        self.results = list(results or [])
        self.is_configured = is_configured
        self.sent_texts: list[str] = []

    def configured(self):
        return self.is_configured

    def send(self, text):
        self.sent_texts.append(text)
        if self.results:
            return self.results.pop(0)
        return tg.SendResult(tg.SENT, message_id="42")


@pytest.fixture
def session(_application, monkeypatch):
    monkeypatch.setenv("TELEGRAM_NOTIFICATIONS_ENABLED", "true")
    from app.db.database import SessionLocal, init_db
    init_db()
    with SessionLocal() as s:
        for table in ("notification_story_members", "notification_events",
                      "notification_watermarks"):
            s.execute(text(f"DELETE FROM {table}"))
        s.commit()
        set_watermark(s, PROFILE, POLICY)
        yield s
        s.rollback()
        for table in ("notification_story_members", "notification_events",
                      "notification_watermarks"):
            s.execute(text(f"DELETE FROM {table}"))
        s.commit()


def _plant_event(session, member="rss_d153_a", headline="ים מדר חתם במכבי",
                 url="https://example.test/story"):
    out = plan_story(session, profile_id=PROFILE, policy_version=POLICY,
                     story=StorySnapshot(
                         member_article_ids=[member], cluster_id=None,
                         canonical_article_id=member,
                         canonical_headline=headline, source="ספורט 5",
                         url=url, tier="push"))
    return out.event_id


def _event(session, event_id):
    return session.execute(text(
        "SELECT status, attempt_count, provider_message_id, last_error_class, "
        "claimed_at FROM notification_events WHERE id=:i"), {"i": event_id}).fetchone()


class TestConfirmedSuccess:
    def test_sent_stores_message_id_and_never_resends(self, session):
        eid = _plant_event(session)
        sender = FakeSender([tg.SendResult(tg.SENT, message_id="777")])
        s1 = dispatch_pending(session, sender)
        assert s1["sent"] == 1
        row = _event(session, eid)
        assert row[0] == SENT and row[2] == "777"

        # Restart / next cycle / manual run — nothing resends:
        s2 = dispatch_pending(session, FakeSender())
        assert s2["attempted"] == 0
        assert _event(session, eid)[1] == 1        # attempt count unchanged

    def test_message_contract_plain_text(self, session):
        _plant_event(session, headline="כותרת קנונית", url="https://example.test/x")
        sender = FakeSender()
        dispatch_pending(session, sender)
        assert sender.sent_texts == ["כותרת קנונית\nספורט 5\nhttps://example.test/x"]


class TestDefiniteFailures:
    def test_retryable_backs_off_then_retries(self, session, monkeypatch):
        monkeypatch.setenv("TELEGRAM_RETRY_BACKOFF_SECONDS", "60")
        eid = _plant_event(session)
        s1 = dispatch_pending(session, FakeSender(
            [tg.SendResult(tg.FAILED_RETRYABLE, error_class="http_500")]))
        assert s1["failed_retryable"] == 1
        # Immediately after: still inside the backoff window → not attempted.
        s2 = dispatch_pending(session, FakeSender())
        assert s2["attempted"] == 0 and s2["waiting_backoff"] == 1
        # Age the last attempt past the window → retried and sent.
        session.execute(text(
            "UPDATE notification_events SET last_attempt_at=:t WHERE id=:i"),
            {"t": (datetime.now(tz=timezone.utc) - timedelta(minutes=10)).isoformat(),
             "i": eid})
        session.commit()
        s3 = dispatch_pending(session, FakeSender())
        assert s3["sent"] == 1
        assert _event(session, eid)[1] == 2

    def test_attempts_are_capped_then_final(self, session, monkeypatch):
        monkeypatch.setenv("TELEGRAM_MAX_ATTEMPTS", "2")
        monkeypatch.setenv("TELEGRAM_RETRY_BACKOFF_SECONDS", "1")
        eid = _plant_event(session)
        fail = lambda: FakeSender([tg.SendResult(tg.FAILED_RETRYABLE, error_class="http_500")])
        dispatch_pending(session, fail())
        session.execute(text(
            "UPDATE notification_events SET last_attempt_at=:t WHERE id=:i"),
            {"t": (datetime.now(tz=timezone.utc) - timedelta(minutes=10)).isoformat(),
             "i": eid})
        session.commit()
        dispatch_pending(session, fail())          # attempt 2 → cap reached
        assert _event(session, eid)[0] == "failed_final"
        s = dispatch_pending(session, FakeSender())
        assert s["attempted"] == 0                  # final is terminal

    def test_provider_rejection_is_final_immediately(self, session):
        eid = _plant_event(session)
        dispatch_pending(session, FakeSender(
            [tg.SendResult(tg.FAILED_FINAL, error_class="http_403:bot blocked")]))
        row = _event(session, eid)
        assert row[0] == "failed_final"
        assert "403" in row[3]
        assert dispatch_pending(session, FakeSender())["attempted"] == 0


class TestAmbiguousOutcomes:
    def test_unknown_is_never_automatically_resent(self, session):
        eid = _plant_event(session)
        s1 = dispatch_pending(session, FakeSender(
            [tg.SendResult(tg.UNKNOWN, error_class="timeout")]))
        assert s1["unknown"] == 1
        assert _event(session, eid)[0] == "unknown"
        # Restarts, next cycles, manual runs — never again:
        for _ in range(3):
            assert dispatch_pending(session, FakeSender())["attempted"] == 0
        assert _event(session, eid)[1] == 1

    def test_crash_after_claim_is_diagnosable_and_not_reset(self, session):
        """Simulate a worker crash between claim-commit and result-recording:
        the row stays `claimed` with a timestamp — and no dispatcher run may
        auto-reset it to pending."""
        eid = _plant_event(session)

        class CrashingSender(FakeSender):
            def send(self, text):
                raise KeyboardInterrupt        # process death mid-delivery

        with pytest.raises(KeyboardInterrupt):
            dispatch_pending(session, CrashingSender())
        row = _event(session, eid)
        assert row[0] == "claimed" and row[4] is not None

        s = dispatch_pending(session, FakeSender())
        assert s["attempted"] == 0             # claimed is untouched
        assert _event(session, eid)[0] == "claimed"

    def test_uniqueness_prevents_a_replacement_event_after_unknown(self, session):
        """The next planner run must not create a substitute event for a story
        whose delivery outcome is unknown — the lineage already exists."""
        from app.notifications.outbox import ALREADY_NOTIFIED
        _plant_event(session, member="rss_d153_u")
        dispatch_pending(session, FakeSender(
            [tg.SendResult(tg.UNKNOWN, error_class="timeout")]))
        out = plan_story(session, profile_id=PROFILE, policy_version=POLICY,
                         story=StorySnapshot(
                             member_article_ids=["rss_d153_u"], cluster_id=None,
                             canonical_article_id="rss_d153_u",
                             canonical_headline="x", source="s",
                             url="https://example.test/u", tier="push"))
        assert out.outcome == ALREADY_NOTIFIED


class TestGatingAndIndependence:
    def test_disabled_telegram_skips(self, session, monkeypatch):
        monkeypatch.setenv("TELEGRAM_NOTIFICATIONS_ENABLED", "false")
        _plant_event(session)
        assert dispatch_pending(session, FakeSender()) == {"skipped": "telegram_disabled"}

    def test_unconfigured_sender_reports_unavailable(self, session):
        _plant_event(session)
        s = dispatch_pending(session, FakeSender(is_configured=False))
        assert s == {"skipped": "not_configured"}
        # The event remains pending for when configuration arrives:
        status = session.execute(text(
            "SELECT status FROM notification_events")).fetchone()[0]
        assert status == "pending"

    def test_delivery_failure_never_fails_the_ingestion_cycle(self, session, monkeypatch):
        import types
        from unittest.mock import patch as mpatch

        from app.ingestion.orchestration import orchestrate_cycle
        _plant_event(session)
        fake_results = [types.SimpleNamespace(
            source_id="walla_sport", fetched=1, inserted=1, skipped_duplicate=0,
            skipped_filtered=0, failed=0, errors=[])]
        with mpatch("app.ingestion.ingestion_service.run_ingestion",
                    return_value=fake_results), \
             mpatch("app.notifications.dispatcher.dispatch_pending",
                    side_effect=RuntimeError("telegram down")):
            out = orchestrate_cycle("manual")
        assert out.status == "succeeded_with_warnings"   # degraded, NOT failed
        assert "telegram down" in (out.error_summary or "")


class TestSenderSecrecy:
    def test_unconfigured_real_sender_fails_final_without_network(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        sender = tg.TelegramSender()
        assert not sender.configured()
        result = sender.send("x")
        assert result.status == tg.FAILED_FINAL
        assert result.error_class == "not_configured"

    def test_send_result_never_carries_the_token(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "SECRET_TOKEN_123")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "555")

        class Boom(Exception):
            pass

        def explode(*a, **k):
            raise Boom("boom")

        monkeypatch.setattr("httpx.post", explode)
        result = tg.TelegramSender().send("hello")
        assert result.status == tg.UNKNOWN
        assert "SECRET_TOKEN_123" not in (result.error_class or "")

    def test_httpx_request_url_logging_is_capped(self, caplog):
        """httpx logs the full request URL (token included) at INFO; importing
        the adapter must cap the httpx/httpcore loggers so that line can never
        be emitted even when root logging runs at INFO (as the worker does)."""
        import logging as _logging

        for name in ("httpx", "httpcore"):
            assert _logging.getLogger(name).getEffectiveLevel() >= _logging.WARNING

        with caplog.at_level(_logging.INFO):
            _logging.getLogger("httpx").info(
                "HTTP Request: POST https://api.telegram.org/botSECRET_TOKEN_123/sendMessage"
            )
        assert not any("SECRET_TOKEN_123" in r.getMessage() for r in caplog.records)
