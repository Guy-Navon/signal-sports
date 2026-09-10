"""The feed-quality gate must fail in BOTH directions (issue #189).

These tests exercise `app.qa.feed_quality_gate` with synthetic score reports and
therefore run anywhere, including CI, which has no corpus. That split is
deliberate and is the whole reason the comparison logic is a pure function:

- the **gate** (`scripts/feed_ground_truth.py gate`) needs the real corpus DB and
  is local-only;
- the **rules the gate enforces** are pure, and are proven here.

The central property under test is directionality. A single accuracy number
cannot express it: `casual_deni_fan` scores 98% exact agreement while hiding
98.3% of the corpus. So every test below asserts on one specific direction of
movement, and the pair `test_show_precision_regression_fails` /
`test_recall_regression_fails` is the acceptance evidence for #189.
"""

import json
from pathlib import Path

import pytest

from app.qa import feed_quality_gate as gate


# ── synthetic fixtures ────────────────────────────────────────────────────────


def _profile_block(
    *,
    rated=185,
    shown=110,
    worth_showing=108,
    false_hide=0.1941,
    false_show=0.0035,
    push_rated=17,
    push_agreed=7,
):
    precision = round(worth_showing / shown, 3) if shown else None
    push_precision = round(push_agreed / push_rated, 3) if push_rated else None
    return {
        "rated": rated,
        "sample_counts": {"rated": rated},
        "shown_precision": {
            "shown": shown,
            "worth_showing": worth_showing,
            "precision": precision,
            "note": "census of the visible tiers; not an estimate",
        },
        "population_estimates": {
            "exact": 0.7233,
            "false_show": false_show,
            "false_hide": false_hide,
            "over_ranked": 0.0546,
            "under_ranked": 0.0245,
        },
        "push_precision": {
            "rated": push_rated,
            "agreed_push_worthy": push_agreed,
            "precision": push_precision,
        },
        "disagreements": [],
    }


def _report(guy=None, deni=None):
    return {
        "meta": {"engine": "v2", "corpus_articles": 1427},
        "profiles": {
            "guy": guy if guy is not None else _profile_block(),
            "casual_deni_fan": deni
            if deni is not None
            else _profile_block(
                rated=97, shown=24, worth_showing=22, false_hide=0.0076,
                false_show=0.0014, push_rated=0, push_agreed=0,
            ),
        },
    }


def _decisions(guy_overrides=None, deni_overrides=None):
    guy = {f"a{i}": "hidden" for i in range(185)}
    guy.update(guy_overrides or {})
    deni = {f"d{i}": "hidden" for i in range(97)}
    deni.update(deni_overrides or {})
    return {"guy": guy, "casual_deni_fan": deni}


@pytest.fixture
def baseline():
    return gate.build_baseline(_report(), _decisions())


def _check(verdict, check_id):
    for check in verdict.checks:
        if check.check_id == check_id:
            return check
    raise AssertionError(f"no check {check_id} in {[c.check_id for c in verdict.checks]}")


# ── the control ───────────────────────────────────────────────────────────────


def test_unchanged_run_passes(baseline):
    verdict = gate.evaluate(baseline, _report(), _decisions())
    assert verdict.passed
    assert verdict.blocking == ()
    assert verdict.flips == ()


def test_baseline_stores_per_item_decisions(baseline):
    """Aggregates can net two opposite flips to zero; stored decisions cannot."""
    assert len(baseline["profiles"]["guy"]["decisions"]) == 185
    assert len(baseline["profiles"]["casual_deni_fan"]["decisions"]) == 97


# ── direction 1: losing precision on what is shown ────────────────────────────


def test_show_precision_regression_fails(baseline):
    """ACCEPTANCE (#189): a deliberately injected show-precision regression fails.

    Two of the shown items become unwanted. One item is within slack; two is not.
    """
    verdict = gate.evaluate(
        baseline,
        _report(guy=_profile_block(worth_showing=106)),
        _decisions(),
    )
    assert not verdict.passed
    assert _check(verdict, "guy.shown_precision").passed is False


def test_show_precision_may_lose_exactly_one_item(baseline):
    """The slack that lets a recall fix trade one bad show for several hides."""
    verdict = gate.evaluate(
        baseline,
        _report(guy=_profile_block(worth_showing=107)),
        _decisions(),
    )
    assert _check(verdict, "guy.shown_precision").passed is True


def test_a_feed_that_shows_nothing_is_not_a_precision_win(baseline):
    """Perfect precision over an empty set must not read as a pass."""
    verdict = gate.evaluate(
        baseline,
        _report(guy=_profile_block(shown=0, worth_showing=0)),
        _decisions(),
    )
    assert _check(verdict, "guy.shown_precision").passed is False


