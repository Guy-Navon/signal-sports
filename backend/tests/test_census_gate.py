"""The census regression gate (issue #254) must fail in the right direction.

Same split as `test_feed_quality_gate.py`: the gate itself
(`scripts/feed_ground_truth.py gate --census`) needs the corpus DB and is
local-only, while the rules it enforces live in the pure
`app.qa.census_gate` module and are proven here, in CI.

The census differs from N05 in two ways that shape the checks:

- every row is rated (weight 1.0), so recall can be read directly instead of
  through `false_hide`, which the 76% hide base rate dilutes;
- a single owner rating is noisy by about one notch (census #2's blind review:
  28 of 58 large gaps changed, 26 toward the engine), so the disagreement check
  counts only gaps of two notches or more.

The last block runs the acceptance demonstrations on the COMMITTED baseline:
its stored per-article decisions plus the committed census ratings are real
data, and both are in the repository, so CI can replay them without a corpus.
"""

import json
from pathlib import Path

import pytest

from app.qa import census_gate as gate
from app.qa.feed_quality_gate import GateInputError

# ── synthetic census ──────────────────────────────────────────────────────────
#
# (id, owner rating, engine decision). Small, but every relation the checks
# read is present: agreements, false shows and hides, one- and two-notch gaps,
# a correct push, a missed push and an over-pushed row.

_ROWS = (
    [(f"h{i}", "hide", "hidden") for i in range(20)]
    + [(f"f{i}", "feed", "feed") for i in range(6)]
    + [(f"l{i}", "low", "low_feed") for i in range(4)]
    + [(f"g{i}", "high", "high_feed") for i in range(3)]
    + [
        ("p0", "push", "push"),
        ("p1", "push", "push"),
        ("p2", "high", "push"),       # over-pushed by one notch
        ("pm", "push", "hidden"),     # missed push, four notches
        ("fh0", "feed", "hidden"),    # false hide, two notches
        ("fh1", "feed", "hidden"),    # false hide, two notches
        ("fs0", "hide", "feed"),      # false show, two notches
        ("n0", "low", "hidden"),      # one notch
        ("n1", "hide", "low_feed"),   # one notch
    ]
)

_RATINGS = {aid: rating for aid, rating, _ in _ROWS}
_GUY = {aid: decision for aid, _, decision in _ROWS}
_DENI = {aid: "hidden" for aid in _RATINGS} | {"p0": "push"}


def _source(ratings=None, ids=None, *, seed=7, path="c.json"):
    ratings = dict(_RATINGS if ratings is None else ratings)
    ids = list(ratings if ids is None else ids)
    return gate.CensusSource(
        ratings_path=f"ratings_{path}",
        sample_path=f"sample_{path}",
        ratings_doc={"seed": seed, "ratings": {"guy": ratings}},
        sample_doc={
            "meta": {"seed": seed},
            "profiles": {"guy": {"items": [{"id": aid} for aid in ids]}},
        },
    )


def _merged(**kwargs):
    return gate.merge_census([_source(**kwargs)])


def _decisions(guy=None, deni=None):
    return {
        "guy": dict(_GUY) | dict(guy or {}),
        "casual_deni_fan": dict(_DENI) | dict(deni or {}),
    }


@pytest.fixture
def baseline():
    return gate.build_baseline(_merged(), _decisions(), meta={"engine": "v2"})


def _evaluate(baseline, decisions, **kwargs):
    return gate.evaluate(baseline, _merged(), decisions, **kwargs)


def _check(verdict, check_id):
    for check in verdict.checks:
        if check.check_id == check_id:
            return check
    raise AssertionError(f"no check {check_id} in {[c.check_id for c in verdict.checks]}")


def _surface_everything(decisions):
    """The N05 demonstration: show every hidden row at the lowest visible tier."""
    return {aid: ("low_feed" if d == "hidden" else d) for aid, d in decisions.items()}


def _hide_more(decisions):
    """Hide the two lowest visible tiers."""
    return {aid: ("hidden" if d in ("low_feed", "feed") else d) for aid, d in decisions.items()}


# ── metrics ───────────────────────────────────────────────────────────────────


