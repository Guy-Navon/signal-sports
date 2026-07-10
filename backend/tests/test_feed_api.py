# PR 6 (#54): this file exercises the legacy {user_id}/ops surface, which is
# admin-gated fail-closed — it runs under the explicit admin_client identity.
"""
Integration tests for the feed, profile, article, and feedback API endpoints.
Uses FastAPI TestClient with session-scoped fixture from conftest.py.
"""
import pytest


# ── Health ────────────────────────────────────────────────────────────────────

def test_health(admin_client):
    r = admin_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Profiles ──────────────────────────────────────────────────────────────────

def test_profile_list_returns_both_profiles(admin_client):
    r = admin_client.get("/api/profiles")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    user_ids = {p["user_id"] for p in data}
    assert "guy" in user_ids
    assert "casual_deni_fan" in user_ids


def test_get_profile_guy(admin_client):
    r = admin_client.get("/api/profiles/guy")
    assert r.status_code == 200
    data = r.json()
    assert data["user_id"] == "guy"
    assert len(data["topics"]) > 0


def test_get_profile_not_found(admin_client):
    r = admin_client.get("/api/profiles/nonexistent_user")
    assert r.status_code == 404


# ── Articles ──────────────────────────────────────────────────────────────────

def test_article_list_not_empty(rss_seeded, admin_client):
    r = admin_client.get("/api/articles")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_article_by_id(admin_client):
    r = admin_client.get("/api/articles/article_007")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "article_007"
    assert "Deni Avdija" in data["entities"]


def test_get_article_not_found(admin_client):
    r = admin_client.get("/api/articles/nonexistent_article")
    assert r.status_code == 404


# ── Feed for Guy ──────────────────────────────────────────────────────────────

def test_feed_for_guy_is_not_empty(rss_seeded, admin_client):
    r = admin_client.get("/api/feed/guy")
    assert r.status_code == 200
    data = r.json()
    assert len(data) > 0, "Guy's feed must not be empty"


def test_feed_for_guy_contains_no_hidden(admin_client):
    r = admin_client.get("/api/feed/guy")
    assert r.status_code == 200
    for item in r.json():
        assert item["decision"] != "hidden", f"Hidden article leaked into feed: {item['article']['id']}"


def test_feed_not_found_for_unknown_user(admin_client):
    r = admin_client.get("/api/feed/ghost_user")
    assert r.status_code == 404


# ── Debug feed ────────────────────────────────────────────────────────────────

def test_debug_feed_includes_hidden_articles(rss_seeded, admin_client):
    r = admin_client.get("/api/debug/feed/guy")
    assert r.status_code == 200
    data = r.json()
    decisions = {item["decision"] for item in data}
    assert "hidden" in decisions, "Debug feed must include hidden articles"


def test_debug_feed_includes_reasoning(admin_client):
    r = admin_client.get("/api/debug/feed/guy")
    assert r.status_code == 200
    for item in r.json():
        assert len(item["reasoning"]) > 0, f"Missing reasoning on {item['article']['id']}"


def test_debug_feed_has_more_items_than_normal_feed(admin_client):
    feed = admin_client.get("/api/feed/guy").json()
    debug = admin_client.get("/api/debug/feed/guy").json()
    assert len(debug) >= len(feed)


# ── Profile divergence ────────────────────────────────────────────────────────

def test_hornets_wizards_visible_for_guy_hidden_for_deni_fan(rss_seeded, admin_client):
    guy_debug = admin_client.get("/api/debug/feed/guy").json()
    deni_debug = admin_client.get("/api/debug/feed/casual_deni_fan").json()

    guy_hornets = next((i for i in guy_debug if i["article"]["id"] == "rss_article_006"), None)
    deni_hornets = next((i for i in deni_debug if i["article"]["id"] == "rss_article_006"), None)

    assert guy_hornets is not None
    assert deni_hornets is not None
    assert guy_hornets["decision"] != "hidden", f"Guy should see Hornets/Wizards, got hidden"
    assert deni_hornets["decision"] == "hidden", f"Deni Fan should NOT see Hornets/Wizards, got {deni_hornets['decision']}"


def test_deni_trade_is_push_for_both(rss_seeded, admin_client):
    guy_debug = admin_client.get("/api/debug/feed/guy").json()
    deni_debug = admin_client.get("/api/debug/feed/casual_deni_fan").json()

    guy_trade = next((i for i in guy_debug if i["article"]["id"] == "rss_article_007"), None)
    deni_trade = next((i for i in deni_debug if i["article"]["id"] == "rss_article_007"), None)

    assert guy_trade is not None and guy_trade["decision"] == "push", \
        f"Guy: expected push for Deni trade, got {guy_trade['decision'] if guy_trade else 'not found'}"
    assert deni_trade is not None and deni_trade["decision"] == "push", \
        f"Deni Fan: expected push for Deni trade, got {deni_trade['decision'] if deni_trade else 'not found'}"


