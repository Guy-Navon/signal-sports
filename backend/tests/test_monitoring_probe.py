"""Monitoring pings (app/monitoring.py) and the fetch-only source probe
(scripts/source_probe.py). Fake HTTP and fake adapters only: no test pings a
real monitor or fetches a real source.
"""

import importlib.util
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import monitoring

BACKEND = Path(__file__).resolve().parents[1]
CYCLE_URL = "https://hc.example.test/ping/cycle-uuid-SECRET"
SOURCES_URL = "https://hc.example.test/ping/sources-uuid"
FRESH_URL = "https://hc.example.test/ping/fresh-uuid"


@dataclass
class _Result:
    source_id: str
    fetched: int = 0
    inserted: int = 0
    errors: list = field(default_factory=list)


def _outcome(status="succeeded", results=None, skipped=False, error=None):
    return SimpleNamespace(cycle_id="cycle_test", status=status, skipped=skipped,
                           source_results=results or [], error_summary=error)


@pytest.fixture
def pings(monkeypatch):
    sent = []

    def fake_post(url, content=b"", timeout=None):
        sent.append({"url": url, "body": content.decode("utf-8"), "timeout": timeout})
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setenv("DEPLOY_ENV", "hosted")
    return sent


@pytest.fixture
def all_checks(monkeypatch):
    monkeypatch.setenv("MONITOR_CYCLE_URL", CYCLE_URL)
    monkeypatch.setenv("MONITOR_SOURCES_URL", SOURCES_URL)
    monkeypatch.setenv("MONITOR_FRESH_URL", FRESH_URL)


# ── Pings ─────────────────────────────────────────────────────────────────────

def test_nothing_configured_sends_nothing(pings):
    assert monitoring.report_cycle(_outcome(results=[_Result("walla_sport", 30, 2)])) == {
        "cycle": None, "sources": None, "fresh": None}
    assert pings == []


def test_good_cycle_pings_all_three(pings, all_checks):
    sent = monitoring.report_cycle(_outcome(results=[_Result("walla_sport", 30, 2), _Result("ynet_sport", 20, 0)]))
    assert sent == {"cycle": True, "sources": True, "fresh": True}
    assert [p["url"] for p in pings] == [CYCLE_URL, SOURCES_URL, FRESH_URL]
    assert "walla_sport: fetched=30 inserted=2 errors=0" in pings[0]["body"]
    assert all(p["timeout"] <= 10 for p in pings)


def test_quiet_cycle_keeps_sources_ok_but_not_fresh(pings, all_checks):
    sent = monitoring.report_cycle(_outcome(results=[_Result("walla_sport", 30, 0)]))
    assert sent == {"cycle": True, "sources": True, "fresh": None}
    assert [p["url"] for p in pings] == [CYCLE_URL, SOURCES_URL]


def test_all_sources_failing_fails_sources(pings, all_checks):
    sent = monitoring.report_cycle(_outcome(
        status="succeeded_with_warnings",
        results=[_Result("walla_sport", 0, 0, ["DNS"]), _Result("ynet_sport", 0, 0, ["timeout"])]))
    assert sent["cycle"] is True and sent["sources"] is True and sent["fresh"] is None
    assert pings[1]["url"] == SOURCES_URL + "/fail"


def test_failed_cycle_pings_fail(pings, all_checks):
    monitoring.report_cycle(_outcome(status="failed", error="OperationalError: locked"))
    assert pings[0]["url"] == CYCLE_URL + "/fail"
    assert "OperationalError" in pings[0]["body"]
    assert pings[1]["url"] == SOURCES_URL + "/fail"


def test_skipped_tick_sends_nothing(pings, all_checks):
    monitoring.report_cycle(_outcome(status="skipped_active_run", skipped=True))
    assert pings == []


def test_dev_mode_never_pings(pings, all_checks, monkeypatch):
    monkeypatch.setenv("DEPLOY_ENV", "dev")
    assert monitoring.ping("cycle") is False
    assert pings == []


def test_ping_errors_never_raise_or_log_the_url(monkeypatch, all_checks, caplog):
    monkeypatch.setenv("DEPLOY_ENV", "hosted")

    def boom(url, content=b"", timeout=None):
        raise httpx.ConnectError(f"cannot reach {url}")

    monkeypatch.setattr(httpx, "post", boom)
    caplog.set_level(logging.WARNING)
    assert monitoring.ping("cycle") is False
    assert "SECRET" not in caplog.text and "cycle" in caplog.text


def test_non_2xx_is_not_success(monkeypatch, all_checks):
    monkeypatch.setenv("DEPLOY_ENV", "hosted")
    monkeypatch.setattr(httpx, "post", lambda url, content=b"", timeout=None:
                        httpx.Response(404, request=httpx.Request("POST", url)))
    assert monitoring.ping("cycle") is False


def test_worker_tick_reports_the_cycle(pings, all_checks, monkeypatch):
    from app import worker
    from app.ingestion import orchestration

    outcome = _outcome(results=[_Result("walla_sport", 5, 1)])
    outcome.started_at = outcome.finished_at = datetime.now(tz=timezone.utc)
    monkeypatch.setattr(orchestration, "orchestrate_cycle", lambda trigger: outcome)
    worker.run_tick(worker.read_scheduler_config(), "scheduled")
    assert [p["url"] for p in pings] == [CYCLE_URL, SOURCES_URL, FRESH_URL]


