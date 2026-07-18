import { describe, it, expect } from "vitest";
import {
  deriveFollows,
  isRelevant,
  filterRelevant,
  hasAnyFollows,
} from "./resultsRelevance";
import { userProfiles } from "@/data/userProfiles";
import { mockResults } from "@/data/mockResults";
import { normalizeResultFromApi } from "./resultsModel";

const games = mockResults.map(normalizeResultFromApi);
const byId = (id) => games.find((g) => g.id === id);

describe("deriveFollows", () => {
  it("derives Guy's followed competitions and teams", () => {
    const f = deriveFollows(userProfiles.guy);
    expect(f.competitionIds.has("comp:nba")).toBe(true);
    expect(f.competitionIds.has("comp:euroleague")).toBe(true);
    expect(f.competitionIds.has("comp:ibl")).toBe(true);
    expect(f.competitionIds.has("comp:acb")).toBe(false); // high-importance-only, not broad
    expect(f.teamIds.has("team:maccabi_tlv_bb")).toBe(true);
    expect(f.teamIds.has("team:portland_blazers")).toBe(true); // via Deni Avdija
  });

  it("derives only the followed player's team for the casual Deni fan", () => {
    const f = deriveFollows(userProfiles.casual_deni_fan);
    expect(f.competitionIds.size).toBe(0);
    expect([...f.teamIds]).toEqual(["team:portland_blazers"]);
  });
});

describe("isRelevant", () => {
  const follows = { teamIds: new Set(["team:portland_blazers"]), competitionIds: new Set(["comp:euroleague"]) };

  it("is relevant via a followed team", () => {
    expect(isRelevant(byId("game_mock_nba_por_was"), follows)).toBe(true);
  });

  it("is relevant via a followed competition", () => {
    expect(isRelevant(byId("game_mock_el_oly_pao"), follows)).toBe(true);
  });

  it("excludes an unrelated game", () => {
    expect(isRelevant(byId("game_mock_acb_bar_bas"), follows)).toBe(false);
    expect(isRelevant(byId("game_mock_nba_lal_bos"), follows)).toBe(false);
  });
});

describe("filterRelevant + isolation", () => {
  it("Guy sees NBA/EuroLeague/IBL but never Spanish ACB", () => {
    const visible = filterRelevant(games, deriveFollows(userProfiles.guy));
    const comps = new Set(visible.map((g) => g.competitionId));
    expect(comps.has("comp:nba")).toBe(true);
    expect(comps.has("comp:euroleague")).toBe(true);
    expect(comps.has("comp:acb")).toBe(false);
  });

  it("Deni fan sees strictly fewer games than Guy (isolation)", () => {
    const guy = new Set(filterRelevant(games, deriveFollows(userProfiles.guy)).map((g) => g.id));
    const deni = new Set(filterRelevant(games, deriveFollows(userProfiles.casual_deni_fan)).map((g) => g.id));
    expect(deni.size).toBeGreaterThan(0);
    expect([...deni].every((id) => guy.has(id))).toBe(true);
    expect(deni.size).toBeLessThan(guy.size);
  });

  it("a preference change changes visible results", () => {
    const noFollows = { teamIds: new Set(), competitionIds: new Set() };
    expect(filterRelevant(games, noFollows)).toHaveLength(0);
    const nbaOnly = { teamIds: new Set(), competitionIds: new Set(["comp:nba"]) };
    const visible = filterRelevant(games, nbaOnly);
    expect(new Set(visible.map((g) => g.competitionId))).toEqual(new Set(["comp:nba"]));
  });
});

describe("hasAnyFollows", () => {
  it("reflects whether there are any follows", () => {
    expect(hasAnyFollows({ teamIds: new Set(), competitionIds: new Set() })).toBe(false);
    expect(hasAnyFollows({ teamIds: new Set(["x"]), competitionIds: new Set() })).toBe(true);
  });
});
