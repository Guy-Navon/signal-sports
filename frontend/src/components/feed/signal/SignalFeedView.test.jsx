import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import { normalizeScoredArticleFromApi } from "@/api/normalizers";
import FeedbackControls from "@/components/feed/FeedbackControls";
import { AppContext } from "@/context/appContextCore";
import SignalFeedView from "./SignalFeedView";

// The consumer feed rendered in node. The public demo renders the same view
// read-only, with no AppProvider.

const REASON = "מכבי תל אביב (כדורסל) ברשימת המעקב שלך";
const NOW = Date.parse("2026-11-13T18:00:00Z");

function story(id, decision, league = "EuroLeague", publishedAt = "2026-11-13T16:00:00Z") {
  return normalizeScoredArticleFromApi({
    decision,
    reason_he: REASON,
    article: {
      id,
      source: "walla_sport",
      source_display_name: "וואלה ספורט",
      url: `https://example.test/${id}`,
      title: `כותרת ${id}`,
      published_at: publishedAt,
      sport: "basketball",
      league,
      entities: [],
      event_type: "signing",
      importance: "high",
      tags: [],
    },
    cluster: null,
  });
}

let renderer;
afterEach(() => {
  if (renderer) act(() => renderer.unmount());
  renderer = null;
  vi.restoreAllMocks();
});

function render(items, props = {}) {
  act(() => {
    renderer = create(
      <SignalFeedView
        items={items}
        activeFilters={new Set(["all"])}
        onToggleFilter={() => {}}
        onResetFilters={() => {}}
        nowMs={NOW}
        readOnly
        {...props}
      />
    );
  });
  return renderer;
}

const byClass = (root, name) =>
  root.findAll((node) => typeof node.type === "string" && String(node.props.className ?? "").split(" ").includes(name));

const DRAYMOND = 'דריימונד גרין החמיא לאבדיה: "עם דני תמיד יש סיכוי לנצח"';
const nodeText = (node) => typeof node === "string" ? node : node.children.map(nodeText).join("");

it.each([["high_feed", "sg-important__item"], ["feed", "sg-row"], ["low_feed", "sg-brief__item"]])(
  "%s shows context and quote inside one headline link", (decision, rowClass) => {
    const item = story("quote", decision);
    item.title = DRAYMOND;
    item.entities = ["Deni Avdija"];
    const row = byClass(render([item]).root, rowClass)[0];
    expect(nodeText(byClass(row, "sg-headline-context")[0])).toBe("דריימונד גרין החמיא לאבדיה");
    expect(nodeText(byClass(row, "sg-headline-quote")[0])).toBe("עם דני תמיד יש סיכוי לנצח");
    const links = byClass(row, "sg-headline-link");
    expect(links).toHaveLength(1);
    expect(links[0].type).toBe("a");
    expect(nodeText(links[0])).toContain("דריימונד גרין החמיא לאבדיה");
    expect(nodeText(links[0])).toContain("עם דני תמיד יש סיכוי לנצח");
    const glyph = byClass(row, "sg-quote-glyph")[0];
    expect(glyph.props["aria-hidden"]).toBe("true");
    expect(glyph.props.fill).toBe("#E03A3E");
  }
);

it("leaves the lead and latest headlines plain", () => {
  const item = story("quote", "push");
  item.title = DRAYMOND;
  const root = render([item]).root;
  for (const rowClass of ["sg-lead", "sg-latest__item"]) {
    const row = byClass(root, rowClass)[0];
    expect(byClass(row, "sg-headline-context")).toHaveLength(0);
    expect(nodeText(byClass(row, "sg-headline-link")[0])).toBe(DRAYMOND);
  }
});

it("keeps untranslated foreign quotes plain while highlighting numbers", () => {
  const item = story("foreign-quote", "feed");
  item.title = 'Coach: "We won 145:151"';
  item.language = "en";
  const row = byClass(render([item]).root, "sg-row")[0];
  expect(byClass(row, "sg-headline-quote")).toHaveLength(0);
  expect(nodeText(byClass(row, "sg-headline-link")[0])).toBe(item.title);
  expect(nodeText(row.findByType("mark"))).toBe("145:151");
});

