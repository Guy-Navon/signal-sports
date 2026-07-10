from app.classification.event_evidence import validate_event_evidence
from app.classification.merge import merge_with_guardrails
from app.ingestion.classifier import classify
from app.classification.llm_result import LLMClassificationResult


def _llm_event(event_type: str, confidence: float = 0.9) -> LLMClassificationResult:
    return LLMClassificationResult(
        sport="basketball",
        league="NBA",
        entities=[],
        event_type=event_type,
        importance="high",
        confidence=confidence,
        reason="test",
    )


class TestEventEvidenceContract:
    def test_title_win_requires_positive_championship_evidence(self):
        assert validate_event_evidence("title_win", "Boston Celtics are NBA champions").valid
        assert validate_event_evidence("title_win", "Celtics clinched the title").valid
        assert not validate_event_evidence("title_win", "Celtics want the title").valid
        assert not validate_event_evidence("title_win", "Celtics dream of a title").valid

    def test_hebrew_title_win_existing_hardening_is_table_driven(self):
        assert validate_event_evidence("title_win", "מכבי תל אביב זכה בגביע").valid
        assert validate_event_evidence("title_win", "ניו יורק אלופת ה-NBA").valid
        assert not validate_event_evidence("title_win", "המאמן זכה לביקורת קשה").valid
        assert not validate_event_evidence("title_win", "נהרג לשעבר אלוף העולם בתאונה").valid

    def test_signing_requires_completed_signing_not_candidate_or_negotiation(self):
        assert validate_event_evidence("signing", "Maccabi signed a new guard").valid
        assert not validate_event_evidence("signing", "Maccabi candidate to sign a guard").valid
        assert not validate_event_evidence("signing", "Maccabi in talks to sign a guard").valid

    def test_release_is_specific_but_hospital_release_is_blocked(self):
        assert validate_event_evidence("release", "Hapoel released the guard from the roster").valid
        assert validate_event_evidence("release", "הפועל ירושלים שחררה את הגארד").valid
        assert not validate_event_evidence("release", "השחקן שוחרר מבית החולים").valid

    def test_schedule_and_result_are_distinct(self):
        assert validate_event_evidence("schedule", "Greek League schedule for next round").valid
        assert not validate_event_evidence("match_result", "Schedule: Lakers-Warriors upcoming").valid
        assert validate_event_evidence("match_result", "Hornets beat Wizards 112-105").valid


class TestClassifierEventEvidence:
    def test_wants_the_title_falls_back_to_news(self):
        result = classify("Celtics want the title", source_id="eurohoops", language="en")
        assert result.event_type == "news"

    def test_dreams_of_title_falls_back_to_news(self):
        result = classify("Knicks dream of a title", source_id="eurohoops", language="en")
        assert result.event_type == "news"

    def test_candidate_does_not_become_signing(self):
        result = classify("Maccabi candidate to sign a EuroLeague guard", source_id="eurohoops", language="en")
        assert result.event_type == "candidate"

    def test_negotiation_does_not_become_signing(self):
        result = classify("Maccabi in talks to sign a EuroLeague guard", source_id="eurohoops", language="en")
        assert result.event_type == "negotiation"

    def test_release_is_not_generic_news(self):
        result = classify("Hapoel Jerusalem released the guard", source_id="walla_sport", language="en")
        assert result.event_type == "release"
        assert result.event_certainty in {"confirmed", "probable"}

    def test_hospital_release_falls_back_to_news(self):
        result = classify("השחקן שוחרר מבית החולים לאחר הפציעה", source_id="walla_sport", language="he")
        assert result.event_type == "injury"
        assert result.event_type != "release"

    def test_schedule_does_not_become_match_result(self):
        result = classify("Greek League schedule: upcoming Panathinaikos fixture", source_id="eurohoops")
        assert result.event_type == "schedule"

    def test_rules_certainty_is_confirmed_for_unambiguous_title_win(self):
        result = classify("Boston Celtics are NBA champions", source_id="eurohoops", language="en")
        assert result.event_type == "title_win"
        assert result.event_certainty == "confirmed"

    def test_rules_certainty_can_be_probable_for_single_source_specific(self):
        result = classify("חוזה חדש לפורוורד בהפועל ירושלים", source_id="walla_sport", language="he")
        assert result.event_type == "signing"
        assert result.event_certainty == "probable"


class TestLLMEventEvidenceContract:
    def test_llm_title_win_without_evidence_rejected_to_news(self):
        rules = classify("Celtics want the title", source_id="eurohoops", language="en")
        merged, by = merge_with_guardrails(
            _llm_event("title_win"),
            rules,
            "celtics want the title",
        )
        assert merged.event_type == "news"
        assert by == "llm+rules_guardrail"

    def test_llm_signing_candidate_rejected_to_rules_candidate(self):
        rules = classify("Maccabi candidate to sign a EuroLeague guard", source_id="eurohoops")
        merged, by = merge_with_guardrails(
            _llm_event("signing"),
            rules,
            "maccabi candidate to sign a euroleague guard",
        )
        assert merged.event_type == "candidate"
        assert by == "llm+rules_guardrail"

    def test_llm_rules_agreement_sets_confirmed_certainty(self):
        rules = classify("Maccabi signed a EuroLeague guard", source_id="eurohoops")
        merged, by = merge_with_guardrails(
            _llm_event("signing"),
            rules,
            "maccabi signed a euroleague guard",
        )
        assert merged.event_type == "signing"
        assert merged.event_certainty == "confirmed"
        assert by == "llm"

    def test_llm_only_specific_event_is_weak(self):
        rules = classify("Maccabi signed a EuroLeague guard", source_id="eurohoops")
        rules.event_type = "news"
        rules.event_certainty = "confirmed"
        merged, _ = merge_with_guardrails(
            _llm_event("signing"),
            rules,
            "maccabi signed a euroleague guard",
        )
        assert merged.event_type == "signing"
        assert merged.event_certainty == "weak"


