import React from "react";
import { act, create } from "react-test-renderer";
import { expect, it, vi } from "vitest";
import { useMouseDragScroll } from "./useMouseDragScroll";

function setup(options) {
  let api;
  function Probe() { api = useMouseDragScroll(true, options); return null; }
  act(() => { create(<Probe />); });
  const doc = Object.assign(new EventTarget(), { getSelection: () => null });
  const scroller = Object.assign(new EventTarget(), {
    ownerDocument: doc, scrollLeft: 0, scrollTop: 100,
    setPointerCapture: vi.fn(), hasPointerCapture: () => false, releasePointerCapture: vi.fn(),
  });
  const move = (x, y) => {
    const e = Object.assign(new Event("pointermove", { cancelable: true }), { pointerId: 1, buttons: 1, clientX: x, clientY: y });
    act(() => doc.dispatchEvent(e));
    return e;
  };
  const up = () => act(() => doc.dispatchEvent(Object.assign(new Event("pointerup"), { pointerId: 1 })));
  const down = (extra = {}) => act(() => api.onPointerDown({
    currentTarget: scroller, target: scroller, pointerType: "mouse", pointerId: 1, button: 0, clientX: 0, clientY: 0, ...extra,
  }));
  const click = () => { const e = Object.assign(new Event("click", { cancelable: true }), { detail: 1 }); act(() => api.onClickCapture(e)); return e; };
  return { scroller, move, up, down, click };
}

it("leaves a press alone when shouldStart says it is on text: no scroll, no preventDefault, click kept", () => {
  const t = setup({ shouldStart: () => false, axes: () => ({ x: null, y: { scrollTop: 0 } }) });
  t.down();
  expect(t.move(0, 40).defaultPrevented).toBe(false);
  t.up();
  expect(t.click().defaultPrevented).toBe(false);
});

it("scrolls vertically and horizontally on empty space past the threshold, then swallows the click", () => {
  const x = { scrollLeft: 20 }, y = { scrollTop: 100 };
  const t = setup({ shouldStart: () => true, axes: () => ({ x, y }) });
  t.down();
  expect(t.move(2, 4).defaultPrevented).toBe(false);
  expect(y.scrollTop).toBe(100);
  expect(t.move(10, 30).defaultPrevented).toBe(true);
  expect(y.scrollTop).toBe(70);
  expect(x.scrollLeft).toBe(10);
  t.up();
  expect(t.click().defaultPrevented).toBe(true);
});

it("a vertical-only move past the threshold starts a drag; a tiny wobble stays a click", () => {
  const y = { scrollTop: 0 };
  const t = setup({ axes: () => ({ x: null, y }) });
  t.down(); t.move(3, 4); t.up();
  expect(t.click().defaultPrevented).toBe(false);
  t.down(); t.move(0, 12); t.up();
  expect(y.scrollTop).toBe(-12);
  expect(t.click().defaultPrevented).toBe(true);
});

it("does nothing without a scrollable axis, for touch, or on the scrollbar", () => {
  const t = setup({ axes: () => ({ x: null, y: null }) });
  t.down();
  expect(t.move(0, 40).defaultPrevented).toBe(false);
  const touch = setup({ axes: () => ({ x: null, y: { scrollTop: 0 } }) });
  touch.down({ pointerType: "touch" });
  expect(touch.move(0, 40).defaultPrevented).toBe(false);
  const bar = setup({ axes: () => ({ x: null, y: { scrollTop: 0 } }) });
  Object.assign(bar.scroller, { clientWidth: 100, clientHeight: 100, clientLeft: 0, getBoundingClientRect: () => ({ left: 0, top: 0 }) });
  bar.down({ clientX: 108, clientY: 20 });
  expect(bar.move(108, 60).defaultPrevented).toBe(false);
});
