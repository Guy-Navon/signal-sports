import { describe, expect, it } from "vitest";
import { numberInk, teamMarkFor } from "./teamMarkModel";

// Real legacy names and colours from teamIdentity.generated.json (#591).
const basketball = (entities) => teamMarkFor({ entities, sport: "basketball" });
/** The teams a mark shows; fails the test when it shows a glyph or nothing. */
function teamsOf(mark) {
  expect(mark?.kind).toBe("teams");
  return mark?.kind === "teams" ? mark.teams : [];
}
const teamIds = (mark) => teamsOf(mark).map((team) => team.teamId);

describe("teamMarkFor", () => {
  it("gives one followed club its jersey in the club's colours", () => {
    const teams = teamsOf(basketball(["Maccabi Tel Aviv Basketball"]));
    expect(teams).toHaveLength(1);
    expect(teams[0]).toMatchObject({
      teamId: "team:maccabi_tlv_bb",
      sport: "basketball",
      displayHe: "מכבי תל אביב",
      primary: "#FFD100",
      secondary: "#003DA5",
      number: null,
      personDisplayHe: null,
    });
  });

  it("maps a player to their club, with no number until one is verified", () => {
    const mark = basketball(["Deni Avdija"]);
    expect(teamIds(mark)).toEqual(["team:portland_blazers"]);
    expect(teamsOf(mark)[0]).toMatchObject({ number: null, personDisplayHe: "דני אבדיה" });
  });

  it("keeps one team when a player and their own club both appear", () => {
    const mark = basketball(["Deni Avdija", "Portland Trail Blazers"]);
    expect(teamIds(mark)).toEqual(["team:portland_blazers"]);
    expect(teamsOf(mark)[0].personDisplayHe).toBe("דני אבדיה");
    expect(teamsOf(basketball(["Portland Trail Blazers", "Deni Avdija"]))[0].personDisplayHe).toBe("דני אבדיה");
  });

  it("gives two clubs two jerseys, in the order they first appear", () => {
    expect(teamIds(basketball(["Deni Avdija", "LeBron James"]))).toEqual(["team:portland_blazers", "team:la_lakers"]);
  });

  it("falls back to the sport glyph for three or more teams", () => {
    // A real story, 2026-11-23.
    expect(basketball(["Maccabi Ramat Gan", "Hapoel Tel Aviv Basketball", "Maccabi Tel Aviv Basketball"]))
      .toEqual({ kind: "sport", sport: "basketball" });
  });

  it("falls back to the sport glyph for a team without colours", () => {
    expect(basketball(["Hapoel Holon"])).toEqual({ kind: "sport", sport: "basketball" });
    expect(basketball(["Hapoel Holon", "Maccabi Tel Aviv Basketball"])).toEqual({ kind: "sport", sport: "basketball" });
  });

  it("follows an implies_team player to the club", () => {
    expect(teamIds(basketball(["Roman Sorkin"]))).toEqual(["team:maccabi_tlv_bb"]);
  });

  it("shows the glyph with no team and abstains when the sport is unknown too", () => {
    expect(basketball([])).toEqual({ kind: "sport", sport: "basketball" });
    expect(teamMarkFor({ entities: [], sport: "football" })).toEqual({ kind: "sport", sport: "football" });
    expect(teamMarkFor({ entities: [], sport: "unknown" })).toBeNull();
    expect(teamMarkFor({ entities: ["Hapoel Holon"], sport: "tennis" })).toBeNull();
    expect(teamMarkFor({})).toBeNull();
  });

  it("ignores names the taxonomy does not know", () => {
    expect(basketball(["Nobody FC"])).toEqual({ kind: "sport", sport: "basketball" });
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
