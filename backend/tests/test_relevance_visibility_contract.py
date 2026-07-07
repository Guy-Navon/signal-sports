"""
Issue #29 — Relevance Visibility Contract.

Covers the required-coverage list from the issue: competition-aware
league/league_group matching (explicit / legacy / team-membership reach),
the membership-only feed ceiling, the entity_ids-first identity contract
(both for membership reach and for entity backing), the explicit
team/competition event-reach allowlists (fail-closed for unlisted event
types, `interview` deliberately excluded), the removed
`major_importance_fallback` leak, and the documented sport=unknown behavior.

Test-local `Article`/profile fixtures are used throughout (per project
convention here) rather than growing `seed_articles.py`, since these
scenarios don't need to be discoverable in the manual debug/product UI.
"""
from datetime import datetime, timezone

import pytest

from app.models.article import Article
from app.models.profile import UserProfile, TopicPreference
from app.seed.seed_profiles import SEED_PROFILES
from app.services.relevance_engine import (
    score_article,
    TEAM_ANCHORED_EVENTS,
    COMPETITION_ANCHORED_EVENTS,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def guy():
    return next(p for p in SEED_PROFILES if p.user_id == "guy")


@pytest.fixture(scope="module")
def deni_fan():
    return next(p for p in SEED_PROFILES if p.user_id == "casual_deni_fan")


@pytest.fixture(scope="module")
def euroleague_only_profile() -> UserProfile:
    """A synthetic single-topic profile that follows EuroLeague only — no
    Maccabi/entity preference, no IBL follow. Used to prove team-anchored
    membership reach and competition-anchored explicit-only matching without
    Guy's broader topic set masking the behavior."""
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
                event_rules={
                    "match_result": "feed",
                    "signing": "feed",
                    "negotiation": "feed",
                    "interview": "feed",
                    "major_signing": "high_feed",
                },
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


# ── Event-reach allowlists — sanity on the constants themselves ─────────────

def test_event_reach_allowlists_are_disjoint():
    assert TEAM_ANCHORED_EVENTS.isdisjoint(COMPETITION_ANCHORED_EVENTS)


def test_interview_is_in_neither_allowlist():
    assert "interview" not in TEAM_ANCHORED_EVENTS
    assert "interview" not in COMPETITION_ANCHORED_EVENTS


# ── League-visibility suite ──────────────────────────────────────────────────

def test_maccabi_ramat_gan_signing_visible_via_ibl_follow_not_maccabi_tlv(guy):
    """Case 1 (product level): a Maccabi Ramat Gan signing must surface via
    Guy's broad Israeli Basketball League interest alone — no explicit
    competition text, no dedicated team preference — but must NOT receive
    Maccabi-Tel-Aviv-level (push-eligible) treatment, and must not be hidden."""
    article = _make_article(
        entities=["Maccabi Ramat Gan"],
        entity_ids=["team:maccabi_ramat_gan"],
        event_type="signing",
        importance="medium",
        taxonomy_version=1,
    )
    result = score_article(article, guy)
    assert result.decision in ("feed", "high_feed"), result.reasoning
    assert result.matched_topic == "israeli_basketball"
    assert result.matched_topic != "maccabi_tel_aviv_basketball"


def test_hapoel_tlv_roster_release_visible_via_ibl_follow(guy):
    """Case 8: Hapoel Tel Aviv Basketball roster release is visible via a
    broad league follow with no manual team follow needed. Hapoel TLV is a
    member of both IBL and EuroLeague, so either (higher-priority EuroLeague
    wins the tie) may end up as the matched topic — the point is it's
    reachable via membership on a league Guy actually follows, not hidden."""
    article = _make_article(
        entities=["Hapoel Tel Aviv Basketball"],
        entity_ids=["team:hapoel_tlv_bb"],
        event_type="release",
        importance="medium",
        taxonomy_version=1,
    )
    result = score_article(article, guy)
    assert result.decision != "hidden", result.reasoning
    assert result.matched_topic in ("israeli_basketball", "euroleague")
    assert any("via_team_membership" in line for line in result.reasoning)


def test_israeli_roster_story_without_league_keyword_visible_via_membership(guy):
    """Case 9: an Israeli roster story with no explicit league keyword is
    visible via team-membership reach."""
    article = _make_article(
        entities=["Maccabi Kiryat Gat"],
        entity_ids=["team:maccabi_kiryat_gat"],
        event_type="negotiation",
        importance="medium",
        taxonomy_version=1,
    )
    result = score_article(article, guy)
    assert result.decision != "hidden", result.reasoning


def test_correctly_classified_euroleague_article_visible(guy):
    """Case 7: correctly-classified EuroLeague article → visible (feed or
    higher), via explicit competition evidence."""
    article = _make_article(
        entities=["Panathinaikos"],
        entity_ids=[],
        primary_competition="comp:euroleague",
        event_type="match_result",
        importance="medium",
        taxonomy_version=1,
    )
    result = score_article(article, guy)
    assert result.decision != "hidden", result.reasoning
    assert result.matched_topic == "euroleague"


# ── Team-anchored vs competition-anchored reach ─────────────────────────────

def test_maccabi_domestic_game_not_visible_to_euroleague_only_follower(euroleague_only_profile):
    """A competition-anchored event (match_result) with explicit IBL evidence
    must NOT reach a EuroLeague-only follower merely because the team also
    plays EuroLeague — competition-anchored events require explicit
    competition evidence for the FOLLOWED competition, not membership."""
    article = _make_article(
        entities=["Maccabi Tel Aviv Basketball"],
        entity_ids=["team:maccabi_tlv_bb"],
        primary_competition="comp:ibl",
        event_type="match_result",
        importance="high",
        taxonomy_version=1,
    )
    result = score_article(article, euroleague_only_profile)
    assert result.decision == "hidden", result.reasoning


def test_maccabi_euroleague_signing_reaches_euroleague_only_follower_via_membership(euroleague_only_profile):
    """A team-anchored event (signing) with NO explicit competition text still
    reaches a EuroLeague-only follower via team-membership reach — Maccabi
    Tel Aviv Basketball is a EuroLeague member."""
    article = _make_article(
        entities=["Maccabi Tel Aviv Basketball"],
        entity_ids=["team:maccabi_tlv_bb"],
        event_type="signing",
        importance="medium",
        taxonomy_version=1,
    )
    result = score_article(article, euroleague_only_profile)
    assert result.decision != "hidden", result.reasoning
    assert any("via_team_membership: comp:euroleague" in line for line in result.reasoning)


def test_interview_does_not_reach_euroleague_only_follower_via_membership(euroleague_only_profile):
    """Required refinement: `interview` is excluded from TEAM_ANCHORED_EVENTS.
    A competition-unspecified Maccabi interview must not become visible to a
    EuroLeague-only user solely via team membership."""
    article = _make_article(
        entities=["Maccabi Tel Aviv Basketball"],
        entity_ids=["team:maccabi_tlv_bb"],
        event_type="interview",
        importance="medium",
        taxonomy_version=1,
    )
    result = score_article(article, euroleague_only_profile)
    assert result.decision == "hidden", result.reasoning


def test_unlisted_event_type_gets_no_membership_reach(guy):
    """A conservative, fail-closed check: an unlisted event type (not in
    either allowlist) must not gain membership reach even for an entity that
    a *listed* event type would successfully reach through."""
    negotiation_article = _make_article(
        entities=["Maccabi Ramat Gan"],
        entity_ids=["team:maccabi_ramat_gan"],
        event_type="negotiation",  # listed (team-anchored)
        importance="medium",
        taxonomy_version=1,
    )
    rumor_article = _make_article(
        entities=["Maccabi Ramat Gan"],
        entity_ids=["team:maccabi_ramat_gan"],
        event_type="rumor",  # unlisted on purpose
        importance="medium",
        taxonomy_version=1,
    )
    assert score_article(negotiation_article, guy).decision != "hidden"
    assert score_article(rumor_article, guy).decision == "hidden"


def test_release_event_reaches_ibl_follower_via_membership(guy):
    """`release` is a team-anchored event; a release article with no explicit
    competition text still reaches the IBL follow via membership."""
    article = _make_article(
        entities=["Hapoel Holon"],
        entity_ids=["team:hapoel_holon"],
        event_type="release",
        importance="medium",
        taxonomy_version=1,
    )
    result = score_article(article, guy)
    assert result.decision != "hidden", result.reasoning


# ── entity_ids-first identity contract ───────────────────────────────────────

def test_post_facts_membership_reach_ignores_stale_legacy_entities_field(guy):
    """A post-ArticleFacts row (taxonomy_version set) must resolve membership
    reach ONLY through entity_ids, never falling back to a legacy `entities`
    string even if one happens to be present and resolvable — the two are not
    merged, entity_ids is authoritative once facts have run."""
    article = _make_article(
        entities=["Maccabi Ramat Gan"],  # present, resolvable — must be ignored
        entity_ids=[],  # nothing canonical resolved
        event_type="negotiation",
        importance="medium",
        taxonomy_version=1,
    )
    result = score_article(article, guy)
    assert result.decision == "hidden", (
        "post-facts row with empty entity_ids must not fall back to the legacy "
        f"entities field for membership reach. Reasoning: {result.reasoning}"
    )


def test_post_facts_entity_backing_survives_empty_legacy_entities_field(guy):
    """A post-facts article with a valid entity_ids hit must still receive
    entity backing (unlocks entity_event_rules / skips the membership feed
    ceiling) even when its legacy `entities` display list is empty/changed —
    canonical identity, not the display string, is load-bearing."""
    article = _make_article(
        entities=[],  # empty/changed — must not matter
        entity_ids=["player:deni_avdija"],
        event_type="major_trade",  # team-anchored; entityEventRules["Deni Avdija"] -> push
        importance="medium",
        taxonomy_version=1,
    )
    result = score_article(article, guy)
    assert result.decision == "push", (
        f"canonical entity_ids should back Deni Avdija's entity_event_rules "
        f"(major_trade -> push) despite the empty legacy entities list. Reasoning: {result.reasoning}"
    )


def test_legacy_pre_taxonomy_row_still_works_through_entities_fallback(guy):
    """A legacy row (taxonomy_version is None, entity_ids never populated)
    still resolves membership reach through the `entities` display-string
    fallback — this is the 100%-backward-compatible path."""
    article = _make_article(
        entities=["Maccabi Ramat Gan"],
        entity_ids=[],
        event_type="negotiation",
        importance="medium",
        taxonomy_version=None,
    )
    result = score_article(article, guy)
    assert result.decision != "hidden", result.reasoning


# ── Membership-only feed ceiling / push discipline ──────────────────────────

def test_membership_only_match_caps_at_feed_without_entity_backing(guy):
    """A membership-only match with no independent entity backing cannot climb
    above feed even when importance would otherwise boost it — push must stay
    explicit-rule-only, and high_feed requires stronger evidence."""
    article = _make_article(
        entities=["Ironi Ramat Gan"],
        entity_ids=["team:ironi_ramat_gan"],
        event_type="major_signing",  # israeli_basketball event_rules: major_signing -> high_feed
        importance="very_high",  # would additionally importance-boost if uncapped
        taxonomy_version=1,
    )
    result = score_article(article, guy)
    assert result.decision == "feed", (
        f"membership-only reach (no entity backing) must cap at feed, "
        f"never high_feed/push, even under importance boost. Reasoning: {result.reasoning}"
    )


def test_deni_trade_is_still_push_for_guy_with_membership_match(guy):
    """Regression guard: Deni Avdija matches the nba topic via team-membership
    reach (no explicit 'NBA' keyword), but the entity backing (Deni Avdija is
    a topic/profile-followed entity) exempts it from the feed ceiling — push
    must still fire via entity_event_rules."""
    article = _make_article(
        entities=["Deni Avdija"],
        entity_ids=["player:deni_avdija"],
        event_type="major_trade",
        importance="high",
        taxonomy_version=1,
    )
    result = score_article(article, guy)
    assert result.decision == "push", result.reasoning


# ── No low_feed without a legitimate matched scope ──────────────────────────

def test_generic_international_noise_is_hidden_not_low_feed(guy):
    article = _make_article(
        sport="football",
        entities=[],
        event_type="regular_season_result",
        importance="very_high",
        league="Portuguese Liga",
        taxonomy_version=None,
    )
    result = score_article(article, guy)
    assert result.decision == "hidden", result.reasoning


def test_major_only_mode_no_longer_leaks_to_low_feed():
    """The major_importance_fallback leak is removed: a topic in major_only
    mode with no matching event rule is hidden regardless of importance, not
    low_feed."""
    from app.services.relevance_engine import _score_against_topic

    topic = TopicPreference(
        topic_id="test_major_only",
        label="Test",
        sport="football",
        scope="sport",
        priority=20,
        mode="major_only",
        leagues=[],
        entities=[],
        event_rules={},
    )
    profile = UserProfile(user_id="test", display_name="Test", profile_type="test", topics=[topic])
    article = _make_article(sport="football", event_type="regular_season_result", importance="very_high")
    decision, rule, _reasoning = _score_against_topic(article, topic, profile, None)
    assert decision == "hidden"
    assert rule == "major_only_no_match"


# ── sport=unknown handling (documented, conservative) ───────────────────────

def test_sport_unknown_article_visible_via_surviving_explicit_competition_evidence(euroleague_only_profile):
    """Per ArticleFacts (#28), primary_competition/article_competitions survive
    sport abstention. A sport=unknown article can still match a league topic
    via explicit competition evidence."""
    article = _make_article(
        sport="unknown",
        entities=[],
        entity_ids=[],
        primary_competition="comp:euroleague",
        event_type="match_result",
        importance="medium",
        taxonomy_version=1,
    )
    result = score_article(article, euroleague_only_profile)
    assert result.decision != "hidden", result.reasoning


def test_sport_unknown_article_cannot_reach_via_membership(euroleague_only_profile):
    """Per ArticleFacts (#28), entities/entity_ids are always cleared on
    abstention, so a sport=unknown article with no explicit competition
    evidence has nothing to resolve membership reach from — conservative,
    documented behavior, not a special case in the matching code."""
    article = _make_article(
        sport="unknown",
        entities=[],
        entity_ids=[],
        event_type="signing",
        importance="medium",
        taxonomy_version=1,
    )
    result = score_article(article, euroleague_only_profile)
    assert result.decision == "hidden", result.reasoning


# ── Explicit mute still overrides everything ────────────────────────────────

def test_explicit_mute_overrides_membership_reach(guy):
    muted_guy = guy.model_copy(update={"muted_topics": ["basketball"]})
    article = _make_article(
        entities=["Maccabi Ramat Gan"],
        entity_ids=["team:maccabi_ramat_gan"],
        event_type="negotiation",
        importance="very_high",
        taxonomy_version=1,
    )
    result = score_article(article, muted_guy)
    assert result.decision == "hidden"
    assert result.matched_event_rule == "muted_topic"
