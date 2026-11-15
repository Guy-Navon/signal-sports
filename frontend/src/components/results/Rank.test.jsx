import React from "react";
import { create } from "react-test-renderer";
import { expect, it } from "vitest";
import Rank from "./Rank";
import ResultTile from "./ResultTile";

const flat = (n) => (typeof n === "string" ? n : (n.children ?? []).map(flat).join(""));
const side = (id, name, rank) => ({ id, name, score: 100, rank, isWinner: false });

it("keeps the parentheses outside and isolates only the digits", () => {
  const json = create(<Rank value={17} />).toJSON();
  expect(json.props.className).toBe("sr-rank");
  expect(flat(json)).toBe("(17)");
  expect(json.children[0]).toBe("(");
  expect(json.children[1].type).toBe("bdi");
  expect(json.children[1].props.dir).toBe("ltr");
  expect(json.children[2]).toBe(")");
});
it("renders nothing without a rank", () => {
  expect(create(<Rank value={null} />).toJSON()).toBeNull();
});
it("sits beside, not inside, the truncating name in a tile", () => {
  const game = { id: "g", localDate: "2026-11-14", status: "final", winner: "home", sport: "basketball", competitionHe: "יורוליג",
    home: side("team:m", "מכבי תל אביב", 17), away: side("team:o", "אולימפיאקוס", null), detailAvailable: false };
  const tile = create(<ResultTile entry={{ game, verdict: null, chosen: null }} followed={new Set()} dayLabel="אתמול" onOpen={() => {}} />).root;
  const name = tile.findAll((n) => n.props.className === "sr-tile__name")[0];
  expect(name.findAll((n) => n.props.className === "sr-rank")).toHaveLength(0);
  expect(tile.findAll((n) => n.props.className === "sr-rank")).toHaveLength(1);
});
