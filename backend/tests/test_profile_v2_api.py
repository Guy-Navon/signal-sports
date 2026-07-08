"""
Issue #32 — ProfileV2 persistence + API surface.

Covers: profile_v2 round-trip through the profiles row, the seed backfill
for pre-existing DBs, PUT /api/profiles/{user_id} (validation, mismatch
rejection, 404), GET /api/debug/shadow/{user_id}, and the feed-engine flag.
"""
from fastapi.testclient import TestClient


class TestPersistence:
    def test_seed_profiles_carry_v2(self, client: TestClient):
        body = client.get("/api/profiles/guy").json()
        assert body["profile_v2"] is not None
        assert body["profile_v2"]["version"] == 2
        assert len(body["profile_v2"]["scope_affinities"]) > 0

    def test_v2_backfill_on_existing_rows(self, client: TestClient):
        """Simulate a pre-#32 DB: null the column, re-run the seed runner,
        and confirm the seed v2 payload is restored (only when missing)."""
        from app.db.database import SessionLocal
        from app.db.orm_models import ProfileRow
        from app.repositories.seed_runner import seed_all_if_empty

        with SessionLocal() as session:
            row = session.get(ProfileRow, "guy")
            row.profile_v2 = None
            session.commit()
        with SessionLocal() as session:
            seed_all_if_empty(session)
        body = client.get("/api/profiles/guy").json()
        assert body["profile_v2"] is not None


class TestMutationApi:
    def test_put_profile_updates_v2(self, client: TestClient):
        profile = client.get("/api/profiles/casual_deni_fan").json()
        profile["profile_v2"]["scope_affinities"].append({
            "scope": "competition", "target_id": "comp:nba", "level": 0,
            "source": "explicit", "evidence_count": 0,
        })
        resp = client.put("/api/profiles/casual_deni_fan", json=profile)
        assert resp.status_code == 200
        stored = client.get("/api/profiles/casual_deni_fan").json()
        targets = [a["target_id"] for a in stored["profile_v2"]["scope_affinities"]]
        assert "comp:nba" in targets
        # restore the seed shape for other tests
        profile["profile_v2"]["scope_affinities"] = [
            a for a in profile["profile_v2"]["scope_affinities"]
            if a["target_id"] != "comp:nba"
        ]
        client.put("/api/profiles/casual_deni_fan", json=profile)

    def test_put_rejects_invalid_affinity(self, client: TestClient):
        profile = client.get("/api/profiles/guy").json()
        profile["profile_v2"]["scope_affinities"].append({
            "scope": "competition", "target_id": "team:la_lakers", "level": 1,
        })
        resp = client.put("/api/profiles/guy", json=profile)
        assert resp.status_code == 422

    def test_put_rejects_out_of_range_level(self, client: TestClient):
        profile = client.get("/api/profiles/guy").json()
        profile["profile_v2"]["scope_affinities"].append({
            "scope": "competition", "target_id": "comp:nba", "level": 5,
        })
        resp = client.put("/api/profiles/guy", json=profile)
        assert resp.status_code == 422

    def test_put_rejects_user_id_mismatch(self, client: TestClient):
        profile = client.get("/api/profiles/guy").json()
        profile["user_id"] = "someone_else"
        resp = client.put("/api/profiles/guy", json=profile)
        assert resp.status_code == 422

    def test_put_unknown_profile_404(self, client: TestClient):
        profile = client.get("/api/profiles/guy").json()
        profile["user_id"] = "nobody"
        resp = client.put("/api/profiles/nobody", json=profile)
        assert resp.status_code == 404


class TestShadowEndpoint:
    def test_shadow_report_shape(self, client: TestClient, rss_seeded):
        resp = client.get("/api/debug/shadow/guy")
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "guy"
        assert body["total"] > 0
        assert body["agreements"] + body["disagreements"] == body["total"]
        for c in body["comparisons"]:
            assert c["agree"] is False
            assert c["legacy_decision"] != c["v2_decision"]
            assert c["v2_contributions"]

    def test_shadow_unknown_profile_404(self, client: TestClient):
        assert client.get("/api/debug/shadow/nobody").status_code == 404


class TestFeedEngineFlag:
    def test_default_engine_is_v2(self, client: TestClient):
        # Flipped after the Fable shadow checkpoint (2026-07-08).
        assert client.get("/api/feed-engine").json() == {"engine": "v2"}

    def test_legacy_rollback_path(self, client: TestClient, monkeypatch):
        monkeypatch.setenv("PREFERENCE_ENGINE", "legacy")
        assert client.get("/api/feed-engine").json() == {"engine": "legacy"}

    def test_v2_engine_serves_feed(self, client: TestClient, rss_seeded, monkeypatch):
        monkeypatch.setenv("PREFERENCE_ENGINE", "v2")
        assert client.get("/api/feed-engine").json() == {"engine": "v2"}
        resp = client.get("/api/feed/guy")
        assert resp.status_code == 200
        feed = resp.json()
        assert len(feed) > 0
        assert all(item["decision"] != "hidden" for item in feed)
        # v2 results carry the structured contribution trace
        assert any(item.get("contributions") for item in feed)

    def test_invalid_engine_value_falls_back_to_v2(self, client: TestClient, monkeypatch):
        monkeypatch.setenv("PREFERENCE_ENGINE", "quantum")
        assert client.get("/api/feed-engine").json() == {"engine": "v2"}


class TestObservabilityShape:
    """Issue #35 — trace fields exposed through the debug feed payload."""

    def test_debug_payload_carries_engine_and_contributions(self, client: TestClient, rss_seeded):
        items = client.get("/api/debug/feed/guy").json()
        assert len(items) > 0
        for item in items:
            assert item["engine"] in ("v2", "legacy")
        v2_items = [i for i in items if i["engine"] == "v2" and i["decision"] != "hidden"]
        assert any(i.get("contributions") for i in v2_items)

    def test_v2_trace_shows_rejected_scopes(self, client: TestClient, rss_seeded):
        items = client.get("/api/debug/feed/guy").json()
        with_rejected = [
            i for i in items
            if any(c["step"] == "scopes_considered" for c in (i.get("contributions") or []))
        ]
        assert len(with_rejected) > 0
        entry = next(
            c for c in with_rejected[0]["contributions"]
            if c["step"] == "scopes_considered"
        )
        assert entry["effect"] == "no_match"
        assert entry["detail"]  # comma-separated non-matching followed scopes
