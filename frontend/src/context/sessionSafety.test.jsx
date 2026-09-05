import React from "react";
import { act, create } from "react-test-renderer";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ getAuthSession: vi.fn() }));
vi.mock("@/api/client", () => ({
  ...api, AUTH_EXPIRED_EVENT: "signal:auth-expired",
  authLogin: vi.fn(), authLogout: vi.fn(), authSignup: vi.fn(),
}));

let renderer;
afterEach(() => {
  if (renderer) act(() => renderer.unmount());
  renderer = null;
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetAllMocks();
});

describe("session bootstrap failure", () => {
  it("blocks children after a network failure and recovers through retry", async () => {
    vi.stubEnv("VITE_DATA_MODE", "backend");
    vi.stubGlobal("window", new EventTarget());
    vi.resetModules();
    const { AuthProvider } = await import("./AuthContext");
    api.getAuthSession.mockRejectedValueOnce(new Error("offline"));
    await act(async () => {
      renderer = create(<MemoryRouter><AuthProvider><p data-private>Private app</p></AuthProvider></MemoryRouter>);
    });
    expect(renderer.root.findAllByProps({ "data-private": true })).toHaveLength(0);
    expect(renderer.root.findAllByProps({ role: "alert" })).toHaveLength(1);
    api.getAuthSession.mockResolvedValueOnce({ auth_enforced: true, user: { id: "u" } });
    await act(async () => { await renderer.root.findByType("button").props.onClick(); });
    expect(renderer.root.findAllByProps({ "data-private": true })).toHaveLength(1);
  });
});