def test_metrics_read_recall_from_the_rated_rows_not_from_the_corpus():
    m = gate.census_metrics(_RATINGS, _GUY)
    assert (m["shown"], m["worth_showing"]) == (18, 16)
    # feed or better: 6 feed + 3 high + p0 p1 p2 pm + fh0 fh1 = 15; the feed hid pm fh0 fh1.
    assert (m["feed_plus"], m["feed_plus_shown"]) == (15, 12)
    assert (m["push_fired"], m["push_agreed"]) == (3, 2)
    assert (m["push_wanted"], m["push_recalled"]) == (3, 2)
    assert m["two_notch"] == 4  # pm, fh0, fh1, fs0
    assert sorted(m["two_notch_ids"]) == ["fh0", "fh1", "fs0", "pm"]


def test_a_rated_row_without_a_decision_is_an_invalid_comparison():
    decisions = dict(_GUY)
    del decisions["f3"]
    with pytest.raises(GateInputError, match="f3"):
        gate.census_metrics(_RATINGS, decisions)


# ── the control ───────────────────────────────────────────────────────────────


def test_unchanged_run_passes(baseline):
    verdict = _evaluate(baseline, _decisions())
    assert verdict.passed
    assert verdict.flips == ()
    assert {c.check_id for c in verdict.checks} == {
        "guy.shown_precision", "guy.feed_plus_recall", "guy.push_precision",
        "guy.push_recall", "guy.push_volume", "guy.two_notch",
        "casual_deni_fan.no_drift",
    }


# ── acceptance: the two directions ────────────────────────────────────────────


def test_surface_everything_fails_on_shown_precision(baseline):
    """ACCEPTANCE (#254): recall looks perfect while precision collapses."""
    verdict = _evaluate(baseline, _decisions(guy=_surface_everything(_GUY)))
    assert not verdict.passed
    assert _check(verdict, "guy.shown_precision").passed is False
    assert _check(verdict, "guy.feed_plus_recall").passed is True


def test_hide_more_fails_on_feed_plus_recall(baseline):
    """ACCEPTANCE (#254): a quieter feed that loses wanted stories is blocked."""
    verdict = _evaluate(baseline, _decisions(guy=_hide_more(_GUY)))
    assert not verdict.passed
    assert _check(verdict, "guy.feed_plus_recall").passed is False


def test_shown_precision_may_lose_exactly_one_item(baseline):
    one = _evaluate(baseline, _decisions(guy={"h0": "low_feed"}))
    two = _evaluate(baseline, _decisions(guy={"h0": "low_feed", "h1": "low_feed"}))
    assert _check(one, "guy.shown_precision").passed is True
    assert _check(two, "guy.shown_precision").passed is False


def test_a_feed_that_shows_nothing_is_not_a_precision_win(baseline):
    nothing = {aid: "hidden" for aid in _GUY}
    verdict = _evaluate(baseline, _decisions(guy=nothing))
    assert _check(verdict, "guy.shown_precision").passed is False


def test_feed_plus_recall_has_no_slack(baseline):
    """Hiding one wanted row with nothing recovered is a real loss."""
    verdict = _evaluate(baseline, _decisions(guy={"f0": "hidden"}))
    assert _check(verdict, "guy.feed_plus_recall").passed is False


def test_feed_plus_recall_may_trade_one_loss_for_a_larger_gain(baseline):
    verdict = _evaluate(
        baseline, _decisions(guy={"f0": "hidden", "fh0": "feed", "fh1": "feed"})
    )
    assert _check(verdict, "guy.feed_plus_recall").passed is True


# ── acceptance: the noise band ────────────────────────────────────────────────


def test_one_notch_moves_do_not_fail_the_two_notch_check(baseline):
    """ACCEPTANCE (#254): moves inside the rating noise band are not regressions.

    Every move here opens a ONE-notch gap on a row the engine agreed with, so
    exact agreement falls by four, which is the movement a re-rate would wash out.
    """
    moves = {"f0": "high_feed", "f1": "low_feed", "g0": "feed", "l0": "feed"}
    verdict = _evaluate(baseline, _decisions(guy=moves))
    check = _check(verdict, "guy.two_notch")
    assert check.passed is True
    assert check.current == check.baseline == 4
    assert verdict.passed


