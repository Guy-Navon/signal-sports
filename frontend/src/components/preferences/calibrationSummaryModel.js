import { SPORT_HE, LEAGUE_HE, ENTITY_HE } from "@/components/feed/storyLabels";

// The apply response is a saved profile, not a before/after diff. Only show
// calibration provenance; explicit follows and feedback learning are separate.
export function calibrationSummary(result) {
  return {
    scopes: (result?.profile_v2?.scope_affinities ?? []).filter((entry) => entry.source === "calibration"),
    events: (result?.profile_v2?.event_affinities ?? []).filter((entry) => entry.source === "calibration"),
    scopeCount: result?.applied_scope_affinities ?? null,
    eventCount: result?.applied_event_affinities ?? null,
  };
}

const scopeLabels = Object.entries({ ...SPORT_HE, ...LEAGUE_HE, ...ENTITY_HE });
const scopeKey = (label) => label.toLowerCase().replaceAll(" ", "_");

export function calibrationScopeLabel(targetId) {
  const name = targetId.replace(/^(sport|comp|team|player|coach):/, "");
  return scopeLabels.find(([key]) => scopeKey(key) === scopeKey(name))?.[1] ?? name.replaceAll("_", " ");
}
