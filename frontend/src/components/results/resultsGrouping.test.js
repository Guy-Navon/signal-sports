import { describe, it, expect } from "vitest";
import { sortGames, groupByDay } from "./resultsGrouping";

const game = (id, startTime) => ({ id, startTime });

describe("sortGames", () => {
  it("orders newest first and sinks undated games", () => {
    const out = sortGames([
      game("a", "2026-04-08T18:00:00+00:00"),
      game("b", null),
      game("c", "2026-04-10T18:00:00+00:00"),
    ]);
    expect(out.map((g) => g.id)).toEqual(["c", "a", "b"]);
  });
});

describe("groupByDay", () => {
  it("groups by Jerusalem day, newest day first, undated last", () => {
    const groups = groupByDay([
      game("apr8", "2026-04-08T18:00:00+00:00"),
      game("apr10-late", "2026-04-10T20:00:00+00:00"),
      game("apr10-early", "2026-04-10T06:00:00+00:00"),
      game("undated", null),
    ]);
    expect(groups.map((g) => g.dayKey)).toEqual(["2026-04-10", "2026-04-08", null]);
    // Within Apr 10, newest first.
    expect(groups[0].games.map((g) => g.id)).toEqual(["apr10-late", "apr10-early"]);
    expect(groups[2].games.map((g) => g.id)).toEqual(["undated"]);
  });

  it("returns an empty array for no games", () => {
    expect(groupByDay([])).toEqual([]);
  });
});
