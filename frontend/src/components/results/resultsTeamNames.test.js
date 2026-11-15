import { expect, it } from "vitest";
import { NBA_SHORT_NAMES, shortTeamName } from "./resultsTeamNames";

const NBA_IDS = ["atlanta_hawks", "boston_celtics", "brooklyn_nets", "charlotte_hornets", "chicago_bulls", "cleveland_cavaliers",
  "dallas_mavericks", "denver_nuggets", "detroit_pistons", "golden_state_warriors", "houston_rockets", "indiana_pacers", "la_clippers",
  "la_lakers", "memphis_grizzlies", "miami_heat", "milwaukee_bucks", "minnesota_timberwolves", "new_orleans_pelicans", "ny_knicks",
  "okc_thunder", "orlando_magic", "philadelphia_76ers", "phoenix_suns", "portland_blazers", "sacramento_kings", "san_antonio_spurs",
  "toronto_raptors", "utah_jazz", "washington_wizards"].map(id => `team:${id}`);

it("covers exactly the 30 NBA team ids, with distinct non-empty names", () => {
  expect(Object.keys(NBA_SHORT_NAMES).sort()).toEqual([...NBA_IDS].sort());
  const names = Object.values(NBA_SHORT_NAMES);
  expect(names.every(n => typeof n === "string" && n.length > 0)).toBe(true);
  expect(new Set(names).size).toBe(30);
});
it("uses the short names Guy chose and never collapses the two Los Angeles teams", () => {
  const short = id => shortTeamName({ id: `team:${id}`, name: "x" });
  expect(short("portland_blazers")).toBe("פורטלנד");
  expect(short("okc_thunder")).toBe("אוקלהומה סיטי");
  expect(short("golden_state_warriors")).toBe("גולדן סטייט");
  expect(short("la_clippers")).toBe("קליפרס");
  expect(short("la_lakers")).toBe("לייקרס");
  expect(short("ny_knicks")).toBe("ניו יורק");
  expect(short("brooklyn_nets")).toBe("ברוקלין");
});
it("falls back to the full name for any other team and never shortens by heuristic", () => {
  expect(shortTeamName({ id: "team:maccabi_tlv_bb", name: "מכבי תל אביב" })).toBe("מכבי תל אביב");
  expect(shortTeamName({ id: null, name: "Some Club FC" })).toBe("Some Club FC");
  expect(shortTeamName({ id: "team:unknown_nba", name: "לוס אנג'לס משהו" })).toBe("לוס אנג'לס משהו");
  expect(shortTeamName(null)).toBe("");
});
