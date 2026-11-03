"""#409 follow-up (owner decision R11): count the articles that end with sport=unknown
after an LLM failure, per run, so an outage's cost is visible.

The decision itself is unchanged: such an article stays hidden. These tests pin the
counter only: it counts `rules_fallback_after_llm_failure` rows whose final sport is
unknown, split by failure reason, and nothing else (a fallback that still found a
sport is not counted; neither is a low-confidence fallback). Fake adapter and fake
provider; no network.
"""
import logging
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config
from app.ingestion.run_metrics import ArticleQualityCounters, compute_run_metrics

WALLA = "walla_sport"
UNKNOWN_TITLES = ["סערה גדולה הלילה: ההחלטה שמחכה לכולם", "הוא חזר הביתה אחרי שנים: הסיפור המלא"]
KNOWN_TITLE = "ליגת העל בכדורסל: מכבי תל אביב החתימה גארד חדש"
LOWCONF_TITLE = "מה קרה שם אתמול בערב? כולם מדברים על זה"
URLS = [f"https://sports.walla.co.il/item/4090{i:04d}" for i in range(4)]


class _FakeAdapter:
    def __init__(self, items):
        self._items = items

    def fetch(self):
        return list(self._items)


class _FailingProvider:
    """Fails every call with a typed reason, except titles mapped to a low-confidence answer."""
    can_classify = True
    provider_id = "fake:failing"
    last_failure_was_connect_error = False
    last_call_latency_ms = 0.0
    last_usage = None
    last_raw_content = None

    def __init__(self, reasons, low_conf_titles=()):
        self.reasons = list(reasons)
        self.low_conf_titles = set(low_conf_titles)
        self.last_failure_reason = "none"

    def classify_title(self, title, language, subtitle=None):
        if title in self.low_conf_titles:
            from app.classification.llm_result import LLMClassificationResult
            self.last_failure_reason = "none"
            return LLMClassificationResult(
                sport="unknown", league=None, entities=[], event_type="news",
                importance="low", confidence=0.2, reason="unsure",
            )
        self.last_failure_reason = self.reasons.pop(0)
        return None


@pytest.fixture
def db(_application):
    from app.db.database import SessionLocal, init_db
    from app.db.orm_models import ArticleRow

    init_db()

    def cleanup(s):
        s.query(ArticleRow).filter(ArticleRow.url.in_(URLS)).delete(synchronize_session=False)
        s.execute(text("DELETE FROM ingestion_runs WHERE source_id = :w"), {"w": WALLA})
        s.commit()

    with SessionLocal() as s:
        cleanup(s)
    yield SessionLocal
    with SessionLocal() as s:
        cleanup(s)


def _run(db, monkeypatch, titles, provider):
    from app.ingestion import ingestion_service

    monkeypatch.setattr(ingestion_service, "_LLM_PROVIDER", provider)
    items = [RawSourceItem(WALLA, u, t, datetime.now(tz=timezone.utc), "") for u, t in zip(URLS, titles)]
    with patch("app.ingestion.ingestion_service.build_adapter",
               side_effect=lambda cfg: _FakeAdapter(items)), \
         patch("app.ingestion.ingestion_service.get_effective_enabled_sources",
               return_value=[get_source_config(WALLA)]), \
         db() as session:
        [result] = ingestion_service.run_ingestion(session, llm_gating_enabled_override=False)
        stored = dict(session.execute(text(
            "SELECT title, sport || '|' || classified_by FROM articles WHERE url IN ("
            + ",".join(f"'{u}'" for u in URLS) + ")")).all())
        persisted = session.execute(text(
            "SELECT metrics FROM ingestion_runs WHERE source_id = :w"), {"w": WALLA}).scalar()
    return result, stored, persisted


def test_counts_unknown_sport_after_llm_failure_by_reason(db, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="app.ingestion.ingestion_service")
    provider = _FailingProvider(["timeout", "http_error", "timeout"], low_conf_titles=[LOWCONF_TITLE])
    titles = [*UNKNOWN_TITLES, KNOWN_TITLE, LOWCONF_TITLE]
    result, stored, persisted = _run(db, monkeypatch, titles, provider)

    # The fixture does what it claims: two unknown failures, one failure that still
    # found a sport, one low-confidence fallback that is also unknown.
    assert stored[UNKNOWN_TITLES[0]] == "unknown|rules_fallback_after_llm_failure"
    assert stored[UNKNOWN_TITLES[1]] == "unknown|rules_fallback_after_llm_failure"
    assert stored[KNOWN_TITLE] == "basketball|rules_fallback_after_llm_failure"
    assert stored[LOWCONF_TITLE].endswith("|rules_fallback_low_confidence")

    m = result.metrics
    assert m["rules_fallback_unknown_sport"] == 2
    assert m["rules_fallback_unknown_sport_by_reason"] == {"timeout": 1, "http_error": 1}
    assert '"rules_fallback_unknown_sport": 2' in persisted     # persisted on the run row
    assert "Unknown-sport fallbacks: 2 {'timeout': 1, 'http_error': 1}" in caplog.text


def test_metrics_default_to_zero_when_nothing_fell_back():
    m = compute_run_metrics(
        counters=ArticleQualityCounters(), llm_attempts=0, llm_successes=0,
        llm_fallback_connect_error=0, llm_fallback_timeout=0, llm_fallback_http_error=0,
        llm_fallback_bad_response_shape=0, llm_fallback_unparseable_json=0,
        llm_fallback_low_confidence=0, llm_failure_latencies={}, llm_skipped=0,
        llm_skip_reasons={}, llm_call_reasons={}, llm_avg_ms=None, llm_p95_ms=None, total_ms=1.0,
    )
    assert m["rules_fallback_unknown_sport"] == 0
    assert m["rules_fallback_unknown_sport_by_reason"] == {}
