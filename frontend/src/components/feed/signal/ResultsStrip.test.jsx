import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import ResultsStrip from "./ResultsStrip";
import SignalFeedView from "./SignalFeedView";

vi.mock("./StripGameDetail", () => ({
  default: ({ game, onClose }) => <div data-testid="box" data-game={game.id} onClick={onClose} />,
}));

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

function dragFixture() {
  render(<ResultsStrip results={[final]} nowMs={NOW} />);
  const doc = Object.assign(new EventTarget(), { getSelection: () => null });
  let captured = false;
  const scroller = Object.assign(new EventTarget(), {
    ownerDocument: doc,
    scrollLeft: -100,
    setPointerCapture: vi.fn(() => { captured = true; }),
    hasPointerCapture: () => captured,
    releasePointerCapture: vi.fn(() => { captured = false; }),
  });
  const props = () => view.root.findByProps({ role: "group" }).props;
  const pointer = (type, overrides = {}) => Object.assign(new Event(type, { cancelable: true }), {
    pointerType: "mouse", pointerId: 1, button: 0, buttons: 1, clientX: 100, ...overrides,
  });
  return {
    scroller, props,
    down(overrides = {}) {
      const event = { currentTarget: scroller, pointerType: "mouse", pointerId: 1, button: 0, clientX: 100, ...overrides };
      act(() => props().onPointerDown(event));
    },
    send(type, overrides = {}) {
      const event = pointer(type, overrides);
      act(() => (type === "lostpointercapture" ? scroller : doc).dispatchEvent(event));
      return event;
    },
    click(detail = 1) {
      const event = Object.assign(new Event("click", { cancelable: true }), { detail });
      const stop = vi.spyOn(event, "stopPropagation");
      act(() => props().onClickCapture(event));
      return { event, stop };
    },
  };
}

it("starts after the threshold and moves RTL content with the mouse in both directions", () => {
  const drag = dragFixture();
  drag.down();
  expect(drag.send("pointermove", { clientX: 104 }).defaultPrevented).toBe(false);
  expect(drag.scroller.scrollLeft).toBe(-100);
  expect(drag.scroller.setPointerCapture).not.toHaveBeenCalled();
  expect(drag.send("pointermove", { clientX: 130 }).defaultPrevented).toBe(true);
  expect(drag.scroller.scrollLeft).toBe(-130);
  expect(drag.scroller.hasPointerCapture()).toBe(true);
  expect(drag.props().className).toContain("--dragging");
  drag.send("pointermove", { clientX: 80 });
  expect(drag.scroller.scrollLeft).toBe(-80);
  drag.send("pointerup", { buttons: 0 });
  expect(drag.scroller.hasPointerCapture()).toBe(false);
  expect(drag.props().className).not.toContain("--dragging");
  drag.send("pointermove", { clientX: 160 });
  expect(drag.scroller.scrollLeft).toBe(-80);
});

it("leaves a press on the native scrollbar to the browser", () => {
  const drag = dragFixture();
  Object.assign(drag.scroller, { clientHeight: 100, clientTop: 0, getBoundingClientRect: () => ({ top: 10 }) });
  drag.down({ clientY: 112 });
  expect(drag.send("pointermove", { clientX: 140 }).defaultPrevented).toBe(false);
  expect(drag.scroller.scrollLeft).toBe(-100);
  drag.down({ clientY: 60 });
  drag.send("pointermove", { clientX: 140 });
  expect(drag.scroller.scrollLeft).toBe(-140);
});

it.each([
  { pointerType: "touch" }, { pointerType: "pen" }, { button: 1 }, { button: 2 },
])("leaves native scrolling alone for $pointerType / button $button", (input) => {
  const drag = dragFixture();
  drag.down(input);
  const move = drag.send("pointermove", { ...input, clientX: 140 });
  expect(move.defaultPrevented).toBe(false);
  expect(drag.scroller.scrollLeft).toBe(-100);
  expect(drag.scroller.setPointerCapture).not.toHaveBeenCalled();
});

