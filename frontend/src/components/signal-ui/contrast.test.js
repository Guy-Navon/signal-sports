import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("./signal-ui.css", import.meta.url), "utf8");
const blocks = [...css.matchAll(/\.signal-ui(?:\[data-ground="(soft|dark)"\])?\s*\{([^}]+)\}/g)];
const grounds = Object.fromEntries(blocks.map(([, ground, block]) => [ground || "light",
  Object.fromEntries([...block.matchAll(/--sg-([\w-]+):\s*(#[\da-f]{6})\s*;/gi)].map(([, key, value]) => [key, value])),
]));

function luminance(hex) {
  const [r, g, b] = hex.slice(1).match(/../g).map((part) => {
    const channel = parseInt(part, 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return r * 0.2126 + g * 0.7152 + b * 0.0722;
}

function contrast(first, second) {
  const a = luminance(first), b = luminance(second);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

describe("Signal ground WCAG AA contrast", () => {
  it("measures all three declared grounds", () => {
    expect(Object.keys(grounds)).toEqual(["light", "soft", "dark"]);
  });
  for (const ground of ["light", "soft", "dark"]) {
    it(`${ground}: hot, dim and accent pass small text on the page, card, band and hover tint`, () => {
      const tokens = grounds[ground];
      for (const ink of ["hot", "dim", "acc"]) {
        for (const surface of ["bg", "card", "band", "tint"]) {
          expect(contrast(tokens[ink], tokens[surface]), `${ink} on ${surface}`).toBeGreaterThanOrEqual(4.5);
        }
      }
      expect(contrast(tokens["hot-fg"], tokens.hot), "hot label").toBeGreaterThanOrEqual(4.5);
      // Current push marks also appear on the lead label's slab-fg ground.
      expect(contrast(tokens.hot, tokens["slab-fg"]), "push label dot").toBeGreaterThanOrEqual(3);
    });
  }

  // The logo (#491): the app icon's three bars. Non-text, so 3:1 (WCAG 1.4.11)
  // against every ground it sits on, and against the navy header.
  for (const ground of ["light", "soft", "dark"]) {
    it(`${ground}: the logo bars and the header text pass on their grounds`, () => {
      const tokens = grounds[ground];
      for (const bar of ["logo-a", "logo-b"]) {
        for (const surface of ["bg", "card", "band"]) {
          expect(contrast(tokens[bar], tokens[surface]), `${bar} on ${surface}`).toBeGreaterThanOrEqual(3);
        }
        expect(contrast(tokens[`top-${bar}`], tokens.top), `top-${bar} on top`).toBeGreaterThanOrEqual(3);
      }
      // Inactive tabs are 15px bold text: AA for small text.
      expect(contrast(tokens["top-dim"], tokens.top), "top-dim on top").toBeGreaterThanOrEqual(4.5);
      expect(contrast(tokens["top-fg"], tokens.top), "top-fg on top").toBeGreaterThanOrEqual(4.5);
    });
  }
});
