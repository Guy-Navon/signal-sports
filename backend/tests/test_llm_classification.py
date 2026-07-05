"""
Tests for LLM classification module.

All tests use DisabledLLMProvider, FakeLLMProvider, or monkeypatched providers.
No test requires Ollama to be running.
"""

import sys

import pytest
from unittest.mock import MagicMock, patch

from app.classification.entity_normalizer import normalize_llm_entities
from app.classification.llm_result import LLMClassificationResult
from app.classification.merge import merge_with_guardrails
from app.classification.prompt import build_user_message
from app.classification.providers import DisabledLLMProvider, FakeLLMProvider, GeminiLLMProvider, OllamaProvider
from app.classification.validation import parse_and_validate_llm_json
from app.ingestion.classifier import ClassificationResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_rules_result(
    sport="unknown",
    league=None,
    entities=None,
    event_type="news",
    importance="low",
    confidence=0.40,
    tags=None,
) -> ClassificationResult:
    return ClassificationResult(
        sport=sport,
        league=league,
        entities=entities or [],
        event_type=event_type,
        importance=importance,
        confidence=confidence,
        tags=tags or [],
    )


def make_llm_result(
    sport="basketball",
    league=None,
    entities=None,
    event_type="news",
    importance="medium",
    confidence=0.85,
    reason="test",
) -> LLMClassificationResult:
    return LLMClassificationResult(
        sport=sport,
        league=league,
        entities=entities or [],
        event_type=event_type,
        importance=importance,
        confidence=confidence,
        reason=reason,
    )


# ── JSON validation ───────────────────────────────────────────────────────────

class TestValidation:
    def test_valid_json_parsed(self):
        raw = ('{"sport":"basketball","league":"NBA","entities":["Jalen Brunson"],'
               '"event_type":"finals_result","importance":"very_high","confidence":0.92,'
               '"reason":"NBA finals context."}')
        result = parse_and_validate_llm_json(raw)
        assert result is not None
        assert result.sport == "basketball"
        assert result.league == "NBA"
        assert result.confidence == 0.92

    def test_invalid_sport_becomes_unknown(self):
        raw = ('{"sport":"volleyball","league":null,"entities":[],'
               '"event_type":"news","importance":"medium","confidence":0.8,"reason":"x"}')
        result = parse_and_validate_llm_json(raw)
        assert result is not None
        assert result.sport == "unknown"

    def test_invalid_league_becomes_null(self):
        raw = ('{"sport":"basketball","league":"SuperLeague","entities":[],'
               '"event_type":"news","importance":"medium","confidence":0.8,"reason":"x"}')
        result = parse_and_validate_llm_json(raw)
        assert result is not None
        assert result.league is None

    def test_invalid_event_type_becomes_news(self):
        raw = ('{"sport":"basketball","league":"NBA","entities":[],'
               '"event_type":"goal","importance":"medium","confidence":0.8,"reason":"x"}')
        result = parse_and_validate_llm_json(raw)
        assert result is not None
        assert result.event_type == "news"

    def test_release_event_type_is_allowed(self):
        raw = ('{"sport":"basketball","league":"NBA","entities":[],'
               '"event_type":"release","importance":"medium","confidence":0.8,"reason":"x"}')
        result = parse_and_validate_llm_json(raw)
        assert result is not None
        assert result.event_type == "release"

    def test_early_round_result_event_type_is_allowed(self):
        raw = ('{"sport":"tennis","league":"Wimbledon","entities":[],'
               '"event_type":"early_round_result","importance":"low","confidence":0.8,"reason":"x"}')
        result = parse_and_validate_llm_json(raw)
        assert result is not None
        assert result.event_type == "early_round_result"

    def test_unparseable_json_returns_none(self):
        assert parse_and_validate_llm_json("Here is the classification: {...}") is None

    def test_empty_string_returns_none(self):
        assert parse_and_validate_llm_json("") is None

    def test_low_confidence_preserved(self):
        raw = ('{"sport":"basketball","league":"NBA","entities":[],'
               '"event_type":"news","importance":"medium","confidence":0.4,"reason":"x"}')
        result = parse_and_validate_llm_json(raw)
        assert result is not None
        assert result.confidence == 0.4

    def test_confidence_out_of_range_becomes_zero(self):
        raw = ('{"sport":"basketball","league":"NBA","entities":[],'
               '"event_type":"news","importance":"medium","confidence":1.5,"reason":"x"}')
        result = parse_and_validate_llm_json(raw)
        assert result is not None
        assert result.confidence == 0.0

    def test_json_with_preamble_extracted_via_regex(self):
        raw = 'Here is my answer: {"sport":"football","league":null,"entities":[],"event_type":"news","importance":"medium","confidence":0.7,"reason":"football"}'
        result = parse_and_validate_llm_json(raw)
        assert result is not None
        assert result.sport == "football"

    def test_all_allowed_leagues_accepted(self):
        from app.classification.validation import ALLOWED_LEAGUES
        for league in ALLOWED_LEAGUES:
            raw = (f'{{"sport":"basketball","league":"{league}","entities":[],'
                   f'"event_type":"news","importance":"medium","confidence":0.8,"reason":"x"}}')
            result = parse_and_validate_llm_json(raw)
            assert result is not None
            assert result.league == league, f"League {league!r} was not preserved"


# ── Fake provider ─────────────────────────────────────────────────────────────

class TestFakeProvider:
    def test_brunson_mvp_is_known(self):
        provider = FakeLLMProvider()
        result = provider.classify_title(
            "ג'יילן ברונסון ה-MVP של סדרת הגמר: \"בכל פעם, פשוט לקחנו את זה\"",
            language="he",
        )
        assert result is not None
        assert result.sport == "basketball"
        assert result.league == "NBA"
        assert result.confidence >= 0.85

    def test_knicks_champion_is_known(self):
        provider = FakeLLMProvider()
        result = provider.classify_title(
            "ערב היסטורי לברונסון ולניקס: ניו יורק אלופת ה-NBA!",
            language="he",
        )
        assert result is not None
        assert result.event_type == "title_win"
        assert result.importance == "very_high"

    def test_hapoel_tlv_harper_is_known(self):
        provider = FakeLLMProvider()
        result = provider.classify_title(
            "סיכום בהפועל תל אביב? בירושלים לא שחררו את ג'ארד הארפר",
            language="he",
        )
        assert result is not None
        assert result.sport == "basketball"
        assert result.league == "Israeli Basketball League"

    def test_olympiacos_is_known(self):
        provider = FakeLLMProvider()
        result = provider.classify_title(
            "אולימפיאקוס נקצה, ינאקופולוס עצבני אחרי הסערה הגדולה ביוון",
            language="he",
        )
        assert result is not None
        assert result.sport == "basketball"
        assert result.league == "Greek Basket League"

    def test_disabled_provider_returns_none(self):
        provider = DisabledLLMProvider()
        assert provider.can_classify is False
        assert provider.classify_title("anything", "he") is None

    def test_unknown_headline_returns_none(self):
        provider = FakeLLMProvider()
        result = provider.classify_title("כותרת שאיננה בדאטה - לא ידועה כלל", "he")
        assert result is None


