import React from "react";
import { act, create } from "react-test-renderer";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

// The session provider's flows beyond bootstrap failure (sessionSafety.test):
// local passthrough, the derived view, login/logout, verification, session
// expiry and stale responses. Only the HTTP client is stubbed; routing is a
// real MemoryRouter so redirects are observed where the reader would land.

const EXPIRED = "signal:auth-expired";
const api = vi.hoisted(() => ({
  getAuthSession: vi.fn(),
  authLogin: vi.fn(),
  authLogout: vi.fn(),
  authSignup: vi.fn(),
  authVerificationConfirm: vi.fn(),
}));
vi.mock("@/api/client", () => ({ ...api, AUTH_EXPIRED_EVENT: "signal:auth-expired" }));

const seen = { auth: /** @type {any} */ (null), location: /** @type {any} */ (null) };
// Re-imported per test after vi.resetModules so the data-mode stub applies.
/** @type {typeof import("./AuthContext").useAuth} */
let useAuth;
let renderer;

function Probe() {
  seen.auth = useAuth();
  seen.location = useLocation();
  return <p data-page={seen.location.pathname}>{seen.auth.user?.id ?? "anon"}</p>;
}

afterEach(() => {
  if (renderer) act(() => renderer.unmount());
  renderer = null;
  seen.auth = null;
  seen.location = null;
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.resetAllMocks();
});

