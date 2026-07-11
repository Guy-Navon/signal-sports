"""
Issue #77 — Preference Acquisition Contract + Interests API.

Covers: tier→level mapping, managed explicit-subset replacement (the
merge-survival matrix), event preset expansion, validation (unknown /
non-selectable / duplicate targets, injected user_id), interest-stage
completion states incl. the legacy-user rule, session bootstrap, engine
integration (a profile written via this API scores through the frozen
engine), and persistence round-trips.
"""
from datetime import datetime, timezone

import pytest

from app.db.database import SessionLocal
from app.models.profile import UserProfile
from app.models.profile_v2 import EventAffinity, OverrideRule, ProfileV2, ScopeAffinity
from app.repositories import profile_repository
from app.services.interests_service import (
    EVENT_PRESET_GROUPS,
    InterestsPutRequest,
    InterestsValidationError,
    TIER_LEVELS,
    interests_document,
    replace_managed_interests,
)


# ── Unit: tier → level mapping ────────────────────────────────────────────────

class TestTierMapping:
    def test_kind_sensitive_levels(self):
        assert TIER_LEVELS["sport"] == {"follow": 0, "star": 1}
        assert TIER_LEVELS["competition"] == {"follow": 1, "star": 2}
        assert TIER_LEVELS["team"] == {"follow": 1, "star": 2}
        assert TIER_LEVELS["player"] == {"follow": 1, "star": 2}

    def test_presets_expand_to_canonical_event_types_only(self):
        """Preset groups are product presets over the EXISTING event
        taxonomy — every expanded type must be a plain event-type string,
        and groups must not overlap (a delta would double-write)."""
        seen = set()
        for group, events in EVENT_PRESET_GROUPS.items():
            for event_type in events:
                assert event_type not in seen, f"{event_type} in two groups"
                seen.add(event_type)


# ── Unit/service: managed-subset replacement (merge-survival matrix) ──────────

def _rich_profile() -> UserProfile:
    """A profile containing every category the PUT must preserve."""
    return UserProfile(
        user_id="survival_user",
        display_name="Survival",
        profile_type="test",
        topics=[],
        muted_topics=["tennis"],
        muted_sources=["spammy_source"],
        profile_v2=ProfileV2(
            scope_affinities=[
                # managed: explicit, level >= 0 → replaced
                ScopeAffinity(scope="sport", target_id="basketball", level=0,
                              source="explicit"),
                # NOT managed: explicit negative level (seed-style nuance)
                ScopeAffinity(scope="competition", target_id="comp:acb", level=-1,
                              source="explicit"),
                # NOT managed: calibration
                ScopeAffinity(scope="competition", target_id="comp:nba", level=1,
                              source="calibration"),
                # NOT managed: learned
                ScopeAffinity(scope="player", target_id="player:deni_avdija",
                              level=1, source="learned"),
            ],
            event_affinities=[
                # managed: explicit global → replaced
                EventAffinity(scope_ref=None, event_type="injury", delta=1,
                              source="explicit"),
                # NOT managed: scoped explicit
                EventAffinity(scope_ref="comp:nba", event_type="schedule", delta=-2,
                              source="explicit"),
                # NOT managed: calibration (global or scoped)
                EventAffinity(scope_ref="comp:nba", event_type="interview", delta=1,
                              source="calibration"),
                # NOT managed: learned
                EventAffinity(scope_ref=None, event_type="match_result", delta=-1,
                              source="learned"),
            ],
            overrides=[
                OverrideRule(kind="never_show", scope="competition",
                             target_id="comp:nba", event_type="schedule"),
                OverrideRule(kind="always_push", scope="player",
                             target_id="player:deni_avdija", event_type="injury"),
            ],
        ),
    )