def test_a_new_two_notch_gap_fails(baseline):
    verdict = _evaluate(baseline, _decisions(guy={"l0": "high_feed"}))
    assert _check(verdict, "guy.two_notch").passed is False
    assert not verdict.passed


def test_closing_one_large_gap_pays_for_opening_another(baseline):
    verdict = _evaluate(baseline, _decisions(guy={"fs0": "hidden", "l0": "high_feed"}))
    assert _check(verdict, "guy.two_notch").passed is True


# ── push ──────────────────────────────────────────────────────────────────────


def test_losing_a_correct_push_fails_push_recall(baseline):
    verdict = _evaluate(baseline, _decisions(guy={"p0": "high_feed"}))
    assert _check(verdict, "guy.push_recall").passed is False
    assert _check(verdict, "guy.push_precision").passed is True


def test_push_precision_drop_fails(baseline):
    verdict = _evaluate(baseline, _decisions(guy={"p0": "high_feed", "p1": "high_feed"}))
    assert _check(verdict, "guy.push_precision").passed is False


def test_push_volume_may_not_rise_without_a_precision_gain(baseline):
    verdict = _evaluate(baseline, _decisions(guy={"g0": "push"}))
    assert _check(verdict, "guy.push_precision").passed is True  # 2/4 within 1-push slack
    assert _check(verdict, "guy.push_volume").passed is False
    assert not verdict.passed


def test_push_volume_may_rise_when_precision_improves(baseline):
    verdict = _evaluate(baseline, _decisions(guy={"pm": "push"}))
    assert _check(verdict, "guy.push_volume").passed is True
    assert _check(verdict, "guy.push_recall").passed is True
    assert verdict.passed


# ── drift on the canary profile ───────────────────────────────────────────────


def test_casual_deni_fan_drift_fails(baseline):
    verdict = _evaluate(baseline, _decisions(deni={"h4": "feed"}))
    assert _check(verdict, "casual_deni_fan.no_drift").passed is False
    assert [(f.profile, f.article_id, f.after) for f in verdict.flips] == [
        ("casual_deni_fan", "h4", "feed")
    ]


def test_drift_needs_no_ratings():
    """The census rates only Guy; Deni's drift is read over the same article ids."""
    merged = _merged()
    assert "casual_deni_fan" not in merged.ratings
    baseline = gate.build_baseline(merged, _decisions(), meta={})
    assert set(baseline["profiles"]["casual_deni_fan"]["decisions"]) == set(_RATINGS)


def test_an_article_leaving_the_corpus_counts_as_a_drift_flip(baseline):
    decisions = _decisions()
    del decisions["casual_deni_fan"]["h7"]
    verdict = _evaluate(baseline, decisions)
    assert not verdict.passed
    assert any(f.article_id == "h7" and f.after == "<missing>" for f in verdict.flips)


def test_guy_movement_is_recorded_but_only_the_census_checks_gate_it(baseline):
    verdict = _evaluate(baseline, _decisions(guy={"f0": "high_feed"}))
    assert verdict.passed
    assert [f.article_id for f in verdict.flips] == ["f0"]


# ── accepting a regression is an argued act ───────────────────────────────────


def test_accept_unblocks_a_named_check_and_records_the_reason(baseline):
    # Hiding f0 opens a two-notch gap; hiding fs0 closes one, so only recall moves.
    verdict = _evaluate(
        baseline,
        _decisions(guy={"f0": "hidden", "fs0": "hidden"}),
        accepted=["guy.feed_plus_recall"],
        accept_reason="argued in the PR",
    )
    assert verdict.passed
    check = _check(verdict, "guy.feed_plus_recall")
    assert check.accepted and check.accept_reason == "argued in the PR"


def test_a_stale_accept_fails_the_gate(baseline):
    verdict = _evaluate(baseline, _decisions(), accepted=["guy.false_hide"], accept_reason="x")
    assert not verdict.passed
    assert verdict.unknown_accepts == ("guy.false_hide",)


# ── invalid comparisons are errors, not scores ────────────────────────────────


