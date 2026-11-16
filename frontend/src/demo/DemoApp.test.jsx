import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { normalizeScoredArticleFromApi } from "@/api/normalizers";
import FeedbackControls from "@/components/feed/FeedbackControls";
import SignalFeedView from "@/components/feed/signal/SignalFeedView";
import SignalWordmark from "@/components/signal-ui/SignalWordmark";
import DemoApp from "./DemoApp";
import { loadDemoSnapshot } from "./demoModel";

vi.mock("./demoModel", async (importOriginal) => ({
  ...await importOriginal(),
  loadDemoSnapshot: vi.fn(),
}));

const NOW = Date.parse("2026-11-14T10:00:00Z");
const meta = { generated_at: new Date(NOW).toISOString() };
const results = [{
  id: "game-1", competitionHe: "יורוליג", status: "final",
  startTime: "2026-11-14T09:00:00Z", winner: "home",
  home: { name: "מכבי תל אביב", score: 90 }, away: { name: "ריאל מדריד", score: 85 },
}];
const items = ["NBA", "EuroLeague"].map((league, index) => normalizeScoredArticleFromApi({
  decision: "feed",
  reason_he: "ליגה במעקב שלך",
  article: {
    id: `story-${index}`, title: `כותרת ${league}`, league,
    url: `https://example.test/${index}`, source: "sport5",
    published_at: "2026-11-14T09:00:00Z",
  },
}));

let renderer;
beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  vi.stubGlobal("window", { fetch: vi.fn() });
});
afterEach(() => {
  if (renderer) act(() => renderer.unmount());
  renderer = null;
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.resetAllMocks();
});

async function render() {
  await act(async () => { renderer = create(<DemoApp />, {
    createNodeMock: element => element.type === "dialog" ? { showModal() {}, close() {} } : { focus() {} },
  }); });
  return renderer.root;
}

it("renders the shared feed read-only without providers, with one banner and only the feed and results tabs", async () => {
  vi.mocked(loadDemoSnapshot).mockResolvedValue({ items, meta, results, resultDetails: {} });
  const root = await render();
  expect(root.findAllByType(SignalWordmark)).toHaveLength(1);
  expect(root.findByType(SignalFeedView).props.readOnly).toBe(true);
  expect(root.findByType(SignalFeedView).props.results).toBe(results);
  expect(root.findAllByProps({ className: "sg-result" })).toHaveLength(1);
  expect(root.findAllByType(FeedbackControls)).toHaveLength(0);
  // Only the two demo tabs: no account, preferences or calibration entries.
  expect(root.findAllByType("nav")).toHaveLength(1);
  expect(root.findAllByProps({ className: "sg-tab" }).map((a) => a.props.href)).toEqual(["#", "#results"]);
  expect(root.findAllByProps({ className: "sg-demo-banner" })).toHaveLength(1);

  act(() => root.findByType(SignalFeedView).props.onToggleFilter("league:NBA"));
  // The feed owns filtering; its summary and pill counts keep the full snapshot.
  expect(root.findByType(SignalFeedView).props.items).toBe(items);
  expect(root.findAllByProps({ className: "sg-row" })).toHaveLength(1);
  expect(JSON.stringify(renderer.toJSON())).toContain("כותרת NBA");
  expect(JSON.stringify(renderer.toJSON())).not.toContain("כותרת EuroLeague");

  act(() => vi.advanceTimersByTime(181 * 60_000));
  expect(JSON.stringify(renderer.toJSON())).toContain("הנתונים בהדגמה לא התעדכנו כבר כמה שעות");
});

it("announces only the staleness warning, not the minute-by-minute update time", async () => {
  vi.mocked(loadDemoSnapshot).mockResolvedValue({ items, meta, results, resultDetails: {} });
  const root = await render();
  const banner = root.findByProps({ className: "sg-demo-banner" });
  expect(banner.props.role).toBeUndefined();
  const slot = banner.findByProps({ className: "sg-demo-banner__status" });
  expect(slot.props.role).toBe("status");
  expect(slot.findAllByProps({ className: "sg-demo-banner__warning" })).toHaveLength(0);
  act(() => vi.advanceTimersByTime(181 * 60_000));
  const warning = slot.findByProps({ className: "sg-demo-banner__warning" });
  expect(warning.children).toContain("הנתונים בהדגמה לא התעדכנו כבר כמה שעות");
});

it("keeps the loading and empty states", async () => {
  let resolve;
  vi.mocked(loadDemoSnapshot).mockReturnValue(new Promise((done) => { resolve = done; }));
  const root = await render();
  expect(root.findByProps({ "aria-busy": "true" }).props["aria-label"]).toBe("טוען את הפיד שלך");
  await act(async () => { resolve({ items: [], meta }); });
  expect(JSON.stringify(renderer.toJSON())).toContain("אין כרגע סיפורים בפיד");
  expect(root.findAllByType(SignalFeedView)).toHaveLength(0);
});

