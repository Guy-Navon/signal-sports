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
  await act(async () => { renderer = create(<DemoApp />); });
  return renderer.root;
}

it("renders the shared feed read-only without providers, with one banner and no navigation", async () => {
  vi.mocked(loadDemoSnapshot).mockResolvedValue({ items, meta, results });
  const root = await render();
  expect(root.findAllByType(SignalWordmark)).toHaveLength(1);
  expect(root.findByType(SignalFeedView).props.readOnly).toBe(true);
  expect(root.findByType(SignalFeedView).props.results).toBe(results);
  expect(root.findAllByProps({ className: "sg-result" })).toHaveLength(1);
  expect(root.findAllByType(FeedbackControls)).toHaveLength(0);
  expect(root.findAllByType("nav")).toHaveLength(0);
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
  vi.mocked(loadDemoSnapshot).mockResolvedValue({ items, meta, results });
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
    .mockResolvedValueOnce({ items, meta, results: [] });
  const root = await render();
  expect(root.findByProps({ role: "alert" }).findByType("h2").children).toEqual(["לא הצלחנו לטעון את ההדגמה"]);
  await act(async () => { root.findByType("button").props.onClick(); });
  expect(root.findByType(SignalFeedView).props.items).toBe(items);
  expect(loadDemoSnapshot).toHaveBeenCalledTimes(2);
});
