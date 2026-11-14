# Orbit — historical screenshot record

Last updated: 2026-11-14 (#473). These screenshots and measurements record the former
2026-07-31 consumer UI. They are not the current implementation or an acceptance reference.
All consumer screens and the demo on `ui/next` use Signal UI; the unused Orbit code was
removed in #473. See [FRONTEND_DESIGN_SYSTEM.md](../../FRONTEND_DESIGN_SYSTEM.md) for the
current engineering and visual contract. No current deployment is claimed here.

Visual record of the Orbit consumer frontend as merged. Captured from the real
application (`VITE_DATA_MODE=backend`) against the real corpus — 198 stories in
Guy's feed, RTL Hebrew — with `document.fonts.ready` awaited before every
measurement and screenshot.

Orbit's look was superseded on 2026-11-13 by the direction in
[`docs/FRONTEND_DESIGN_SYSTEM.md`](../../FRONTEND_DESIGN_SYSTEM.md) Part B (milestone 15). It
is retained here only as historical evidence, independently of the removed implementation.
Orbit was selected over two other concepts, Pulse and Vector, in a July 2026 exploration. That
write-up and its comparison screenshots were retired on 2026-10-12 and are in git history
(`docs/SPORTS_INTELLIGENCE_OS_CONCEPTS.md`, `docs/frontend-concepts/sports-intelligence-os/`).

Capture conditions: `FEED_FRESHNESS_ENABLED=false` (the corpus is older than the
production 36-hour window) and `ALLOW_INSECURE_AUTH_BYPASS=true` (the documented
local-only bypass). Both are process-level; no file changed, and the live
database was neither copied nor modified.

## Screens

| file | what it shows |
|---|---|
| `01-desktop-solo-field.png` | the single-source field — ~95% of real items, composed as the primary state |
| `02-desktop-3-source-compact.png` | a 3-source cluster with satellites |
| `03-desktop-4-source-expanded.png` | the expanded field: *"4 דיווחים מ־4 מקורות. סיפור אחד."* |
| `04-desktop-tier-low-feed.png` | the `low_feed` tier — compact, dimmed, one line, no subtitle |
| `05-tier-boundary-feed-to-low.png` | **the hierarchy proof**: `רגיל` rows give way to `נמוך` rows mid-scroll |
| `06-mobile-390.png` · `07-mobile-320.png` | both mobile widths |
| `08-mobile-390-reduced-motion.png` | `prefers-reduced-motion: reduce` |
| `09-ops-debug-no-serif.png` | Ops console — no serif leakage |

## Measured on this run

Raw values in `verification.json`.

| check | result |
|---|---|
| horizontal overflow (desktop / 390 / 320 / ops) | −10 / 0 / 0 / −10 px — none |
| queue pagination | 40 of 197 rendered, "עוד 157 במסלול" |
| expanded cluster | 4 reports, correct heading |
| console errors | 0 |
| Ops serif elements | 0 (`h1` = Heebo) |

Decision levels — filtering isolates each one, and the rendered type scale is
strictly descending:

| level | queue after filter | tones present | title size |
|---|---|---|---|
| `push` | 19 | `push` | 19 px |
| `high_feed` | 37 | `high` | 16.5 px |
| `feed` | 40 (capped, 103 results) | `feed` | 14.5 px |
| `low_feed` | 36 | `low` | 13 px |

Filter latency measured **in-page** by the hermetic harness (no CDP round-trip):
**15 ms** normal motion, **43 ms** reduced — against a 100 ms budget, and against
4,000–8,000 ms before the queue-motion fix.

## Historical residuals

These limitations belong to the old captures and do not describe Signal UI.

- At 320×640 the signal chip may need a small scroll. The **primary action is
  enforced clear** of the fixed dock by the harness used for this historical run.
- The compact field caption renders only its first half at 320 px (pre-existing).
- Auth typography cannot be reached in the hermetic harness — local mode
  redirects `/login` and `/signup`. `/no-such-route` covers the identical
  `font-display` utility.
- The former empty-state headline was not browser-verified: it rendered only
  when zero items were visible, which the real corpus could not produce. No synthetic
  data path was added to force it.
