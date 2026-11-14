import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it } from "vitest";
import ResultsStrip from "./ResultsStrip";
import SignalFeedView from "./SignalFeedView";

const NOW = Date.parse("2026-11-14T12:00:00Z");
const final = {
  id: "final", status: "final", startTime: "2026-11-14T10:00:00Z",
  competitionHe: "יורוליג", winner: "away",
  home: { name: "מכבי תל אביב", score: 85 },
  away: { name: "ריאל מדריד", score: 89 },
};
let view;
afterEach(() => { if (view) act(() => view.unmount()); });

function render(element) {
  act(() => { view = create(element); });
  return view;
}

it("renders no placeholder or heading when results are absent or have no finals", () => {
  render(<ResultsStrip nowMs={NOW} />);
  expect(view.toJSON()).toBeNull();
  act(() => view.update(<ResultsStrip results={[{ ...final, status: "live" }]} nowMs={NOW} />));
  expect(view.toJSON()).toBeNull();
});

it("labels the region, games and keyboard-reachable scroller without an app provider or router", () => {
  render(<ResultsStrip results={[final]} nowMs={NOW} />);
  const heading = view.root.findByType("h2");
  expect(view.root.findByType("section").props["aria-labelledby"]).toBe(heading.props.id);
  expect(heading.children).toEqual(["תוצאות"]);
  expect(view.root.findByType("a").props.href).toBe("/results");
  expect(view.root.findByType("a").children).toEqual(["ללוח המלא"]);
  const scroller = view.root.findByProps({ role: "group" });
  expect(scroller.props.tabIndex).toBe(0);
  expect(scroller.props["aria-label"]).toContain("תוצאות");
  expect(view.root.findByType("article").props["aria-label"]).toBe(
    "יורוליג, לפני שעתיים, מכבי תל אביב 85, ריאל מדריד 89, תוצאה סופית"
  );
  const winner = view.root.findByProps({ className: "sg-result__team sg-result__team--winner" });
  expect(winner.findByType("bdi").children).toEqual(["ריאל מדריד"]);
  expect(winner.findByType("bdi").props.dir).toBe("auto");
  expect(winner.findByType("span").props.dir).toBe("ltr");
});

it("the read-only feed accepts optional results and places them between important stories and the stream", () => {
  const story = (id, decision) => ({
    id, type: "article", title: `כותרת ${id}`, url: `https://example.test/${id}`,
    score: { decision }, league: "NBA", publishedAt: "2026-11-14T10:00:00Z",
  });
  const props = {
    items: [story("important", "high_feed"), story("stream", "feed")],
    activeFilters: new Set(["all"]), onToggleFilter: () => {}, onResetFilters: () => {},
    nowMs: NOW, readOnly: true,
  };
  render(<SignalFeedView {...props} />);
  expect(view.root.findAllByType(ResultsStrip)[0].findAllByType("section")).toHaveLength(0);
  act(() => view.update(<SignalFeedView {...props} results={[final]} />));
  const markup = JSON.stringify(view.toJSON());
  expect(markup.indexOf('"sg-important"')).toBeLessThan(markup.indexOf('"sg-results"'));
  expect(markup.indexOf('"sg-results"')).toBeLessThan(markup.indexOf('"sg-band"'));
  act(() => view.update(<SignalFeedView {...props} results={[]} />));
  expect(JSON.stringify(view.toJSON())).not.toContain('"sg-results"');
});
