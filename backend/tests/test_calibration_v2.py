"""
Issue #33 — Calibration V2: dataset coverage, hierarchical inference,
support/contradiction handling, apply round-trip, version stamping.
"""
from fastapi.testclient import TestClient

from app.calibration_v2 import (
    CALIBRATION_DATASET_VERSION,
    CALIBRATION_ITEMS,
    infer_calibration_profile,
)


def _rate(**by_id) -> dict:
    return dict(by_id)


# ── Dataset coverage — every dimension isolatable ────────────────────────────

class TestDatasetCoverage:
    def test_dataset_size_and_version(self):
        assert len(CALIBRATION_ITEMS) == 24
        assert CALIBRATION_DATASET_VERSION == 2

    def test_every_competition_scope_has_two_baseline_items(self):
        """Competition support ≥2 must be reachable for every tagged
        competition (entity-tagged items are excluded from baselines)."""
        counts: dict[str, int] = {}
        for i in CALIBRATION_ITEMS:
            if i.competition_id and not i.entity_ids:
                counts[i.competition_id] = counts.get(i.competition_id, 0) + 1
        assert set(counts) == {"comp:nba", "comp:euroleague", "comp:ibl", "comp:acb"}
        assert all(n >= 2 for n in counts.values()), counts

    def test_sport_scoped_sports_have_two_items(self):
        counts: dict[str, int] = {}
        for i in CALIBRATION_ITEMS:
            if i.competition_id is None and not i.entity_ids:
                counts[i.sport] = counts.get(i.sport, 0) + 1
        assert counts["football"] >= 2 and counts["tennis"] >= 2

    def test_contrast_groups_pair_entity_with_baseline(self):
        groups: dict[str, dict[str, int]] = {}
        for i in CALIBRATION_ITEMS:
            if i.contrast_group:
                g = groups.setdefault(i.contrast_group, {"entity": 0, "baseline": 0})
                g["entity" if i.entity_ids else "baseline"] += 1
        # Entity-vs-league groups must have both sides.
        for name in ("maccabi_vs_ibl", "maccabi_vs_el", "deni_vs_nba"):
            assert groups[name]["entity"] >= 1 and groups[name]["baseline"] >= 1, name

    def test_major_and_routine_events_per_competition(self):
        majors = {"star_trade", "finals_result", "title_win", "playoff_result",
                  "major_transfer", "grand_slam_winner"}
        routines = {"regular_season_result", "match_result", "early_round_result"}
        for comp in ("comp:nba", "comp:euroleague", "comp:ibl", "comp:acb"):
            events = {i.event_type for i in CALIBRATION_ITEMS
                      if i.competition_id == comp and not i.entity_ids}
            assert events & majors, comp
            assert events & routines, comp


# ── Inference — hierarchy levels ─────────────────────────────────────────────

class TestSportBaseline:
    def test_low_interest_sport_inferred(self):
        inf = infer_calibration_profile(_rate(
            cal2_fb_mbappe="neutral", cal2_fb_routine="not_interesting",
            cal2_fb_ucl_title="not_interesting",
        ))
        sport = next(a for a in inf.scope_affinities if a.target_id == "football")
        assert sport.level == -1
        assert sport.source == "calibration"
        assert sport.evidence_count == 3

    def test_positive_sport_interest_capped_at_medium(self):
        inf = infer_calibration_profile(_rate(
            cal2_nba_star_trade="push", cal2_nba_finals="push",
            cal2_nba_routine_result="interesting",
        ))
        sport = next(a for a in inf.scope_affinities if a.target_id == "basketball")
        assert sport.level == 0  # enthusiasm lives at the competition level

    def test_single_rating_gives_no_sport_entry(self):
        inf = infer_calibration_profile(_rate(cal2_tn_gs_winner="push"))
        assert not any(a.scope == "sport" for a in inf.scope_affinities)


