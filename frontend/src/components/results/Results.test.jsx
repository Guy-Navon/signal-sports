import React from "react";
import { act, create } from "react-test-renderer";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Results from "@/pages/Results";
import ResultRow from "./ResultRow";

const app = vi.hoisted(() => ({ current: {} }));
vi.mock("@/context/AppContext", () => ({ useApp: () => app.current }));
let view;
beforeEach(() => {
  app.current = {
    resultsGames: [], resultsHasPreferences: true, resultsLoading: false,
    resultsError: null, refreshResults: vi.fn(), isBackendMode: true,
  };
});
afterEach(() => { if (view) act(() => view.unmount()); });
const render = (overrides = {}) => {
  Object.assign(app.current, overrides);
  act(() => { view = create(<MemoryRouter><Results /></MemoryRouter>); });
};

it("distinguishes no preferences from no games and links to Preferences", () => {
  render({ resultsHasPreferences: false });
  expect(JSON.stringify(view.toJSON())).toContain("עדיין לא בחרת מה מעניין אותך");
  expect(view.root.findByType("a").props.href).toBe("/preferences");
  app.current.resultsHasPreferences = true;
  act(() => view.update(<MemoryRouter><Results /></MemoryRouter>));
  expect(JSON.stringify(view.toJSON())).toContain("אין משחקים להיום");
  expect(view.root.findAllByType("a")).toHaveLength(0);
});

it("keeps the retry action and gives errors precedence over empty preferences", () => {
  render({ resultsError: "offline", resultsHasPreferences: false });
  expect(JSON.stringify(view.toJSON())).toContain("לא הצלחנו לטעון את התוצאות");
  act(() => view.root.findByType("button").props.onClick());
  expect(app.current.refreshResults).toHaveBeenCalledOnce();
});

it("announces initial backend loading before the empty and error branches", () => {
  render({ resultsLoading: true, resultsHasPreferences: false, resultsError: "offline" });
  expect(view.root.findByProps({ role: "status" }).children.join("")).toContain("טוען תוצאות");
  expect(JSON.stringify(view.toJSON())).not.toContain("עדיין לא בחרת");
  expect(view.root.findAllByType("button")).toHaveLength(0);
});

it("keeps Jerusalem day groups, newest first within a day, undated last, during background refresh", () => {
  const game = (id, startTime) => ({
    id, startTime, competitionId: "comp:nba", sport: "basketball", competitionHe: "NBA", status: "final", localDate: null,
    home: { name: "בית", score: 1 }, away: { name: "חוץ", score: 0 }, leaders: [], chosenPlayerLines: [], detailAvailable: false,
  });
  render({ resultsLoading: true, resultsGames: [
    game("undated", null), game("older", "2026-04-08T18:00:00Z"),
    game("newer", "2026-04-09T22:30:00Z"), game("same-day", "2026-04-10T10:00:00Z"),
  ] });
  expect(view.root.findAllByType(ResultRow).map((node) => node.props.game.id)).toEqual([
    "same-day", "newer", "older", "undated",
  ]);
  const heads = view.root.findAll((node) => node.props.className === "sr-day__head" && typeof node.type === "string");
  expect(heads).toHaveLength(3);
  expect(heads.at(-1).findByType("span").children).toEqual(["ללא תאריך"]);
});
