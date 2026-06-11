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

def test_euroleague_major_transfer_is_visible_for_guy(guy):
    # The Maccabi topic matches ALL basketball articles by sport (OR-logic matching).
    # major_transfer aliases to major_signing, which is "push" in the Maccabi topic.
    # This means non-Maccabi EuroLeague transfers resolve to "push" — a known engine quirk
    # that also exists in the frontend. The test verifies visibility, not the exact level.
    result = score_article(article("article_014"), guy)
    assert result.decision != "hidden"
    assert result.decision == "push"  # Maccabi topic catches it via sport + signing alias


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