it("swallows the ending click in capture, then allows a plain click and the header link", () => {
  const drag = dragFixture();
  drag.down();
  drag.send("pointermove", { clientX: 130 });
  drag.send("pointerup", { buttons: 0 });
  const blocked = drag.click();
  expect(blocked.event.defaultPrevented).toBe(true);
  expect(blocked.stop).toHaveBeenCalledOnce();
  drag.down();
  drag.send("pointermove", { clientX: 103 });
  drag.send("pointerup", { buttons: 0 });
  const plain = drag.click();
  expect(plain.event.defaultPrevented).toBe(false);
  expect(plain.stop).not.toHaveBeenCalled();
  expect(view.root.findByType("a").props.href).toBe("/results");
  expect(view.root.findByType("a").props.onClickCapture).toBeUndefined();
});

it.each(["pointercancel", "lostpointercapture"])("ends a drag on %s and allows later keyboard and mouse clicks", (type) => {
  const drag = dragFixture();
  drag.down();
  drag.send("pointermove", { clientX: 130 });
  drag.send(type);
  drag.send("pointermove", { clientX: 170 });
  expect(drag.scroller.scrollLeft).toBe(-130);
  expect(drag.scroller.hasPointerCapture()).toBe(false);
  expect(drag.props().className).not.toContain("--dragging");
  expect(drag.click(0).event.defaultPrevented).toBe(false);
  drag.down();
  drag.send("pointerup", { buttons: 0 });
  expect(drag.click().event.defaultPrevented).toBe(false);
});

it("keeps a touch tap after a cancelled mouse drag native", () => {
  const drag = dragFixture();
  drag.down();
  drag.send("pointermove", { clientX: 130 });
  drag.send("pointercancel");
  drag.down({ pointerType: "touch", pointerId: 2 });
  expect(drag.click().event.defaultPrevented).toBe(false);
});

it("ignores other pointers and cleans up a release outside the strip before the threshold", () => {
  const drag = dragFixture();
  drag.down();
  expect(drag.send("pointermove", { pointerId: 2, clientX: 150 }).defaultPrevented).toBe(false);
  drag.send("pointerup", { pointerId: 2, buttons: 0 });
  drag.send("pointerup", { buttons: 0 });
  drag.send("pointermove", { clientX: 170 });
  expect(drag.scroller.scrollLeft).toBe(-100);
  expect(drag.scroller.setPointerCapture).not.toHaveBeenCalled();
});

it.each(["unmount", "no finals"])("releases capture and stops tracking the mouse on %s", (change) => {
  const drag = dragFixture();
  drag.down();
  drag.send("pointermove", { clientX: 130 });
  act(() => {
    if (change === "unmount") view.unmount();
    else view.update(<ResultsStrip results={[]} nowMs={NOW} />);
  });
  drag.send("pointermove", { clientX: 170 });
  expect(drag.scroller.scrollLeft).toBe(-130);
  expect(drag.scroller.hasPointerCapture()).toBe(false);
});

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

it("opens the box score from a plain click on a game with stored details, via a real button", async () => {
  const getDetail = vi.fn();
  render(<ResultsStrip results={[{ ...final, detailAvailable: true }]} nowMs={NOW} getDetail={getDetail} />);
  const item = view.root.findByType("button");
  expect(item.props.type).toBe("button");
  expect(item.props["aria-haspopup"]).toBe("dialog");
  expect(view.root.findAllByType("article")).toHaveLength(0);
  const focus = vi.fn();
  await act(async () => item.props.onClick({ currentTarget: { focus } }));
  expect(view.root.findByProps({ "data-testid": "box" }).props["data-game"]).toBe("final");
  await act(async () => view.root.findByProps({ "data-testid": "box" }).props.onClick());
  expect(view.root.findAllByProps({ "data-testid": "box" })).toHaveLength(0);
  expect(focus).toHaveBeenCalled();
});

it("keeps a game without stored details, or a strip without a detail reader, non-interactive", () => {
  render(<ResultsStrip results={[final]} nowMs={NOW} getDetail={() => {}} />);
  expect(view.root.findAllByType("button")).toHaveLength(0);
  act(() => view.update(<ResultsStrip results={[{ ...final, detailAvailable: true }]} nowMs={NOW} />));
  expect(view.root.findAllByType("button")).toHaveLength(0);
});