it("keeps the error state and retries the snapshot", async () => {
  vi.mocked(loadDemoSnapshot).mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ items, meta, results: [], resultDetails: {} });
  const root = await render();
  expect(root.findByProps({ role: "alert" }).findByType("h2").children).toEqual(["לא הצלחנו לטעון את ההדגמה"]);
  await act(async () => { root.findByType("button").props.onClick(); });
  expect(root.findByType(SignalFeedView).props.items).toBe(items);
  expect(loadDemoSnapshot).toHaveBeenCalledTimes(2);
});

const finalGame = (id, extra = {}) => ({
  id, competitionId: "comp:nba", competitionHe: "NBA", sport: "basketball", status: "final",
  startTime: "2026-11-14T03:00:00Z", localDate: "2026-11-14", winner: "home", relevanceReason: "",
  home: { id: "team:a", name: "פורטלנד בלייזרס", score: 121, isWinner: true },
  away: { id: "team:b", name: "סקרמנטו קינגס", score: 118, isWinner: false }, ...extra,
});

function withHash(hash) {
  const listeners = [];
  window.location = /** @type {any} */ ({ hash });
  window.addEventListener = (type, fn) => listeners.push(fn);
  window.removeEventListener = () => {};
  return () => listeners.forEach((fn) => fn());
}

it("opens exported box scores from the results tab without API calls or preference links", async () => {
  withHash("#results");
  const detail = { game_id: "g1", venue: "Moda Center", team_stats: {
    home: { quarters: [30, 30, 30, 31] }, away: { quarters: [30, 30, 30, 28] },
  }, players: [{ side: "home", name: "דני אבדיה", minutes: 35,
    stats: { points: 34, rebounds: 6, assists: 4, starter: true } }] };
  vi.mocked(loadDemoSnapshot).mockResolvedValue({ items, meta,
    results: [finalGame("g1", { relevanceReason: "followed_team:team:a", detailAvailable: true,
      leaders: [{ side: "home", name: "דני אבדיה", stat: "points", value: 34 }],
      chosenPlayerLines: detail.players,
    })], resultDetails: { g1: detail } });
  const root = await render();
  expect(root.findAllByType(SignalFeedView)).toHaveLength(0);
  expect(root.findAllByProps({ "aria-current": "page" })[0].props.href).toBe("#results");
  expect(root.findAllByProps({ className: "sr-tile" })).toHaveLength(1);
  expect(root.findAllByProps({ className: "sr-row" })).toHaveLength(1);
  const interactive = root.findAll((n) => n.type === "button" && /sr-(row|tile)/.test(n.props.className || ""));
  expect(interactive).toHaveLength(2);
  expect(root.findAllByType("a").some(a => a.props.href === "/preferences")).toBe(false);
  expect(root.findAllByProps({ className: "sr-side" })).toHaveLength(1);
  await act(async () => interactive[0].props.onClick({ currentTarget: { focus() {} } }));
  expect(root.findAllByType("dialog")).toHaveLength(1);
  for (const value of ["Moda Center", "רבע ", "דני אבדיה", "חמישייה", "34"])
    expect(JSON.stringify(renderer.toJSON())).toContain(value);
  expect(window.fetch).not.toHaveBeenCalled();
  act(() => root.findByProps({ "aria-label": "סגירת פרטי המשחק" }).props.onClick());
  expect(root.findAllByType("dialog")).toHaveLength(0);
});

it("shows upcoming games even with no completed games, with no account or preferences links", async () => {
  withHash("#results");
  vi.mocked(loadDemoSnapshot).mockResolvedValue({ items, meta, resultDetails: {}, results: [finalGame("next", {
    status: "scheduled", winner: null, localDate: "2026-11-15", startTime: "2026-11-15T18:00:00Z",
    home: { name: "מכבי תל אביב", score: null }, away: { name: "הפועל ירושלים", score: null },
  })] });
  const root = await render();
  expect(JSON.stringify(renderer.toJSON())).toContain("הקרוב");
  expect(JSON.stringify(renderer.toJSON())).toContain("מכבי תל אביב");
  expect(root.findAllByProps({ className: "sr-row" })).toHaveLength(0);
  expect(root.findAllByType("a").some(a => a.props.href?.startsWith("/"))).toBe(false);
});

it("switches tabs when the hash changes", async () => {
  const fire = withHash("");
  vi.mocked(loadDemoSnapshot).mockResolvedValue({ items, meta, resultDetails: {}, results: [finalGame("g1")] });
  const root = await render();
  expect(root.findAllByType(SignalFeedView)).toHaveLength(1);
  window.location.hash = "#results";
  act(() => fire());
  expect(root.findAllByType(SignalFeedView)).toHaveLength(0);
  window.location.hash = "";
  act(() => fire());
  expect(root.findAllByType(SignalFeedView)).toHaveLength(1);
});

it("shows an honest note when there are no results, and does not invent games", async () => {
  withHash("#results");
  vi.mocked(loadDemoSnapshot).mockResolvedValue({ items, meta, resultDetails: {}, results: [] });
  const root = await render();
  expect(JSON.stringify(renderer.toJSON())).toContain("אין תוצאות להצגה כרגע");
  expect(root.findAllByProps({ className: "sr-row" })).toHaveLength(0);
  expect(root.findAllByProps({ className: "sr-tile" })).toHaveLength(0);
});
