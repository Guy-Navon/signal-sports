import { describe, it, expect } from "vitest";
import {
  authPagesRedundant,
  deriveAuthView,
  requiresLoginRedirect,
} from "./authView";

// AuthContext branching contract (issue #51): enforced vs bypass vs local.

describe("deriveAuthView", () => {
  it("local mode is authless and never fetches", () => {
    const view = deriveAuthView("local", null);
    expect(view).toEqual({
      mode: "local",
      authEnforced: false,
      user: null,
      onboarding: null,
    });
  });

  it("backend mode without a bootstrap payload is loading", () => {
    expect(deriveAuthView("backend", null).mode).toBe("loading");
  });

  it("bypass: backend reports auth_enforced=false → pre-auth UI branch", () => {
    const view = deriveAuthView("backend", {
      auth_enforced: false,
      user: null,
      onboarding: null,
    });
    expect(view.mode).toBe("bypass");
    expect(view.authEnforced).toBe(false);
  });

  it("enforced + user: exposes user and onboarding block", () => {
    const onboarding = { completed: false, calibration: { answered: 0, total: 24 } };
    const view = deriveAuthView("backend", {
      auth_enforced: true,
      user: { id: "usr_1", email: "a@b.c", role: "user" },
      onboarding,
    });
    expect(view.mode).toBe("enforced");
    expect(view.user.id).toBe("usr_1");
    expect(view.onboarding).toEqual(onboarding);
  });
});

describe("requiresLoginRedirect", () => {
  it("redirects only when enforced and anonymous", () => {
    expect(
      requiresLoginRedirect(deriveAuthView("backend", { auth_enforced: true, user: null })),
    ).toBe(true);
    expect(
      requiresLoginRedirect(
        deriveAuthView("backend", { auth_enforced: true, user: { id: "u" } }),
      ),
    ).toBe(false);
    expect(
      requiresLoginRedirect(deriveAuthView("backend", { auth_enforced: false, user: null })),
    ).toBe(false);
    expect(requiresLoginRedirect(deriveAuthView("local", null))).toBe(false);
  });
});

describe("authPagesRedundant", () => {
  it("login/signup are redundant in local and bypass modes", () => {
    expect(authPagesRedundant(deriveAuthView("local", null))).toBe(true);
    expect(
      authPagesRedundant(deriveAuthView("backend", { auth_enforced: false, user: null })),
    ).toBe(true);
  });

  it("login/signup are shown to anonymous users under enforcement", () => {
    expect(
      authPagesRedundant(deriveAuthView("backend", { auth_enforced: true, user: null })),
    ).toBe(false);
  });

  it("signed-in users bounce back to the feed; loading never redirects", () => {
    expect(
      authPagesRedundant(
        deriveAuthView("backend", { auth_enforced: true, user: { id: "u" } }),
      ),
    ).toBe(true);
    expect(authPagesRedundant(deriveAuthView("backend", null))).toBe(false);
  });
});
