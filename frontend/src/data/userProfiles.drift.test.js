/**
 * Profile drift guard (issue #29) — frontend mirror of
 * backend/tests/test_profile_drift_guard.py.
 *
 * docs/fixtures/profile_parity.json is the single canonical snapshot of
 * every relevance-driving field on every shipped topic for both built-in
 * profiles. This test normalizes userProfiles.js the same way the backend
 * test normalizes SEED_PROFILES and asserts equality against that one file.
 * Either side drifting from the snapshot fails that side's test.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { userProfiles } from "@/data/userProfiles";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SNAPSHOT_PATH = path.resolve(__dirname, "../../../docs/fixtures/profile_parity.json");

function normalizeTopic(t) {
  return {
    topic_id: t.topicId,
    sport: t.sport,
    scope: t.scope ?? null,
    priority: t.priority,
    mode: t.mode,
    leagues: [...(t.leagues || [])].sort(),
    entities: [...(t.entities || [])].sort(),
    event_rules: sortedObject(t.eventRules || {}),
    entity_event_rules: t.entityEventRules
      ? sortedObjectOfObjects(t.entityEventRules)
      : null
  };
}

function sortedObject(obj) {
  const out = {};
  for (const key of Object.keys(obj).sort()) out[key] = obj[key];
  return out;
}

function sortedObjectOfObjects(obj) {
  const out = {};
  for (const key of Object.keys(obj).sort()) out[key] = sortedObject(obj[key]);
  return out;
}

function loadSnapshot() {
  return JSON.parse(readFileSync(SNAPSHOT_PATH, "utf-8"));
}

describe("profile drift guard", () => {
  it("guy profile matches the parity snapshot", () => {
    const normalized = userProfiles.guy.topics.map(normalizeTopic);
    const snapshot = loadSnapshot();
    expect(normalized).toEqual(snapshot.guy);
  });

  it("casual_deni_fan profile matches the parity snapshot", () => {
    const normalized = userProfiles.casual_deni_fan.topics.map(normalizeTopic);
    const snapshot = loadSnapshot();
    expect(normalized).toEqual(snapshot.casual_deni_fan);
  });

  it("snapshot covers every shipped topic", () => {
    const snapshot = loadSnapshot();
    expect(new Set(userProfiles.guy.topics.map(t => t.topicId))).toEqual(
      new Set(snapshot.guy.map(t => t.topic_id))
    );
    expect(new Set(userProfiles.casual_deni_fan.topics.map(t => t.topicId))).toEqual(
      new Set(snapshot.casual_deni_fan.map(t => t.topic_id))
    );
  });
});
