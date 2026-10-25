"""A preview answers 'disabled' to provider-calling operations BEFORE any provider code runs.

scripts/preview.ps1 sets PROVIDER_CALLS_DISABLED=true. The dead outbound proxy stays as a
second layer, but an operator must see an explicit refusal, not a cycle that "fetched 0"
(#365) or a results sync full of ConnectErrors. Spies prove the orchestration and the results
provider are never entered; nothing here touches the network.
"""
from unittest.mock import MagicMock

import pytest

ROUTES = (
    ("/api/ingest/run", "app.api.routes_ingest.orchestrate_cycle"),
    ("/api/ingest/scheduler/run-now", "app.api.routes_ingest.orchestrate_cycle"),
    ("/api/results/sync", "app.api.routes_results.sync_results"),
)


@pytest.mark.parametrize("path,target", ROUTES)
def test_refused_before_any_provider_code_runs(admin_client, monkeypatch, path, target):
    monkeypatch.setenv("PROVIDER_CALLS_DISABLED", "true")
    monkeypatch.setenv("RESULTS_ENABLED", "true")
    spy = MagicMock(side_effect=AssertionError("provider path entered"))
    monkeypatch.setattr(target, spy)

    r = admin_client.post(path)

    assert r.status_code == 503
    assert r.json()["detail"]["status"] == "disabled"
    assert "PROVIDER_CALLS_DISABLED" in r.json()["detail"]["reason"]
    spy.assert_not_called()


def test_results_sync_runs_when_the_flag_is_off(admin_client, monkeypatch):
    monkeypatch.delenv("PROVIDER_CALLS_DISABLED", raising=False)
    monkeypatch.setenv("RESULTS_ENABLED", "true")
    spy = MagicMock(return_value={"status": "ok"})
    monkeypatch.setattr("app.api.routes_results.sync_results", spy)

    r = admin_client.post("/api/results/sync")

    assert r.status_code == 200
    spy.assert_called_once()


def test_a_regular_user_is_still_refused_by_authorization_first(user_client, monkeypatch):
    monkeypatch.setenv("PROVIDER_CALLS_DISABLED", "true")
    assert user_client.post("/api/results/sync").status_code in (401, 403)
