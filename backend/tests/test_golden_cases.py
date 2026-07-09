"""Golden-15 reliability regression suite (issue #59; evidence: issue #58 /
docs/CLASSIFICATION_RELIABILITY_INVESTIGATION.md §3).

Seventeen real production articles (15 investigation cases + the C2 sibling and
the C5 walla variant) replayed through the REAL ingestion pipeline
(``ingestion_service._normalise``: classify → gate → recorded-LLM merge →
enrichment → ArticleFacts → post-facts event validation) and scored with the
REAL Preference V2 engine for both seed profiles. No network, no DB: inputs and
the recorded LLM proposals live in ``tests/fixtures/golden_cases.json``.

Contract per case ``status``:

- ``positive`` — one test asserts BOTH the exact ``pinned`` behavior (drift
  alarm) and the looser ``desired`` behavioral contract. These must never
  regress.
- ``failure`` — TWO tests:
  * ``test_pinned_current_behavior`` asserts today's (wrong) behavior exactly.
    It exists so that any unplanned behavior change fails loudly BEFORE the
    owning fix issue lands.
  * ``test_desired_contract`` asserts the corrected behavioral contract and is
    ``xfail(strict=True)`` — while the defect exists it xfails; the moment
    behavior changes it XPASSes and strict mode fails the suite, forcing the
    fixing PR to flip the case.

Flip procedure for a fixing PR (issues #60/#61/#62): set the case's
``status`` to ``positive`` and replace its ``pinned`` block with the new
actual behavior (keep ``desired`` as the contract). Do not delete cases.

Expectation keys support three forms: exact (``"event_type": "signing"``),
negative (``"event_type__not": "title_win"``), and membership
(``"guy__in": ["feed", "high_feed"]``).
"""

import json
from pathlib import Path

import pytest

from app.classification.llm_result import LLMClassificationResult
from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "golden_cases.json"
_FIXTURE = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
CASES = {c["case"]: c for c in _FIXTURE["cases"]}

_PROFILES = {p.user_id: p for p in SEED_PROFILES}


class _ReplayProvider:
    """LLM provider that replays the recorded proposal for this case.

    can_classify=True so the real gate logic runs; if the gate decides to call
    the LLM for a case with no recorded proposal, the replay is out of sync
    with reality and the test must fail loudly rather than fall back.
    """

    can_classify = True
    last_failure_was_connect_error = False
    provider_id = "golden-replay"

    def __init__(self, proposal):
        self._proposal = proposal

    def classify_title(self, title, language, subtitle=None):
        if self._proposal is None:
            raise AssertionError(
                "gate called the LLM but the golden fixture has no recorded "
                "proposal for this case — pipeline gating behavior changed"
            )
        return LLMClassificationResult(**self._proposal)


def _run_case(case: dict, monkeypatch):
    cfg = get_source_config(case["source_id"])
    assert cfg is not None, f"unknown source {case['source_id']}"
    monkeypatch.setattr(
        ingestion_service, "_LLM_PROVIDER", _ReplayProvider(case["llm_proposal"])
    )
    item = RawSourceItem(
        source_id=case["source_id"],
        url=case["url"],
        title=case["title"],
        published_at=None,
        summary=case["subtitle"],
    )
    article, _llm_ms, _gate = ingestion_service._normalise(item, cfg)
    guy = score_article_v2(article, _PROFILES["guy"]).decision
    deni = score_article_v2(article, _PROFILES["casual_deni_fan"]).decision
    return article, guy, deni


def _actual_fields(article, guy, deni) -> dict:
    return {
        "sport": article.sport,
        "league": article.league,
        "entities": list(article.entities or []),
        "entity_ids": list(article.entity_ids or []),
        "event_type": article.event_type,
        "event_certainty": article.event_certainty,
        "importance": article.importance,
        "primary_competition": article.primary_competition,
        "classified_by": article.classified_by,
        "guy": guy,
        "deni": deni,
    }


def _assert_expectations(actual: dict, expected: dict, case_id: str, block: str):
    for key, want in expected.items():
        if key.endswith("__not"):
            field = key[: -len("__not")]
            assert actual[field] != want, (
                f"{case_id} [{block}] {field} must not be {want!r} "
                f"(actual: {actual[field]!r})"
            )
        elif key.endswith("__in"):
            field = key[: -len("__in")]
            assert actual[field] in want, (
                f"{case_id} [{block}] {field}={actual[field]!r} not in {want!r}"
            )
        else:
            assert actual[key] == want, (
                f"{case_id} [{block}] {key}={actual[key]!r}, expected {want!r}"
            )


_ALL_IDS = sorted(CASES)
_FAILURE_IDS = sorted(c for c, v in CASES.items() if v["status"] == "failure")
_POSITIVE_IDS = sorted(c for c, v in CASES.items() if v["status"] == "positive")


@pytest.mark.parametrize("case_id", _ALL_IDS)
def test_pinned_current_behavior(case_id, monkeypatch):
    """Exact pin of current behavior — the unplanned-drift alarm (all cases)."""
    case = CASES[case_id]
    article, guy, deni = _run_case(case, monkeypatch)
    _assert_expectations(_actual_fields(article, guy, deni), case["pinned"], case_id, "pinned")


@pytest.mark.parametrize("case_id", _POSITIVE_IDS)
def test_positive_contract(case_id, monkeypatch):
    """The behavioral contract for cases that are already correct."""
    case = CASES[case_id]
    article, guy, deni = _run_case(case, monkeypatch)
    _assert_expectations(_actual_fields(article, guy, deni), case["desired"], case_id, "desired")


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param(
            cid,
            marks=pytest.mark.xfail(
                strict=True,
                reason=f"known reliability defect — fix owner {CASES[cid]['fix_owner']} "
                f"(flip this case to status=positive when the fix lands)",
            ),
        )
        for cid in _FAILURE_IDS
    ],
)
def test_desired_contract(case_id, monkeypatch):
    """The corrected behavioral contract — strict-xfail until the owning fix lands."""
    case = CASES[case_id]
    article, guy, deni = _run_case(case, monkeypatch)
    _assert_expectations(_actual_fields(article, guy, deni), case["desired"], case_id, "desired")


def test_deni_fan_fully_isolated(monkeypatch):
    """casual_deni_fan sees none of the 17 cases — isolation is a standing invariant."""
    for case_id in _ALL_IDS:
        _, _, deni = _run_case(CASES[case_id], monkeypatch)
        assert deni == "hidden", f"{case_id}: casual_deni_fan must stay hidden, got {deni}"


def test_fixture_shape():
    """Fixture sanity: every case carries the fields the harness depends on."""
    assert len(CASES) == 17
    for case_id, case in CASES.items():
        for field in ("article_id", "source_id", "url", "title", "status",
                      "fix_owner", "pinned", "desired"):
            assert field in case, f"{case_id} missing {field}"
        assert case["status"] in ("positive", "failure")
        assert case["pinned"]["deni"] == "hidden"
