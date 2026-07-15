"""
D1 (#121) — `release` (and the other silently-omitted event types) become clusterable.

Driven by `feed_dedup_cases.json`: articles frozen verbatim from Guy's REAL ranked feed, where
the gap produced FOUR near-identical `high_feed` cards for one Maccabi release.

The root cause was not a threshold. It was a **hole in the contract**: an event type present in
NEITHER `CLUSTERABLE_EVENT_STATES` nor `NEVER_CLUSTERED_EVENT_STATES` does not "default to
safe" — it falls through the event-state gate and becomes **unclusterable at any similarity**,
silently. Seven event types were in that hole, including `grand_slam_winner` (the Noskova pair).
"""

import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from app.clustering import DEFAULT_CONFIG, ClusterInput, cluster_articles
from app.clustering.config import (
    CLUSTERABLE_EVENT_STATES,
    NEVER_CLUSTERED_EVENT_STATES,
    unclassified_event_states,
)
from app.clustering.event_states import is_clusterable_state, states_compatible

FIXTURES = Path(__file__).parent / "fixtures" / "feed_dedup_cases.json"
EVENT_EVIDENCE = Path(__file__).parent.parent / "app" / "classification" / "event_evidence.py"


@pytest.fixture(scope="module")
def cases():
    with FIXTURES.open(encoding="utf-8") as fh:
        return json.load(fh)


def _group(cases, gid):
    return next(g for g in cases["duplicate_groups"] if g["id"] == gid)


def _to_input(raw):
    return ClusterInput(
        id=raw["id"], source=raw["source"], title=raw["title"],
        subtitle=raw.get("subtitle", ""),
        published_at=datetime.fromisoformat(raw["published_at"].replace("Z", "+00:00")),
        sport=raw["sport"], event_type=raw["event_type"],
        event_certainty=raw.get("event_certainty"),
        entity_ids=tuple(raw.get("entity_ids") or ()),
        primary_competition=raw.get("primary_competition"),
    )


def _known_event_types() -> frozenset[str]:
    """Every event type the classifier can emit (from the evidence-rule registry)."""
    src = EVENT_EVIDENCE.read_text(encoding="utf-8")
    return frozenset(re.findall(r'^\s{4}"([a-z_]+)": EventEvidenceRule', src, re.M))


# ── The structural fix: the omission must be impossible to repeat ────────────

class TestNoSilentlyOmittedEventType:
    def test_every_event_type_is_explicitly_classified(self):
        """THE regression guard. An event type in neither set is unclusterable at any
        similarity, silently — that is exactly how `release` and `grand_slam_winner` went
        unmergeable for a whole milestone."""
        missing = unclassified_event_states(_known_event_types())
        assert missing == frozenset(), (
            f"event types in NEITHER clusterable nor never-clustered: {sorted(missing)}. "
            "They will silently fail to cluster. Add each to exactly one set, deliberately."
        )

    def test_the_two_sets_are_disjoint(self):
        assert not (CLUSTERABLE_EVENT_STATES & NEVER_CLUSTERED_EVENT_STATES)

    def test_previously_omitted_types_are_now_clusterable(self):
        for state in ("release", "major_trade", "title_win", "grand_slam_winner",
                      "playoff_result", "regular_season_result", "early_round_result"):
            assert is_clusterable_state(state), state

    def test_perspective_pieces_remain_non_clusterable(self):
        # Two columnists on the same transfer are TWO stories, not one.
        for state in ("schedule", "preview", "interview", "analysis", "opinion"):
            assert not is_clusterable_state(state), state

    def test_every_clusterable_state_has_a_time_window(self):
        for state in CLUSTERABLE_EVENT_STATES:
            assert state in DEFAULT_CONFIG.time_window_hours, f"{state} has no window"


# ── Strict same-state still holds ────────────────────────────────────────────

class TestReleaseStaysItsOwnState:
    def test_release_clusters_with_release(self):
        assert states_compatible("release", "release")

    def test_release_never_merges_with_signing(self):
        """A departure and an arrival are DIFFERENT story developments — the distinction
        #113's departure blockers were built to protect."""
        assert not states_compatible("release", "signing")
        assert not states_compatible("signing", "release")

    def test_results_do_not_cross_states(self):
        assert not states_compatible("title_win", "match_result")
        assert not states_compatible("grand_slam_winner", "early_round_result")


# ── The real-feed harm ───────────────────────────────────────────────────────

