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

it("a cluster in the important row names each source as a link to its report", () => {
  const cluster = clusterStory("c2", "high_feed", [
    member("m1", "one", "ONE"),
    member("m2", "walla_sport", "וואלה ספורט"),
  ]);
  const view = render([cluster]);
  const links = byClass(view.root, "sg-source-link");
  expect(links.map((link) => link.props.href)).toEqual([
    "https://one.test/m1",
    "https://walla_sport.test/m2",
  ]);
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

const radios = (root) => root.findAll((node) => node.type === "input" && node.props.type === "radio");
const textOf = (node) =>
  node.children.map((child) => (typeof child === "string" ? child : textOf(child))).join("");

it("offers the importance thresholds as one radio group, each named with its count", () => {
  const items = [
    story("p", "push", "NBA"),
    story("h", "high_feed", "EuroLeague"),
    story("f", "feed", "NBA"),
    story("l", "low_feed", "NBA"),
  ];
  const view = render(items);
  expect(radios(view.root)).toHaveLength(0);
  expect(byClass(view.root, "sg-pill")).toHaveLength(0);
  act(() => byClass(view.root, "sg-filter-toggle")[0].props.onClick());
  const group = view.root.find((node) => node.props.role === "radiogroup");
  expect(group.props["aria-label"]).toBe("סינון לפי חשיבות");
  const inputs = radios(view.root);
  expect(new Set(inputs.map((input) => input.props.name)).size).toBe(1);
  expect(inputs.map((input) => input.props.checked)).toEqual([true, false, false]);
  const names = byClass(view.root, "sg-seg__opt").map((label) =>
    textOf(label).replace(/\s+/g, " ").trim()
  );
  expect(names).toEqual([
    "הכול4, 4 סיפורים",
    "רגיל ומעלה3, 3 סיפורים",
    "חשוב ומעלה2, 2 סיפורים",
  ]);
});

it("choosing a threshold asks for it; 'הכול' clears only the threshold", () => {
  const onToggleFilter = vi.fn();
  const items = [story("h", "high_feed"), story("f", "feed")];
  const view = render(items, { onToggleFilter });
  act(() => byClass(view.root, "sg-filter-toggle")[0].props.onClick());
  act(() => radios(view.root)[2].props.onChange());
  expect(onToggleFilter).toHaveBeenLastCalledWith("min:high_feed");
  act(() => view.update(
    <SignalFeedView items={items} activeFilters={new Set(["min:high_feed"])}
      onToggleFilter={onToggleFilter} onResetFilters={() => {}} nowMs={NOW} readOnly />
  ));
  act(() => radios(view.root)[0].props.onChange());
  expect(onToggleFilter).toHaveBeenLastCalledWith("min:*");
});

it("a threshold narrows every section, keeps the push lead, and never reveals a hidden story", () => {
  const items = [
    story("p", "push", "NBA"),
    story("h", "high_feed", "EuroLeague"),
    story("f", "feed", "NBA"),
    story("l", "low_feed", "NBA"),
    story("x", "hidden", "NBA"),
  ];
  const view = render(items, { activeFilters: new Set(["min:high_feed"]) });
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

it("the league pills count under the threshold, and 'כל הליגות' clears only the leagues", () => {
  const onToggleFilter = vi.fn();
  const items = [
    story("h", "high_feed", "NBA"),
    story("f1", "feed", "NBA"),
    story("f2", "feed", "EuroLeague"),
  ];
  const view = render(items, { activeFilters: new Set(["min:high_feed"]), onToggleFilter });
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
  const view = render(items, { activeFilters: new Set(["min:high_feed"]), onResetFilters });
  const empty = byClass(view.root, "sg-filter-empty")[0];
  expect(textOf(empty)).toContain("אין כרגע סיפורים ברמת חשוב ומעלה.");
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
  const view = render(items, { activeFilters: new Set(["min:feed", "league:NBA", "source:walla_sport"]), onToggleFilter, onResetFilters });
  const chips = byClass(view.root, "sg-filter-chip");
  expect(chips.map((chip) => chip.props["data-filter"])).toEqual(["min:feed", "league:NBA", "source:walla_sport"]);
  expect(textOf(chips[2])).toBe("וואלה ספורט");
  expect(textOf(byClass(view.root, "sg-filter-badge")[0])).toBe("3");
  act(() => chips[2].props.onClick());
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