# ── Entity normalizer ─────────────────────────────────────────────────────────

class TestEntityNormalizer:
    def test_deni_avdija_hebrew(self):
        assert normalize_llm_entities(["דני אבדיה"], sport="basketball") == ["Deni Avdija"]

    def test_avdija_standalone(self):
        result = normalize_llm_entities(["אבדיה"], sport="basketball")
        assert "Deni Avdija" in result

    def test_deni_standalone_matches(self):
        result = normalize_llm_entities(["deni avdija"], sport="basketball")
        assert "Deni Avdija" in result

    def test_maccabi_tlv_hebrew_variants(self):
        for alias in ["מכבי תל אביב", "maccabi tel aviv", "maccabi tlv"]:
            result = normalize_llm_entities([alias], sport="basketball")
            assert "Maccabi Tel Aviv Basketball" in result, f"Alias {alias!r} not normalized"

    def test_bare_family_names_never_normalize(self):
        # Taxonomy contract: generic family names from the LLM are discarded —
        # bare "מכבי" must never become Maccabi Tel Aviv (Ramat Gan / Kiryat Gat
        # contamination) and bare "הפועל" must never become Hapoel Tel Aviv.
        for family in ["מכבי", "maccabi", "הפועל", "hapoel"]:
            assert normalize_llm_entities([family], sport="basketball") == []

    def test_knicks_hebrew(self):
        result = normalize_llm_entities(["ניקס"], sport="basketball")
        assert "New York Knicks" in result

    def test_knicks_english(self):
        result = normalize_llm_entities(["New York Knicks"], sport="basketball")
        assert "New York Knicks" in result

    def test_hapoel_tlv_basketball_context(self):
        result = normalize_llm_entities(["הפועל תל אביב"], sport="basketball")
        assert "Hapoel Tel Aviv Basketball" in result

    def test_hapoel_tlv_blocked_in_football_context(self):
        result = normalize_llm_entities(["הפועל תל אביב"], sport="football")
        assert "Hapoel Tel Aviv Basketball" not in result
        assert result == []

    def test_hapoel_jerusalem_basketball_context(self):
        result = normalize_llm_entities(["הפועל ירושלים"], sport="basketball")
        assert "Hapoel Jerusalem Basketball" in result

    def test_maccabi_blocked_in_football_context(self):
        result = normalize_llm_entities(["מכבי"], sport="football")
        assert "Maccabi Tel Aviv Basketball" not in result

    def test_unknown_entity_discarded(self):
        result = normalize_llm_entities(["Giannakopoulos", "Unknown Coach"], sport="basketball")
        assert result == []

    def test_deduplication_maintains_order(self):
        result = normalize_llm_entities(["ניקס", "New York Knicks", "ניקס"], sport="basketball")
        assert result.count("New York Knicks") == 1

    def test_multiple_recognized_entities(self):
        result = normalize_llm_entities(["אבדיה", "ניקס"], sport="basketball")
        assert "Deni Avdija" in result
        assert "New York Knicks" in result


# ── Merge with guardrails ─────────────────────────────────────────────────────

