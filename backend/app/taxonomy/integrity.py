"""
Registry integrity validation — pure data checks, enforced by tests.

Every rule here is an architecture invariant of the taxonomy:
violating any of them means the registry data is wrong, not the code.
"""

from app.taxonomy.competitions import COMPETITIONS
from app.taxonomy.entities import ENTITIES, FAMILY_NAMES


def validate_registry() -> list[str]:
    """Return a list of violation messages; empty list means the registry is valid."""
    errors: list[str] = []
    seen_legacy: dict[str, str] = {}

    for entity in ENTITIES.values():
        # Memberships must reference existing competitions of the same sport.
        for comp_id, _season in entity.memberships:
            comp = COMPETITIONS.get(comp_id)
            if comp is None:
                errors.append(f"{entity.id}: membership {comp_id} does not exist")
            elif comp.sport != entity.sport:
                errors.append(
                    f"{entity.id} ({entity.sport}): membership {comp_id} is a {comp.sport} competition"
                )

        # domestic_competition must exist, match sport, and appear in memberships.
        if entity.domestic_competition is not None:
            comp = COMPETITIONS.get(entity.domestic_competition)
            if comp is None:
                errors.append(f"{entity.id}: domestic {entity.domestic_competition} does not exist")
            else:
                if comp.sport != entity.sport:
                    errors.append(
                        f"{entity.id} ({entity.sport}): domestic {comp.id} is a {comp.sport} competition"
                    )
                if entity.domestic_competition not in {c for c, _ in entity.memberships}:
                    errors.append(f"{entity.id}: domestic competition missing from memberships")

        # No family name may be a direct alias of a specific team.
        family_lower = {f.lower() for f in FAMILY_NAMES}
        for alias in entity.aliases:
            if alias.lower() in family_lower:
                errors.append(f"{entity.id}: family name {alias!r} used as a direct alias")

        # Legacy display names must be unique (they are the Article.entities contract).
        if entity.legacy_name in seen_legacy:
            errors.append(
                f"{entity.id}: legacy_name {entity.legacy_name!r} already used by {seen_legacy[entity.legacy_name]}"
            )
        seen_legacy[entity.legacy_name] = entity.id

        # Players/coaches with a team link must point at an existing team of the same sport.
        if entity.team_id is not None:
            team = ENTITIES.get(entity.team_id)
            if team is None:
                errors.append(f"{entity.id}: team_id {entity.team_id} does not exist")
            elif team.sport != entity.sport:
                errors.append(f"{entity.id}: team {team.id} sport mismatch")

    # An alias may be shared only by entities of DIFFERENT sports (the
    # cross-sport ambiguity mechanism). Same-sport alias collisions are data bugs.
    alias_owners: dict[str, list[str]] = {}
    for entity in ENTITIES.values():
        for alias in entity.aliases:
            alias_owners.setdefault(alias.lower(), []).append(entity.id)
    for alias, owners in alias_owners.items():
        if len(owners) > 1:
            sports = {ENTITIES[o].sport for o in owners}
            if len(sports) != len(owners):
                errors.append(f"alias {alias!r} shared by same-sport entities: {owners}")

    return errors