class TestCompetitionLevel:
    def test_broad_league_affinity_from_multiple_examples(self):
        inf = infer_calibration_profile(_rate(
            cal2_nba_star_trade="push", cal2_nba_routine_result="interesting",
            cal2_nba_finals="interesting", cal2_nba_interview="interesting",
        ))
        nba = next(a for a in inf.scope_affinities if a.target_id == "comp:nba")
        assert nba.scope == "competition"
        assert nba.level >= 1
        assert nba.evidence_count == 4

    def test_entity_items_excluded_from_competition_baseline(self):
        """Loving Deni must not inflate the NBA baseline."""
        inf = infer_calibration_profile(_rate(
            cal2_nba_deni_big_game="push", cal2_nba_deni_quiet_game="push",
            cal2_nba_routine_result="not_interesting", cal2_nba_interview="not_interesting",
        ))
        nba = next(a for a in inf.scope_affinities if a.target_id == "comp:nba")
        assert nba.level == -1

    def test_single_item_competition_gets_no_entry(self):
        inf = infer_calibration_profile(_rate(cal2_acb_title="interesting"))
        assert not any(a.target_id == "comp:acb" for a in inf.scope_affinities)


class TestEventDelta:
    def test_event_preference_separated_from_league(self):
        """NBA loved, interviews disliked → positive comp level + negative
        scoped interview delta (event-vs-scope contrast)."""
        inf = infer_calibration_profile(_rate(
            cal2_nba_star_trade="push", cal2_nba_finals="push",
            cal2_nba_routine_result="interesting", cal2_nba_interview="never_show",
        ))
        nba = next(a for a in inf.scope_affinities if a.target_id == "comp:nba")
        assert nba.level >= 1
        interview = next(
            e for e in inf.event_affinities
            if e.scope_ref == "comp:nba" and e.event_type == "interview"
        )
        assert interview.delta < 0
        assert interview.source == "calibration"

    def test_tennis_major_only_pattern(self):
        inf = infer_calibration_profile(_rate(
            cal2_tn_gs_winner="push", cal2_tn_gs_final="interesting",
            cal2_tn_early_round="never_show",
        ))
        gs = next(e for e in inf.event_affinities
                  if e.scope_ref == "tennis" and e.event_type == "grand_slam_winner")
        early = next(e for e in inf.event_affinities
                     if e.scope_ref == "tennis" and e.event_type == "early_round_result")
        assert gs.delta > 0
        assert early.delta < 0


class TestEntityContrast:
    def test_entity_boost_inferred_from_contrast_pair(self):
        """Maccabi signing push, generic IBL signing neutral → team entry."""
        inf = infer_calibration_profile(_rate(
            cal2_ibl_maccabi_signing="push", cal2_ibl_generic_signing="neutral",
        ))
        maccabi = next(a for a in inf.scope_affinities
                       if a.target_id == "team:maccabi_tlv_bb")
        assert maccabi.scope == "team"
        assert maccabi.level == 2

    def test_no_entity_entry_when_league_explains_ratings(self):
        inf = infer_calibration_profile(_rate(
            cal2_ibl_maccabi_signing="interesting", cal2_ibl_generic_signing="interesting",
        ))
        assert not any(a.target_id == "team:maccabi_tlv_bb"
                       for a in inf.scope_affinities)

    def test_deni_only_fan_pattern(self):
        inf = infer_calibration_profile(_rate(
            cal2_nba_deni_big_game="push", cal2_nba_deni_quiet_game="interesting",
            cal2_nba_routine_result="not_interesting", cal2_nba_interview="not_interesting",
            cal2_nba_star_trade="not_interesting", cal2_nba_finals="neutral",
        ))
        deni = next(a for a in inf.scope_affinities
                    if a.target_id == "player:deni_avdija")
        assert deni.scope == "player"
        assert deni.level >= 1
        nba = next(a for a in inf.scope_affinities if a.target_id == "comp:nba")
        assert nba.level <= -1


# ── Safety: contradictions and excludes ──────────────────────────────────────

