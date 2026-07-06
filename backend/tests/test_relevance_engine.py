"""
Unit tests for the backend relevance engine.
All tests mirror the product semantics documented in CLAUDE.md and IMPLEMENTATION_AUDIT.md.
"""
import pytest
from app.seed.seed_articles import SEED_ARTICLES
from app.seed.seed_profiles import SEED_PROFILES
from app.services.relevance_engine import score_article

# ── Profile fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def guy():
    return next(p for p in SEED_PROFILES if p.user_id == "guy")


@pytest.fixture(scope="module")
def deni_fan():
    return next(p for p in SEED_PROFILES if p.user_id == "casual_deni_fan")


# ── Article fixtures ───────────────────────────────────────────────────────────

def article(article_id: str):
    a = next((a for a in SEED_ARTICLES if a.id == article_id), None)
    assert a is not None, f"Seed article {article_id!r} not found"
    return a


# ── Maccabi basketball ────────────────────────────────────────────────────────

def test_maccabi_negotiation_is_push_for_guy(guy):
    result = score_article(article("article_001"), guy)
    assert result.decision == "push", f"Expected push, got {result.decision}. Reasoning: {result.reasoning}"


def test_maccabi_signing_is_push_for_guy(guy):
    result = score_article(article("article_002"), guy)
    assert result.decision == "push"


def test_maccabi_injury_is_push_for_guy(guy):
    result = score_article(article("article_003"), guy)
    assert result.decision == "push"


def test_maccabi_candidate_is_high_feed_for_guy(guy):
    result = score_article(article("article_004"), guy)
    assert result.decision == "high_feed"


def test_maccabi_friendly_is_not_push_for_guy(guy):
    result = score_article(article("article_005"), guy)
    assert result.decision in ("low_feed", "feed")


# ── NBA profile divergence ────────────────────────────────────────────────────

def test_hornets_wizards_visible_for_guy(guy):
    result = score_article(article("article_006"), guy)
    assert result.decision != "hidden", f"Expected visible for Guy, got hidden. Reasoning: {result.reasoning}"


def test_hornets_wizards_hidden_for_deni_fan(deni_fan):
    result = score_article(article("article_006"), deni_fan)
    assert result.decision == "hidden", f"Expected hidden for Deni Fan, got {result.decision}. Reasoning: {result.reasoning}"


def test_deni_trade_is_push_for_guy(guy):
    result = score_article(article("article_007"), guy)
    assert result.decision == "push"


def test_deni_trade_is_push_for_deni_fan(deni_fan):
    result = score_article(article("article_007"), deni_fan)
    assert result.decision == "push"


def test_deni_injury_is_push_for_guy(guy):
    result = score_article(article("article_008"), guy)
    assert result.decision == "push"


def test_deni_injury_is_push_for_deni_fan(deni_fan):
    result = score_article(article("article_008"), deni_fan)
    assert result.decision == "push"


# ── Tennis titles_only ────────────────────────────────────────────────────────

def test_grand_slam_winner_is_high_feed_for_guy(guy):
    result = score_article(article("article_011"), guy)
    assert result.decision == "high_feed"


def test_early_round_tennis_is_hidden_for_guy(guy):
    result = score_article(article("article_012"), guy)
    assert result.decision == "hidden"


# ── Football noise ────────────────────────────────────────────────────────────

def test_football_regular_season_is_hidden_for_guy(guy):
    result = score_article(article("article_013"), guy)
    assert result.decision == "hidden"


# ── Push discipline: importance boost NEVER reaches push ─────────────────────

def test_nba_major_trade_no_deni_very_high_importance_is_not_push(guy):
    # article_010: Lakers/Suns major_trade, very_high importance — no Deni entity
    # NBA topic: major_trade = "high_feed", importance boost capped at high_feed
    result = score_article(article("article_010"), guy)
    assert result.decision != "push", (
        f"Importance boost must never escalate to push. Got {result.decision}. "
        f"Reasoning: {result.reasoning}"
    )
    assert result.decision == "high_feed"


# ── European domestic basketball ──────────────────────────────────────────────

def test_acb_playoff_is_visible_for_guy(guy):
    result = score_article(article("article_015"), guy)
    assert result.decision != "hidden"


def test_greek_regular_season_is_hidden_for_guy(guy):
    result = score_article(article("article_016"), guy)
    assert result.decision == "hidden"


# ── EuroLeague ────────────────────────────────────────────────────────────────

