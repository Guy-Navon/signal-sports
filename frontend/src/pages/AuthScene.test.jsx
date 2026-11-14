import React from "react";
import { act, create } from "react-test-renderer";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import AuthScene from "@/pages/AuthScene";
import Onboarding from "@/pages/Onboarding";
import PageNotFound from "@/lib/PageNotFound";
import { GROUND_STORAGE_KEY } from "@/components/signal-ui/ground";

vi.mock("@/context/AppContext", () => ({ useApp: () => ({ activeProfile: null }) }));
vi.mock("@/context/AuthContext", () => ({ useAuth: () => ({ user: null, refreshSession: vi.fn() }) }));
vi.mock("@/api/client", () => ({ completeMeOnboarding: vi.fn() }));

/** @param {string | null} stored */
function storeGround(stored) {
  vi.stubGlobal("window", {
    localStorage: {
      getItem: (key) => (key === GROUND_STORAGE_KEY ? stored : null),
      setItem: () => {},
    },
  });
}

/** The data-ground of the one `.signal-ui` root a screen renders. */
function renderedGround(element) {
  /** @type {import("react-test-renderer").ReactTestRenderer} */
  let renderer = /** @type {any} */ (null);
  act(() => {
    renderer = create(<MemoryRouter>{element}</MemoryRouter>);
  });
  const roots = renderer.root.findAll((node) =>
    typeof node.type === "string" && String(node.props.className ?? "").split(" ").includes("signal-ui"));
  const grounds = roots.map((node) => node.props["data-ground"]);
  act(() => renderer.unmount());
  return grounds;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// #504: the standalone consumer screens (login family, 404, welcome) follow the
// ground the reader picked in the shell, and stay white when nothing is stored.
describe("standalone screens follow the chosen ground", () => {
  const screens = {
    "auth scene": <AuthScene title="התחברות"><p>x</p></AuthScene>,
    "404": <PageNotFound />,
    welcome: <Onboarding />,
  };

  for (const [name, element] of Object.entries(screens)) {
    it(`${name}: uses the stored ground`, () => {
      for (const ground of ["soft", "dark", "light"]) {
        storeGround(ground);
        expect(renderedGround(element)).toEqual([ground]);
      }
    });

    it(`${name}: stays white with nothing stored, a bad value or no storage`, () => {
      storeGround(null);
      expect(renderedGround(element)).toEqual(["light"]);
      storeGround("neon");
      expect(renderedGround(element)).toEqual(["light"]);
      vi.stubGlobal("window", {
        get localStorage() { throw new Error("SecurityError"); },
      });
      expect(renderedGround(element)).toEqual(["light"]);
    });
  }
});
