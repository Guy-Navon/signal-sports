"""
Quality regression tests — 15 manual QA cases discovered during the LLM gating benchmark.

These tests protect against feed-quality regressions in:
1. Classifier: sport, league, event_type detection for IBL/NBA/Maccabi articles
2. Enrichment helpers: enrich_maccabi_entity_after_sport_resolve, compute_importance
3. Relevance engine: Guy's per-article feed decisions

Cases 1–9:  positive — must be visible in Guy's feed (were hidden before this fix)
Cases 10–15: negative — must be hidden in Guy's feed (were leaking before this fix)
"""

from datetime import datetime, timezone

import pytest

from app.ingestion.classifier import (
    classify,
    compute_importance,
    enrich_maccabi_entity_after_sport_resolve,
)
from app.models.article import Article
from app.seed.seed_profiles import SEED_PROFILES
from app.services.relevance_engine import score_article


# ── Helpers ───────────────────────────────────────────────────────────────────


@pytest.fixture
def guy_profile():
    return next(p for p in SEED_PROFILES if p.user_id == "guy")


def _article(**kwargs) -> Article:
    defaults = dict(
        id="test_regression",
        source="test",
        source_display_name="Test",
        url="https://example.com/test",
        title="Test Article",
        original_title=None,
        translated_title=None,
        language="he",
        published_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        sport="basketball",
        league=None,
        entities=[],
        event_type="news",
        importance="medium",
        confidence=0.75,
        tags=[],
        subtitle=None,
        classified_by="rules",
        classification_provider=None,
        classification_reason=None,
        classification_confidence=None,
    )
    defaults.update(kwargs)
    return Article(**defaults)


def _guy_decision(article, guy_profile) -> str:
    return score_article(article, guy_profile).decision


# ── Group A: IBL classifier fixes ─────────────────────────────────────────────


class TestIBLClassifier:
    """IBL team names now in keyword lists → sport=basketball and league=Israeli Basketball League."""

    def test_gilboa_article_classified_as_basketball(self):
        """Case 9a: Gilboa Elyon → basketball (was unknown before)."""
        r = classify("גלבוע עליון ניצחה בחולון 88-75")
        assert r.sport == "basketball"

    def test_gilboa_article_classified_as_ibl(self):
        """Case 9b: Gilboa Elyon → Israeli Basketball League."""
        r = classify("גלבוע עליון ניצחה בחולון 88-75")
        assert r.league == "Israeli Basketball League"

    def test_emek_yizrael_classified_as_basketball(self):
        r = classify("עמק יזרעאל עברה לגמר הליגה הישראלית")
        assert r.sport == "basketball"

    def test_hapoel_eilat_classified_as_basketball(self):
        """Case 3a: Hapoel Eilat → basketball."""
        r = classify("הפועל אילת צירפה שחקן חדש")
        assert r.sport == "basketball"

    def test_hapoel_eilat_classified_as_ibl(self):
        """Case 3b: Hapoel Eilat → Israeli Basketball League."""
        r = classify("הפועל אילת צירפה שחקן חדש")
        assert r.league == "Israeli Basketball League"

    def test_bnei_herzliya_still_basketball(self):
        """Case 5a: Bnei Herzliya still detected as basketball."""
        r = classify("דג'יי בראנס ימשיך בבני הרצליה לעונה נוספת")
        assert r.sport == "basketball"

    def test_bnei_herzliya_classified_as_ibl(self):
        """Case 5b: Bnei Herzliya → Israeli Basketball League (was None before)."""
        r = classify("דג'יי בראנס ימשיך בבני הרצליה לעונה נוספת")
        assert r.league == "Israeli Basketball League"

    def test_gilboa_article_not_football(self):
        r = classify("שגיא של ממשיך בחולון, עודד הגדיל עבר מגלבוע עליון לעמק")
        assert r.sport == "basketball"
        assert r.sport != "football"

    def test_gilboa_article_ibl_league(self):
        """Case 9c: Holon/Gilboa/Emek article → Israeli Basketball League."""
        r = classify("שגיא של ממשיך בחולון, עודד הגדיל עבר מגלבוע עליון לעמק")
        assert r.league == "Israeli Basketball League"


# ── Group B: NBA keyword fixes ────────────────────────────────────────────────


