// Pure routing decisions for the onboarding state machine (User Platform
// PR 4, #52). States are DERIVED, never stored:
//   UNAUTHENTICATED  → handled by RequireSession (login redirect)
//   NEEDS_ONBOARDING → session + onboarding.completed=false + 0 answers
//   CALIBRATING      → session + onboarding.completed=false + ≥1 answer
//   ACTIVE           → onboarding.completed=true
//
// Demo users never enter this machine (they cannot log in); env-bootstrapped
// admins are stamped complete at creation and ops identities skip the
// consumer funnel by role as defense-in-depth.

export function onboardingState(view) {
  if (!view.authEnforced || !view.user) return "UNAUTHENTICATED";
  const block = view.onboarding;
  if (!block || block.completed) return "ACTIVE";
  const answered = block.calibration?.answered ?? 0;
  return answered === 0 ? "NEEDS_ONBOARDING" : "CALIBRATING";
}

// Where should the router send this visitor? null = stay put.
export function onboardingRedirect(view, pathname) {
  if (view.user?.role === "admin") return null; // ops identity, not the consumer funnel
  const state = onboardingState(view);
  if (state === "NEEDS_ONBOARDING") {
    // Welcome first; going straight to calibration is also entering the flow.
    return pathname === "/welcome" || pathname === "/calibration" ? null : "/welcome";
  }
  if (state === "CALIBRATING") {
    // Resume where the answers are. The welcome screen is behind them now.
    return pathname === "/calibration" ? null : "/calibration";
  }
  return null; // ACTIVE / UNAUTHENTICATED (handled elsewhere)
}

// The feed's uncalibrated state (explicit product decision: an intentionally
// empty feed with a persistent calibrate CTA — never a generic fallback feed).
export function showCalibrateEmptyState(view) {
  if (!view.authEnforced || !view.user || view.user.role === "admin") return false;
  const answered = view.onboarding?.calibration?.answered ?? 0;
  return answered === 0;
}

// First unanswered calibration item id (resume anchor), or null.
export function firstUnansweredItemId(items, ratings) {
  const item = (items || []).find((i) => !(i.id in (ratings || {})));
  return item ? item.id : null;
}
