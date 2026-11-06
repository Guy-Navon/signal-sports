import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import Debug from "./Debug";

const state = vi.hoisted(() => ({ isBackendMode: false, demoLoads: 0 }));
vi.mock("@/context/AppContext", () => ({
  useApp: () => ({
    debugItems: [],
    activeProfile: { displayName: "Guy" },
    activeProfileId: "guy",
    isBackendMode: state.isBackendMode,
  }),
  useEngineTraceVisible: () => true,
}));
// Counts real loads of the lazy demo module: its factory runs only on import.
vi.mock("@/components/debug/DemoProfileComparison", () => {
  state.demoLoads += 1;
  return { default: () => <p>טבלת ההדגמה</p> };
});

const COMPARE_TAB = "השוואת פרופילים";
const DEMO_ONLY = "השוואת פרופילים זמינה רק במצב הדגמה.";
const LEGEND = "השוואה בין כל הפרופילים לכל כתבה";

let renderer;
afterEach(() => {
  if (renderer) act(() => renderer.unmount());
  renderer = null;
});

const textOf = () => JSON.stringify(renderer.toJSON());
const textIn = (node) => (typeof node === "string" ? node : node.children.map(textIn).join(""));

async function openCompareTab(isBackendMode) {
  state.isBackendMode = isBackendMode;
  await act(async () => { renderer = create(<Debug />); });
  const tab = renderer.root.find(
    (node) => node.type === "button" && textIn(node).includes(COMPARE_TAB)
  );
  await act(async () => { tab.props.onClick(); });
  // Let the lazy import settle, so a wrongly loaded demo would show up below.
  await act(async () => { await vi.dynamicImportSettled(); });
}

// Order matters: the module cache keeps the factory from running twice, so the
// backend case must come first to see a real count of zero.
it("backend mode shows one line and never loads the demo table", async () => {
  await openCompareTab(true);
  expect(textOf()).toContain(DEMO_ONLY);
  expect(textOf()).not.toContain(LEGEND);
  expect(textOf()).not.toContain("טבלת ההדגמה");
  expect(state.demoLoads).toBe(0);
});

it("local mode shows the legend and the demo table, without the line", async () => {
  await openCompareTab(false);
  expect(textOf()).toContain(LEGEND);
  expect(textOf()).toContain("טבלת ההדגמה");
  expect(textOf()).not.toContain(DEMO_ONLY);
  expect(state.demoLoads).toBe(1);
});
