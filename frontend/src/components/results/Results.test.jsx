import React from "react";
import { act, create } from "react-test-renderer";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Results from "@/pages/Results";
import ResultCard from "./ResultCard";

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

it("distinguishes no preferences from no games and keeps the interests destination", () => {
  render({ resultsHasPreferences: false });
  expect(JSON.stringify(view.toJSON())).toContain("עדיין לא בחרת מה מעניין אותך");
  expect(view.root.findByType("a").props.href).toBe("/interests");
  app.current.resultsHasPreferences = true;
  act(() => view.update(<MemoryRouter><Results /></MemoryRouter>));
  expect(JSON.stringify(view.toJSON())).toContain("אין תוצאות רלוונטיות כרגע");
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

it("keeps all supplied games grouped by Jerusalem day, newest first, during background refresh", () => {
  const game = (id, startTime) => ({
    id, startTime, competitionHe: "NBA", status: "scheduled",
    home: { name: "בית", score: null }, away: { name: "חוץ", score: null },
  });
  render({ resultsLoading: true, resultsGames: [
    game("undated", null), game("older", "2026-04-08T18:00:00Z"),
    game("newer", "2026-04-09T22:30:00Z"), game("same-day", "2026-04-10T10:00:00Z"),
  ] });
  expect(view.root.findAllByType(ResultCard).map((node) => node.props.game.id)).toEqual([
    "same-day", "newer", "older", "undated",
  ]);
  expect(view.root.findAllByType("h2").map((node) => node.children[0])).toEqual([
    expect.stringContaining("10"), expect.stringContaining("8"), "ללא תאריך",
  ]);
});
