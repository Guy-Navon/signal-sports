import { expect, it, vi } from "vitest";
import { pointIsOnText } from "./pointerText";

const text = (value = "שלום") => ({ nodeType: 3, nodeValue: value });
const rectDoc = (node, rects, api = "caretPositionFromPoint") => ({
  [api]: () => (api === "caretPositionFromPoint" ? { offsetNode: node } : { startContainer: node }),
  createRange: () => ({ selectNodeContents: vi.fn(), getClientRects: () => rects }),
});
const box = { left: 10, right: 50, top: 10, bottom: 24 };

it.each(["caretPositionFromPoint", "caretRangeFromPoint"])("is text inside a glyph box and empty outside it (%s)", api => {
  const doc = rectDoc(text(), [box], api);
  expect(pointIsOnText(doc, 30, 17)).toBe(true);
  expect(pointIsOnText(doc, 80, 17)).toBe(false); // nearest text is elsewhere
  expect(pointIsOnText(doc, 30, 40)).toBe(false);
});

it("checks every line box of wrapped text", () => {
  const doc = rectDoc(text(), [box, { left: 10, right: 30, top: 26, bottom: 40 }]);
  expect(pointIsOnText(doc, 20, 33)).toBe(true);
  expect(pointIsOnText(doc, 45, 33)).toBe(false);
});

it("treats whitespace-only and non-text nodes as empty", () => {
  expect(pointIsOnText(rectDoc(text("  \n "), [box]), 30, 17)).toBe(false);
  expect(pointIsOnText(rectDoc({ nodeType: 1 }, [box]), 30, 17)).toBe(false);
  expect(pointIsOnText({ caretPositionFromPoint: () => null }, 30, 17)).toBe(false);
});

it("falls back to text when unsure: no API, thrown error, bad point, form field", () => {
  expect(pointIsOnText({}, 30, 17)).toBe(true);
  expect(pointIsOnText({ caretPositionFromPoint: () => { throw new Error("x"); } }, 30, 17)).toBe(true);
  expect(pointIsOnText(rectDoc(text(), [box]), NaN, 17)).toBe(true);
  expect(pointIsOnText(rectDoc(text(), []), 30, 17, { tagName: "INPUT" })).toBe(true);
});