def test_a_changed_rating_is_an_error_even_at_the_same_count(baseline):
    changed = dict(_RATINGS) | {"f0": "high"}
    with pytest.raises(GateInputError, match="ratings changed"):
        gate.evaluate(baseline, _merged(ratings=changed), _decisions())


def test_a_different_census_article_set_is_an_error(baseline):
    smaller = {k: v for k, v in _RATINGS.items() if k != "h0"}
    with pytest.raises(GateInputError):
        gate.evaluate(baseline, _merged(ratings=smaller), _decisions())


def test_empty_baseline_is_an_error():
    with pytest.raises(GateInputError, match="no rated profiles"):
        gate.evaluate({"profiles": {}}, _merged(), _decisions())


def test_a_run_on_other_facts_than_the_baseline_is_an_error(baseline):
    """Stored facts and a rules-only rerun are different measurements (#398 lesson)."""
    assert baseline["facts"] == "stored"
    with pytest.raises(GateInputError, match="facts"):
        gate.evaluate(baseline, _merged(), _decisions(), facts="rerun")


def test_a_rerun_baseline_accepts_a_rerun_run():
    rerun = gate.build_baseline(_merged(), _decisions(), meta={}, facts="rerun")
    assert gate.evaluate(rerun, _merged(), _decisions(), facts="rerun").passed
    with pytest.raises(GateInputError, match="facts"):
        gate.evaluate(rerun, _merged(), _decisions())


def test_an_unknown_facts_source_is_rejected():
    with pytest.raises(ValueError, match="facts"):
        gate.build_baseline(_merged(), _decisions(), meta={}, facts="llm")


# ── inputs: several censuses, deduplicated, with reviews on top ───────────────


def test_census_files_combine_and_deduplicate_by_article_id():
    a = _source({"x1": "feed", "x2": "hide"}, path="a.json")
    b = _source({"x2": "hide", "x3": "push"}, path="b.json")
    merged = gate.merge_census([a, b])
    assert merged.ratings == {"guy": {"x1": "feed", "x2": "hide", "x3": "push"}}
    assert merged.article_ids == ("x1", "x2", "x3")
    assert merged.inputs["duplicate_rows"] == 1
    assert [c["ratings"] for c in merged.inputs["censuses"]] == ["ratings_a.json", "ratings_b.json"]


def test_two_censuses_disagreeing_on_an_article_is_an_error():
    a = _source({"x1": "feed"}, path="a.json")
    b = _source({"x1": "hide"}, path="b.json")
    with pytest.raises(GateInputError, match="x1"):
        gate.merge_census([a, b])


def test_a_review_rating_wins_and_settles_a_disagreement():
    a = _source({"x1": "feed", "x2": "low"}, path="a.json")
    b = _source({"x1": "hide"}, path="b.json")
    review = gate.ReviewSource(path="review.json", doc={"seed": 7, "ratings": {"guy": {"x1": "low", "x2": "low"}}})
    merged = gate.merge_census([a, b], [review])
    assert merged.ratings["guy"] == {"x1": "low", "x2": "low"}
    assert merged.inputs["reviews"] == [{"path": "review.json", "rows": 2, "changed": 1}]


def test_a_review_naming_an_unrated_article_is_an_error():
    review = gate.ReviewSource(path="r.json", doc={"ratings": {"guy": {"nope": "low"}}})
    with pytest.raises(GateInputError, match="nope"):
        gate.merge_census([_source()], [review])


def test_ratings_from_another_sample_are_rejected():
    with pytest.raises(GateInputError, match="seed"):
        gate.merge_census([gate.CensusSource(
            ratings_path="r", sample_path="s",
            ratings_doc={"seed": 1, "ratings": {"guy": {"x1": "feed"}}},
            sample_doc={"meta": {"seed": 2}, "profiles": {"guy": {"items": [{"id": "x1"}]}}},
        )])


def test_a_rating_for_an_article_outside_its_sample_is_rejected():
    with pytest.raises(GateInputError, match="x9"):
        gate.merge_census([_source({"x1": "feed", "x9": "low"}, ids=["x1"])])


def test_an_unknown_rating_value_is_rejected():
    with pytest.raises(GateInputError, match="meh"):
        gate.merge_census([_source({"x1": "meh"})])


