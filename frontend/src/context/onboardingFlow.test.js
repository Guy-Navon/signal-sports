import { describe, it, expect } from "vitest";
import {
  firstUnansweredItemId,
  onboardingRedirect,
  onboardingState,
  showCalibrateEmptyState,
} from "./onboardingFlow";

// The derived onboarding state machine (issue #52):
// UNAUTHENTICATED → NEEDS_ONBOARDING → CALIBRATING → ACTIVE.

const user = { id: "usr_1", role: "user" };
const admin = { id: "usr_a", role: "admin" };

function view({ enforced = true, u = user, completed = false, answered = 0 } = {}) {
  return {
    authEnforced: enforced,
    user: u,
    onboarding: u
      ? { completed, calibration: { answered, total: 24 } }
      : null,
  };
}

describe("onboardingState", () => {
  it("derives all four states from the session block", () => {
    expect(onboardingState(view({ u: null }))).toBe("UNAUTHENTICATED");
    expect(onboardingState(view({ answered: 0 }))).toBe("NEEDS_ONBOARDING");
    expect(onboardingState(view({ answered: 3 }))).toBe("CALIBRATING");
    expect(onboardingState(view({ completed: true, answered: 3 }))).toBe("ACTIVE");
  });

  it("bypass mode never enters the machine", () => {
    expect(onboardingState(view({ enforced: false }))).toBe("UNAUTHENTICATED");
  });
});

describe("onboardingRedirect", () => {
  it("NEEDS_ONBOARDING routes everything to /welcome except the flow itself", () => {
    expect(onboardingRedirect(view(), "/")).toBe("/welcome");
    expect(onboardingRedirect(view(), "/preferences")).toBe("/welcome");
    expect(onboardingRedirect(view(), "/welcome")).toBe(null);
    expect(onboardingRedirect(view(), "/calibration")).toBe(null);
  });

  it("CALIBRATING resumes at the calibration page", () => {
    const v = view({ answered: 5 });
    expect(onboardingRedirect(v, "/")).toBe("/calibration");
    expect(onboardingRedirect(v, "/welcome")).toBe("/calibration");
    expect(onboardingRedirect(v, "/calibration")).toBe(null);
  });

  it("ACTIVE and admins are never redirected", () => {
    expect(onboardingRedirect(view({ completed: true }), "/")).toBe(null);
    expect(onboardingRedirect(view({ u: admin }), "/")).toBe(null);
  });
});

describe("showCalibrateEmptyState", () => {
  it("uncalibrated consumer sessions get the calibrate CTA species", () => {
    expect(showCalibrateEmptyState(view({ completed: true, answered: 0 }))).toBe(true);
    expect(showCalibrateEmptyState(view({ answered: 0 }))).toBe(true);
  });

  it("calibrated users, admins, bypass and anonymous get the default species", () => {
    expect(showCalibrateEmptyState(view({ completed: true, answered: 4 }))).toBe(false);
    expect(showCalibrateEmptyState(view({ u: admin }))).toBe(false);
    expect(showCalibrateEmptyState(view({ enforced: false }))).toBe(false);
    expect(showCalibrateEmptyState(view({ u: null }))).toBe(false);
  });
});

describe("firstUnansweredItemId", () => {
  const items = [{ id: "a" }, { id: "b" }, { id: "c" }];
  it("finds the resume anchor", () => {
    expect(firstUnansweredItemId(items, { a: "x" })).toBe("b");
    expect(firstUnansweredItemId(items, {})).toBe("a");
    expect(firstUnansweredItemId(items, { a: "x", b: "x", c: "x" })).toBe(null);
  });
});