class TestMergeWithGuardrails:
    def test_llm_sport_fills_rules_unknown(self):
        rules = make_rules_result(sport="unknown")
        llm = make_llm_result(sport="basketball", league="NBA", confidence=0.90)
        merged, by = merge_with_guardrails(llm, rules, "nba finals")
        assert merged.sport == "basketball"
        assert merged.league == "NBA"
        assert by == "llm"

    def test_guardrail_forces_football_on_maccabi_haifa(self):
        """Rules detected מכבי חיפה (football Maccabi). LLM says basketball. Rules win."""
        rules = make_rules_result(sport="football", confidence=0.85)
        llm = make_llm_result(sport="basketball", league="Israeli Basketball League",
                               confidence=0.70)
        merged, by = merge_with_guardrails(llm, rules, "מכבי חיפה מנצחת",
                                           football_maccabi_detected=True)
        assert merged.sport == "football"
        assert by == "llm+rules_guardrail"

    def test_guardrail_does_not_fire_without_football_maccabi_flag(self):
        """Without football_maccabi_detected=True, LLM sport is not overridden."""
        rules = make_rules_result(sport="football")
        llm = make_llm_result(sport="basketball", confidence=0.80)
        merged, by = merge_with_guardrails(llm, rules, "...", football_maccabi_detected=False)
        assert merged.sport == "basketball"

    def test_importance_never_downgraded(self):
        rules = make_rules_result(importance="very_high")
        llm = make_llm_result(importance="low", confidence=0.85)
        merged, _ = merge_with_guardrails(llm, rules, "maccabi signed a guard")
        assert merged.importance == "very_high"

    def test_rules_event_type_wins_over_llm_news(self):
        """Rules found a specific event type; LLM says 'news' → rules event wins."""
        rules = make_rules_result(event_type="finals_result", importance="very_high")
        llm = make_llm_result(sport="basketball", league="NBA", event_type="news",
                               confidence=0.88)
        merged, by = merge_with_guardrails(llm, rules, "nba finals")
        assert merged.event_type == "finals_result"
        assert by == "llm+rules_guardrail"

    def test_llm_event_type_wins_when_rules_returns_news(self):
        """Rules has event_type=news; LLM has a better one → LLM wins."""
        rules = make_rules_result(event_type="news")
        llm = make_llm_result(sport="basketball", league="NBA", event_type="signing",
                               confidence=0.90)
        merged, _ = merge_with_guardrails(llm, rules, "maccabi signed a guard")
        assert merged.event_type == "signing"

    def test_llm_league_fills_rules_none(self):
        rules = make_rules_result(sport="basketball", league=None)
        llm = make_llm_result(sport="basketball", league="NBA", confidence=0.90)
        merged, _ = merge_with_guardrails(llm, rules, "...")
        assert merged.league == "NBA"

    def test_rules_league_fills_llm_null(self):
        rules = make_rules_result(sport="basketball", league="EuroLeague")
        llm = make_llm_result(sport="basketball", league=None, confidence=0.88)
        merged, by = merge_with_guardrails(llm, rules, "...")
        assert merged.league == "EuroLeague"
        assert by == "llm+rules_guardrail"

    def test_recognized_llm_entity_added_to_entities(self):
        """LLM entity 'אבדיה' is normalized and added to article.entities."""
        rules = make_rules_result(sport="basketball", entities=[])
        llm = make_llm_result(sport="basketball", entities=["אבדיה"], confidence=0.90)
        merged, _ = merge_with_guardrails(llm, rules, "...")
        assert "Deni Avdija" in merged.entities

    def test_unknown_llm_entity_discarded(self):
        """Free-text LLM entity not in canonical map is not added."""
        rules = make_rules_result(entities=["Maccabi Tel Aviv Basketball"], sport="basketball")
        llm = make_llm_result(entities=["Maccabi TLV", "Shlomi Avduh"], confidence=0.90,
                               sport="basketball")
        merged, _ = merge_with_guardrails(llm, rules, "...")
        assert "Maccabi Tel Aviv Basketball" in merged.entities
        assert "Maccabi TLV" not in merged.entities
        assert "Shlomi Avduh" not in merged.entities

    def test_basketball_club_entity_blocked_in_football(self):
        """הפועל תל אביב not added to entities when merged sport=football."""
        rules = make_rules_result(sport="football")
        llm = make_llm_result(sport="football", entities=["הפועל תל אביב"], confidence=0.85)
        merged, _ = merge_with_guardrails(llm, rules, "...", football_maccabi_detected=True)
        assert "Hapoel Tel Aviv Basketball" not in merged.entities

    def test_knicks_entity_normalized_from_hebrew(self):
        """'ניקס' → 'New York Knicks' via normalization."""
        rules = make_rules_result(sport="basketball", entities=[])
        llm = make_llm_result(sport="basketball", league="NBA",
                               entities=["ניקס", "Jalen Brunson"], confidence=0.90)
        merged, _ = merge_with_guardrails(llm, rules, "...")
        assert "New York Knicks" in merged.entities
        # Jalen Brunson became canonical in PR 13
        assert "Jalen Brunson" in merged.entities

    def test_unknown_entity_still_discarded(self):
        """Entities absent from the canonical map are silently dropped."""
        rules = make_rules_result(sport="basketball", entities=[])
        llm = make_llm_result(sport="basketball", league="NBA",
                               entities=["ניקס", "Some Unknown Rookie"], confidence=0.90)
        merged, _ = merge_with_guardrails(llm, rules, "...")
        assert merged.entities == ["New York Knicks"]

    def test_entity_order_is_deterministic(self):
        """Rules entities come first, then LLM-recognized additions, in stable order."""
        rules = make_rules_result(entities=["Maccabi Tel Aviv Basketball"], sport="basketball")
        llm = make_llm_result(entities=["אבדיה", "ניקס"], sport="basketball", confidence=0.90)
        merged1, _ = merge_with_guardrails(llm, rules, "...")
        merged2, _ = merge_with_guardrails(llm, rules, "...")
        assert merged1.entities == merged2.entities
        assert merged1.entities[0] == "Maccabi Tel Aviv Basketball"

    def test_rules_entities_not_duplicated_by_llm(self):
        """If LLM returns an alias for an entity already in rules, no duplicate."""
        rules = make_rules_result(entities=["Maccabi Tel Aviv Basketball"], sport="basketball")
        llm = make_llm_result(entities=["מכבי"], sport="basketball", confidence=0.90)
        merged, _ = merge_with_guardrails(llm, rules, "...")
        assert merged.entities.count("Maccabi Tel Aviv Basketball") == 1

    def test_no_guardrail_when_all_agree(self):
        """When LLM and rules agree on everything, classified_by is 'llm'."""
        rules = make_rules_result(sport="basketball", league="NBA",
                                  event_type="signing", importance="high")
        llm = make_llm_result(sport="basketball", league="NBA",
                               event_type="signing", importance="high", confidence=0.92)
        _, by = merge_with_guardrails(llm, rules, "maccabi signed a guard")
        assert by == "llm"

    # ── Entity pruning (sport compatibility) ──────────────────────────────────

    def test_football_article_prunes_maccabi_basketball_from_rules(self):
        """Rules added Maccabi TLV Basketball from ambiguous 'מכבי'; final sport=football → pruned."""
        rules = make_rules_result(
            sport="football", entities=["Maccabi Tel Aviv Basketball"]
        )
        llm = make_llm_result(sport="football", confidence=0.88)
        merged, _ = merge_with_guardrails(llm, rules, "מכבי חיפה",
                                          football_maccabi_detected=True)
        assert merged.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in merged.entities

    def test_football_article_prunes_hapoel_tlv_basketball_from_rules(self):
        """Rules added Hapoel TLV Basketball from ambiguous 'הפועל תל אביב'; final sport=football → pruned."""
        rules = make_rules_result(
            sport="football", entities=["Hapoel Tel Aviv Basketball"]
        )
        llm = make_llm_result(sport="football", confidence=0.88)
        merged, _ = merge_with_guardrails(llm, rules, "הפועל תל אביב")
        assert merged.sport == "football"
        assert "Hapoel Tel Aviv Basketball" not in merged.entities

    def test_football_article_prunes_hapoel_jerusalem_basketball_from_rules(self):
        """All three basketball club entities pruned when final sport=football."""
        rules = make_rules_result(
            sport="football",
            entities=["Hapoel Jerusalem Basketball", "Maccabi Tel Aviv Basketball"]
        )
        llm = make_llm_result(sport="football", confidence=0.85)
        merged, _ = merge_with_guardrails(llm, rules, "...")
        assert "Hapoel Jerusalem Basketball" not in merged.entities
        assert "Maccabi Tel Aviv Basketball" not in merged.entities

    def test_basketball_article_keeps_basketball_club_entities(self):
        """sport=basketball — no pruning occurs."""
        rules = make_rules_result(
            sport="basketball", entities=["Maccabi Tel Aviv Basketball"]
        )
        llm = make_llm_result(sport="basketball", league="EuroLeague", confidence=0.90)
        merged, _ = merge_with_guardrails(llm, rules, "...")
        assert "Maccabi Tel Aviv Basketball" in merged.entities

    def test_tags_do_not_contain_pruned_basketball_entity(self):
        """Tags are recomputed after pruning — no basketball tags on football article."""
        rules = make_rules_result(
            sport="football", entities=["Maccabi Tel Aviv Basketball"],
            tags=["basketball", "maccabi"]
        )
        llm = make_llm_result(sport="football", confidence=0.85)
        merged, _ = merge_with_guardrails(llm, rules, "מכבי חיפה",
                                          football_maccabi_detected=True)
        assert merged.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in merged.entities
        # Tags are recomputed from the pruned entity list
        assert "maccabi" not in merged.tags or merged.tags.count("maccabi") == 0

    # ── Guardrail 4b: LLM title_win without championship evidence ─────────────

    def test_guardrail_4b_title_win_no_evidence_rejected(self):
        """LLM title_win for a fluff article with no championship keyword → fallback to rules."""
        rules = make_rules_result(event_type="news")
        llm = make_llm_result(sport="football", event_type="title_win", importance="very_high",
                               confidence=0.85)
        title = '"התפרקו, אני שחקן נבחרת": צפו ברגע המביך במחנה של ספרד'
        merged, by = merge_with_guardrails(llm, rules, title.lower())
        assert merged.event_type != "title_win"
        assert by == "llm+rules_guardrail"

    def test_guardrail_4b_title_win_with_alufat_kept(self):
        """LLM title_win where title contains 'אלופת' → championship evidence present → kept."""
        rules = make_rules_result(event_type="news")
        llm = make_llm_result(sport="basketball", league="NBA", event_type="title_win",
                               importance="very_high", confidence=0.95)
        title = "ניו יורק אלופת ה-NBA!"
        merged, _ = merge_with_guardrails(llm, rules, title.lower())
        assert merged.event_type == "title_win"

    def test_guardrail_4b_title_win_with_gabia_kept(self):
        """LLM title_win where title contains 'גביע' → championship evidence present → kept."""
        rules = make_rules_result(event_type="news")
        llm = make_llm_result(sport="basketball", event_type="title_win",
                               importance="very_high", confidence=0.90)
        title = "מכבי תל אביב זכה בגביע"
        merged, _ = merge_with_guardrails(llm, rules, title.lower())
        assert merged.event_type == "title_win"

    def test_guardrail_4b_champion_in_title_kept(self):
        """LLM title_win with English 'champion' → evidence present → kept."""
        rules = make_rules_result(event_type="news")
        llm = make_llm_result(sport="basketball", league="NBA", event_type="title_win",
                               confidence=0.90)
        title = "Boston Celtics are NBA champions"
        merged, _ = merge_with_guardrails(llm, rules, title.lower())
        assert merged.event_type == "title_win"

    # ── Guardrail 6: League-sport compatibility ───────────────────────────────

    def test_guardrail_6_spanish_acb_forces_basketball(self):
        """LLM returns sport=football + league=Spanish ACB → impossible → sport corrected."""
        rules = make_rules_result(sport="basketball", league="Spanish ACB")
        llm = make_llm_result(sport="football", league="Spanish ACB", confidence=0.80)
        merged, by = merge_with_guardrails(llm, rules, "...")
        assert merged.sport == "basketball"
        assert merged.league == "Spanish ACB"
        assert by == "llm+rules_guardrail"

    def test_guardrail_6_euroleague_forces_basketball(self):
        """LLM returns sport=football + league=EuroLeague → sport corrected to basketball."""
        rules = make_rules_result(sport="basketball", league="EuroLeague")
        llm = make_llm_result(sport="football", league="EuroLeague", confidence=0.78)
        merged, by = merge_with_guardrails(llm, rules, "יורוליג")
        assert merged.sport == "basketball"
        assert by == "llm+rules_guardrail"

    def test_guardrail_6_nba_forces_basketball(self):
        """LLM returns sport=football + league=NBA → sport corrected to basketball."""
        rules = make_rules_result(sport="basketball", league="NBA")
        llm = make_llm_result(sport="football", league="NBA", confidence=0.75)
        merged, by = merge_with_guardrails(llm, rules, "...")
        assert merged.sport == "basketball"

    def test_guardrail_6_israeli_premier_league_forces_football(self):
        """LLM returns sport=basketball + league=Israeli Premier League → sport corrected."""
        rules = make_rules_result(sport="football", league="Israeli Premier League")
        llm = make_llm_result(sport="basketball", league="Israeli Premier League", confidence=0.80)
        merged, by = merge_with_guardrails(llm, rules, "...")
        assert merged.sport == "football"
        assert by == "llm+rules_guardrail"

    def test_guardrail_6_null_league_no_sport_override(self):
        """Null league does not force any sport change."""
        rules = make_rules_result(sport="unknown", league=None)
        llm = make_llm_result(sport="football", league=None, confidence=0.80)
        merged, _ = merge_with_guardrails(llm, rules, "...")
        assert merged.sport == "football"

    def test_guardrail_6_entity_pruning_runs_after_sport_correction(self):
        """After Guardrail 6 corrects sport to basketball, basketball entities are kept."""
        rules = make_rules_result(
            sport="basketball", league="EuroLeague",
            entities=["Maccabi Tel Aviv Basketball"],
        )
        llm = make_llm_result(sport="football", league="EuroLeague", confidence=0.78,
                               entities=["Real Madrid"])
        merged, _ = merge_with_guardrails(llm, rules, "יורוליג")
        assert merged.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in merged.entities

    # ── Guardrail 7: Source URL category hint ─────────────────────────────────

    def test_guardrail_7_basketball_hint_overrides_llm_football(self):
        """source_sport_hint=basketball overrides LLM sport=football."""
        rules = make_rules_result(sport="unknown")
        llm = make_llm_result(sport="football", confidence=0.80)
        merged, by = merge_with_guardrails(llm, rules, "...",
                                            source_sport_hint="basketball")
        assert merged.sport == "basketball"
        assert by == "llm+rules_guardrail"

    def test_guardrail_7_football_hint_overrides_llm_basketball(self):
        """source_sport_hint=football overrides LLM sport=basketball."""
        rules = make_rules_result(sport="unknown")
        llm = make_llm_result(sport="basketball", league="Israeli Basketball League",
                               confidence=0.80)
        merged, by = merge_with_guardrails(llm, rules, "...",
                                            source_sport_hint="football")
        assert merged.sport == "football"
        assert by == "llm+rules_guardrail"

    def test_guardrail_7_none_hint_does_not_override(self):
        """source_sport_hint=None leaves LLM sport unchanged."""
        rules = make_rules_result(sport="unknown")
        llm = make_llm_result(sport="football", confidence=0.85)
        merged, _ = merge_with_guardrails(llm, rules, "...", source_sport_hint=None)
        assert merged.sport == "football"

    def test_guardrail_7_matching_hint_does_not_set_guardrail_fired(self):
        """When hint agrees with LLM sport, guardrail is not fired unnecessarily."""
        rules = make_rules_result(sport="unknown")
        llm = make_llm_result(sport="basketball", confidence=0.85)
        merged, by = merge_with_guardrails(llm, rules, "...",
                                            source_sport_hint="basketball")
        assert merged.sport == "basketball"
        assert by == "llm"  # no guardrail fired