def test_maccabi_negotiation_is_push_for_guy(rss_seeded, admin_client):
    r = admin_client.get("/api/debug/feed/guy")
    data = r.json()
    item = next((i for i in data if i["article"]["id"] == "rss_article_001"), None)
    assert item is not None
    assert item["decision"] == "push"


def test_early_round_tennis_is_hidden_for_guy(rss_seeded, admin_client):
    r = admin_client.get("/api/debug/feed/guy")
    data = r.json()
    item = next((i for i in data if i["article"]["id"] == "rss_article_012"), None)
    assert item is not None
    assert item["decision"] == "hidden"


def test_push_not_from_importance_boost_alone(rss_seeded, admin_client):
    # rss_article_010: NBA major_trade, very_high importance, no Deni entity
    # Expected: high_feed (not push) because importance boost is capped at high_feed
    r = admin_client.get("/api/debug/feed/guy")
    data = r.json()
    item = next((i for i in data if i["article"]["id"] == "rss_article_010"), None)
    assert item is not None, "rss_article_010 not found in debug feed"
    assert item["decision"] != "push", (
        f"Importance boost must never reach push. Got {item['decision']}. "
        f"Reasoning: {item['reasoning']}"
    )
    assert item["decision"] == "high_feed"


def test_non_maccabi_euroleague_transfer_is_high_feed_not_push(rss_seeded, admin_client):
    # rss_article_014: Real Madrid EuroLeague major_transfer, NO Maccabi entity.
    # Maccabi topic (scope: entity) requires entity match → no match.
    # EuroLeague topic (scope: league) matches → major_transfer → high_feed.
    r = admin_client.get("/api/debug/feed/guy")
    data = r.json()
    item = next((i for i in data if i["article"]["id"] == "rss_article_014"), None)
    assert item is not None, "rss_article_014 not found in debug feed"
    assert item["decision"] != "push", (
        f"Non-Maccabi EuroLeague major transfer must not be push via Maccabi topic. "
        f"Got {item['decision']}. Reasoning: {item['reasoning']}"
    )
    assert item["decision"] == "high_feed", (
        f"Non-Maccabi EuroLeague major transfer must be high_feed via EuroLeague topic. "
        f"Got {item['decision']}. Reasoning: {item['reasoning']}"
    )
    # Engine flip (#32): matched_topic is now the v2 canonical scope id
    # (comp:euroleague), not the legacy topic_id ("euroleague").
    assert item["matched_topic"] == "comp:euroleague", (
        f"Must be matched by the EuroLeague scope. Got matched_topic={item['matched_topic']}"
    )


def test_maccabi_negotiation_still_push_after_scope_guard(rss_seeded, admin_client):
    # rss_article_001: Maccabi entity present → entity scope matches → push
    r = admin_client.get("/api/debug/feed/guy")
    data = r.json()
    item = next((i for i in data if i["article"]["id"] == "rss_article_001"), None)
    assert item is not None
    assert item["decision"] == "push"
    # Engine flip (#32): v2 canonical scope id instead of the legacy topic_id.
    assert item["matched_topic"] == "team:maccabi_tlv_bb"


# ── Feedback ──────────────────────────────────────────────────────────────────

def test_feedback_accepted(admin_client):
    r = admin_client.post("/api/feedback", json={
        "user_id": "guy",
        "article_id": "article_001",
        "action": "more_like_this",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["user_id"] == "guy"
    assert data["article_id"] == "article_001"
    assert data["action"] == "more_like_this"
    assert "id" in data


def test_feedback_invalid_action(admin_client):
    r = admin_client.post("/api/feedback", json={
        "user_id": "guy",
        "article_id": "article_001",
        "action": "invalid_action_xyz",
    })
    assert r.status_code == 422


def test_feedback_unknown_user(admin_client):
    r = admin_client.post("/api/feedback", json={
        "user_id": "ghost",
        "article_id": "article_001",
        "action": "more_like_this",
    })
    assert r.status_code == 404


# ── Calibration headlines ─────────────────────────────────────────────────────

def test_calibration_headlines_not_empty(admin_client):
    r = admin_client.get("/api/calibration/headlines")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_calibration_headlines_have_required_fields(admin_client):
    r = admin_client.get("/api/calibration/headlines")
    for h in r.json():
        assert "id" in h
        assert "title" in h
        assert "sport" in h
        assert "event_type" in h
        assert "importance" in h