async function mount(mode, { path = "/" } = {}) {
  vi.stubEnv("VITE_DATA_MODE", mode);
  vi.stubGlobal("window", new EventTarget());
  vi.resetModules();
  const mod = await import("./AuthContext");
  useAuth = mod.useAuth;
  const { AuthProvider } = mod;
  await act(async () => {
    renderer = create(
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <Routes>
            <Route path="*" element={<Probe />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
  });
}

const SESSION = {
  auth_enforced: true,
  user: { id: "u1", role: "user", email: "reader@example.test" },
  onboarding: { completed: true },
};

describe("local mode", () => {
  it("renders the app immediately, never asks the server, and reports an authless view", async () => {
    await mount("");
    expect(api.getAuthSession).not.toHaveBeenCalled();
    expect(seen.auth).toMatchObject({ status: "ready", mode: "local", authEnforced: false, user: null });
    expect(await seen.auth.refreshSession()).toBeNull();
    expect(api.getAuthSession).not.toHaveBeenCalled();
  });

  it("ignores a session-expired event", async () => {
    await mount("", { path: "/feed" });
    await act(async () => { window.dispatchEvent(new Event(EXPIRED)); });
    expect(seen.location.pathname).toBe("/feed");
  });
});

describe("backend bootstrap", () => {
  it("is loading until the session answers, then exposes the user and server flags", async () => {
    let answer = (_value) => {};
    api.getAuthSession.mockImplementationOnce(() => new Promise((resolve) => { answer = resolve; }));
    await mount("backend");
    expect(seen.auth).toMatchObject({ status: "loading", mode: "loading", user: null });

    await act(async () => {
      answer({ ...SESSION, signup_enabled: false, signup_by_invitation: true, google_enabled: true });
    });
    expect(seen.auth).toMatchObject({
      status: "ready",
      mode: "enforced",
      authEnforced: true,
      user: SESSION.user,
      onboarding: SESSION.onboarding,
      signupEnabled: false,
      signupByInvitation: true,
      googleEnabled: true,
    });
    expect(api.getAuthSession).toHaveBeenCalledTimes(1);
  });

  it("treats a backend that reports no enforcement as the open bypass view", async () => {
    api.getAuthSession.mockResolvedValueOnce({ auth_enforced: false, user: null });
    await mount("backend");
    expect(seen.auth).toMatchObject({ status: "ready", mode: "bypass", authEnforced: false, signupEnabled: true });
  });
});

describe("login, signup and verification", () => {
  it("login posts the credentials, then re-reads the session so the user appears", async () => {
    api.getAuthSession.mockResolvedValueOnce({ auth_enforced: true, user: null });
    await mount("backend", { path: "/login" });
    expect(renderer.root.findByType("p").children).toEqual(["anon"]);

    api.authLogin.mockResolvedValueOnce({});
    api.getAuthSession.mockResolvedValueOnce(SESSION);
    await act(async () => { await seen.auth.login("reader@example.test", "סיסמה-ארוכה"); });
    expect(api.authLogin).toHaveBeenCalledWith("reader@example.test", "סיסמה-ארוכה");
    expect(api.getAuthSession).toHaveBeenCalledTimes(2);
    expect(renderer.root.findByType("p").children).toEqual(["u1"]);
  });

  it("a rejected login surfaces the error and leaves the session untouched", async () => {
    api.getAuthSession.mockResolvedValueOnce({ auth_enforced: true, user: null });
    await mount("backend", { path: "/login" });
    api.authLogin.mockRejectedValueOnce(new Error("אימייל או סיסמה שגויים"));
    await act(async () => {
      await expect(seen.auth.login("reader@example.test", "wrong")).rejects.toThrow("אימייל או סיסמה שגויים");
    });
    expect(api.getAuthSession).toHaveBeenCalledTimes(1);
    expect(seen.auth.user).toBeNull();
  });

  it("signup only starts a pending registration — no session refresh", async () => {
    api.getAuthSession.mockResolvedValueOnce({ auth_enforced: true, user: null });
    await mount("backend", { path: "/signup" });
    api.authSignup.mockResolvedValueOnce({ status: "pending", email: "new@example.test" });
    const result = await seen.auth.signup({ email: "new@example.test", password: "pw-long-enough", displayName: "קורא" });
    expect(result).toEqual({ status: "pending", email: "new@example.test" });
    expect(api.authSignup).toHaveBeenCalledWith({ email: "new@example.test", password: "pw-long-enough", displayName: "קורא" });
    expect(api.getAuthSession).toHaveBeenCalledTimes(1);
  });

  it("confirming the emailed link signs the reader in", async () => {
    api.getAuthSession.mockResolvedValueOnce({ auth_enforced: true, user: null });
    await mount("backend", { path: "/verify-email" });
    api.authVerificationConfirm.mockResolvedValueOnce({});
    api.getAuthSession.mockResolvedValueOnce(SESSION);
    await act(async () => { await seen.auth.confirmVerification("tok-1", "pw-long-enough"); });
    expect(api.authVerificationConfirm).toHaveBeenCalledWith("tok-1", "pw-long-enough");
    expect(seen.auth.user).toEqual(SESSION.user);
  });
});

describe("logout", () => {
  it("under enforcement, clears the user and lands on /login", async () => {
    api.getAuthSession.mockResolvedValueOnce(SESSION);
    await mount("backend", { path: "/feed" });
    api.authLogout.mockResolvedValueOnce(null);
    api.getAuthSession.mockResolvedValueOnce({ auth_enforced: true, user: null });
    await act(async () => { await seen.auth.logout(); });
    expect(seen.auth.user).toBeNull();
    expect(seen.location.pathname).toBe("/login");
  });

  it("re-reads the session and redirects even when the logout request fails", async () => {
    api.getAuthSession.mockResolvedValueOnce(SESSION);
    await mount("backend", { path: "/feed" });
    api.authLogout.mockRejectedValueOnce(new Error("network"));
    api.getAuthSession.mockResolvedValueOnce({ auth_enforced: true, user: null });
    await act(async () => {
      await expect(seen.auth.logout()).rejects.toThrow("network");
    });
    expect(api.getAuthSession).toHaveBeenCalledTimes(2);
    expect(seen.location.pathname).toBe("/login");
  });

  it("in bypass mode stays on the current page", async () => {
    api.getAuthSession.mockResolvedValue({ auth_enforced: false, user: null });
    await mount("backend", { path: "/feed" });
    api.authLogout.mockResolvedValueOnce(null);
    await act(async () => { await seen.auth.logout(); });
    expect(seen.location.pathname).toBe("/feed");
  });
});

describe("session expiry", () => {
  it("drops the user and sends the reader to /login marked expired", async () => {
    api.getAuthSession.mockResolvedValueOnce(SESSION);
    await mount("backend", { path: "/results" });
    await act(async () => { window.dispatchEvent(new Event(EXPIRED)); });
    expect(seen.auth.user).toBeNull();
    expect(seen.auth.authEnforced).toBe(true);
    expect(seen.location.pathname).toBe("/login");
    expect(seen.location.state).toEqual({ expired: true });
  });

  it("does not redirect in bypass mode", async () => {
    api.getAuthSession.mockResolvedValueOnce({ auth_enforced: false, user: null });
    await mount("backend", { path: "/results" });
    await act(async () => { window.dispatchEvent(new Event(EXPIRED)); });
    expect(seen.location.pathname).toBe("/results");
  });

  it("a session response that was already in flight cannot resurrect the expired user", async () => {
    api.getAuthSession.mockResolvedValueOnce(SESSION);
    await mount("backend", { path: "/feed" });

    let late = (_value) => {};
    api.getAuthSession.mockImplementationOnce(() => new Promise((resolve) => { late = resolve; }));
    let pending;
    await act(async () => { pending = seen.auth.refreshSession(); });
    await act(async () => { window.dispatchEvent(new Event(EXPIRED)); });
    await act(async () => { late(SESSION); });

    await expect(pending).resolves.toBeNull();
    expect(seen.auth.user).toBeNull();
    expect(seen.location.pathname).toBe("/login");
  });
});

describe("failure screen", () => {
  it("is right-to-left Hebrew with a single alert", async () => {
    api.getAuthSession.mockRejectedValueOnce(new Error("offline"));
    await mount("backend");
    const main = renderer.root.findByType("main");
    expect(main.props.dir).toBe("rtl");
    expect(main.findByProps({ role: "alert" }).children).toEqual(["לא ניתן להתחבר לשרת. נסו שוב בעוד רגע."]);
    expect(main.findByType("button").children).toEqual(["ניסיון נוסף"]);
  });
});

it("useAuth outside the provider fails loudly instead of returning a fake session", async () => {
  vi.resetModules();
  const mod = await import("./AuthContext");
  function Orphan() { mod.useAuth(); return null; }
  vi.spyOn(console, "error").mockImplementation(() => {});
  expect(() => act(() => { create(<Orphan />); })).toThrow("useAuth must be used within AuthProvider");
});