class TestNBAKeywordFixes:
    """LeBron (Hebrew) now in _BASKETBALL_KW + _NBA_TEAM_KW → NBA inferred."""

    def test_lebron_classified_as_basketball(self):
        """Case 8a: LeBron Hebrew name → basketball."""
        r = classify("לברון ג'יימס ודיווד בלאט מסכמים עשור לניצחון בגביע")
        assert r.sport == "basketball"

    def test_lebron_classified_as_nba(self):
        """Case 8b: LeBron Hebrew name → NBA league."""
        r = classify("לברון ג'יימס ודיווד בלאט מסכמים עשור לניצחון בגביע")
        assert r.league == "NBA"

    def test_lebron_short_form_classified_as_basketball(self):
        r = classify("לברון חוזר לקליבלנד")
        assert r.sport == "basketball"


# ── Group C: Event type keyword fixes ─────────────────────────────────────────


class TestEventTypeKeywordFixes:
    """New signing and candidate keywords now trigger correct event_type."""

    def test_coach_appointed_is_signing(self):
        """Case 3c: 'מונה למאמן' → signing."""
        r = classify("אהרוני מונה למאמן הפועל אילת")
        assert r.event_type == "signing"

    def test_contract_extension_is_signing(self):
        """Case 5c: 'לעונה נוספת' → signing."""
        r = classify("דג'יי בראנס ימשיך בבני הרצליה לעונה נוספת")
        assert r.event_type == "signing"

    def test_next_targets_is_candidate(self):
        """Case 7a: 'המטרות הבאות' → candidate."""
        r = classify("המטרות הבאות של מכבי תל אביב לקראת העונה הבאה")
        assert r.event_type == "candidate"

    def test_death_article_is_news_not_title_win(self):
        """Death/accident guard prevents 'נהרג אלוף' from triggering title_win."""
        r = classify("נהרג לשעבר אלוף העולם בתאונת דרכים")
        assert r.event_type == "news"

    def test_eurocup_schedule_detected(self):
        """Case 4a: EuroCup schedule article → event_type=schedule."""
        r = classify("שידורי יורוקאפ השבוע")
        assert r.event_type == "schedule"


# ── Group D: EuroCup classifier ───────────────────────────────────────────────


class TestEuroCupClassifier:
    """EuroCup articles correctly classified (sport + league)."""

    def test_eurocup_hebrew_classified_as_basketball(self):
        r = classify("שידורי יורוקאפ השבוע")
        assert r.sport == "basketball"

    def test_eurocup_hebrew_classified_as_eurocup_league(self):
        """Case 4b: 'יורוקאפ' → EuroCup (not EuroLeague)."""
        r = classify("שידורי יורוקאפ השבוע")
        assert r.league == "EuroCup"


# ── Group E: Maccabi entity enrichment helpers ───────────────────────────────


class TestMaccabiEntityEnrichment:
    """enrich_maccabi_entity_after_sport_resolve injects entity when LLM resolved sport."""

    def test_enriches_when_sport_basketball(self):
        result = enrich_maccabi_entity_after_sport_resolve(
            [], "מכבי תל אביב נקנסה", "basketball"
        )
        assert "Maccabi Tel Aviv Basketball" in result

    def test_no_enrich_when_entity_already_present(self):
        entities = ["Maccabi Tel Aviv Basketball"]
        result = enrich_maccabi_entity_after_sport_resolve(
            entities, "מכבי תל אביב נקנסה", "basketball"
        )
        assert result is entities  # same object — no modification

    def test_no_enrich_when_sport_not_basketball(self):
        result = enrich_maccabi_entity_after_sport_resolve(
            [], "מכבי תל אביב נקנסה", "football"
        )
        assert result == []

    def test_no_enrich_for_football_maccabi_club(self):
        result = enrich_maccabi_entity_after_sport_resolve(
            [], "מכבי חיפה ניצחה", "basketball"
        )
        assert "Maccabi Tel Aviv Basketball" not in result

    def test_no_enrich_when_no_maccabi_phrase_in_title(self):
        result = enrich_maccabi_entity_after_sport_resolve(
            [], "הפועל ירושלים ניצחה בגביע", "basketball"
        )
        assert result == []

    def test_compute_importance_medium_with_maccabi_entity(self):
        """After enrichment: news + Maccabi entity → medium (not low)."""
        importance = compute_importance("news", ["Maccabi Tel Aviv Basketball"], None)
        assert importance == "medium"

    def test_compute_importance_low_without_entity(self):
        importance = compute_importance("news", [], None)
        assert importance == "low"

    def test_compute_importance_high_for_signing_with_entity(self):
        importance = compute_importance("signing", ["Maccabi Tel Aviv Basketball"], None)
        assert importance == "high"


