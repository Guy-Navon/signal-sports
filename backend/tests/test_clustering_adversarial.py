"""The adversarial regression corpus (#134) — the precision gate that the fixtures could not be.

WHY THIS FILE EXISTS. `clustering_cases.json` has 7 must-not-cluster groups, of which only
**4 pairs** survive the hard gates. That corpus certifies nothing: an evidence-primary
mechanism scored **27/31 with ZERO fixture over-merges** — and produced **21 over-merges**
across 2,922 real corpus pairs. A mechanism can look perfect on the fixtures and be
catastrophic in production.

Every entry in `clustering_adversarial.json` is HAND-ADJUDICATED. An automated sweep flagged
11 pairs as over-merges; manual review found **three were genuine duplicates** — including the
Storonski pair that D2c (#137) exists to fix. Freezing those as negatives would have
permanently locked in the bug.

These tests do not assert matcher behaviour (the current matcher rejects everything here on
Jaccard, for the wrong reasons). They guard the DATA and state the contract that #135–#138
must satisfy, so a future mechanism cannot be graded against a corpus that has quietly rotted.
"""

import json
from pathlib import Path

import pytest

from app.clustering.tokens import is_generic

FIXTURE = Path(__file__).parent / "fixtures" / "clustering_adversarial.json"


@pytest.fixture(scope="module")
def adv():
    with FIXTURE.open(encoding="utf-8") as fh:
        return json.load(fh)


class TestTheAdversarialCorpusIsIntact:
    def test_the_negatives_are_all_present(self, adv):
        ids = {n["id"] for n in adv["must_not_merge"]}
        assert ids == {
            "adv_coach_as_bridge_bryant",
            "adv_coach_as_bridge_otooru",
            "adv_same_club_different_player_1",
            "adv_same_club_different_player_2",
            "adv_money_vocabulary_madar",
            "adv_money_vocabulary_diallo",
            "adv_formulaic_negotiation_template",
        }

    def test_every_negative_records_the_evidence_that_fooled_a_mechanism(self, adv):
        """A negative without its bad evidence is a negative nobody can learn from."""
        for n in adv["must_not_merge"]:
            assert n["bad_evidence"], n["id"]
            assert n["merged_by"], n["id"]
            assert len(n["why"]) > 60, f"{n['id']} needs a real reason, not a label"

    def test_every_negative_is_a_cross_source_pair(self, adv):
        for n in adv["must_not_merge"]:
            a, b = n["articles"]
            assert a["source"] != b["source"], n["id"]


class TestTheRequiredNegativeClasses:
    """The four classes #136 (story anchors) must defeat, each grounded in a real pair."""

    def test_same_club_different_player(self, adv):
        """Bryant's extension and Otooru's extension, both at Hapoel TA, bridged by
        'לשלוש שנים נוספות' — a CONTRACT-EXTENSION TEMPLATE. Every extension says it."""
        n = next(x for x in adv["must_not_merge"]
                 if x["id"] == "adv_same_club_different_player_1")
        assert set(n["bad_evidence"]) == {"לשלוש", "נוספות"}

    def test_same_coach_unrelated_stories(self, adv):
        """A coach's name is a CLUB-level token, not a story anchor. 'איטודיס' bridges
        Storonski's arrival with two different players' extensions."""
        for cid in ("adv_coach_as_bridge_bryant", "adv_coach_as_bridge_otooru"):
            n = next(x for x in adv["must_not_merge"] if x["id"] == cid)
            assert n["bad_evidence"] == ["איטודיס"]

    def test_formulaic_terms_without_a_shared_named_subject(self, adv):
        """THE pair that proves containment alone is insufficient. Wheeler↔Eilat and
        Holon↔two-players share only במו"מ / בשיחות ('in negotiations') — and sit at
        C=0.31, the SAME containment at which Madar first becomes reachable."""
        n = next(x for x in adv["must_not_merge"]
                 if x["id"] == "adv_formulaic_negotiation_template")
        assert set(n["bad_evidence"]) == {"במו", "בשיחות"}
        assert "containment_0.30" in n["merged_by"], "this is the containment survivor"
        assert n["metrics"]["containment"] >= 0.30

    def test_rare_is_not_story_identifying(self, adv):
        """THE architectural conclusion, as data. Every token below passed the production
        discriminative test (df <= max_story_coverage, not generic) and identifies NOTHING."""
        fooled = {t for n in adv["must_not_merge"] for t in n["bad_evidence"]}
        assert {"דולר", "איטודיס", "לשלוש", "במו"} <= fooled
        for tok in fooled:
            assert not is_generic(tok), (
                f"{tok!r} is caught by the generic list — then it could not have fooled a "
                "mechanism, and this negative is stale"
            )