class TestManagedSubsetReplacement:
    PUT = InterestsPutRequest(
        follows=[
            {"scope": "competition", "target_id": "comp:euroleague", "starred": True},
            {"scope": "team", "target_id": "team:maccabi_tlv_bb", "starred": False},
        ],
        event_preferences={"transfers_rumors": "more", "schedules_previews": "less"},
    )

    @pytest.fixture()
    def replaced(self, client):
        profile = _rich_profile()
        with SessionLocal() as session:
            profile_repository.insert(session, profile)
            try:
                yield replace_managed_interests(session, profile, self.PUT)
            finally:
                from app.db.orm_models import ProfileRow
                session.query(ProfileRow).filter(
                    ProfileRow.user_id == "survival_user"
                ).delete(synchronize_session=False)
                session.commit()

    def test_managed_scopes_replaced(self, replaced):
        explicit_managed = [
            a for a in replaced.profile_v2.scope_affinities
            if a.source == "explicit" and a.level >= 0
        ]
        assert {(a.scope, a.target_id, a.level) for a in explicit_managed} == {
            ("competition", "comp:euroleague", 2),  # starred
            ("team", "team:maccabi_tlv_bb", 1),     # follow
        }

    def test_unmanaged_scope_entries_survive(self, replaced):
        kept = {(a.scope, a.target_id, a.level, a.source)
                for a in replaced.profile_v2.scope_affinities}
        assert ("competition", "comp:acb", -1, "explicit") in kept
        assert ("competition", "comp:nba", 1, "calibration") in kept
        assert ("player", "player:deni_avdija", 1, "learned") in kept

    def test_global_explicit_events_replaced_by_presets(self, replaced):
        managed = {
            (e.event_type, e.delta)
            for e in replaced.profile_v2.event_affinities
            if e.source == "explicit" and e.scope_ref is None
        }
        expected = {(et, 1) for et in EVENT_PRESET_GROUPS["transfers_rumors"]}
        expected |= {(et, -1) for et in EVENT_PRESET_GROUPS["schedules_previews"]}
        assert managed == expected  # the old global injury +1 is gone

    def test_unmanaged_event_entries_survive(self, replaced):
        kept = {(e.scope_ref, e.event_type, e.delta, e.source)
                for e in replaced.profile_v2.event_affinities}
        assert ("comp:nba", "schedule", -2, "explicit") in kept
        assert ("comp:nba", "interview", 1, "calibration") in kept
        assert (None, "match_result", -1, "learned") in kept

    def test_overrides_and_mutes_untouched(self, replaced):
        kinds = {(o.kind, o.target_id) for o in replaced.profile_v2.overrides}
        assert kinds == {("never_show", "comp:nba"),
                         ("always_push", "player:deni_avdija")}
        assert replaced.muted_topics == ["tennis"]
        assert replaced.muted_sources == ["spammy_source"]

    def test_document_round_trip(self, replaced):
        doc = interests_document(replaced, completed=True)
        assert {(f.scope, f.target_id, f.starred) for f in doc.follows} == {
            ("competition", "comp:euroleague", True),
            ("team", "team:maccabi_tlv_bb", False),
        }
        assert doc.event_preferences == {"transfers_rumors": "more",
                                         "schedules_previews": "less"}
        assert doc.selected == 2


