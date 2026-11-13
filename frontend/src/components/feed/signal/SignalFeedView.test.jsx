import React from "react";
import { act, create } from "react-test-renderer";
import { afterEach, expect, it, vi } from "vitest";
import { normalizeScoredArticleFromApi } from "@/api/normalizers";
import FeedbackControls from "@/components/feed/FeedbackControls";
import SignalFeedView from "./SignalFeedView";

// The new feed view (#464) rendered in node, the way the Orbit read-only test
// does it. The public demo (#469) will render it with no AppProvider.

const REASON = "מכבי תל אביב (כדורסל) ברשימת המעקב שלך";
const NOW = Date.parse("2026-11-13T18:00:00Z");

function story(id, decision, league = "EuroLeague") {
  return normalizeScoredArticleFromApi({
    decision,
    reason_he: REASON,
    article: {
      id,
      source: "walla_sport",
      source_display_name: "וואלה ספורט",
      url: `https://example.test/${id}`,
      title: `כותרת ${id}`,
      published_at: "2026-11-13T16:00:00Z",
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

it("the league pills say whether they are selected", () => {
  const items = [story("a", "feed", "NBA"), story("b", "feed", "EuroLeague")];
  const view = render(items, { activeFilters: new Set(["league:NBA"]) });
  const pressed = byClass(view.root, "sg-pill").map((pill) => pill.props["aria-pressed"]);
  expect(pressed).toEqual([false, true, false]);
  expect(JSON.stringify(view.toJSON())).not.toContain("כותרת b");
});
