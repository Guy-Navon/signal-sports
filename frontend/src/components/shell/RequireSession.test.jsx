import React from "react";
import { act, create } from "react-test-renderer";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

// The two route guards rendered inside a real router, so each case asserts the
// page a visitor actually lands on. Only the session hook is stubbed; the
// redirect rules (authView, onboardingFlow, dataRouting) are the real ones.

const state = vi.hoisted(() => ({ auth: /** @type {any} */ (null) }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => state.auth }));

function Landed() {
  const location = useLocation();
  return <p data-landed={location.pathname}>{location.pathname}</p>;
}

let renderer;
afterEach(() => {
  if (renderer) act(() => renderer.unmount());
  renderer = null;
  vi.unstubAllEnvs();
});

async function guards(mode) {
  vi.stubEnv("VITE_DATA_MODE", mode);
  vi.resetModules();
  const { default: RequireSession } = await import("./RequireSession");
  const { default: RequireOpsRole } = await import("./RequireOpsRole");
  return { RequireSession, RequireOpsRole };
}

async function visit(path, auth, mode = "backend") {
  if (renderer) act(() => renderer.unmount());
  state.auth = auth;
  const { RequireSession, RequireOpsRole } = await guards(mode);
  act(() => {
    renderer = create(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/login" element={<Landed />} />
          <Route path="/welcome" element={<Landed />} />
          <Route element={<RequireSession />}>
            <Route path="/" element={<Landed />} />
            <Route path="/results" element={<Landed />} />
            <Route path="/interests" element={<Landed />} />
            <Route path="/preferences" element={<Landed />} />
            <Route path="/preferences/calibration" element={<Landed />} />
            <Route element={<RequireOpsRole />}>
              <Route path="/ops" element={<Landed />} />
            </Route>
          </Route>
        </Routes>
      </MemoryRouter>,
    );
  });
  const landed = renderer.root.findAll((node) => node.props["data-landed"] !== undefined);
  return landed.length ? landed[0].props["data-landed"] : null;
}

const enforced = (user, onboarding = { completed: true }) => ({
  status: "ready", mode: "enforced", authEnforced: true, user, onboarding,
});
const READER = { id: "u1", role: "user" };
const ADMIN = { id: "a1", role: "admin" };

describe("RequireSession", () => {
  it("renders nothing while the session is still loading — no flash of private content", async () => {
    expect(await visit("/results", { status: "loading", mode: "loading", authEnforced: false, user: null })).toBeNull();
    expect(renderer.toJSON()).toBeNull();
  });

  it("sends an anonymous visitor to /login under enforcement", async () => {
    expect(await visit("/results", enforced(null, null))).toBe("/login");
  });

  it("lets a fully onboarded reader through to the page they asked for", async () => {
    expect(await visit("/results", enforced(READER))).toBe("/results");
  });

  it("passes everyone through in local and bypass modes", async () => {
    expect(await visit("/results", { status: "ready", mode: "local", authEnforced: false, user: null }, "")).toBe("/results");
    expect(await visit("/results", { status: "ready", mode: "bypass", authEnforced: false, user: null })).toBe("/results");
  });

  describe("onboarding funnel", () => {
    const fresh = { completed: false, interests: { completed: false, selected: 0 }, calibration: { answered: 0 } };
    const picking = { completed: false, interests: { completed: false, selected: 2 }, calibration: { answered: 0 } };
    const calibrating = { completed: false, interests: { completed: true, selected: 3 }, calibration: { answered: 4 } };

    it("a brand-new reader starts at /welcome", async () => {
      expect(await visit("/", enforced(READER, fresh))).toBe("/welcome");
    });

    it("a new reader may enter the funnel at interests directly", async () => {
      expect(await visit("/interests", enforced(READER, fresh))).toBe("/interests");
    });

    it("a reader mid-way through interests resumes at /preferences", async () => {
      expect(await visit("/results", enforced(READER, picking))).toBe("/preferences");
    });

    it("a reader who chose interests resumes calibration, and may revisit interests", async () => {
      expect(await visit("/", enforced(READER, calibrating))).toBe("/preferences/calibration");
      expect(await visit("/interests", enforced(READER, calibrating))).toBe("/interests");
    });

    it("an admin is never pulled into the consumer funnel", async () => {
      expect(await visit("/results", enforced(ADMIN, fresh))).toBe("/results");
    });
  });
});

// RequireOpsRole reads VITE_DATA_MODE in a form vi.stubEnv cannot reach
// (#577), so its data mode here comes from the developer's .env.local, not
// from guards(mode). Only cases whose answer is the same in every data mode
// are asserted; the backend-only reader redirect waits for #577.
describe("RequireOpsRole", () => {
  it("lets an admin into the console", async () => {
    expect(await visit("/ops", enforced(ADMIN))).toBe("/ops");
  });

  it("keeps the console open when no consumer session is enforced", async () => {
    expect(await visit("/ops", { status: "ready", mode: "local", authEnforced: false, user: null }, "")).toBe("/ops");
    expect(await visit("/ops", { status: "ready", mode: "bypass", authEnforced: false, user: null })).toBe("/ops");
  });

  // Passes only where .env.local sets backend mode; un-skip with the #577 fix.
  it.skip("routes a signed-in reader back to the product (#577)", async () => {
    expect(await visit("/ops", enforced(READER))).toBe("/");
  });
});
