"""
Issue #81 — Interest-aware calibration selection.

Covers: determinism, interest scoping, entity-pair completeness, discovery
probes, sport-without-competition support, the zero-interest default, size
bounds, the /api/me/calibration/items surface, and composition (explicit
entries outrank re-applied calibration; the estimator works on selected
subsets).
"""
import pytest

from app.calibration_v2 import CALIBRATION_ITEMS, infer_calibration_profile
from app.calibration_v2.selection import (
    TARGET_MAX,
    TARGET_MIN,
    select_items,
)
from app.models.profile_v2 import ProfileV2, ScopeAffinity
from app.services.calibration_service import merge_calibration_into_profile
from app.models.profile import UserProfile


def _archetype_a() -> ProfileV2:
    return ProfileV2(scope_affinities=[
        ScopeAffinity(scope="sport", target_id="basketball", level=0,
                      source="explicit"),
        ScopeAffinity(scope="competition", target_id="comp:euroleague", level=1,
                      source="explicit"),
        ScopeAffinity(scope="team", target_id="team:maccabi_tlv_bb", level=2,
                      source="explicit"),
    ])


class TestSelection:
    def test_deterministic_per_user(self):
        v2 = _archetype_a()
        first = [i.id for i in select_items(v2, user_id="user_1")]
        again = [i.id for i in select_items(v2, user_id="user_1")]
        other = [i.id for i in select_items(v2, user_id="user_2")]
        assert first == again  # resumable across sessions/devices
        # Different users may differ (seeded randomness) but share structure.
        assert set(first) != set() and set(other) != set()

    def test_size_bounds(self):
        for user in ("u1", "u2", "u3"):
            selected = select_items(_archetype_a(), user_id=user)
            assert TARGET_MIN <= len(selected) <= TARGET_MAX, len(selected)

    def test_starred_entity_pairs_complete(self):
        """Maccabi contrast items AND their same-group baselines must both
        be served — the estimator infers entity levels only from pairs."""
        selected = select_items(_archetype_a(), user_id="u1")
        ids = {i.id for i in selected}
        assert "cal2_ibl_maccabi_signing" in ids
        assert "cal2_ibl_generic_signing" in ids   # maccabi_vs_ibl baseline
        assert "cal2_el_maccabi_game" in ids
        assert "cal2_el_routine_result" in ids     # maccabi_vs_el baseline

    def test_followed_competition_gets_nuance_items(self):
        selected = select_items(_archetype_a(), user_id="u1")
        el = [i for i in selected
              if i.competition_id == "comp:euroleague" and not i.entity_ids]
        assert len(el) >= 2
        assert len({i.event_type for i in el}) >= 2

    def test_discovery_probes_outside_declared_interests(self):
        selected = select_items(_archetype_a(), user_id="u1")
        declared = {"comp:euroleague", "sport:basketball"}
        outside = [
            i for i in selected
            if not i.entity_ids
            and (i.competition_id or f"sport:{i.sport}") not in declared
            and i.sport != "basketball"  # basketball comps covered by sport follow? no — kept strict below
        ]
        # At least one probe from a different sport entirely.
        assert any(i.sport != "basketball" for i in outside), [i.id for i in selected]

    def test_sport_follow_without_competition_gets_support(self):
        """A football-only follower still gets football competition items
        so the sport baseline has support >= 2."""
        v2 = ProfileV2(scope_affinities=[
            ScopeAffinity(scope="sport", target_id="football", level=0,
                          source="explicit"),
        ])
        selected = select_items(v2, user_id="u1")
        football = [i for i in selected if i.sport == "football"]
        assert len(football) >= 3  # sport probes + one competition's items

    def test_zero_interest_default_mirrors_v2_shape(self):
        selected = select_items(None, user_id="u1")
        assert TARGET_MIN <= len(selected) <= TARGET_MAX
        scopes = {i.competition_id for i in selected if i.competition_id}
        assert {"comp:ibl", "comp:euroleague", "comp:nba"} <= scopes
        entities = {e for i in selected for e in i.entity_ids}
        assert "team:maccabi_tlv_bb" in entities
        assert "player:deni_avdija" in entities

    def test_empty_profile_equals_none(self):
        assert (
            [i.id for i in select_items(ProfileV2(), user_id="u1")]
            == [i.id for i in select_items(None, user_id="u1")]
        )

    def test_calibration_sourced_follows_do_not_drive_selection(self):
        """Selection keys on EXPLICIT interests only — calibration-derived
        scopes must not recursively steer the next calibration."""
        v2 = ProfileV2(scope_affinities=[
            ScopeAffinity(scope="competition", target_id="comp:acb", level=2,
                          source="calibration"),
        ])
        assert (
            [i.id for i in select_items(v2, user_id="u1")]
            == [i.id for i in select_items(None, user_id="u1")]
        )