it.each([[[], null], [["Deni Avdija"], "דני אבדיה"], [["Maccabi Tel Aviv Basketball"], "מכבי תל אביב"]])(
  "quote-only headlines use the chip name as context when available: %j", (entities, name) => {
    const item = story("quote-only", "feed");
    item.title = '"קלעתי 31 נקודות"';
    item.entities = entities;
    const row = byClass(render([item]).root, "sg-row")[0];
    const contexts = byClass(row, "sg-headline-context");
    expect(contexts).toHaveLength(name ? 1 : 0);
    if (name) expect(nodeText(contexts[0])).toBe(name);
    expect(nodeText(row.findByType("mark"))).toBe("31 נקודות");
  }
);

it("highlights units in a plain headline and keeps Hebrew prefixes together", () => {
  const item = story("numbers", "feed");
  item.title = "עופר ינאי נקנס ב-60 אלף שקל";
  const row = byClass(render([item]).root, "sg-row")[0];
  expect(nodeText(row.findByType("mark"))).toBe("60 אלף שקל");
  expect(row.findByType("mark").props.dir).not.toBe("ltr");
  expect(nodeText(byClass(row, "sg-headline-link")[0])).toBe("עופר ינאי נקנס ב-\u206060 אלף שקל");
});

it("read-only renders the stories and the reader reason without feedback controls", () => {
  const view = render([story("a", "high_feed"), story("b", "feed")]);
  const text = JSON.stringify(view.toJSON());
  expect(text).toContain("כותרת a");
  expect(text).toContain("כותרת b");
  expect(text).toContain(REASON);
  expect(view.root.findAllByType(FeedbackControls)).toHaveLength(0);
});

it.each(["admin", "reader", "demo"])("%s sees reader sentences in every section, never engine scores", (role) => {
  const items = [story("lead", "push"), story("important", "high_feed"), story("stream", "feed")];
  items.forEach((item) => { item.score.reasoning = ["ניקוד: 3 → חשוב", "החלטה סופית: חשוב"]; });
  act(() => {
    renderer = create(
      <AppContext.Provider value={{ qaSurfaceAllowed: role === "admin", isBackendMode: true }}>
        <SignalFeedView items={items} activeFilters={new Set(["all"])} onToggleFilter={() => {}} onResetFilters={() => {}} nowMs={NOW} readOnly={role === "demo"} />
      </AppContext.Provider>
    );
  });
  for (const section of ["sg-lead", "sg-row"]) {
    const node = byClass(renderer.root, section)[0];
    expect(node).toBeDefined();
    expect(node.findAll((n) => n.children?.includes(REASON)).length).toBeGreaterThan(0);
  }
  const text = JSON.stringify(renderer.toJSON());
  expect(text).not.toContain("ניקוד:");
  expect(text).not.toContain("החלטה סופית");
  expect(renderer.root.findAllByType(FeedbackControls)).toHaveLength(role === "demo" ? 0 : 3);
});

it.each(["admin", "reader", "demo"])("%s gets no why line when the reader sentence is absent", (role) => {
  const items = [story("lead", "push"), story("important", "high_feed"), story("stream", "feed")];
  items.forEach((item) => {
    item.score.reasonHe = null;
    item.score.reasoning = ["ניקוד: 3 → חשוב", "החלטה סופית: חשוב"];
  });
  act(() => {
    renderer = create(
      <AppContext.Provider value={{ qaSurfaceAllowed: role === "admin", isBackendMode: true }}>
        <SignalFeedView items={items} activeFilters={new Set(["all"])} onToggleFilter={() => {}} onResetFilters={() => {}} nowMs={NOW} readOnly={role === "demo"} />
      </AppContext.Provider>
    );
  });
  const text = JSON.stringify(renderer.toJSON());
  expect(text).not.toContain("למה אצלך");
  expect(text).not.toContain("ניקוד:");
});

it("without read-only every placed story gets feedback controls (and they need the app context)", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  expect(() => render([story("a", "feed")], { readOnly: false })).toThrow(
    "useApp must be used within AppProvider"
  );
});

it("shows no lead block without a push, and exactly one with pushes", () => {
  const noPush = render([story("h", "high_feed"), story("f", "feed")]);
  expect(byClass(noPush.root, "sg-lead")).toHaveLength(0);
  act(() => noPush.unmount());

  const withPush = render([story("p1", "push"), story("p2", "push"), story("f", "feed")]);
  const leads = byClass(withPush.root, "sg-lead");
  expect(leads).toHaveLength(1);
  expect(JSON.stringify(withPush.toJSON())).toContain("כותרת p2");
});

