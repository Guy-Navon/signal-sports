"""
#407 — "ליגת האלופות" is a name two sports share.

Census #3 (fit half): "סאנוגו כיכב, הפועל חולון ניצחה לראשונה בליגת האלופות" is the FIBA
Basketball Champions League, but the bare phrase was committed FOOTBALL vocabulary, so the
article was stored football / UEFA Champions League, Hapoel Holon was dropped as a
cross-sport entity and the story was hidden. Owner rating: feed.

Corpus measurement (frozen 2026-11-01 copy, held-out rows excluded): 72 rows say
"ליגת האלופות" / "champions league"; 65 are UEFA (or Asian) football, 7 are the
Basketball Champions League with Hapoel Holon or Bnei Herzliya.

The rule: the bare name takes the sport the text itself proves — a basketball club or
person named in a form that proves its sport, or a basketball scoreline, and no entity of
another sport — and is football otherwise (the corpus prior). Qualified names
("ליגת האלופות של פיב"א", "BCL") are the basketball competition outright.

Rows marked "corpus" are verbatim and run through the real ingestion path (`_normalise`,
LLM disabled by conftest).
"""

import pytest

from app.classification.sport_guards import committed_sport, shared_champions_league_sport
from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2
from app.taxonomy import COMPETITIONS, validate_registry

PROFILES = {p.user_id: p for p in SEED_PROFILES}


def _ingest(source_id: str, url: str, title: str, subtitle: str = ""):
    item = RawSourceItem(source_id=source_id, url=url, title=title, published_at=None, summary=subtitle)
    article, _llm_ms, _gate = ingestion_service._normalise(item, get_source_config(source_id))
    return article


def _comps(a) -> set:
    return {c for c in [a.primary_competition, *a.article_competitions] if c}


# ── corpus rows ──────────────────────────────────────────────────────────────

HOLON_FIRST_WIN = (  # corpus rss_fd09dded9f…, census #3 fit half, owner: feed
    "walla_sport", "https://sports.walla.co.il/item/3872248",
    "סאנוגו כיכב, הפועל חולון ניצחה לראשונה בליגת האלופות",
    "אחרי שהפסידה במחזור הפתיחה של ליגת האלופות וגם במחזור הפתיחה של ליגת העל, הפועל חולון "
    "התאוששה הערב (רביעי) עם ניצחון חוץ 84:86 על ספרטק סובוטיצה בסרביה.",
)
HOLON_SECOND_WIN = (  # corpus rss_0d2787d5…: only "חולון" in the title, the score in the subtitle
    "walla_sport", "https://sports.walla.co.il/item/3874096",
    "ממשיכה להתחבר: חולון השיגה ניצחון שני בליגת האלופות",
    "הסגולים גברו 81:88 על רסטה וכטה בגרמניה והשלימו את הסיבוב הראשון במאזן 1:2. "
    "מדפורד הצטיין עם 23 נקודות, סאנוגו הוסיף 17",
)
HERZLIYA_OPENER = (  # corpus rss_b9898e90…, census #2, owner: feed
    "ynet_sport", "https://www.ynet.co.il/sport/article/one535197",
    "הגנה במנוחה: בני הרצליה נכנעה 86:75 לחובנטוד",
    "החבורה מהשרון לא ניצלה יום קליעה רע מחוץ לקשת של היריבה הספרדית, ספגה סלים קלים בצבע "
    "והפסידה במשחק הפתיחה בליגת האלופות. ברוטון בלט (20 נק')",
)
HOLON_CHOLET = (  # corpus rss_9bfa06aa…, census #2, owner: feed — the qualified FIBA form
    "ynet_sport", "https://www.ynet.co.il/sport/article/one535203",
    "פתיחה נוראית: הפועל חולון הובסה 99:79 לשולה",
    "החבורה של קרוניץ' התקשתה בפתיחת ליגת האלופות של פיב\"א. דיארה ופאל הובילו את הצרפתים, "
    "אדאמה סאנוגו רשם דאבל דאבל אך לא הצליח למנוע את ההפסד",
)
JERUSALEM_EUROCUP_HOLON_BCL = (  # corpus rss_b3d02944…: "BCL" abbreviation
    "israel_hayom_sport", "https://www.israelhayom.co.il/sport/israeli-basketball/article/21628801",
    "הפועל ירושלים נותרה מושלמת ביורוקאפ, ניצחון ראשון לחולון ב-BCL",
    "החבורה של סשה אוברדוביץ' נקלעה לדרמה גדולה, אבל קני לופטון ג'וניור הוביל אותה ל-84:85 על "
    "סן פבלו בורגוס • חולוניה נאבקה באלופת סרביה ספרטק וסימנה וי ראשון באירופה העונה עם 84:86",
)

