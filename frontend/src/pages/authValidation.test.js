import { describe, it, expect } from "vitest";
import {
  authErrorMessage,
  hasErrors,
  signupErrorMessage,
  validateLoginForm,
  validateSignupForm,
} from "./authValidation";

// Login/signup form validation states (issue #51).

describe("validateLoginForm", () => {
  it("requires both fields", () => {
    const errors = validateLoginForm({ email: "", password: "" });
    expect(errors.email).toBeTruthy();
    expect(errors.password).toBeTruthy();
    expect(hasErrors(errors)).toBe(true);
  });

  it("rejects malformed email shapes (backend parity)", () => {
    expect(validateLoginForm({ email: "nope", password: "x" }).email).toBeTruthy();
    expect(validateLoginForm({ email: "@nope", password: "x" }).email).toBeTruthy();
    expect(validateLoginForm({ email: "nope@", password: "x" }).email).toBeTruthy();
  });

  it("accepts a valid form", () => {
    expect(
      hasErrors(validateLoginForm({ email: "a@b.co", password: "secret" })),
    ).toBe(false);
  });
});

describe("validateSignupForm", () => {
  it("enforces the backend's 8-character password minimum", () => {
    expect(
      validateSignupForm({ email: "a@b.co", password: "short" }).password,
    ).toBeTruthy();
    expect(
      hasErrors(validateSignupForm({ email: "a@b.co", password: "long enough" })),
    ).toBe(false);
  });
});

describe("authErrorMessage", () => {
  it("maps backend statuses to product-voice Hebrew", () => {
    expect(authErrorMessage(new Error("API POST /api/auth/login failed (401): x")))
      .toBe("אימייל או סיסמה שגויים");
    expect(authErrorMessage(new Error("API POST /api/auth/signup failed (409): x")))
      .toBe("כתובת האימייל כבר רשומה במערכת");
    expect(authErrorMessage(new Error("API POST /api/auth/login failed (429): x")))
      .toContain("יותר מדי");
    expect(authErrorMessage(new Error("Cannot reach backend at /api/auth/login: x")))
      .toBe("לא ניתן להתחבר לשרת כרגע");
  });
});

describe("signupErrorMessage", () => {
  const err = (status, detail) => new Error(`API POST /api/auth/signup failed (${status}): ${detail}`);

  it("explains each signup refusal", () => {
    expect(signupErrorMessage(err(403, "Signup is closed"))).toBe("ההרשמה סגורה לכתובת הזאת");
    expect(signupErrorMessage(err(429, "Too many signup attempts"))).toContain("יותר מדי");
    expect(signupErrorMessage(err(503, "Email delivery is not configured"))).toContain("אימיילים");
  });

  it("falls back to the shared auth notices", () => {
    expect(signupErrorMessage(err(409, "Email already in use")))
      .toBe("כתובת האימייל כבר רשומה במערכת");
  });
});
