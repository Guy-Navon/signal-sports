import { expect, it } from "vitest";
import fixture from "./resultsFixtures.json";
it("uses the saved real game payloads without changing their scores or Deni's line", () => {
  const game = id => fixture.games.find(g => g.competition_id === id && g.status === "final");
  expect([game("comp:ibl").home.score, game("comp:ibl").away.score]).toEqual([87, 105]);
  expect([game("comp:euroleague").home.score, game("comp:euroleague").away.score]).toEqual([80, 73]);
  expect([game("comp:ligat_haal").home.score, game("comp:ligat_haal").away.score]).toEqual([2, 2]);
  expect(game("comp:ligat_haal").leaders).toHaveLength(4);
  const deni = game("comp:nba").chosen_player_lines.find(p => p.entity_id === "player:deni_avdija");
  expect(deni.name).toBe("דני אבדיה"); expect(deni.stats.points).toBe(34);
  expect(fixture.sources).toHaveLength(4);
});