def test_euroleague_major_transfer_is_high_feed_for_guy(guy):
    # article_014: Real Madrid EuroLeague major_transfer — NO Maccabi entity.
    # With scope guards, the Maccabi topic (scope: entity) does NOT match because
    # article.entities = ["Real Madrid Basketball"], not a Maccabi entity.
    # The EuroLeague topic (scope: league) DOES match via league "EuroLeague".
    # EuroLeague eventRules: major_transfer → high_feed (not push).
    result = score_article(article("article_014"), guy)
    assert result.decision != "hidden", "EuroLeague transfer must be visible for Guy"
    assert result.decision == "high_feed", (
        f"Non-Maccabi EuroLeague transfer must be high_feed via EuroLeague topic, "
        f"not push via Maccabi topic. Got {result.decision}. "
        f"Reasoning: {result.reasoning}"
    )
    assert result.matched_topic == "euroleague", (
        f"Must be matched by EuroLeague topic, not maccabi_tel_aviv_basketball. "
        f"Got matched_topic={result.matched_topic}"
    )


def test_euroleague_content_hidden_for_deni_fan(deni_fan):
    result = score_article(article("article_014"), deni_fan)
    assert result.decision == "hidden"


# ── Muting ────────────────────────────────────────────────────────────────────

def test_muted_source_returns_hidden(guy):
    from app.seed.seed_articles import SEED_ARTICLES
    from copy import deepcopy
    import app.models.profile as pm

    muted_profile = guy.model_copy(update={"muted_sources": ["sport5"]})
    result = score_article(article("article_001"), muted_profile)
    assert result.decision == "hidden"
    assert result.matched_event_rule == "muted_source"


def test_muted_topic_returns_hidden(guy):
    muted_profile = guy.model_copy(update={"muted_topics": ["basketball"]})
    result = score_article(article("article_001"), muted_profile)
    assert result.decision == "hidden"
    assert result.matched_event_rule == "muted_topic"


def test_disabled_source_returns_hidden(guy):
    result = score_article(article("article_001"), guy, disabled_source_ids={"sport5"})
    assert result.decision == "hidden"
    assert result.matched_event_rule == "disabled_source"


# ── Topic scope guards ─────────────────────────────────────────────────────────

from app.models.article import Article
from app.services.relevance_engine import _does_topic_match_article


def _make_article(**kwargs) -> Article:
    from datetime import datetime, timezone
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
    )
    defaults.update(kwargs)
    return Article(**defaults)


def test_scope_guard_profiles_have_correct_scopes(guy):
    topics_by_id = {t.topic_id: t for t in guy.topics}
    assert topics_by_id["maccabi_tel_aviv_basketball"].scope == "entity"
    assert topics_by_id["nba"].scope == "league"
    assert topics_by_id["euroleague"].scope == "league"
    assert topics_by_id["israeli_basketball"].scope == "league"
    assert topics_by_id["major_european_domestic_basketball"].scope == "league_group"
    assert topics_by_id["football"].scope == "sport"
    assert topics_by_id["tennis"].scope == "sport"


def test_entity_scope_maccabi_matches_maccabi_entity(guy):
    maccabi_topic = next(t for t in guy.topics if t.topic_id == "maccabi_tel_aviv_basketball")
    art = _make_article(
        sport="basketball", league="EuroLeague",
        entities=["Maccabi Tel Aviv Basketball"], event_type="negotiation"
    )
    matched, reason, _ = _does_topic_match_article(art, maccabi_topic)
    assert matched is True
    assert "entity" in reason.lower() or "ישות" in reason


def test_entity_scope_maccabi_does_not_match_real_madrid(guy):
    maccabi_topic = next(t for t in guy.topics if t.topic_id == "maccabi_tel_aviv_basketball")
    art = _make_article(
        sport="basketball", league="EuroLeague",
        entities=["Real Madrid Basketball"], event_type="major_transfer"
    )
    matched, _, _ = _does_topic_match_article(art, maccabi_topic)
    assert matched is False, "Entity scope must not match non-Maccabi entity"


def test_entity_scope_maccabi_does_not_match_via_sport_alone(guy):
    maccabi_topic = next(t for t in guy.topics if t.topic_id == "maccabi_tel_aviv_basketball")
    art = _make_article(
        sport="basketball", league="Spanish ACB",
        entities=["FC Barcelona Basketball"], event_type="playoff_result"
    )
    matched, _, _ = _does_topic_match_article(art, maccabi_topic)
    assert matched is False, "Entity scope must not match via sport alone"