# ── normalize_league_sport_compatibility() — rules-only path ──────────────────

class TestNormalizeLeagueSportCompat:
    """normalize_league_sport_compatibility() catches impossible combos on the rules-only path."""

    from app.classification.merge import normalize_league_sport_compatibility

    def _result(self, sport, league="EuroLeague", **kw):
        return ClassificationResult(
            sport=sport, league=league,
            entities=kw.get("entities", []),
            event_type=kw.get("event_type", "news"),
            importance=kw.get("importance", "medium"),
            confidence=kw.get("confidence", 0.60),
            tags=kw.get("tags", []),
        )

    def test_football_plus_euroleague_corrected(self):
        from app.classification.merge import normalize_league_sport_compatibility
        r = normalize_league_sport_compatibility(self._result("football", "EuroLeague"))
        assert r.sport == "basketball"
        assert r.league == "EuroLeague"

    def test_football_plus_nba_corrected(self):
        from app.classification.merge import normalize_league_sport_compatibility
        r = normalize_league_sport_compatibility(self._result("football", "NBA"))
        assert r.sport == "basketball"

    def test_football_plus_spanish_acb_corrected(self):
        from app.classification.merge import normalize_league_sport_compatibility
        r = normalize_league_sport_compatibility(self._result("football", "Spanish ACB"))
        assert r.sport == "basketball"

    def test_basketball_plus_israeli_premier_corrected(self):
        from app.classification.merge import normalize_league_sport_compatibility
        r = normalize_league_sport_compatibility(
            self._result("basketball", "Israeli Premier League")
        )
        assert r.sport == "football"

    def test_null_league_no_override(self):
        from app.classification.merge import normalize_league_sport_compatibility
        r = normalize_league_sport_compatibility(self._result("football", league=None))
        assert r.sport == "football"

    def test_valid_combination_unchanged(self):
        from app.classification.merge import normalize_league_sport_compatibility
        r = normalize_league_sport_compatibility(self._result("basketball", "EuroLeague"))
        assert r.sport == "basketball"
        assert r.league == "EuroLeague"

    def test_all_basketball_leagues_force_sport(self):
        from app.classification.merge import normalize_league_sport_compatibility, _BASKETBALL_LEAGUES
        for league in _BASKETBALL_LEAGUES:
            r = normalize_league_sport_compatibility(self._result("football", league))
            assert r.sport == "basketball", f"Expected basketball for league {league!r}"

    def test_returns_new_instance_on_correction(self):
        from app.classification.merge import normalize_league_sport_compatibility
        original = self._result("football", "EuroLeague")
        corrected = normalize_league_sport_compatibility(original)
        assert corrected is not original
        assert original.sport == "football"  # original unchanged

    def test_returns_same_instance_when_no_correction(self):
        from app.classification.merge import normalize_league_sport_compatibility
        r = self._result("basketball", "EuroLeague")
        assert normalize_league_sport_compatibility(r) is r


