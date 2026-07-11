import { describe, it, expect } from "vitest";
import {
  buildPutPayload,
  competitionsForSport,
  documentToState,
  isFollowed,
  parentSuggestions,
  peopleForSelection,
  searchCatalog,
  teamsForSelection,
  toggleFollow,
  toggleStar,
} from "./interestsModel";

// A miniature catalog in the exact GET /api/taxonomy/catalog shape.
const catalog = {
  taxonomy_version: 1,
  sports: [
    {
      id: "basketball", display_he: "כדורסל", display_en: "Basketball",
      selectable: true,
      competitions: [
        { id: "comp:ibl", kind: "league", display_he: "ליגת ווינר סל",
          display_en: "Israeli Basketball League", selectable: true },
        { id: "comp:euroleague", kind: "international_league",
          display_he: "יורוליג", display_en: "EuroLeague", selectable: true },
      ],
    },
    {
      id: "football", display_he: "כדורגל", display_en: "Football",
      selectable: true,
      competitions: [
        { id: "comp:ligat_haal", kind: "league", display_he: "ליגת העל",
          display_en: "Israeli Premier League", selectable: true },
        { id: "comp:epl", kind: "league", display_he: "הפרמייר ליג",
          display_en: "Premier League", selectable: false },
      ],
    },
  ],
  teams: [
    { id: "team:hapoel_tlv_bb", sport: "basketball",
      display_he: "הפועל תל אביב", display_en: "Hapoel Tel Aviv",
      aliases: ["הפועל תל אביב", "hapoel tel aviv"],
      domestic_competition: "comp:ibl",
      memberships: ["comp:ibl", "comp:euroleague"], selectable: true },
    { id: "team:maccabi_haifa_fc", sport: "football",
      display_he: "מכבי חיפה", display_en: "Maccabi Haifa",
      aliases: ["מכבי חיפה", "maccabi haifa"],
      domestic_competition: "comp:ligat_haal",
      memberships: ["comp:ligat_haal"], selectable: true },
  ],
  people: [
    { id: "player:deni_avdija", kind: "player", sport: "basketball",
      display_he: "דני אבדיה", display_en: "Deni Avdija",
      aliases: ["דני אבדיה", "deni avdija"],
      team_id: "team:portland", selectable: true },
  ],
};

describe("follow gestures", () => {
  it("toggleFollow adds at Follow tier and removes on second tap", () => {
    let follows = toggleFollow([], "team", "team:hapoel_tlv_bb");
    expect(follows).toEqual([
      { scope: "team", target_id: "team:hapoel_tlv_bb", starred: false },
    ]);
    follows = toggleFollow(follows, "team", "team:hapoel_tlv_bb");
    expect(follows).toEqual([]);
  });

  it("NEVER creates parent scopes implicitly (the acceptance criterion)", () => {
    const follows = toggleFollow([], "team", "team:hapoel_tlv_bb");
    expect(isFollowed(follows, "sport", "basketball")).toBe(false);
    expect(isFollowed(follows, "competition", "comp:ibl")).toBe(false);
    expect(follows).toHaveLength(1);
  });

  it("toggleStar flips priority; starring an unfollowed scope follows it starred", () => {
    let follows = toggleFollow([], "competition", "comp:euroleague");
    follows = toggleStar(follows, "competition", "comp:euroleague");
    expect(follows[0].starred).toBe(true);
    follows = toggleStar(follows, "competition", "comp:euroleague");
    expect(follows[0].starred).toBe(false);
    const fresh = toggleStar([], "team", "team:hapoel_tlv_bb");
    expect(fresh).toEqual([
      { scope: "team", target_id: "team:hapoel_tlv_bb", starred: true },
    ]);
  });
});

describe("buildPutPayload", () => {
  it("emits the wire shape and drops normal presets", () => {
    const payload = buildPutPayload(
      [{ scope: "sport", target_id: "basketball", starred: false }],
      { transfers_rumors: "more", injuries: "normal", results: "less" },
    );
    expect(payload).toEqual({
      follows: [{ scope: "sport", target_id: "basketball", starred: false }],
      eventPreferences: { transfers_rumors: "more", results: "less" },
    });
  });
});