# ── direction 2: losing recall ────────────────────────────────────────────────


def test_recall_regression_fails(baseline):
    """ACCEPTANCE (#189): a deliberately injected recall regression fails.

    False hide is zero-tolerance — it is the failure the epic exists to fix.
    """
    verdict = gate.evaluate(
        baseline,
        _report(guy=_profile_block(false_hide=0.1966)),
        _decisions(),
    )
    assert not verdict.passed
    assert _check(verdict, "guy.false_hide").passed is False


def test_recall_improvement_passes(baseline):
    verdict = gate.evaluate(
        baseline,
        _report(guy=_profile_block(false_hide=0.1500)),
        _decisions(),
    )
    assert verdict.passed
    assert _check(verdict, "guy.false_hide").passed is True


def test_false_hide_has_no_slack(baseline):
    """Even the smallest rise fails: a newly hidden wanted item is a real loss."""
    verdict = gate.evaluate(
        baseline,
        _report(guy=_profile_block(false_hide=0.1942)),
        _decisions(),
    )
    assert _check(verdict, "guy.false_hide").passed is False


# ── push ──────────────────────────────────────────────────────────────────────


def test_push_precision_drop_fails(baseline):
    verdict = gate.evaluate(
        baseline,
        _report(guy=_profile_block(push_rated=17, push_agreed=5)),
        _decisions(),
    )
    assert _check(verdict, "guy.push_precision").passed is False


def test_push_volume_may_not_rise_without_a_precision_gain(baseline):
    """22 pushes at the same quality is the failure CLAUDE.md warns about."""
    verdict = gate.evaluate(
        baseline,
        _report(guy=_profile_block(push_rated=22, push_agreed=9)),
        _decisions(),
    )
    assert _check(verdict, "guy.push_precision").passed is True  # 0.409 within 1-push slack
    assert _check(verdict, "guy.push_volume").passed is False
    assert not verdict.passed


def test_push_volume_may_rise_when_precision_improves(baseline):
    verdict = gate.evaluate(
        baseline,
        _report(guy=_profile_block(push_rated=20, push_agreed=15)),
        _decisions(),
    )
    assert _check(verdict, "guy.push_volume").passed is True
    assert verdict.passed


def test_push_falling_silent_is_reported_not_scored_as_perfect(baseline):
    verdict = gate.evaluate(
        baseline,
        _report(guy=_profile_block(push_rated=0, push_agreed=0)),
        _decisions(),
    )
    check = _check(verdict, "guy.push_precision")
    assert check.passed is True
    assert "undefined rather than perfect" in check.detail


# ── drift on the canary profile ───────────────────────────────────────────────


def test_casual_deni_fan_drift_fails(baseline):
    verdict = gate.evaluate(
        baseline,
        _report(),
        _decisions(deni_overrides={"d3": "feed"}),
    )
    assert not verdict.passed
    assert _check(verdict, "casual_deni_fan.no_drift").passed is False
    assert verdict.flips[0].article_id == "d3"
    assert verdict.flips[0].after == "feed"


def test_guy_drift_is_recorded_but_not_gated(baseline):
    """Guy is the profile changes target; his movement is reported, not blocked."""
    verdict = gate.evaluate(
        baseline,
        _report(),
        _decisions(guy_overrides={"a5": "feed"}),
    )
    assert verdict.passed
    assert [f.article_id for f in verdict.flips] == ["a5"]
    with pytest.raises(AssertionError):
        _check(verdict, "guy.no_drift")


def test_an_article_leaving_the_corpus_counts_as_a_flip(baseline):
    current = _decisions()
    del current["casual_deni_fan"]["d7"]
    verdict = gate.evaluate(baseline, _report(), current)
    assert not verdict.passed
    assert any(f.article_id == "d7" and f.after == "<missing>" for f in verdict.flips)


# ── accepting a regression is an argued act, not a relaxed threshold ──────────


def test_accept_unblocks_a_named_check_and_records_the_reason(baseline):
    verdict = gate.evaluate(
        baseline,
        _report(guy=_profile_block(false_hide=0.1966)),
        _decisions(),
        accepted=["guy.false_hide"],
        accept_reason="mention-vs-subject fix; the cost is argued in #193",
    )
    assert verdict.passed
    check = _check(verdict, "guy.false_hide")
    assert check.passed is False and check.accepted is True
    assert check.blocking is False
    assert "#193" in check.accept_reason


def test_accept_does_not_leak_to_other_checks(baseline):
    verdict = gate.evaluate(
        baseline,
        _report(guy=_profile_block(worth_showing=106, false_hide=0.1966)),
        _decisions(),
        accepted=["guy.false_hide"],
        accept_reason="only the recall cost was argued",
    )
    assert not verdict.passed
    assert [c.check_id for c in verdict.blocking] == ["guy.shown_precision"]


