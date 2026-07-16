"""The in-process scheduler retirement lock (PR 13 → M7-2 #148 → M7-4 #150).

History: PR 13 put a polling loop + process-local lock inside the FastAPI
lifespan. M7-2 retired the loop (the dedicated worker owns cadence). M7-4
deleted the leftover in-memory status mirror entirely — the legacy status
endpoint now reads the same durable rows as /api/scheduler/health.

What this file locks: the API process has NO scheduler machinery at all.
A second polling loop must stay impossible by construction.
"""

import inspect

import pytest


class TestInProcessSchedulerIsRetired:
    def test_the_scheduler_module_is_gone(self):
        with pytest.raises(ModuleNotFoundError):
            import app.ingestion.scheduler  # noqa: F401

    def test_app_lifespan_does_not_reference_a_scheduler(self):
        import app.main as main_module
        source = inspect.getsource(main_module)
        assert "start_scheduler" not in source
        assert "scheduler_state" not in source

    def test_no_route_imports_process_local_scheduler_state(self):
        import app.api.routes_ingest as routes
        source = inspect.getsource(routes)
        assert "scheduler_state" not in source