it("never renders a hidden story, even if one is passed in", () => {
  const view = render([story("x", "hidden"), story("f", "feed")]);
  expect(JSON.stringify(view.toJSON())).not.toContain("כותרת x");
});

it("bounds the stream to one page and says how many more there are", () => {
  const many = Array.from({ length: 45 }, (_, index) => story(`f${index}`, "feed"));
  const view = render(many);
  expect(byClass(view.root, "sg-row")).toHaveLength(40);
  expect(JSON.stringify(view.toJSON())).toContain("40/45");
});

function clusterStory(id, decision, members) {
  return normalizeScoredArticleFromApi({
    decision,
    reason_he: REASON,
    article: {
      id: members[0].article_id,
      source: members[0].source,
      source_display_name: members[0].source_display_name,
      url: members[0].url,
      title: `כותרת ${id}`,
      published_at: "2026-11-13T16:00:00Z",
      sport: "basketball",
      league: "EuroLeague",
      entities: [],
      event_type: "signing",
      importance: "high",
      tags: [],
    },
    cluster: {
      cluster_id: id,
      decision,
      displayed_article_id: members[0].article_id,
      priority_article_id: members[0].article_id,
      source_count: members.length,
      sort_at: "2026-11-13T16:00:00Z",
      members,
    },
  });
}

const member = (id, source, name) => ({
  article_id: id,
  source,
  source_display_name: name,
  title: `דיווח ${id}`,
  url: `https://${source}.test/${id}`,
  published_at: "2026-11-13T15:00:00Z",
  decision: "feed",
});

it("a stream cluster's badge discloses every member source with a link, and closes again", () => {
  const cluster = clusterStory("c1", "feed", [
    member("m1", "one", "ONE"),
    member("m2", "walla_sport", "וואלה ספורט"),
  ]);
  const view = render([cluster]);
  const badge = byClass(view.root, "sg-badge")[0];
  expect(badge.props["aria-expanded"]).toBe(false);
  act(() => badge.props.onClick());
  expect(byClass(view.root, "sg-badge")[0].props["aria-expanded"]).toBe(true);
  const links = byClass(view.root, "sg-members__item");
  expect(links.map((link) => link.props.href)).toEqual([
    "https://one.test/m1",
    "https://walla_sport.test/m2",
  ]);
  act(() => byClass(view.root, "sg-badge")[0].props.onClick());
  expect(byClass(view.root, "sg-members")).toHaveLength(0);
});

const textIn = (node) =>
  node.children.map((child) => (typeof child === "string" ? child : textIn(child))).join("");

function openStory(view, section) {
  const scope = byClass(view.root, section)[0];
  const badge = byClass(scope, "sg-badge")[0];
  expect(badge.props["aria-expanded"]).toBe(false);
  act(() => badge.props.onClick());
  const opened = byClass(view.root, section)[0];
  const list = byClass(opened, "sg-members")[0];
  expect(byClass(opened, "sg-badge")[0].props["aria-expanded"]).toBe(true);
  expect(list.props.id).toBe(byClass(opened, "sg-badge")[0].props["aria-controls"]);
  return byClass(list, "sg-members__item");
}

it("a multi-source story in the important row opens to each source's own report (#501)", () => {
  const cluster = clusterStory("c2", "high_feed", [
    { ...member("m2", "walla_sport", "וואלה ספורט"), published_at: "2026-11-13T15:30:00Z" },
    { ...member("m3", "israel_hayom", "ישראל היום"), published_at: "2026-11-13T15:10:00Z" },
    { ...member("m1", "one", "ONE"), published_at: "2026-11-13T14:00:00Z" },
  ]);
  const view = render([cluster]);
  // The names stay a readable list in the meta line, but are not links: the
  // badge is the one way in, and the links live in the opened list.
  const meta = byClass(byClass(view.root, "sg-important__item")[0], "sg-meta")[0];
  expect(meta.findAll((node) => node.type === "a")).toHaveLength(0);
  expect(textIn(meta)).toContain("ישראל היום");

  const items = openStory(view, "sg-important__item");
  // Displayed report first, then the others newest first.
  expect(items.map((link) => link.props.href)).toEqual([
    "https://walla_sport.test/m2",
    "https://israel_hayom.test/m3",
    "https://one.test/m1",
  ]);
  for (const link of items) {
    expect(link.props.target).toBe("_blank");
    expect(link.props.rel).toContain("noopener");
  }
  const [first, , second] = items;
  expect(textIn(byClass(first, "sg-members__mark")[0])).toBe("הדיווח המוצג");
  expect(byClass(second, "sg-members__mark")).toHaveLength(0);
  expect(textIn(byClass(second, "sg-members__title")[0])).toContain("דיווח m1");
  expect(byClass(second, "sg-members__go")).toHaveLength(1);
  expect(textIn(second.findAll((node) => node.type === "time")[0])).toBe("לפני 4 שעות");
});

