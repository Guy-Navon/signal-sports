// Browser-harness fixture only. Local legacy scores have no reasonHe, so the
// typography audit must render a reader sentence explicitly (#497), rather than
// depending on an admin trace. This module is never imported by a product entry.
import React from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import SignalFeedView from "../src/components/feed/signal/SignalFeedView";

export const READER_REASON = "NBA ברשימת המעקב שלך";
let root;
let container;

export function mount() {
  container = document.createElement("div");
  container.id = "reader-reason-fixture";
  document.body.append(container);
  root = createRoot(container);
  flushSync(() => root.render(
    <SignalFeedView
      items={[{
        id: "reader-reason-fixture", type: "article", title: "תרחיש בדיקה: הסבר לקורא",
        sourceDisplayName: "מקור לבדיקה", league: "NBA",
        score: { decision: "feed", reasonHe: READER_REASON, reasoning: ["ניקוד: 3 → חשוב"] },
      }]}
      readOnly
      activeFilters={new Set(["all"])}
      onToggleFilter={() => {}}
      onResetFilters={() => {}}
    />
  ));
  return {
    text: container.querySelector(".sg-row__why")?.textContent,
    expected: READER_REASON,
  };
}

export function unmount() {
  flushSync(() => root.unmount());
  container.remove();
}
