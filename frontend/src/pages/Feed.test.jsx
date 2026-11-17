import React from "react";
import { act, create } from "react-test-renderer";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FEED_LOAD_ERROR } from "@/components/feed/feedLoadModel";
import Feed from "./Feed";

// The feed screen picks one body — loading skeleton, connection error, empty
// state (plain or the calibrate call to action) or the stream — from the app
// context. The context, the session and the two network-bound children are
// stubbed so each case is deterministic; the state components are real.

const state = vi.hoisted(() => ({ app: /** @type {any} */ (null), auth: /** @type {any} */ (null) }));
const api = vi.hoisted(() => ({
  getMeResultsGameDetail: vi.fn(),
  getResultsGameDetail: vi.fn(),
}));
const view = vi.hoisted(() => ({ props: /** @type {any} */ (null), renders: 0 }));

vi.mock("@/api/client", () => api);
vi.mock("@/context/AppContext", () => ({ useApp: () => state.app }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => state.auth }));
vi.mock("@/components/feed/FeedFreshness", () => ({
  default: ({ enabled }) => <span data-freshness={enabled ? "on" : "off"}>עודכן לפני 4 דק׳</span>,
}));
vi.mock("@/components/feed/signal/SignalFeedView", () => ({
  default: (props) => {
    view.props = props;
    view.renders += 1;
    return <section data-stream>{props.items.map((item) => <p key={item.id}>{item.id}</p>)}</section>;
  },
}));

function story(id, decision = "feed") {
  return { id, title: `כותרת ${id}`, score: { decision } };
}

function appState(overrides = {}) {
  return {
    feedItems: [],
    resultsGames: [],
    scoredArticles: [],
    activeProfileId: "guy",
    isBackendMode: true,
    isLoading: false,
    feedLoadFailed: false,
    refreshFeed: vi.fn(),
    consumerSession: false,
    qaSurfaceAllowed: false,
    ...overrides,
  };
}

const READER = {
  status: "ready",
  authEnforced: true,
  user: { id: "u1", role: "user" },
  onboarding: { completed: true, calibration: { answered: 0 }, interests: { completed: true, selected: 0 } },
};

let renderer;
afterEach(() => {
  if (renderer) act(() => renderer.unmount());
  renderer = null;
  view.props = null;
  view.renders = 0;
  vi.resetAllMocks();
});

function render(app, auth = { status: "ready", authEnforced: false, user: null, onboarding: null }) {
  state.app = appState(app);
  state.auth = auth;
  act(() => {
    renderer = create(<MemoryRouter><Feed /></MemoryRouter>);
  });
  return renderer;
}

const text = () => JSON.stringify(renderer.toJSON());
const byProps = (props) => renderer.root.findAll((node) =>
  typeof node.type === "string" && Object.entries(props).every(([key, value]) => node.props[key] === value));

describe("loading", () => {
  it("shows only a busy skeleton with a Hebrew label while the first request is in flight", () => {
    render({ isLoading: true });
    const skeleton = byProps({ "aria-busy": "true" });
    expect(skeleton).toHaveLength(1);
    expect(skeleton[0].props["aria-label"]).toBe("טוען את הפיד שלך");
    expect(byProps({ role: "alert" })).toHaveLength(0);
    expect(byProps({ "data-freshness": "on" })).toHaveLength(0);
    expect(view.renders).toBe(0);
  });

  it("keeps stories already on screen during a reload instead of blanking to a skeleton", () => {
    render({ isLoading: true, feedItems: [story("a1")] });
    expect(byProps({ "aria-busy": "true" })).toHaveLength(0);
    expect(view.props.items.map((item) => item.id)).toEqual(["a1"]);
  });

  it("never shows a skeleton in local mode, where nothing is fetched", () => {
    render({ isBackendMode: false, isLoading: true });
    expect(byProps({ "aria-busy": "true" })).toHaveLength(0);
    expect(text()).toContain("אין סיגנלים חדשים");
  });
});

describe("connection error", () => {
  it("names the failure in Hebrew, says nothing about an empty feed, and retries on click", () => {
    const refreshFeed = vi.fn();
    render({ feedLoadFailed: true, refreshFeed });
    const alert = byProps({ role: "alert" });
    expect(alert).toHaveLength(1);
    expect(text()).toContain(FEED_LOAD_ERROR.title);
    expect(text()).toContain(FEED_LOAD_ERROR.message);
    expect(text()).not.toContain("אין סיגנלים חדשים");
    const retry = alert[0].findByType("button");
    expect(retry.children).toEqual([FEED_LOAD_ERROR.retryLabel]);
    expect(retry.props.type).toBe("button");
    act(() => retry.props.onClick());
    expect(refreshFeed).toHaveBeenCalledTimes(1);
  });

  it("keeps the freshness line above the error", () => {
    render({ feedLoadFailed: true });
    expect(byProps({ "data-freshness": "on" })).toHaveLength(1);
  });

  it("does not replace stories already on screen when a later refresh fails", () => {
    render({ feedLoadFailed: true, feedItems: [story("a1"), story("a2", "high_feed")] });
    expect(byProps({ role: "alert" })).toHaveLength(0);
    expect(view.props.items.map((item) => item.id)).toEqual(["a1", "a2"]);
  });
});

