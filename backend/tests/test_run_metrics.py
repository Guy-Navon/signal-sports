"""
Issue #31 — per-run LLM dependency / classification quality metrics.

Covers: metric computation (rates, division-by-zero on empty runs), the
disabled-provider path (call_rate=0, abstention still measured), persistence
round-trip through ingestion_runs, quality-endpoint shape, old-run
compatibility (metrics=None), and the denominator-honesty guarantee (the
forced classification backfill never writes ingestion_runs rows).
"""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.ingestion.run_metrics import (
    ArticleQualityCounters,
    METRICS_SCHEMA_VERSION,
    compute_run_metrics,
)
from app.models.article import Article
from app.models.ingestion import IngestionRunRecord
from app.repositories import ingestion_repository


def _article(**kwargs) -> Article:
    defaults = dict(
        id="m1",
        source="test",
        source_display_name="Test",
        url="https://example.com/a",
        title="t",
        language="he",
        published_at=datetime(2026, 7, 7, tzinfo=timezone.utc),
        sport="basketball",
        league=None,
        entities=[],
        event_type="news",
        importance="medium",
        confidence=0.9,
        tags=[],
    )
    defaults.update(kwargs)
    return Article(**defaults)


def _compute(counters=None, **overrides) -> dict:
    kwargs = dict(
        counters=counters or ArticleQualityCounters(),
        llm_attempts=0,
        llm_successes=0,
        llm_fallback_connect_error=0,
        llm_fallback_timeout_or_parse=0,
        llm_fallback_low_confidence=0,
        llm_skipped=0,
        llm_skip_reasons={},
        llm_call_reasons={},
        llm_avg_ms=None,
        llm_p95_ms=None,
        total_ms=1000.0,
    )
    kwargs.update(overrides)
    return compute_run_metrics(**kwargs)


class TestCounters:
    def test_observe_counts_abstention_ambiguity_conflicts(self):
        c = ArticleQualityCounters()
        c.observe(_article(sport="unknown"))
        c.observe(_article(tags=["ambiguous_club"]))
        c.observe(_article(classification_trace={
            "conflicts": [
                {"rule": "weighted_evidence_override"},
                {"rule": "entity_dropped_sport_conflict"},
            ],
            "event": {"corrected": True},
        }))
        c.observe(_article())  # clean article
        assert c.articles == 4
        assert c.abstained == 1
        assert c.ambiguous == 1
        assert c.with_conflicts == 1
        assert c.weighted_evidence_overrides == 1
        assert c.events_corrected == 1

    def test_observe_handles_missing_trace(self):
        c = ArticleQualityCounters()
        c.observe(_article(classification_trace=None))
        assert c.with_conflicts == 0
        assert c.events_corrected == 0


class TestComputeRunMetrics:
    def test_empty_run_all_rates_none_no_division_error(self):
        m = _compute(total_ms=0.0)
        assert m["schema_version"] == METRICS_SCHEMA_VERSION
        assert m["new_articles"] == 0
        for key in (
            "deterministic_accept_rate", "llm_call_rate", "gate_skip_rate",
            "fallback_rate", "low_confidence_fallback_rate", "abstention_rate",
            "ambiguity_rate", "conflict_rate", "weighted_evidence_override_rate",
            "event_correction_rate", "articles_per_minute",
            "estimated_cost_per_1000_articles",
        ):
            assert m[key] is None, key
        assert m["estimated_cost_per_run"] == 0.0

    def test_disabled_provider_run_reports_call_rate_zero(self):
        # 4 inserted articles, one abstained, zero LLM activity — the
        # LLM-disabled path must measure call_rate 0.0, abstention 0.25.
        c = ArticleQualityCounters()
        for sport in ("basketball", "unknown", "football", "basketball"):
            c.observe(_article(sport=sport))
        m = _compute(counters=c)
        assert m["llm_call_rate"] == 0.0
        assert m["deterministic_accept_rate"] == 1.0
        assert m["abstention_rate"] == 0.25
        assert m["fallback_rate"] is None  # no attempts → not measurable

    def test_rates_computed_from_counts(self):
        c = ArticleQualityCounters()
        for _ in range(10):
            c.observe(_article())
        m = _compute(
            counters=c,
            llm_attempts=4,
            llm_successes=3,
            llm_fallback_low_confidence=1,
            llm_skipped=6,
            llm_skip_reasons={"deterministic_accept": 6},
            llm_call_reasons={"sport_unknown": 4},
            llm_avg_ms=800.0,
            llm_p95_ms=1500.0,
            total_ms=60000.0,
        )
        assert m["llm_call_rate"] == 0.4
        assert m["deterministic_accept_rate"] == 0.6
        assert m["gate_skip_rate"] == 0.6
        assert m["fallback_rate"] == 0.25
        assert m["low_confidence_fallback_rate"] == 0.25
        assert m["articles_per_minute"] == 10.0
        assert m["llm_avg_ms"] == 800.0
        assert m["llm_p95_ms"] == 1500.0

    def test_cost_estimate_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_COST_PER_CALL_ESTIMATE", "0.002")
        c = ArticleQualityCounters()
        for _ in range(10):
            c.observe(_article())
        m = _compute(counters=c, llm_attempts=5, llm_successes=5)
        assert m["estimated_cost_per_run"] == 0.01
        assert m["estimated_cost_per_1000_articles"] == 1.0

    def test_invalid_cost_env_falls_back_to_zero(self, monkeypatch):
        monkeypatch.setenv("LLM_COST_PER_CALL_ESTIMATE", "not-a-number")
        m = _compute(llm_attempts=3)
        assert m["cost_per_call_estimate"] == 0.0
        assert m["estimated_cost_per_run"] == 0.0