# ── regenerating a baseline: the delta first (owner rule, PR #399) ────────────
#
# A baseline is a change detector, not proof the result is correct. Rewriting it
# to absorb a change before its delta against the PREVIOUS baseline is reviewed
# would launder a regression into the reference. So an update runs the gate
# against the previous baseline first and refuses to write on a failure.


def _check_update(baseline, decisions, **kwargs):
    return gate.check_baseline_update(baseline, _merged(), decisions, facts="stored", **kwargs)


def test_update_is_allowed_when_the_gate_passes_and_reports_the_delta(baseline):
    update = _check_update(baseline, _decisions(guy={"pm": "push"}))
    assert update.allowed
    delta = update.delta
    checks = {c["check_id"]: c for c in delta["checks"]}
    assert (checks["guy.push_recall"]["baseline"], checks["guy.push_recall"]["current"]) == (0.6667, 1.0)
    assert delta["rated_rows_changed"] == [
        {"profile": "guy", "article_id": "pm", "before": "hidden", "after": "push", "rating": "push"}
    ]


def test_update_is_refused_when_the_gate_fails(baseline):
    update = _check_update(baseline, _decisions(guy=_hide_more(_GUY)))
    assert not update.allowed
    assert "guy.feed_plus_recall" in update.message
    assert update.delta["passed"] is False


def test_an_argued_accept_allows_the_update_and_is_recorded(baseline):
    update = _check_update(
        baseline,
        _decisions(guy={"f0": "hidden", "fs0": "hidden"}),
        accepted=["guy.feed_plus_recall"],
        accept_reason="reviewed in #999",
    )
    assert update.allowed
    accepted = [c for c in update.delta["checks"] if c["accepted"]]
    assert [c["check_id"] for c in accepted] == ["guy.feed_plus_recall"]
    assert update.delta["accept_reason"] == "reviewed in #999"


def test_force_overrides_a_failing_gate_only_with_a_reason(baseline):
    failing = _decisions(guy=_hide_more(_GUY))
    with pytest.raises(ValueError, match="reason"):
        _check_update(baseline, failing, force=True)
    update = _check_update(baseline, failing, force=True, force_reason="owner reviewed the delta in #999")
    assert update.allowed
    assert update.delta["forced_reason"] == "owner reviewed the delta in #999"


def test_an_incomparable_previous_baseline_refuses_without_force(baseline):
    changed = gate.merge_census([_source(dict(_RATINGS) | {"f0": "high"})])
    update = gate.check_baseline_update(baseline, changed, _decisions(), facts="stored")
    assert not update.allowed
    assert update.delta["comparable"] is False
    assert "ratings changed" in update.message
    forced = gate.check_baseline_update(
        baseline, changed, _decisions(), facts="stored", force=True, force_reason="census re-rated, #999"
    )
    assert forced.allowed


def test_the_first_baseline_needs_no_delta():
    update = gate.check_baseline_update(None, _merged(), _decisions(), facts="stored")
    assert update.allowed and update.delta is None


def test_the_new_baseline_records_the_reviewed_delta(baseline):
    update = _check_update(baseline, _decisions(guy={"pm": "push"}))
    fresh = gate.build_baseline(
        _merged(), _decisions(guy={"pm": "push"}), meta={}, previous=baseline, delta=update.delta
    )
    assert fresh["previous"]["delta"]["rated_rows_changed"][0]["article_id"] == "pm"
    assert fresh["previous"]["facts"] == "stored"


def test_the_delta_renders_before_and_after_per_check_and_the_rated_rows(baseline):
    update = _check_update(baseline, _decisions(guy={"pm": "push"}))
    text = gate.format_delta(update.delta)
    assert "guy.push_recall" in text and "0.6667 -> 1.0" in text
    assert "pm" in text and "hidden -> push" in text and "rated push" in text


# ── the report ────────────────────────────────────────────────────────────────


def test_rendered_verdict_leads_with_precision_and_recall(baseline):
    text = gate.format_verdict(_evaluate(baseline, _decisions()))
    assert "shown precision" in text
    assert "feed+ recall" in text
    assert "push recall" in text
    assert ">=2-notch" in text
    assert "GATE PASSED" in text