describe("empty", () => {
  it("says the sources are quiet when a set-up profile has nothing new", () => {
    render({});
    expect(text()).toContain("אין סיגנלים חדשים");
    expect(text()).not.toContain("עוד אין לנו ממה ללמוד");
    expect(byProps({ role: "alert" })).toHaveLength(0);
    expect(view.renders).toBe(0);
  });

  it("treats a feed of hidden-only stories as empty — hidden never reaches the reader", () => {
    render({ feedItems: [story("h1", "hidden"), story("h2", "hidden")] });
    expect(text()).toContain("אין סיגנלים חדשים");
    expect(view.renders).toBe(0);
    expect(text()).not.toContain("h1");
  });

  it("invites a reader with no follows and no calibration to pick interests", () => {
    render({ consumerSession: true }, READER);
    expect(text()).toContain("עוד אין לנו ממה ללמוד");
    const link = renderer.root.findByType("a");
    expect(link.props.href).toBe("/interests");
    expect(link.children).toEqual(["בחרו תחומי עניין"]);
  });

  it("shows the plain empty state once the reader follows something", () => {
    render({ consumerSession: true }, {
      ...READER,
      onboarding: { ...READER.onboarding, interests: { completed: true, selected: 2 } },
    });
    expect(text()).toContain("אין סיגנלים חדשים");
    expect(renderer.root.findAllByType("a")).toHaveLength(0);
  });

  it("never shows the consumer call to action to an admin", () => {
    render({}, { ...READER, user: { id: "a1", role: "admin" } });
    expect(text()).toContain("אין סיגנלים חדשים");
    expect(text()).not.toContain("בחרו תחומי עניין");
  });
});

describe("stream", () => {
  it("passes only visible stories, in order, with the freshness line", () => {
    render({ feedItems: [story("a1", "push"), story("h1", "hidden"), story("a2", "low_feed")] });
    expect(view.props.items.map((item) => item.id)).toEqual(["a1", "a2"]);
    expect(view.props.localScoredArticles).toEqual([]);
    expect(view.props.status.props.enabled).toBe(true);
  });

  it("starts unfiltered, applies a toggle and resets back to everything", () => {
    render({ feedItems: [story("a1", "high_feed")] });
    expect([...view.props.activeFilters]).toEqual(["all"]);
    act(() => view.props.onToggleFilter("high_feed"));
    expect([...view.props.activeFilters]).toEqual(["high_feed"]);
    act(() => view.props.onToggleFilter("league:NBA"));
    expect([...view.props.activeFilters].sort()).toEqual(["high_feed", "league:NBA"]);
    act(() => view.props.onResetFilters());
    expect([...view.props.activeFilters]).toEqual(["all"]);
  });

  it("reads game detail from the reader's own results under a consumer session", async () => {
    api.getMeResultsGameDetail.mockResolvedValue({ id: "g1" });
    render({ feedItems: [story("a1")], consumerSession: true, qaSurfaceAllowed: false });
    await expect(view.props.getResultDetail("g1")).resolves.toEqual({ id: "g1" });
    expect(api.getMeResultsGameDetail).toHaveBeenCalledWith("g1");
    expect(api.getResultsGameDetail).not.toHaveBeenCalled();
  });

  it("reads game detail for the viewed profile on the QA surface", async () => {
    api.getResultsGameDetail.mockResolvedValue({ id: "g2" });
    render({ feedItems: [story("a1")], consumerSession: true, qaSurfaceAllowed: true, activeProfileId: "deni" });
    await view.props.getResultDetail("g2");
    expect(api.getResultsGameDetail).toHaveBeenCalledWith("deni", "g2");
    expect(api.getMeResultsGameDetail).not.toHaveBeenCalled();
  });

  it("offers no game detail and no freshness fetch in local mode", () => {
    const scoredArticles = [{ article: { id: "a1" } }];
    render({ isBackendMode: false, feedItems: [story("a1")], scoredArticles });
    expect(view.props.getResultDetail).toBeNull();
    expect(view.props.localScoredArticles).toBe(scoredArticles);
    expect(view.props.status.props.enabled).toBe(false);
  });
});
