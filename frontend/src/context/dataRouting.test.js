import { describe, it, expect } from "vitest";
import {
  backendFetchesBlocked,
  canFetchQaSurface,
  isConsumerSession,
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
