"""Owner rule (#423): an injury to a team's player pushes for a user who follows that team or
a player on it. The registry's current-team link (`team_id`) carries it."""
import pytest

from app.classification.attention_evidence import attention_evidence
from app.ingestion import ingestion_service
from app.ingestion.adapters.base import RawSourceItem
from app.ingestion.config import get_source_config
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2

MACCABI = "team:maccabi_tlv_bb"
PORTLAND = "team:portland_blazers"


def _profile(user_id):
    return next(p for p in SEED_PROFILES if p.user_id == user_id)


def _article(title, subtitle=""):
    article, _, _ = ingestion_service._normalise(
        RawSourceItem(source_id="ynet_sport", url="https://example.test/x", title=title,
                      published_at=None, summary=subtitle),
        get_source_config("ynet_sport"), llm_available=False,
    )
    return article


@pytest.mark.parametrize("title", ["לונדברג נפצע וייעדר", "ים מדר ייעדר חודש"])
def test_own_player_named_without_the_club_pushes_for_a_team_follower(title):
    article = _article(title)
    assert article.event_type == "injury"
    assert MACCABI in article.classification_trace["attention"]["subject_entity_ids"]
    assert score_article_v2(article, _profile("guy")).decision == "push"
    assert score_article_v2(article, _profile("casual_deni_fan")).decision == "hidden"


@pytest.mark.parametrize("user_id", ["guy", "casual_deni_fan"])
def test_teammate_injury_pushes_for_a_follower_of_a_player_on_the_team(user_id):
    article = _article("פורטלנד: השחקן נפצע וייעדר חודש")
    assert article.entity_ids == [PORTLAND]
    assert score_article_v2(article, _profile(user_id)).decision == "push"


@pytest.mark.parametrize("title", ["פורטלנד ניצחה את דנבר 110:100", "פורטלנד מתכוננת לעונה החדשה"])
def test_other_stories_on_the_followed_players_team_stay_hidden_for_the_deni_fan(title):
    assert score_article_v2(_article(title), _profile("casual_deni_fan")).decision == "hidden"


def test_opponent_of_the_followed_players_team_does_not_push():
    article = _article("השחקן שייעדר מול פורטלנד")
    assert PORTLAND not in article.classification_trace["attention"]["subject_entity_ids"]
    assert score_article_v2(article, _profile("casual_deni_fan")).decision != "push"


def test_own_player_rule_is_scoped_to_injury_events():
    evidence = attention_evidence("לונדברג חתם על חוזה", "", "interview", [MACCABI])
    assert MACCABI not in evidence["subject_entity_ids"]