# ── Group F: Guy feed — positive cases (should be visible) ───────────────────


class TestGuyPositiveCasesQA:
    """Positive QA cases 1–9: articles that should appear in Guy's feed."""

    def test_case1_maccabi_ambiguous_post_injection_visible(self, guy_profile):
        """Case 1: Ambiguous Maccabi TLV — after entity injection, reaches Maccabi topic."""
        title = "דיווח: זו הקבוצה הבאה של שחקן מכבי תל אביב"
        enriched = enrich_maccabi_entity_after_sport_resolve([], title.lower(), "basketball")
        importance = compute_importance("news", enriched, None)
        article = _article(
            title=title,
            sport="basketball",
            league=None,
            entities=enriched,
            event_type="news",
            importance=importance,
        )
        assert _guy_decision(article, guy_profile) != "hidden"

    def test_case3_coach_appointment_hapoel_eilat_visible(self, guy_profile):
        """Case 3: Coaching appointment at Hapoel Eilat — IBL topic, signing → feed."""
        r = classify("במקביל לעזוב למכבי: אהרוני מונה למאמן הפועל אילת")
        assert r.sport == "basketball"
        article = _article(
            title="במקביל לעזוב למכבי: אהרוני מונה למאמן הפועל אילת",
            sport=r.sport,
            league=r.league,
            entities=r.entities,
            event_type=r.event_type,
            importance=r.importance,
        )
        assert _guy_decision(article, guy_profile) != "hidden"

    def test_case4_eurocup_schedule_visible(self, guy_profile):
        """Case 4: EuroCup schedule — EuroLeague topic now includes EuroCup + schedule=low_feed."""
        article = _article(
            title="שידורי יורוקאפ השבוע",
            sport="basketball",
            league="EuroCup",
            entities=[],
            event_type="schedule",
            importance="low",
        )
        assert _guy_decision(article, guy_profile) == "low_feed"

    def test_case5_bnei_herzliya_contract_visible(self, guy_profile):
        """Case 5: DJ Burns stays at Bnei Herzliya — IBL topic, signing → feed."""
        r = classify("דג'יי בראנס ימשיך בבני הרצליה לעונה נוספת")
        article = _article(
            title="דג'יי בראנס ימשיך בבני הרצליה לעונה נוספת",
            sport=r.sport,
            league=r.league,
            entities=r.entities,
            event_type=r.event_type,
            importance=r.importance,
        )
        assert _guy_decision(article, guy_profile) != "hidden"

    def test_case6_maccabi_fined_post_injection_visible(self, guy_profile):
        """Case 6: Maccabi TLV fined (ambiguous title) — post-injection must be visible."""
        title = "אחרי שמעון מזרחי? מכבי תל אביב נקנסה"
        enriched = enrich_maccabi_entity_after_sport_resolve([], title.lower(), "basketball")
        importance = compute_importance("news", enriched, None)
        article = _article(
            title=title,
            sport="basketball",
            league=None,
            entities=enriched,
            event_type="news",
            importance=importance,
        )
        assert _guy_decision(article, guy_profile) != "hidden"

    def test_case7_maccabi_next_targets_high_feed(self, guy_profile):
        """Case 7: Maccabi TLV next targets (candidate) — after injection → high_feed."""
        title = "אחרי בוני קולסון: המטרות הבאות של מכבי תל אביב"
        r = classify(title)
        assert r.event_type == "candidate"
        enriched = enrich_maccabi_entity_after_sport_resolve(r.entities, title.lower(), "basketball")
        importance = compute_importance(r.event_type, enriched, r.league)
        article = _article(
            title=title,
            sport="basketball",
            league=r.league,
            entities=enriched,
            event_type=r.event_type,
            importance=importance,
        )
        assert _guy_decision(article, guy_profile) in ("high_feed", "push")

    def test_case8_lebron_nba_visible(self, guy_profile):
        """Case 8: LeBron James NBA article — must reach NBA topic."""
        r = classify("לברון ג'יימס ודיווד בלאט מסכמים עשור לניצחון בגביע")
        assert r.sport == "basketball"
        assert r.league == "NBA"
        article = _article(
            title="לברון ג'יימס ודיווד בלאט מסכמים עשור לניצחון בגביע",
            sport=r.sport,
            league=r.league,
            entities=r.entities,
            event_type=r.event_type,
            importance=r.importance,
        )
        assert _guy_decision(article, guy_profile) != "hidden"

    def test_case9_gilboa_ibl_visible(self, guy_profile):
        """Case 9: Gilboa/Holon Israeli Basketball League — must not be hidden for Guy."""
        r = classify("שגיא של ממשיך בחולון, עודד הגדיל עבר מגלבוע עליון לעמק")
        assert r.sport == "basketball"
        assert r.league == "Israeli Basketball League"
        article = _article(
            title="שגיא של ממשיך בחולון, עודד הגדיל עבר מגלבוע עליון לעמק",
            sport=r.sport,
            league=r.league,
            entities=r.entities,
            event_type=r.event_type,
            importance=r.importance,
        )
        assert _guy_decision(article, guy_profile) != "hidden"


