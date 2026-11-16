import { useEffect, useRef, useState } from "react";

export const DRAG_THRESHOLD_PX = 5;

const defaultAxes = (event) => ({ x: event.currentTarget, y: null });

/**
 * Mouse drag-to-scroll with click suppression. Touch and pen keep native scrolling.
 *
 * - active: re-arms cleanup when the scroller goes away.
 * - axes(event): { x, y } elements to scroll horizontally / vertically for this
 *   press; null for an axis that cannot scroll. Default: the current target, x only.
 * - shouldStart(event): false leaves the press alone (e.g. it is on selectable text).
 *
 * A press moving at most DRAG_THRESHOLD_PX stays a click; a real drag swallows the
 * click that ends it (onClickCapture), but never a keyboard activation (detail 0).
 */
export function useMouseDragScroll(active, { axes = defaultAxes, shouldStart = null } = {}) {
  const cleanup = useRef(null);
  const suppressClick = useRef(false);
  const [dragging, setDragging] = useState(false);

  useEffect(() => () => cleanup.current?.(), [active]);

  function onPointerDown(event) {
    suppressClick.current = false;
    if (event.pointerType !== "mouse" || event.button !== 0) return;
    cleanup.current?.();
    const scroller = event.currentTarget;
    // A press on the native scrollbar drags its thumb natively; a second drag
    // would fight it over the scroll offset.
    const rect = scroller.getBoundingClientRect?.();
    if (rect) {
      if (event.clientY - rect.top - (scroller.clientTop || 0) >= scroller.clientHeight) return;
      const relX = event.clientX - rect.left - (scroller.clientLeft || 0);
      if (Number.isFinite(relX) && scroller.clientWidth && (relX < 0 || relX >= scroller.clientWidth)) return;
    }
    if (shouldStart && !shouldStart(event)) return;
    const { x: xEl, y: yEl } = axes(event);
    if (!xEl && !yEl) return;
    const doc = scroller.ownerDocument;
    const { pointerId, clientX: startX, clientY: startY } = event;
    const startLeft = xEl ? xEl.scrollLeft : 0;
    const startTop = yEl ? yEl.scrollTop : 0;
    let started = false;

    function finish() {
      doc.removeEventListener("pointermove", move);
      doc.removeEventListener("pointerup", end);
      doc.removeEventListener("pointercancel", end);
      scroller.removeEventListener("lostpointercapture", end);
      cleanup.current = null;
      setDragging(false);
      if (scroller.hasPointerCapture(pointerId)) scroller.releasePointerCapture(pointerId);
    }

    function move(pointer) {
      if (pointer.pointerId !== pointerId) return;
      if (!(pointer.buttons & 1)) {
        finish();
        return;
      }
      const dx = pointer.clientX - startX;
      const dy = pointer.clientY - startY;
      if (!started) {
        const moved = Math.max(xEl ? Math.abs(dx) : 0, yEl ? Math.abs(dy) : 0);
        if (moved <= DRAG_THRESHOLD_PX) return;
        started = true;
        suppressClick.current = true;
        scroller.setPointerCapture(pointerId);
        setDragging(true);
        doc.getSelection()?.removeAllRanges();
      }
      pointer.preventDefault();
      // RTL scrollLeft is zero or negative; content follows the hand in either direction.
      if (xEl) xEl.scrollLeft = startLeft - dx;
      if (yEl) yEl.scrollTop = startTop - dy;
    }

    function end(pointer) {
      if (pointer.pointerId === pointerId) finish();
    }

    // Track this mouse only, including a release outside the scroller before capture.
    doc.addEventListener("pointermove", move, { passive: false });
    doc.addEventListener("pointerup", end);
    doc.addEventListener("pointercancel", end);
    scroller.addEventListener("lostpointercapture", end);
    cleanup.current = finish;
  }

  function onClickCapture(event) {
    if (!suppressClick.current) return;
    suppressClick.current = false;
    // Keyboard activation has no pointer click count, even after a cancelled drag.
    if (event.detail === 0) return;
    event.preventDefault();
    event.stopPropagation();
  }

  return { dragging, onPointerDown, onClickCapture };
}

/** The nearest ancestor of `from` (up to, excluding, `stop`) that scrolls horizontally. */
export function horizontalScroller(from, stop) {
  for (let node = from; node && node !== stop; node = node.parentElement) {
    if (node.scrollWidth > node.clientWidth && /(auto|scroll)/.test(getComputedStyle(node).overflowX)) return node;
  }
  return null;
}
