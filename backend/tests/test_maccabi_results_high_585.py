"""#585 — a Maccabi Tel Aviv game result is high (4+) for guy, not feed.

Owner decision 2026-11-18: game results only. guy's seed carried an explicit −1 on
Maccabi `match_result`, `regular_season_result` and `match_summary`, which capped a
Maccabi result at feed. Those three go. News, interview, analysis and opinion keep
their −1 (feed), and a result is still never a push (no override covers it).
"""
from datetime import datetime, timezone

import pytest

from app.models.article import Article
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2

GUY = next(p for p in SEED_PROFILES if p.user_id == "guy")
DENI = next(p for p in SEED_PROFILES if p.user_id == "casual_deni_fan")


def _maccabi(event_type, title="מכבי תל אביב הפסידה 97:95 לאולימפיאקוס"):
    return Article(
        id=f"t585_{event_type}", source="walla_sport", source_display_name="וואלה",
        url="https://example.test/585", title=title, language="he",
        published_at=datetime(2026, 11, 17, 21, 0, tzinfo=timezone.utc),
        sport="basketball", league=None,
        entities=["Maccabi Tel Aviv Basketball", "Olympiacos Basketball"],
        event_type=event_type, importance="medium", confidence=0.9, tags=[],
        entity_ids=["team:maccabi_tlv_bb", "team:olympiacos_bb"], taxonomy_version=1,
    )


@pytest.mark.parametrize("event_type", ["match_result", "regular_season_result", "match_summary"])
def test_maccabi_game_result_is_high_for_guy(event_type):
    assert score_article_v2(_maccabi(event_type), GUY).decision == "high_feed"


@pytest.mark.parametrize("event_type", ["news", "interview", "analysis", "opinion"])
def test_other_routine_maccabi_stories_stay_feed(event_type):
    assert score_article_v2(_maccabi(event_type), GUY).decision == "feed"


def test_a_maccabi_result_is_never_a_push():
    assert score_article_v2(_maccabi("match_result"), GUY).decision != "push"


def test_deni_profile_is_untouched_by_this():
    # The casual Deni fan does not follow Maccabi: hidden before and after.
    assert score_article_v2(_maccabi("match_result"), DENI).decision == "hidden"
