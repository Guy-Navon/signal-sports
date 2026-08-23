# Signal Sports — Frontend Design System ("Orbit")

Last updated: 2026-07-31 — this describes the **shipped** consumer frontend.
Orbit replaced the previous "Court Vision / The Edition" frontend entirely; that
direction, its tier composer and its story species no longer exist in the
codebase. The exploration that selected Orbit is archived in
[`SPORTS_INTELLIGENCE_OS_CONCEPTS.md`](./SPORTS_INTELLIGENCE_OS_CONCEPTS.md).

Read this before adding any consumer UI. `docs/CURRENT_PROJECT_STATE.md` carries
the whole-project summary; this file is the frontend deep reference.

---

## 1. Product thesis

**One story at the centre; its sources in orbit around it; everything else
queued behind it.**

The product exists to answer "what is worth *this* reader's attention right
now?", so the interface leads with a single answer rather than a scrollable
list. The field shows the top-ranked story large and legible; the queue behind
it is ranked, and its typography encodes that ranking so the hierarchy is
readable before any label is.

Two consequences drive most decisions below:

- **Relevance is visual, not verbal.** Type scale, density, ink and spacing
  carry the ranking. The decision word confirms it; it is never the only cue.
- **The corpus is ~95% single-source.** In a 1,356-article corpus there are 41
  clusters, maximum size 4; in a 36-hour window, 11 clusters, nine of them
  exactly two sources. The single-source field is therefore the *primary* state
  and is composed for deliberately, not treated as a degraded cluster.

Orbit geometry is deliberately **decorative and honest**: satellite position
does not encode agreement, confidence or chronology. The data cannot support
such a claim, so the UI does not make one.

---

## 2. Surface boundaries

Three worlds, one shell (`components/shell/AppShell.jsx`):

| surface | routes | shell | character |
|---|---|---|---|
| **Consumer product** | `/` (Feed), `/preferences`, `/interests`, `/calibration`, `/results`, `/account` | `AppShell area="product"` + `Atmosphere` | ambient canvas, no sidebar, masthead carries nav |
| **Ops console** | `/sources`, `/debug`, `/llm-qa` | `AppShell area="ops"` + `OpsGrid` | flat instrument panel, console rail, monospace values |
| **Utility** | `/login`, `/signup`, `/welcome`, 404 | outside both shells | product-styled, standalone |

The consumer shell sets `.orbit-product`, which re-scopes the colour tokens
(mineral signals, opaque spatial surfaces). Ops keeps the base token palette.

**Only the Feed renders Orbit itself.** Other product routes carry the shell and
its tokens but none of `.orbit-feed-view`, `.orbit-field` or `.orbit-queue-*`.
That distinction matters: several Orbit rules are scoped to those containers and
must never reach Preferences, Results or account surfaces.

---

## 3. Decision hierarchy

Four visible levels, plus `hidden` (debug-only). The contract lives in
`DECISION_CONFIG[...].orbit` in `components/feed/decisionConfig.js` and is
locked by `decisionConfig.test.js` — a level cannot silently become a twin of
its neighbour.

| level | queue title | weight | title ink | signal | density |
|---|---|---|---|---|---|
| `push` | 19 px | 660 | foreground | salmon `--orbit-alert` | full + **signal rail** |
| `high_feed` | 16.5 px | 630 | foreground | aqua `--orbit-aqua` | full |
| `feed` | 14.5 px | 590 | foreground | violet `--orbit-violet` | standard |
| `low_feed` | 13 px | 520 | secondary | desaturated `--orbit-quiet` | compact — one line, no subtitle |

`feed` and `low_feed` differ on **six** axes (size, weight, ink, hue, spacing,
density). They were once byte-identical apart from the word; the unit tests and
the browser harness both guard against regressing to that.

The signal rail on the card's inline-start edge is reserved for `push` alone,
asserted in markup *and* in paint.

**Labels are single-sourced.** `DECISION_CONFIG[...].label` is the only Hebrew
decision vocabulary; `DECISION_LABELS_HE` in `api/normalizers.js` is kept
identical by test. Orbit previously carried a private second table and the
filter chips disagreed with the cards — do not reintroduce one.

---

## 4. The story field

`components/feed/orbit/OrbitStoryField.jsx`.

### Solo (single source) — the primary state

