import { describe, expect, it } from "vitest";
import { normalizeScoredArticleFromApi } from "@/api/normalizers";
import { storyReports } from "@/components/feed/storyModel";
import {
  clusterReportList,
  relativeTimeHe,
  storyLink,
  storySources,
  titleDirection,
  unbreakableHebrewPrefixes,
} from "./signalStoryModel";

const member = (id, source, name, url, publishedAt, decision = "feed") => ({
  article_id: id,
  source,
  source_display_name: name,
  title: `כותרת ${id}`,
  url,
  published_at: publishedAt,
  decision,
});

function cluster({ sourceCount, members, displayed }) {
  return normalizeScoredArticleFromApi({
    decision: "feed",
    reason_he: null,
    article: {
      id: displayed,
      source: "walla_sport",
      source_display_name: "וואלה ספורט",
      url: `https://walla.test/${displayed}`,
      title: "כותרת",
      published_at: "2026-11-13T10:00:00Z",
      sport: "basketball",
      league: "EuroLeague",
      entities: [],
      event_type: "signing",
      importance: "high",
      tags: [],
    },
    cluster: {
      cluster_id: "c1",
      decision: "high_feed",
      displayed_article_id: displayed,
      priority_article_id: displayed,
      source_count: sourceCount,
      sort_at: "2026-11-13T12:00:00Z",
      members,
    },
  });
}

describe("storySources", () => {
  it("names a cluster's member sources once each, the displayed one first", () => {
    const item = cluster({
      sourceCount: 2,
      displayed: "b",
      members: [
        member("a", "one", "ONE", "https://one.test/a", "2026-11-13T09:00:00Z"),
        member("b", "walla_sport", "וואלה ספורט", "https://walla.test/b", "2026-11-13T12:00:00Z"),
        member("c", "one", "ONE", "https://one.test/c", "2026-11-13T11:00:00Z"),
      ],
    });
    const view = storySources(item, storyReports(item));
    expect(view.multi).toBe(true);
    expect(view.names).toEqual(["וואלה ספורט", "ONE"]);
    expect(view.reports.map((r) => r.articleId)).toEqual(["b", "a"]);
  });

  it("takes the count from the backend, not from the client's deduplication", () => {
    // Deliberate disagreement: the backend says 3 sources, the members show 2.
    const item = cluster({
      sourceCount: 3,
      displayed: "a",
      members: [
        member("a", "one", "ONE", "https://one.test/a", "2026-11-13T09:00:00Z"),
        member("b", "walla_sport", "וואלה ספורט", "https://walla.test/b", "2026-11-13T12:00:00Z"),
      ],
    });
    expect(storySources(item, storyReports(item)).count).toBe(3);
  });

  it("never lists a hidden member", () => {
    const item = cluster({
      sourceCount: 1,
      displayed: "a",
      members: [
        member("a", "one", "ONE", "https://one.test/a", "2026-11-13T09:00:00Z"),
        member("h", "sport5", "ספורט 5", "https://s5.test/h", "2026-11-13T12:00:00Z", "hidden"),
      ],
    });
    const view = storySources(item, storyReports(item));
    expect(view.names).toEqual(["ONE"]);
    expect(view.multi).toBe(false);
  });

  it("is a single source for a plain article", () => {
    const item = { type: "article", id: "x", source: "one", sourceDisplayName: "ONE", url: "u" };
    const view = storySources(item, storyReports(item));
    expect(view).toMatchObject({ count: 1, multi: false, names: ["ONE"] });
  });
});