it("the lead and 'in brief' open a multi-source story the same way", () => {
  const members = [member("m1", "one", "ONE"), member("m2", "walla_sport", "וואלה ספורט")];
  const lead = render([clusterStory("cp", "push", members)]);
  expect(openStory(lead, "sg-lead")).toHaveLength(2);
  act(() => lead.unmount());
  const brief = render([clusterStory("cl", "low_feed", members)]);
  expect(openStory(brief, "sg-brief__item")).toHaveLength(2);
});

it("a multi-source story whose payload carries no reports shows its names only", () => {
  const cluster = clusterStory("c3", "high_feed", [
    member("m1", "one", "ONE"),
    member("m2", "walla_sport", "וואלה ספורט"),
  ]);
  const bare = { ...cluster, members: [], articleIds: [] };
  const view = render([bare]);
  expect(byClass(view.root, "sg-badge")).toHaveLength(0);
  expect(JSON.stringify(view.toJSON())).toContain("מקורות");
});

it("'show more' reveals the next page and moves focus to its first new row", () => {
  const focused = [];
  const many = Array.from({ length: 45 }, (_, index) => story(`f${index}`, "feed"));
  act(() => {
    renderer = create(
      <SignalFeedView
        items={many}
        activeFilters={new Set(["all"])}
        onToggleFilter={() => {}}
        onResetFilters={() => {}}
        nowMs={NOW}
        readOnly
      />,
      {
        createNodeMock: (element) =>
          element.type === "a" ? { focus: () => focused.push(element.props.href) } : null,
      }
    );
  });
  const more = byClass(renderer.root, "sg-more")[0];
  act(() => more.props.onClick());
  expect(byClass(renderer.root, "sg-row")).toHaveLength(45);
  expect(byClass(renderer.root, "sg-more")).toHaveLength(0);
  expect(focused).toEqual(["https://example.test/f40"]);
});

const headlinesIn = (node) =>
  byClass(node, "sg-headline-link").map((link) => link.props.href.split("/").pop());

it("the side column holds 'latest' by time and the low_feed stories, never hidden ones, and leaves the stream's order alone", () => {
  const items = [
    story("h1", "high_feed", "EuroLeague", "2026-11-13T10:00:00Z"),
    ...["h2", "h3", "h4", "h5"].map((id) => story(id, "high_feed", "EuroLeague", "2026-11-13T09:00:00Z")),
    story("f1", "feed", "EuroLeague", "2026-11-13T12:00:00Z"),
    story("f2", "feed", "EuroLeague", "2026-11-13T17:30:00Z"),
    story("l1", "low_feed", "EuroLeague", "2026-11-13T17:55:00Z"),
    story("x", "hidden", "EuroLeague", "2026-11-13T17:59:00Z"),
  ];
  const view = render(items);
  const side = byClass(view.root, "sg-side")[0];
  const [latest] = byClass(side, "sg-latest");
  const [brief] = byClass(side, "sg-brief");
  expect(headlinesIn(latest).slice(0, 3)).toEqual(["f2", "f1", "h1"]);
  expect(headlinesIn(latest)).not.toContain("l1");
  expect(headlinesIn(brief)).toEqual(["l1"]);
  expect(JSON.stringify(view.toJSON())).not.toContain("כותרת x");
  // The ranked stream is unchanged; f2 stands both there and in "latest".
  expect(headlinesIn(byClass(view.root, "sg-stream")[0])).toEqual(["h5", "f1", "f2"]);
  // Only the story under an hour old carries the fresh marker.
  expect(byClass(latest, "sg-latest__item").filter((li) => li.props["data-fresh"])).toHaveLength(1);
  // "בקצרה" no longer follows the stream outside the column.
  expect(byClass(view.root, "sg-brief")).toHaveLength(1);
});