`.orbit-field--solo`. No satellite is rendered: the core's own meta line already
names the source, so an orbiting chip would only repeat it beside a large empty
field. The field is shorter (560 px desktop, ~400 px at 390), and the core and
signal meter sit on one vertical axis.

### Clustered (2–4 sources)

Up to three satellites in fixed slots plus an overflow chip. Four is the corpus
maximum, so `+N` is effectively a safety path; its Hebrew is singular-aware
(`עוד מקור אחד`).

### Expanded cluster

The strongest screen in the product: *"N דיווחים מ־N מקורות. סיפור אחד."* with
each source as a card around the ellipse and the story core at the centre.
Sequence numbers and role labels (`הדיווח המוצג` / `העדכון האחרון` /
`דיווח נוסף`) show how the story accumulated. **Preserve this.**

---

## 5. Queue behaviour

`components/feed/orbit/OrbitFeedView.jsx` + `orbitQueueMotion.js`.

**The queue renders a bounded page of 40 cards** with a "show more" control. The
heading shows `visible/total` while more remain. This is not cosmetic: the
number of animating, laid-out nodes must not track feed size.

**Motion is bounded, not merely fast.** Two rules make filtering feel immediate:

1. the enter stagger is **capped** at 6 steps, so settle time is constant for
   any list length (`queueSettleSeconds(198) === queueSettleSeconds(50)`,
   test-locked);
2. **removal is not animated** — a card that stops matching unmounts
   synchronously.

The previous strategy (`delay: index * 0.025` inside `AnimatePresence`) meant
card 196 began animating 4.9 s after a filter click while exiting cards stayed
mounted: filtering 198 → 20 left 197 stale cards on screen for 4–8 s while the
header already read "20 תוצאות". Measured after the fix: **stale cards clear in
16–56 ms**. Do not reintroduce an index-proportional delay.

---

## 6. Typography

Two faces, with a deliberate boundary.

**Frank Ruhl Libre 500 — display serif, consumer product only.** Exactly four
rules consume it, each targeting a specific element:

- `.orbit-feed-heading h1` — the feed's main headline
- `.orbit-core h2` — the focused story headline
- `.orbit-cluster__core h3` — the expanded cluster's central headline
- `.orbit-feed-empty h2` — the consumer feed's empty-state heading

**Heebo everywhere else**, including queue titles, filters, labels, body copy,
DeskVoice, metadata, timestamps, source names, buttons, navigation, and all Ops
and utility surfaces.

### Scoping rules — do not break these

- `--font-display` **stays Heebo** in `:root`. Ops, Auth, 404 and `PageHeader`
  use that token; leaving it alone is what keeps them untouched.
- The serif lives in its own token, `--orbit-serif`, declared on
  `.orbit-feed-view`.
- **No global `h1`/`h2`/`h3` rule and no `.font-display` override.** Either
  would leak the face onto non-product routes.
- Only weight **500** is imported. `500.css` gates each subset by
  `unicode-range`, so the Hebrew face is the only one fetched for Hebrew copy.

### Hebrew tuning

The serif carries more vertical detail than Heebo, so the sans's tight tracking
closes its counters: tracking is relaxed (`-0.035em` → `-0.012em`) and leading
opened (1.15 → 1.22 on the H1, 1.16 → 1.24 on the core). **Type sizes are
unchanged** — never shrink display type to hide a face swap.

Weight 500 rather than a bolder cut is deliberate: on the near-black canvas a
heavy serif reads ornamental. The sans/serif split carries the editorial
identity, not weight.

---

## 7. RTL and responsive rules

**Hebrew-first, RTL-first.** Hard rules:

- `<html lang="he" dir="rtl">` is set in `frontend/index.html`. This is what
  makes Radix portals (which render into `document.body`) inherit RTL — a
  div-level `dir` does **not** reach them.
- **Logical properties/utilities only**: `inset-inline-*`, `border-inline-*`,
  `margin-inline`, `padding-inline`, `ms-/me-/ps-/pe-`, `start-/end-`,
  `text-start/text-end`. **Never** `ml-/mr-/pl-/pr-/left-/right-`.
- Prefer `gap` over `space-x-*` (the latter needs `space-x-reverse` in RTL).
- Wrap LTR runs (source names, English entities) in `<bdi dir="auto">`.
- Numerals that must read LTR carry `dir="ltr"`.
- Visual position must never reorder the accessibility tree.

