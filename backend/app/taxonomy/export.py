"""
Canonical-taxonomy → frontend export (issue #29).

Single conversion function, used by both the generation script
(``backend/scripts/generate_taxonomy_export.py``) and the freshness-guard
test (``tests/test_taxonomy_export_freshness.py``), so there is exactly one
place that defines the export shape.

Contract: canonical-id-first, matching the entity_ids-first identity model
introduced by ArticleFacts (#28) and used by the relevance engine (#29).
``entities`` is keyed by taxonomy id (``team:*`` / ``player:*`` / ``coach:*``)
— the authoritative lookup path for post-ArticleFacts articles.
``legacy_name_to_id`` is a separate, explicitly-secondary compatibility index
used only by the legacy/pre-ArticleFacts fallback path. ``legacy_name`` is
never the primary key of this artifact.
"""

from app.taxonomy import COMPETITIONS, ENTITIES, TAXONOMY_VERSION
from app.taxonomy.identity import JERSEY_NUMBERS, TEAM_CODES, TEAM_COLORS


def build_taxonomy_export() -> dict:
    competitions = {
        c.id: {"sport": c.sport, "display_en": c.display_en}
        for c in COMPETITIONS.values()
    }
    entities = {
        e.id: {
            "legacy_name": e.legacy_name,
            "sport": e.sport,
            "kind": e.kind,
            "memberships": [comp_id for comp_id, _season in e.memberships],
        }
        for e in ENTITIES.values()
    }
    legacy_name_to_id = {e.legacy_name: e.id for e in ENTITIES.values()}
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "competitions": competitions,
        "entities": entities,
        "legacy_name_to_id": legacy_name_to_id,
    }


def build_identity_export() -> dict:
    """Team identity for the feed's team mark (#591, #592).

    Written to ``frontend/src/data/teamIdentity.generated.json``. Separate from
    the taxonomy-reach export, which feeds only the frozen local-mode engine.
    ``legacy_name_to_id`` exists because the feed payload still carries legacy
    names in ``article.entities``.
    """
    teams = {}
    people = {}
    for e in ENTITIES.values():
        if e.kind == "team":
            primary, secondary, _source = TEAM_COLORS.get(e.id, (None, None, None))
            teams[e.id] = {
                "sport": e.sport,
                "display_he": e.display_he,
                "primary": primary,
                "secondary": secondary,
                "code": TEAM_CODES.get(e.id),
            }
        elif e.team_id is not None:
            number = JERSEY_NUMBERS.get(e.id)
            people[e.id] = {
                "kind": e.kind,
                "display_he": e.display_he,
                "team_id": e.team_id,
                "number": number[0] if number else None,
            }
    legacy_name_to_id = {
        e.legacy_name: e.id for e in ENTITIES.values() if e.id in teams or e.id in people
    }
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "teams": teams,
        "people": people,
        "legacy_name_to_id": legacy_name_to_id,
    }
