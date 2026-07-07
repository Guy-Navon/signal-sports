"""
Issue #40 Part B — participant-set competition inference.

A relevance-time-only reach tier for competition-anchored events: the
intersection of the participating TEAM entities' taxonomy memberships
identifies the event's competition when — and only when — it is a singleton.
Empty or multi-competition intersections abstain (fail-closed); explicit
competition evidence stays higher authority; the inferred competition is
never persisted into primary_competition/article_competitions.

Mirrored by frontend/src/engine/participantInference.test.js — the required
regression list from issue #40 must pass identically in both engines.
"""
from datetime import datetime, timezone

import pytest

from app.models.article import Article
from app.models.profile import UserProfile, TopicPreference
from app.seed.seed_profiles import SEED_PROFILES
from app.services.relevance_engine import (
    COMPETITION_ANCHORED_EVENTS,
    PARTICIPANT_INFERENCE_EXCLUDED_EVENTS,
    _participant_inferred_competition,
    score_article,
)


@pytest.fixture(scope="module")
def guy():
    return next(p for p in SEED_PROFILES if p.user_id == "guy")


@pytest.fixture(scope="module")
def euroleague_only_profile() -> UserProfile:
    """Synthetic single-topic EuroLeague-only follower (same shape as the #29
    suite's fixture): no team/entity preference, no IBL follow."""
    return UserProfile(
        user_id="test_euroleague_only",
        display_name="Test EuroLeague-only",
        profile_type="test",
        topics=[
            TopicPreference(
                topic_id="euroleague_only",
                label="EuroLeague only",
                sport="basketball",
                scope="league",
                priority=90,
                mode="all",
                leagues=["EuroLeague"],
                entities=[],
                event_rules={"match_result": "feed", "playoff_result": "high_feed"},
            ),
        ],
    )


@pytest.fixture(scope="module")
def nba_only_profile() -> UserProfile:
    """Synthetic broad-NBA follower with no entity follows — isolates the
    participant-inference tier from entity backing and other topics."""
    return UserProfile(
        user_id="test_nba_only",
        display_name="Test NBA-only",
        profile_type="test",
        topics=[
            TopicPreference(
                topic_id="nba_only",
                label="NBA only",
                sport="basketball",
                scope="league",
                priority=90,
                mode="all",
                leagues=["NBA"],
                entities=[],
                event_rules={"match_result": "feed", "finals_result": "high_feed"},
            ),
        ],
    )


def _make_article(**kwargs) -> Article:
    defaults = dict(
        id="test_article",
        source="test",
        source_display_name="Test",
        url="https://example.com",
        title="Test article",
        language="he",
        published_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
        sport="basketball",
        league=None,
        entities=[],
        event_type="match_result",
        importance="medium",
        confidence=0.9,
        tags=[],
        primary_competition=None,
        article_competitions=[],
        entity_ids=[],
        taxonomy_version=None,
    )
    defaults.update(kwargs)
    return Article(**defaults)


def _nba_game(**overrides) -> Article:
    """Lakers vs Celtics game result, post-ArticleFacts row, NO explicit
    competition evidence — the exact shape of the #29 QA hidden row."""
    base = dict(
        entities=["Los Angeles Lakers", "Boston Celtics"],
        entity_ids=["team:la_lakers", "team:boston_celtics"],
        event_type="match_result",
        importance="medium",
        taxonomy_version=1,
        league="NBA",  # classifier/LLM string — deliberately NOT explicit evidence
    )
    base.update(overrides)
    return _make_article(**base)


# ── The inference function itself ────────────────────────────────────────────

