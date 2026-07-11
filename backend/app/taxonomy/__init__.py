"""
Canonical taxonomy for Signal Sports — single source of truth for entities
(teams, players, coaches) and competitions.

Design principles (Signal Intelligence Architecture v2, PR 1):
- Every entity has a stable canonical ID (``team:*``, ``player:*``, ``coach:*``)
  and a ``legacy_name`` — the display string the rest of the system already
  uses (``Article.entities``, profile topics, relevance engine). PR 1 keeps
  all public contracts on legacy names; IDs become persistable in PR 2.
- Club family names ("מכבי", "הפועל", "עירוני", 'בית"ר') are NEVER aliases of
  any specific team. A bare family mention resolves to nothing.
- Alias matching is longest-match-wins; ambiguous mentions (same alias shared
  by entities of different sports, no sport evidence) abstain rather than guess.
- The registry is code-config data, versioned via TAXONOMY_VERSION. Integrity
  is enforced by ``validate_registry()`` (run in tests).
"""

from app.taxonomy.competitions import COMPETITIONS, Competition
from app.taxonomy.entities import (
    ENTITIES,
    FAMILY_NAMES,
    TaxonomyEntity,
    entities_by_sport,
    entity_by_id,
    entity_by_legacy_name,
    legacy_sport,
)
from app.taxonomy.resolver import (
    EntityResolution,
    is_cross_sport_ambiguous,
    resolve_entities,
    resolve_mention,
)
from app.taxonomy.integrity import validate_registry
from app.taxonomy.policy import (
    NON_SELECTABLE_COMPETITIONS,
    SELECTABLE_SPORTS,
    competition_selectable,
    scope_target_selectable,
)

TAXONOMY_VERSION = 1

__all__ = [
    "TAXONOMY_VERSION",
    "Competition",
    "COMPETITIONS",
    "TaxonomyEntity",
    "ENTITIES",
    "FAMILY_NAMES",
    "entity_by_id",
    "entity_by_legacy_name",
    "is_cross_sport_ambiguous",
    "entities_by_sport",
    "legacy_sport",
    "EntityResolution",
    "resolve_entities",
    "resolve_mention",
    "validate_registry",
    "NON_SELECTABLE_COMPETITIONS",
    "SELECTABLE_SPORTS",
    "competition_selectable",
    "scope_target_selectable",
]