def test_league_scope_nba_matches_nba_league(guy):
    nba_topic = next(t for t in guy.topics if t.topic_id == "nba")
    art = _make_article(
        sport="basketball", league="NBA",
        entities=["Charlotte Hornets", "Washington Wizards"], event_type="regular_season_result"
    )
    matched, reason, _ = _does_topic_match_article(art, nba_topic)
    assert matched is True
    assert "NBA" in reason


def test_league_scope_nba_does_not_match_euroleague(guy):
    nba_topic = next(t for t in guy.topics if t.topic_id == "nba")
    art = _make_article(
        sport="basketball", league="EuroLeague",
        entities=["Fenerbahce"], event_type="match_result"
    )
    matched, _, _ = _does_topic_match_article(art, nba_topic)
    assert matched is False


def test_league_scope_euroleague_matches_non_maccabi_euroleague(guy):
    el_topic = next(t for t in guy.topics if t.topic_id == "euroleague")
    art = _make_article(
        sport="basketball", league="EuroLeague",
        entities=["Real Madrid Basketball"], event_type="major_transfer"
    )
    matched, reason, _ = _does_topic_match_article(art, el_topic)
    assert matched is True
    assert "EuroLeague" in reason


def test_league_group_scope_matches_spanish_acb(guy):
    eu_topic = next(t for t in guy.topics if t.topic_id == "major_european_domestic_basketball")
    art = _make_article(
        sport="basketball", league="Spanish ACB",
        entities=["Real Madrid Basketball"], event_type="playoff_result", importance="high"
    )
    matched, _, _ = _does_topic_match_article(art, eu_topic)
    assert matched is True


def test_league_group_scope_matches_turkish_bsl(guy):
    eu_topic = next(t for t in guy.topics if t.topic_id == "major_european_domestic_basketball")
    art = _make_article(
        sport="basketball", league="Turkish BSL",
        entities=["Fenerbahce"], event_type="match_result"
    )
    matched, _, _ = _does_topic_match_article(art, eu_topic)
    assert matched is True


def test_league_group_scope_does_not_match_nba(guy):
    eu_topic = next(t for t in guy.topics if t.topic_id == "major_european_domestic_basketball")
    art = _make_article(
        sport="basketball", league="NBA",
        entities=["Charlotte Hornets"], event_type="regular_season_result"
    )
    matched, _, _ = _does_topic_match_article(art, eu_topic)
    assert matched is False


def test_sport_scope_football_matches_any_football(guy):
    football_topic = next(t for t in guy.topics if t.topic_id == "football")
    art = _make_article(
        sport="football", league="Israeli Premier League",
        entities=[], event_type="regular_season_result"
    )
    matched, _, _ = _does_topic_match_article(art, football_topic)
    assert matched is True


def test_sport_scope_football_does_not_match_basketball(guy):
    football_topic = next(t for t in guy.topics if t.topic_id == "football")
    art = _make_article(
        sport="basketball", league="NBA",
        entities=[], event_type="regular_season_result"
    )
    matched, _, _ = _does_topic_match_article(art, football_topic)
    assert matched is False


def test_sport_scope_tennis_matches_regardless_of_league(guy):
    tennis_topic = next(t for t in guy.topics if t.topic_id == "tennis")
    art = _make_article(
        sport="tennis", league="Wimbledon",
        entities=["Carlos Alcaraz"], event_type="early_round_result"
    )
    matched, _, _ = _does_topic_match_article(art, tennis_topic)
    assert matched is True


def test_non_maccabi_euroleague_transfer_is_high_feed_end_to_end(guy):
    # Reproduces the article_014 scenario but via _does_topic_match_article directly
    maccabi_topic = next(t for t in guy.topics if t.topic_id == "maccabi_tel_aviv_basketball")
    el_topic = next(t for t in guy.topics if t.topic_id == "euroleague")
    art = _make_article(
        sport="basketball", league="EuroLeague",
        entities=["Real Madrid Basketball"], event_type="major_transfer", importance="high"
    )
    maccabi_matched, _, _ = _does_topic_match_article(art, maccabi_topic)
    el_matched, _, _ = _does_topic_match_article(art, el_topic)
    assert maccabi_matched is False, "Maccabi entity scope must not match Real Madrid article"
    assert el_matched is True, "EuroLeague league scope must match EuroLeague article"
    # End-to-end: score the article and expect high_feed
    result = score_article(art, guy)
    assert result.decision == "high_feed", (
        f"Non-Maccabi EuroLeague transfer must be high_feed, got {result.decision}. "
        f"Reasoning: {result.reasoning}"
    )