# ── Group G: Guy feed — negative cases (must be hidden) ──────────────────────


class TestGuyNegativeCasesQA:
    """Negative QA cases 10–15: football articles that must be hidden for Guy.

    Root cause was mode='major_only' + major_importance_fallback allowing high-importance
    football into the feed. Fix: mode='titles_only' with empty event_rules.
    """

    def test_case10_football_regular_season_hidden(self, guy_profile):
        """Case 10: Football regular-season result → hidden (any importance)."""
        article = _article(
            title="ספורטינג ליסבון ניצחה בליגה הפורטוגלית",
            sport="football",
            league="Portuguese Liga",
            entities=[],
            event_type="regular_season_result",
            importance="medium",
        )
        assert _guy_decision(article, guy_profile) == "hidden"

    def test_case11_football_high_importance_hidden(self, guy_profile):
        """Case 11: Football article LLM-classified as high importance → still hidden."""
        article = _article(
            title="ריאל מדריד זכה 3-0 בגביע",
            sport="football",
            league="La Liga",
            entities=[],
            event_type="match_result",
            importance="high",
        )
        assert _guy_decision(article, guy_profile) == "hidden"

    def test_case12_football_very_high_importance_hidden(self, guy_profile):
        """Case 12: Football with very_high importance (LLM over-estimate) → still hidden."""
        article = _article(
            title="קבוצה ניצחת בגמר הליגה",
            sport="football",
            league="Unknown Football League",
            entities=[],
            event_type="finals_result",
            importance="very_high",
        )
        assert _guy_decision(article, guy_profile) == "hidden"

    def test_case13_football_title_win_is_low_feed(self, guy_profile):
        """Case 13 (updated for issue #29): football title_win was hidden under the
        old all-hidden titles_only policy; the unified football policy (issue #29,
        applied identically to seed_profiles.py and userProfiles.js) declares an
        explicit title_win/major_transfer low_feed rule instead — "genuinely major
        event, low priority" rather than a titles_only blanket hide or a
        major_only importance-fallback leak. Still nowhere near feed/high_feed/push."""
        article = _article(
            title="ריאל מדריד אלוף ליגת האלופות",
            sport="football",
            league="UEFA Champions League",
            entities=[],
            event_type="title_win",
            importance="very_high",
        )
        assert _guy_decision(article, guy_profile) == "low_feed"

    def test_case14_football_major_transfer_hidden(self, guy_profile):
        """Case 14: Football major_trade — was 'feed' in old rules, now hidden."""
        article = _article(
            title="מבאפה עבר לריאל מדריד בעסקת ענק",
            sport="football",
            league="La Liga",
            entities=[],
            event_type="major_trade",
            importance="very_high",
        )
        assert _guy_decision(article, guy_profile) == "hidden"

    def test_case15_hapoel_rl_football_or_unknown_hidden(self, guy_profile):
        """Case 15: Hapoel Rishon LeZion — ambiguous club, not a Maccabi TLV topic match.

        Expected: sport=football or unknown, hidden for Guy.
        'הפועל ראשון לציון' without basketball context should not trigger basketball.
        """
        r = classify("מכוונת גבוה: הפועל ראשון לציון צירפה את אזיקיאל הנטי")
        assert r.sport in ("football", "unknown")
        article = _article(
            title="מכוונת גבוה: הפועל ראשון לציון צירפה את אזיקיאל הנטי",
            sport=r.sport,
            league=r.league,
            entities=r.entities,
            event_type=r.event_type,
            importance=r.importance,
        )
        assert _guy_decision(article, guy_profile) == "hidden"


