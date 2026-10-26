"""The reader's "למה אצלך" line (journey audit D6, #360).

The feed used to show the engine trace ("ניקוד: 3 → חשוב", "via_team_membership:
comp:euroleague") to every reader. The reader now gets one Hebrew sentence built only from
the step that actually decided the article (`contributions`), with taxonomy names. When no
step can be stated accurately there is no sentence at all — never an invented one.
"""
from datetime import datetime, timezone

from app.models.article import Article
from app.models.profile import UserProfile
from app.models.profile_v2 import OverrideRule, ProfileV2, ScopeAffinity
from app.services.consumer_reason import consumer_reason
from app.services.preference_engine import score_article_v2


def _article(**kw) -> Article:
    base = dict(
        id="why", source="test", source_display_name="Test", url="https://example.com",
        title="t", language="he", published_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
        sport="basketball", league=None, entities=[], event_type="news", importance="medium",
        confidence=0.9, tags=[], primary_competition=None, article_competitions=[],
        entity_ids=[], taxonomy_version=1,
    )
    base.update(kw)
    return Article(**base)


def _why(article: Article, *affinities, overrides=()) -> str | None:
    profile = UserProfile(user_id="u", display_name="u", profile_type="test", topics=[],
                          profile_v2=ProfileV2(scope_affinities=list(affinities),
                                               overrides=list(overrides)))
    result = score_article_v2(article, profile, set())
    return consumer_reason(result, article)


def test_a_followed_team():
    why = _why(_article(entity_ids=["team:maccabi_tlv_bb"]),
               ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=1))
    assert why == "מכבי תל אביב (כדורסל) ברשימת המעקב שלך"


def test_a_followed_competition_named_in_the_article():
    why = _why(_article(primary_competition="comp:euroleague", article_competitions=["comp:euroleague"]),
               ScopeAffinity(scope="competition", target_id="comp:euroleague", level=1))
    assert why == "יורוליג ברשימת המעקב שלך"


def test_a_competition_reached_through_a_team_names_that_team():
    # match_kind "membership": the article is about a team that plays in the followed league
    why = _why(_article(entity_ids=["team:portland_blazers"], event_type="signing"),
               ScopeAffinity(scope="competition", target_id="comp:nba", level=1))
    assert why == "פורטלנד בלייזרס משחקת ב-NBA, שברשימת המעקב שלך"


def test_a_followed_person_in_the_article_is_added():
    why = _why(_article(entity_ids=["player:deni_avdija", "team:portland_blazers"],
                        primary_competition="comp:nba", article_competitions=["comp:nba"]),
               ScopeAffinity(scope="competition", target_id="comp:nba", level=2),
               ScopeAffinity(scope="player", target_id="player:deni_avdija", level=2))
    # equal points: the engine keeps the broader scope as the base and boosts the person
    assert why == "NBA ברשימת המעקב שלך · בכתבה: דני אבדיה"


def test_the_stronger_followed_person_is_the_reason():
    why = _why(_article(entity_ids=["player:deni_avdija", "team:portland_blazers"],
                        primary_competition="comp:nba", article_competitions=["comp:nba"]),
               ScopeAffinity(scope="competition", target_id="comp:nba", level=1),
               ScopeAffinity(scope="player", target_id="player:deni_avdija", level=2))
    assert why == "דני אבדיה ברשימת המעקב שלך"


def test_a_push_says_why_it_is_urgent():
    why = _why(_article(entity_ids=["team:maccabi_tlv_bb"], event_type="negotiation"),
               ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2),
               overrides=[OverrideRule(kind="always_push", scope="team",
                                       target_id="team:maccabi_tlv_bb", event_type="negotiation")])
    assert why == "עדכון דחוף — משא ומתן · מכבי תל אביב (כדורסל) ברשימת המעקב שלך"


def test_a_hidden_article_has_no_line():
    assert _why(_article(sport="tennis"),
                ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=1)) is None


def test_no_engine_vocabulary_ever_reaches_the_reader():
    why = _why(_article(entity_ids=["team:portland_blazers"], event_type="signing"),
               ScopeAffinity(scope="competition", target_id="comp:nba", level=1))
    for leak in ("via_", "comp:", "team:", "ניקוד", "high", "membership", "match_kind"):
        assert leak not in why


def test_a_competition_reached_through_a_player_names_the_player():
    # membership reach via the player's club (registry team_id); no team named in the article
    why = _why(_article(entity_ids=["player:lebron_james"], event_type="signing"),
               ScopeAffinity(scope="competition", target_id="comp:nba", level=2))
    assert why == "לברון ג'יימס משחק ב-NBA, שברשימת המעקב שלך"


def test_the_followed_person_is_not_named_twice():
    # equal levels: the league stays the base and the person is the boost (the corpus shape)
    why = _why(_article(entity_ids=["player:deni_avdija"], event_type="signing"),
               ScopeAffinity(scope="competition", target_id="comp:nba", level=2),
               ScopeAffinity(scope="player", target_id="player:deni_avdija", level=2))
    assert why == "דני אבדיה משחק ב-NBA, שברשימת המעקב שלך"