class TestSafetyRules:
    def test_one_never_show_cannot_create_exclude(self):
        inf = infer_calibration_profile(_rate(
            cal2_fb_mbappe="never_show", cal2_fb_routine="not_interesting",
        ))
        football = next(a for a in inf.scope_affinities if a.target_id == "football")
        assert football.level == -1  # not -2: only one -2 rating

    def test_consistent_double_never_show_can_exclude(self):
        inf = infer_calibration_profile(_rate(
            cal2_fb_mbappe="never_show", cal2_fb_routine="never_show",
            cal2_fb_ucl_title="never_show",
        ))
        football = next(a for a in inf.scope_affinities if a.target_id == "football")
        assert football.level == -2

    def test_positive_signal_blocks_exclude(self):
        inf = infer_calibration_profile(_rate(
            cal2_fb_mbappe="interesting", cal2_fb_routine="never_show",
            cal2_fb_ucl_title="never_show",
        ))
        football = next(a for a in inf.scope_affinities if a.target_id == "football")
        assert football.level > -2

    def test_contradictions_shrink_toward_neutral_and_flag_uncertainty(self):
        inf = infer_calibration_profile(_rate(
            cal2_nba_star_trade="push", cal2_nba_routine_result="never_show",
            cal2_nba_finals="push", cal2_nba_interview="never_show",
        ))
        est = next(u for u in inf.uncertainty if u.target == "comp:nba")
        assert est.contradictory
        nba = next(a for a in inf.scope_affinities if a.target_id == "comp:nba")
        assert -1 <= nba.level <= 1  # pulled toward neutral, never an exclude

    def test_calibration_never_writes_overrides(self):
        inf = infer_calibration_profile({
            i.id: "push" for i in CALIBRATION_ITEMS
        })
        assert not hasattr(inf, "overrides") or not getattr(inf, "overrides", [])

    def test_empty_and_unknown_ratings_are_safe(self):
        assert infer_calibration_profile({}).scope_affinities == []
        inf = infer_calibration_profile({"nonexistent": "push", "cal2_nba_finals": "bogus"})
        assert inf.scope_affinities == []


# ── API round-trip ───────────────────────────────────────────────────────────

GUY_LIKE_RATINGS = {
    "cal2_nba_star_trade": "push",
    "cal2_nba_routine_result": "interesting",
    "cal2_nba_finals": "interesting",
    "cal2_nba_interview": "neutral",
    "cal2_nba_deni_big_game": "push",
    "cal2_nba_deni_quiet_game": "interesting",
    "cal2_el_title": "push",
    "cal2_el_routine_result": "interesting",
    "cal2_el_signing": "interesting",
    "cal2_el_interview": "neutral",
    "cal2_el_maccabi_game": "push",
    "cal2_ibl_maccabi_signing": "push",
    "cal2_ibl_generic_signing": "interesting",
    "cal2_ibl_routine_result": "interesting",
    "cal2_ibl_playoff": "interesting",
    "cal2_ibl_schedule": "never_show",
    "cal2_acb_title": "interesting",
    "cal2_acb_routine": "not_interesting",
    "cal2_fb_mbappe": "neutral",
    "cal2_fb_routine": "never_show",
    "cal2_fb_ucl_title": "neutral",
    "cal2_tn_gs_winner": "interesting",
    "cal2_tn_early_round": "never_show",
    "cal2_tn_gs_final": "neutral",
}


