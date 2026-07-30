# Orbit B1 + B2 — decision hierarchy and bounded queue motion

Visual evidence for the first improvement scope on the Orbit feed. Every capture
is the real application (`VITE_DATA_MODE=backend`) against the real article
corpus — 1,356 articles, 198 in Guy's feed, RTL Hebrew.

`before/` was captured **before any code in this scope was written**.
`after/` was captured from the same states once it was done.

## Capture conditions

Two process-level environment overrides, no file changed:

- `FEED_FRESHNESS_ENABLED=false` — the corpus's newest article is 2026-07-24, so
  the production 36-hour window renders an empty feed.
- `ALLOW_INSECURE_AUTH_BYPASS=true` — the project's documented local-only bypass;
  `/api/feed/{user_id}` is admin-gated.

Both are disclosed because they change what the screenshots show. Nothing was
committed from the live database, and it was neither copied nor modified.

## What this scope changed

### 1. Filtering is immediate

Filtering 198 stories down to 20 used to leave **197 stale cards on screen for
4–8 seconds** while the header already read "20 תוצאות". The cause was
`delay: index * 0.025` inside `AnimatePresence`: card 196 began animating 4.9s
after the click, and exiting cards stayed mounted throughout.

| | stale cards clear |
|---|---|
| before | between 4,000 ms and 8,000 ms |
| after | **16 ms** (first sampled frame) |

The fix is structural, not a smaller multiplier — see
`frontend/src/components/feed/orbit/orbitQueueMotion.js`:

- the enter stagger is **capped** at 6 steps, so settle time is constant for any
  list length (`queueSettleSeconds(198) === queueSettleSeconds(50)`, locked by test);
- removal is **not animated**, so a card that stops matching unmounts at once;
- the rendered queue is **bounded** to 40 cards with a "show more" control, so
  per-frame layout cost does not track feed size.

`before/14-filter-push-settled.png` · `after/13-level-push.png`

### 2. Ranking is visible without reading the label

Previously all four levels rendered at `16px / weight 610 / rgb(242,244,248)`
with identical padding — `feed` and `low_feed` shared the *same* violet dot, so
they were pixel-identical apart from one word.

| level | title | weight | title ink | signal | padding | density |
|---|---|---|---|---|---|---|
| push | 19 px | 660 | `#F2F4F8` | `#FF7F66` | 21/11 | full + signal rail |
| high_feed | 16.5 px | 630 | `#F2F4F8` | `#7AD6D0` | 18/10 | full |
| feed | 14.5 px | 590 | `#F2F4F8` | `#908AE5` | 15/9 | one-line subtitle |
| low_feed | 13 px | 520 | `#9AA2B6` | `#9296AB` | 10/8 | compact, no subtitle |

`feed` and `low_feed` now differ on six axes: size, weight, title ink, signal
hue, spacing and density.

The contract lives in `DECISION_CONFIG[…].orbit` in
`frontend/src/components/feed/decisionConfig.js` and is locked by
`decisionConfig.test.js` — a level cannot silently become a twin of its neighbour.

Clearest evidence: `after/15-boundary-push-high.png` and
`after/16-boundary-feed-low.png` show the tier changes mid-scroll.

### 3. One Hebrew vocabulary

Filter chips used to read `דחוף / חשוב / במסלול / שקט` while cards read
`דורש תשומת לב / חשוב / רגיל / נמוך` — three of four disagreed, both visible in a
single screenshot.

Orbit's private `LEVEL_LABELS` table is deleted. Everything now reads
`getDecisionConfig(id).label`. Consolidation went **into** the existing shared
source of truth rather than replacing its wording, so the Ops console
(`DecisionBadge` in Debug / LLM-QA / ProfileComparison) is byte-identical.

Trade-off: `דורש תשומת לב` is a long filter chip. Left as-is deliberately — one
vocabulary beats a shorter chip. Worth revisiting as a naming decision, not a
per-surface override.

## Not in this scope

The one-source field layout (~95% of real feed items), mobile field resilience,
typography, cluster-value authority, focus management and component cleanup are
all deliberately untouched. The multi-source expanded field
(`after/06-desktop-sources-4-expanded.png`) is preserved unchanged — it remains
the strongest screen in the product.

## Index

| state | before | after |
|---|---|---|
| Desktop, top of feed | `before/01-desktop-default.png` | `after/01-desktop-default.png` |
| Desktop, queue scrolled | — | `after/02-desktop-scrolled.png` |
| push tier | `before/13-level-push.png` | `after/13-level-push.png` |
| high_feed tier | `before/13-level-high_feed.png` | `after/13-level-high_feed.png` |
| feed tier | `before/13-level-feed.png` | `after/13-level-feed.png` |
| low_feed tier | `before/13-level-low_feed.png` | `after/13-level-low_feed.png` |
| push → high_feed boundary | — | `after/15-boundary-push-high.png` |
| feed → low_feed boundary | — | `after/16-boundary-feed-low.png` |
| Filter settled | `before/14-filter-push-settled.png` | `after/13-level-push.png` |
| 4-source expanded (preserved) | `before/06-desktop-sources-4-expanded.png` | `after/06-desktop-sources-4-expanded.png` |
| Reduced motion | `before/09-desktop-reduced-motion.png` | `after/09-desktop-reduced-motion.png` |
| Mobile 390 field | `before/10-mobile-390-default.png` | `after/10-mobile-390-default.png` |
| Mobile 390 queue | `before/11-mobile-390-queue.png` | `after/11-mobile-390-queue.png` |
| Mobile 320 field | `before/10-mobile-320-default.png` | `after/10-mobile-320-default.png` |
| Mobile 320 queue | `before/11-mobile-320-queue.png` | `after/11-mobile-320-queue.png` |