it("the side column follows the active league filter, like the stream", () => {
  const items = [
    story("nba", "feed", "NBA", "2026-11-13T17:00:00Z"),
    story("el", "feed", "EuroLeague", "2026-11-13T17:50:00Z"),
    story("lnba", "low_feed", "NBA"),
    story("lel", "low_feed", "EuroLeague"),
  ];
  const view = render(items, { activeFilters: new Set(["league:NBA"]) });
  const side = byClass(view.root, "sg-side")[0];
  expect(headlinesIn(byClass(side, "sg-latest")[0])).toEqual(["nba"]);
  expect(headlinesIn(byClass(side, "sg-brief")[0])).toEqual(["lnba"]);
});

it("the league pills say whether they are selected", () => {
  const items = [story("a", "feed", "NBA"), story("b", "feed", "EuroLeague")];
  const view = render(items, { activeFilters: new Set(["league:NBA"]) });
  act(() => byClass(view.root, "sg-filter-toggle")[0].props.onClick());
  const pressed = byClass(view.root, "sg-pill").map((pill) => pill.props["aria-pressed"]);
  expect(pressed).toEqual([false, true, false]);
  expect(JSON.stringify(view.toJSON())).not.toContain("כותרת b");
});

// The filter bar (#483): C's disclosure contains all three facets.

const levelBoxes = (root) => root.findAll((node) => node.type === "input" && node.props.type === "checkbox" && node.props.className === "sg-seg__input");
const textOf = (node) =>
  node.children.map((child) => (typeof child === "string" ? child : textOf(child))).join("");

it("offers each importance level as its own checkbox, each named with its count", () => {
  const items = [
    story("p", "push", "NBA"),
    story("h", "high_feed", "EuroLeague"),
    story("f", "feed", "NBA"),
    story("l", "low_feed", "NBA"),
  ];
  const view = render(items);
  expect(levelBoxes(view.root)).toHaveLength(0);
  expect(byClass(view.root, "sg-pill")).toHaveLength(0);
  act(() => byClass(view.root, "sg-filter-toggle")[0].props.onClick());
  const group = view.root.find((node) => node.props.role === "group" && node.props["aria-label"] === "סינון לפי חשיבות");
  expect(group.props["aria-label"]).toBe("סינון לפי חשיבות");
  const inputs = levelBoxes(view.root);
  expect(inputs.map((input) => input.props.checked)).toEqual([true, false, false, false, false]);
  const names = byClass(view.root, "sg-seg__opt").map((label) =>
    textOf(label).replace(/\s+/g, " ").trim()
  );
  expect(names).toEqual([
    "הכול4, 4 סיפורים",
    "דורש תשומת לב1, 1 סיפורים",
    "חשוב1, 1 סיפורים",
    "רגיל1, 1 סיפורים",
    "נמוך1, 1 סיפורים",
  ]);
  expect(names.join("")).not.toContain("ומעלה");
});

it("choosing a level asks for exactly it; 'הכול' clears only the importance group", () => {
  const onToggleFilter = vi.fn();
  const items = [story("h", "high_feed"), story("f", "feed")];
  const view = render(items, { onToggleFilter });
  act(() => byClass(view.root, "sg-filter-toggle")[0].props.onClick());
  act(() => levelBoxes(view.root)[2].props.onChange());
  expect(onToggleFilter).toHaveBeenLastCalledWith("high_feed");
  act(() => view.update(
    <SignalFeedView items={items} activeFilters={new Set(["high_feed"])}
      onToggleFilter={onToggleFilter} onResetFilters={() => {}} nowMs={NOW} readOnly />
  ));
  act(() => levelBoxes(view.root)[0].props.onChange());
  expect(onToggleFilter).toHaveBeenLastCalledWith("level:*");
});

