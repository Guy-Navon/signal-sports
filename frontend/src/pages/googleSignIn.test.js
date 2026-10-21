import { describe, it, expect } from "vitest";
import {
  GOOGLE_NOTICE_CODES,
  accountHasPassword,
  captureGoogleNotice,
  dismissGoogleNotice,
  googleNoticeMessage,
  readGoogleNotice,
} from "./googleSignIn";

// Google sign-in: the fixed /login?google=<code> notices from the callback,
// and how the Account page treats accounts without a password.

describe("readGoogleNotice", () => {
  it("reads the callback's code from the query string", () => {
    expect(readGoogleNotice("?google=cancelled")).toBe("cancelled");
    expect(readGoogleNotice("?x=1&google=account_exists")).toBe("account_exists");
  });

  it("returns null without one", () => {
    expect(readGoogleNotice("")).toBeNull();
    expect(readGoogleNotice("?x=1")).toBeNull();
  });
});

describe("googleNoticeMessage", () => {
  it("has a distinct Hebrew next step for every code the backend sends", () => {
    const texts = GOOGLE_NOTICE_CODES.map(googleNoticeMessage);
    texts.forEach((text) => expect(text).toMatch(/[\u0590-\u05FF]/));
    expect(new Set(texts).size).toBe(texts.length);
  });

  it("tells an existing password account how to proceed, without linking", () => {
    expect(googleNoticeMessage("account_exists")).toContain("סיסמה");
  });

  it("points a non-Gmail Google account at password signup", () => {
    expect(googleNoticeMessage("unsupported_email")).toContain("הרשמה");
  });

  it("falls back to a generic notice for an unknown code", () => {
    expect(googleNoticeMessage("something_new")).toBe(googleNoticeMessage("failed"));
  });
});

describe("accountHasPassword", () => {
  it("is false only when the backend says so", () => {
    expect(accountHasPassword({ has_password: false })).toBe(false);
    expect(accountHasPassword({ has_password: true })).toBe(true);
    // A backend that predates the field: every account had a password.
    expect(accountHasPassword({})).toBe(true);
  });
});

describe("captureGoogleNotice", () => {
  it("survives the login page remounting after the code left the URL", () => {
    dismissGoogleNotice();
    expect(captureGoogleNotice("?google=cancelled")).toBe("cancelled");
    expect(captureGoogleNotice("")).toBe("cancelled");
  });

  it("is cleared once dismissed, and a new code replaces an old one", () => {
    captureGoogleNotice("?google=expired");
    expect(captureGoogleNotice("?google=account_exists")).toBe("account_exists");
    dismissGoogleNotice();
    expect(captureGoogleNotice("")).toBeNull();
  });
});
