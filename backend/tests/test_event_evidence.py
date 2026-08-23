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


class TestMedalPlacementIsNotTitleWin:
    """#63 product decision: silver/bronze placement is not a title victory."""

    def test_bronze_medal_at_championship_is_not_title_win(self):
        ev = validate_event_evidence(
            "title_win",
            "היסטוריה בכדורעף הישראלי: נבחרת העתודה זכתה במדליית הארד באליפות אירופה",
        )
        assert not ev.valid and ev.event_type == "news"

    def test_silver_medal_is_not_title_win(self):
        ev = validate_event_evidence("title_win", "הנבחרת זכתה במדליית כסף באליפות העולם")
        assert not ev.valid

    def test_gold_medal_at_championship_is_title_win(self):
        # Gold at a championship IS winning it — deliberately not blocked.
        assert validate_event_evidence(
            "title_win", "הנבחרת זכתה במדליית הזהב באליפות אירופה"
        ).valid

    def test_plain_championship_win_still_valid(self):
        assert validate_event_evidence("title_win", "מכבי זכתה באליפות המדינה").valid


class TestGrandSlamChampionNoun:
    """#133: a Grand Slam win must reach `grand_slam_winner`, not `title_win`.

    The slam rule accepted only win VERBS (זכה/זכתה/זוכה) plus the ENGLISH
    "champion"; the Hebrew champion NOUN was recognised by title_win alone. So
    the clearest possible slam headline — "סינר אלוף ווימבלדון" — was claimed by
    title_win and never reached a tennis preference keyed on grand_slam_winner.
    """

    # ── The reported articles (verbatim from the live corpus) ─────────────────
    def test_champion_noun_slam_headline_is_grand_slam_winner(self):
        ev = validate_event_evidence(
            "grand_slam_winner",
            "מכסח דשא: יאניק סינר אלוף ווימבלדון בפעם השנייה ברציפות",
            sport="tennis",
        )
        assert ev.valid and ev.event_type == "grand_slam_winner"
        assert ev.certainty == "confirmed"

    def test_defended_title_slam_headline_is_grand_slam_winner(self):
        ev = validate_event_evidence(
            "grand_slam_winner",
            "סינר שוב אלוף ווימבלדון: ניצח את זברב והגן על התואר",
            sport="tennis",
        )
        assert ev.valid and ev.event_type == "grand_slam_winner"

    def test_classifier_end_to_end_prefers_grand_slam_over_title_win(self):
        article = classify(
            "מכסח דשא: יאניק סינר אלוף ווימבלדון בפעם השנייה ברציפות",
            source_id="walla_sport",
            language="he",
            source_sport_hint="tennis",
        )
        assert article.event_type == "grand_slam_winner"

    # ── The win VERB path must keep working, both genders ────────────────────
    def test_masculine_win_verb_still_valid(self):
        assert validate_event_evidence(
            "grand_slam_winner",
            "גראנד סלאם 5 בקריירה: יאניק סינר זכה בטורניר וימבלדון",
            sport="tennis",
        ).valid

    def test_feminine_win_verb_is_confirmed_not_merely_probable(self):
        # Only the masculine זכה sat in confirmed_any, so a woman's slam win was
        # capped at `probable` and lost very_high importance.
        ev = validate_event_evidence(
            "grand_slam_winner", "אלופה בת 21: לינדה נוסקובה זכתה בווימבלדון",
            sport="tennis",
        )
        assert ev.valid and ev.certainty == "confirmed"

    # ── Adversarial neighbours: none of these may become a slam win ──────────
    def test_early_round_result_is_not_promoted(self):
        assert not validate_event_evidence(
            "grand_slam_winner",
            "וימבלדון: אלקאראז מתקדם לסיבוב שלישי לאחר ניצחון קל",
            sport="tennis",
        ).valid

    def test_eliminated_defending_champion_is_not_a_slam_win(self):
        # The commonest way a champion noun sits beside a slam name.
        assert not validate_event_evidence(
            "grand_slam_winner", "אלופת ווימבלדון הודחה בסיבוב הראשון", sport="tennis"
        ).valid

    def test_champion_noun_as_epithet_is_not_a_slam_win(self):
        assert not validate_event_evidence(
            "grand_slam_winner",
            "מול אלופת ווימבלדון: הישראלית מקווה להפתיע",
            sport="tennis",
        ).valid

    def test_role_holder_champion_noun_is_not_a_slam_win(self):
        assert not validate_event_evidence(
            "grand_slam_winner", "המאמן של אלוף ווימבלדון מדבר על העונה", sport="tennis"
        ).valid

    def test_aspiration_is_not_a_slam_win(self):
        assert not validate_event_evidence(
            "grand_slam_winner",
            'אלקראס חולם על ווימבלדון: "זה התואר שאני הכי רוצה"',
            sport="tennis",
        ).valid

    def test_slam_win_stays_tennis_only(self):
        assert not validate_event_evidence(
            "grand_slam_winner", "מכבי אלופת ווימבלדון", sport="basketball"
        ).valid

    # ── title_win must keep its own domain ───────────────────────────────────
    def test_domestic_title_is_still_title_win(self):
        article = classify(
            "מכבי תל אביב אלופת הליגה",
            source_id="walla_sport",
            language="he",
            source_sport_hint="basketball",
        )
        assert article.event_type == "title_win"

    def test_world_cup_crowning_is_still_title_win(self):
        assert validate_event_evidence(
            "title_win", "ספרד הוכתרה לאלופת העולם", sport="football"
        ).valid


class TestGrandSlamWinnerIsTitleLocal:
    """#133: a champion noun in a SUBTITLE is an epithet, exactly as #125 found
    for domestic titles — so the slam win joins the title-local set."""

    def test_grand_slam_winner_is_title_local(self):
        from app.classification.event_evidence import TITLE_LOCAL_EVENT_TYPES

        assert "grand_slam_winner" in TITLE_LOCAL_EVENT_TYPES
        assert "title_win" in TITLE_LOCAL_EVENT_TYPES
