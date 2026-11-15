import { describe, expect, it } from "vitest";
import { deskVoiceView } from "./deskVoiceModel";

const trace = ["פרופיל (v2): Guy", "בסיס: עוקב (high) אחרי EuroLeague (via_team_membership: comp:euroleague) → 2 נק'", "ניקוד: 3 → חשוב", "החלטה סופית: חשוב"];

describe("deskVoiceView (journey audit D6)", () => {
  it("a reader gets the Hebrew reason and no trace", () => {
    const v = deskVoiceView({ showTrace: false, reason: "מכבי תל אביב (כדורסל) ברשימת המעקב שלך", reasoning: trace });
    expect(v).toEqual({ mode: "reader", text: "מכבי תל אביב (כדורסל) ברשימת המעקב שלך", steps: [] });
  });

  it("a reader with no accurate reason gets nothing, never the trace", () => {
    expect(deskVoiceView({ showTrace: false, reason: null, reasoning: trace })).toBeNull();
  });

  it("admins and local QA get the same reader sentence on the consumer feed", () => {
    const v = deskVoiceView({ showTrace: true, reason: "x", reasoning: trace });
    expect(v).toEqual({ mode: "reader", text: "x", steps: [] });
  });

  it("admins with no reader sentence get nothing even with a full trace", () => {
    expect(deskVoiceView({ showTrace: true, reason: null, reasoning: trace })).toBeNull();
  });
});