CITY_PSG = (  # corpus rss_4b5b6716…
    "israel_hayom_sport", "https://www.israelhayom.co.il/sport/world-soccer/article/21628166",
    "חי מליגת האלופות: מנצ'סטר סיטי - פריז סן ז'רמן 0:0",
    "המחזור השני של המפעל מפגיש בין שתי הענקיות באיתיחאד • אלופת אירופה בשנתיים האחרונות רוצה "
    "לספק הצהרה בממלכה • התכולים ניצחו בכל המשחקים שלהם העונה, מלבד מגן הקהילה",
)
JERUSALEM_WOMEN_UCL = (  # corpus rss_d25d6225…: a cross-sport twin club, football here
    "walla_sport", "https://sports.walla.co.il/item/3855476",
    "חלום ליגת האלופות מתחיל: הפועל ירושלים יוצאת למשימה היסטורית",
    "קבוצת הנשים של הפועל ירושלים תפגוש הערב את פאוק סלוניקי בחצי גמר מוקדמות המפעל, במטרה "
    "להפוך לישראלית הראשונה שעולה לשלב הבא במתכונת החדשה",
)
BEER_SHEVA_QUALIFIER = (  # corpus rss_919f4646…
    "israel_hayom_sport", "https://www.israelhayom.co.il/sport/israeli-soccer/article/21032594",
    "חי ממוקדמות ליגת האלופות: ויקינגור - הפועל באר שבע 0:0",
    "האדומים מתחילים את המסע לעבר ליגת האלופות, כשמשחק הראשון מבין שניים בסיבוב המוקדמות השני "
    "נערך באיסלנד • קינגס קאנגווה בהרכב בצל סערת א.א.ק אתונה",
)
ASIAN_CL = (  # corpus rss_0ed6f894…: the Asian (football) Champions League Two, no hint URL
    "walla_sport", "https://sports.walla.co.il/item/3872371",
    "עבדאללה חליחל כבש לראשונה בליגת האלופות המשנית של אסיה",
    "עבדאללה חליחל, שכבש שמונה שערים העונה בליגה הדרום קוריאנית, הבקיע היום (חמישי) שער בכורה "
    "בליגת האלופות המשנית של אסיה, אך לא מנע מגאנגוון הפסד ביתי 2:1 מול פנום פן קראון מקמבודיה.",
)


# ── 1. Registry ──────────────────────────────────────────────────────────────

class TestRegistry:
    def test_bcl_is_a_basketball_international_league(self):
        comp = COMPETITIONS["comp:bcl"]
        assert comp.sport == "basketball"
        assert comp.kind == "international_league"
        assert comp.parent is None
        assert validate_registry() == []

    def test_bcl_is_selectable_and_listed_after_eurocup(self):
        # Owner decision 2026-11-02 (R13): followable in onboarding.
        from app.api.routes_taxonomy import build_catalog
        from app.taxonomy.policy import competition_selectable

        assert competition_selectable("comp:bcl")
        assert not competition_selectable("comp:ucl")
        basketball = next(s for s in build_catalog().sports if s.id == "basketball")
        bcl = next(c for c in basketball.competitions if c.id == "comp:bcl")
        assert bcl.selectable
        ids = [c.id for c in basketball.competitions]
        assert ids.index("comp:bcl") == ids.index("comp:eurocup") + 1

    def test_a_user_can_follow_bcl_through_interests(self):
        from app.services.interests_service import (
            InterestFollow, InterestsPutRequest, InterestsValidationError, _validate,
        )
        _validate(InterestsPutRequest(follows=[
            InterestFollow(scope="competition", target_id="comp:bcl")]))
        with pytest.raises(InterestsValidationError):
            _validate(InterestsPutRequest(follows=[
                InterestFollow(scope="competition", target_id="comp:ucl")]))


# ── 2. The shared name ───────────────────────────────────────────────────────

