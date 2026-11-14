import React from "react";
import { act, create } from "react-test-renderer";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import * as api from "@/api/client";
import Calibration from "./Calibration";

const state = vi.hoisted(() => ({ app: null, auth: null }));
vi.mock("@/context/AppContext", () => ({ useApp: () => state.app }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => state.auth }));
vi.mock("@/api/client", () => ({
  getCalibrationItems: vi.fn(), getMeCalibrationItems: vi.fn(),
  previewCalibration: vi.fn(), applyCalibration: vi.fn(), getCalibrationResponses: vi.fn(),
  applyMeCalibration: vi.fn(), getMeCalibrationResponses: vi.fn(),
  saveMeCalibrationResponses: vi.fn(), completeMeOnboarding: vi.fn(),
}));

const items = [{ id: "a", sport: "basketball", title: "כותרת א" }, { id: "b", sport: "tennis", title: "כותרת ב" }];
const result = {
  applied_scope_affinities: 1, applied_event_affinities: 0,
  profile_v2: { scope_affinities: [{ source: "calibration", scope: "sport", target_id: "tennis", level: -1 }], event_affinities: [] },
};
let renderer;
const focus = vi.fn();
function Location() { return <output>{useLocation().pathname}</output>; }
async function render() {
  await act(async () => {
    renderer = create(<MemoryRouter initialEntries={["/preferences/calibration"]}><Calibration embedded /><Location /></MemoryRouter>, {
      createNodeMock: () => ({ focus }),
    });
  });
}
const button = (label) => renderer.root.findAllByType("button").find((node) => node.props["aria-label"] === label || node.children.some((text) => typeof text === "string" && text.includes(label)));
const text = () => JSON.stringify(renderer.toJSON());

beforeEach(() => {
  vi.clearAllMocks();
  state.app = { isBackendMode: true, consumerSession: true, activeProfileId: "qa-other", refreshProfiles: vi.fn(), refreshFeed: vi.fn() };
  state.auth = { authEnforced: true, user: { id: "me", role: "user" }, onboarding: { completed: true }, refreshSession: vi.fn().mockResolvedValue(undefined) };
  for (const fn of [api.getCalibrationItems, api.getMeCalibrationItems]) vi.mocked(fn).mockResolvedValue({ version: 3, items });
  for (const fn of [api.getCalibrationResponses, api.getMeCalibrationResponses]) vi.mocked(fn).mockResolvedValue({ ratings: {} });
  for (const fn of [api.applyCalibration, api.applyMeCalibration]) vi.mocked(fn).mockResolvedValue(result);
  vi.mocked(api.saveMeCalibrationResponses).mockResolvedValue({});
  vi.mocked(api.previewCalibration).mockResolvedValue({ scope_affinities: [], event_affinities: [] });
});
afterEach(() => { if (renderer) act(() => renderer.unmount()); renderer = null; });

it("keeps consumer rate/clear and apply payloads and shows saved levels with focused summary links", async () => {
  await render();
  await act(async () => button("מעניין").props.onClick());
  await act(async () => button("מעניין").props.onClick());
  expect(api.saveMeCalibrationResponses).toHaveBeenLastCalledWith({ a: null });
  await act(async () => button("תעדכן אותי מיד").props.onClick());
  await act(async () => button("שמור לפרופיל").props.onClick());
  expect(api.applyMeCalibration).toHaveBeenCalledWith({ a: "push" });
  expect(api.applyCalibration).not.toHaveBeenCalled();
  expect(state.app.refreshProfiles).toHaveBeenCalledOnce();
  expect(state.app.refreshFeed).toHaveBeenCalledOnce();
  expect(text()).toContain("מה השתנה בהעדפות שלך");
  expect(text()).toContain("טניס");
  expect(text()).toContain("אין כאן השוואה לרמות הקודמות");
  expect(focus).toHaveBeenCalled();
  expect(renderer.root.findAllByType("a").map((node) => node.props.href)).toEqual(["/", "/preferences", "/preferences/learned"]);
  focus.mockClear();
  await act(async () => button("המשך דירוג").props.onClick());
  expect(focus).toHaveBeenCalledOnce();
  expect(text()).not.toContain("מה השתנה בהעדפות שלך");
  expect(button("תעדכן אותי מיד").props["aria-pressed"]).toBe(true);
});

it("keeps onboarding completion and shows proof before the explicit continue to feed", async () => {
  state.auth.onboarding = { completed: false, interests: { completed: true } };
  await render();
  await act(async () => button("מעניין").props.onClick());
  await act(async () => button("שמור לפרופיל").props.onClick());
  expect(state.auth.refreshSession).toHaveBeenCalledOnce();
  expect(renderer.root.findByType("output").children).toEqual(["/preferences/calibration"]);
  expect(text()).toContain("המשך לפיד שלי");
});

it("keeps the bypass apply target and does not write consumer responses", async () => {
  state.app.consumerSession = false;
  await render();
  await act(async () => button("מעניין").props.onClick());
  await act(async () => button("שמור לפרופיל").props.onClick());
  expect(api.applyCalibration).toHaveBeenCalledWith("qa-other", { a: "interesting" });
  expect(api.applyMeCalibration).not.toHaveBeenCalled();
  expect(api.saveMeCalibrationResponses).not.toHaveBeenCalled();
});

it("keeps failed apply ratings available and clears stale preview after a changed rating", async () => {
  await render();
  await act(async () => button("מעניין").props.onClick());
  await act(async () => button("תצוגה מקדימה").props.onClick());
  expect(text()).toContain("מה המערכת למדה עליך");
  await act(async () => button("תעדכן אותי מיד").props.onClick());
  expect(text()).not.toContain("מה המערכת למדה עליך");
  vi.mocked(api.applyMeCalibration).mockRejectedValueOnce(new Error("שמירה נכשלה"));
  await act(async () => button("שמור לפרופיל").props.onClick());
  expect(text()).toContain("שמירה נכשלה");
  expect(text()).not.toContain("מה השתנה בהעדפות שלך");
  expect(button("תעדכן אותי מיד").props["aria-pressed"]).toBe(true);
});