# ── Backfill endpoint ─────────────────────────────────────────────────────────

class TestBackfill:
    def test_backfill_updates_sport_league_event_type(self, client, rss_seeded):
        """Backfill with fake provider changes core classification fields on existing articles."""
        import os
        os.environ["CLASSIFICATION_PROVIDER"] = "fake"

        # First insert a walla_sport article with sport=unknown (simulating rules-only path)
        from app.db.database import SessionLocal
        from app.models.article import Article
        from app.repositories.article_repository import insert, get_by_id
        from datetime import datetime, timezone

        test_article = Article(
            id="rss_backfill_test_001",
            source="walla_sport",
            source_display_name="וואלה ספורט",
            url="https://sports.walla.co.il/test/backfill001",
            title="ג'יילן ברונסון ה-MVP של סדרת הגמר: \"בכל פעם, פשוט לקחנו את זה\"",
            language="he",
            published_at=datetime.now(tz=timezone.utc),
            sport="unknown",
            league=None,
            entities=[],
            event_type="news",
            importance="low",
            confidence=0.40,
            tags=[],
            classified_by="rules",
        )

        with SessionLocal() as session:
            if get_by_id(session, test_article.id) is None:
                insert(session, test_article)

        # Run backfill with fake provider
        resp = client.post("/api/classify/backfill?source_id=walla_sport&dry_run=false")
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] >= 1

        with SessionLocal() as session:
            updated = get_by_id(session, test_article.id)

        assert updated is not None
        assert updated.sport == "basketball"
        assert updated.league == "NBA"
        assert updated.classified_by in ("llm", "llm+rules_guardrail")

        # Cleanup
        del os.environ["CLASSIFICATION_PROVIDER"]

    def test_backfill_source_id_filter_applied_at_query(self, client, rss_seeded):
        """source_id filter is applied in the DB query, not in Python post-filter."""
        import os
        os.environ["CLASSIFICATION_PROVIDER"] = "fake"

        from app.db.database import SessionLocal
        from app.models.article import Article
        from app.repositories.article_repository import insert, get_by_id
        from datetime import datetime, timezone

        # Insert a eurohoops article — must NOT be touched by walla_sport backfill
        euro_article = Article(
            id="rss_backfill_test_euro_001",
            source="eurohoops",
            source_display_name="Eurohoops",
            url="https://eurohoops.net/test/backfill001",
            title="Olympiacos beats Panathinaikos",
            language="en",
            published_at=datetime.now(tz=timezone.utc),
            sport="basketball",
            league="EuroLeague",
            entities=[],
            event_type="match_result",
            importance="medium",
            confidence=0.75,
            tags=["basketball", "EuroLeague"],
            classified_by="rules",
        )

        with SessionLocal() as session:
            if get_by_id(session, euro_article.id) is None:
                insert(session, euro_article)

        # Run backfill filtered to walla_sport only
        resp = client.post("/api/classify/backfill?source_id=walla_sport&dry_run=true")
        assert resp.status_code == 200

        # The eurohoops article classified_by should be unchanged
        with SessionLocal() as session:
            unchanged = get_by_id(session, euro_article.id)
        assert unchanged is not None
        assert unchanged.classified_by == "rules"  # untouched

        del os.environ["CLASSIFICATION_PROVIDER"]

    def test_backfill_dry_run_does_not_write(self, client, rss_seeded):
        """dry_run=true returns counts but makes no DB changes."""
        import os
        os.environ["CLASSIFICATION_PROVIDER"] = "fake"

        from app.db.database import SessionLocal
        from app.models.article import Article
        from app.repositories.article_repository import insert, get_by_id
        from datetime import datetime, timezone

        dry_article = Article(
            id="rss_backfill_dryrun_001",
            source="walla_sport",
            source_display_name="וואלה ספורט",
            url="https://sports.walla.co.il/test/dryrun001",
            title="כותרת ייחודית לבדיקת dry run",
            language="he",
            published_at=datetime.now(tz=timezone.utc),
            sport="unknown",
            league=None,
            entities=[],
            event_type="news",
            importance="low",
            confidence=0.40,
            tags=[],
            classified_by="rules",
        )

        with SessionLocal() as session:
            if get_by_id(session, dry_article.id) is None:
                insert(session, dry_article)

        resp = client.post("/api/classify/backfill?source_id=walla_sport&dry_run=true")
        assert resp.status_code == 200
        assert resp.json()["dry_run"] is True

        with SessionLocal() as session:
            after = get_by_id(session, dry_article.id)
        assert after is not None
        assert after.sport == "unknown"  # unchanged — dry_run did not write
        assert after.classified_by == "rules"

        del os.environ["CLASSIFICATION_PROVIDER"]

    def test_backfill_skips_already_llm_classified_when_force_false(self, client, rss_seeded):
        """Articles with classified_by=llm are skipped unless force=true."""
        import os
        os.environ["CLASSIFICATION_PROVIDER"] = "fake"

        from app.db.database import SessionLocal
        from app.models.article import Article
        from app.repositories.article_repository import insert, get_by_id, update_full_classification
        from datetime import datetime, timezone

        already_llm = Article(
            id="rss_backfill_already_llm_001",
            source="walla_sport",
            source_display_name="וואלה ספורט",
            url="https://sports.walla.co.il/test/alreadyllm001",
            title="כותרת שכבר סווגה על ידי LLM",
            language="he",
            published_at=datetime.now(tz=timezone.utc),
            sport="basketball",
            league="NBA",
            entities=[],
            event_type="news",
            importance="medium",
            confidence=0.90,
            tags=["basketball", "NBA"],
            classified_by="llm",
            classification_provider="fake",
        )

        with SessionLocal() as session:
            if get_by_id(session, already_llm.id) is None:
                insert(session, already_llm)

        resp = client.post("/api/classify/backfill?source_id=walla_sport&force=false&dry_run=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped_already_classified"] >= 1

        del os.environ["CLASSIFICATION_PROVIDER"]


