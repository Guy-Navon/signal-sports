import { expect, it } from "vitest";
import { calibrationSummary, calibrationScopeLabel } from "./calibrationSummaryModel";

it("reads saved calibration levels without claiming explicit or learned entries changed", () => {
  const scopes = [
    { source: "explicit", target_id: "comp:nba", level: 2 },
    { source: "calibration", target_id: "comp:nba", level: 1 },
    { source: "calibration", target_id: "sport:tennis", level: -1 },
    { source: "learned", target_id: "team:a", level: 2 },
  ];
  const events = [
    { source: "calibration", event_type: "injury", scope_ref: "comp:nba", delta: 1 },
    { source: "explicit", event_type: "signing", delta: 2 },
  ];
  const result = { applied_scope_affinities: 2, applied_event_affinities: 1,
    profile_v2: { scope_affinities: scopes, event_affinities: events } };
  const before = JSON.stringify(result);
  expect(calibrationSummary(result)).toEqual({ scopes: [scopes[1], scopes[2]], events: [events[0]], scopeCount: 2, eventCount: 1 });
  expect(JSON.stringify(result)).toBe(before);
});

it("keeps authoritative zero counts and handles an empty or unavailable profile honestly", () => {
  expect(calibrationSummary({ applied_scope_affinities: 0, applied_event_affinities: 0 }))
    .toEqual({ scopes: [], events: [], scopeCount: 0, eventCount: 0 });
  expect(calibrationSummary(null)).toEqual({ scopes: [], events: [], scopeCount: null, eventCount: null });
});

it("reuses existing reader labels and keeps unknown scopes identifiable", () => {
  expect(calibrationScopeLabel("tennis")).toBe("טניס");
  expect(calibrationScopeLabel("sport:basketball")).toBe("כדורסל");
  expect(calibrationScopeLabel("comp:nba")).toBe("NBA");
  expect(calibrationScopeLabel("player:deni_avdija")).toBe("דני אבדיה");
  expect(calibrationScopeLabel("team:unlisted_club")).toBe("unlisted club");
});