class TestValidationRules:
    def _attempt(self, payload: InterestsPutRequest):
        profile = UserProfile(user_id="v_user", display_name="V",
                              profile_type="test", topics=[],
                              profile_v2=ProfileV2())
        with pytest.raises(InterestsValidationError):
            replace_managed_interests(None, profile, payload)

    def test_unknown_target_rejected(self):
        self._attempt(InterestsPutRequest(follows=[
            {"scope": "team", "target_id": "team:not_a_real_team"},
        ]))

    def test_non_selectable_competition_rejected(self):
        for comp in ("comp:epl", "comp:la_liga", "comp:bundesliga", "comp:ucl"):
            self._attempt(InterestsPutRequest(follows=[
                {"scope": "competition", "target_id": comp},
            ]))

    def test_tennis_slams_are_selectable(self, client):
        """Grand Slams are competition-only selectable (zero entities is fine)."""
        profile = UserProfile(user_id="t_user", display_name="T",
                              profile_type="test", topics=[],
                              profile_v2=ProfileV2())
        with SessionLocal() as session:
            profile_repository.insert(session, profile)
            try:
                result = replace_managed_interests(
                    session, profile, InterestsPutRequest(follows=[
                        {"scope": "competition", "target_id": "comp:wimbledon"},
                    ]))
                assert result.profile_v2.scope_affinities[0].level == 1
            finally:
                from app.db.orm_models import ProfileRow
                session.query(ProfileRow).filter(
                    ProfileRow.user_id == "t_user"
                ).delete(synchronize_session=False)
                session.commit()

    def test_duplicate_target_rejected(self):
        self._attempt(InterestsPutRequest(follows=[
            {"scope": "team", "target_id": "team:maccabi_tlv_bb"},
            {"scope": "team", "target_id": "team:maccabi_tlv_bb", "starred": True},
        ]))

    def test_unknown_preset_group_rejected(self):
        self._attempt(InterestsPutRequest(event_preferences={"betting_odds": "more"}))


# ── API: /api/me/interests round trip + isolation + completion states ─────────

def _signup(client_factory, email):
    c = client_factory
    response = c.post("/api/auth/signup",
                      json={"email": email, "password": "password-123"})
    assert response.status_code == 201, response.text
    return c


ARCHETYPE_A_PUT = {
    "follows": [
        {"scope": "sport", "target_id": "basketball", "starred": False},
        {"scope": "competition", "target_id": "comp:euroleague", "starred": False},
        {"scope": "team", "target_id": "team:maccabi_tlv_bb", "starred": True},
    ],
    "event_preferences": {"transfers_rumors": "more"},
}


