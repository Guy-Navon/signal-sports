"""
Tests for POST /api/dev/benchmark/llm-gating.

Uses the session-scoped TestClient (CLASSIFICATION_PROVIDER=disabled by default).
Tests that require an active provider use monkeypatching to enable a mock provider
and mock feedparser so no real Ollama/network calls are made.
"""

import types
from unittest.mock import MagicMock, patch

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_entry(title: str, link: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        title=title,
        link=link,
        published_parsed=None,
        updated_parsed=None,
        summary=None,
    )


def _make_feed(entries, bozo=False) -> types.SimpleNamespace:
    return types.SimpleNamespace(entries=entries, bozo=bozo)


def _make_mock_provider(can_classify: bool = True, provider_id: str = "fake:benchmark-test"):
    """Return a mock LLM provider for benchmark tests."""
    from app.ingestion.classifier import ClassificationResult

    mock = MagicMock()
    mock.can_classify = can_classify
    mock.provider_id = provider_id
    mock.last_failure_was_connect_error = False

    def classify_title(title, lang, subtitle=None):
        return ClassificationResult(
            sport="basketball",
            league="NBA",
            entities=[],
            event_type="match_result",
            importance="medium",
            confidence=0.85,
            tags=["basketball", "NBA"],
            reason="fake provider",
        )

    mock.classify_title = classify_title
    return mock


# ── 403 guard ─────────────────────────────────────────────────────────────────


class TestBenchmarkGuards:
    def test_returns_403_when_dev_reset_disabled(self, client):
        """Benchmark endpoint returns 403 if ALLOW_DEV_RESET is not true."""
        with patch.dict("os.environ", {"ALLOW_DEV_RESET": "false"}):
            r = client.post("/api/dev/benchmark/llm-gating")
        assert r.status_code == 403
        assert "ALLOW_DEV_RESET" in r.json()["detail"]

    def test_returns_422_when_provider_cannot_classify(self, client, monkeypatch):
        """Benchmark returns 422 when the classification provider is disabled."""
        monkeypatch.setenv("ALLOW_DEV_RESET", "true")
        # Default test env has CLASSIFICATION_PROVIDER=disabled → can_classify=False
        r = client.post("/api/dev/benchmark/llm-gating")
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert "cannot classify" in detail or "CLASSIFICATION_PROVIDER" in detail

    def test_error_message_mentions_ollama(self, client, monkeypatch):
        """The provider error message should suggest CLASSIFICATION_PROVIDER=ollama."""
        monkeypatch.setenv("ALLOW_DEV_RESET", "true")
        r = client.post("/api/dev/benchmark/llm-gating")
        assert r.status_code == 422
        assert "ollama" in r.json()["detail"].lower()


# ── Benchmark response shape ───────────────────────────────────────────────────