class TestApiRoundTrip:
    def test_items_endpoint_versioned(self, client: TestClient):
        body = client.get("/api/calibration/items").json()
        assert body["version"] == CALIBRATION_DATASET_VERSION
        assert len(body["items"]) == 24
        assert set(body["rating_keys"]) == {
            "never_show", "not_interesting", "neutral", "interesting", "push"
        }

    def test_preview_does_not_persist(self, client: TestClient):
        resp = client.post("/api/calibration/preview", json={"ratings": GUY_LIKE_RATINGS})
        assert resp.status_code == 200
        body = resp.json()
        assert body["dataset_version"] == CALIBRATION_DATASET_VERSION
        assert len(body["scope_affinities"]) > 0
        assert len(body["uncertainty"]) > 0
        # nothing saved
        saved = client.get("/api/calibration/responses/casual_deni_fan").json()
        assert saved["ratings"] == {}

    def test_preview_rejects_unknown_rating(self, client: TestClient):
        resp = client.post("/api/calibration/preview",
                           json={"ratings": {"cal2_nba_finals": "meh"}})
        assert resp.status_code == 422

    def test_apply_persists_and_survives_reload(self, client: TestClient):
        resp = client.post("/api/calibration/apply", json={
            "user_id": "casual_deni_fan", "ratings": GUY_LIKE_RATINGS,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["applied_scope_affinities"] > 0

        # fresh read: calibration-sourced entries present, explicit preserved
        profile = client.get("/api/profiles/casual_deni_fan").json()
        sources = {a["source"] for a in profile["profile_v2"]["scope_affinities"]}
        assert "calibration" in sources
        explicit = [a for a in profile["profile_v2"]["scope_affinities"]
                    if a["source"] == "explicit"]
        assert any(a["target_id"] == "player:deni_avdija" for a in explicit)
        # overrides untouched
        assert len(profile["profile_v2"]["overrides"]) > 0

        # ratings persisted with version
        saved = client.get("/api/calibration/responses/casual_deni_fan").json()
        assert saved["dataset_version"] == CALIBRATION_DATASET_VERSION
        assert saved["ratings"] == GUY_LIKE_RATINGS

    def test_reapply_replaces_only_calibration_entries(self, client: TestClient):
        before = client.get("/api/profiles/casual_deni_fan").json()
        explicit_before = [a for a in before["profile_v2"]["scope_affinities"]
                           if a["source"] == "explicit"]
        # re-apply with a much smaller rating set
        resp = client.post("/api/calibration/apply", json={
            "user_id": "casual_deni_fan",
            "ratings": {"cal2_tn_gs_winner": "push", "cal2_tn_early_round": "never_show"},
        })
        assert resp.status_code == 200
        after = client.get("/api/profiles/casual_deni_fan").json()
        explicit_after = [a for a in after["profile_v2"]["scope_affinities"]
                          if a["source"] == "explicit"]
        assert explicit_after == explicit_before
        calibration_after = [a for a in after["profile_v2"]["scope_affinities"]
                             if a["source"] == "calibration"]
        assert all(a["target_id"] == "tennis" for a in calibration_after)

    def test_apply_unknown_profile_404(self, client: TestClient):
        resp = client.post("/api/calibration/apply",
                           json={"user_id": "nobody", "ratings": {}})
        assert resp.status_code == 404

    def test_calibrated_feed_reflects_ratings(self, client: TestClient):
        """Acceptance: apply persists and a fresh session shows the
        calibrated feed — Guy-like ratings on the Deni-fan profile make NBA
        game results visible (hidden for the narrow explicit profile).

        Inserts its own rss_ article rather than using the session-scoped
        rss_seeded fixture (which must not be instantiated before
        test_dev_reset in suite order)."""
        from datetime import datetime, timezone
        from app.db.database import SessionLocal
        from app.models.article import Article
        from app.repositories.article_repository import get_by_id, insert

        with SessionLocal() as session:
            if get_by_id(session, "rss_cal2_nba_game") is None:
                insert(session, Article(
                    id="rss_cal2_nba_game",
                    source="test", source_display_name="Test",
                    url="https://rss.test.local/cal2-nba-game",
                    title="לייקרס ניצחו את סלטיקס במשחק ליגה",
                    language="he",
                    published_at=datetime(2026, 7, 8, tzinfo=timezone.utc),
                    sport="basketball", league="NBA",
                    entities=["Los Angeles Lakers", "Boston Celtics"],
                    entity_ids=["team:la_lakers", "team:boston_celtics"],
                    event_type="regular_season_result", importance="medium",
                    confidence=0.9, tags=[], taxonomy_version=1,
                ))

        client.post("/api/calibration/apply", json={
            "user_id": "casual_deni_fan", "ratings": GUY_LIKE_RATINGS,
        })
        feed = client.get("/api/feed/casual_deni_fan").json()
        nba_item = next(
            (i for i in feed if i["article"]["id"] == "rss_cal2_nba_game"), None
        )
        assert nba_item is not None, "NBA game must now be visible"
        assert nba_item["decision"] != "hidden"

        # Cleanup: an empty-ratings apply removes all calibration-sourced
        # entries, restoring the explicit-only seed profile for later tests.
        client.post("/api/calibration/apply",
                    json={"user_id": "casual_deni_fan", "ratings": {}})
        restored = client.get("/api/profiles/casual_deni_fan").json()
        assert all(a["source"] != "calibration"
                   for a in restored["profile_v2"]["scope_affinities"])

    def test_legacy_headlines_endpoint_serves_v2_dataset(self, client: TestClient):
        body = client.get("/api/calibration/headlines").json()
        assert len(body) == 24
        assert all("importance" in h and "sport" in h for h in body)
