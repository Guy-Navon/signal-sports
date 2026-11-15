import { expect, it } from "vitest";
import { searchResultPlayers, toggleResultPlayer } from "./resultsPlayersModel";
const catalog = [
  { entity_id: "player:deni_avdija", name: "דני אבדיה", name_en: "Deni Avdija", aliases: ["אבדיה"] },
  { entity_id: "player:roman_sorkin", name: "רומן סורקין", name_en: "Roman Sorkin", aliases: [] },
];
it("searches Hebrew, English and aliases, excluding selected players", () => {
  expect(searchResultPlayers(catalog, " AVDIJA ", [])).toEqual([catalog[0]]);
  expect(searchResultPlayers(catalog, "אבדיה", [catalog[0].entity_id])).toEqual([]);
  expect(searchResultPlayers(catalog, "רומן", [])).toEqual([catalog[1]]);
});
it("bounds suggestions and does not mutate choice arrays", () => {
  expect(searchResultPlayers(Array.from({ length: 30 }, (_, i) => ({ ...catalog[0], entity_id: `player:${i}` })), "", [])).toHaveLength(8);
  const ids = ["player:a"];
  expect(toggleResultPlayer(ids, "player:b")).toEqual(["player:a", "player:b"]);
  expect(toggleResultPlayer(ids, "player:a")).toEqual([]);
  expect(ids).toEqual(["player:a"]);
});
