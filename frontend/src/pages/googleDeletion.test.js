import { describe, it, expect } from "vitest";
import {
  ACCOUNT_GOOGLE_CODES,
  captureAccountGoogleState,
  deletionNoticeMessage,
  forgetAccountGoogleState,
  matchesAccountEmail,
} from "./googleDeletion";

// Self-deletion of a Google-only account (#331): what the Account page does
// with the callback's /account?delete=confirm and /account?google=<code>.

describe("captureAccountGoogleState", () => {
  it("reads a confirmed Google round trip", () => {
    forgetAccountGoogleState();
    expect(captureAccountGoogleState("?delete=confirm")).toEqual({ confirm: true, code: null });
  });

  it("reads a failure code", () => {
    forgetAccountGoogleState();
    expect(captureAccountGoogleState("?google=delete_wrong_account"))
      .toEqual({ confirm: false, code: "delete_wrong_account" });
  });

  it("survives the page remounting after the URL was cleaned", () => {
    forgetAccountGoogleState();
    captureAccountGoogleState("?delete=confirm");
    expect(captureAccountGoogleState("")).toEqual({ confirm: true, code: null });
    forgetAccountGoogleState();
    expect(captureAccountGoogleState("")).toEqual({ confirm: false, code: null });
  });
});

describe("deletionNoticeMessage", () => {
  it("has a distinct Hebrew message for every code the callback sends", () => {
    const texts = ACCOUNT_GOOGLE_CODES.map(deletionNoticeMessage);
    texts.forEach((t) => expect(t).toMatch(/[\u0590-\u05FF]/));
    expect(new Set(texts).size).toBe(texts.length);
  });

  it("names the wrong-account case so the person can pick the right one", () => {
    expect(deletionNoticeMessage("delete_wrong_account")).toContain("Google");
  });

  it("falls back to the generic failure for an unknown code", () => {
    expect(deletionNoticeMessage("brand_new")).toBe(deletionNoticeMessage("failed"));
  });
});

describe("matchesAccountEmail", () => {
  it("ignores case and surrounding spaces, like the server", () => {
    expect(matchesAccountEmail("  Leaver@Gmail.com ", "leaver@gmail.com")).toBe(true);
    expect(matchesAccountEmail("other@gmail.com", "leaver@gmail.com")).toBe(false);
    expect(matchesAccountEmail("", "leaver@gmail.com")).toBe(false);
  });
});
