"""
Tests for the deterministic keyword classifier.

Every test calls classify() as a pure function — no DB, no network.
"""

import pytest
from app.ingestion.classifier import classify


# ── Hebrew titles ─────────────────────────────────────────────────────────────

class TestHebrewMaccabi:
    def test_negotiation(self):
        r = classify('דיווח: מכבי ת"א במו"מ עם גארד יורוליג', language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert r.event_type == "negotiation"
        assert r.league == "EuroLeague"
        assert r.importance in ("high", "very_high")
        assert r.confidence >= 0.70

    def test_signing(self):
        # Full-name form without basketball context — ambiguous_club, sport unknown
        r = classify('רשמי: מכבי ת"א חתמה על שחקן חדש', language="he")
        assert r.sport == "unknown"
        assert "ambiguous_club" in r.tags
        assert r.event_type == "signing"

    def test_injury(self):
        # Full-name form without basketball context — ambiguous_club, sport unknown
        r = classify("פציעה: שחקן מכבי ת״א ייעדר שלושה שבועות", language="he")
        assert r.sport == "unknown"
        assert "ambiguous_club" in r.tags
        assert r.event_type == "injury"

    def test_candidate(self):
        r = classify('מכבי ת"א בודקת גארד ששיחק ביורוליג', language="he")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert r.event_type == "candidate"
        assert r.league == "EuroLeague"

    def test_friendly_match_is_low_importance(self):
        # Full-name form without basketball context — ambiguous_club, sport unknown
        r = classify('מכבי ת"א תשחק משחק ידידות לקראת העונה', language="he")
        assert r.sport == "unknown"
        assert "ambiguous_club" in r.tags
        assert r.importance not in ("high", "very_high")


class TestHebrewDeni:
    def test_trade(self):
        r = classify("דני אבדיה נסחר לקבוצה חדשה ב-NBA", language="he")
        assert r.sport == "basketball"
        assert "Deni Avdija" in r.entities
        assert r.event_type == "major_trade"
        assert r.league == "NBA"
        assert r.importance == "high"
        assert r.confidence >= 0.75

    def test_injury(self):
        r = classify("דני אבדיה נפצע — צפוי להיעדר 4 שבועות", language="he")
        assert r.sport == "basketball"
        assert "Deni Avdija" in r.entities
        assert r.event_type == "injury"
        assert r.league == "NBA"
        assert r.importance == "high"


class TestHebrewTennis:
    def test_grand_slam_winner(self):
        r = classify("אלקאראז זוכה בגראנד סלאם — ניצחון מרהיב", language="he")
        assert r.sport == "tennis"
        assert r.event_type == "grand_slam_winner"
        assert r.importance == "very_high"

    def test_wimbledon_early_round(self):
        r = classify("וימבלדון: שחקן מתקדם לסיבוב שלישי לאחר ניצחון קל", language="he")
        assert r.sport == "tennis"
        assert r.event_type == "early_round_result"
        assert r.importance == "low"

    def test_grand_slam_without_winner_signal_is_not_grand_slam_winner(self):
        # Reaching the final is not a "grand_slam_winner"
        r = classify("גראנד סלאם: שחקן מגיע לגמר", language="he")
        assert r.sport == "tennis"
        assert r.event_type != "grand_slam_winner"


class TestHebrewFootball:
    def test_regular_result(self):
        r = classify('תוצאה: הפועל ת"א מפסידה לבית"ר ירושלים 2-1 בליגת העל', language="he")
        assert r.sport == "football"
        # Could be match_result or regular_season_result — not basketball/tennis
        assert r.sport == "football"
        assert r.importance not in ("high", "very_high")


# ── English titles (basketball-only sources) ──────────────────────────────────

class TestEnglishEurohoops:
    """Articles from basketball-only source — sport defaults to basketball."""

    def test_deni_injury(self):
        r = classify("Deni Avdija injured — expected to miss 4 weeks", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert "Deni Avdija" in r.entities
        assert r.event_type == "injury"
        assert r.league == "NBA"
        assert r.importance == "high"
        assert r.confidence >= 0.80

    def test_deni_trade(self):
        r = classify("Official: Deni Avdija traded to new NBA team", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert "Deni Avdija" in r.entities
        assert r.event_type == "major_trade"
        assert r.league == "NBA"
        assert r.importance == "high"

    def test_maccabi_negotiation(self):
        r = classify("Maccabi Tel Aviv in advanced talks with EuroLeague guard", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert r.event_type == "negotiation"
        assert r.league == "EuroLeague"
        assert r.importance == "high"

    def test_euroleague_signing(self):
        r = classify("Real Madrid sign Kennard from NBA in biggest summer move", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        # "sign" is a word-boundary match
        assert r.event_type == "signing"
        assert r.league == "NBA"
        assert r.importance == "high"   # NBA league + signing

    def test_hornets_wizards_regular_season(self):
        r = classify("Hornets beat Wizards 112-105 in regular season", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert r.league == "NBA"
        assert r.event_type == "regular_season_result"
        assert r.importance in ("low", "medium")

    def test_nba_finals(self):
        r = classify("NBA Finals: Celtics beat Heat 4-1 to win championship", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert r.event_type == "finals_result"
        assert r.importance == "very_high"

    def test_acb_finals(self):
        r = classify("ACB: Real Madrid beat Barcelona in finals to win title", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert r.league == "Spanish ACB"
        assert r.event_type == "finals_result"
        assert r.importance == "very_high"

    def test_greek_schedule_is_low(self):
        r = classify("Greek League: Schedule for next round — Nika vs Panathinaikos", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert r.league == "Greek Basket League"
        assert r.event_type == "schedule"
        assert r.importance == "low"


# ── Confidence checks ─────────────────────────────────────────────────────────

class TestConfidence:
    def test_low_confidence_unknown_sport(self):
        r = classify("some random article with no sport keywords")
        assert r.sport == "unknown"
        assert r.confidence <= 0.5

    def test_higher_confidence_with_entity_and_league(self):
        r = classify("Deni Avdija traded to new NBA team", source_id="eurohoops", language="en")
        r2 = classify("some basketball game happened")
        assert r.confidence > r2.confidence


class TestHebrewRegressions:
    """
    Real Hebrew headlines that were/are misclassified by the deterministic classifier.
    Tests document the state after PR 11 deterministic fixes.
    Articles still requiring LLM are documented as known gaps.
    """

    def test_ny_knicks_champion_title_win(self):
        """אלופת fix: 'אלופת ה-NBA' now resolves to title_win (was: news/title)."""
        r = classify(
            "ערב היסטורי לברונסון ולניקס: ניו יורק אלופת ה-NBA!",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"
        assert r.league == "NBA"
        assert r.event_type == "title_win"
        assert r.importance == "very_high"

    def test_brunson_mvp_sport_and_league_now_resolved(self):
        """mvp fix: sport basketball. League now NBA deterministically (issue #28):
        Brunson resolves to a taxonomy entity whose membership is NBA, and legacy
        league is now membership-inferred — this class of article no longer needs
        the LLM to recover the league."""
        r = classify(
            "ג'יילן ברונסון ה-MVP של סדרת הגמר: \"בכל פעם, פשוט לקחנו את זה\"",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"        # fixed from unknown
        assert r.event_type == "finals_result"
        assert r.importance == "very_high"
        assert r.league == "NBA"              # membership-inferred (was: None, LLM-only)

    def test_hapoel_tlv_harper_still_ambiguous_without_llm(self):
        """Multi-sport entity: still unknown without LLM. Documents known gap."""
        r = classify(
            "סיכום בהפועל תל אביב? בירושלים לא שחררו את ג'ארד הארפר",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "unknown"
        assert "ambiguous_club" in r.tags

    def test_olympiacos_still_unknown_without_llm(self):
        """Multi-sport entity with no context keywords. Documents known gap."""
        r = classify(
            "אולימפיאקוס נקצה, ינאקופולוס עצבני אחרי הסערה הגדולה ביוון",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "unknown"
        assert r.league is None


# ── Subtitle gap-filling ──────────────────────────────────────────────────────

class TestSubtitleSportGap:
    """Subtitle fills sport=unknown when title is ambiguous or lacks sport keywords."""

    def test_subtitle_resolves_sport_basketball(self):
        """Title alone: sport=unknown. Subtitle has 'כדורסל' → sport=basketball."""
        r = classify(
            "גרנדיוזי: המהלך שכולם דיברו עליו קורה",
            subtitle="כדורסל: מכבי תל אביב חתמה על שחקן חדש",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"

    def test_subtitle_dual_sport_club_name_is_not_sport_evidence(self):
        """Taxonomy contract change: 'הפועל ירושלים' exists in BOTH sports, so its
        bare name is an entity mention, not basketball evidence. The old behavior
        (club name → basketball context) is exactly the mechanism that classified
        Hapoel Jerusalem FOOTBALL articles as basketball. Abstention is correct —
        the LLM gate force-calls on sport=unknown."""
        r = classify(
            "ערב מרגש לאוהדים",
            subtitle="הפועל ירושלים מנצחת בגמר האליפות",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "unknown"
        assert r.entities == []

    def test_subtitle_resolves_sport_tennis(self):
        """Title has no sport. Subtitle with 'טניס' → sport=tennis."""
        r = classify(
            "ניצחון מרהיב בגמר",
            subtitle="טניס: אלקאראז זוכה בגראנד סלאם",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "tennis"

    def test_subtitle_does_not_override_title_sport(self):
        """Title already resolved sport=football. Subtitle basketball context is ignored."""
        r_no_sub = classify(
            "הפועל באר שבע ניצחה את מכבי חיפה 2-0 בליגת העל",
            source_id="walla_sport", language="he",
        )
        r_with_sub = classify(
            "הפועל באר שבע ניצחה את מכבי חיפה 2-0 בליגת העל",
            subtitle="כדורסל: מכבי ירושלים זוכה ביורוליג",
            source_id="walla_sport", language="he",
        )
        assert r_no_sub.sport == "football"
        assert r_with_sub.sport == "football"  # subtitle basketball context not applied

    def test_subtitle_does_not_override_title_basketball(self):
        """Title resolved sport=basketball. Football subtitle context is ignored."""
        r = classify(
            "מכבי תל אביב ניצחה ביורוליג",
            subtitle="כדורגל: הפועל תל אביב נוצחת בליגת העל",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"

    def test_subtitle_without_title_sport_still_unknown_when_subtitle_also_ambiguous(self):
        """Neither title nor subtitle has clear sport → still unknown."""
        r = classify(
            "מה קורה עם הקבוצה?",
            subtitle="הכוכב הוא אחד הטובים בעולם",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "unknown"


class TestSubtitleFootballMaccabiGuardrail:
    """Football Maccabi clubs in subtitle must not trigger basketball classification."""

    def test_maccabi_haifa_in_subtitle_is_football(self):
        """Subtitle names מכבי חיפה (football) → sport=football, no basketball entity."""
        r = classify(
            "תוצאת הלילה",
            subtitle="מכבי חיפה ניצחה את הפועל תל אביב 2-0 בליגת העל",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in r.entities

    def test_maccabi_netanya_subtitle_is_football(self):
        """מכבי נתניה in subtitle → football, not basketball."""
        r = classify(
            "משחק חשוב בליגה",
            subtitle="מכבי נתניה הפסידה לבית\"ר ירושלים",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in r.entities

    def test_title_basketball_subtitle_football_maccabi_no_override(self):
        """Title already resolves basketball. Subtitle with football Maccabi club
        must NOT change sport — subtitle cannot override resolved sport."""
        r = classify(
            "מכבי תל אביב הגיעה לגמר יורוליג",
            subtitle="בכדורגל: מכבי חיפה ניצחה הלילה",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"


class TestSubtitleAmbiguousClubResolution:
    """Ambiguous club titles (מכבי ת"א without context) resolved via subtitle."""

    def test_ambiguous_maccabi_resolved_basketball_via_subtitle(self):
        """Title has full מכבי ת"א (ambiguous). Subtitle has כדורסל → basketball entity."""
        r = classify(
            'מכבי ת"א חתמה על שחקן חדש',
            subtitle="הגארד הצטרף לקבוצה הכדורסל לעונה הבאה ביורוליג",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities
        assert "ambiguous_club" not in r.tags  # resolved

    def test_ambiguous_hapoel_tlv_resolved_basketball_via_subtitle(self):
        """הפועל ת"א (ambiguous). Subtitle with כדורסל → basketball entity assigned."""
        r = classify(
            'הפועל ת"א במו"מ עם שחקן',
            subtitle="כדורסל: הפועל תל אביב מחפשת חיזוק לתפקיד הגארד",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"
        assert "Hapoel Tel Aviv Basketball" in r.entities
        assert "ambiguous_club" not in r.tags

    def test_ambiguous_maccabi_still_ambiguous_when_subtitle_also_vague(self):
        """Subtitle doesn't provide sport context → still ambiguous_club, sport=unknown."""
        r = classify(
            'מכבי ת"א חתמה על שחקן חדש',
            subtitle="המהלך הוכרז הלילה בהצהרה רשמית",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "unknown"
        assert "ambiguous_club" in r.tags


class TestSubtitleEntityGap:
    """Subtitle adds entities when title produced none."""

    def test_subtitle_adds_deni_entity(self):
        """Title has no entity. Subtitle names 'אבדיה' → Deni Avdija entity added."""
        r = classify(
            "עסקת הספורט של השנה",
            subtitle="דני אבדיה נסחר לקבוצה חדשה ב-NBA",
            source_id="walla_sport", language="he",
        )
        assert "Deni Avdija" in r.entities
        assert r.league == "NBA"

    def test_subtitle_does_not_add_basketball_entity_to_football_article(self):
        """Title resolved football. Subtitle names מכבי (basketball) → entity filtered out."""
        r = classify(
            "הפועל באר שבע ניצחה בכדורגל",
            subtitle="מכבי ניצחה גם היא בכדורסל",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in r.entities


class TestSubtitleLeagueAndEventTypeGap:
    """Subtitle fills league and event_type when title is vague."""

    def test_subtitle_adds_league_euroleague(self):
        """Title has sport=basketball but no league. Subtitle has 'יורוליג' → EuroLeague."""
        r = classify(
            "ניצחון מרשים אמש",
            subtitle="מכבי תל אביב ניצחה ביורוליג 82-75",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"
        assert r.league == "EuroLeague"

    def test_subtitle_adds_israeli_basketball_league_context(self):
        """Subtitle with חולון → Israeli Basketball League inferred."""
        r = classify(
            "מכבי ניצחה הלילה",
            subtitle="הפועל חולון נוצחת בגמר ווינר סל",
            source_id="walla_sport", language="he",
        )
        assert r.sport == "basketball"
        assert r.league == "Israeli Basketball League"

    def test_subtitle_refines_event_type_from_news_to_injury(self):
        """Title is vague (news event_type). Subtitle has 'פציעה' → injury."""
        r = classify(
            "עדכון על שחקן ה-NBA",
            subtitle="הכוכב נפצע ויעדר ארבעה שבועות",
            source_id="walla_sport", language="he",
        )
        assert r.event_type == "injury"

    def test_subtitle_refines_event_type_from_news_to_negotiation(self):
        """Title is vague. Subtitle has מו\"מ → negotiation."""
        r = classify(
            "חדשות ממכבי תל אביב",
            subtitle='מכבי ת"א במו"מ עם גארד מהיורוליג',
            source_id="walla_sport", language="he",
        )
        assert r.event_type == "negotiation"

    def test_title_event_type_not_overridden_by_subtitle(self):
        """Title already detected signing. Subtitle with 'פציעה' must not change it."""
        r_no_sub = classify(
            'מכבי ת"א חתמה על שחקן כדורסל חדש',
            source_id="walla_sport", language="he",
        )
        r_with_sub = classify(
            'מכבי ת"א חתמה על שחקן כדורסל חדש',
            subtitle="השחקן נפצע בסיזון הקודם",
            source_id="walla_sport", language="he",
        )
        assert r_no_sub.event_type == "signing"
        assert r_with_sub.event_type == "signing"  # subtitle "פציעה" must not override


class TestSubtitleNoRegression:
    """classify() without subtitle must behave identically to previous version."""

    def test_no_subtitle_maccabi_negotiation_unchanged(self):
        r = classify('דיווח: מכבי ת"א במו"מ עם גארד יורוליג', language="he")
        assert r.sport == "basketball"
        assert r.event_type == "negotiation"
        assert r.league == "EuroLeague"

    def test_no_subtitle_deni_trade_unchanged(self):
        r = classify("דני אבדיה נסחר לקבוצה חדשה ב-NBA", language="he")
        assert r.sport == "basketball"
        assert "Deni Avdija" in r.entities
        assert r.league == "NBA"
        assert r.event_type == "major_trade"

    def test_no_subtitle_football_maccabi_haifa_unchanged(self):
        r = classify("מכבי חיפה ניצחה 2-0", language="he")
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in r.entities

    def test_no_subtitle_ambiguous_club_unchanged(self):
        r = classify('מכבי ת"א חתמה על שחקן חדש', language="he")
        assert r.sport == "unknown"
        assert "ambiguous_club" in r.tags

    def test_no_subtitle_eurohoops_basketball_only_unchanged(self):
        r = classify("Maccabi Tel Aviv wins EuroLeague game", source_id="eurohoops", language="en")
        assert r.sport == "basketball"
        assert "Maccabi Tel Aviv Basketball" in r.entities


# ══════════════════════════════════════════════════════════════════════════════
# title_win hardening — false positives and true positives
# ══════════════════════════════════════════════════════════════════════════════

class TestTitleWinHardening:
    """Verify title_win is not triggered by loose Hebrew win-verbs in non-championship context."""

    def _classify(self, title: str) -> object:
        return classify(title, source_id="walla_sport", language="he")

    # ── False positives that must NOT trigger title_win ───────────────────────

    def test_no_title_win_for_zache_levi_kartet(self):
        """'זכה לביקורת' = received criticism — not a title win."""
        r = self._classify("השחקן זכה לביקורת קשה אחרי המשחק")
        assert r.event_type != "title_win", f"Got event_type={r.event_type!r}"

    def test_no_title_win_for_zache_lemachaot(self):
        """'זכה למחמאות' = received praise — not a title win."""
        r = self._classify("המאמן זכה למחמאות רבות מהתקשורת")
        assert r.event_type != "title_win"

    def test_no_title_win_for_zachu_barega(self):
        """'זכו ברגע' = caught/received a moment — not a title win."""
        r = self._classify('"התפרקו, אני שחקן נבחרת": צפו ברגע המביך במחנה של ספרד')
        assert r.event_type != "title_win"

    def test_no_title_win_for_tzipyu_barega(self):
        """'צפו ברגע' = watch the moment — not a title win."""
        r = self._classify("צפו ברגע המביך: שחקן הכדורגל נפל על המגרש")
        assert r.event_type != "title_win"

    def test_no_title_win_for_zacha_leteguva(self):
        """'זכתה לתגובה' = received a response — not a title win."""
        r = self._classify("ההחלטה זכתה לתגובה חריפה מהאגודה")
        assert r.event_type != "title_win"

    def test_no_title_win_for_zachu_letiyud(self):
        """'זכו לתיעוד' = were documented/captured — not a title win."""
        r = self._classify("הרגעים זכו לתיעוד נרחב ברשתות החברתיות")
        assert r.event_type != "title_win"

    # ── True positives that MUST still trigger title_win ─────────────────────

    def test_title_win_with_alufat_regression(self):
        """'אלופת ה-NBA' — unambiguous championship word; must stay title_win."""
        r = self._classify("ניו יורק אלופת ה-NBA!")
        assert r.event_type == "title_win"
        assert r.importance == "very_high"

    def test_title_win_with_aluf(self):
        """'אלוף' — unambiguous championship word."""
        r = self._classify("מכבי תל אביב אלוף ישראל בכדורסל")
        assert r.event_type == "title_win"

    def test_title_win_with_compound_gabia(self):
        """'זכה בגביע' — win-verb + cup context = title_win."""
        r = self._classify("מכבי תל אביב זכה בגביע הכדורסל")
        assert r.event_type == "title_win"

    def test_title_win_with_compound_betavar(self):
        """'זכה בתואר' — win-verb + title/award context = title_win."""
        r = self._classify("השחקן זכה בתואר המצטיין")
        assert r.event_type == "title_win"

    def test_title_win_with_hanifa_gabia(self):
        """'הניפה גביע' — lifted the trophy = title_win."""
        r = self._classify("מכבי תל אביב הניפה את הגביע בסיום המשחק")
        assert r.event_type == "title_win"

    def test_title_win_english_champions(self):
        """English 'champions' — unambiguous championship word."""
        r = classify("Boston Celtics are NBA champions", source_id="eurohoops", language="en")
        assert r.event_type == "title_win"


# ══════════════════════════════════════════════════════════════════════════════
# Source URL sport hint — integration with classify()
# ══════════════════════════════════════════════════════════════════════════════

class TestSourceSportHintInClassifier:
    """source_sport_hint parameter flows through classify() → _detect_sport()."""

    def test_basketball_hint_overrides_ambiguous_maccabi(self):
        """Israel Hayom basketball URL: Maccabi TLV title without context → basketball via hint."""
        r = classify(
            "אירוע חמור: מכבי תל אביב מנעה מעיתונאים גישה לחדר ההלבשה",
            source_id="israel_hayom_sport", language="he",
            url="https://www.israelhayom.co.il/sport/israeli-basketball/article/20752364",
            source_sport_hint="basketball",
        )
        assert r.sport == "basketball"

    def test_football_hint_overrides_unknown(self):
        """Israel Hayom football URL: generic title → football via hint."""
        r = classify(
            "מפתיע: ניצחון דרמטי במשחק הערב",
            source_id="israel_hayom_sport", language="he",
            url="https://www.israelhayom.co.il/sport/world-soccer/article/20752578",
            source_sport_hint="football",
        )
        assert r.sport == "football"

    def test_none_hint_falls_back_to_keyword_detection(self):
        """No hint: sport detected normally from title keywords."""
        r = classify(
            "מכבי תל אביב ניצחה בגמר ליגת היורוליג",
            source_id="israel_hayom_sport", language="he",
            url="https://www.israelhayom.co.il/sport/world-basketball/article/123",
            source_sport_hint=None,
        )
        assert r.sport == "basketball"
