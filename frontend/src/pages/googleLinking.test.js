import { describe, it, expect } from "vitest";
import { LINK_CODES, isLinkCode, linkNoticeMessage } from "./googleLinking";

// Connect / disconnect Google (#330): the callback reports back as
// /account?google=linked or /account?google=link_<reason>.

describe("isLinkCode", () => {
  it("claims only the connect flow's codes", () => {
    expect(isLinkCode("linked")).toBe(true);
    expect(isLinkCode("link_taken")).toBe(true);
    expect(isLinkCode("delete_wrong_account")).toBe(false);
    expect(isLinkCode("cancelled")).toBe(false);
    expect(isLinkCode(null)).toBe(false);
  });
});

describe("linkNoticeMessage", () => {
  it("has a distinct Hebrew message for every code the callback sends", () => {
    const texts = LINK_CODES.map(linkNoticeMessage);
    texts.forEach((t) => expect(t).toMatch(/[\u0590-\u05FF]/));
    expect(new Set(texts).size).toBe(texts.length);
  });

  it("explains a Google account that belongs to someone else", () => {
    expect(linkNoticeMessage("link_taken")).toContain("חשבון אחר");
  });

  it("falls back to the generic failure for an unknown link code", () => {
    expect(linkNoticeMessage("link_something_new")).toBe(linkNoticeMessage("link_failed"));
  });
});
