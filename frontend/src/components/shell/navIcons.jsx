import React from "react";
import { Newspaper, SlidersHorizontal, Target } from "lucide-react";
import { consumerIconKey } from "./productShellModel";

// The consumer header's icon set (#491). Lucide geometry: 24px grid, 2px
// stroke, round caps and joins, no fill, so the custom scoreboard sits in the
// same family as the three Lucide icons beside it. The shared navConfig icons
// are left alone: the Ops rail renders them and must not change.

function scoreboard(name, children) {
  function ScoreboardIcon({ size = 24, strokeWidth = 2, className = "", ...rest }) {
    return (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        className={`lucide ${className}`.trim()}
        {...rest}
      >
        {children}
      </svg>
    );
  }
  ScoreboardIcon.displayName = name;
  return ScoreboardIcon;
}

// A: a score panel, two score blocks and a colon between them.
export const ScoreboardPanel = scoreboard("ScoreboardPanel", (
  <>
    <rect x="2" y="5" width="20" height="14" rx="2.5" />
    <rect x="5.5" y="9" width="4" height="6" rx="1" />
    <rect x="14.5" y="9" width="4" height="6" rx="1" />
    <path d="M12 10.25v.01M12 13.75v.01" />
  </>
));

// B: a stadium board on two posts, two score blocks.
export const ScoreboardStand = scoreboard("ScoreboardStand", (
  <>
    <rect x="3" y="3" width="18" height="12" rx="2" />
    <rect x="6.5" y="6.5" width="3.5" height="5" rx="1" />
    <rect x="14" y="6.5" width="3.5" height="5" rx="1" />
    <path d="M8 15v6M16 15v6" />
  </>
));

// C: two flip-score cards side by side, each with its hinge line.
export const ScoreboardFlip = scoreboard("ScoreboardFlip", (
  <>
    <rect x="2" y="5" width="9" height="14" rx="2" />
    <rect x="13" y="5" width="9" height="14" rx="2" />
    <path d="M2 12h9M13 12h9" />
  </>
));

export const RESULTS_ICON_CANDIDATES = [
  { id: "panel", label: "לוח עם נקודתיים", Icon: ScoreboardPanel },
  { id: "stand", label: "לוח על עמודים", Icon: ScoreboardStand },
  { id: "flip", label: "כרטיסי ניקוד מתהפכים", Icon: ScoreboardFlip },
];

export const CONSUMER_NAV_ICONS = {
  feed: Newspaper,
  results: ScoreboardPanel,
  preferences: SlidersHorizontal,
  calibration: Target,
};

// The icon of one consumer destination: the new set, or the item's own
// navConfig icon for a destination the set does not know yet.
export function consumerIcon(item) {
  return CONSUMER_NAV_ICONS[consumerIconKey(item.path)] ?? item.icon;
}
