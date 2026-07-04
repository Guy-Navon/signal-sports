// Framer Motion variants for the edition. All movement is y-axis only —
// deliberately no x translations anywhere, which sidesteps RTL mirroring.
// Callers pass the result of useReducedMotion(); reduced mode falls back to
// short opacity-only fades (the global CSS media query handles CSS animations).

export const EASE_SOFT = [0.22, 1, 0.36, 1];

export function editionVariants(reduce) {
  if (reduce) {
    const fade = {
      hidden: { opacity: 0 },
      show: { opacity: 1, transition: { duration: 0.15 } },
    };
    return { container: { hidden: {}, show: {} }, item: fade, headline: fade };
  }

  return {
    container: {
      hidden: {},
      show: { transition: { staggerChildren: 0.07, delayChildren: 0.04 } },
    },
    item: {
      hidden: { opacity: 0, y: 16 },
      show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: EASE_SOFT } },
    },
    // The lead headline reveal: rise + blur-to-sharp. Used once per edition.
    headline: {
      hidden: { opacity: 0, y: 20, filter: "blur(8px)" },
      show: {
        opacity: 1,
        y: 0,
        filter: "blur(0px)",
        transition: { duration: 0.65, ease: EASE_SOFT },
      },
    },
  };
}

// Row-level presence transition for filter recomposition.
export function rowPresence(reduce) {
  if (reduce) {
    return {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
      transition: { duration: 0.12 },
    };
  }
  return {
    initial: { opacity: 0, y: 10 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, transition: { duration: 0.15 } },
    transition: { duration: 0.3, ease: EASE_SOFT },
  };
}
