"""The census gate's rules-only rerun must never reach the LLM (#254 review).

`ingestion_service._LLM_PROVIDER` is built from the environment at IMPORT time,
and the owner's backend/.env enables a hosted provider. Setting
CLASSIFICATION_PROVIDER=disabled inside the rerun is therefore too late when
the module was already imported. The rerun must pass `llm_available=False`
so the LLM branch is unreachable whatever was configured at import.
"""

import logging
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion import ingestion_service  # noqa: E402
from scripts.feed_ground_truth import _rerun_articles  # noqa: E402


class _ArmedProvider:
    """A provider that is configured and would classify, and must never be asked."""

    can_classify = True
    provider_id = "armed-test-provider"

    def classify_title(self, *args, **kwargs):  # pragma: no cover - reaching it is the failure
        raise AssertionError("the rules-only rerun called the LLM")


def _stored(title):
    return SimpleNamespace(
        id="rss_test_row",
        source="walla_sport",
        url="https://sports.walla.co.il/item/1",
        title=title,
        subtitle="",
        published_at=None,
    )


def test_rerun_never_consults_the_llm_even_when_a_provider_was_armed_at_import(monkeypatch):
    consulted = []
    monkeypatch.setattr(ingestion_service, "_LLM_PROVIDER", _ArmedProvider())
    monkeypatch.setattr(
        ingestion_service, "should_call_llm_for_article",
        lambda **kwargs: consulted.append(kwargs) or (_ for _ in ()).throw(AssertionError("gate consulted")),
    )
    monkeypatch.setenv("CLASSIFICATION_PROVIDER", "openai_compat")
    monkeypatch.setenv("TRANSLATION_PROVIDER", "disabled")

    out = _rerun_articles([_stored("מכבי תל אביב ניצחה את הפועל בדרבי")])

    assert consulted == []
    assert [a.id for a in out] == ["rss_test_row"]


def test_rerun_leaves_logging_enabled_for_the_rest_of_the_process(monkeypatch):
    monkeypatch.setenv("CLASSIFICATION_PROVIDER", "disabled")
    monkeypatch.setenv("TRANSLATION_PROVIDER", "disabled")
    _rerun_articles([_stored("מכבי תל אביב ניצחה את הפועל בדרבי")])
    assert logging.getLogger("x").isEnabledFor(logging.CRITICAL)
    assert logging.root.manager.disable == logging.NOTSET