class TestTheTrueDuplicatesTheSweepMislabelled:
    """Three pairs the automated sweep called over-merges are REAL stories.

    This class is the guard against the failure mode that nearly happened: freezing a true
    duplicate as a permanent must-not-merge negative, locking the bug in forever.
    """

    def test_storonski_is_a_true_duplicate_not_a_negative(self, adv):
        """Storonski IS Chris Jones's replacement. israel_hayom headlines the ROLE and names
        him only in the subtitle. This is D2c's POSITIVE CONTROL — any transliteration fix
        must MERGE these, and any negative that blocks them is a bug."""
        g = next(x for x in adv["true_duplicates_from_sweep"]
                 if x["id"] == "tp_storonski_chris_jones_replacement")
        assert len(g["articles"]) == 3
        negatives = {n["id"] for n in adv["must_not_merge"]}
        assert "tp_storonski_chris_jones_replacement" not in negatives

    def test_the_transliteration_split_is_preserved_in_the_data(self, adv):
        """The whole point of D2c: sport5 spells him סטרונסקי, the others סטורנסקי."""
        g = next(x for x in adv["true_duplicates_from_sweep"]
                 if x["id"] == "tp_storonski_chris_jones_replacement")
        blob = " ".join(f"{a['title']} {a['subtitle']}" for a in g["articles"])
        assert "סטרונסקי" in blob and "סטורנסקי" in blob, (
            "both spellings must survive in the frozen data, or D2c has no positive control"
        )

    def test_no_pair_belongs_to_conflicting_fixture_classes(self, adv):
        """THE consistency invariant, across ALL FOUR classes.

        A pair frozen as both "must merge" and "must not merge" makes the gate unsatisfiable
        by construction — which is exactly what would have happened to #137 if the automated
        sweep's Storonski verdict had been accepted.
        """
        def pair_keys(entries):
            keys = set()
            for e in entries:
                ids = sorted(a["id"] for a in e["articles"])
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        keys.add((ids[i], ids[j]))
            return keys

        must_merge = pair_keys(adv["true_duplicates_from_sweep"])
        must_not = pair_keys(adv["must_not_merge"])
        material = pair_keys(adv["material_update_same_thread"])
        ambiguous = pair_keys(adv["ambiguous"])

        for name_a, a, name_b, b in [
            ("true_duplicates", must_merge, "must_not_merge", must_not),
            ("true_duplicates", must_merge, "material_update", material),
            ("true_duplicates", must_merge, "ambiguous", ambiguous),
            ("must_not_merge", must_not, "material_update", material),
            ("must_not_merge", must_not, "ambiguous", ambiguous),
            ("material_update", material, "ambiguous", ambiguous),
        ]:
            clash = a & b
            assert not clash, (
                f"pair(s) {clash} are frozen as BOTH {name_a} and {name_b} — the gate would "
                "be unsatisfiable by construction"
            )


class TestMaterialUpdateOnOneThread:
    """A fourth adjudication class, because three were not enough.

    A reviewed pair must NOT be forced into merge / not-merge / ambiguous. The Diarra pair is
    the reason: same subject, same ongoing thread, 12h apart — and the two reports CONTRADICT
    each other (israel_hayom: the Reds have not given up; walla: he will not sign, he is close
    to Kasimpasa).

    That is not an over-merge in the classification sense, and it is not an undecided case.
    It is a DECIDED PRODUCT POLICY: **same subject and same thread do not make two articles
    interchangeable.** A user shown only one of these cards is told something false about the
    state of the world. Until Signal has an update-aware cluster UI that preserves chronology
    and conflicting claims, such pairs must not collapse through de-duplication.
    """

    def test_diarra_is_a_material_update_not_an_ambiguity(self, adv):
        m = adv["material_update_same_thread"]
        assert len(m) == 1 and m[0]["id"] == "material_update_diarra_hapoel"
        assert m[0]["policy"] == "must_not_collapse_until_update_aware_ui"

    def test_it_may_later_share_a_thread_id_but_is_not_an_interchangeable_card(self, adv):
        """The distinction that keeps this from silently becoming a must_not_merge: these two
        MAY eventually share a saga/thread identifier. What they may never do is collapse into
        one card where canonical selection hides the other report."""
        m = adv["material_update_same_thread"][0]
        assert m["may_later_share"] == "saga_or_thread_identifier"
        assert "canonical selection must not hide either report" in m["why"]

    def test_the_two_reports_actually_contradict(self, adv):
        """If they ever stop contradicting, this case's whole justification is gone and the
        class must be re-argued rather than quietly reused."""
        m = adv["material_update_same_thread"][0]
        a, b = m["articles"]
        blob = " ".join(f"{x['title']} {x['subtitle']}" for x in (a, b))
        assert "לא ירדו" in blob or "לא יחתום" in blob, (
            "the contradiction (still pursuing him / he will not sign) must survive in the "
            "frozen data"
        )

    def test_ambiguous_is_empty_by_design(self, adv):
        """`ambiguous` is not a parking space for decisions we have not made."""
        assert adv["ambiguous"] == []
        assert "EMPTY by design" in adv["_meta"]["adjudication_classes"]["ambiguous"]


class TestGroundTruthIsNeverAutomated:
    def test_the_rule_is_recorded_in_the_fixture(self, adv):
        """Automated candidate generation may surface REVIEW TARGETS. It may never assign
        GROUND TRUTH. Storonski is the proof: subtitle-only identity evidence made a genuine
        duplicate look like an over-merge."""
        rule = adv["_meta"]["ground_truth_rule"]
        assert "MAY NEVER ASSIGN GROUND" in rule
        assert "Storonski" in rule


class TestTheGateContract:
    def test_the_fixture_records_why_the_old_negatives_were_insufficient(self, adv):
        meta = adv["_meta"]
        assert meta["eligible_pairs_enumerated"] > 2000, (
            "the whole point is that it took thousands of real pairs to falsify a mechanism "
            "that looked perfect on four"
        )
        assert "HAND-ADJUDICATED" in meta["adjudication"]