describe("clusterReportList", () => {
  const twoSources = (displayed, members, sourceCount = 2) =>
    cluster({ sourceCount, displayed, members });

  it("puts the displayed report first, then the others in the order they were published", () => {
    const item = twoSources("b", [
      member("c", "sport5", "ספורט 5", "https://s5.test/c", "2026-11-13T11:00:00Z"),
      member("b", "walla_sport", "וואלה ספורט", "https://walla.test/b", "2026-11-13T12:00:00Z"),
      member("a", "one", "ONE", "https://one.test/a", "2026-11-13T09:00:00Z"),
    ], 3);
    const list = clusterReportList(item, storyReports(item));
    expect(list.reports.map((r) => r.articleId)).toEqual(["b", "a", "c"]);
    expect(list.reports.map((r) => r.displayed)).toEqual([true, false, false]);
  });

  it("keeps every visible report, including a second one from the same source", () => {
    const item = twoSources("b", [
      member("a", "one", "ONE", "https://one.test/a", "2026-11-13T09:00:00Z"),
      member("b", "walla_sport", "וואלה ספורט", "https://walla.test/b", "2026-11-13T12:00:00Z"),
      member("c", "one", "ONE", "https://one.test/c", "2026-11-13T11:00:00Z"),
    ]);
    const list = clusterReportList(item, storyReports(item));
    expect(list.reports.map((r) => r.articleId)).toEqual(["b", "a", "c"]);
    expect(list).toMatchObject({ reportCount: 3, sourceCount: 2, canOpen: true });
  });

  it("lists an undated report last, without inventing a time", () => {
    const item = twoSources("b", [
      member("x", "sport5", "ספורט 5", "https://s5.test/x", null),
      member("a", "one", "ONE", "https://one.test/a", "2026-11-13T09:00:00Z"),
      member("b", "walla_sport", "וואלה ספורט", "https://walla.test/b", "2026-11-13T12:00:00Z"),
    ], 3);
    const list = clusterReportList(item, storyReports(item));
    expect(list.reports.map((r) => r.articleId)).toEqual(["b", "a", "x"]);
    expect(list.reports[2].publishedAt).toBeNull();
  });

  it("marks the report the headline opens when the displayed member is not visible", () => {
    // Same fallback as storyLink: the first visible report stands in.
    const item = twoSources("h", [
      member("a", "one", "ONE", "https://one.test/a", "2026-11-13T09:00:00Z"),
      member("b", "walla_sport", "וואלה ספורט", "https://walla.test/b", "2026-11-13T12:00:00Z"),
      member("h", "sport5", "ספורט 5", "https://s5.test/h", "2026-11-13T13:00:00Z", "hidden"),
    ]);
    const reports = storyReports(item);
    const list = clusterReportList(item, reports);
    const displayed = list.reports.filter((r) => r.displayed);
    expect(displayed).toHaveLength(1);
    expect(displayed[0].url).toBe(storyLink(item, reports));
    expect(list.reports.map((r) => r.articleId)).toEqual(["a", "b"]);
  });

  it("never lists a hidden member or the same report twice", () => {
    const item = twoSources("a", [
      member("a", "one", "ONE", "https://one.test/a", "2026-11-13T09:00:00Z"),
      member("a", "one", "ONE", "https://one.test/a", "2026-11-13T09:00:00Z"),
      member("b", "walla_sport", "וואלה ספורט", "https://walla.test/b", "2026-11-13T12:00:00Z"),
      member("h", "sport5", "ספורט 5", "https://s5.test/h", "2026-11-13T13:00:00Z", "hidden"),
    ]);
    const list = clusterReportList(item, storyReports(item));
    expect(list.reports.map((r) => r.articleId)).toEqual(["a", "b"]);
  });

  it("cannot open when the payload carries fewer than two reports (names only, honestly)", () => {
    // The backend says two sources but sent no members: nothing to open.
    const item = { ...twoSources("a", []), members: [] };
    const list = clusterReportList(item, storyReports(item));
    expect(list).toMatchObject({ canOpen: false, reportCount: 0, sourceCount: 2 });
  });

  it("does not open a plain article", () => {
    const item = { type: "article", id: "x", source: "one", sourceDisplayName: "ONE", url: "u" };
    expect(clusterReportList(item, storyReports(item)).canOpen).toBe(false);
  });
});

describe("storyLink", () => {
  it("opens a cluster at its displayed member", () => {
    const item = cluster({
      sourceCount: 2,
      displayed: "b",
      members: [
        member("a", "one", "ONE", "https://one.test/a", "2026-11-13T09:00:00Z"),
        member("b", "walla_sport", "וואלה ספורט", "https://walla.test/b", "2026-11-13T12:00:00Z"),
      ],
    });
    expect(storyLink(item, storyReports(item))).toBe("https://walla.test/b");
  });

  it("opens an article at its own url, and has none when the article has none", () => {
    expect(storyLink({ type: "article", url: "https://x.test" }, [])).toBe("https://x.test");
    expect(storyLink({ type: "article" }, [])).toBeNull();
  });
});

describe("relativeTimeHe", () => {
  const now = Date.parse("2026-11-13T18:00:00Z");
  const ago = (minutes) => new Date(now - minutes * 60_000).toISOString();

  it("reads like the approved mock", () => {
    expect(relativeTimeHe(ago(0.2), now)).toBe("לפני 1 דק׳");
    expect(relativeTimeHe(ago(12), now)).toBe("לפני 12 דק׳");
    expect(relativeTimeHe(ago(60), now)).toBe("לפני שעה");
    expect(relativeTimeHe(ago(120), now)).toBe("לפני שעתיים");
    expect(relativeTimeHe(ago(5 * 60), now)).toBe("לפני 5 שעות");
    expect(relativeTimeHe(ago(24 * 60), now)).toBe("אתמול");
    expect(relativeTimeHe(ago(48 * 60), now)).toBe("שלשום");
    expect(relativeTimeHe(ago(5 * 24 * 60), now)).toBe("לפני 5 ימים");
  });

  it("says nothing rather than inventing a time", () => {
    expect(relativeTimeHe(null, now)).toBeNull();
    expect(relativeTimeHe("not a date", now)).toBeNull();
  });

  it("does not report a future timestamp as the past", () => {
    expect(relativeTimeHe(ago(-30), now)).toBe("עכשיו");
  });
});

describe("unbreakableHebrewPrefixes", () => {
  const WJ = "⁠";

  it("keeps a Hebrew prefix and hyphen on the line of the name or number it belongs to", () => {
    expect(unbreakableHebrewPrefixes("MVP של ה-NBA")).toBe(`MVP של ה-${WJ}NBA`);
    expect(unbreakableHebrewPrefixes("במקום ה-12")).toBe(`במקום ה-${WJ}12`);
  });

  it("leaves other hyphens alone and does not change the visible text", () => {
    const title = "קארל-אנתוני טאונס, 2004-5";
    expect(unbreakableHebrewPrefixes(title)).toBe(title);
    expect(unbreakableHebrewPrefixes("ה-NBA").replaceAll(WJ, "")).toBe("ה-NBA");
    expect(unbreakableHebrewPrefixes("")).toBe("");
  });
});

describe("titleDirection", () => {
  it("lets an untranslated foreign-language title find its own direction", () => {
    expect(titleDirection({ language: "en", title: "Deni Avdija traded" })).toBe("auto");
  });

  it("keeps Hebrew and translated titles in the page direction", () => {
    expect(titleDirection({ language: "he", title: "דני אבדיה" })).toBeUndefined();
    expect(
      titleDirection({ language: "en", title: "Deni", translatedTitle: "דני אבדיה הועבר" })
    ).toBeUndefined();
  });
});