def test_a_stale_accept_fails_the_gate(baseline):
    """An override left behind after its regression is gone is how a gate rots."""
    verdict = gate.evaluate(
        baseline,
        _report(),
        _decisions(),
        accepted=["guy.nonexistent_check"],
        accept_reason="stale",
    )
    assert not verdict.passed
    assert verdict.unknown_accepts == ("guy.nonexistent_check",)


# ── invalid comparisons are errors, not scores ────────────────────────────────


def test_changed_rating_count_is_an_error_not_a_regression(baseline):
    with pytest.raises(gate.GateInputError, match="rating set changed"):
        gate.evaluate(baseline, _report(guy=_profile_block(rated=200)), _decisions())


def test_missing_profile_is_an_error(baseline):
    report = _report()
    del report["profiles"]["casual_deni_fan"]
    with pytest.raises(gate.GateInputError, match="different measurements"):
        gate.evaluate(baseline, report, _decisions())


def test_empty_baseline_is_an_error():
    with pytest.raises(gate.GateInputError, match="no rated profiles"):
        gate.evaluate({"profiles": {}}, _report(), _decisions())


# ── the report must never lead with overall accuracy ──────────────────────────


def test_rendered_verdict_shows_both_directions(baseline):
    verdict = gate.evaluate(baseline, _report(), _decisions())
    text = gate.format_verdict(verdict)
    assert "shown precision" in text
    assert "false hide" in text
    assert "GATE PASSED" in text
    # The metric trap: overall exact-agreement is base-rate dominated and must
    # not appear as a headline number.
    assert "exact" not in text.lower().split("note:")[0]


def test_rendered_verdict_names_the_blocking_checks(baseline):
    verdict = gate.evaluate(
        baseline, _report(guy=_profile_block(false_hide=0.30)), _decisions()
    )
    text = gate.format_verdict(verdict)
    assert "GATE FAILED" in text
    assert "guy.false_hide" in text


# ── the committed baseline must be machine-generated, not hand-tuned ──────────
#
# These run in CI. They cannot verify the NUMBERS (CI has no corpus), but they
# can verify the baseline is internally consistent — which is what a hand-edit
# to make a failing gate pass would break.

_BASELINE_PATH = Path(__file__).resolve().parents[2] / "docs" / "qa" / "n05_gate_baseline.json"


@pytest.fixture(scope="module")
def committed_baseline():
    assert _BASELINE_PATH.exists(), (
        f"{_BASELINE_PATH} is missing. Regenerate deliberately with:\n"
        "  scripts/feed_ground_truth.py gate --update-baseline"
    )
    return json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))


def test_committed_baseline_has_both_profiles(committed_baseline):
    assert set(committed_baseline["profiles"]) == {"guy", "casual_deni_fan"}
    assert committed_baseline["baseline_version"] == gate.BASELINE_VERSION


def test_committed_baseline_guards_the_canary_profile(committed_baseline):
    assert "casual_deni_fan" in committed_baseline["policy"]["drift_must_be_zero"]


@pytest.mark.parametrize("profile_id", ["guy", "casual_deni_fan"])
def test_committed_baseline_ratios_match_their_own_counts(committed_baseline, profile_id):
    """A hand-edited precision would no longer equal worth_showing / shown."""
    p = committed_baseline["profiles"][profile_id]
    assert p["shown_precision"] == pytest.approx(p["worth_showing"] / p["shown"], abs=5e-4)
    if p["push_rated"]:
        assert p["push_precision"] == pytest.approx(p["push_agreed"] / p["push_rated"], abs=5e-4)
    else:
        assert p["push_precision"] is None


@pytest.mark.parametrize("profile_id", ["guy", "casual_deni_fan"])
def test_committed_baseline_stores_one_decision_per_rated_item(committed_baseline, profile_id):
    p = committed_baseline["profiles"][profile_id]
    assert len(p["decisions"]) == p["rated"]
    assert set(p["decisions"].values()) <= {
        "push", "high_feed", "feed", "low_feed", "hidden",
    }


def test_committed_baseline_records_the_two_measured_failures(committed_baseline):
    """Sanity anchors from docs/qa/N05_FEED_GROUND_TRUTH.md.

    Deliberately loose: these assert the baseline still describes the product we
    measured, not exact values (which move when the baseline is legitimately
    regenerated). If either of these trips, the baseline was regenerated against
    a materially different corpus or engine — which needs a human, not a nudge.
    """
    guy = committed_baseline["profiles"]["guy"]
    assert guy["shown_precision"] > 0.9, "shown precision was 97-98%; the feed is not noisy"
    assert guy["false_hide"] > 0.05, "false hide was 19.4%; the open failure is recall"