Breakpoints:

| range | layout |
|---|---|
| ≥1200 px | field and queue side by side; field is `position: sticky` |
| 768–1199 px | stacked; queue becomes a two-column grid; field 620 px (solo 520 px) |
| ≤767 px | single column; field height auto; signal meter becomes a horizontal chip in normal flow |

**Cascade warning.** `orbit.css` declares some base rules *after* their
modifiers, so a modifier that ties on specificity loses. Three rules
intentionally repeat their class or restate themselves inside a media query and
are commented as load-bearing —
`.orbit-queue-story.orbit-queue-story--<tone> h3`, `.orbit-field--solo` height
inside `@media (max-width: 1199px)`, and `.orbit-field--solo .orbit-core` inside
`@media (max-width: 767px)`. Do not "simplify" them; each one silently broke a
shipped surface when it was a single class.

---

## 8. Keyboard focus and reduced motion

Focus is **ref-based**. There are no `document.querySelector` lookups, no
class-name coupling and no `requestAnimationFrame` chains in the Orbit
components.

Decisions live as pure functions in `orbitFocusModel.js` (node-tested): focus
intents per interaction, a scroll policy resolved against the viewport,
`resolveStoryChange` for a story replaced by a filter, and `isFieldExpanded`.

**Each view focuses its own element on mount** (`useSelfFocus`). Focusing across
component boundaries is not deterministic here: `AnimatePresence` decides when
the incoming view mounts, and on collapse the compact core — which owns the
primary action — is absent for that commit. A parent effect therefore found a
null ref, dropped the intent, and focus fell to `<body>`. Inside the view the
ref is attached by definition, so no animation-completion callback or retry is
needed. Only scrolling stays imperative, because the `<section>` is not
animated and its position is stable immediately.

Guaranteed transitions, asserted in a real browser under **both** motion
preferences:

| action | focus lands on |
|---|---|
| choose a queue story | that story's core |
| open a cluster | the close control |
| switch stories while expanded | previous expansion collapses; focus follows the **new** core |
| close | the primary action |

**Reduced motion** is honoured through `useReducedMotion`; the enter stagger
drops to zero and durations shorten. There are **no CSS `animation` declarations
in `orbit.css`**, so nothing bypasses the preference.

---

## 9. Backend authority vs local hydration

Cluster values are **backend-authoritative**. `ClusterCard`
(`docs/CLUSTERING.md` §9) guarantees `source_count`, `members`,
`displayed_article_id` and `sort_at` are VISIBLE-only and test-locked
server-side, and `api/normalizers.js` maps each one directly.

`prepareFeedItems(items, { isBackendMode, localScoredArticles })` owns the split:

- **backend** — items pass through untouched; same array, same object
  identities. Debug renders the same payload, so the two views cannot disagree.
- **local/mock** — clusters are hydrated from the scored catalogue, because
  local clusters carry no `members`.

The render path reads authoritative values too, not just the preparation path:

- `orbitSourceCount(item, reports)` prefers a finite `item.sourceCount` and
  deduplicates reports only as a local fallback;
- `orbitStoryTimestamp(item, reports)` prefers `item.lastUpdatedAt`, deriving
  from reports only as a local/legacy fallback.

`latestReportTimestamp(reports)` is kept separate on purpose: rendering *reads*
`lastUpdatedAt` while local hydration *calculates* it. Merging them would make
hydration echo whatever stale value a mock item already carried.

Adversarial tests construct clusters where the backend value and the client
derivation deliberately disagree, so any fallback for a backend item fails.

---

## 10. Verification

Three layers.

**Unit (node, no jsdom).** `npm test` — the repo deliberately has no
component-testing stack. Logic that needs testing is extracted into pure modules
(`orbitStoryModel`, `orbitQueueMotion`, `orbitFocusModel`, `decisionConfig`,
`feedFilters`, `storyLabels`).

**Hermetic browser harness.** `npm run capture:orbit` drives the real app
through Chrome over CDP and asserts what the browser *paints*:

- rendered decision signatures stay distinct with a strictly descending type
  scale (config-level tests cannot catch this — a correct config once rendered
  at one size because a ranking rule lost the cascade);