describe("progressive disclosure", () => {
  it("competitionsForSport returns catalog order incl. non-selectable", () => {
    const comps = competitionsForSport(catalog, "football");
    expect(comps.map((c) => c.id)).toEqual(["comp:ligat_haal", "comp:epl"]);
  });

  it("teamsForSelection: members of followed competitions", () => {
    const follows = [{ scope: "competition", target_id: "comp:euroleague",
                       starred: false }];
    expect(teamsForSelection(catalog, follows).map((t) => t.id))
      .toEqual(["team:hapoel_tlv_bb"]);
  });

  it("teamsForSelection: sport-only follow exposes the sport's teams", () => {
    const follows = [{ scope: "sport", target_id: "football", starred: false }];
    expect(teamsForSelection(catalog, follows).map((t) => t.id))
      .toEqual(["team:maccabi_haifa_fc"]);
  });

  it("peopleForSelection follows sport and competition context", () => {
    const bySport = [{ scope: "sport", target_id: "basketball", starred: false }];
    expect(peopleForSelection(catalog, bySport).map((p) => p.id))
      .toEqual(["player:deni_avdija"]);
    const byComp = [{ scope: "competition", target_id: "comp:ligat_haal",
                      starred: false }];
    expect(peopleForSelection(catalog, byComp)).toEqual([]);
  });
});

describe("searchCatalog (global, disclosure-independent)", () => {
  it("finds a team in Hebrew with zero prior selections", () => {
    const results = searchCatalog(catalog, "הפועל תל");
    expect(results.map((r) => r.item.id)).toContain("team:hapoel_tlv_bb");
  });

  it("finds by English alias", () => {
    const results = searchCatalog(catalog, "maccabi hai");
    expect(results.map((r) => r.item.id)).toEqual(["team:maccabi_haifa_fc"]);
  });

  it("never returns non-selectable competitions", () => {
    const results = searchCatalog(catalog, "פרמייר");
    expect(results).toEqual([]);
  });

  it("ignores sub-2-character queries", () => {
    expect(searchCatalog(catalog, "ה")).toEqual([]);
  });
});

describe("parentSuggestions (suggest, never auto-create)", () => {
  it("suggests domestic competition and sport for a followed team", () => {
    const follows = toggleFollow([], "team", "team:hapoel_tlv_bb");
    const suggestions = parentSuggestions(catalog, follows);
    const keys = suggestions.map((s) => `${s.scope}:${s.item.id}`);
    expect(keys).toContain("competition:comp:ibl");
    expect(keys).toContain("sport:basketball");
    // And crucially: the follow set itself is untouched.
    expect(follows).toHaveLength(1);
  });

  it("drops suggestions already followed", () => {
    let follows = toggleFollow([], "team", "team:hapoel_tlv_bb");
    follows = toggleFollow(follows, "competition", "comp:ibl");
    const keys = parentSuggestions(catalog, follows)
      .map((s) => `${s.scope}:${s.item.id}`);
    expect(keys).not.toContain("competition:comp:ibl");
    expect(keys).toContain("sport:basketball");
  });

  it("suggests the sport for a followed competition", () => {
    const follows = toggleFollow([], "competition", "comp:ligat_haal");
    const keys = parentSuggestions(catalog, follows)
      .map((s) => `${s.scope}:${s.item.id}`);
    expect(keys).toEqual(["sport:football"]);
  });
});

describe("provenance display (issue #83)", () => {
  const profileV2 = {
    scope_affinities: [
      { scope: "sport", target_id: "basketball", level: 0, source: "explicit" },
      { scope: "competition", target_id: "comp:ibl", level: 1, source: "calibration" },
      { scope: "player", target_id: "player:deni_avdija", level: 1, source: "learned" },
      { scope: "competition", target_id: "comp:euroleague", level: -1, source: "explicit" },
    ],
  };

  it("nonExplicitEntries returns derived entries + negative explicit levels", async () => {
    const { nonExplicitEntries } = await import("./interestsModel");
    const entries = nonExplicitEntries(profileV2);
    expect(entries.map((e) => `${e.source}:${e.target_id}`)).toEqual([
      "calibration:comp:ibl",
      "learned:player:deni_avdija",
      "explicit:comp:euroleague", // negative explicit — read-only, not managed
    ]);
  });

  it("displayNameFor resolves Hebrew names per scope kind", async () => {
    const { displayNameFor } = await import("./interestsModel");
    expect(displayNameFor(catalog, "sport", "basketball")).toBe("כדורסל");
    expect(displayNameFor(catalog, "competition", "comp:ibl")).toBe("ליגת ווינר סל");
    expect(displayNameFor(catalog, "team", "team:hapoel_tlv_bb")).toBe("הפועל תל אביב");
    expect(displayNameFor(catalog, "player", "player:deni_avdija")).toBe("דני אבדיה");
    expect(displayNameFor(catalog, "competition", "comp:unknown")).toBe("comp:unknown");
  });
});

describe("documentToState", () => {
  it("round-trips the GET document into picker state", () => {
    const state = documentToState({
      follows: [{ scope: "team", target_id: "team:hapoel_tlv_bb", starred: true }],
      event_preferences: { injuries: "more" },
      completed: true, selected: 1,
    });
    expect(state.follows[0].starred).toBe(true);
    expect(state.eventPreferences).toEqual({ injuries: "more" });
  });
});
