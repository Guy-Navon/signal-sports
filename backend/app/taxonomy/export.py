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


def build_taxonomy_export() -> dict:
    competitions = {
        c.id: {"sport": c.sport, "display_en": c.display_en}
        for c in COMPETITIONS.values()
    }
    entities = {
        e.id: {
            "legacy_name": e.legacy_name,
            "sport": e.sport,
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
