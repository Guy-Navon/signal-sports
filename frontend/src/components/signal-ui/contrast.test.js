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
});
