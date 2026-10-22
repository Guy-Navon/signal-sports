import { describe, it, expect } from "vitest";
import {
  FORGOT_SENT_MESSAGE,
  captureResetToken,
  forgetResetToken,
  resetErrorMessage,
} from "./passwordReset";

// Password reset by email (#200): the /reset-password#t=<token> link and the
// Hebrew outcome messages.

const apiError = (status, detail = "x") =>
  new Error(`API POST /api/auth/password/reset failed (${status}): ${detail}`);

describe("captureResetToken", () => {
  it("survives the page remounting after the fragment was cleared", () => {
    forgetResetToken();
    expect(captureResetToken("#t=abc")).toBe("abc");
    expect(captureResetToken("")).toBe("abc");
    forgetResetToken();
    expect(captureResetToken("")).toBeNull();
  });
});

describe("resetErrorMessage", () => {
  it("explains each outcome", () => {
    expect(resetErrorMessage(apiError(400))).toContain("הקישור");
    expect(resetErrorMessage(apiError(404))).toContain("הקישור");
    expect(resetErrorMessage(apiError(422))).toContain("8");
    expect(resetErrorMessage(apiError(503))).toContain("אימיילים");
    expect(resetErrorMessage(new Error("Cannot reach backend at /api"))).toBe("לא ניתן להתחבר לשרת כרגע");
  });
});

describe("FORGOT_SENT_MESSAGE", () => {
  it("never says whether an account exists", () => {
    expect(FORGOT_SENT_MESSAGE).toContain("אם");
  });
});
