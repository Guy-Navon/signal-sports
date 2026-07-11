import { describe, it, expect } from "vitest";
import {
  firstUnansweredItemId,
  onboardingRedirect,
  onboardingState,
  showCalibrateEmptyState,
} from "./onboardingFlow";

// The derived onboarding state machine (issue #52, extended by #82):
// UNAUTHENTICATED → NEEDS_ONBOARDING → SELECTING_INTERESTS → CALIBRATING
// → ACTIVE. Interests completion drives the funnel split.

const user = { id: "usr_1", role: "user" };
const admin = { id: "usr_a", role: "admin" };

function view({
  enforced = true, u = user, completed = false, answered = 0,
  interestsCompleted = false, selected = 0,
} = {}) {
  return {
    authEnforced: enforced,
    user: u,
    onboarding: u
      ? {
          completed,
          calibration: { answered, total: 73 },
          interests: { completed: interestsCompleted, selected },
        }
      : null,
  };
}

describe("onboardingState", () => {
  it("derives all five states from the session block", () => {
    expect(onboardingState(view({ u: null }))).toBe("UNAUTHENTICATED");
    expect(onboardingState(view())).toBe("NEEDS_ONBOARDING");
    expect(onboardingState(view({ selected: 2 }))).toBe("SELECTING_INTERESTS");
    expect(onboardingState(view({ interestsCompleted: true }))).toBe("CALIBRATING");
    expect(onboardingState(view({ interestsCompleted: true, answered: 3 })))
      .toBe("CALIBRATING");
    expect(onboardingState(view({ completed: true, answered: 3 }))).toBe("ACTIVE");
  });

  it("legacy users (onboarding done before interests existed) are ACTIVE", () => {
    // The backend derives interests.completed=true from the legacy rule;
    // completed=true makes the whole machine ACTIVE regardless.
    expect(onboardingState(view({ completed: true, interestsCompleted: true })))
      .toBe("ACTIVE");
  });

  it("a legacy bootstrap WITHOUT an interests block still calibrates", () => {
    // Defensive: an old cached bootstrap shape must not crash the machine.
    const v = {
      authEnforced: true, user,
      onboarding: { completed: false, calibration: { answered: 2, total: 24 } },
    };
    expect(onboardingState(v)).toBe("SELECTING_INTERESTS");
  });

  it("bypass mode never enters the machine", () => {
    expect(onboardingState(view({ enforced: false }))).toBe("UNAUTHENTICATED");
  });
});

describe("onboardingRedirect", () => {
  it("NEEDS_ONBOARDING routes everything to /welcome except the funnel", () => {
    expect(onboardingRedirect(view(), "/")).toBe("/welcome");
    expect(onboardingRedirect(view(), "/preferences")).toBe("/welcome");
    expect(onboardingRedirect(view(), "/welcome")).toBe(null);
    expect(onboardingRedirect(view(), "/interests")).toBe(null);
    expect(onboardingRedirect(view(), "/calibration")).toBe(null);
  });

  it("SELECTING_INTERESTS resumes at /interests", () => {
    const v = view({ selected: 3 });
    expect(onboardingRedirect(v, "/")).toBe("/interests");
    expect(onboardingRedirect(v, "/interests")).toBe(null);
    expect(onboardingRedirect(v, "/calibration")).toBe(null);
  });

  it("CALIBRATING resumes at calibration; interests stays reachable", () => {
    const v = view({ interestsCompleted: true, answered: 5 });
    expect(onboardingRedirect(v, "/")).toBe("/calibration");
    expect(onboardingRedirect(v, "/welcome")).toBe("/calibration");
    expect(onboardingRedirect(v, "/calibration")).toBe(null);
    expect(onboardingRedirect(v, "/interests")).toBe(null);
  });

  it("ACTIVE and admins are never redirected", () => {
    expect(onboardingRedirect(view({ completed: true }), "/")).toBe(null);
    expect(onboardingRedirect(view({ u: admin }), "/")).toBe(null);
  });
});

describe("showCalibrateEmptyState", () => {
  it("shows only when the user has neither answers nor follows", () => {
    expect(showCalibrateEmptyState(view({ completed: true }))).toBe(true);
    expect(showCalibrateEmptyState(view())).toBe(true);
  });

  it("explicit follows alone dismiss the CTA (interests-only feed is valid)", () => {
    expect(showCalibrateEmptyState(
      view({ completed: true, interestsCompleted: true, selected: 3 }),
    )).toBe(false);
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
