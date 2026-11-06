import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ auth: null, mockDataLoads: 0 }));
vi.mock("./AuthContext", () => ({ useAuth: () => state.auth }));
// Counts real loads of the demo data; re-evaluated after each vi.resetModules().
vi.mock("@/data/mockArticles", async (importOriginal) => {
  state.mockDataLoads += 1;
  return importOriginal();
});
vi.mock("@/api/client", async (importOriginal) => ({
  ...await importOriginal(),
  getProfiles: vi.fn().mockResolvedValue([]),
  getMeProfile: vi.fn().mockRejectedValue(new Error("test profile unavailable")),
  getFeed: vi.fn().mockResolvedValue([]),
  getDebugFeed: vi.fn().mockResolvedValue([]),
  getMeFeed: vi.fn().mockResolvedValue([]),
  getResults: vi.fn().mockResolvedValue({ has_preferences: false, games: [] }),
  getMeResults: vi.fn().mockResolvedValue({ has_preferences: false, games: [] }),
  submitFeedback: vi.fn().mockResolvedValue({}),
  submitMeFeedback: vi.fn().mockResolvedValue({}),
}));
let renderer;
afterEach(() => {
  if (renderer) act(() => renderer.unmount());
  renderer = null;
  vi.clearAllMocks();
  vi.unstubAllEnvs();
});

async function mount(role) {
  vi.stubEnv("VITE_DATA_MODE", "backend");
  vi.resetModules();
  state.auth = { status: "ready", authEnforced: true, user: { id: "user-one", role } };
  const { AppProvider, useApp } = await import("./AppContext");
  let context;
  function Probe() { context = useApp(); return null; }
  const element = () => <AppProvider><Probe /></AppProvider>;
  await act(async () => { renderer = create(element()); });
  return { context: () => context, element };
}

it("backend mode never loads the demo data or the local engine (#199)", async () => {
  state.mockDataLoads = 0;
  const app = await mount("admin");
  expect(state.mockDataLoads).toBe(0);
  expect(app.context().feedItems).toEqual([]);
  expect(app.context().scoredArticles).toEqual([]);
  expect(app.context().profiles).toEqual({});
});

it("local mode renders nothing until the demo arrives, then serves the mock feed (#199)", async () => {
  vi.stubEnv("VITE_DATA_MODE", "");
  vi.resetModules();
  state.mockDataLoads = 0;
  state.auth = { status: "ready", authEnforced: false, user: null };
  const { AppProvider, useApp } = await import("./AppContext");
  let context = /** @type {any} */ (null);
  function Probe() { context = useApp(); return null; }
  act(() => { renderer = create(<AppProvider><Probe /></AppProvider>); });
  expect(context).toBeNull();
  await vi.waitFor(async () => {
    await act(async () => { await Promise.resolve(); });
    expect(context).not.toBeNull();
  });
  expect(state.mockDataLoads).toBe(1);
  expect(context.activeProfile.userId).toBe("guy");
  expect(context.feedItems.length).toBeGreaterThan(0);
  expect(context.debugItems.length).toBeGreaterThanOrEqual(context.feedItems.length);
  expect(context.profileList.map((p) => p.id)).toContain("casual_deni_fan");
});

it("sends feedback to the profile whose feed an admin is viewing", async () => {
  const app = await mount("admin");
  const api = await import("@/api/client");
  await act(async () => { app.context().setActiveProfileId("guy"); });
  await act(async () => { app.context().addFeedback("rss_test", "not_interested"); });
  expect(api.submitFeedback).toHaveBeenCalledWith({ user_id: "guy", article_id: "rss_test", action: "not_interested" });
  expect(api.submitMeFeedback).not.toHaveBeenCalled();
});

it("keeps regular-user feedback session-derived and clears it on account switch", async () => {
  const app = await mount("user");
  const api = await import("@/api/client");
  await act(async () => { app.context().addFeedback("rss_test", "more_like_this"); });
  expect(api.submitMeFeedback).toHaveBeenCalledWith("rss_test", "more_like_this");
  expect(app.context().feedback[0].userId).toBe("user-one");
  state.auth = { ...state.auth, user: { id: "user-two", role: "user" } };
  await act(async () => { renderer.update(app.element()); });
  expect(app.context().feedback).toEqual([]);
});