# ── Gemini provider ───────────────────────────────────────────────────────────

class TestGeminiLLMProvider:
    """
    GeminiLLMProvider tests — google.genai is always mocked via monkeypatch.
    No test makes a real Gemini API call.
    """

    def _make_provider(self, monkeypatch, model="gemini-2.5-flash-lite"):
        """
        Inject MagicMocks for both google and google.genai and instantiate GeminiLLMProvider.
        monkeypatch restores sys.modules after the test.
        Returns (provider, mock_genai_module).
        """
        mock_genai = MagicMock()
        mock_google = MagicMock()
        mock_google.genai = mock_genai
        monkeypatch.setitem(sys.modules, "google", mock_google)
        monkeypatch.setitem(sys.modules, "google.genai", mock_genai)
        monkeypatch.setitem(sys.modules, "google.genai.types", mock_genai.types)
        provider = GeminiLLMProvider(api_key="test-key", model=model)
        # provider._client == mock_genai.Client.return_value
        return provider, mock_genai

    def test_provider_id_includes_model(self, monkeypatch):
        provider, _ = self._make_provider(monkeypatch)
        assert provider.provider_id == "gemini:gemini-2.5-flash-lite"

    def test_custom_model_reflected_in_provider_id(self, monkeypatch):
        provider, _ = self._make_provider(monkeypatch, model="gemini-2.0-flash")
        assert provider.provider_id == "gemini:gemini-2.0-flash"

    def test_can_classify_is_true(self, monkeypatch):
        provider, _ = self._make_provider(monkeypatch)
        assert provider.can_classify is True

    def test_valid_response_returns_result(self, monkeypatch):
        provider, _ = self._make_provider(monkeypatch)
        mock_response = MagicMock()
        mock_response.text = (
            '{"sport":"basketball","league":"NBA","entities":["New York Knicks"],'
            '"event_type":"title_win","importance":"very_high","confidence":0.95,'
            '"reason":"Knicks win the NBA championship."}'
        )
        provider._client.models.generate_content.return_value = mock_response

        result = provider.classify_title("ניו יורק ניקס אלופות ה-NBA", "he")

        assert result is not None
        assert result.sport == "basketball"
        assert result.league == "NBA"
        assert result.event_type == "title_win"
        assert result.confidence == 0.95

    def test_api_exception_returns_none(self, monkeypatch):
        provider, _ = self._make_provider(monkeypatch)
        provider._client.models.generate_content.side_effect = Exception("Quota exceeded")

        result = provider.classify_title("כותרת", "he")

        assert result is None

    def test_unparseable_response_returns_none(self, monkeypatch):
        provider, _ = self._make_provider(monkeypatch)
        mock_response = MagicMock()
        mock_response.text = "I cannot classify this headline at this time."
        provider._client.models.generate_content.return_value = mock_response

        result = provider.classify_title("כותרת", "he")

        assert result is None

    def test_generate_content_called_once_per_classify(self, monkeypatch):
        provider, _ = self._make_provider(monkeypatch)
        mock_response = MagicMock()
        mock_response.text = (
            '{"sport":"football","league":null,"entities":[],"event_type":"news",'
            '"importance":"medium","confidence":0.75,"reason":"football context."}'
        )
        provider._client.models.generate_content.return_value = mock_response

        provider.classify_title("מכבי חיפה נגד מכבי תל אביב", "he")

        provider._client.models.generate_content.assert_called_once()

    def test_result_entities_list_preserved(self, monkeypatch):
        provider, _ = self._make_provider(monkeypatch)
        mock_response = MagicMock()
        mock_response.text = (
            '{"sport":"basketball","league":"EuroLeague","entities":["Maccabi Tel Aviv Basketball"],'
            '"event_type":"signing","importance":"high","confidence":0.93,'
            '"reason":"Maccabi TLV EuroLeague signing."}'
        )
        provider._client.models.generate_content.return_value = mock_response

        result = provider.classify_title('מכבי ת"א חתמה על גארד יורוליג', "he")

        assert result is not None
        assert "Maccabi Tel Aviv Basketball" in result.entities

    def test_retries_once_on_rate_limit_and_succeeds(self, monkeypatch):
        """429 triggers one sleep+retry; second attempt succeeds."""
        import time as time_module
        provider, _ = self._make_provider(monkeypatch)

        mock_response = MagicMock()
        mock_response.text = (
            '{"sport":"basketball","league":"NBA","entities":[],'
            '"event_type":"news","importance":"medium","confidence":0.85,"reason":"ok"}'
        )
        rate_limit_exc = Exception("429 RESOURCE_EXHAUSTED. 'retryDelay': '3s'")
        provider._client.models.generate_content.side_effect = [rate_limit_exc, mock_response]

        sleep_calls = []
        monkeypatch.setattr(time_module, "sleep", lambda s: sleep_calls.append(s))

        result = provider.classify_title("כותרת", "he")

        assert result is not None
        assert result.sport == "basketball"
        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(3.0, abs=0.1)
        assert provider._client.models.generate_content.call_count == 2

    def test_no_retry_on_non_rate_limit_error(self, monkeypatch):
        """503 and other non-429 errors are not retried."""
        provider, _ = self._make_provider(monkeypatch)
        provider._client.models.generate_content.side_effect = Exception("503 UNAVAILABLE")

        result = provider.classify_title("כותרת", "he")

        assert result is None
        provider._client.models.generate_content.assert_called_once()

    def test_returns_none_if_retry_also_fails(self, monkeypatch):
        """If the retry after 429 also fails, returns None without a third attempt."""
        import time as time_module
        provider, _ = self._make_provider(monkeypatch)

        exc1 = Exception("429 RESOURCE_EXHAUSTED. 'retryDelay': '1s'")
        exc2 = Exception("429 RESOURCE_EXHAUSTED. 'retryDelay': '60s'")
        provider._client.models.generate_content.side_effect = [exc1, exc2]
        monkeypatch.setattr(time_module, "sleep", lambda s: None)

        result = provider.classify_title("כותרת", "he")

        assert result is None
        assert provider._client.models.generate_content.call_count == 2

    def test_subtitle_included_in_contents_when_provided(self, monkeypatch):
        """Subtitle is passed through to generate_content contents field."""
        provider, _ = self._make_provider(monkeypatch)
        mock_response = MagicMock()
        mock_response.text = (
            '{"sport":"basketball","league":"EuroLeague","entities":[],'
            '"event_type":"signing","importance":"high","confidence":0.91,'
            '"reason":"EuroLeague signing with subtitle context."}'
        )
        provider._client.models.generate_content.return_value = mock_response

        provider.classify_title("כותרת עמומה", "he", subtitle="שחקן חדש מהיורוליג")

        call_kwargs = provider._client.models.generate_content.call_args
        contents_arg = call_kwargs[1].get("contents") or call_kwargs[0][1]
        assert "Subtitle: שחקן חדש מהיורוליג" in contents_arg

    def test_no_subtitle_sends_headline_only(self, monkeypatch):
        """Without subtitle, only Headline: prefix is sent to Gemini."""
        provider, _ = self._make_provider(monkeypatch)
        mock_response = MagicMock()
        mock_response.text = (
            '{"sport":"basketball","league":null,"entities":[],'
            '"event_type":"news","importance":"medium","confidence":0.80,"reason":"ok"}'
        )
        provider._client.models.generate_content.return_value = mock_response

        provider.classify_title("כותרת", "he")

        call_kwargs = provider._client.models.generate_content.call_args
        contents_arg = call_kwargs[1].get("contents") or call_kwargs[0][1]
        assert "Headline: כותרת" in contents_arg
        assert "Subtitle:" not in contents_arg


