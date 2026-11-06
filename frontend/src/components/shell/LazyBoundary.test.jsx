import React, { lazy } from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import LazyBoundary from "./LazyBoundary";

let renderer;
afterEach(() => {
  if (renderer) act(() => renderer.unmount());
  renderer = null;
  vi.restoreAllMocks();
});

const textOf = () => JSON.stringify(renderer.toJSON());

it("shows a loading status, then the screen", async () => {
  let release = () => {};
  const Screen = lazy(() => /** @type {Promise<{ default: React.ComponentType }>} */ (new Promise((resolve) => {
    release = () => resolve({ default: () => <p>המסך</p> });
  })));
  await act(async () => { renderer = create(<LazyBoundary><Screen /></LazyBoundary>); });
  expect(textOf()).toContain("טוען");
  await act(async () => { release(); });
  expect(textOf()).toContain("המסך");
});

it("a chunk that fails to load shows an error with a reload, and blanks nothing else", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const Broken = lazy(() => Promise.reject(new Error("Failed to fetch dynamically imported module")));
  await act(async () => {
    renderer = create(<div><span>המעטפת</span><LazyBoundary><Broken /></LazyBoundary></div>);
  });
  expect(textOf()).toContain("המעטפת");
  expect(textOf()).toContain("לא הצלחנו להציג את המסך");
  expect(textOf()).toContain("Failed to fetch dynamically imported module");
  expect(textOf()).toContain("טען מחדש");
});

it("a render crash shows its own message, not a claim about an app update", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const Crashing = () => { throw new TypeError("sources.filter is not a function"); };
  await act(async () => { renderer = create(<LazyBoundary><Crashing /></LazyBoundary>); });
  expect(textOf()).toContain("sources.filter is not a function");
  expect(textOf()).toContain("לא הצלחנו להציג את המסך");
  expect(textOf()).not.toContain("עודכנה");
});