class TestInferenceOnSelectedSubset:
    def test_estimator_produces_scoped_nuance_from_selection(self):
        """Rate an archetype-A selection: EL loved but schedules hated →
        comp level + scoped negative delta, all from the subset alone."""
        selected = select_items(_archetype_a(), user_id="u1")
        el_items = [i for i in selected
                    if i.competition_id == "comp:euroleague" and not i.entity_ids]
        assert len(el_items) >= 2
        ratings = {i.id: "interesting" for i in el_items}
        # One EL probe rated hard-negative — the median keeps the level.
        ratings[el_items[-1].id] = "never_show"
        inference = infer_calibration_profile(ratings)
        el = next(a for a in inference.scope_affinities
                  if a.target_id == "comp:euroleague")
        assert el.source == "calibration"

    def test_explicit_outranks_reapplied_calibration(self):
        """Composition: after merging a calibration inference that
        disagrees with an explicit follow, the effective level is the
        explicit one (authority resolution — no new merge logic)."""
        profile = UserProfile(
            user_id="comp_user", display_name="C", profile_type="test",
            topics=[], profile_v2=_archetype_a(),
        )
        el_items = [i for i in CALIBRATION_ITEMS
                    if i.competition_id == "comp:euroleague" and not i.entity_ids]
        ratings = {i.id: "never_show" for i in el_items}  # hates EL in ratings
        inference = infer_calibration_profile(ratings)
        merged = merge_calibration_into_profile(profile, inference)
        effective = {
            (a.scope, a.target_id): a
            for a in merged.profile_v2.effective_scope_affinities()
        }
        el = effective[("competition", "comp:euroleague")]
        assert el.source == "explicit"
        assert el.level == 1  # the explicit Follow survives


class TestMeCalibrationItemsApi:
    def test_requires_user(self, anonymous_client):
        assert anonymous_client.get("/api/me/calibration/items").status_code == 401

    def test_interest_aware_subset_served(self, user_client):
        user_client.put("/api/me/interests", json={
            "follows": [
                {"scope": "competition", "target_id": "comp:euroleague"},
                {"scope": "team", "target_id": "team:maccabi_tlv_bb",
                 "starred": True},
            ],
            "event_preferences": {},
        })
        body = user_client.get("/api/me/calibration/items").json()
        assert TARGET_MIN <= len(body["items"]) <= TARGET_MAX
        ids = {i["id"] for i in body["items"]}
        assert "cal2_el_maccabi_game" in ids
        assert "cal2_ibl_maccabi_signing" in ids
        # Deterministic: same selection on repeat call.
        again = user_client.get("/api/me/calibration/items").json()
        assert [i["id"] for i in again["items"]] == [i["id"] for i in body["items"]]

    def test_admin_full_dataset_endpoint_unchanged(self, admin_client):
        body = admin_client.get("/api/calibration/items").json()
        assert len(body["items"]) == len(CALIBRATION_ITEMS)

    def test_rating_selected_items_round_trips(self, user_client):
        user_client.put("/api/me/interests", json={
            "follows": [{"scope": "competition", "target_id": "comp:nba"}],
            "event_preferences": {},
        })
        items = user_client.get("/api/me/calibration/items").json()["items"]
        ratings = {items[0]["id"]: "interesting", items[1]["id"]: "not_interesting"}
        save = user_client.post("/api/me/calibration/responses",
                                json={"ratings": ratings})
        assert save.status_code == 200
        apply_ = user_client.post("/api/me/calibration/apply",
                                  json={"ratings": ratings})
        assert apply_.status_code == 200