class TestSharedName:
    @pytest.mark.parametrize("text", [
        "סאנוגו כיכב, הפועל חולון ניצחה לראשונה בליגת האלופות",   # club, multi-word alias
        "בני הרצליה ניצחה בליגת האלופות",
        "חולון גברה 81:88 על רסטה וכטה בליגת האלופות",             # basketball scoreline
    ])
    def test_named_basketball_evidence_makes_it_basketball(self, text):
        assert shared_champions_league_sport(text.lower()) == "basketball"

    @pytest.mark.parametrize("text", [
        "חי מליגת האלופות: מנצ'סטר סיטי - פריז סן ז'רמן 0:0",
        "עבדאללה חליחל כבש לראשונה בליגת האלופות המשנית של אסיה",
        # "ספרס" is Tottenham in football copy; a one-word alias proves nothing.
        "ספרס ניצחה בליגת האלופות",
        # A cross-sport twin (no context) is not basketball evidence.
        "הפועל ירושלים בליגת האלופות",
        # Guarded European club: its bare name usually means football.
        "ריאל מדריד אלוף ליגת האלופות",
        # A football club beside a basketball one: contradiction, keep the default.
        "מכבי חיפה והפועל חולון בליגת האלופות",
    ])
    def test_otherwise_it_is_football(self, text):
        assert shared_champions_league_sport(text.lower()) == "football"

    def test_committed_sport_follows_the_shared_name(self):
        assert committed_sport("הפועל חולון ניצחה בליגת האלופות") == "basketball"
        assert committed_sport("ריאל מדריד ניצחה בליגת האלופות") == "football"

    @pytest.mark.parametrize("text", [
        'פתיחת ליגת האלופות של פיב"א', "ליגת האלופות בכדורסל", "basketball champions league",
    ])
    def test_qualified_forms_are_committed_basketball(self, text):
        assert committed_sport(text) == "basketball"


# ── 3. Facts on corpus rows ──────────────────────────────────────────────────

class TestBasketballChampionsLeagueFacts:
    def test_holon_first_win_is_basketball_bcl_with_the_club(self):
        a = _ingest(*HOLON_FIRST_WIN)
        assert a.sport == "basketball"
        assert a.primary_competition == "comp:bcl"
        assert a.league == "Basketball Champions League"
        assert "team:hapoel_holon" in a.entity_ids
        assert "comp:ucl" not in _comps(a)

    def test_holon_second_win_score_in_subtitle(self):
        a = _ingest(*HOLON_SECOND_WIN)
        assert a.sport == "basketball"
        assert "comp:bcl" in _comps(a)
        assert "comp:ucl" not in _comps(a)

    def test_herzliya_subtitle_mention_is_bcl_not_ucl(self):
        a = _ingest(*HERZLIYA_OPENER)
        assert a.sport == "basketball"
        assert "comp:bcl" in _comps(a)
        assert "comp:ucl" not in _comps(a)

    def test_qualified_fiba_form(self):
        a = _ingest(*HOLON_CHOLET)
        assert a.sport == "basketball"
        assert "comp:bcl" in _comps(a)

    def test_bcl_abbreviation_beside_eurocup(self):
        a = _ingest(*JERUSALEM_EUROCUP_HOLON_BCL)
        assert a.primary_competition == "comp:eurocup"
        assert "comp:bcl" in a.article_competitions


class TestFootballChampionsLeagueStaysFootball:
    @pytest.mark.parametrize("row", [CITY_PSG, BEER_SHEVA_QUALIFIER, ASIAN_CL],
                             ids=["city_psg", "beer_sheva", "asian_cl"])
    def test_uefa_rows_stay_football_ucl(self, row):
        a = _ingest(*row)
        assert a.sport == "football"
        assert a.primary_competition == "comp:ucl"
        assert "comp:bcl" not in _comps(a)

    def test_cross_sport_twin_resolves_to_the_football_club(self):
        a = _ingest(*JERUSALEM_WOMEN_UCL)
        assert a.sport == "football"
        assert a.entity_ids == ["team:hapoel_jlm_fc"]
        assert a.primary_competition == "comp:ucl"

    @pytest.mark.parametrize("title", [
        "ספרס ניצחה בליגת האלופות",
        "מכבי תל אביב העפילה לשלב הבתים של ליגת האלופות",
        "ריאל מדריד אלוף ליגת האלופות",
    ])
    def test_weak_or_ambiguous_names_keep_football(self, title):
        a = _ingest("walla_sport", "https://sports.walla.co.il/item/1", title)
        assert a.sport == "football"
        assert a.primary_competition == "comp:ucl"

    @pytest.mark.parametrize("row", [CITY_PSG, BEER_SHEVA_QUALIFIER, ASIAN_CL, JERUSALEM_WOMEN_UCL],
                             ids=["city_psg", "beer_sheva", "asian_cl", "jerusalem_women"])
    def test_uefa_rows_stay_hidden_for_both_profiles(self, row):
        a = _ingest(*row)
        assert score_article_v2(a, PROFILES["guy"]).decision == "hidden"
        assert score_article_v2(a, PROFILES["casual_deni_fan"]).decision == "hidden"