# ── the committed baseline: real data, replayed in CI ─────────────────────────
#
# The baseline stores every per-article decision, and the census ratings it was
# built from are committed. That is enough to (1) prove the baseline was
# machine-generated (its metrics equal a recomputation from its own decisions)
# and (2) run the acceptance demonstrations on the real census, without a corpus.

_REPO = Path(__file__).resolve().parents[2]
# One baseline per facts source: stored facts (what the corpus serves; relevance and
# profile changes) and a rules-only rerun (classifier and taxonomy changes).
_BASELINES = {
    "stored": _REPO / "docs" / "qa" / "census_gate_baseline.json",
    "rerun": _REPO / "docs" / "qa" / "census_gate_rerun_baseline.json",
}


def _load(rel: str) -> dict:
    return json.loads((_REPO / rel).read_text(encoding="utf-8"))


@pytest.fixture(scope="module", params=sorted(_BASELINES))
def committed(request):
    facts = request.param
    path = _BASELINES[facts]
    assert path.exists(), (
        f"{path} is missing. Regenerate deliberately with:\n"
        f"  scripts/feed_ground_truth.py gate --census --facts {facts} --update-baseline"
    )
    baseline = json.loads(path.read_text(encoding="utf-8"))
    inputs = baseline["inputs"]
    merged = gate.merge_census(
        [
            gate.CensusSource(c["ratings"], c["sample"], _load(c["ratings"]), _load(c["sample"]))
            for c in inputs["censuses"]
        ],
        [gate.ReviewSource(r["path"], _load(r["path"])) for r in inputs["reviews"]],
    )
    decisions = {p: dict(block["decisions"]) for p, block in baseline["profiles"].items()}
    return baseline, merged, decisions


def _replay(committed, guy):
    baseline, merged, decisions = committed
    return gate.evaluate(baseline, merged, dict(decisions) | {"guy": guy}, facts=baseline["facts"])


def test_committed_baseline_shape(committed):
    baseline, _, _ = committed
    assert baseline["baseline_version"] == gate.BASELINE_VERSION
    assert baseline["kind"] == "census"
    assert baseline["facts"] in gate.FACTS_SOURCES
    assert "casual_deni_fan" in baseline["policy"]["drift_must_be_zero"]
    assert set(baseline["profiles"]) == {"guy", "casual_deni_fan"}


def test_committed_baselines_use_the_same_census():
    """Both facts sources must measure the same rows, or comparing them means nothing."""
    inputs = [json.loads(p.read_text(encoding="utf-8"))["inputs"] for p in _BASELINES.values()]
    assert inputs[0] == inputs[1]


def test_committed_baseline_matches_the_committed_ratings(committed):
    """Editing a rating without regenerating the baseline is caught here."""
    baseline, merged, _ = committed
    for profile_id, ratings in merged.ratings.items():
        assert baseline["profiles"][profile_id]["ratings_sha256"] == gate.ratings_fingerprint(ratings)


def test_committed_baseline_metrics_recompute_from_its_own_decisions(committed):
    """A hand-tuned number would no longer equal a recomputation."""
    baseline, merged, decisions = committed
    stored = baseline["profiles"]["guy"]["metrics"]
    assert gate.census_metrics(merged.ratings["guy"], decisions["guy"]) == stored


def test_committed_baseline_covers_every_census_article_for_the_canary(committed):
    baseline, merged, _ = committed
    assert set(baseline["profiles"]["casual_deni_fan"]["decisions"]) == set(merged.article_ids)


def test_committed_baseline_passes_against_itself(committed):
    assert _replay(committed, committed[2]["guy"]).passed


def test_real_census_surface_everything_fails_on_shown_precision(committed):
    """ACCEPTANCE (#254) on census #2: the N05 lesson replayed on 804 real rows."""
    verdict = _replay(committed, _surface_everything(committed[2]["guy"]))
    assert _check(verdict, "guy.shown_precision").passed is False
    assert _check(verdict, "guy.feed_plus_recall").passed is True


def test_real_census_hide_more_fails_on_feed_plus_recall(committed):
    verdict = _replay(committed, _hide_more(committed[2]["guy"]))
    assert _check(verdict, "guy.feed_plus_recall").passed is False