class TestPersistenceRoundTrip:
    def test_run_record_metrics_round_trip(self, client: TestClient):
        from app.db.database import SessionLocal
        metrics = _compute()
        record = IngestionRunRecord(
            id="run-metrics-rt",
            source_id="metrics-rt-source",
            started_at=datetime(2026, 7, 7, 10, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 7, 7, 10, 1, tzinfo=timezone.utc),
            status="ok",
            fetched_count=5,
            inserted_count=0,
            skipped_duplicate_count=5,
            failed_count=0,
            metrics=metrics,
        )
        with SessionLocal() as session:
            ingestion_repository.insert(session, record)
        with SessionLocal() as session:
            loaded = ingestion_repository.get_recent_for_source(
                session, "metrics-rt-source", limit=1
            )[0]
        assert loaded.id == "run-metrics-rt"
        assert loaded.metrics == metrics

    def test_old_run_without_metrics_loads_as_none(self, client: TestClient):
        from app.db.database import SessionLocal
        record = IngestionRunRecord(
            id="run-pre-metrics",
            started_at=datetime(2026, 7, 6, tzinfo=timezone.utc),
            source_id="pre-metrics-source",
            status="ok",
            fetched_count=1,
            inserted_count=1,
            skipped_duplicate_count=0,
            failed_count=0,
        )
        with SessionLocal() as session:
            ingestion_repository.insert(session, record)
        with SessionLocal() as session:
            loaded = ingestion_repository.get_recent_for_source(
                session, "pre-metrics-source", limit=1
            )[0]
        assert loaded.id == "run-pre-metrics"
        assert loaded.metrics is None


class TestQualityEndpoint:
    def test_quality_endpoint_exposes_run_history(self, client: TestClient):
        from app.db.database import SessionLocal
        # Far-future started_at so the row is guaranteed inside the endpoint's
        # newest-20 window even when the full suite has inserted many runs.
        record = IngestionRunRecord(
            id="run-quality-shape",
            source_id="quality-shape-source",
            started_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
            status="ok",
            fetched_count=3,
            inserted_count=0,
            skipped_duplicate_count=3,
            failed_count=0,
            metrics=_compute(),
        )
        with SessionLocal() as session:
            ingestion_repository.insert(session, record)
        resp = client.get("/api/ingest/quality")
        assert resp.status_code == 200
        body = resp.json()
        assert "llm_dependency_runs" in body
        run = next(r for r in body["llm_dependency_runs"] if r["id"] == "run-quality-shape")
        assert run["metrics"]["schema_version"] == METRICS_SCHEMA_VERSION
        assert run["metrics"]["llm_call_rate"] is None  # empty run

    def test_forced_backfill_writes_no_run_records(self, client: TestClient):
        # Denominator honesty: /api/classify/backfill must never create
        # ingestion_runs rows — its numbers are not gated-ingestion metrics.
        from app.db.database import SessionLocal
        with SessionLocal() as session:
            before = len(ingestion_repository.get_recent(session, limit=200))
        resp = client.post("/api/classify/backfill?source_id=walla_sport")
        assert resp.status_code in (200, 400, 409, 503)
        with SessionLocal() as session:
            after = len(ingestion_repository.get_recent(session, limit=200))
        assert after == before


class TestEndToEndIngestion:
    def test_normal_ingestion_run_persists_metrics(self, client: TestClient):
        """A real (mocked-feed) gated ingestion run writes a run record whose
        metrics dict reflects the disabled-provider path: call_rate 0.0,
        deterministic accept 1.0, abstention measured."""
        import types
        from unittest.mock import patch
        from app.db.database import SessionLocal

        entry = types.SimpleNamespace(
            title="Metrics e2e: fake basketball headline",
            link="https://eurohoops.net/fake/metrics-e2e-001",
            published_parsed=None,
            updated_parsed=None,
            summary=None,
        )
        feed = types.SimpleNamespace(entries=[entry], bozo=False)
        with patch("feedparser.parse", return_value=feed):
            resp = client.post("/api/ingest/run?source_id=eurohoops")
        assert resp.status_code == 200
        live = resp.json()["sources"][0]
        assert live["metrics"] is not None
        assert live["metrics"]["llm_attempts"] == 0

        with SessionLocal() as session:
            run = ingestion_repository.get_recent_for_source(session, "eurohoops", limit=1)[0]
        m = run.metrics
        assert m is not None
        assert m["schema_version"] == METRICS_SCHEMA_VERSION
        assert m["new_articles"] == run.inserted_count
        if run.inserted_count > 0:
            assert m["llm_call_rate"] == 0.0
            assert m["deterministic_accept_rate"] == 1.0
            assert m["abstention_rate"] is not None
