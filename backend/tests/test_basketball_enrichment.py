"""
PR 13 — generalized post-merge basketball entity enrichment tests.

enrich_basketball_entities_after_sport_resolve() replaces the Maccabi-only
enrichment. Per entity: positive injection when sport=basketball + phrase
present; negatives for football/unknown sport, football context, football
Maccabi context, and already-present entities. Maccabi semantics must stay
identical to the legacy enrich_maccabi_entity_after_sport_resolve().
"""

import pytest

from app.ingestion.classifier import (
    _BASKETBALL_ENRICHMENT_PHRASES,
    enrich_basketball_entities_after_sport_resolve,
    enrich_maccabi_entity_after_sport_resolve,
)


POSITIVE_CASES = [
    ("מכבי תל אביב מנצחת", "Maccabi Tel Aviv Basketball"),
    ("הפועל תל אביב חתמה על רכז", "Hapoel Tel Aviv Basketball"),
    ("הפועל ירושלים ניצחה בבית", "Hapoel Jerusalem Basketball"),
    ("הפועל חולון מחפשת גארד חדש", "Hapoel Holon"),
    ("בני הרצליה עם הודעה דרמטית", "Bnei Herzliya"),
]


class TestPositiveInjection:
    @pytest.mark.parametrize("title,expected", POSITIVE_CASES)
    def test_injects_entity_for_basketball(self, title, expected):
        entities, injected = enrich_basketball_entities_after_sport_resolve(
            [], title.lower(), "basketball"
        )
        assert expected in entities
        assert injected == [expected] or expected in injected

    def test_derby_title_injects_both_clubs(self):
        title = "דרבי: מכבי תל אביב נגד הפועל תל אביב".lower()
        entities, injected = enrich_basketball_entities_after_sport_resolve(
            [], title, "basketball"
        )
        assert "Maccabi Tel Aviv Basketball" in entities
        assert "Hapoel Tel Aviv Basketball" in entities

    def test_existing_entities_preserved_and_order_stable(self):
        entities, injected = enrich_basketball_entities_after_sport_resolve(
            ["Deni Avdija"], "הפועל חולון מנצחת", "basketball"
        )
        assert entities == ["Deni Avdija", "Hapoel Holon"]
        assert injected == ["Hapoel Holon"]


class TestNegativeGuards:
    @pytest.mark.parametrize("sport", ["football", "unknown", "tennis"])
    @pytest.mark.parametrize("title,_", POSITIVE_CASES)
    def test_never_injects_when_sport_not_basketball(self, title, _, sport):
        entities, injected = enrich_basketball_entities_after_sport_resolve(
            [], title.lower(), sport
        )
        assert entities == []
        assert injected == []

    def test_hapoel_tlv_football_title_no_injection(self):
        # Football article resolved as football — must never get the basketball entity.
        title = "הפועל תל אביב ניצחה בליגת העל בכדורגל".lower()
        entities, injected = enrich_basketball_entities_after_sport_resolve(
            [], title, "football"
        )
        assert entities == []

    def test_football_context_blocks_non_maccabi_injection(self):
        # Even if sport is (incorrectly) basketball, football context words block
        # injection for non-Maccabi clubs — extra-conservative second layer.
        title = "הפועל ירושלים עם חלוץ חדש".lower()
        entities, injected = enrich_basketball_entities_after_sport_resolve(
            [], title, "basketball"
        )
        assert "Hapoel Jerusalem Basketball" not in entities
        assert injected == []

    def test_football_maccabi_context_blocks_everything(self):
        title = "מכבי חיפה נגד הפועל חולון".lower()
        entities, injected = enrich_basketball_entities_after_sport_resolve(
            [], title, "basketball"
        )
        assert entities == []
        assert injected == []

    def test_already_present_entity_not_duplicated(self):
        existing = ["Hapoel Holon"]
        entities, injected = enrich_basketball_entities_after_sport_resolve(
            existing, "הפועל חולון מנצחת", "basketball"
        )
        assert entities is existing
        assert injected == []

    def test_no_phrase_no_injection(self):
        entities, injected = enrich_basketball_entities_after_sport_resolve(
            [], "כתבה כללית על כדורסל ישראלי", "basketball"
        )
        assert entities == []
        assert injected == []

    def test_identity_returned_when_unchanged(self):
        existing: list = []
        entities, injected = enrich_basketball_entities_after_sport_resolve(
            existing, "כתבה כללית", "basketball"
        )
        assert entities is existing


class TestMaccabiBackwardCompatibility:
    """The Maccabi path must behave exactly like the legacy function."""

    MACCABI_TITLES = [
        "מכבי תל אביב מנצחת",
        'מכבי ת"א חתמה על גארד',
        "maccabi tel aviv wins",
        "מכבי חיפה ניצחה",                      # football Maccabi — no injection
        'מכבי תל אביב בכדורגל מול בית"ר',       # football context in title
        "כתבה בלי מכבי בכלל",
    ]

    @pytest.mark.parametrize("title", MACCABI_TITLES)
    @pytest.mark.parametrize("sport", ["basketball", "football", "unknown"])
    @pytest.mark.parametrize("existing", [[], ["Maccabi Tel Aviv Basketball"],
                                          ["Maccabi Tel Aviv Football"]])
    def test_maccabi_injection_matches_legacy(self, title, sport, existing):
        title_lower = title.lower()
        legacy = enrich_maccabi_entity_after_sport_resolve(
            list(existing), title_lower, sport
        )
        new_entities, _ = enrich_basketball_entities_after_sport_resolve(
            list(existing), title_lower, sport
        )
        legacy_has = "Maccabi Tel Aviv Basketball" in legacy
        new_has = "Maccabi Tel Aviv Basketball" in new_entities or (
            "Maccabi Tel Aviv Basketball" in existing
        )
        assert legacy_has == new_has

    def test_maccabi_football_entity_exclusion_preserved(self):
        entities, injected = enrich_basketball_entities_after_sport_resolve(
            ["Maccabi Tel Aviv Football"], "מכבי תל אביב", "basketball"
        )
        assert "Maccabi Tel Aviv Basketball" not in entities
        assert injected == []


class TestEnrichmentPhraseTable:
    def test_expected_entities_in_table(self):
        assert set(_BASKETBALL_ENRICHMENT_PHRASES) == {
            "Maccabi Tel Aviv Basketball",
            "Hapoel Tel Aviv Basketball",
            "Hapoel Jerusalem Basketball",
            "Hapoel Holon",
            "Bnei Herzliya",
        }
