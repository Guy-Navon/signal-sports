// Pure data-routing decisions for the consumer/QA split (User Platform PR 5,
// #53). AppContext consumes these; extracted so the split contract is
// unit-testable in the repo's node-environment vitest setup.
//
// The invariant this file protects: PRODUCT identity (the session user) and
// QA view-as identity (the ops ProfileSwitcher target) are DIFFERENT states.
// They were one state ("activeProfileId") in the pre-auth app; under
// enforcement they must never collapse back into one.

// A consumer session exists only under real enforcement with a signed-in user
// in backend mode. Local mode and bypass keep the legacy single-identity app.
export function isConsumerSession({ isBackendMode, authEnforced, user }) {
  return Boolean(isBackendMode && authEnforced && user);
}

// Which identity feeds the PRODUCT surface (Feed/Preferences/Calibration)?
export function productDataSource(view) {
  return isConsumerSession(view) ? "me" : "legacy";
}

// May this client fetch the admin/QA surface (profiles list, debug feed)?
// Consumer sessions with role=user must never issue {user_id} calls — the
// backend would 403 them and the product would surface errors.
export function canFetchQaSurface(view) {
  if (!isConsumerSession(view)) return true; // local / bypass: today's app
  return view.user?.role === "admin";
}

// Does the product masthead show the ProfileSwitcher? Only outside consumer
// sessions (local/bypass keep today's UI). Ops always shows it — there it is
// the admin "QA view-as" control, not a product identity.
export function productShowsProfileSwitcher(view) {
  return !isConsumerSession(view);
}

// Should backend fetches wait? Under enforcement with no user yet (login
// screen / bootstrap), the app must stay quiet instead of firing {user_id}
// calls that 401 and loop the session-expiry redirect.
export function backendFetchesBlocked({ isBackendMode, authStatus, authEnforced, user }) {
  if (!isBackendMode) return false;
  if (authStatus === "loading") return true;
  return Boolean(authEnforced && !user);
}