# ── PR 13: new event-type keywords + league-order safety ──────────────────────


class TestPR13EventKeywords:
    """New contract-extension/coach-appointment keywords + excluded risky phrases."""

    def test_contract_extension_noun_is_signing(self):
        r = classify("הארכת חוזה לגארד של הפועל חולון", source_id="walla_sport", language="he")
        assert r.event_type == "signing"

    def test_extended_contract_masculine_is_signing(self):
        r = classify("הרכז האריך חוזה במכבי תל אביב", source_id="walla_sport", language="he")
        assert r.event_type == "signing"

    def test_extended_contract_feminine_is_signing(self):
        r = classify("בני הרצליה האריכה חוזה עם הסנטר", source_id="walla_sport", language="he")
        assert r.event_type == "signing"

    def test_new_contract_is_signing(self):
        r = classify("חוזה חדש לפורוורד בהפועל ירושלים", source_id="walla_sport", language="he")
        assert r.event_type == "signing"

    def test_coach_appointed_feminine_is_signing(self):
        r = classify("מונתה למאמנת הקבוצה בליגת העל סל", source_id="walla_sport", language="he")
        assert r.event_type == "signing"

    # Excluded phrases — must NOT fire signing (false-positive guards)

    def test_bare_released_not_signing(self):
        r = classify("השחקן שוחרר מבית החולים לאחר הפציעה", source_id="walla_sport", language="he")
        assert r.event_type != "signing"

    def test_bare_left_not_signing(self):
        r = classify("הגארד עזב את האימון באמצע", source_id="walla_sport", language="he")
        assert r.event_type != "signing"

    def test_new_coach_presentation_not_signing(self):
        r = classify("המאמן החדש דיבר עם האוהדים ביציע", source_id="walla_sport", language="he")
        assert r.event_type != "signing"

    def test_broadcast_schedule_stays_low_priority(self):
        r = classify("שידורי יורוקאפ השבוע: לוח משחקים מלא", source_id="walla_sport", language="he")
        assert r.event_type == "schedule"
        assert r.importance == "low"

    def test_no_title_win_regression_from_new_keywords(self):
        r = classify("זכה למחמאות אחרי הארכת חוזה", source_id="walla_sport", language="he")
        assert r.event_type != "title_win"


class TestPR13LeagueOrderSafety:
    """Lock the load-bearing detection orderings (no code change — regression net)."""

    def test_eurocup_checked_before_euroleague(self):
        r = classify("יורוליג מציגה את מפעל היורוקאפ המורחב", source_id="walla_sport", language="he")
        assert r.league == "EuroCup"

    def test_football_maccabi_beats_basketball_keyword(self):
        r = classify("מכבי חיפה חתמה על חלוץ", source_id="walla_sport", language="he")
        assert r.sport == "football"
        assert "Maccabi Tel Aviv Basketball" not in r.entities

    def test_ibl_club_maps_to_israeli_league(self):
        r = classify("הפועל חולון ניצחה את בני הרצליה", source_id="walla_sport", language="he")
        assert r.sport == "basketball"
        assert r.league == "Israeli Basketball League"

    def test_nba_hebrew_team_maps_to_nba(self):
        r = classify("הלייקרס ניצחו את הסלטיקס", source_id="walla_sport", language="he")
        assert r.sport == "basketball"

    def test_football_article_never_gets_basketball_entity(self):
        r = classify("מכבי נתניה בניצחון בליגת העל", source_id="walla_sport", language="he")
        assert r.sport == "football"
        assert all("Basketball" not in e for e in r.entities)