class TestHankinsReleasePassesTheEventStateGate:
    """D1 removes the EVENT-STATE blocker. It does NOT (yet) merge these four cards.

    A SECOND, independent defect blocks the merge — and it belongs to #122, not here:

        Jaccard is LENGTH-SENSITIVE. The israel_hayom article has 40 tokens (its subtitle
        even appends an unrelated story, "נבחרת העתודה של ישראל ניצחה"); sport5 has 13.
        Jaccard divides by the UNION, so divergent-length near-duplicates are crushed —
        even a perfect subset match of 13-in-40 caps at 0.32. All four pairs land at
        J = 0.06–0.25 against a 0.30 floor, despite being Tier A with strong
        discriminative evidence (הנקינס, נפרדה).

    Lowering the floor is explicitly forbidden (it would manufacture merges and treat a
    symptom). The fix is a length-robust similarity measure — #122's analysis.

    What D1 CAN prove, and does: the rejection reason has MOVED from
    `not_clusterable_state` (nothing was even evaluated) to `below_threshold` (the pair is
    now fully evaluated and fails on similarity alone). That is real, measurable progress
    and a precise handoff.
    """

    def _pairs(self, cases):
        from itertools import combinations

        from app.clustering.matcher import match_pair
        from app.clustering.tokens import DocumentFrequency, tokenize

        arts = [_to_input(a) for a in _group(cases, "dup_hankins_release")["articles"]]
        tok = {a.id: tokenize(f"{a.title} {a.subtitle}") for a in arts}
        df = DocumentFrequency.over(tok.values())
        return [
            (x, y, *match_pair(x, y, tok[x.id], tok[y.id], df, DEFAULT_CONFIG))
            for x, y in combinations(arts, 2)
        ]

    def test_the_group_holds_all_four_real_cards(self, cases):
        assert len(_group(cases, "dup_hankins_release")["articles"]) == 4

    def test_no_pair_is_rejected_on_the_event_state_gate_any_more(self, cases):
        from app.clustering.matcher import Rejection

        for x, y, edge, rej in self._pairs(cases):
            if rej is not None:
                assert rej.reason not in (
                    Rejection.NOT_CLUSTERABLE_STATE,
                    Rejection.EVENT_STATE_INCOMPATIBLE,
                ), f"{x.source}~{y.source} still blocked by the event-state gate"

    def test_pairs_are_now_fully_evaluated_and_reach_tier_a(self, cases):
        from app.clustering.matcher import TIER_A, select_tier

        for x, y, _edge, _rej in self._pairs(cases):
            assert select_tier(x, y) == TIER_A, "all four share team:maccabi_tlv_bb"

    def test_the_remaining_blocker_is_similarity_not_evidence(self, cases):
        """Hands #122 a precise, reproducible statement of the second root cause."""
        from app.clustering.matcher import Rejection

        for x, y, edge, rej in self._pairs(cases):
            assert edge is None, "unexpected merge — update this test if #122 has landed"
            assert rej.reason == Rejection.BELOW_JACCARD, (
                f"{x.source}~{y.source}: expected the length-sensitive Jaccard to be the "
                f"only remaining blocker, got {rej.reason}"
            )

    def test_discriminative_evidence_is_present_and_strong(self, cases):
        """The evidence is NOT the problem — which is why lowering the evidence bar would
        be fixing the wrong thing."""
        from itertools import combinations

        from app.clustering.tokens import DocumentFrequency, tokenize

        arts = [_to_input(a) for a in _group(cases, "dup_hankins_release")["articles"]]
        tok = {a.id: tokenize(f"{a.title} {a.subtitle}") for a in arts}
        df = DocumentFrequency.over(tok.values())
        for x, y in combinations(arts, 2):
            shared = df.discriminative_shared(tok[x.id], tok[y.id], DEFAULT_CONFIG)
            assert shared, f"{x.source}~{y.source} has no discriminative evidence"

    def test_the_subtitle_only_card_still_carries_its_evidence(self, cases):
        """The israel_hayom card names NO player in its title ('נפרדה מאחד משחקניה') —
        'הנקינס' lives ONLY in the subtitle. Any #122 fix must keep using title+subtitle,
        or this card can never join and the user's feed is not actually fixed."""
        hard = next(
            a for a in _group(cases, "dup_hankins_release")["articles"]
            if a["source"] == "israel_hayom_sport"
        )
        assert "הנקינס" not in hard["title"]
        assert "הנקינס" in hard["subtitle"]


class TestNoskovaIsNowEligible:
    def test_grand_slam_winner_is_clusterable(self, cases):
        """The Noskova pair is `grand_slam_winner` — ALSO in the contract hole. Even the
        intra-source dedup stage (#123) could not have helped while this state was
        unclusterable."""
        g = _group(cases, "dup_noskova_same_source")
        assert {a["event_type"] for a in g["articles"]} == {"grand_slam_winner"}
        assert is_clusterable_state("grand_slam_winner")

    def test_now_merges_via_the_intra_source_stage(self, cases):
        """The loop closes: D1 removed the event-state blocker, #123 added the dedicated
        intra-source republish stage — the pair this class documented as unreachable now
        collapses to one cluster (via a tier-I edge, never the cross-source gate)."""
        from app.clustering.intra_source import TIER_INTRA_SOURCE

        g = _group(cases, "dup_noskova_same_source")
        arts = [_to_input(a) for a in g["articles"]]
        assert len({a.source for a in arts}) == 1
        res = cluster_articles(arts, DEFAULT_CONFIG)
        assert len(res.clusters) == 1
        assert len(res.clusters[0].member_ids) == 2
        assert all(e.tier == TIER_INTRA_SOURCE for e in res.edges)
