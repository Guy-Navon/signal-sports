import { describe, expect, it } from "vitest";
import { normalizeScoredArticleFromApi } from "@/api/normalizers";
import { storyReports } from "@/components/feed/storyModel";
import {
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
