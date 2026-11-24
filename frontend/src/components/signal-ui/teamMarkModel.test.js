import { describe, expect, it } from "vitest";
import { numberInk, teamMarkFor } from "./teamMarkModel";

// Real legacy names, colours, codes and numbers from teamIdentity.generated.json
// (#591, #601).
const basketball = (entities) => teamMarkFor({ entities });

/** The teams a mark names; fails the test when the mark abstains. */
function teamsOf(mark) {
  expect(mark).not.toBeNull();
  return mark?.teams ?? [];
}
const teamIds = (mark) => teamsOf(mark).map((team) => team.teamId);

describe("teamMarkFor", () => {
  it("gives one club its colours and code", () => {
    const teams = teamsOf(basketball(["Maccabi Tel Aviv Basketball"]));
    expect(teams).toHaveLength(1);
    expect(teams[0]).toEqual({
      teamId: "team:maccabi_tlv_bb",
      sport: "basketball",
      displayHe: "מכבי תל אביב",
      primary: "#FFD100",
      secondary: "#003DA5",
      code: "MTA",
      number: null,
      personDisplayHe: null,
    });
  });

  it("maps a player to their club and carries the player's name and verified number", () => {
    const mark = basketball(["Deni Avdija"]);
    expect(teamIds(mark)).toEqual(["team:portland_blazers"]);
    expect(teamsOf(mark)[0]).toMatchObject({ code: "POR", number: "8", personDisplayHe: "דני אבדיה" });
  });

  it("keeps one team when a player and their own club both appear, in either order", () => {
    for (const entities of [["Deni Avdija", "Portland Trail Blazers"], ["Portland Trail Blazers", "Deni Avdija"]]) {
      const mark = basketball(entities);
      expect(teamIds(mark)).toEqual(["team:portland_blazers"]);
      expect(teamsOf(mark)[0]).toMatchObject({ number: "8", personDisplayHe: "דני אבדיה" });
    }
  });

  it("names both of two clubs, the first-seen one first", () => {
    const mark = basketball(["Deni Avdija", "LeBron James"]);
    expect(teamIds(mark)).toEqual(["team:portland_blazers", "team:la_lakers"]);
    expect(teamsOf(mark)[1]).toMatchObject({ number: null, personDisplayHe: "לברון ג'יימס" });
  });

  it("abstains for three or more teams", () => {
    // A real story, 2026-11-23.
    expect(basketball(["Maccabi Ramat Gan", "Hapoel Tel Aviv Basketball", "Maccabi Tel Aviv Basketball"])).toBeNull();
  });

  it("abstains when any chosen team has no colours", () => {
    expect(basketball(["Bnei Herzliya"])).toBeNull();
    expect(basketball(["Bnei Herzliya", "Maccabi Tel Aviv Basketball"])).toBeNull();
  });

  it("follows an implies_team player to the club", () => {
    expect(teamIds(basketball(["Roman Sorkin"]))).toEqual(["team:maccabi_tlv_bb"]);
  });

  it("abstains with no team (no sport fallback) and never reads names it does not know", () => {
    expect(basketball([])).toBeNull();
    expect(basketball(["Nobody FC"])).toBeNull();
    expect(teamMarkFor({})).toBeNull();
  });
});

describe("numberInk", () => {
  it("keeps the secondary colour when it contrasts at least 3:1 with the body", () => {
    expect(numberInk("#FFD100", "#003DA5")).toBe("#003DA5");
    expect(numberInk("#E03A3E", "#000000")).toBe("#000000");
  });

  it("otherwise picks whichever of white and black contrasts more", () => {
    expect(numberInk("#C8102E", "#1D42BA")).toBe("#FFFFFF");
    expect(numberInk("#004D98", "#A50044")).toBe("#FFFFFF");
    expect(numberInk("#FFD100", "#FFE000")).toBe("#000000");
    expect(numberInk("#004D98", null)).toBe("#FFFFFF");
  });
});