- filtering clears stale cards within 100 ms;
- the queue is bounded to 40 and "show more" reveals exactly one page;
- focus transitions land correctly, both motion modes;
- the fixed dock occludes no control, using `elementFromPoint`;
- computed font families — serif only where intended, zero serif on `/debug`,
  `/results`, `/preferences`, `/no-such-route`, and `--font-display` still sans.

**Harness ownership.** The harness reserves a free ephemeral port, captures Vite
stdout/stderr, refuses a 200 from a dead child, and proves in-page that it is
the local-data instance (local mode never calls `/api/`). It once "passed"
against a different application that owned a fixed port;
`capture-orbit-production.test.mjs` locks that regression. Redirecting routes
fail the audit explicitly rather than being measured on the wrong page.

Guards against vacuous passes are mandatory: every asserted element must exist,
and an audit with nothing to measure fails.

---

## 11. Accepted limitations at 320 px

Measured, not assumed; documented rather than hidden:

- **The signal chip may require a small scroll.** At 320×640 there is not enough
  height for core, action and chip above the fixed dock. The chip is an
  indicator, not a control. It is fully visible at rest at 390.
- **The primary action must remain unobstructed** — this one is enforced. It
  once rested with 28 of its 44 px under the dock; spacing was corrected and
  `assertDockOcclusion` now fails if it is covered at rest. Clearance is 8 px at
  320 and 252 px at 390; focusing any story scrolls the field and widens that to
  245 px.
- **The field caption renders only its first half** (`הסיפור שמוביל כרגע`,
  without the source count) at 320. Pre-existing, unrelated to the Orbit
  typography or layout work.
- **Auth typography is not reachable** in the hermetic harness: `main.jsx`
  redirects `/login` and `/signup` away in local/bypass mode, the mode the
  harness runs. `/no-such-route` exercises the identical `font-display` utility.
- **`.orbit-feed-empty h2` is implemented but not browser-verified**: it renders
  only when zero items are visible, which the real corpus cannot produce. No
  synthetic data path was added to force it.

---

## 12. Component inventory

```
components/feed/orbit/
  OrbitFeedView.jsx      heading, filters, queue, focus orchestration
  OrbitStoryField.jsx    solo + clustered + expanded field, self-owned focus
  orbit.css              all Orbit styling (scoped, imported by Feed)
  orbitStoryModel.js     cluster reads, authority resolvers, local hydration
  orbitQueueMotion.js    bounded stagger + pagination budget
  orbitFocusModel.js     focus intents, scroll policy, story-change resolution
components/feed/
  decisionConfig.js      decision contract: labels, tone, strength, orbit block
  feedFilters.js         level + topic filtering
  storyLabels.js         Hebrew kickers, condensed reasoning
  DeskVoice.jsx          "why you're seeing this", one clamped line
  FeedbackControls.jsx · SourceMeta.jsx · EditionEmptyState.jsx
  DecisionBadge.jsx      console affordance (Debug / LLM-QA / Preferences)
  clusterModel.js        cluster roles for Debug's ClusterEvidence
components/shell/
  AppShell · Masthead · MobileNav · ProductNav · OpsNav · Atmosphere ·
  OpsGrid · SignalMark
```

`EditionEmptyState` keeps its legacy name but is live — it is the consumer
feed's zero-items state. The Edition-era story species (`LeadStory`,
`BulletinStrip`, `EditorialTier`, `StreamRow`, `BriefsDigest`, `SignalBoard`,
`SignalSpectrum`, `TopicFilters`, `SectionHeading`, `EditionHeader`,
`EditionSkeleton`, `ClusterSources`, `editionComposer`, `motionPresets`) were
removed when Orbit shipped.

---

## 13. Engineering rules

1. **Components render; models decide.** Anything worth testing goes in a pure
   module beside the component.
2. **Never trust source CSS for a visual guarantee.** If it matters, assert the
   computed value in the harness.
3. **No DOM queries for focus or identity.** Use refs; focus from inside the
   view that owns the element.
4. **Backend-authoritative values are read, never re-derived** — in both the
   preparation and the render path.
5. **Logical properties only.** RTL is the default, not an adaptation.
6. **Bounded work.** Anything proportional to feed size (animation, layout,
   rendered nodes) must be capped.
7. **Scope new tokens.** Never redefine a shared token to style one surface.