class TestChampionAssertionSemantics:
    """Issue #60: championship VOCABULARY is not championship EVIDENCE."""

    # -- The mandatory minimal pair -----------------------------------------
    def test_minimal_pair_bare_construct_assertion_is_title_win(self):
        # "New York champions of the NBA" — champion noun as bare predicate.
        assert validate_event_evidence("title_win", "ניו יורק אלופת ה-NBA").valid

    def test_minimal_pair_prefixed_epithet_is_not_title_win(self):
        # "approaching the champion of Italy" — prepositional prefix = epithet.
        ev = validate_event_evidence("title_win", "מתקרב לאלופת איטליה?")
        assert not ev.valid and ev.event_type == "news"

    # -- Epithets ------------------------------------------------------------
    def test_definite_article_epithet_blocked(self):
        # "the champion returned from training camp" (reigning champion).
        ev = validate_event_evidence("title_win", "האלופה חזרה ממחנה האימון בפולין")
        assert not ev.valid

    def test_object_marker_epithet_blocked(self):
        # "trying to smear the world champion" — direct-object reference.
        ev = validate_event_evidence("title_win", "מנסים להכתים את אלופת העולם")
        assert not ev.valid

    def test_champion_kit_epithet_blocked(self):
        # C11 subtitle: "in the champion's kit" must not be a title win.
        ev = validate_event_evidence("title_win", "קפטן הצהובים ימשיך לעונה עשירית במדי האלופה")
        assert not ev.valid

    # -- Competition names containing champion vocabulary --------------------
    def test_champions_league_name_is_not_title_win(self):
        ev = validate_event_evidence("title_win", "ריאל מדריד תארח את ליברפול בליגת האלופות")
        assert not ev.valid

    def test_super_cup_name_is_not_title_win(self):
        # "אלוף האלופים" is the Israeli Super Cup's NAME (golden C4).
        ev = validate_event_evidence(
            "title_win", "כמות הכרטיסים שמכרה מכבי תל אביב לאלוף האלופים בטרנר"
        )
        assert not ev.valid

    # -- Aspirational win language -------------------------------------------
    def test_aspirational_infinitive_blocked(self):
        # "the best chance to win a championship" (golden C1) — the win verb
        # is inside the infinitive "לזכות"; Hebrew word boundaries reject it.
        ev = validate_event_evidence(
            "title_win", "זו הקבוצה שנותנת לך את הסיכוי הטוב ביותר לזכות באליפות"
        )
        assert not ev.valid

    def test_actual_win_verb_with_object_still_valid(self):
        assert validate_event_evidence("title_win", "מכבי זכתה באליפות המדינה").valid

    def test_trophy_lift_still_valid(self):
        assert validate_event_evidence("title_win", "מכבי הניפה את הגביע").valid


class TestFinalsResultRequiresResult:
    """Issue #60: finals context without a result signal is not finals_result."""

    def test_knockout_preview_is_not_finals_result(self):
        ev = validate_event_evidence(
            "finals_result", "רונאלדו נגד ספרד במוקד: כל מה שצריך לדעת על שמינית גמר המונדיאל"
        )
        assert not ev.valid

    def test_legal_story_mentioning_final_is_not_finals_result(self):
        ev = validate_event_evidence(
            "finals_result", "ניסיון נוסף לגישור הפערים בעסקת הטיעון של גמר הגביע"
        )
        assert not ev.valid

    def test_word_completely_does_not_match_final(self):
        # "לגמרי" (completely) contains "גמר" but is not a finals word.
        ev = validate_event_evidence("finals_result", "השחקן לגמרי ניצח את הביקורת")
        assert not ev.valid

    def test_finals_with_result_verb_is_valid(self):
        assert validate_event_evidence(
            "finals_result", "גמר NBA: סלטיקס מנצחים את הית' 4-1"
        ).valid

    def test_finals_with_score_is_valid(self):
        assert validate_event_evidence(
            "finals_result", "צרפת ברבע גמר אחרי 0:1 על פרגוואי"
        ).valid


class TestNegotiationPhraseGap:
    """Issue #60 / golden C9: 'על סף סיכום' is negotiation evidence."""

    def test_on_verge_of_agreement_is_negotiation(self):
        ev = validate_event_evidence("negotiation", "זאק לידיי על סף סיכום בהפועל")
        assert ev.valid and ev.event_type == "negotiation"
