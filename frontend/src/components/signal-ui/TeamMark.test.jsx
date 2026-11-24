import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it } from "vitest";
import TeamMark, { TeamChip, TeamEdge } from "./TeamMark";

let renderer;
afterEach(() => {
  if (renderer) act(() => renderer.unmount());
  renderer = null;
});

function render(element) {
  if (renderer) act(() => renderer.unmount());
  act(() => {
    renderer = create(element);
  });
  return renderer;
}

const team = (overrides = {}) => ({
  teamId: "team:maccabi_tlv_bb",
  sport: "basketball",
  displayHe: "מכבי תל אביב",
  primary: "#FFD100",
  secondary: "#003DA5",
  code: "MTA",
  number: null,
  personDisplayHe: null,
  ...overrides,
});
const portland = team({
  teamId: "team:portland_blazers", displayHe: "פורטלנד בלייזרס", primary: "#E03A3E", secondary: "#000000",
  code: "POR", number: "8", personDisplayHe: "דני אבדיה",
});
const lakers = team({ teamId: "team:la_lakers", displayHe: "לוס אנג'לס לייקרס", primary: "#552583", secondary: "#FDB927", code: "LAL" });

const img = () => renderer.root.findByProps({ role: "img" });
const chest = () => renderer.root.findAllByType("text");
const textOf = (node) => (typeof node === "string" ? node : (node.children ?? []).map(textOf).join(""));

it("draws one club's jersey, named for the club, with its code on the chest in the chosen ink", () => {
  render(<TeamMark mark={{ teams: [team()] }} />);
  expect(img().props["aria-label"]).toBe("מכבי תל אביב");
  expect(renderer.root.findAllByProps({ "data-shape": "tank" })).toHaveLength(1);
  expect(chest().map((node) => node.children)).toEqual([["MTA"]]);
  expect(chest()[0].props.fill).toBe("#003DA5");
  expect(chest()[0].props.fontSize).toBe("10.5");
});

it("puts a known player number on the chest instead of the code, and in the name", () => {
  render(<TeamMark mark={{ teams: [portland] }} />);
  expect(img().props["aria-label"]).toBe("פורטלנד בלייזרס · 8");
  expect(chest().map((node) => node.children)).toEqual([["8"]]);
  expect(chest()[0].props.fill).toBe("#000000");
});

it("leaves the chest empty with no code and no number", () => {
  render(<TeamMark mark={{ teams: [team({ code: null })] }} />);
  expect(chest()).toHaveLength(0);
});

it("draws only the first of two teams", () => {
  render(<TeamMark mark={{ teams: [portland, lakers] }} />);
  expect(renderer.root.findAllByProps({ "data-shape": "tank" })).toHaveLength(1);
  expect(img().props["aria-label"]).toBe("פורטלנד בלייזרס · 8");
});

it("draws a sleeved shirt for a football team", () => {
  render(<TeamMark mark={{ teams: [team({ sport: "football", displayHe: "מכבי חיפה", primary: "#00703C", secondary: "#FFFFFF" })] }} />);
  expect(renderer.root.findAllByProps({ "data-shape": "shirt" })).toHaveLength(1);
  expect(renderer.root.findAllByProps({ "data-shape": "tank" })).toHaveLength(0);
});

it("the chip names the followed player, else the club, and adds the second team", () => {
  render(<TeamChip mark={{ teams: [team()] }} />);
  expect(textOf(renderer.toJSON())).toBe("מכבי תל אביב");
  render(<TeamChip mark={{ teams: [portland, lakers] }} />);
  expect(textOf(renderer.toJSON())).toBe("דני אבדיה· גם לוס אנג'לס לייקרס");
});

it("the edge carries the first team's colours and is hidden from assistive tech", () => {
  render(<TeamEdge mark={{ teams: [portland, lakers] }} />);
  const edge = renderer.toJSON();
  expect(edge.props["aria-hidden"]).toBe(true);
  expect(edge.props.style).toEqual({ "--sg-team-p": "#E03A3E", "--sg-team-s": "#000000" });
});

it("renders nothing at all when the model abstains", () => {
  for (const Part of [TeamMark, TeamChip, TeamEdge]) {
    render(<Part mark={null} />);
    expect(renderer.toJSON()).toBeNull();
  }
});