class TestInterestsApi:
    def test_new_user_starts_incomplete_and_empty(self, user_client):
        doc = user_client.get("/api/me/interests").json()
        assert doc == {"follows": [], "event_preferences": {},
                       "completed": False, "selected": 0}
        session = user_client.get("/api/auth/session").json()
        assert session["onboarding"]["interests"] == {"completed": False,
                                                      "selected": 0}

    def test_put_round_trip_and_completion(self, user_client):
        put = user_client.put("/api/me/interests", json=ARCHETYPE_A_PUT)
        assert put.status_code == 200, put.text
        doc = put.json()
        assert doc["completed"] is True
        assert doc["selected"] == 3
        assert {(f["scope"], f["target_id"], f["starred"])
                for f in doc["follows"]} == {
            ("sport", "basketball", False),
            ("competition", "comp:euroleague", False),
            ("team", "team:maccabi_tlv_bb", True),
        }
        # GET agrees; bootstrap reflects the stage.
        assert user_client.get("/api/me/interests").json() == doc
        session = user_client.get("/api/auth/session").json()
        assert session["onboarding"]["interests"] == {"completed": True,
                                                      "selected": 3}
        assert session["user"]["interests_completed_at"] is not None

    def test_put_writes_explicit_profile_v2_entries(self, user_client):
        user_client.put("/api/me/interests", json=ARCHETYPE_A_PUT)
        profile = user_client.get("/api/me/profile").json()
        affs = {(a["scope"], a["target_id"]): a
                for a in profile["profile_v2"]["scope_affinities"]}
        assert affs[("sport", "basketball")]["level"] == 0
        assert affs[("competition", "comp:euroleague")]["level"] == 1
        assert affs[("team", "team:maccabi_tlv_bb")]["level"] == 2
        assert all(a["source"] == "explicit" for a in affs.values())
        globals_ = [e for e in profile["profile_v2"]["event_affinities"]
                    if e["scope_ref"] is None and e["source"] == "explicit"]
        assert {e["event_type"] for e in globals_} == set(
            EVENT_PRESET_GROUPS["transfers_rumors"])
        assert all(e["delta"] == 1 for e in globals_)
        # No overrides were created — push stays out of this surface.
        assert profile["profile_v2"]["overrides"] == []

    def test_injected_user_id_is_422(self, user_client):
        response = user_client.put("/api/me/interests", json={
            **ARCHETYPE_A_PUT, "user_id": "guy",
        })
        assert response.status_code == 422

    def test_non_selectable_target_is_422(self, user_client):
        response = user_client.put("/api/me/interests", json={
            "follows": [{"scope": "competition", "target_id": "comp:epl"}],
            "event_preferences": {},
        })
        assert response.status_code == 422
        assert "comp:epl" in response.text

    def test_skip_path_completes_without_data(self, user_client):
        response = user_client.post("/api/me/interests/complete")
        assert response.status_code == 200
        doc = response.json()
        assert doc["completed"] is True and doc["selected"] == 0
        # Idempotent: repeat keeps the same state.
        again = user_client.post("/api/me/interests/complete").json()
        assert again["completed"] is True

    def test_selections_later_removed_stays_completed(self, user_client):
        user_client.put("/api/me/interests", json=ARCHETYPE_A_PUT)
        cleared = user_client.put("/api/me/interests",
                                  json={"follows": [], "event_preferences": {}})
        doc = cleared.json()
        assert doc["selected"] == 0
        assert doc["completed"] is True  # no re-funnel

    def test_legacy_user_reads_completed(self, user_client):
        """Old-onboarding users (onboarding_completed_at set, interests
        NULL) are treated as interests-complete — never re-funneled."""
        user_client.post("/api/me/onboarding/complete")
        session = user_client.get("/api/auth/session").json()
        assert session["user"]["interests_completed_at"] is None
        assert session["onboarding"]["interests"]["completed"] is True

    def test_engine_scores_api_written_profile(self, user_client):
        """A profile created purely through this API produces personalized
        feed decisions through the frozen engine (zero engine changes)."""
        from datetime import datetime, timezone
        from app.models.article import Article
        from app.services.preference_engine import score_article_v2

        user_client.put("/api/me/interests", json=ARCHETYPE_A_PUT)
        raw = user_client.get("/api/me/profile").json()
        profile = UserProfile.model_validate(raw)
        maccabi = Article(
            id="x", source="test", source_display_name="T", url="https://x",
            title="t", language="he",
            published_at=datetime(2026, 7, 11, tzinfo=timezone.utc),
            sport="basketball", league=None, entities=[],
            event_type="signing", importance="medium", confidence=0.9,
            tags=[], primary_competition=None, article_competitions=[],
            entity_ids=["team:maccabi_tlv_bb"], taxonomy_version=1,
        )
        unknown = maccabi.model_copy(update={"entity_ids": [], "event_type": "news"})
        assert score_article_v2(maccabi, profile).decision == "high_feed"
        assert score_article_v2(unknown, profile).decision == "low_feed"

    def test_horizontal_isolation(self, user_client, admin_client):
        """One user's PUT never leaks into another identity's document."""
        user_client.put("/api/me/interests", json=ARCHETYPE_A_PUT)
        other = admin_client.get("/api/me/interests").json()
        assert other["follows"] == []


class TestPersistenceRoundTrip:
    def test_interests_survive_logout_login(self, _application, client):
        from tests.conftest import (
            _TEST_IDENTITY_PASSWORD, _dispose_identity, _identity_client,
        )

        c = _identity_client(_application, "user")
        try:
            c.put("/api/me/interests", json=ARCHETYPE_A_PUT)
            c.post("/api/auth/logout")
            login = c.post("/api/auth/login", json={
                "email": c.identity_email, "password": _TEST_IDENTITY_PASSWORD,
            })
            assert login.status_code == 200
            doc = c.get("/api/me/interests").json()
            assert doc["selected"] == 3 and doc["completed"] is True
        finally:
            _dispose_identity(c)