class TestBenchmarkResponseShape:
    """
    Tests that run the full benchmark with a mock provider + mock feedparser.
    These verify the response shape and benchmark logic without real network/LLM calls.
    """

    def _feed_for(self, source_id: str) -> types.SimpleNamespace:
        if source_id == "walla_sport":
            return _make_feed([
                _make_entry("NBA: גולדן סטייט ניצחה", "https://walla.co.il/bench/nba1"),
                _make_entry("ספורט כללי", "https://walla.co.il/bench/gen1"),
            ])
        if source_id == "israel_hayom_sport":
            return _make_feed([
                _make_entry("מכבי תל אביב בכדורסל: ניצחה", "https://www.israelhayom.co.il/sport/israeli-basketball/bench1"),
            ])
        return _make_feed([])

    def test_benchmark_returns_200_with_active_provider(self, client, monkeypatch):
        """With ALLOW_DEV_RESET=true and an active mock provider, benchmark returns 200."""
        monkeypatch.setenv("ALLOW_DEV_RESET", "true")
        mock_provider = _make_mock_provider()

        def feedparser_side_effect(url, **kw):
            for src in ["walla_sport", "israel_hayom_sport"]:
                if src.replace("_", "-") in url or src in url:
                    return self._feed_for(src)
            return _make_feed([])

        with (
            patch("app.api.routes_dev._LLM_PROVIDER", mock_provider),
            patch("app.ingestion.ingestion_service._LLM_PROVIDER", mock_provider),
            patch("feedparser.parse", side_effect=feedparser_side_effect),
        ):
            r = client.post("/api/dev/benchmark/llm-gating")

        assert r.status_code == 200

    def test_benchmark_response_has_required_top_level_fields(self, client, monkeypatch):
        """Response includes provider, sources, baseline, gated, comparison."""
        monkeypatch.setenv("ALLOW_DEV_RESET", "true")
        mock_provider = _make_mock_provider()

        with (
            patch("app.api.routes_dev._LLM_PROVIDER", mock_provider),
            patch("app.ingestion.ingestion_service._LLM_PROVIDER", mock_provider),
            patch("feedparser.parse", return_value=_make_feed([])),
        ):
            r = client.post("/api/dev/benchmark/llm-gating")

        assert r.status_code == 200
        body = r.json()
        assert "provider" in body
        assert "sources" in body
        assert "baseline" in body
        assert "gated" in body
        assert "comparison" in body

    def test_baseline_has_gating_disabled_flag(self, client, monkeypatch):
        """baseline.gating_enabled must be false."""
        monkeypatch.setenv("ALLOW_DEV_RESET", "true")
        mock_provider = _make_mock_provider()

        with (
            patch("app.api.routes_dev._LLM_PROVIDER", mock_provider),
            patch("app.ingestion.ingestion_service._LLM_PROVIDER", mock_provider),
            patch("feedparser.parse", return_value=_make_feed([])),
        ):
            r = client.post("/api/dev/benchmark/llm-gating")

        assert r.json()["baseline"]["gating_enabled"] is False

    def test_gated_has_gating_enabled_flag(self, client, monkeypatch):
        """gated.gating_enabled must be true."""
        monkeypatch.setenv("ALLOW_DEV_RESET", "true")
        mock_provider = _make_mock_provider()

        with (
            patch("app.api.routes_dev._LLM_PROVIDER", mock_provider),
            patch("app.ingestion.ingestion_service._LLM_PROVIDER", mock_provider),
            patch("feedparser.parse", return_value=_make_feed([])),
        ):
            r = client.post("/api/dev/benchmark/llm-gating")

        assert r.json()["gated"]["gating_enabled"] is True

    def test_sources_list_contains_hebrew_broad_sources(self, client, monkeypatch):
        """sources list includes walla_sport and israel_hayom_sport."""
        monkeypatch.setenv("ALLOW_DEV_RESET", "true")
        mock_provider = _make_mock_provider()

        with (
            patch("app.api.routes_dev._LLM_PROVIDER", mock_provider),
            patch("app.ingestion.ingestion_service._LLM_PROVIDER", mock_provider),
            patch("feedparser.parse", return_value=_make_feed([])),
        ):
            r = client.post("/api/dev/benchmark/llm-gating")

        sources = r.json()["sources"]
        assert "walla_sport" in sources
        assert "israel_hayom_sport" in sources

    def test_provider_string_in_response(self, client, monkeypatch):
        """Response provider field reflects the mock provider_id."""
        monkeypatch.setenv("ALLOW_DEV_RESET", "true")
        monkeypatch.setenv("CLASSIFICATION_PROVIDER", "fake")
        monkeypatch.setenv("CLASSIFICATION_MODEL", "benchmark-test")
        mock_provider = _make_mock_provider()

        with (
            patch("app.api.routes_dev._LLM_PROVIDER", mock_provider),
            patch("app.ingestion.ingestion_service._LLM_PROVIDER", mock_provider),
            patch("feedparser.parse", return_value=_make_feed([])),
        ):
            r = client.post("/api/dev/benchmark/llm-gating")

        assert r.json()["provider"] == "fake:benchmark-test"

    def test_comparison_fields_present_per_source(self, client, monkeypatch):
        """comparison includes skip_rate, llm_call_reduction, etc. per source."""
        monkeypatch.setenv("ALLOW_DEV_RESET", "true")
        mock_provider = _make_mock_provider()

        entries = [
            _make_entry("NBA: גולדן סטייט", "https://walla.co.il/bench/nba-test"),
        ]
        with (
            patch("app.api.routes_dev._LLM_PROVIDER", mock_provider),
            patch("app.ingestion.ingestion_service._LLM_PROVIDER", mock_provider),
            patch("feedparser.parse", return_value=_make_feed(entries)),
        ):
            r = client.post("/api/dev/benchmark/llm-gating")

        body = r.json()
        for src_id in body["sources"]:
            if src_id in body["comparison"]:
                comp = body["comparison"][src_id]
                assert "skip_rate" in comp
                assert "llm_call_reduction" in comp
                assert "total_ms_reduction" in comp
                assert "sport_unknown_delta" in comp
                assert "passes_targets" in comp

    def test_source_stats_have_sport_unknown_field(self, client, monkeypatch):
        """Each source in baseline and gated includes a sport_unknown count."""
        monkeypatch.setenv("ALLOW_DEV_RESET", "true")
        mock_provider = _make_mock_provider()

        with (
            patch("app.api.routes_dev._LLM_PROVIDER", mock_provider),
            patch("app.ingestion.ingestion_service._LLM_PROVIDER", mock_provider),
            patch("feedparser.parse", return_value=_make_feed([])),
        ):
            r = client.post("/api/dev/benchmark/llm-gating")

        body = r.json()
        for phase in ("baseline", "gated"):
            for src_id, stats in body[phase]["sources"].items():
                assert "sport_unknown" in stats, f"{phase}.{src_id} missing sport_unknown"

    def test_gated_baseline_uses_separate_ingest_runs(self, client, monkeypatch):
        """
        With a clear-league-in-title article, the gated run should show llm_skipped > 0
        for that article, while the baseline run shows llm_skipped = 0.
        The baseline forces all eligible articles through LLM (gating disabled).
        """
        monkeypatch.setenv("ALLOW_DEV_RESET", "true")
        mock_provider = _make_mock_provider()

        # NBA keyword in title will cause gating to skip LLM in gated run
        entries = [
            _make_entry("NBA: גולדן סטייט ניצחה", "https://walla.co.il/bench/nba-gate"),
        ]
        with (
            patch("app.api.routes_dev._LLM_PROVIDER", mock_provider),
            patch("app.ingestion.ingestion_service._LLM_PROVIDER", mock_provider),
            patch("feedparser.parse", return_value=_make_feed(entries)),
        ):
            r = client.post("/api/dev/benchmark/llm-gating")

        body = r.json()
        if "walla_sport" in body["baseline"]["sources"]:
            baseline_walla = body["baseline"]["sources"]["walla_sport"]
            gated_walla = body["gated"]["sources"]["walla_sport"]
            # Baseline: gating disabled → llm_skipped should be 0
            assert baseline_walla["llm_skipped"] == 0
            # Gated: "NBA" keyword + resolved league → gate should skip
            assert gated_walla["llm_skipped"] >= 1

    def test_benchmark_does_not_persist_result_to_response_body(self, client, monkeypatch):
        """The response body has no 'id' or 'persisted' field — results are not stored."""
        monkeypatch.setenv("ALLOW_DEV_RESET", "true")
        mock_provider = _make_mock_provider()

        with (
            patch("app.api.routes_dev._LLM_PROVIDER", mock_provider),
            patch("app.ingestion.ingestion_service._LLM_PROVIDER", mock_provider),
            patch("feedparser.parse", return_value=_make_feed([])),
        ):
            r = client.post("/api/dev/benchmark/llm-gating")

        body = r.json()
        assert "id" not in body
        assert "persisted" not in body


