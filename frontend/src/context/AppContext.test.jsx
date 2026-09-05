import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ auth: null }));
vi.mock("./AuthContext", () => ({ useAuth: () => state.auth }));
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