it("a level filter narrows every section, keeps the push lead, and never reveals a hidden story", () => {
  const items = [
    story("p", "push", "NBA"),
    story("h", "high_feed", "EuroLeague"),
    story("f", "feed", "NBA"),
    story("l", "low_feed", "NBA"),
    story("x", "hidden", "NBA"),
  ];
  const view = render(items, { activeFilters: new Set(["push", "high_feed"]) });
  const text = JSON.stringify(view.toJSON());
  expect(byClass(view.root, "sg-lead")).toHaveLength(1);
  expect(text).toContain("כותרת h");
  expect(text).not.toContain("כותרת f");
  expect(text).not.toContain("כותרת l");
  expect(text).not.toContain("כותרת x");
  // The summary still counts the whole feed; the result line says what is shown.
  expect(textOf(byClass(view.root, "sg-summary")[0])).toContain("4");
  expect(textOf(byClass(view.root, "sg-filter-result")[0])).toContain("מוצגים 2 מתוך 4 סיפורים");
});

it("the league pills count under the level, and 'כל הליגות' clears only the leagues", () => {
  const onToggleFilter = vi.fn();
  const items = [
    story("h", "high_feed", "NBA"),
    story("f1", "feed", "NBA"),
    story("f2", "feed", "EuroLeague"),
  ];
  const view = render(items, { activeFilters: new Set(["high_feed"]), onToggleFilter });
  act(() => byClass(view.root, "sg-filter-toggle")[0].props.onClick());
  const pills = byClass(view.root, "sg-pill");
  // EuroLeague has nothing at חשוב or above, so it is not offered.
  expect(pills.map((pill) => pill.props["data-filter"] ?? "all")).toEqual(["all", "league:NBA"]);
  expect(pills.map((pill) => textOf(pill))).toEqual(["כל הליגות1", "NBA1"]);
  act(() => pills[0].props.onClick());
  expect(onToggleFilter).toHaveBeenLastCalledWith("league:*");
});

it("an empty result names the filter and offers the whole feed", () => {
  const onResetFilters = vi.fn();
  const items = [story("f", "feed", "NBA")];
  const view = render(items, { activeFilters: new Set(["high_feed"]), onResetFilters });
  const empty = byClass(view.root, "sg-filter-empty")[0];
  expect(textOf(empty)).toContain("אין סיפורים ברמה שבחרת.");
  act(() => empty.findByType("button").props.onClick());
  expect(onResetFilters).toHaveBeenCalled();
  expect(byClass(view.root, "sg-row")).toHaveLength(0);
});

it("says nothing in the result line while nothing is filtered", () => {
  const view = render([story("f", "feed")]);
  expect(textOf(byClass(view.root, "sg-filter-result")[0])).toBe("");
  expect(byClass(view.root, "sg-filter-clear")).toHaveLength(0);
});

it("shows removable chips for all three facets and counts sources in read-only mode", () => {
  const onToggleFilter = vi.fn();
  const onResetFilters = vi.fn();
  const items = [story("h", "high_feed", "NBA"), story("f", "feed", "EuroLeague")];
  const view = render(items, { activeFilters: new Set(["feed", "high_feed", "league:NBA", "source:walla_sport"]), onToggleFilter, onResetFilters });
  const chips = byClass(view.root, "sg-filter-chip");
  expect(chips.map((chip) => chip.props["data-filter"])).toEqual(["high_feed", "feed", "league:NBA", "source:walla_sport"]);
  expect(textOf(chips[3])).toBe("וואלה ספורט");
  expect(textOf(byClass(view.root, "sg-filter-badge")[0])).toBe("4");
  act(() => chips[3].props.onClick());
  expect(onToggleFilter).toHaveBeenLastCalledWith("source:walla_sport");
  act(() => byClass(view.root, "sg-filter-clear")[0].props.onClick());
  expect(onResetFilters).toHaveBeenCalledOnce();
  act(() => byClass(view.root, "sg-filter-toggle")[0].props.onClick());
  const source = byClass(view.root, "sg-filter-check")[0];
  expect(source.props["data-filter"]).toBe("source:walla_sport");
  expect(source.findByType("input").props.checked).toBe(true);
  expect(textOf(source)).toBe("וואלה ספורט1");
  expect(view.root.findAllByType(FeedbackControls)).toHaveLength(0);
});