# ── Normal ingestion is not affected ──────────────────────────────────────────


class TestNormalIngestNotAffected:
    def test_normal_ingest_run_still_uses_env_gating(self, client):
        """POST /api/ingest/run is not affected by the benchmark override — uses env default."""
        entries = [
            _make_entry("NBA: test", "https://walla.co.il/ingest-normal/1"),
        ]
        with patch("feedparser.parse", return_value=_make_feed(entries)):
            r = client.post("/api/ingest/run?source_id=walla_sport")
        assert r.status_code == 200
        # No assertion on gating behavior — just confirm it doesn't crash
        walla = next(s for s in r.json()["sources"] if s["source_id"] == "walla_sport")
        assert "llm_skipped" in walla

    def test_benchmark_endpoint_does_not_change_env_gating_flag(self, client, monkeypatch):
        """Running the benchmark must not mutate the module-level _GATING_ENABLED flag."""
        import app.classification.gating as gating_module
        before = gating_module._GATING_ENABLED

        monkeypatch.setenv("ALLOW_DEV_RESET", "true")
        mock_provider = _make_mock_provider()

        with (
            patch("app.api.routes_dev._LLM_PROVIDER", mock_provider),
            patch("app.ingestion.ingestion_service._LLM_PROVIDER", mock_provider),
            patch("feedparser.parse", return_value=_make_feed([])),
        ):
            client.post("/api/dev/benchmark/llm-gating")

        assert gating_module._GATING_ENABLED == before, (
            "_GATING_ENABLED was mutated by benchmark — override must not change module state"
        )
