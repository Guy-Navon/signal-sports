import React, { lazy } from "react";
import { act, create } from "react-test-renderer";
import { afterEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ auth: null }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => state.auth }));
vi.mock("@/api/client", async (importOriginal) => ({
  ...await importOriginal(),
  getProfiles: vi.fn().mockResolvedValue([]),
  getMeProfile: vi.fn().mockResolvedValue({ user_id: "user-one", display_name: "קורא", topics: [] }),
  getFeed: vi.fn().mockResolvedValue([]),
  getDebugFeed: vi.fn().mockResolvedValue([]),
  getMeFeed: vi.fn().mockResolvedValue([]),
  getResults: vi.fn().mockResolvedValue({ has_preferences: false, games: [] }),
  getMeResults: vi.fn().mockResolvedValue({ has_preferences: false, games: [] }),
}));

let renderer;
afterEach(() => {
  if (renderer) act(() => renderer.unmount());
  renderer = null;
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

const textOf = () => JSON.stringify(renderer.toJSON());
const TITLE = "לא הצלחנו להציג את המסך";
const RELOAD = "טען מחדש";

// A real AppProvider in backend mode under a real session role, so the hook's
// answer comes from the same rule the app uses, not from a mock of the hook.
async function renderInSession(role, child) {
  vi.stubEnv("VITE_DATA_MODE", "backend");
  vi.resetModules();
  state.auth = { status: "ready", authEnforced: true, user: { id: "user-one", role } };
  const { AppProvider } = await import("@/context/AppContext");
  const { default: LazyBoundary } = await import("./LazyBoundary");
  await act(async () => {
    renderer = create(<AppProvider><LazyBoundary>{child}</LazyBoundary></AppProvider>);
  });
}

const crash = new TypeError("sources.filter is not a function");
/** @returns {React.ReactNode} */
function Crashing() { throw crash; }

it("shows a loading status, then the screen", async () => {
  const { default: LazyBoundary } = await import("./LazyBoundary");
  let release = () => {};
  const Screen = lazy(() => /** @type {Promise<{ default: React.ComponentType }>} */ (new Promise((resolve) => {
    release = () => resolve({ default: () => <p>המסך</p> });
  })));
  await act(async () => { renderer = create(<LazyBoundary><Screen /></LazyBoundary>); });
  expect(textOf()).toContain("טוען");
  await act(async () => { release(); });
  expect(textOf()).toContain("המסך");
});

it("a chunk that fails to load blanks nothing around it", async () => {
  const { default: LazyBoundary } = await import("./LazyBoundary");
  vi.spyOn(console, "error").mockImplementation(() => {});
  const Broken = lazy(() => Promise.reject(new Error("Failed to fetch dynamically imported module")));
  await act(async () => {
    renderer = create(<div><span>המעטפת</span><LazyBoundary><Broken /></LazyBoundary></div>);
  });
  expect(textOf()).toContain("המעטפת");
  expect(textOf()).toContain(TITLE);
  expect(textOf()).toContain(RELOAD);
});

describe("what a failed screen says, by who is looking", () => {
  it("a regular reader gets the Hebrew title and reload, and no raw error text", async () => {
    const logged = vi.spyOn(console, "error").mockImplementation(() => {});
    await renderInSession("user", <Crashing />);
    expect(textOf()).toContain(TITLE);
    expect(textOf()).toContain(RELOAD);
    expect(textOf()).not.toContain("sources.filter");
    expect(logged.mock.calls.some((call) => call.includes(crash))).toBe(true);
  });

  it("an admin also gets the raw message", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    await renderInSession("admin", <Crashing />);
    expect(textOf()).toContain(TITLE);
    expect(textOf()).toContain("sources.filter is not a function");
  });
});
