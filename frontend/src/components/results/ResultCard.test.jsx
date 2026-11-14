import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it } from "vitest";
import ResultCard from "./ResultCard";

const game = {
  id: "mixed", competitionHe: "יורוקאפ", stage: "פלייאוף",
  startTime: "2026-04-10T02:00:00Z", status: "final", winner: "away",
  home: { name: "London Lions", score: 89 },
  away: { name: "הפועל ירושלים", score: 85 },
};
let view;
afterEach(() => { if (view) act(() => view.unmount()); });
const render = (overrides = {}) => {
  act(() => { view = create(<ResultCard game={{ ...game, ...overrides }} />); });
};

it("isolates mixed-direction team names and scores, and keeps competition, stage and Jerusalem time", () => {
  render();
  expect(view.root.findAllByType("bdi").map((node) => node.children.join(""))).toEqual(
    expect.arrayContaining(["London Lions", "הפועל ירושלים", "יורוקאפ", "פלייאוף"])
  );
  for (const node of view.root.findAllByType("bdi")) expect(node.props.dir).toBe("auto");
  const time = view.root.findByType("time");
  expect(time.props.dateTime).toBe(game.startTime);
  expect(time.props.dir).toBe("ltr");
  expect(time.children).toEqual(["05:00"]);
  const scores = view.root.findAllByProps({ className: "sg-result__score" });
  expect(scores.map((node) => node.children.join(""))).toEqual(["89", "85"]);
  expect(scores.every((node) => node.props.dir === "ltr")).toBe(true);
});

it("emphasizes only the declared winner, even when the score suggests otherwise", () => {
  render();
  const winner = view.root.findByProps({ className: "sg-result__team sg-result__team--winner" });
  expect(winner.findByType("bdi").children).toEqual(["הפועל ירושלים"]);
});

it.each(["live", "scheduled", "postponed", "cancelled"])("retains the %s label and never declares an unfinished winner", (status) => {
  render({ status });
  expect(view.root.findAllByProps({ className: "sg-result__team sg-result__team--winner" })).toHaveLength(0);
  const labels = { live: "משחק חי", scheduled: "עתידי", postponed: "נדחה", cancelled: "בוטל" };
  expect(JSON.stringify(view.toJSON())).toContain(labels[status]);
});

it("shows a zero score, omits incomplete score pairs and leaves draws without winner emphasis", () => {
  render({ home: { name: "בית", score: 0 }, away: { name: "חוץ", score: 0 }, winner: "draw" });
  expect(view.root.findAllByProps({ className: "sg-result__score" }).map((node) => node.children)).toEqual([["0"], ["0"]]);
  expect(view.root.findAllByProps({ className: "sg-result__team sg-result__team--winner" })).toHaveLength(0);
  act(() => view.update(<ResultCard game={{ ...game, away: { name: "חוץ", score: null } }} />));
  expect(view.root.findAllByProps({ className: "sg-result__score" })).toHaveLength(0);
});
