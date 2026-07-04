import { describe, it, expect } from "vitest";
import { buildKicker, condensedReason, entityLabel } from "./storyLabels";

describe("buildKicker", () => {
  it("uses mapped entity + event type", () => {
    const item = {
      entities: ["Maccabi Tel Aviv Basketball"],
      league: "EuroLeague",
      sport: "basketball",
      eventType: "negotiation",
    };
    expect(buildKicker(item)).toBe("מכבי ת״א · מו״מ");
  });

  it("skips unmapped English entities and falls back to the league", () => {
    const item = {
      entities: ["Some Unknown Club"],
      league: "NBA",
      sport: "basketball",
      eventType: "injury",
    };
    expect(buildKicker(item)).toBe("NBA · פציעה");
  });

  it("falls back to sport when league is unmapped", () => {
    const item = { entities: [], league: "Obscure League", sport: "tennis", eventType: "injury" };
    expect(buildKicker(item)).toBe("טניס · פציעה");
  });

  it("omits filler event types but keeps the subject", () => {
    const item = { entities: [], league: "NBA", sport: "basketball", eventType: "generic_preview" };
    expect(buildKicker(item)).toBe("NBA");
  });

  it("returns null when nothing meaningful can be said", () => {
    expect(buildKicker({ entities: [], sport: "unknown", eventType: "generic_news" })).toBeNull();
    expect(buildKicker({})).toBeNull();
  });
});

describe("condensedReason", () => {
  it("prefers the quoted topic label from the engine", () => {
    const reasoning = [
      'נושא: "מכבי תל אביב כדורסל" (עדיפות 100)',
      "החלטה סופית: push",
    ];
    expect(condensedReason(reasoning)).toBe("מכבי תל אביב כדורסל");
  });

  it("falls back to the most specific non-final line", () => {
    const reasoning = ["שלב 1", "שלב 2 ספציפי", "החלטה סופית: feed"];
    expect(condensedReason(reasoning)).toBe("שלב 2 ספציפי");
  });

  it("returns null for empty reasoning", () => {
    expect(condensedReason([])).toBeNull();
    expect(condensedReason(undefined)).toBeNull();
  });
});

describe("entityLabel", () => {
  it("maps known entities to Hebrew and passes unknown through", () => {
    expect(entityLabel("Deni Avdija")).toBe("דני אבדיה");
    expect(entityLabel("Unknown Person")).toBe("Unknown Person");
  });
});
