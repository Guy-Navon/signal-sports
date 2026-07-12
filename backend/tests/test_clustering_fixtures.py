"""
Frozen clustering contract fixtures (#99 / C1) — shape + integrity.

These fixtures are the regression corpus for the deterministic matcher (#100 / C2).
They are COMMITTED DATA, never queried from the corpus DB: a suite that depends on a
mutable, ungitted corpus is exactly the fragility that destroyed the corpus (#106).

This module does not test clustering logic (none exists yet). It guarantees the
fixture file stays well-formed and self-describing, so C2 can be written against it
with no corpus access.
"""

import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "clustering_cases.json"

SECTIONS = {
    "true_positive_groups": "cluster",
    "must_not_cluster": "must_not_cluster",
    "excluded_from_candidacy": "excluded",
}

REQUIRED_ARTICLE_FIELDS = {
    "id", "source", "title", "sport", "event_type",
    "event_certainty", "entity_ids", "primary_competition", "published_at",
}


@pytest.fixture(scope="module")
def fixtures() -> dict:
    with FIXTURE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _all_cases(fx: dict):
    for section in SECTIONS:
        for case in fx[section]:
            yield section, case


class TestFixtureShape:
    def test_file_parses(self, fixtures):
        assert isinstance(fixtures, dict)

    def test_all_sections_present_and_non_empty(self, fixtures):
        for section in SECTIONS:
            assert section in fixtures, f"missing section: {section}"
            assert fixtures[section], f"empty section: {section}"

    def test_every_case_declares_an_expected_outcome(self, fixtures):
        # The core C1 acceptance criterion: no case may be ambiguous about what
        # the matcher is supposed to do with it.
        for section, case in _all_cases(fixtures):
            assert case.get("expect") == SECTIONS[section], (
                f"{case.get('id')}: expect={case.get('expect')!r} "
                f"does not match section {section}"
            )

    def test_every_case_explains_why(self, fixtures):
        # A fixture without a rationale is a fixture nobody can safely change later.
        for _, case in _all_cases(fixtures):
            assert case.get("why", "").strip(), f"{case.get('id')}: missing 'why'"

    def test_case_ids_unique(self, fixtures):
        ids = [c["id"] for _, c in _all_cases(fixtures)]
        assert len(ids) == len(set(ids)), "duplicate case ids"

    def test_every_case_has_at_least_two_articles(self, fixtures):
        for _, case in _all_cases(fixtures):
            assert len(case["articles"]) >= 2, f"{case['id']}: needs >= 2 articles"

    def test_every_article_has_the_facts_the_matcher_needs(self, fixtures):
        for _, case in _all_cases(fixtures):
            for art in case["articles"]:
                missing = REQUIRED_ARTICLE_FIELDS - set(art)
                assert not missing, f"{case['id']}/{art.get('id')}: missing {missing}"

    def test_no_corpus_db_access_required(self, fixtures):
        # Self-contained: every article carries its own facts inline.
        for _, case in _all_cases(fixtures):
            for art in case["articles"]:
                assert isinstance(art["entity_ids"], list)
                assert isinstance(art["title"], str) and art["title"].strip()


