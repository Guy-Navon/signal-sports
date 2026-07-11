// Pure routing decisions for the onboarding state machine (User Platform
// PR 4, #52; extended by Explicit Interests, #82). States are DERIVED,
// never stored:
//   UNAUTHENTICATED     → handled by RequireSession (login redirect)
//   NEEDS_ONBOARDING    → session + interests not completed + 0 answers
//   SELECTING_INTERESTS → session + interests not completed (in the funnel)
//   CALIBRATING         → session + interests completed + not onboarded
//   ACTIVE              → onboarding.completed=true
//
// interests.completed comes from the bootstrap (#77): explicit stamp OR the
// legacy rule (onboarding completed before the interests stage existed) —
// legacy users are never re-funneled.
//
// Demo users never enter this machine (they cannot log in); env-bootstrapped
// admins are stamped complete at creation and ops identities skip the
// consumer funnel by role as defense-in-depth.

export function onboardingState(view) {
  if (!view.authEnforced || !view.user) return "UNAUTHENTICATED";
  const block = view.onboarding;
  if (!block || block.completed) return "ACTIVE";
  const interestsDone = block.interests?.completed ?? false;
  const answered = block.calibration?.answered ?? 0;
  if (!interestsDone) {
    return answered === 0 && (block.interests?.selected ?? 0) === 0
      ? "NEEDS_ONBOARDING"
      : "SELECTING_INTERESTS";
  }
  return "CALIBRATING";
}

// Where should the router send this visitor? null = stay put.
export function onboardingRedirect(view, pathname) {
  if (view.user?.role === "admin") return null; // ops identity, not the consumer funnel
  const state = onboardingState(view);
  const inFunnelEntrance = ["/welcome", "/interests", "/calibration"].includes(pathname);
  if (state === "NEEDS_ONBOARDING") {
    // Welcome first; entering anywhere in the funnel is fine too.
    return inFunnelEntrance ? null : "/welcome";
  }
  if (state === "SELECTING_INTERESTS") {
    return inFunnelEntrance ? null : "/interests";
  }
  if (state === "CALIBRATING") {
    // Resume at calibration; revisiting interests mid-flow stays allowed.
    return pathname === "/calibration" || pathname === "/interests"
      ? null
      : "/calibration";
  }
  return null; // ACTIVE / UNAUTHENTICATED (handled elsewhere)
}

// The feed's empty state. Since #82, explicit interests alone produce a
// REAL feed (interests-only feed is valid — supersedes the #52 skip
// decision), so the calibrate CTA shows only when the user has neither
// calibration answers NOR explicit follows.
export function showCalibrateEmptyState(view) {
  if (!view.authEnforced || !view.user || view.user.role === "admin") return false;
  const answered = view.onboarding?.calibration?.answered ?? 0;
  const selected = view.onboarding?.interests?.selected ?? 0;
  return answered === 0 && selected === 0;
}

// First unanswered calibration item id (resume anchor), or null.
export function firstUnansweredItemId(items, ratings) {
  const item = (items || []).find((i) => !(i.id in (ratings || {})));
  return item ? item.id : null;
}