# ── 4. Relevance ─────────────────────────────────────────────────────────────

def _guy_following_bcl():
    """Guy's seed plus the proposed (owner-pending) comp:bcl follow at the EuroCup level."""
    from app.models.profile_v2 import EventAffinity, ScopeAffinity

    guy = PROFILES["guy"].model_copy(deep=True)
    v2 = guy.profile_v2
    v2.scope_affinities.append(ScopeAffinity(scope="competition", target_id="comp:bcl", level=1))
    v2.event_affinities += [
        EventAffinity(scope_ref="comp:bcl", event_type="generic_preview", delta=-1),
        EventAffinity(scope_ref="comp:bcl", event_type="schedule", delta=-1),
    ]
    return guy


ISRAELI_BCL_ROWS = [HOLON_FIRST_WIN, HOLON_SECOND_WIN, HERZLIYA_OPENER, HOLON_CHOLET]
ISRAELI_BCL_IDS = ["holon_first", "holon_second", "herzliya", "holon_cholet"]


class TestRelevance:
    @pytest.mark.parametrize("row", ISRAELI_BCL_ROWS, ids=ISRAELI_BCL_IDS)
    def test_seed_profiles_do_not_move(self, row):
        # No followed scope reaches a BCL game in today's seeds: the facts fix alone
        # changes no decision. Deni must never drift.
        a = _ingest(*row)
        assert score_article_v2(a, PROFILES["guy"]).decision == "hidden"
        assert score_article_v2(a, PROFILES["casual_deni_fan"]).decision == "hidden"

    @pytest.mark.parametrize("row", [HOLON_FIRST_WIN, HOLON_SECOND_WIN, HERZLIYA_OPENER],
                             ids=["holon_first", "holon_second", "herzliya"])
    def test_a_bcl_follow_shows_israeli_bcl_games_at_feed(self, row):
        assert score_article_v2(_ingest(*row), _guy_following_bcl()).decision == "feed"

    def test_a_bcl_story_typed_news_is_low_feed(self):
        # "הובסה 99:79" is not read as a match result, so the event is news, one notch
        # below a game (owner: feed). The event detector is out of #407's scope.
        a = _ingest(*HOLON_CHOLET)
        assert a.event_type == "news"
        assert score_article_v2(a, _guy_following_bcl()).decision == "low_feed"

    def test_a_bcl_follow_never_pushes_and_leaves_uefa_hidden(self):
        guy = _guy_following_bcl()
        for row in ISRAELI_BCL_ROWS:
            assert score_article_v2(_ingest(*row), guy).decision != "push"
        for row in (CITY_PSG, BEER_SHEVA_QUALIFIER, ASIAN_CL, JERUSALEM_WOMEN_UCL):
            assert score_article_v2(_ingest(*row), guy).decision == "hidden"


# ── 5. Review fixes (PR #417) ────────────────────────────────────────────────

def _walla(title, subtitle=""):
    return _ingest("walla_sport", "https://sports.walla.co.il/item/1", title, subtitle)


class TestCompetitionNameIsNotTitleWinEvidence:
    # The bare name is masked before title_win analysis, like every registered
    # competition name containing a champion noun (event_evidence).
    @pytest.mark.parametrize("title", [
        "Champions League: Inter 2-1 Barcelona",
        "ברצלונה הוכתרה בליגת האלופות",
        "champions league odds 60:40 for city",
    ])
    def test_bare_name_does_not_make_a_title_win(self, title):
        a = _walla(title)
        assert a.event_type != "title_win"
        assert a.sport == "football"
        assert score_article_v2(a, PROFILES["guy"]).decision == "hidden"


