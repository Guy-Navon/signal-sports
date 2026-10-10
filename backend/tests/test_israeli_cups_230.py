"""
#230 — the Israeli basketball cups (Winner Cup, Super Cup).

Census #2 found both missing from the registry: 49 corpus rows, 39 with no competition, some
stored football or sport=unknown. The owner rated 15 of 16 Winner Cup articles low or better
and decided (2026-10-10) that following the IBL follows its cups.

Three layers, each kept in its own lane:
  1. FACTS — the cup is its own competition and basketball sport evidence. Bare "סופרקאפ" is
     not an alias: the corpus uses it for European and football super cups too.
  2. RELEVANCE — `parent="comp:ibl"` lifts a cup match to the IBL at scoring time only.
  3. EVENTS — a quarter-/semi-final is not a final (every Winner Cup group-stage story was
     `finals_result` because `hword("גמר")` matched inside "רבע הגמר").

Rows marked "corpus" are frozen verbatim and run through the real ingestion path
(`_normalise`, LLM disabled by conftest).
"""

from datetime import datetime, timezone

import pytest

from app.classification.event_evidence import validate_event_evidence
from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config
from app.models.article import Article
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2
from app.services.relevance_engine import match_competition_names
from app.taxonomy import COMPETITIONS, validate_registry

PROFILES = {p.user_id: p for p in SEED_PROFILES}


def _ingest(source_id: str, url: str, title: str, subtitle: str):
    item = RawSourceItem(source_id=source_id, url=url, title=title, published_at=None, summary=subtitle)
    article, _llm_ms, _gate = ingestion_service._normalise(item, get_source_config(source_id))
    return article


def _article(**kwargs) -> Article:
    defaults = dict(
        id="t230", source="test", source_display_name="Test", url="https://example.com",
        title="t", language="he", published_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        sport="basketball", league=None, entities=[], event_type="news", importance="medium",
        confidence=0.9, tags=[], primary_competition=None, article_competitions=[],
        entity_ids=[], taxonomy_version=1,
    )
    defaults.update(kwargs)
    return Article(**defaults)


# ── 1. Registry ──────────────────────────────────────────────────────────────

class TestRegistry:
    def test_cups_are_basketball_children_of_the_ibl(self):
        for cid in ("comp:winner_cup", "comp:il_super_cup"):
            comp = COMPETITIONS[cid]
            assert comp.sport == "basketball"
            assert comp.parent == "comp:ibl"

    def test_parent_rules_are_validated(self):
        assert validate_registry() == []

    def test_cups_ride_on_the_league_follow_not_their_own(self):
        # Not offered in onboarding (no "בקרוב" chip either): following the IBL
        # already follows them, so a separate follow would be redundant.
        from app.api.routes_taxonomy import build_catalog
        from app.taxonomy.policy import competition_selectable

        listed = {c.id for s in build_catalog().sports for c in s.competitions}
        for cid in ("comp:winner_cup", "comp:il_super_cup"):
            assert not competition_selectable(cid)
            assert cid not in listed
        assert competition_selectable("comp:ibl")


# ── 2. Facts ─────────────────────────────────────────────────────────────────

class TestCupFacts:
    def test_winner_cup_makes_a_football_row_basketball(self):
        # corpus: stored football / team:hapoel_jlm_fc before #230
        a = _ingest(
            "israel_hayom_sport", "https://www.israelhayom.co.il/sport/article/21451377",
            "שלשה אחת הספיקה: הפועל ירושלים העפילה לרבע גמר גביע ווינר",
            "משחק רע מחוץ לקשת של החבורה מהבירה (1/20) הספיק כדי לנצח את הפועל באר שבע/דימונה "
            "ולהבטיח את המקום בשלב הבא",
        )
        assert a.sport == "basketball"
        assert a.entity_ids == ["team:hapoel_jlm_bb"]
        # primary is set only when it matches the legacy league (facts.py); the cup is
        # still explicit article evidence in article_competitions.
        assert "comp:winner_cup" in [a.primary_competition, *a.article_competitions]

    def test_qualified_super_cup_resolves_both_tel_aviv_clubs(self):
        # corpus: stored sport=unknown, no entities, hidden for Guy (rated feed)
        a = _ingest(
            "walla_sport", "https://sports.walla.co.il/item/3868575",
            "מכבי תל אביב - הפועל תל אביב 0:0 (רבע 1)",
            "שתי התל אביביות נאבקות על זכייה בתואר הראשון לעונת 2026/27: הסופרקאפ החברתי. "
            "בכורה מחודשת לקולסון בצהוב, ים מדר פוגש את האקסית. בריאנט חסר לאדומים",
        )
        assert a.sport == "basketball"
        assert "comp:il_super_cup" in a.article_competitions
        assert "team:maccabi_tlv_bb" in a.entity_ids
        assert score_article_v2(a, PROFILES["guy"]).decision != "hidden"

    def test_winner_sal_cup_is_the_cup_not_the_league(self):
        # corpus: "גביע ווינר סל" used to match the IBL keyword "ווינר סל"
        a = _ingest(
            "ynet_sport", "https://www.ynet.co.il/sport/article/one533750",
            'רבע 3, 04:35: הפועל י-ם - הפועל ב"ש 40:54',
            "גביע ווינר סל: הביתיים שולטים בצבע אך מתקשים לקלוע מחוץ לקשת בזריקות פנויות. "
            "מנגד, האורחת נשארת בתמונה בזכות יכולת טובה של לובל קאביל לשלוש",
        )
        assert "comp:winner_cup" in a.article_competitions
        assert "comp:ibl" not in [a.primary_competition, *a.article_competitions]

    # ── Adversarial neighbour: the bare word stays unregistered ──────────────
    def test_bare_super_cup_in_french_football_stays_football(self):
        # corpus: Lens won the (French football) super cup
        a = _ingest(
            "walla_sport", "https://sports.walla.co.il/item/3867961",
            "לאנס צפויה לפטר את דינו טופמולר אחרי ארבעה משחקי ליגה בלבד",
            "הגרמני הצעיד את הקבוצה מצפון צרפת לזכייה בסופרקאפ, אבל מאז התוצאות והיכולת לא "
            "משכנעות. יאניק קאהוזאק צפוי להחליפו",
        )
        assert a.sport != "basketball"
        assert "comp:il_super_cup" not in [a.primary_competition, *a.article_competitions]