it("an empty source result has one filter announcement and a descriptive recovery", () => {
  const view = render([story("f", "feed")], { activeFilters: new Set(["source:missing"]) });
  const empty = byClass(view.root, "sg-filter-empty")[0];
  expect(textOf(empty)).toContain("במקורות שבחרת");
  expect(empty.props.role).toBeUndefined();
  const result = byClass(view.root, "sg-filter-result")[0];
  expect(result.findByProps({ role: "status" }).children).toEqual(["אין סיפורים שמתאימים לסינון"]);
});

// Motion (#467): the motion is CSS; the view decides which rows are new and
// how long each waits, and both are bounded.

const enterDelay = (node) => node.props.style?.["--sg-enter-delay"];
const arrivedRows = (root) => byClass(root, "sg-row").filter((row) => row.props["data-arrived"]);

it("marks nothing as new on the first render", () => {
  const view = render([story("f1", "feed"), story("f2", "feed")]);
  expect(arrivedRows(view.root)).toHaveLength(0);
  expect(byClass(view.root, "sg-new")).toHaveLength(0);
});

it("marks the stories a refresh brought with a word, and only those", () => {
  const base = Array.from({ length: 4 }, (_, index) => story(`f${index}`, "feed"));
  const view = render(base);
  act(() => {
    view.update(
      <SignalFeedView
        items={[story("fresh", "feed"), ...base]}
        activeFilters={new Set(["all"])}
        onToggleFilter={() => {}}
        onResetFilters={() => {}}
        nowMs={NOW}
        readOnly
      />
    );
  });
  const arrived = arrivedRows(view.root);
  expect(arrived).toHaveLength(1);
  expect(arrived[0].props["data-league"]).toBeDefined();
  expect(byClass(arrived[0], "sg-row__title")[0].findByType("a").props.href).toContain("/fresh");
  expect(byClass(arrived[0], "sg-new")).toHaveLength(1);
  expect(JSON.stringify(view.toJSON())).toContain("סיפור חדש אחד נוסף לפיד");
});

it("caps the stream's entrance stagger, whatever the page length", () => {
  const many = Array.from({ length: 40 }, (_, index) => story(`f${index}`, "feed"));
  const view = render(many);
  const delays = byClass(view.root, "sg-row").map((row) => Number.parseInt(enterDelay(row), 10));
  expect(delays).toHaveLength(40);
  const max = Math.max(...delays);
  expect(delays.slice(6).every((value) => value === max)).toBe(true);
  expect(new Set(delays).size).toBe(7);
});

// Subtitle on demand (2026-11-16): clicking the card (not the headline) or the chevron
// opens the story's subtitle in place; the headline link still opens the article.
function withSubtitle(item, subtitle) {
  item.subtitle = subtitle;
  return item;
}
const plainClick = { target: { closest: () => null } };
const linkClick = { target: { closest: () => ({ tagName: "A" }) } };

it("a stream row opens and closes its subtitle from the chevron and from the card", () => {
  const view = render([story("lead", "push"), withSubtitle(story("s", "feed"), "כותרת משנה של s")]);
  const row = byClass(view.root, "sg-row")[0];
  expect(byClass(row, "sg-dek")).toHaveLength(0);

  const toggle = byClass(row, "sg-dek-toggle")[0];
  expect(toggle.props["aria-expanded"]).toBe(false);
  act(() => toggle.props.onClick());
  expect(byClass(row, "sg-dek")[0].props.children).toBe("כותרת משנה של s");
  expect(byClass(row, "sg-dek-toggle")[0].props["aria-expanded"]).toBe(true);

  act(() => row.props.onClick(plainClick));
  expect(byClass(row, "sg-dek")).toHaveLength(0);
  act(() => row.props.onClick(plainClick));
  expect(byClass(row, "sg-dek")).toHaveLength(1);
});

it("a click on the headline link (or any control) does not toggle the subtitle", () => {
  const view = render([story("lead", "push"), withSubtitle(story("s", "feed"), "כותרת משנה")]);
  const row = byClass(view.root, "sg-row")[0];
  act(() => row.props.onClick(linkClick));
  expect(byClass(row, "sg-dek")).toHaveLength(0);
  const link = row.findAll((n) => n.type === "a" && n.props.href === "https://example.test/s");
  expect(link.length).toBeGreaterThan(0);
});