class TestInferenceContract:
    def test_unique_intersection_nba(self):
        assert _participant_inferred_competition(_nba_game()) == "comp:nba"

    def test_unique_intersection_euroleague(self):
        # Maccabi {IBL, EuroLeague} ∩ Real Madrid {ACB, EuroLeague} = {EuroLeague}
        article = _make_article(
            entity_ids=["team:maccabi_tlv_bb", "team:real_madrid_bb"],
            taxonomy_version=1,
        )
        assert _participant_inferred_competition(article) == "comp:euroleague"

    def test_ambiguous_intersection_abstains(self):
        # Maccabi {IBL, EuroLeague} ∩ Hapoel TLV {IBL, EuroLeague} — two shared → abstain
        article = _make_article(
            entity_ids=["team:maccabi_tlv_bb", "team:hapoel_tlv_bb"],
            taxonomy_version=1,
        )
        assert _participant_inferred_competition(article) is None

    def test_empty_intersection_abstains(self):
        # Lakers {NBA} ∩ Maccabi {IBL, EuroLeague} = {} → abstain
        article = _make_article(
            entity_ids=["team:la_lakers", "team:maccabi_tlv_bb"],
            taxonomy_version=1,
        )
        assert _participant_inferred_competition(article) is None

    def test_single_team_abstains(self):
        article = _make_article(entity_ids=["team:la_lakers"], taxonomy_version=1)
        assert _participant_inferred_competition(article) is None

    def test_players_and_coaches_are_never_participants(self):
        # Lakers + LeBron (player) is ONE participant, not two.
        article = _make_article(
            entity_ids=["team:la_lakers", "player:lebron_james"],
            taxonomy_version=1,
        )
        assert _participant_inferred_competition(article) is None
        # Two players alone are zero participants.
        article = _make_article(
            entity_ids=["player:lebron_james", "player:deni_avdija"],
            taxonomy_version=1,
        )
        assert _participant_inferred_competition(article) is None

    def test_incidental_third_team_can_only_force_abstention(self):
        # Lakers ∩ Celtics = {NBA}; an incidental Maccabi mention empties the
        # intersection → abstain. Fail-closed: never a wrong unique inference.
        article = _make_article(
            entity_ids=["team:la_lakers", "team:boston_celtics", "team:maccabi_tlv_bb"],
            taxonomy_version=1,
        )
        assert _participant_inferred_competition(article) is None

    def test_third_nba_team_keeps_unique_inference(self):
        article = _make_article(
            entity_ids=["team:la_lakers", "team:boston_celtics", "team:brooklyn_nets"],
            taxonomy_version=1,
        )
        assert _participant_inferred_competition(article) == "comp:nba"

    def test_legacy_row_infers_via_display_strings(self):
        article = _make_article(
            entities=["Brooklyn Nets", "Sacramento Kings"],
            entity_ids=[],
            taxonomy_version=None,
        )
        assert _participant_inferred_competition(article) == "comp:nba"

    def test_friendly_match_is_excluded_constant(self):
        assert "friendly_match" in PARTICIPANT_INFERENCE_EXCLUDED_EVENTS
        assert PARTICIPANT_INFERENCE_EXCLUDED_EVENTS <= COMPETITION_ANCHORED_EVENTS


# ── Required regression list (issue #40) — engine-level ─────────────────────

class TestRequiredRegressions:
    def test_broad_nba_follower_sees_participant_inferred_game(self, nba_only_profile):
        """Lakers vs Celtics game result, no explicit 'NBA' keyword → visible."""
        result = score_article(_nba_game(), nba_only_profile)
        assert result.decision == "feed", result.reasoning
        assert any("via_participant_inference: comp:nba" in r for r in result.reasoning)

    def test_guy_sees_participant_inferred_nba_game(self, guy):
        result = score_article(_nba_game(), guy)
        assert result.decision == "feed", result.reasoning
        assert result.matched_topic == "nba"

    def test_euroleague_follower_sees_maccabi_vs_real(self, euroleague_only_profile):
        article = _make_article(
            entity_ids=["team:maccabi_tlv_bb", "team:real_madrid_bb"],
            event_type="match_result",
            taxonomy_version=1,
        )
        result = score_article(article, euroleague_only_profile)
        assert result.decision == "feed", result.reasoning
        assert any("via_participant_inference: comp:euroleague" in r for r in result.reasoning)

    def test_euroleague_follower_does_not_see_ambiguous_israeli_derby(
        self, euroleague_only_profile
    ):
        """Maccabi vs Hapoel TLV ({IBL, EuroLeague} → abstain): the derby must
        NOT reach a EuroLeague-only follower — the same guarantee #29 enforces."""
        article = _make_article(
            entity_ids=["team:maccabi_tlv_bb", "team:hapoel_tlv_bb"],
            event_type="match_result",
            taxonomy_version=1,
        )
        result = score_article(article, euroleague_only_profile)
        assert result.decision == "hidden", result.reasoning

    def test_explicit_evidence_outranks_participant_inference(self, euroleague_only_profile):
        """A Maccabi-vs-Hapoel article WITH explicit EuroLeague evidence matches
        via the explicit tier — inference ambiguity does not block it, and the
        trace shows the explicit match, not participant inference."""
        article = _make_article(
            entity_ids=["team:maccabi_tlv_bb", "team:hapoel_tlv_bb"],
            primary_competition="comp:euroleague",
            event_type="match_result",
            taxonomy_version=1,
        )
        result = score_article(article, euroleague_only_profile)
        assert result.decision == "feed", result.reasoning
        assert any("תחרות מפורשת" in r for r in result.reasoning)
        assert not any("via_participant_inference" in r for r in result.reasoning)

    def test_participant_inference_never_creates_push_by_itself(self, nba_only_profile):
        """No explicit push rule → even a very_high-importance inferred finals
        result caps at high_feed (importance boost never reaches push)."""
        article = _nba_game(event_type="finals_result", importance="very_high")
        result = score_article(article, nba_only_profile)
        assert result.decision != "push", result.reasoning

    def test_empty_intersection_hides_for_nba_only(self, nba_only_profile):
        article = _make_article(
            entity_ids=["team:la_lakers", "team:maccabi_tlv_bb"],
            event_type="match_result",
            taxonomy_version=1,
        )
        result = score_article(article, nba_only_profile)
        assert result.decision == "hidden", result.reasoning

    def test_single_participant_hides_for_nba_only(self, nba_only_profile):
        article = _make_article(
            entity_ids=["team:la_lakers"],
            event_type="match_result",
            taxonomy_version=1,
        )
        result = score_article(article, nba_only_profile)
        assert result.decision == "hidden", result.reasoning


