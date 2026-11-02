"""
Issue #404 — closed-league reach.

An NBA club plays in no competition other than the NBA, so a story about an NBA club is an
NBA game even when the text never prints "NBA". Census #3 found such stories ending at
`no_matching_scope` (hidden) for a broad NBA follower: the season-opening roundup that only
names San Antonio, LeBron vs Westbrook in the Lakers locker room, Jokic vs the Denver fans.

The contract under test:
- The reach is a property of the COMPETITION (`Competition.closed`), never inferred from a
  club having a single registered membership. Hapoel Holon is registered only in the IBL and
  still plays the Basketball Champions League; Partizan is registered only in the EuroLeague
  because its domestic league is untracked.
- Every resolved entity's memberships must be exactly that one closed competition, at least
  one TEAM must carry it (a player's membership is season data and moves with him), and the
  article's sport must be the competition's sport.
- Competition-anchored events only (participant inference with one team, because the
  league is closed), minus title_win and friendly_match. `news`/`interview` keep no diffuse
  reach: the #64 Q2 owner lock (test_decision_contract.py) is untouched.
- It is opt-in and the weakest tier: the v2 scorer uses it only when no followed scope matched
  at all, as a `membership` match (feed ceiling). It never changes an already-visible
  article, never fires an always_push, and the legacy engine does not use it.
- Facts are untouched: nothing is written into primary_competition.
"""
from datetime import datetime, timezone

import pytest

from app.models.article import Article
from app.models.profile import UserProfile
from app.models.profile_v2 import EventAffinity, OverrideRule, ProfileV2, ScopeAffinity
from app.seed.seed_profiles import SEED_PROFILES
from app.services.preference_engine import score_article_v2
from app.services.relevance_engine import (
    closed_league_competition,
    match_competition_names,
    score_article,
)
from app.taxonomy import COMPETITIONS


def _article(**kwargs) -> Article:
    defaults = dict(
        id="closed_league_test",
        source="test",
        source_display_name="Test",
        url="https://example.com",
        title="Test article",
        language="he",
        published_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        sport="basketball",
        league="NBA",  # display string from membership: NOT competition evidence
        entities=[],
        event_type="match_result",
        importance="medium",
        confidence=0.9,
        tags=[],
        primary_competition=None,
        article_competitions=[],
        entity_ids=["team:san_antonio_spurs"],
        taxonomy_version=1,
    )
    defaults.update(kwargs)
    return Article(**defaults)


def _profile(v2: ProfileV2) -> UserProfile:
    return UserProfile(
        user_id="closed_league_user", display_name="Test", profile_type="test",
        topics=[], profile_v2=v2,
    )


@pytest.fixture(scope="module")
def guy():
    return next(p for p in SEED_PROFILES if p.user_id == "guy")


@pytest.fixture(scope="module")
def deni_fan():
    return next(p for p in SEED_PROFILES if p.user_id == "casual_deni_fan")


# ── The reach itself ─────────────────────────────────────────────────────────

class TestClosedLeagueCompetition:
    def test_only_the_nba_is_closed(self):
        # A closed league is registry truth, set deliberately per competition.
        assert {c.id for c in COMPETITIONS.values() if c.closed} == {"comp:nba"}

    def test_single_nba_club_story_reaches_the_nba(self):
        # rss_ba27a1aebdb3e9f91a23 shape: only San Antonio resolves, no competition named.
        assert closed_league_competition(_article()) == "comp:nba"

    def test_several_nba_clubs_and_an_nba_player(self):
        art = _article(entity_ids=["team:la_lakers", "player:lebron_james", "team:philadelphia_76ers"])
        assert closed_league_competition(art) == "comp:nba"

    def test_a_club_from_another_competition_abstains(self):
        # An NBA club next to Maccabi (IBL, EuroLeague): the story may be about either.
        art = _article(entity_ids=["team:denver_nuggets", "team:maccabi_tlv_bb"])
        assert closed_league_competition(art) is None

    def test_player_only_story_abstains(self):
        # A player's membership is season data; a club is the anchor.
        assert closed_league_competition(_article(entity_ids=["player:lebron_james"])) is None
        assert closed_league_competition(_article(entity_ids=["player:deni_avdija"])) is None

    @pytest.mark.parametrize("team_id", ["team:hapoel_holon", "team:partizan_bb"])
    def test_single_membership_club_of_an_open_competition_abstains(self, team_id):
        # Hapoel Holon (IBL only in the registry) plays the Basketball Champions League;
        # Partizan's domestic league is untracked. One membership is not a closed league.
        assert closed_league_competition(_article(entity_ids=[team_id])) is None

    @pytest.mark.parametrize("sport", ["unknown", "tennis", "football"])
    def test_sport_must_be_the_competitions_sport(self, sport):
        # Census #2: Rybakina's US Open title carried team:charlotte_hornets.
        assert closed_league_competition(_article(sport=sport, entity_ids=["team:charlotte_hornets"])) is None

    @pytest.mark.parametrize("event_type", ["title_win", "friendly_match"])
    def test_excluded_events_abstain(self, event_type):
        # title_win: a real NBA title names the NBA; homonyms do not (the Milwaukee Brewers'
        # baseball title resolved team:milwaukee_bucks). friendly_match: not a league game.
        assert closed_league_competition(_article(event_type=event_type)) is None

    @pytest.mark.parametrize("event_type", ["news", "interview", "analysis", "relocation"])
    def test_events_outside_both_allowlists_abstain(self, event_type):
        # #64 Q2 lock: an unknown/narrative event gets no diffuse reach. Extending it to
        # closed leagues is an owner decision (#404 NEEDS GUY), not this change.
        assert closed_league_competition(_article(event_type=event_type)) is None

    def test_team_anchored_events_keep_their_own_tier(self):
        # signing/injury/... already reach every membership through tier 4.
        art = _article(event_type="injury")
        assert closed_league_competition(art) is None
        assert match_competition_names(art, ["NBA"])[2] == "via_team_membership: comp:nba"

    def test_pre_facts_row_abstains(self):
        art = _article(taxonomy_version=None, entities=["San Antonio Spurs"], entity_ids=[])
        assert closed_league_competition(art) is None

    def test_reach_is_opt_in_in_the_matching_primitive(self):
        art = _article()
        assert match_competition_names(art, ["NBA"]) is None
        assert match_competition_names(art, ["NBA"], closed_league=True) == (
            "membership", "NBA", "via_closed_league_membership: comp:nba",
        )

    def test_explicit_evidence_still_wins(self):
        art = _article(primary_competition="comp:nba")
        assert match_competition_names(art, ["NBA"], closed_league=True)[0] == "explicit"

    def test_facts_are_not_written(self):
        art = _article()
        match_competition_names(art, ["NBA"], closed_league=True)
        assert art.primary_competition is None and art.article_competitions == []