# ── 3. Relevance: following the IBL follows its cups ─────────────────────────

class TestParentCompetitionMatch:
    def test_cup_article_matches_an_ibl_follow_with_provenance(self):
        a = _article(article_competitions=["comp:winner_cup"])
        hit = match_competition_names(a, ["Israeli Basketball League"])
        assert hit == ("explicit", "Israeli Basketball League", "via_parent_competition: comp:winner_cup")

    def test_cup_does_not_match_an_unrelated_follow(self):
        a = _article(primary_competition="comp:il_super_cup")
        assert match_competition_names(a, ["EuroLeague", "NBA"]) is None

    def test_the_league_does_not_match_a_cup_follow(self):
        # The relation is one-way: following a cup does not follow the league.
        a = _article(primary_competition="comp:ibl")
        assert match_competition_names(a, ["Winner Cup"]) is None

    def test_ibl_event_affinities_apply_to_the_cup(self):
        # Guy: comp:ibl × schedule = -2. A cup fixture is hidden exactly like a league one.
        shown = _article(primary_competition="comp:winner_cup", event_type="match_result")
        sched = _article(primary_competition="comp:winner_cup", event_type="schedule")
        assert score_article_v2(shown, PROFILES["guy"]).decision == "feed"
        assert score_article_v2(sched, PROFILES["guy"]).decision == "hidden"

    def test_deni_profile_is_untouched(self):
        a = _article(primary_competition="comp:winner_cup", event_type="match_result")
        assert score_article_v2(a, PROFILES["casual_deni_fan"]).decision == "hidden"


# ── 4. Events: a quarter-final is not a final ────────────────────────────────

class TestSubfinalRoundsAreNotFinals:
    @pytest.mark.parametrize("text", [
        # corpus: Winner Cup group stage — "רבע הגמר" plus a tip-off time read as a score
        "גביע ווינר: מכבי ראשון לציון פותחת עונה נגד הפועל אילת שני בגביע ווינר (20:30): "
        "הכתומים ינסו לעשות צעד לעבר רבע הגמר במשחק ביתי",
        "בני הרצליה הביסה את מכבי ראשל\"צ ועלתה לרבע גמר גביע ווינר 79:99",
        "ארגנטינה גברה 1:3 על שוויץ ועלתה לחצי הגמר",
        "england beat norway 2-1 to reach the semi-final",
        "spain won 2-0 in the quarterfinals",
    ], ids=["cup_group_stage", "cup_quarter", "wc_semi_he", "semi_final_en", "quarterfinals_en"])
    def test_subfinal_round_is_not_a_finals_result(self, text):
        assert not validate_event_evidence("finals_result", text, sport="basketball").valid

    # ── Adversarial neighbours: real finals must survive ─────────────────────
    def test_cup_final_with_a_score_is_still_a_final(self):
        assert validate_event_evidence(
            "finals_result", "מכבי ניצחה 85:80 בגמר הגביע", sport="basketball"
        ).valid

    def test_a_final_named_beside_a_semi_still_counts(self):
        # Masked, not blocked: the semi is removed, the final elsewhere remains.
        assert validate_event_evidence(
            "finals_result", "אחרי חצי הגמר: מכבי ניצחה 85:80 בגמר", sport="basketball"
        ).valid
