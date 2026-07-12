"""
Corpus DB protection (issue #106).

The real corpus (backend/data/signal_sports.db) is not in git and cannot be
restored. On 2026-07-12 it was reset from 404 RSS articles to 0 by a dev endpoint
whose only protection was ALLOW_DEV_RESET=true — which was set, while
DATABASE_URL pointed at the corpus.

These tests lock the guard that replaced that boolean-only protection:
- the LLM gating benchmark can NEVER touch the corpus (no override exists);
- reset-rss-data needs a SECOND, corpus-specific opt-in;
- non-corpus databases (the test DB, a benchmark copy) are unaffected.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.db.corpus_protection import (
    CANONICAL_CORPUS_PATH,
    corpus_reset_opt_in,
    is_protected_corpus_db,
)


# ── Protected-path resolution ─────────────────────────────────────────────────

class TestProtectedPathResolution:
    def test_relative_corpus_url_is_protected(self):
        # This is the exact form used in backend/.env — the one that lost the corpus.
        assert is_protected_corpus_db("sqlite:///./data/signal_sports.db") is True

    def test_relative_corpus_url_without_dot_is_protected(self):
        assert is_protected_corpus_db("sqlite:///data/signal_sports.db") is True

    def test_absolute_corpus_url_is_protected(self):
        url = f"sqlite:///{CANONICAL_CORPUS_PATH.as_posix()}"
        assert is_protected_corpus_db(url) is True

    def test_benchmark_copy_is_not_protected(self):
        assert is_protected_corpus_db("sqlite:///./data/benchmark_copy.db") is False

    def test_backup_file_is_not_protected(self):
        # A copy is a legitimate destructive-op target.
        assert is_protected_corpus_db(
            "sqlite:///./data/signal_sports.pre_reliability_backfill.backup.db"
        ) is False

    def test_temp_test_db_is_not_protected(self):
        assert is_protected_corpus_db("sqlite:////tmp/pytest-xyz/test.db") is False

    def test_in_memory_is_not_protected(self):
        assert is_protected_corpus_db("sqlite:///:memory:") is False

    def test_non_sqlite_url_is_not_protected(self):
        assert is_protected_corpus_db("postgresql://localhost/signal") is False

    def test_empty_url_is_not_protected(self):
        assert is_protected_corpus_db("") is False

    def test_the_running_test_suite_is_not_on_the_corpus(self):
        # Sanity: conftest points DATABASE_URL at a temp DB. If this ever fails,
        # the whole suite is running against the real corpus — stop everything.
        assert is_protected_corpus_db() is False


class TestCorpusResetOptIn:
    def test_defaults_to_false(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ALLOW_CORPUS_DB_RESET", None)
            assert corpus_reset_opt_in() is False

    def test_true_when_explicitly_set(self):
        with patch.dict(os.environ, {"ALLOW_CORPUS_DB_RESET": "true"}):
            assert corpus_reset_opt_in() is True

    def test_allow_dev_reset_does_not_imply_corpus_opt_in(self):
        # The core lesson of the incident: one boolean is not authority to destroy
        # the corpus. ALLOW_DEV_RESET must NOT satisfy the corpus opt-in.
        with patch.dict(os.environ, {"ALLOW_DEV_RESET": "true"}):
            os.environ.pop("ALLOW_CORPUS_DB_RESET", None)
            assert corpus_reset_opt_in() is False


# ── Route-level refusals ──────────────────────────────────────────────────────

_GUARD = "app.api.routes_dev.is_protected_corpus_db"
_OPT_IN = "app.api.routes_dev.corpus_reset_opt_in"


class TestBenchmarkNeverTouchesCorpus:
    def test_benchmark_refuses_on_corpus_db_even_with_dev_reset(self, admin_client):
        # The #65 landmine: the benchmark resets RSS data twice per run BY DESIGN.
        with patch.dict(os.environ, {"ALLOW_DEV_RESET": "true"}), \
             patch(_GUARD, return_value=True):
            r = admin_client.post("/api/dev/benchmark/llm-gating")
        assert r.status_code == 409
        assert "protected article corpus" in r.json()["detail"]

    def test_benchmark_refuses_on_corpus_db_even_with_corpus_opt_in(self, admin_client):
        # There is NO override for the benchmark — it must always use a copy.
        with patch.dict(os.environ, {
            "ALLOW_DEV_RESET": "true",
            "ALLOW_CORPUS_DB_RESET": "true",
        }), patch(_GUARD, return_value=True):
            r = admin_client.post("/api/dev/benchmark/llm-gating")
        assert r.status_code == 409

    def test_benchmark_error_names_the_copy_workaround(self, admin_client):
        with patch.dict(os.environ, {"ALLOW_DEV_RESET": "true"}), \
             patch(_GUARD, return_value=True):
            r = admin_client.post("/api/dev/benchmark/llm-gating")
        assert "benchmark_copy.db" in r.json()["detail"]


class TestResetRequiresSecondOptIn:
    def test_reset_refuses_on_corpus_with_only_allow_dev_reset(self, admin_client):
        # Exactly the configuration that destroyed the corpus.
        with patch.dict(os.environ, {"ALLOW_DEV_RESET": "true"}), \
             patch(_GUARD, return_value=True), patch(_OPT_IN, return_value=False):
            r = admin_client.post("/api/dev/reset-rss-data")
        assert r.status_code == 409
        assert "ALLOW_CORPUS_DB_RESET" in r.json()["detail"]

    def test_reset_allowed_on_corpus_with_both_opt_ins(self, admin_client):
        with patch.dict(os.environ, {"ALLOW_DEV_RESET": "true"}), \
             patch(_GUARD, return_value=True), patch(_OPT_IN, return_value=True):
            r = admin_client.post("/api/dev/reset-rss-data")
        assert r.status_code == 200

    def test_reset_unaffected_on_non_corpus_db(self, admin_client):
        # The normal dev/test path must keep working with just ALLOW_DEV_RESET.
        with patch.dict(os.environ, {"ALLOW_DEV_RESET": "true"}), \
             patch(_GUARD, return_value=False):
            r = admin_client.post("/api/dev/reset-rss-data")
        assert r.status_code == 200

    def test_reset_still_403_when_dev_reset_disabled(self, admin_client):
        # The original guard must survive: disabled dev reset still wins first.
        with patch.dict(os.environ, {"ALLOW_DEV_RESET": "false"}):
            r = admin_client.post("/api/dev/reset-rss-data")
        assert r.status_code == 403