# ── Preference V2: a rescue for otherwise-unmatched stories only ─────────────

class TestV2Rescue:
    def test_guy_sees_the_nba_club_story(self, guy):
        result = score_article_v2(_article(), guy)
        assert result.decision == "feed"
        assert result.matched_topic == "comp:nba"
        assert any("via_closed_league_membership: comp:nba" in c["detail"]
                   for c in result.contributions if c["step"] == "base_scope")

    def test_low_importance_club_game_is_low_feed(self, guy):
        art = _article(entity_ids=["team:ny_knicks", "player:jalen_brunson"], importance="low")
        assert score_article_v2(art, guy).decision == "low_feed"

    def test_club_news_stays_hidden(self, guy):
        # rss_291fbb5e8c7ed8f38f3c shape (Knicks + Brunson, news): #64 Q2 lock, unchanged.
        art = _article(entity_ids=["team:ny_knicks", "player:jalen_brunson"], event_type="news")
        assert score_article_v2(art, guy).decision == "hidden"

    def test_guy_scoped_nba_schedule_delta_still_hides(self, guy):
        assert score_article_v2(_article(event_type="schedule"), guy).decision == "hidden"

    def test_deni_fan_does_not_see_generic_nba(self, deni_fan):
        # The Deni fan follows Deni Avdija only; a Spurs story is noise for them.
        for event_type in ("match_result", "playoff_result", "match_summary"):
            assert score_article_v2(_article(event_type=event_type), deni_fan).decision == "hidden"

    def test_already_matched_story_is_unchanged(self, guy, deni_fan):
        # Deni + Portland, no competition: Guy already sees it through his Deni follow at
        # feed. The rescue must not add an NBA base plus the Deni boost (high_feed).
        art = _article(entity_ids=["player:deni_avdija", "team:portland_blazers"])
        assert score_article_v2(art, guy).decision == "feed"
        assert score_article_v2(art, deni_fan).decision == "feed"  # Deni match_result −1

    def test_rescue_is_capped_at_feed(self):
        profile = _profile(ProfileV2(
            scope_affinities=[ScopeAffinity(scope="competition", target_id="comp:nba", level=2)],
        ))
        result = score_article_v2(_article(importance="very_high"), profile)
        assert result.decision == "feed"
        assert any(c["step"] == "ceiling" for c in result.contributions)

    def test_rescue_never_fires_always_push(self):
        profile = _profile(ProfileV2(
            scope_affinities=[ScopeAffinity(scope="competition", target_id="comp:nba", level=1)],
            overrides=[OverrideRule(kind="always_push", scope="competition",
                                    target_id="comp:nba", event_type="match_result")],
        ))
        assert score_article_v2(_article(), profile).decision == "feed"

    def test_never_show_still_hides(self):
        profile = _profile(ProfileV2(
            scope_affinities=[ScopeAffinity(scope="competition", target_id="comp:nba", level=1)],
            event_affinities=[EventAffinity(scope_ref="comp:nba", event_type="match_result", delta=1)],
            overrides=[OverrideRule(kind="never_show", scope="competition",
                                    target_id="comp:nba", event_type="match_result")],
        ))
        assert score_article_v2(_article(), profile).decision == "hidden"

    def test_title_win_is_not_rescued(self, guy):
        # Guy has always_push comp:nba × title_win; an unnamed "title" must not reach it.
        art = _article(event_type="title_win", importance="very_high",
                       entity_ids=["team:milwaukee_bucks"])
        assert score_article_v2(art, guy).decision == "hidden"


def test_legacy_engine_does_not_use_the_reach(guy):
    # The rollback engine keeps its pre-#404 behavior.
    assert score_article(_article(), guy).decision == "hidden"


def test_registry_rejects_a_closed_league_club_in_a_second_competition(monkeypatch):
    # The flag is only true while every member club plays nowhere else.
    import dataclasses

    from app.taxonomy import integrity
    lakers = integrity.ENTITIES["team:la_lakers"]
    twin = dataclasses.replace(
        lakers, id="team:test_lakers_twin",
        memberships=(("comp:nba", None), ("comp:euroleague", None)),
    )
    monkeypatch.setitem(integrity.ENTITIES, twin.id, twin)
    assert any("team:test_lakers_twin: member of closed comp:nba" in e
               for e in integrity.validate_registry())