class TestSharedVocabularyIsNotEnough:
    # "ריבאונד" is committed basketball vocabulary, but football copy says
    # "כבש מריבאונד". Only qualified FIBA names (or כדורסל) make the bare name
    # basketball through vocabulary; everything else needs a named cue.
    @pytest.mark.parametrize("title", [
        "גול מריבאונד של מכבי תל אביב בליגת האלופות",
        "מכבי חיפה כבשה מריבאונד בליגת האלופות",
    ])
    def test_rebound_in_football_copy_is_not_basketball(self, title):
        assert shared_champions_league_sport(title) == "football"
        a = _walla(title)
        assert a.sport != "basketball"
        assert "comp:bcl" not in _comps(a)
        assert "team:maccabi_tlv_bb" not in a.entity_ids
        assert score_article_v2(a, PROFILES["guy"]).decision == "hidden"

    def test_basketball_word_still_reads_basketball(self):
        assert shared_champions_league_sport("ליגת האלופות בכדורסל: חולון ניצחה") == "basketball"

    def test_an_llm_football_is_not_overridden_to_basketball(self):
        from app.classification.llm_result import LLMClassificationResult
        from app.classification.merge import merge_with_guardrails
        from app.ingestion.classifier import classify

        title = "גול מריבאונד של מכבי תל אביב בליגת האלופות"
        rules = classify(title, source_id="walla_sport", language="he")
        llm = LLMClassificationResult(
            sport="football", league=None, entities=["Maccabi Tel Aviv FC"],
            event_type="news", importance="medium", confidence=0.9, reason="recorded",
        )
        merged, _ = merge_with_guardrails(llm, rules, title.lower())
        assert merged.sport == "football"

    def test_an_llm_football_through_the_ingestion_path(self, monkeypatch):
        from app.classification.llm_result import LLMClassificationResult

        class _Recorded:
            can_classify = True
            last_failure_was_connect_error = False
            provider_id = "recorded-407"

            def classify_title(self, title, language, subtitle=None):
                return LLMClassificationResult(
                    sport="football", league=None, entities=["Maccabi Tel Aviv FC"],
                    event_type="news", importance="medium", confidence=0.9, reason="recorded",
                )

        monkeypatch.setattr(ingestion_service, "_LLM_PROVIDER", _Recorded())
        a = _walla("גול מריבאונד של מכבי תל אביב בליגת האלופות")
        assert a.sport == "football"
        assert "comp:bcl" not in _comps(a)


class TestOneWordAliasIsNotACue:
    # "deni" inside "denied" is a pre-existing substring alias bug (#415). It must not
    # also turn a UEFA story into basketball through the shared name.
    def test_one_word_person_alias_does_not_prove_basketball(self):
        title = "Arsenal denied a late penalty in Champions League defeat"
        assert shared_champions_league_sport(title.lower()) == "football"
        a = _walla(title)
        assert a.sport == "football"
        assert "player:deni_avdija" not in a.entity_ids
        assert score_article_v2(a, PROFILES["guy"]).decision == "hidden"
        assert score_article_v2(a, PROFILES["casual_deni_fan"]).decision == "hidden"

    def test_a_full_person_name_still_proves_basketball(self):
        assert shared_champions_league_sport("דני אבדיה צפה בליגת האלופות") == "basketball"


class TestBclAbbreviationIsAWholeWord:
    def test_bcl_inside_a_word_is_not_the_competition(self):
        a = _ingest("ynet_sport", "https://www.ynet.co.il/sport/article/x", "abcl report", "")
        assert "comp:bcl" not in _comps(a)
        assert a.sport != "basketball"


class TestDetectLeagueAsksTheSharedName:
    def test_basketball_hint_with_a_football_reading_is_not_bcl(self):
        # A basketball-section article that mentions the UEFA competition in passing.
        from app.ingestion.classifier import _detect_league
        text = "מכבי חיפה בליגת האלופות"
        assert shared_champions_league_sport(text) == "football"
        assert _detect_league(text, "basketball") != "Basketball Champions League"


# ── 6. Onboarding: comp:bcl is calibratable (owner decision R13) ─────────────

class TestCalibration:
    def test_bcl_has_calibration_items_like_eurocup(self):
        from app.calibration_v2 import CALIBRATION_ITEMS
        items = [i for i in CALIBRATION_ITEMS if i.competition_id == "comp:bcl"]
        assert len(items) >= 4
        assert all(i.sport == "basketball" and not i.entity_ids for i in items)
        assert len({i.event_type for i in items}) >= 3
        assert len({i.importance for i in items}) >= 2

    def test_following_bcl_selects_its_items(self):
        from app.calibration_v2.selection import select_items
        from app.models.profile_v2 import ProfileV2, ScopeAffinity
        v2 = ProfileV2(scope_affinities=[ScopeAffinity(
            scope="competition", target_id="comp:bcl", level=1, source="explicit")])
        picked = [i for i in select_items(v2, "u-bcl") if i.competition_id == "comp:bcl"]
        assert len(picked) >= 2

    def test_rating_bcl_items_infers_a_bcl_scope(self):
        from app.calibration_v2 import CALIBRATION_ITEMS, infer_calibration_profile
        ratings = {i.id: "interesting" for i in CALIBRATION_ITEMS
                   if i.competition_id == "comp:bcl"}
        inferred = infer_calibration_profile(ratings)
        targets = {a.target_id for a in inferred.scope_affinities if a.scope == "competition"}
        assert "comp:bcl" in targets
