import { describe, it, expect } from "vitest";
import {
  backendFetchesBlocked,
  canEnterOpsShell,
  canFetchQaSurface,
  isConsumerSession,
  learningSurface,
  productDataSource,
  productShowsProfileSwitcher,
} from "./dataRouting";

// The AppContext consumer/QA split contract (issue #53). The invariant:
// product identity (session user) and QA view-as identity must never
// collapse back into one state.

const LOCAL = { isBackendMode: false, authEnforced: false, user: null };
const BYPASS = { isBackendMode: true, authEnforced: false, user: null };
const ENFORCED_ANON = { isBackendMode: true, authEnforced: true, user: null };
const ENFORCED_USER = {
  isBackendMode: true, authEnforced: true, user: { id: "usr_1", role: "user" },
};
const ENFORCED_ADMIN = {
  isBackendMode: true, authEnforced: true, user: { id: "usr_a", role: "admin" },
};

describe("isConsumerSession / productDataSource", () => {
  it("local and bypass keep the legacy single-identity app", () => {
    expect(isConsumerSession(LOCAL)).toBe(false);
    expect(isConsumerSession(BYPASS)).toBe(false);
    expect(productDataSource(LOCAL)).toBe("legacy");
    expect(productDataSource(BYPASS)).toBe("legacy");
  });

  it("enforcement with a signed-in user routes the product to /me", () => {
    expect(productDataSource(ENFORCED_USER)).toBe("me");
    expect(productDataSource(ENFORCED_ADMIN)).toBe("me");
  });

  it("enforcement without a user is not a consumer session", () => {
    expect(isConsumerSession(ENFORCED_ANON)).toBe(false);
  });
});

describe("canFetchQaSurface", () => {
  it("bypass/local may fetch the QA surface (today's behavior)", () => {
    expect(canFetchQaSurface(LOCAL)).toBe(true);
    expect(canFetchQaSurface(BYPASS)).toBe(true);
  });

  it("consumer role=user must never issue {user_id}/admin calls", () => {
    expect(canFetchQaSurface(ENFORCED_USER)).toBe(false);
  });

  it("admins keep the QA surface (view-as, debug feeds)", () => {
    expect(canFetchQaSurface(ENFORCED_ADMIN)).toBe(true);
  });
});

describe("productShowsProfileSwitcher", () => {
  it("stays in the product masthead for local/bypass", () => {
    expect(productShowsProfileSwitcher(LOCAL)).toBe(true);
    expect(productShowsProfileSwitcher(BYPASS)).toBe(true);
  });

  it("leaves the product masthead under a consumer session (any role)", () => {
    expect(productShowsProfileSwitcher(ENFORCED_USER)).toBe(false);
    expect(productShowsProfileSwitcher(ENFORCED_ADMIN)).toBe(false);
  });
});

describe("backendFetchesBlocked", () => {
  it("local mode never blocks", () => {
    expect(backendFetchesBlocked({ ...LOCAL, authStatus: "loading" })).toBe(false);
  });

  it("blocks while the session bootstrap is in flight", () => {
    expect(
      backendFetchesBlocked({ isBackendMode: true, authStatus: "loading", authEnforced: false, user: null }),
    ).toBe(true);
  });

  it("blocks enforced-anonymous (login screen) so nothing 401-loops", () => {
    expect(
      backendFetchesBlocked({ isBackendMode: true, authStatus: "ready", authEnforced: true, user: null }),
    ).toBe(true);
  });

  it("unblocks bypass and signed-in enforcement", () => {
    expect(
      backendFetchesBlocked({ isBackendMode: true, authStatus: "ready", authEnforced: false, user: null }),
    ).toBe(false);
    expect(
      backendFetchesBlocked({ isBackendMode: true, authStatus: "ready", authEnforced: true, user: { id: "u" } }),
    ).toBe(false);
  });
});

describe("learningSurface (#54 review HIGH-1)", () => {
  it("consumer sessions read/reset ONLY the session account via /me — any role", () => {
    expect(learningSurface(ENFORCED_USER)).toBe("me");
    // An admin using the CONSUMER product sees the account's own state,
    // never the QA view-as target.
    expect(learningSurface(ENFORCED_ADMIN)).toBe("me");
  });

  it("QA view-as state cannot alter the consumer surface by construction", () => {
    // The decision takes no view-as identity at all — whatever activeProfileId
    // is, a consumer session resolves to the /me surface.
    for (const viewAs of ["guy", "casual_deni_fan", "anything"]) {
      void viewAs; // view-as is not even an input
      expect(learningSurface(ENFORCED_USER)).toBe("me");
    }
  });

  it("local/bypass keep the legacy explicit-target QA behavior", () => {
    expect(learningSurface(LOCAL)).toBe("legacy");
    expect(learningSurface(BYPASS)).toBe("legacy");
  });
});

describe("canEnterOpsShell (#54 review MEDIUM)", () => {
  it("local and bypass keep today's open console", () => {
    expect(canEnterOpsShell(LOCAL)).toBe(true);
    expect(canEnterOpsShell(BYPASS)).toBe(true);
  });

  it("consumer role=user is denied the ops shell", () => {
    expect(canEnterOpsShell(ENFORCED_USER)).toBe(false);
  });

  it("admins enter the ops console (QA view-as remains available)", () => {
    expect(canEnterOpsShell(ENFORCED_ADMIN)).toBe(true);
  });
});
