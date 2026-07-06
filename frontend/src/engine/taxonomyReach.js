/**
 * Thin derived-lookup layer over the generated taxonomy artifact (issue #29).
 *
 * `taxonomyReach.generated.json` is produced by
 * `backend/scripts/generate_taxonomy_export.py` from the canonical Python
 * registry (`backend/app/taxonomy/`) — this file holds NO hand-authored
 * entity/competition data of its own, only lookup functions over the
 * generated JSON. `backend/tests/test_taxonomy_export_freshness.py` fails if
 * the JSON drifts from the live registry.
 *
 * Canonical-id-first, matching the entity_ids-first identity contract:
 * `taxonomyData.entities` is keyed by taxonomy id; `legacy_name_to_id` is a
 * secondary compatibility index for legacy (pre-ArticleFacts) articles only.
 */
import taxonomyData from "@/data/taxonomyReach.generated.json";

export function idForLegacyName(legacyName) {
  return taxonomyData.legacy_name_to_id[legacyName] ?? null;
}

export function legacyNameForId(entityId) {
  return taxonomyData.entities[entityId]?.legacy_name ?? null;
}

export function competitionDisplayName(compId) {
  return taxonomyData.competitions[compId]?.display_en ?? null;
}

function addReach(reach, entityId) {
  const entity = taxonomyData.entities[entityId];
  if (!entity) return;
  for (const compId of entity.memberships) {
    const comp = taxonomyData.competitions[compId];
    if (comp && !(comp.display_en in reach)) {
      reach[comp.display_en] = compId;
    }
  }
}

/** Competition display name -> comp id, via canonical entity ids (post-ArticleFacts, authoritative). */
export function reachForEntityIds(entityIds = []) {
  const reach = {};
  for (const id of entityIds) addReach(reach, id);
  return reach;
}

/** Competition display name -> comp id, via legacy display-name strings (pre-ArticleFacts fallback only). */
export function reachForLegacyNames(legacyNames = []) {
  const reach = {};
  for (const name of legacyNames) {
    const id = idForLegacyName(name);
    if (id) addReach(reach, id);
  }
  return reach;
}
