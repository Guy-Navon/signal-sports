"""
Issue #85 — the full milestone acceptance journey (Explicit Interests &
Onboarding v2), end to end over the real API surface:

signup → explicit interest selection (archetype A) → global event prefs →
interest-aware calibration → materially personalized feed → feedback →
learned adjustment visible with provenance → logout/login state intact →
account deletion clean.

Runs on the hermetic test DB (seeded articles), real auth enforcement.
"""
import pytest

from tests.conftest import _TEST_IDENTITY_PASSWORD, _dispose_identity, _identity_client


ARCHETYPE_A = {
    "follows": [
        {"scope": "sport", "target_id": "basketball", "starred": False},
        {"scope": "competition", "target_id": "comp:euroleague", "starred": False},
        {"scope": "team", "target_id": "team:maccabi_tlv_bb", "starred": True},
    ],
    "event_preferences": {"transfers_rumors": "more", "schedules_previews": "less"},
}


@pytest.fixture()
def journey_client(_application, rss_seeded):
    c = _identity_client(_application, "user")
    yield c
    _dispose_identity(c)


class TestFullAcceptanceJourney:
    def test_signup_to_deletion(self, _application, rss_seeded):
        c = _identity_client(_application, "user")
        deleted = False
        try:
            # ── 1. Fresh account: interests stage pending, feed empty-state ──
            session = c.get("/api/auth/session").json()
            assert session["onboarding"]["completed"] is False
            assert session["onboarding"]["interests"] == {
                "completed": False, "selected": 0,
            }

            # ── 2. Explicit interest selection (archetype A) ─────────────────
            put = c.put("/api/me/interests", json=ARCHETYPE_A)
            assert put.status_code == 200
            assert put.json()["selected"] == 3

            # ── 3. Interest-aware calibration: scoped subset, rate, apply ────
            items = c.get("/api/me/calibration/items").json()["items"]
            assert 10 <= len(items) <= 14
            ids = {i["id"] for i in items}
            assert "cal2_el_maccabi_game" in ids  # starred-entity pair served
            ratings = {}
            for item in items:
                if item["competition_id"] == "comp:euroleague" and not item["entity_ids"]:
                    ratings[item["id"]] = "interesting"
                elif item["entity_ids"]:
                    ratings[item["id"]] = "push"
            apply_ = c.post("/api/me/calibration/apply", json={"ratings": ratings})
            assert apply_.status_code == 200

            # Onboarding is now complete.
            session = c.get("/api/auth/session").json()
            assert session["onboarding"]["completed"] is True
            assert session["onboarding"]["interests"]["completed"] is True

            # ── 4. Materially personalized feed ──────────────────────────────
            feed = c.get("/api/me/feed").json()
            assert len(feed) > 0, "explicit interests must produce a real feed"
            decisions = {item["article"]["id"]: item["decision"] for item in feed}
            # The Maccabi negotiation story is prominent for a starred-
            # Maccabi user; tennis early-round is absent (feed serves the
            # rss_-prefixed copies of the seed articles).
            assert "rss_article_001" in decisions
            assert decisions["rss_article_001"] in ("high_feed", "push")
            assert "rss_article_012" not in decisions

            # Provenance chain (issue #84): the base scope of a followed
            # article is explicit-labeled in the structured trace.
            maccabi_item = next(i for i in feed
                                if i["article"]["id"] == "rss_article_001")
            base = next(cnt for cnt in maccabi_item["contributions"]
                        if cnt["step"] == "base_scope")
            assert base["source"] == "explicit"

            # ── 5. Feedback → learned adjustment with explanation ────────────
            target = feed[0]["article"]["id"]
            for _ in range(3):
                response = c.post("/api/me/feedback", json={
                    "article_id": target, "action": "more_like_this",
                })
                assert response.status_code == 201
            learning = c.get("/api/me/learning").json()
            assert learning["features"], "3 consistent events must surface a feature"
            assert any(f.get("active") for f in learning["features"])

            # ── 6. Logout / login: everything survives ───────────────────────
            c.post("/api/auth/logout")
            assert c.get("/api/me/interests").status_code == 401
            login = c.post("/api/auth/login", json={
                "email": c.identity_email, "password": _TEST_IDENTITY_PASSWORD,
            })
            assert login.status_code == 200
            doc = c.get("/api/me/interests").json()
            assert doc["selected"] == 3 and doc["completed"] is True
            assert len(c.get("/api/me/feed").json()) == len(feed)

            # ── 7. Account deletion: clean, own rows only ────────────────────
            delete = c.request("DELETE", "/api/me/account", json={
                "current_password": _TEST_IDENTITY_PASSWORD,
            })
            assert delete.status_code == 200
            deleted = True
            relogin = c.post("/api/auth/login", json={
                "email": c.identity_email, "password": _TEST_IDENTITY_PASSWORD,
            })
            assert relogin.status_code in (401, 403)
        finally:
            if not deleted:
                _dispose_identity(c)
            else:
                c.close()

    def test_interests_only_feed_without_calibration(self, journey_client):
        """The superseded #52 decision: skipping calibration no longer means
        an empty feed — explicit follows alone personalize it."""
        c = journey_client
        c.put("/api/me/interests", json=ARCHETYPE_A)
        c.post("/api/me/onboarding/complete")
        feed = c.get("/api/me/feed").json()
        assert len(feed) > 0
        # And the demo profiles are untouched by any of this (isolation).

    def test_skip_everything_keeps_empty_feed(self, journey_client):
        """Skip-all remains valid: no follows, no answers → empty feed (the
        persistent CTA state), never a generic fallback."""
        c = journey_client
        c.post("/api/me/interests/complete")
        c.post("/api/me/onboarding/complete")
        assert c.get("/api/me/feed").json() == []

    def test_demo_profiles_unchanged_by_journeys(self, admin_client):
        """Corpus-fixture guard at the journey level: guy / casual_deni_fan
        keep their seeded shapes regardless of consumer activity."""
        guy = admin_client.get("/api/profiles/guy").json()
        affs = guy["profile_v2"]["scope_affinities"]
        assert any(a["target_id"] == "team:maccabi_tlv_bb" and a["level"] == 2
                   for a in affs)
        assert not any(a["target_id"] == "basketball" and a["scope"] == "sport"
                       for a in affs), "#64 Q1: no basketball floor on the seed"