class TestContractCoverage:
    """The fixture set must cover every risk class the contract claims to handle."""

    def test_covers_the_flagship_unknown_sport_news_cluster(self, fixtures):
        case = next(c for c in fixtures["true_positive_groups"]
                    if c["id"] == "tp_recanati_federman_ownership")
        # news + a member with sport=unknown AND no entity — must still cluster.
        assert {a["event_type"] for a in case["articles"]} == {"news"}
        assert any(a["sport"] == "unknown" and a["entity_ids"] == []
                   for a in case["articles"])
        assert len({a["source"] for a in case["articles"]}) == 4

    def test_covers_cross_source_signing_with_three_sources(self, fixtures):
        case = next(c for c in fixtures["true_positive_groups"]
                    if c["id"] == "tp_greg_lee_signing")
        assert len({a["source"] for a in case["articles"]}) == 3

    def test_covers_transliteration_variance(self, fixtures):
        case = next(c for c in fixtures["true_positive_groups"]
                    if c["id"] == "tp_cacok_signing_transliteration")
        titles = " ".join(a["title"] for a in case["articles"])
        assert "קייקוק" in titles and "קאקוק" in titles

    def test_covers_formulaic_template_false_positive(self, fixtures):
        case = next(c for c in fixtures["must_not_cluster"]
                    if c["id"] == "fp_formulaic_template")
        assert all("ממשיכה להתחזק" in a["title"] for a in case["articles"])

    def test_covers_youth_qf_vs_sf(self, fixtures):
        assert any(c["id"] == "fp_youth_qf_vs_sf" for c in fixtures["must_not_cluster"])

    def test_covers_cross_sport_hard_reject(self, fixtures):
        case = next(c for c in fixtures["must_not_cluster"]
                    if c["id"] == "fp_cross_sport_maccabi_tlv")
        assert {a["sport"] for a in case["articles"]} == {"basketball", "football"}

    def test_covers_generic_family_name_abstention(self, fixtures):
        case = next(c for c in fixtures["must_not_cluster"]
                    if c["id"] == "fp_bare_family_names_no_entity")
        # Bare family names resolve to no entity (taxonomy abstention, #64).
        assert all(a["entity_ids"] == [] for a in case["articles"])

    def test_covers_same_source_rejection(self, fixtures):
        case = next(c for c in fixtures["must_not_cluster"]
                    if c["id"] == "fp_same_source_pair")
        assert len({a["source"] for a in case["articles"]}) == 1

    def test_covers_transitive_chain_guard(self, fixtures):
        case = next(c for c in fixtures["must_not_cluster"]
                    if c["id"] == "fp_transitive_chain")
        assert len(case["articles"]) == 3
        assert case.get("expected_outcome_detail")

    def test_halaili_saga_is_split_across_three_outcomes(self, fixtures):
        # negotiation cluster + signing cluster + candidate staying separate.
        tp_ids = {c["id"] for c in fixtures["true_positive_groups"]}
        fp_ids = {c["id"] for c in fixtures["must_not_cluster"]}
        assert "tp_halaili_negotiation" in tp_ids
        assert "tp_halaili_signing_medical" in tp_ids
        assert "fp_halaili_candidate_stays_separate" in fp_ids

    def test_covers_inplay_exclusion(self, fixtures):
        excluded = fixtures["excluded_from_candidacy"]
        assert len(excluded) >= 2
        for case in excluded:
            joined = " ".join(a["title"] for a in case["articles"])
            assert "מחצית" in joined or "חי " in joined

    def test_true_positive_groups_are_all_cross_source(self, fixtures):
        # The cross-source hard gate: no TP group may rely on a same-source pair.
        for case in fixtures["true_positive_groups"]:
            sources = [a["source"] for a in case["articles"]]
            assert len(set(sources)) == len(sources), f"{case['id']}: same-source members"

    def test_true_positive_groups_are_single_event_state(self, fixtures):
        # Strict same-event-state: every TP group must already be single-state,
        # which is what makes strictness free.
        for case in fixtures["true_positive_groups"]:
            states = {a["event_type"] for a in case["articles"]}
            assert len(states) == 1, f"{case['id']}: mixed event states {states}"


class TestProvenanceHonesty:
    def test_meta_declares_normalized_timestamps(self, fixtures):
        # The timestamps are synthesized (the corpus was destroyed before absolute
        # times were exported). That must stay stated, not quietly forgotten.
        note = fixtures["_meta"]["honesty_note"]
        assert "NORMALIZED" in note and "delta" in note.lower()

    def test_meta_states_fixtures_do_not_replace_corpus_qa(self, fixtures):
        assert "#102" in fixtures["_meta"]["not_a_substitute_for"]
