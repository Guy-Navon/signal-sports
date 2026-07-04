import { describe, it, expect } from "vitest";
import { composeEdition } from "./editionComposer";

const mk = (id, decision) => ({ id, score: { decision } });

describe("composeEdition", () => {
  it("takes the first push as lead and the rest as bulletins", () => {
    const items = [mk("p1", "push"), mk("p2", "push"), mk("h1", "high_feed"), mk("f1", "feed")];
    const ed = composeEdition(items);
    expect(ed.lead.id).toBe("p1");
    expect(ed.bulletins.map((i) => i.id)).toEqual(["p2"]);
    expect(ed.editorial.map((i) => i.id)).toEqual(["h1"]);
    expect(ed.stream.map((i) => i.id)).toEqual(["f1"]);
  });

  it("promotes the first high_feed to lead when there is no push", () => {
    const items = [mk("h1", "high_feed"), mk("h2", "high_feed"), mk("f1", "feed")];
    const ed = composeEdition(items);
    expect(ed.lead.id).toBe("h1");
    expect(ed.bulletins).toEqual([]);
    expect(ed.editorial.map((i) => i.id)).toEqual(["h2"]);
  });

  it("has no lead when nothing rises above feed", () => {
    const items = [mk("f1", "feed"), mk("l1", "low_feed"), mk("l2", "low_feed")];
    const ed = composeEdition(items);
    expect(ed.lead).toBeNull();
    expect(ed.stream.map((i) => i.id)).toEqual(["f1"]);
    expect(ed.briefs.map((i) => i.id)).toEqual(["l1", "l2"]);
  });

  it("preserves the incoming order inside every tier (stable partition)", () => {
    const items = [
      mk("f1", "feed"),
      mk("p1", "push"),
      mk("f2", "feed"),
      mk("h1", "high_feed"),
      mk("f3", "feed"),
    ];
    const ed = composeEdition(items);
    expect(ed.stream.map((i) => i.id)).toEqual(["f1", "f2", "f3"]);
  });

  it("drops hidden and undecided items defensively", () => {
    const items = [mk("x", "hidden"), { id: "y", score: {} }, mk("f1", "feed")];
    const ed = composeEdition(items);
    expect(ed.lead).toBeNull();
    expect(ed.stream.map((i) => i.id)).toEqual(["f1"]);
    expect(ed.briefs).toEqual([]);
  });

  it("handles an empty feed", () => {
    expect(composeEdition([])).toEqual({
      lead: null,
      bulletins: [],
      editorial: [],
      stream: [],
      briefs: [],
    });
  });
});
