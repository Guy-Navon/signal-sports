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

// Does the product masthead show the ProfileSwitcher? Local/bypass keep it
// always (today's UI). Under a consumer session only admins get it — for an
// admin it doubles as the product-page "view any user's feed" control, not
// just the ops QA view-as control. Non-admin consumer sessions never see it:
// their product feed is always their own (/api/me/feed).
export function productShowsProfileSwitcher(view) {
  if (!isConsumerSession(view)) return true;
  return view.user?.role === "admin";
}

// Should backend fetches wait? Under enforcement with no user yet (login
// screen / bootstrap), the app must stay quiet instead of firing {user_id}
// calls that 401 and loop the session-expiry redirect.
export function backendFetchesBlocked({ isBackendMode, authStatus, authEnforced, user }) {
  if (!isBackendMode) return false;
  if (authStatus === "loading") return true;
  return Boolean(authEnforced && !user);
}

// Which surface serves the consumer Preferences learning panel?
// Consumer sessions (ANY role — an admin using the consumer product reads the
// authenticated account's own state, never the QA view-as target) use the
// session-derived /me learning routes. Legacy explicit-target learning calls
// are QA behavior and exist only outside consumer sessions (local/bypass).
// The function deliberately takes no view-as identity: QA view-as state must
// be UNABLE to influence the consumer surface by construction.
export function learningSurface(view) {
  return isConsumerSession(view) ? "me" : "legacy";
}

// May this visitor enter the frontend ops console shell? Local/bypass keep
// today's open console; under a consumer session only admins enter. Defense
// in depth only — the backend admin gates remain authoritative.
export function canEnterOpsShell(view) {
  if (!isConsumerSession(view)) return true;
  return view.user?.role === "admin";
}
