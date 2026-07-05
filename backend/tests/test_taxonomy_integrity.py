"""
Taxonomy registry integrity — pure data invariants.

Every failure here means the registry DATA is wrong, not the code.
These invariants are the architecture contract of the taxonomy foundation
(Signal Intelligence Architecture v2, PR 1).
"""

from app.taxonomy import (
    COMPETITIONS,
    ENTITIES,
    FAMILY_NAMES,
    entity_by_legacy_name,
    validate_registry,
)


class TestRegistryIntegrity:
    def test_registry_is_valid(self):
        errors = validate_registry()
        assert errors == [], "\n".join(errors)

    def test_no_family_name_is_a_direct_alias(self):
        family_lower = {f.lower() for f in FAMILY_NAMES}
        for entity in ENTITIES.values():
            for alias in entity.aliases:
                assert alias.lower() not in family_lower, (
                    f"{entity.id}: family name {alias!r} must not be a team alias"
                )

    def test_all_memberships_reference_existing_competitions(self):
        for entity in ENTITIES.values():
            for comp_id, _season in entity.memberships:
                assert comp_id in COMPETITIONS, f"{entity.id} → {comp_id}"

    def test_entity_sport_matches_competition_sport(self):
        for entity in ENTITIES.values():
            for comp_id, _season in entity.memberships:
                comp = COMPETITIONS[comp_id]
                assert comp.sport == entity.sport, (
                    f"{entity.id} ({entity.sport}) in {comp.id} ({comp.sport})"
                )

    def test_legacy_names_unique(self):
        seen = {}
        for entity in ENTITIES.values():
            assert entity.legacy_name not in seen, (
                f"{entity.legacy_name!r} used by {entity.id} and {seen[entity.legacy_name]}"
            )
            seen[entity.legacy_name] = entity.id

    def test_shared_aliases_only_across_sports(self):
        owners: dict[str, list[str]] = {}
        for entity in ENTITIES.values():
            for alias in entity.aliases:
                owners.setdefault(alias.lower(), []).append(entity.id)
        for alias, ids in owners.items():
            if len(ids) > 1:
                sports = {ENTITIES[i].sport for i in ids}
                assert len(sports) == len(ids), (
                    f"alias {alias!r} shared by same-sport entities: {ids}"
                )

    def test_cross_sport_club_pairs_exist(self):
        # The distinct-entity requirement: both sides of each Israeli
        # multi-sport club exist as separate canonical entities.
        for bb, fc in [
            ("Maccabi Tel Aviv Basketball", "Maccabi Tel Aviv Football"),
            ("Hapoel Tel Aviv Basketball", "Hapoel Tel Aviv Football"),
            ("Hapoel Jerusalem Basketball", "Hapoel Jerusalem Football"),
        ]:
            bb_entity = entity_by_legacy_name(bb)
            fc_entity = entity_by_legacy_name(fc)
            assert bb_entity is not None and bb_entity.sport == "basketball"
            assert fc_entity is not None and fc_entity.sport == "football"

    def test_screenshot_clubs_registered_and_distinct(self):
        ramat_gan = entity_by_legacy_name("Maccabi Ramat Gan")
        kiryat_gat = entity_by_legacy_name("Maccabi Kiryat Gat")
        maccabi_tlv = entity_by_legacy_name("Maccabi Tel Aviv Basketball")
        assert ramat_gan is not None and ramat_gan.id != maccabi_tlv.id
        assert kiryat_gat is not None and kiryat_gat.id != maccabi_tlv.id

    def test_domestic_competition_is_in_memberships(self):
        for entity in ENTITIES.values():
            if entity.domestic_competition:
                assert entity.domestic_competition in {
                    c for c, _ in entity.memberships
                }, entity.id

    def test_maccabi_tlv_memberships_support_dual_competition(self):
        # The competition model (PR 2/3) relies on teams carrying both domestic
        # and international memberships from day one.
        mta = entity_by_legacy_name("Maccabi Tel Aviv Basketball")
        comp_ids = {c for c, _ in mta.memberships}
        assert "comp:ibl" in comp_ids
        assert "comp:euroleague" in comp_ids