# ── Service factory ───────────────────────────────────────────────────────────

class TestServiceFactory:
    """
    Tests for get_llm_provider() factory in service.py.
    All gemini tests mock google.genai to avoid requiring the real package at test time.
    """

    def _mock_google(self, monkeypatch):
        """Inject google.genai mock into sys.modules. Returns mock_genai."""
        mock_genai = MagicMock()
        mock_google = MagicMock()
        mock_google.genai = mock_genai
        monkeypatch.setitem(sys.modules, "google", mock_google)
        monkeypatch.setitem(sys.modules, "google.genai", mock_genai)
        monkeypatch.setitem(sys.modules, "google.genai.types", mock_genai.types)
        return mock_genai

    def test_gemini_provider_created_with_api_key(self, monkeypatch):
        monkeypatch.setenv("CLASSIFICATION_PROVIDER", "gemini")
        monkeypatch.setenv("CLASSIFICATION_API_KEY", "test-api-key")
        monkeypatch.setenv("CLASSIFICATION_MODEL", "gemini-2.5-flash-lite")
        self._mock_google(monkeypatch)

        from app.classification.service import get_llm_provider
        provider = get_llm_provider()

        assert isinstance(provider, GeminiLLMProvider)
        assert provider.can_classify is True
        assert provider.provider_id == "gemini:gemini-2.5-flash-lite"

    def test_gemini_falls_back_to_disabled_without_api_key(self, monkeypatch):
        monkeypatch.setenv("CLASSIFICATION_PROVIDER", "gemini")
        monkeypatch.delenv("CLASSIFICATION_API_KEY", raising=False)

        from app.classification.service import get_llm_provider
        provider = get_llm_provider()

        assert isinstance(provider, DisabledLLMProvider)
        assert provider.can_classify is False

    def test_gemini_default_model_is_flash_lite(self, monkeypatch):
        monkeypatch.setenv("CLASSIFICATION_PROVIDER", "gemini")
        monkeypatch.setenv("CLASSIFICATION_API_KEY", "test-key")
        monkeypatch.delenv("CLASSIFICATION_MODEL", raising=False)
        self._mock_google(monkeypatch)

        from app.classification.service import get_llm_provider
        provider = get_llm_provider()

        assert provider.provider_id == "gemini:gemini-2.5-flash-lite"

    def test_ollama_provider_still_returned(self, monkeypatch):
        from app.classification.providers import OllamaProvider
        monkeypatch.setenv("CLASSIFICATION_PROVIDER", "ollama")
        monkeypatch.setenv("CLASSIFICATION_MODEL", "llama3.2:3b")

        from app.classification.service import get_llm_provider
        provider = get_llm_provider()

        assert isinstance(provider, OllamaProvider)
        assert provider.provider_id == "ollama:llama3.2:3b"

    def test_fake_provider_still_returned(self, monkeypatch):
        monkeypatch.setenv("CLASSIFICATION_PROVIDER", "fake")

        from app.classification.service import get_llm_provider
        provider = get_llm_provider()

        assert isinstance(provider, FakeLLMProvider)

    def test_disabled_is_default(self, monkeypatch):
        monkeypatch.delenv("CLASSIFICATION_PROVIDER", raising=False)

        from app.classification.service import get_llm_provider
        provider = get_llm_provider()

        assert isinstance(provider, DisabledLLMProvider)
        assert provider.can_classify is False


