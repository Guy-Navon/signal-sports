import { useCallback, useEffect, useRef, useState } from "react";
import { nextBarShown } from "./productShellModel";

// Drives the slim sticky bar of the consumer header (#491). The expanded
// masthead stays in normal page flow and scrolls away; this hook watches the
// masthead's tabs with an IntersectionObserver (no scroll handler) whose root
// line sits at the bar's bottom edge, so the bar appears exactly as the tabs
// slide under it. The decision itself, with its hysteresis, is the pure
// nextBarShown. While keyboard focus or its open menu is inside the bar it
// stays shown, so keyboard focus is never left inside an inert, hidden bar.
export function useCollapsedBar(targetRef, barRef) {
  const [shown, setShown] = useState(false);
  const sample = useRef(null);
  const focusInside = useRef(false);
  const menuOpen = useRef(false);

  const decide = useCallback(() => {
    if (!sample.current) return;
    const holding = focusInside.current || menuOpen.current;
    setShown((current) => nextBarShown(current, { ...sample.current, holding }));
  }, []);

  useEffect(() => {
    const target = targetRef.current;
    const bar = barRef.current;
    if (!target || !bar || typeof IntersectionObserver === "undefined") return undefined;
    // The bar is laid out even while hidden (visibility only), so its height is
    // known before it ever shows.
    const barHeight = Math.round(bar.getBoundingClientRect().height);
    const observer = new IntersectionObserver(
      ([entry]) => {
        const ratio = entry.isIntersecting ? entry.intersectionRatio : 0;
        const rootTop = entry.rootBounds ? entry.rootBounds.top : barHeight;
        sample.current = {
          // Sub-pixel layouts can report 0.999… for a fully visible element.
          ratio: ratio >= 0.99 ? 1 : ratio,
          above: entry.boundingClientRect.top < rootTop,
        };
        decide();
      },
      { rootMargin: `-${barHeight}px 0px 0px 0px`, threshold: [0, 1] }
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [targetRef, barRef, decide]);

  useEffect(() => {
    const bar = barRef.current;
    if (!bar) return undefined;
    // Only keyboard focus holds the bar: after a pointer opened and closed the
    // menu, focus returns to the avatar, and scrolling back to the top must
    // still bring the masthead back.
    const onFocusIn = (event) => {
      const target = /** @type {Element} */ (event.target);
      focusInside.current = Boolean(target?.matches?.(":focus-visible"));
    };
    const onFocusOut = (event) => {
      if (bar.contains(/** @type {Node | null} */ (event.relatedTarget))) return;
      focusInside.current = false;
      decide();
    };
    bar.addEventListener("focusin", onFocusIn);
    bar.addEventListener("focusout", onFocusOut);
    return () => {
      bar.removeEventListener("focusin", onFocusIn);
      bar.removeEventListener("focusout", onFocusOut);
    };
  }, [barRef, decide]);

  // A hidden bar is inert: out of the tab order and the accessibility tree.
  useEffect(() => {
    const bar = barRef.current;
    if (bar) bar.inert = !shown;
  }, [barRef, shown]);

  const onMenuOpenChange = useCallback((open) => {
    menuOpen.current = open;
    decide();
  }, [decide]);

  return { shown, onMenuOpenChange };
}