def test_dev_startup_refuses_monitor_urls(monkeypatch):
    from app.core.deploy_mode import UnsafeDeployConfig, validate_deploy_startup_config

    monkeypatch.setenv("DEPLOY_ENV", "dev")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("MONITOR_BACKUP_URL", "https://hc.example.test/x")
    with pytest.raises(UnsafeDeployConfig, match="MONITOR_BACKUP_URL"):
        validate_deploy_startup_config()


# ── Source probe ─────────────────────────────────────────────────────────────

@pytest.fixture
def probe():
    spec = importlib.util.spec_from_file_location("source_probe_under_test", BACKEND / "scripts" / "source_probe.py")
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve string annotations through sys.modules.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def _items(n, *, hours_old=1.0, title="מכבי ניצחה במשחק", host="sports.walla.co.il", dated=True):
    from app.ingestion.adapters.base import RawSourceItem

    return [RawSourceItem(source_id="walla_sport", url=f"https://{host}/item/{i}", title=title,
                          published_at=(NOW - timedelta(hours=hours_old + i)) if dated else None)
            for i in range(n)]


def _with_adapter(monkeypatch, probe, items=None, error_log=None):
    class FakeAdapter:
        def fetch(self):
            if error_log:
                logging.getLogger("app.ingestion.adapters.fake").error(error_log)
            return list(items or [])

    monkeypatch.setattr(probe, "build_adapter", lambda cfg: FakeAdapter())


def _walla(probe):
    return next(c for c in probe.RSS_SOURCES if c.source_id == "walla_sport")


def test_probe_ok(probe, monkeypatch):
    _with_adapter(monkeypatch, probe, _items(25))
    report = probe.probe_source(_walla(probe), min_items=1, max_age_hours=24, now=NOW, diagnose=False)
    assert report.verdict == "ok", report.problems
    assert report.items == 25 and report.with_date == 25 and report.in_language == 25
    assert report.newest_age_hours == 1.0 and len(report.examples) == 3


@pytest.mark.parametrize("items,needle", [
    (_items(5, hours_old=30), "newest item is 30.0 h old"),
    (_items(5, title="English only headline"), "titles are in Hebrew"),
    (_items(5, host="evil.example"), "links leave walla.co.il"),
    (_items(5, dated=False), "carry a date"),
])
def test_probe_judges_content_not_status(probe, monkeypatch, items, needle):
    _with_adapter(monkeypatch, probe, items)
    report = probe.probe_source(_walla(probe), min_items=1, max_age_hours=24, now=NOW, diagnose=False)
    assert report.verdict == "degraded"
    assert any(needle in p for p in report.problems), report.problems


def test_probe_captures_adapter_errors(probe, monkeypatch):
    _with_adapter(monkeypatch, probe, [], error_log="RSS fetch failed for walla_sport: Name or service not known")
    report = probe.probe_source(_walla(probe), min_items=1, max_age_hours=24, now=NOW, diagnose=False)
    assert report.verdict == "error"
    assert "Name or service not known" in report.adapter_errors[0]


def test_probe_empty_without_errors(probe, monkeypatch):
    _with_adapter(monkeypatch, probe, [])
    report = probe.probe_source(_walla(probe), min_items=1, max_age_hours=24, now=NOW, diagnose=False)
    assert report.verdict == "empty"


def test_probe_reports_http_status(probe, monkeypatch):
    _with_adapter(monkeypatch, probe, [])
    monkeypatch.setattr(probe, "diagnose_endpoint",
                        lambda url: probe.EndpointCheck(url=url, http_status=403, content_type="text/html", bytes=10))
    report = probe.probe_source(_walla(probe), min_items=1, max_age_hours=24, now=NOW)
    assert report.verdict == "error"
    assert any("HTTP 403" in p for p in report.problems)


def test_probe_main_exit_codes(probe, monkeypatch, capsys):
    monkeypatch.setattr(probe, "diagnose_endpoint",
                        lambda url: probe.EndpointCheck(url=url, http_status=200, content_type="application/rss+xml", bytes=900))
    _with_adapter(monkeypatch, probe, _items(3, hours_old=0.5))
    monkeypatch.setattr(probe, "datetime", SimpleNamespace(now=lambda tz=None: NOW))
    assert probe.main(["--source", "walla_sport"]) == 0
    _with_adapter(monkeypatch, probe, [])
    assert probe.main(["--source", "walla_sport", "--json"]) == 1
    assert '"verdict": "empty"' in capsys.readouterr().out


def test_probe_selects_the_hebrew_sources_by_default(probe):
    ids = [c.source_id for c in probe.select_sources([], include_english=False)]
    assert ids == list(probe.HEBREW_SOURCES)
    with pytest.raises(SystemExit):
        probe.select_sources(["nope"], include_english=False)


def test_probe_never_imports_the_database():
    code = ("import importlib.util, sys; "
            "spec = importlib.util.spec_from_file_location('p', 'scripts/source_probe.py'); "
            "m = importlib.util.module_from_spec(spec); sys.modules['p'] = m; spec.loader.exec_module(m); "
            "print('app.db.database' in sys.modules)")
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    proc = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "False"