# ── Subtitle in prompt ────────────────────────────────────────────────────────

class TestSubtitleInPrompt:
    def test_title_only_produces_headline_only_message(self):
        msg = build_user_message("מכבי זכתה")
        assert msg == "Headline: מכבי זכתה"
        assert "Subtitle:" not in msg

    def test_title_and_subtitle_both_included(self):
        msg = build_user_message("מכבי זכתה", subtitle="זכיה בגביע האירולייג")
        assert "Headline: מכבי זכתה" in msg
        assert "Subtitle: זכיה בגביע האירולייג" in msg

    def test_none_subtitle_produces_headline_only(self):
        assert build_user_message("כותרת", subtitle=None) == build_user_message("כותרת")

    def test_empty_string_subtitle_omitted(self):
        msg = build_user_message("כותרת", subtitle="")
        assert "Subtitle:" not in msg

    def test_subtitle_appears_after_headline(self):
        msg = build_user_message("א", subtitle="ב")
        headline_pos = msg.index("Headline:")
        subtitle_pos = msg.index("Subtitle:")
        assert subtitle_pos > headline_pos

    def test_subtitle_content_not_interpreted_as_json(self):
        msg = build_user_message("title", subtitle='{"key": "value"}')
        assert 'Subtitle: {"key": "value"}' in msg


# ── Ollama provider ───────────────────────────────────────────────────────────

_VALID_OLLAMA_JSON = (
    '{"sport":"basketball","league":"EuroLeague","entities":["Maccabi Tel Aviv Basketball"],'
    '"event_type":"signing","importance":"high","confidence":0.93,"reason":"Maccabi signing."}'
)


class TestOllamaProvider:
    def _make_provider(self) -> OllamaProvider:
        return OllamaProvider(
            base_url="http://localhost:11434",
            model="qwen2.5:3b-instruct",
            timeout=15.0,
        )

    def _mock_response(self, json_text: str) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": json_text}}
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    def test_provider_id_includes_model(self):
        provider = self._make_provider()
        assert provider.provider_id == "ollama:qwen2.5:3b-instruct"

    def test_can_classify_is_true(self):
        assert self._make_provider().can_classify is True

    def test_classify_sends_headline_only_when_no_subtitle(self, monkeypatch):
        provider = self._make_provider()
        captured = {}

        def fake_post(url, json, timeout):
            captured["user_msg"] = json["messages"][1]["content"]
            return self._mock_response(_VALID_OLLAMA_JSON)

        monkeypatch.setattr("httpx.post", fake_post)
        provider.classify_title("מכבי חתמה על שחקן", "he")

        assert captured["user_msg"] == "Headline: מכבי חתמה על שחקן"
        assert "Subtitle:" not in captured["user_msg"]

    def test_classify_sends_subtitle_when_provided(self, monkeypatch):
        provider = self._make_provider()
        captured = {}

        def fake_post(url, json, timeout):
            captured["user_msg"] = json["messages"][1]["content"]
            return self._mock_response(_VALID_OLLAMA_JSON)

        monkeypatch.setattr("httpx.post", fake_post)
        provider.classify_title("מכבי חתמה על שחקן", "he", subtitle="שחקן חדש מהיורוליג")

        assert "Headline: מכבי חתמה על שחקן" in captured["user_msg"]
        assert "Subtitle: שחקן חדש מהיורוליג" in captured["user_msg"]

    def test_none_subtitle_same_as_no_subtitle(self, monkeypatch):
        provider = self._make_provider()
        captured = {}

        def fake_post(url, json, timeout):
            captured["user_msg"] = json["messages"][1]["content"]
            return self._mock_response(_VALID_OLLAMA_JSON)

        monkeypatch.setattr("httpx.post", fake_post)
        provider.classify_title("כותרת", "he", subtitle=None)

        assert captured["user_msg"] == "Headline: כותרת"
        assert "Subtitle:" not in captured["user_msg"]

    def test_valid_response_returns_result(self, monkeypatch):
        provider = self._make_provider()
        monkeypatch.setattr("httpx.post", lambda url, json, timeout: self._mock_response(_VALID_OLLAMA_JSON))

        result = provider.classify_title("מכבי חתמה", "he")

        assert result is not None
        assert result.sport == "basketball"
        assert result.league == "EuroLeague"
        assert result.confidence == 0.93

    def test_connect_error_sets_flag_and_returns_none(self, monkeypatch):
        import httpx as httpx_module
        provider = self._make_provider()

        def raise_connect(url, json, timeout):
            raise httpx_module.ConnectError("Connection refused")

        monkeypatch.setattr("httpx.post", raise_connect)
        result = provider.classify_title("כותרת", "he")

        assert result is None
        assert provider.last_failure_was_connect_error is True

    def test_timeout_does_not_set_connect_flag(self, monkeypatch):
        import httpx as httpx_module
        provider = self._make_provider()

        def raise_timeout(url, json, timeout):
            raise httpx_module.ReadTimeout("Timed out")

        monkeypatch.setattr("httpx.post", raise_timeout)
        result = provider.classify_title("כותרת", "he")

        assert result is None
        assert provider.last_failure_was_connect_error is False

    def test_last_failure_flag_reset_on_success(self, monkeypatch):
        provider = self._make_provider()
        provider.last_failure_was_connect_error = True  # simulate prior failure

        monkeypatch.setattr("httpx.post", lambda url, json, timeout: self._mock_response(_VALID_OLLAMA_JSON))
        provider.classify_title("כותרת", "he")

        assert provider.last_failure_was_connect_error is False

    def test_system_prompt_is_sent(self, monkeypatch):
        from app.classification.prompt import CLASSIFICATION_SYSTEM_PROMPT
        provider = self._make_provider()
        captured = {}

        def fake_post(url, json, timeout):
            captured["system"] = json["messages"][0]["content"]
            return self._mock_response(_VALID_OLLAMA_JSON)

        monkeypatch.setattr("httpx.post", fake_post)
        provider.classify_title("כותרת", "he")

        assert captured["system"] == CLASSIFICATION_SYSTEM_PROMPT
