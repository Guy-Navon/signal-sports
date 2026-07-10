// Pure derivation of the auth shell's view state (User Platform PR 3, #51).
// Extracted from AuthContext so the branching contract is unit-testable in
// the repo's node-environment vitest setup (no jsdom renderer in this repo).
//
// Runtime-adaptive contract (docs/USER_PLATFORM.md):
// - local data mode        → authless, exactly today's UI, no session fetch;
// - backend + bypass       → backend reports auth_enforced=false → today's UI;
// - backend + enforcement  → session-gated product: anonymous users are
//                            routed to /login; authenticated users get the
//                            product plus an account menu.

export function deriveAuthView(dataMode, bootstrap) {
  if (dataMode !== "backend") {
    // Local demo mode stays fully authless — no fetch ever happens.
    return { mode: "local", authEnforced: false, user: null, onboarding: null };
  }
  if (!bootstrap) {
    return { mode: "loading", authEnforced: false, user: null, onboarding: null };
  }
  return {
    mode: bootstrap.auth_enforced ? "enforced" : "bypass",
    authEnforced: Boolean(bootstrap.auth_enforced),
    user: bootstrap.user || null,
    onboarding: bootstrap.onboarding || null,
  };
}

// Should the router send this visitor to /login?
export function requiresLoginRedirect(view) {
  return view.mode === "enforced" && !view.user;
}

// Should the auth pages bounce an already-satisfied visitor back to the feed?
// (Login/signup are meaningless in local/bypass modes and for signed-in users.)
export function authPagesRedundant(view) {
  if (view.mode === "loading") return false;
  return view.mode !== "enforced" || Boolean(view.user);
}
