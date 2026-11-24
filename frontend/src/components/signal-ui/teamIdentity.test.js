import { describe, expect, it } from "vitest";
import { teamIdentity } from "./teamIdentity.js";

describe("teamIdentity", () => {
  it("resolves a team by legacy name", () => {
    expect(teamIdentity("Maccabi Tel Aviv Basketball")).toEqual({
      teamId: "team:maccabi_tlv_bb",
      sport: "basketball",
      displayHe: "מכבי תל אביב",
      primary: "#FFD100",
      secondary: "#003DA5",
      code: "MTA",
      number: null,
      personId: null,
    });
  });

  it("resolves a followable player to their team, by legacy name or id", () => {
    const byName = teamIdentity("Deni Avdija");
    expect(byName).toEqual(teamIdentity("player:deni_avdija"));
    expect(byName).toEqual({
      teamId: "team:portland_blazers",
      sport: "basketball",
      displayHe: "פורטלנד בלייזרס",
      primary: "#E03A3E",
      secondary: "#000000",
      code: "POR",
      number: "8", // Wikipedia infobox, checked 2026-11-24
      personId: "player:deni_avdija",
    });
  });

  it("resolves implies_team players and coaches to their club without a number", () => {
    for (const ref of ["Roman Sorkin", "Oded Katash"]) {
      const result = teamIdentity(ref);
      expect(result?.teamId).toBe("team:maccabi_tlv_bb");
      expect(result?.number).toBeNull();
    }
  });

  it("returns null for an unknown ref and null colours for a pending team", () => {
    expect(teamIdentity("Nobody FC")).toBeNull();
    expect(teamIdentity("team:paris_bb")?.primary).toBeNull();
    expect(teamIdentity("team:paris_bb")?.code).toBe("PRS");
  });

});