it("a story without a subtitle has no chevron and the card click does nothing", () => {
  const view = render([story("lead", "push"), story("s", "feed")]);
  const row = byClass(view.root, "sg-row")[0];
  expect(byClass(row, "sg-dek-toggle")).toHaveLength(0);
  act(() => row.props.onClick?.(plainClick));
  expect(byClass(row, "sg-dek")).toHaveLength(0);
});

it("important, brief and latest items offer the subtitle too", () => {
  const items = [
    story("lead", "push"),
    withSubtitle(story("imp", "high_feed"), "משנה imp"),
    withSubtitle(story("brief", "low_feed"), "משנה brief"),
  ];
  const view = render(items);
  for (const cls of ["sg-important__item", "sg-brief__item", "sg-latest__item"]) {
    const cards = byClass(view.root, cls).filter((c) => byClass(c, "sg-dek-toggle").length > 0);
    expect(cards.length, cls).toBeGreaterThan(0);
    act(() => byClass(cards[0], "sg-dek-toggle")[0].props.onClick());
    expect(byClass(cards[0], "sg-dek"), cls).toHaveLength(1);
  }
});

// ── Team mark (#592) ─────────────────────────────────────────────────────────

function withEntities(item, entities) {
  return { ...item, entities };
}

const markIn = (node) => byClass(node, "sg-mark");
const marksNamed = (node) => markIn(node).map((n) => n.props["aria-label"]);
const chipText = (node) => byClass(node, "sg-chip").map(textOf);

it("a team row gets the colour edge, a jersey named for the club and the name chip; a three-team row gets none", () => {
  const items = [
    withEntities(story("f1", "feed"), ["Maccabi Tel Aviv Basketball"]),
    withEntities(story("f2", "feed"), ["Maccabi Ramat Gan", "Hapoel Tel Aviv Basketball", "Maccabi Tel Aviv Basketball"]),
  ];
  const view = render(items);
  const [one, three] = byClass(view.root, "sg-row");
  expect(byClass(one, "sg-edge")).toHaveLength(1);
  expect(marksNamed(one)).toEqual(["מכבי תל אביב"]);
  expect(chipText(one)).toEqual(["מכבי תל אביב"]);
  expect(byClass(three, "sg-edge")).toHaveLength(0);
  expect(markIn(three)).toHaveLength(0);
  expect(byClass(three, "sg-chip")).toHaveLength(0);
  // The empty slot keeps the headline column aligned.
  expect(byClass(three, "sg-row__mark")).toHaveLength(1);
});

it("two teams get one jersey and one edge for the first, and the second by name", () => {
  const view = render([withEntities(story("f1", "feed"), ["Deni Avdija", "LeBron James"])]);
  const [row] = byClass(view.root, "sg-row");
  expect(marksNamed(row)).toEqual(["פורטלנד בלייזרס · 8"]);
  expect(byClass(row, "sg-edge")).toHaveLength(1);
  expect(chipText(row)).toEqual(["דני אבדיה· גם לוס אנג'לס לייקרס"]);
});

it("the important row and 'in brief' carry the mark beside the headline; the lead and 'latest' do not", () => {
  const items = [
    withEntities(story("p1", "push"), ["Maccabi Tel Aviv Basketball"]),
    withEntities(story("h1", "high_feed"), ["Deni Avdija"]),
    withEntities(story("l1", "low_feed"), ["Maccabi Tel Aviv Basketball"]),
  ];
  const view = render(items);
  const [important] = byClass(view.root, "sg-important__item");
  expect(marksNamed(important)).toEqual(["פורטלנד בלייזרס · 8"]);
  expect(chipText(important)).toEqual(["דני אבדיה"]);
  expect(byClass(important, "sg-edge")).toHaveLength(1);
  // Not in the tag line.
  expect(markIn(byClass(important, "sg-important__tags")[0])).toHaveLength(0);
  const [brief] = byClass(view.root, "sg-brief__item");
  expect(marksNamed(brief)).toEqual(["מכבי תל אביב"]);
  expect(chipText(brief)).toEqual(["מכבי תל אביב"]);
  for (const name of ["sg-lead", "sg-latest"]) {
    const [section] = byClass(view.root, name);
    expect(markIn(section)).toHaveLength(0);
    expect(byClass(section, "sg-edge")).toHaveLength(0);
    expect(byClass(section, "sg-chip")).toHaveLength(0);
  }
});
