"""
Issue #78 — Taxonomy Catalog API.

The catalog is a pure projection of the taxonomy modules; these tests lock
projection completeness (freshness by construction), the selectable policy,
search-alias sufficiency, curated ordering, and the auth gate.
"""
from app.api.routes_taxonomy import build_catalog
from app.taxonomy import TAXONOMY_VERSION
from app.taxonomy.competitions import COMPETITIONS
from app.taxonomy.entities import ENTITIES
from app.taxonomy.policy import (
    NON_SELECTABLE_COMPETITIONS,
    scope_target_selectable,
)


class TestProjectionCompleteness:
    """Freshness guard: the catalog can never drift from the registry
    because it is derived — these tests prove the derivation is total."""

    def test_every_competition_appears_exactly_once(self):
        catalog = build_catalog()
        catalog_comp_ids = [
            c.id for sport in catalog.sports for c in sport.competitions
        ]
        assert sorted(catalog_comp_ids) == sorted(COMPETITIONS.keys())

    def test_every_entity_appears_exactly_once(self):
        catalog = build_catalog()
        ids = [t.id for t in catalog.teams] + [p.id for p in catalog.people]
        assert sorted(ids) == sorted(ENTITIES.keys())

    def test_version_matches_registry(self):
        assert build_catalog().taxonomy_version == TAXONOMY_VERSION

    def test_sports_are_the_selectable_sports(self):
        catalog = build_catalog()
        assert [s.id for s in catalog.sports] == ["basketball", "football", "tennis"]
        assert all(s.selectable for s in catalog.sports)


class TestSelectablePolicy:
    def test_selectable_flags_match_shared_policy(self):
        """The same policy functions the interests validation (#77) uses."""
        catalog = build_catalog()
        for sport in catalog.sports:
            for comp in sport.competitions:
                assert comp.selectable == scope_target_selectable(
                    "competition", comp.id
                ), comp.id

    def test_unprovable_football_competitions_visible_but_not_selectable(self):
        catalog = build_catalog()
        flags = {
            c.id: c.selectable
            for sport in catalog.sports for c in sport.competitions
        }
        for comp_id in NON_SELECTABLE_COMPETITIONS:
            assert flags[comp_id] is False, comp_id

    def test_tennis_slams_selectable_competition_only(self):
        catalog = build_catalog()
        tennis = next(s for s in catalog.sports if s.id == "tennis")
        assert len(tennis.competitions) == 4
        assert all(c.selectable for c in tennis.competitions)
        # competition-only: zero tennis entities exist, and that's fine.
        assert not any(t.sport == "tennis" for t in catalog.teams)

    def test_every_selectable_target_passes_interests_validation(self):
        """The contract coupling: a selectable catalog id must validate in
        PUT /api/me/interests, and vice versa."""
        catalog = build_catalog()
        for sport in catalog.sports:
            assert scope_target_selectable("sport", sport.id)
            for comp in sport.competitions:
                assert comp.selectable == scope_target_selectable(
                    "competition", comp.id)
        for team in catalog.teams:
            assert team.selectable == scope_target_selectable("team", team.id)
        for person in catalog.people:
            assert person.selectable == scope_target_selectable(
                "player", person.id)


class TestSearchAndOrdering:
    def test_hapoel_tlv_bb_findable_in_hebrew_and_english(self):
        catalog = build_catalog()
        hapoel = next(t for t in catalog.teams if t.id == "team:hapoel_tlv_bb")
        aliases = [a.lower() for a in hapoel.aliases]
        assert any("הפועל תל אביב" in a for a in aliases)
        assert any("hapoel tel aviv" in a for a in aliases)

    def test_every_selectable_entity_has_search_aliases(self):
        catalog = build_catalog()
        for item in [*catalog.teams, *catalog.people]:
            assert item.aliases, f"{item.id} has no search aliases"
            assert item.display_he and item.display_en

    def test_curated_basketball_ordering(self):
        catalog = build_catalog()
        basketball = next(s for s in catalog.sports if s.id == "basketball")
        assert [c.id for c in basketball.competitions][:4] == [
            "comp:ibl", "comp:euroleague", "comp:nba", "comp:eurocup",
        ]

    def test_teams_carry_memberships_for_disclosure(self):
        """The picker's progressive disclosure needs team→competition
        relationships; Maccabi must expose both IBL and EuroLeague."""
        catalog = build_catalog()
        maccabi = next(t for t in catalog.teams if t.id == "team:maccabi_tlv_bb")
        assert "comp:ibl" in maccabi.memberships
        assert "comp:euroleague" in maccabi.memberships
        assert maccabi.domestic_competition == "comp:ibl"

    def test_people_carry_team_links(self):
        catalog = build_catalog()
        deni = next(p for p in catalog.people if p.id == "player:deni_avdija")
        assert deni.kind == "player"
        assert deni.team_id is not None
        assert deni.follow_scope == "player"


class TestCatalogApi:
    def test_requires_session(self, anonymous_client):
        assert anonymous_client.get("/api/taxonomy/catalog").status_code == 401

    def test_session_user_gets_catalog(self, user_client):
        response = user_client.get("/api/taxonomy/catalog")
        assert response.status_code == 200
        body = response.json()
        assert body["taxonomy_version"] == TAXONOMY_VERSION
        assert {s["id"] for s in body["sports"]} == {
            "basketball", "football", "tennis"}
        assert len(body["teams"]) > 0 and len(body["people"]) > 0