# ── Boundary behavior ────────────────────────────────────────────────────────

class TestBoundaries:
    def test_friendly_between_two_euroleague_clubs_not_inferred(
        self, euroleague_only_profile
    ):
        """A Maccabi–Real preseason friendly is not a EuroLeague game; the
        shared-membership premise fails for friendlies → excluded, hidden."""
        article = _make_article(
            entity_ids=["team:maccabi_tlv_bb", "team:real_madrid_bb"],
            event_type="friendly_match",
            taxonomy_version=1,
        )
        result = score_article(article, euroleague_only_profile)
        assert result.decision == "hidden", result.reasoning

    def test_team_anchored_event_does_not_use_participant_inference(
        self, euroleague_only_profile
    ):
        """A signing involving two clubs keeps using ordinary membership reach
        (team-anchored path), not participant inference — trace must show
        via_team_membership."""
        article = _make_article(
            entity_ids=["team:maccabi_tlv_bb", "team:real_madrid_bb"],
            event_type="signing",
            taxonomy_version=1,
        )
        result = score_article(article, euroleague_only_profile)
        assert result.decision == "feed", result.reasoning
        assert any("via_team_membership" in r for r in result.reasoning)
        assert not any("via_participant_inference" in r for r in result.reasoning)

    def test_unlisted_event_type_gets_no_inference(self, euroleague_only_profile):
        # `interview` is in neither allowlist — fail-closed stays fail-closed.
        article = _make_article(
            entity_ids=["team:maccabi_tlv_bb", "team:real_madrid_bb"],
            event_type="interview",
            taxonomy_version=1,
        )
        result = score_article(article, euroleague_only_profile)
        assert result.decision == "hidden", result.reasoning

    def test_participant_inference_not_subject_to_membership_ceiling(
        self, euroleague_only_profile
    ):
        """A participant-inferred playoff_result with a high_feed rule keeps
        high_feed (no entity backing needed) — unlike membership reach, which
        the #29 ceiling would cap at feed."""
        article = _make_article(
            entity_ids=["team:maccabi_tlv_bb", "team:real_madrid_bb"],
            event_type="playoff_result",
            taxonomy_version=1,
        )
        result = score_article(article, euroleague_only_profile)
        assert result.decision == "high_feed", result.reasoning
        assert any("via_participant_inference" in r for r in result.reasoning)

    def test_inference_never_persists_into_article_facts_fields(self):
        article = _nba_game()
        _ = _participant_inferred_competition(article)
        _ = score_article(
            article,
            next(p for p in SEED_PROFILES if p.user_id == "guy"),
        )
        assert article.primary_competition is None
        assert article.article_competitions == []
