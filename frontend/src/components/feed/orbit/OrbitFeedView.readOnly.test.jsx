import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import { normalizeScoredArticleFromApi } from "@/api/normalizers";
import FeedbackControls from "@/components/feed/FeedbackControls";
import OrbitFeedView from "./OrbitFeedView";

// The public demo (#458) renders this view with no AppProvider. Read-only must
// mean: no feedback controls (they would write preferences) and the reader's
// Hebrew reason instead of the engine trace.

const REASON = "מכבי תל אביב (כדורסל) ברשימת המעקב שלך";
const items = ["rss_1", "rss_2"].map((id, index) =>
  normalizeScoredArticleFromApi({
    decision: index === 0 ? "high_feed" : "feed",
    reason_he: REASON,
    article: {
      id,
      source: "walla_sport",
      source_display_name: "וואלה ספורט",
      url: `https://example.test/${id}`,
      title: `כותרת ${id}`,
      published_at: "2026-11-09T06:39:00Z",
      sport: "basketball",
      league: "EuroLeague",
      entities: ["Maccabi Tel Aviv Basketball"],
      event_type: "negotiation",
      importance: "high",
      tags: [],
    },
    cluster: null,
  })
);

let renderer;
afterEach(() => {
  if (renderer) act(() => renderer.unmount());
  renderer = null;
  vi.restoreAllMocks();
});

function view(props) {
  return (
    <OrbitFeedView
      items={items}
      localScoredArticles={[]}
      profileName="גיא"
      scanned={0}
      decisionCounts={{ push: 0, high_feed: 1, feed: 1, low_feed: 0 }}
      activeFilters={new Set(["all"])}
      onToggleFilter={() => {}}
      onResetFilters={() => {}}
      {...props}
    />
  );
}

it("read-only renders the stories and the reader reason without feedback controls", () => {
  act(() => { renderer = create(view({ readOnly: true })); });
  const text = JSON.stringify(renderer.toJSON());
  expect(text).toContain("כותרת rss_1");
  expect(text).toContain(REASON);
  expect(renderer.root.findAllByType(FeedbackControls)).toHaveLength(0);
});

it("without read-only the feedback controls mount (and need the app context)", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  expect(() => {
    act(() => { renderer = create(view({})); });
  }).toThrow("useApp must be used within AppProvider");
});
