import { describe, it, expect } from "vitest";
import {
  RESEND_COOLDOWN_SECONDS,
  captureVerificationToken,
  forgetVerificationToken,
  isUnverifiedLogin,
  readVerificationToken,
  resendSecondsLeft,
  verificationErrorMessage,
} from "./emailVerification";

// Email verification for password signups: link parsing and the Hebrew
// notices for each backend outcome.

const apiError = (status, detail, path = "/api/auth/verification/confirm") =>
  new Error(`API POST ${path} failed (${status}): ${detail}`);

describe("readVerificationToken", () => {
  it("reads the token from the fragment", () => {
    expect(readVerificationToken("#t=abc_DEF-123")).toBe("abc_DEF-123");
  });

  it("returns null when there is no token", () => {
    expect(readVerificationToken("")).toBeNull();
    expect(readVerificationToken("#")).toBeNull();
    expect(readVerificationToken("#x=1")).toBeNull();
  });
});

describe("isUnverifiedLogin", () => {
  it("recognizes the not-yet-verified login answer", () => {
    expect(isUnverifiedLogin(apiError(403, "Email not verified", "/api/auth/login"))).toBe(true);
  });

  it("does not confuse it with other failures", () => {
    expect(isUnverifiedLogin(apiError(401, "Invalid email or password", "/api/auth/login"))).toBe(false);
    expect(isUnverifiedLogin(apiError(403, "Signup is closed", "/api/auth/signup"))).toBe(false);
    expect(isUnverifiedLogin(null)).toBe(false);
  });
});

describe("verificationErrorMessage", () => {
  it("maps each confirmation outcome to its own next step", () => {
    expect(verificationErrorMessage(apiError(400, "Verification link is invalid or expired")))
      .toContain("הקישור");
    expect(verificationErrorMessage(apiError(403, "Password is incorrect")))
      .toBe("הסיסמה שגויה");
    expect(verificationErrorMessage(apiError(409, "Email already in use")))
      .toContain("כבר קיים");
    expect(verificationErrorMessage(apiError(429, "Please wait before resending")))
      .toContain("רגע");
    expect(verificationErrorMessage(apiError(503, "Email delivery is not configured")))
      .toContain("לא ניתן לשלוח");
  });

  it("says when the server is unreachable", () => {
    expect(verificationErrorMessage(new Error("Cannot reach backend at /api: x")))
      .toBe("לא ניתן להתחבר לשרת כרגע");
  });
});

describe("resendSecondsLeft", () => {
  it("counts down from the last send and never goes negative", () => {
    const sentAt = 1_000_000;
    expect(resendSecondsLeft(sentAt, sentAt)).toBe(RESEND_COOLDOWN_SECONDS);
    expect(resendSecondsLeft(sentAt, sentAt + 59_500)).toBe(1);
    expect(resendSecondsLeft(sentAt, sentAt + 60_000)).toBe(0);
    expect(resendSecondsLeft(null, sentAt)).toBe(0);
  });
});

describe("captureVerificationToken", () => {
  it("keeps the token after the fragment is cleared (the page can remount)", () => {
    forgetVerificationToken();
    expect(captureVerificationToken("#t=abc")).toBe("abc");
    // The first mount removed the fragment; a remount must still find it.
    expect(captureVerificationToken("")).toBe("abc");
  });

  it("a newer link replaces the remembered token, and forgetting clears it", () => {
    captureVerificationToken("#t=old");
    expect(captureVerificationToken("#t=new")).toBe("new");
    forgetVerificationToken();
    expect(captureVerificationToken("")).toBeNull();
  });
});