def test_maccabi_article_still_push_after_scope_guard(guy):
    # Maccabi entity IS present → entity scope matches → push via negotiation rule
    result = score_article(article("article_001"), guy)
    assert result.decision == "push"
    assert result.matched_topic == "maccabi_tel_aviv_basketball"


def test_hornets_wizards_visible_for_guy_via_league_scope(guy):
    # NBA article matches NBA topic via league scope (not sport scope)
    result = score_article(article("article_006"), guy)
    assert result.decision != "hidden"
    assert result.matched_topic == "nba"


def test_hornets_wizards_hidden_for_deni_fan_via_entity_guard(deni_fan):
    # NBA league scope matches, but followed_entities_only mode requires Deni entity
    result = score_article(article("article_006"), deni_fan)
    assert result.decision == "hidden"


def test_acb_playoff_visible_via_league_group_scope(guy):
    # article_015: Spanish ACB playoff — league_group scope matches
    result = score_article(article("article_015"), guy)
    assert result.decision != "hidden"
    assert result.matched_topic == "major_european_domestic_basketball"


def test_greek_regular_season_hidden_via_high_importance_only(guy):
    # article_016: Greek League schedule — league_group matches but high_importance_only
    # filters very_low importance → hidden
    result = score_article(article("article_016"), guy)
    assert result.decision == "hidden"


def test_push_not_via_maccabi_topic_for_non_maccabi_article(guy):
    # Explicit check: a non-Maccabi basketball article must never resolve push via Maccabi topic
    non_maccabi_article = _make_article(
        sport="basketball", league="EuroLeague",
        entities=["Fenerbahce"], event_type="signing", importance="high"
    )
    result = score_article(non_maccabi_article, guy)
    if result.decision == "push":
        assert result.matched_topic != "maccabi_tel_aviv_basketball", (
            "Non-Maccabi article must not reach push via maccabi_tel_aviv_basketball topic"
        )
    # EuroLeague signing → high_feed (from EuroLeague topic's eventRules: signing = high_feed)
    assert result.decision == "high_feed"


# ── Sport compatibility guard (entity scope defense-in-depth) ─────────────────

def test_football_article_with_basketball_entity_does_not_match_maccabi_topic(guy):
    """A football article must never be promoted via maccabi_tel_aviv_basketball topic,
    even if 'Maccabi Tel Aviv Basketball' appears in entities due to a classification error."""
    football_article = _make_article(
        sport="football",
        league="Israeli Premier League",
        entities=["Maccabi Tel Aviv Basketball"],  # stale entity — the bug scenario
        event_type="match_result",
        importance="medium",
    )
    result = score_article(football_article, guy)
    assert result.matched_topic != "maccabi_tel_aviv_basketball", (
        "Football article must not match maccabi_tel_aviv_basketball entity topic"
    )
    # Football article should be hidden or low_feed for Guy (football major_only mode)
    assert result.decision in ("hidden", "low_feed")


def test_football_article_with_hapoel_tlv_entity_does_not_match_via_entity_scope(guy):
    """Hapoel TLV Basketball entity in a football article must not trigger entity scope match."""
    football_article = _make_article(
        sport="football",
        league="Israeli Premier League",
        entities=["Hapoel Tel Aviv Basketball"],
        event_type="match_result",
        importance="medium",
    )
    result = score_article(football_article, guy)
    # No basketball entity topic should match for a football article
    assert result.matched_topic not in (
        "maccabi_tel_aviv_basketball",
        "hapoel_tel_aviv_basketball",
    )


def test_basketball_article_with_maccabi_entity_still_matches(guy):
    """sport=basketball articles with Maccabi entity still match the entity topic — no regression."""
    basketball_article = _make_article(
        sport="basketball",
        league="EuroLeague",
        entities=["Maccabi Tel Aviv Basketball"],
        event_type="signing",
        importance="high",
    )
    result = score_article(basketball_article, guy)
    assert result.matched_topic == "maccabi_tel_aviv_basketball"
    assert result.decision in ("high_feed", "push")


def test_unknown_sport_article_with_basketball_entity_still_matches(guy):
    """An article with sport=unknown but a Maccabi entity should still match the entity topic.
    'unknown' passes through the sport guard — the article may simply be unclassified."""
    unknown_sport_article = _make_article(
        sport="unknown",
        league=None,
        entities=["Maccabi Tel Aviv Basketball"],
        event_type="news",
        importance="medium",
    )
    result = score_article(unknown_sport_article, guy)
    assert result.matched_topic == "maccabi_tel_aviv_basketball"
