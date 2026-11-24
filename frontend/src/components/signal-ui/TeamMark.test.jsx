import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it } from "vitest";
import TeamMark from "./TeamMark";

let renderer;
afterEach(() => {
  if (renderer) act(() => renderer.unmount());
  renderer = null;
});

function render(mark) {
  if (renderer) act(() => renderer.unmount());
  act(() => {
    renderer = create(<TeamMark mark={mark} />);
  });
  return renderer;
}

const team = (overrides = {}) => ({
  teamId: "team:maccabi_tlv_bb",
  sport: "basketball",
  displayHe: "מכבי תל אביב",
  primary: "#FFD100",
  secondary: "#003DA5",
  number: null,
  personDisplayHe: null,
  ...overrides,
});

const img = () => renderer.root.findByProps({ role: "img" });

it("names a single team", () => {
  render({ kind: "teams", teams: [team()] });
  expect(img().props["aria-label"]).toBe("מכבי תל אביב");
  expect(renderer.root.findAllByProps({ "data-shape": "tank" })).toHaveLength(1);
});

it("names a numbered player's team with the number, and draws the number in the chosen ink", () => {
  render({ kind: "teams", teams: [team({ number: "8", personDisplayHe: "שחקן" })] });
  expect(img().props["aria-label"]).toBe("מכבי תל אביב · 8");
  const number = renderer.root.findByType("text");
  expect(number.children).toEqual(["8"]);
  expect(number.props.fill).toBe("#003DA5");
});

it("names two teams joined with ו and draws two jerseys", () => {
  render({
    kind: "teams",
    teams: [
      team({ teamId: "team:portland_blazers", displayHe: "פורטלנד בלייזרס", primary: "#E03A3E", secondary: "#000000" }),
      team({ teamId: "team:la_lakers", displayHe: "לוס אנג'לס לייקרס", primary: "#552583", secondary: "#FDB927" }),
    ],
  });
  expect(img().props["aria-label"]).toBe("פורטלנד בלייזרס ולוס אנג'לס לייקרס");
  expect(renderer.root.findAllByProps({ "data-shape": "tank" })).toHaveLength(2);
});

it("draws a sleeved shirt for a football team", () => {
  render({ kind: "teams", teams: [team({ sport: "football", displayHe: "מכבי חיפה", primary: "#00703C", secondary: "#FFFFFF" })] });
  expect(renderer.root.findAllByProps({ "data-shape": "shirt" })).toHaveLength(1);
  expect(renderer.root.findAllByProps({ "data-shape": "tank" })).toHaveLength(0);
});

it("names the neutral sport glyph", () => {
  render({ kind: "sport", sport: "basketball" });
  expect(img().props["aria-label"]).toBe("כדורסל");
  render({ kind: "sport", sport: "football" });
  expect(img().props["aria-label"]).toBe("כדורגל");
});

it("renders nothing when the model abstains", () => {
  render(null);
  expect(renderer.toJSON()).toBeNull();
});
