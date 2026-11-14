# Signal Sports — Frontend Design System

Last updated: 2026-11-13 (#461). This file has two parts and an appendix:

- **Part A: engineering and accessibility rules.** These hold for any consumer UI, the one on
  main today and the new one. Each statement was checked against `frontend/` on 2026-11-13.
- **Part B: visual language.** On 2026-11-13 Guy approved a new direction from a coded mock
  built on his real feed. Part B describes that direction in full. **Orbit's colours, type,
  shapes and composition are superseded and are not a starting point** for any new work.
- **Appendix C: Orbit as it still ships on main.** Maintenance facts only, removed by #473.

**What is implemented.** Orbit is still the consumer UI on main and in the public demo.
Part B is delivered by milestone 15, "A face of its own — new consumer UI" (#461–#475), on
the integration branch `ui/next`. On `ui/next` so far: the tokens, fonts and marks (#462) and
the feed body (#464: `components/feed/signal/`, used by `pages/Feed.jsx`; the demo still
renders Orbit until #469). Merging `ui/next` to main and
deploying the demo need Guy's explicit approval (#475). Each Part B section names the issue
that delivers it.

The reference mock is committed in
[`design/2026-11-13-feed-direction/`](./design/2026-11-13-feed-direction/README.md): the
approved template and a script that fills it with the demo snapshot. If this doc and the mock
disagree, this doc wins. Approved artifact (private, real data):
https://claude.ai/artifact/D9QZpZhfcz4rpYddXMPHZD.

`docs/CURRENT_PROJECT_STATE.md` carries the whole-project summary. This file is the frontend
deep reference. Read it before adding any consumer UI.

---

# Part A — Engineering and accessibility rules (stay)

## A1. Surfaces and scope

| surface | routes | shell |
|---|---|---|
| **Consumer product** | `/` (Feed), `/preferences`, `/interests`, `/calibration`, `/results`, `/account` | `AppShell area="product"` |
| **Ops console** (admin only, `RequireOpsRole`) | `/sources`, `/debug`, `/llm-qa` | `AppShell area="ops"` |
| **Utility** | `/login`, `/signup`, `/verify-email`, `/forgot-password`, `/reset-password`, `/welcome`, 404 | outside both shells, product-styled |
| **Public demo** | `frontend/demo.html` → `src/demo/` (its own Vite entry) | no router, no auth, no app provider |

- **Milestone 15 covers** the consumer product, the utility screens and the public demo.
- **The Ops console does not change.** It keeps its current look and the base `:root` tokens in
  `src/index.css`. Consumer tokens are scoped to the consumer shell. On main the product shell
  sets `.orbit-product` (`AppShell.jsx`), which re-scopes the colour tokens. On `ui/next` (#463)
  `ProductShell.jsx` puts `.signal-ui` (#462) on its chrome and chooses the page body's scope per
  route (`productShellModel.pageSurface`): pages not yet rebuilt keep `.orbit-product` on the
  body, rebuilt pages are listed in `SIGNAL_SURFACE_PATHS` and get `.signal-ui`. Never redefine
  a shared token to style one surface.
- **Changing the look never changes what the user sees.** Exposure rules, engine decisions,
  ranking and filter behaviour are not touched to make a screen look fuller.

## A2. RTL and mixed direction

Hebrew-first, RTL-first. Hard rules:

- `<html lang="he" dir="rtl">` is set in `frontend/index.html` and `frontend/demo.html`. This
  is what makes Radix portals (rendered into `document.body`) inherit RTL. A div-level `dir`
  does **not** reach them.
- **Logical properties and utilities only**: `inset-inline-*`, `border-inline-*`,
  `margin-inline`, `padding-inline`, `ms-/me-/ps-/pe-`, `start-/end-`, `text-start/text-end`.
  **Never** `ml-/mr-/pl-/pr-/left-/right-`, `margin-left` or `text-left`. This also applies to
  slanted strokes, hover edges and shadows: pick the edge by inline direction, not by a
  physical offset.
- Prefer `gap` over `space-x-*` (the latter needs `space-x-reverse` in RTL).
- Wrap LTR runs (source names, English entities, team names without a Hebrew name) in
  `<bdi dir="auto">`. Numerals that must read LTR (scores, counts in mixed runs) carry
  `dir="ltr"`, and counts and scores use tabular figures.
- Visual position must never reorder the accessibility tree.
- Phone widths 320–390 px have no horizontal page scroll. Rows that can overflow (league pills,
  the results strip) scroll inside themselves.

## A3. Decision levels, labels and data honesty

Four visible levels: `push`, `high_feed`, `feed`, `low_feed`. `hidden` never reaches a
consumer screen. It exists only in the Debug console.

- **The contract lives in `components/feed/decisionConfig.js`** (`DECISION_CONFIG`,
  `DECISION_RANK`: low_feed 1, feed 2, high_feed 3, push 4) and is locked by
  `decisionConfig.test.js`. The signal mark's fill count (B4) is that rank.
- **Labels are single-sourced.** `DECISION_CONFIG[...].label` is the only Hebrew decision
  vocabulary (`דורש תשומת לב`, `חשוב`, `רגיל`, `נמוך`). `DECISION_LABELS_HE` in
  `api/normalizers.js` is kept identical by test. Do not add a second table. Orbit once had
  a private one, and the filter chips disagreed with the cards. Section titles such as
  "בקצרה" (In brief) are headings, not decision labels.
- **Relevance is visual, not verbal.** Placement and the signal mark carry the level. The
  decision word confirms it, and it is never the only cue. Every visual cue has an accessible
  name.
- **Nothing is invented to fill a screen.** No push means no lead block. No results means no
  results strip, not a placeholder. Counts and the summary line come from the real feed. The
  side column never shows hidden stories and never reorders the ranked stream.
- **Reader explanations.** `DeskVoice` / `deskVoiceModel.js`: readers get `reason_he` (one Hebrew
  sentence, or nothing). Admin and local QA get the engine trace. The new "why it is with you"
  line uses the same model.
- **Read-only mode.** The demo renders the feed with `readOnly`: no feedback controls, no engine
  trace, no write path. `npm run check:demo-bundle` enforces this on the built bundle (A7).

## A4. Backend authority vs local hydration

Cluster values are **backend-authoritative**. `ClusterCard` (`docs/CLUSTERING.md` §9) guarantees
that `source_count`, `members`, `displayed_article_id` and `sort_at` are VISIBLE-only and
test-locked server-side, and `api/normalizers.js` maps each one directly.

`prepareFeedItems(items, { isBackendMode, localScoredArticles })` (today in
`orbitStoryModel.js`) owns the split:

- **backend**: items pass through untouched, same array, same object identities. Debug renders
  the same payload, so the two views cannot disagree.
- **local/mock**: clusters are hydrated from the scored catalogue, because local clusters
  carry no `members`.

The render path reads authoritative values too:

- `orbitSourceCount(item, reports)` prefers a finite `item.sourceCount` and deduplicates reports
  only as a local fallback. The cluster badge ("N מקורות") reads it.
- `orbitStoryTimestamp(item, reports)` prefers `item.lastUpdatedAt`, deriving from reports only
  as a local/legacy fallback. Story times and the "Latest" ordering read it.
- `latestReportTimestamp(reports)` stays separate on purpose: rendering *reads*
  `lastUpdatedAt` while local hydration *calculates* it. Merging them would make hydration echo
  whatever stale value a mock item already carried.

Adversarial tests build clusters where the backend value and the client derivation
deliberately disagree, so any fallback for a backend item fails. When #464 renames or moves
these models, the tests move with them unchanged.

## A5. Bounded work

Anything proportional to feed size (animation, layout, rendered nodes) is capped.

- **The ranked list renders a bounded page of 40** with a "show more" control
  (`QUEUE_PAGE_SIZE` in `orbitQueueMotion.js`). The heading shows `visible/total` while more
  remain. This is not cosmetic: the number of animating, laid-out nodes must not track feed
  size.
- **Enter stagger is capped** at 6 steps (`QUEUE_STAGGER_MAX_STEPS`, step 0.018 s), so settle
  time is constant for any list length (`queueSettleSeconds(198) === queueSettleSeconds(50)`,
  test-locked).
- **Removal is not animated.** A row that stops matching a filter unmounts synchronously. An
  earlier `delay: index * 0.025` inside `AnimatePresence` left 197 stale cards on screen for
  4–8 s after filtering 198 → 20. After the fix, stale cards clear in 16–56 ms. Never
  reintroduce an index-proportional delay.
- No virtualization library. The cap is the mechanism.

## A6. Keyboard focus and reduced motion

- **Focus is ref-based.** No `document.querySelector` lookups, no class-name coupling and no
  `requestAnimationFrame` chains for focus or identity.
- **Decisions are pure functions** (today `orbitFocusModel.js`, node-tested): focus intents per
  interaction, a scroll policy resolved against the viewport, what happens when a filter
  removes the focused story.
- **Each view focuses its own element on mount** (`useSelfFocus` in `OrbitStoryField.jsx`).
  Focusing across component boundaries is not deterministic: `AnimatePresence` decides when the
  incoming view mounts, so a parent effect can find a null ref and drop focus to `<body>`.
  Inside the view the ref is attached by definition. Only scrolling stays imperative.
- Every interaction that moves or removes content says where focus lands, and the harness
  asserts it under both motion preferences (A7).
- **Visible focus**: `:focus-visible` outline in `currentColor`, 2 px, offset 2 px (the mock's
  rule). It works on every ground, including the lead block.
- **Reduced motion is honoured everywhere.** Framer Motion components use `useReducedMotion`.
  CSS animations and transitions are also neutralised by the global
  `@media (prefers-reduced-motion: reduce)` rule in `src/index.css` (durations to 0.01 ms, one
  iteration). Any looping animation (the fresh-story pulse) must stop under the preference,
  not merely shorten. Nothing may convey information through motion alone.

## A7. Verification

**Unit tests.** `npm test` runs Vitest in the `node` environment (`vite.config.js`). There is
no jsdom, no React Testing Library and no browser test stack, and none is added. Logic worth
testing is extracted into pure modules (`decisionConfig`, `feedFilters`, `storyLabels`,
`feedLoadModel`, `deskVoiceModel`, the orbit story/queue/focus models). A few `.test.jsx`
files render components with `react-test-renderer` in node (for example
`OrbitFeedView.readOnly.test.jsx`).

**Hermetic browser harness.** `npm run capture:orbit` (`scripts/capture-orbit-production.mjs`)
drives the real app through Chrome over CDP and asserts what the browser *paints*: distinct
decision signatures, stale rows cleared within a 100 ms budget, the 40-row page bound, focus
transitions under both motion modes, no control occluded by a fixed element (via
`elementFromPoint`), and computed font families per route. It reserves a free ephemeral port,
captures Vite output, refuses a 200 from a dead child, and proves in-page that it is the
local-data instance (local mode issues no `/api/` request). `capture-orbit-production.test.mjs`
locks the time it "passed" against another app on a fixed port. Every asserted element must
exist, and an audit with nothing to measure fails. Since #464 it asserts the new feed body:
placement by level (lead only with a push, important row, stream in rank order, "in brief"),
the summary counts, signal-mark fill and colour, the bounded stream page, league-pill filter
latency, pressed state and focus, cluster member links, feedback actions present and
unclipped at 320–390, typography (Assistant, Karantina on the lead only, no serif leak) and
dock occlusion. Since #465 it also asserts the side column: "Latest" newest first, never low_feed
or hidden, every story in it placed elsewhere; "in brief" only inside the column; sticky 14px
from the top halfway down the stream and inside the viewport on desktop; after the stream and
not sticky on a phone, with every visible story painted. The local corpus puts exactly 40 stories in the stream and its clusters in
the lead and important row, so the multi-page "show more" path and the stream cluster
disclosure are locked by `SignalFeedView.test.jsx` instead, and the harness output says so.
#473 renames it (`capture:orbit` stays until then). Orbit itself (still the demo) is no
longer browser-asserted.

**Demo bundle guard.** `npm run build`, `npm run build:demo`, then `npm run check:demo-bundle`.
It fails if the demo bundle holds the API client, router, auth, app provider, a non-feed page
or a write request method. Its markers are confirmed present in the main bundle, so a stale
marker fails loudly.

**Ops unchanged.** Any change to shared CSS or tokens verifies that the computed styles of
`/debug`, `/sources` and `/llm-qa` did not change (#462).

**Screens.** Consumer UI changes are captured at 1440, 390 and 320 px, in all three grounds
once #468 lands. Phone layout counts as unverified until someone has looked at it.

CI (`.github/workflows/checks.yml`) runs lint, typecheck, tests, build, build:demo and
check:demo-bundle. `scripts/check.ps1` runs the same set locally except the demo steps.

## A8. Engineering rules

1. **Components render; models decide.** Anything worth testing goes in a pure module beside
   the component.
2. **Never trust source CSS for a visual guarantee.** If it matters, assert the computed value in
   the harness.
3. **No DOM queries for focus or identity.** Use refs, and focus from inside the view that owns
   the element.
4. **Backend-authoritative values are read, never re-derived**, in both the preparation and the
   render path.
5. **Logical properties only.** RTL is the default, not an adaptation.
6. **Bounded work.** Cap anything proportional to feed size.
7. **Scope new tokens.** Never redefine a shared token to style one surface.
8. **Real data only.** Counts, summaries, results and levels come from the API or the
   snapshot. No hard-coded stories, scores or names in product code.

## A9. Models the new UI builds on

The feed is rebuilt on the existing pure models, renamed or moved only where needed (#464):

```
components/feed/
  decisionConfig.js     levels, labels, rank (drives the signal mark)
  feedFilters.js        level + topic filtering (drives the league pills, #463)
  storyLabels.js        Hebrew kickers, condensed reasoning
  feedLoadModel.js      loading / empty / error states
  deskVoiceModel.js     reader sentence vs engine trace
  feedbackSaveModel.js  feedback action state
  orbit/orbitStoryModel.js   prepareFeedItems + authority resolvers (A4)
  orbit/orbitQueueMotion.js  page size + stagger cap (A5)
  orbit/orbitFocusModel.js   focus intents and scroll policy (A6)
  signal/feedLayoutModel.js  lead / important / stream / brief, league pills, summary (#464)
  signal/signalStoryModel.js per-story sources, link, relative time, title direction (#464)
api/normalizers.js      API → view model, DECISION_LABELS_HE
components/results/     results model, grouping and formatting (#466, #471)
```

---

# Part B — Visual language (approved 2026-11-13)

## B1. Decisions

Decided by Guy on 2026-11-13, from the coded mock on his real feed:

| # | Decision | Delivered by |
|---|---|---|
| 1 | **White ground is the default.** "Soft" (grey-blue) and "dark" (slate, mint accent) remain available | #462 tokens, #468 switch |
| 2 | **Structure inspired by Axios**: navy top bar with navigation, centred wordmark with a slanted accent stroke, a summary line, league pills with counts, a row of up to four important stories | #463, #464 |
| 3 | **Lead block only when the feed has a push.** The headline fills a full-width colour block in Karantina. Summary, "why it is with you" and source sit in one row beneath. No push, no lead: importance is never invented to fill a hero | #464 |
| 4 | **Stream of compact three-line rows** with cluster badge and feedback actions. Large story cards rejected | #464 |
| 5 | **Sticky side column on desktop**: "Latest" (by time) and "In brief" (low_feed), so there is never an empty side next to a long column | #465 |
| 6 | **Results strip** of real finals between the important row and the stream | #466 |
| 7 | **Signal mark**: three slanted strokes echoing the logo stroke, filled by level | #462 |
| 8 | **Type**: Assistant for text, Karantina only for the lead headline | #462 |
| 9 | **More motion than the mock**, carrying meaning, off under reduced motion. Guy approves the set | #467 |
| 10 | **Article images: open owner decision.** The design must work without them | #474 |
| 11 | **Scope**: feed, preferences, interests, calibration, results, account, auth screens, welcome, 404, public demo. Ops keeps its look | #463–#472 |
| 12 | **Process**: work lands on `ui/next`. Merge to main and demo deploy need Guy's approval. The mock was reviewed on desktop only, so phone layout is unverified | #475 |

**Superseded.** Orbit's palette (near-black canvas, mineral signals, aqua/violet/salmon), its
type (Heebo with Frank Ruhl Libre display), its story field with orbiting satellites, its signal
rail and its queue type-scale ladder are all retired as direction. Do not port them, blend them
or treat them as a fallback. Appendix C lists them only so main can be maintained until #473
removes them.

## B2. Grounds and tokens

One look, three grounds. Every colour is a token. The values below are the mock's
`.t-light`, `.t-soft` and `.t-dark`.

In code (#462, `frontend/src/components/signal-ui/signal-ui.css`) the same tokens carry an
`--sg-` prefix (`--sg-bg`, `--sg-acc`, ...) so they cannot shadow the base component tokens.
They are scoped to `.signal-ui`; white is the default and `data-ground="soft"` or
`data-ground="dark"` on the same element switches ground. `npm run lab` (in `frontend/`)
opens a specimen page of the tokens, type and marks in all three grounds.

| token | role | white (default) | soft | dark |
|---|---|---|---|---|
| `--bg` | page ground | `#ffffff` | `#e8ecf2` | `#1a2030` |
| `--band` | band behind stream + side column | `#f3f5f9` | `#dde2ea` | `#141927` |
| `--card` | stream panel, side boxes | `#ffffff` | `#f3f5f9` | `#212839` |
| `--ink` | text | `#1c2230` | `#1c2230` | `#eef1f7` |
| `--dim` | secondary text, meta | `#667085` | `#566072` | `#a3adc0` |
| `--line` | dividers, borders | `#e2e6ee` | `#c9d0dc` | `#353e55` |
| `--acc` | accent: logo stroke, filled mark, tags, actions, link underline, box rule | `#2446e8` | `#2446e8` | `#3cffd0` |
| `--tint` | accent tint: tag ground, row hover | `#edf1ff` | `#d8e0f8` | `#25304a` |
| `--top` | top bar | `#142a66` | `#142a66` | `#0f1422` |
| `--top-fg` | top bar text | `#ffffff` | `#ffffff` | `#eef1f7` |
| `--slab` | lead block ground | `#2446e8` | `#2446e8` | `#3cffd0` |
| `--slab-fg` | lead block text and rule | `#ffffff` | `#ffffff` | `#07130f` |
| `--slab-dim` | lead decoration strokes | `#d5dcff` | `#d5dcff` | `#0d4a3b` |
| `--hot` | alert: push mark, push label, fresh marker | `#ff2f6d` | `#e0245e` | `#ff2f6d` |
| `--hot-fg` | text on `--hot` | `#ffffff` | `#ffffff` | `#ffffff` |
| `--off` | empty mark stroke | `#cfd6e4` | `#b4bdcd` | `#465069` |
| `--t1`…`--t4` | league pill tints, in order | `#e3ecff` `#ffe9dc` `#dff5ea` `#efe6ff` | `#cfdcfa` `#f6d9c8` `#c9e9d8` `#ddd2f5` | `#27365c` `#4a3528` `#1f4034` `#3a2f57` |

Contrast, measured from these values (WCAG ratio): `--dim` on `--card` 4.97 / 5.81 / 6.51;
`--acc` on `--card` 6.74 / 6.17 / 11.5; `--slab-fg` on `--slab` 6.74 / 6.74 / 14.79. **`--hot`
falls short as small text**: on `--card` 3.57 / 4.20 / 4.12, and `--hot-fg` on `--hot` 3.57
(white, dark) and 4.58 (soft). The push label and the fresh-time marker use it at 12–14 px, so
#468 must fix this (a darker text variant or a larger, bolder size) before acceptance.

## B3. Type

- **Assistant** for all text: body 400 17px/1.5. Weights used 400, 500, 600, 700, 800.
  Fallback stack `Assistant, "Noto Sans Hebrew", Arial, sans-serif`.
- **Karantina 700** for exactly one element, the lead headline:
  `clamp(54px, 10.2vw, 150px)`, line-height 0.88. Nowhere else, including empty states and
  page titles.
- Headlines use `text-wrap: balance`. Counts and scores use `font-variant-numeric:
  tabular-nums`.
- The mock loads both faces from Google Fonts. The product loads them the way it already loads
  fonts, with real fallbacks and no layout jump on load (#462). Ops keeps its current fonts.

| element | size / weight |
|---|---|
| wordmark | 44px 800, letter-spacing −0.02em (36px under 900px) |
| top bar | 13px 700, letter-spacing 0.02em |
| summary line | 14px, `--dim`, numbers 700 `--ink` |
| league pill | 15px, name 700 + count |
| important-row headline | 21px 500 / 1.3 |
| stream headline | 21px 600 / 1.3 (19px under 900px) |
| stream meta line | 13.5px `--dim` |
| "why" line | 14.5px `--dim`, label 700 `--ink` |
| section heading | 18px 800, with a 14px 400 `--dim` subtitle |
| side box title / item | 16px 800 / 15.5px 600 / 1.35, meta 12.5px |
| lead summary / why / meta | 19px 600 / 1.4, 16px (label 800), 14px |

## B4. Signal mark and logo

**Signal mark** (`SignalMark`, #462): three slanted strokes, 4px wide, heights 7 / 11 / 15 px,
3px apart, bottom-aligned, `skewX(-18deg)`, the same slant as the logo stroke. Empty strokes
are `--off`.

| level | filled strokes | colour |
|---|---|---|
| `low_feed` | 1 | `--acc` |
| `feed` | 2 | `--acc` |
| `high_feed` | 3 | `--acc` |
| `push` | 3 | `--hot` |

The count comes from `DECISION_RANK` / `strength` in `decisionConfig.js`, never from a second
mapping. It has `role="img"` and an accessible name built from the decision label (for example
"עוצמה: חשוב"). The mock's own words for the levels are illustration only. Labels follow A3.

**Logo lockup**: the wordmark "סיגנל" with a solid `--acc` stroke, 14×38 px, `skewX(-18deg)`,
6px before the word at its inline start.

## B5. Feed composition

Top to bottom, content width `max-width: 1180px`, centred, side gutter
`max(16px, env(safe-area-inset-*))`:

1. **Top bar** (B6), full width.
2. **Masthead**: wordmark, summary line (B6).
3. **League pills** (B6).
4. **Lead block** (B7), only with a push.
5. **Important row** (B8).
6. **Results strip** (B9), only with results.
7. **Band** (`--band`, padding 36px / 60px, 40px above): a two-column grid,
   `minmax(0, 1fr) 330px`, gap 32px, top-aligned. The start column is the stream (B10), the end
   column is the side column (B11).

Breakpoint in the mock: **900px**. Below it, every grid becomes one column, the side column
stops being sticky and follows the stream, pills and results scroll horizontally, and the
top bar keeps only its first and last items. Treat that as a starting point, not as approved
phone design (#475). #465 decides where the side column goes on a phone.

## B6. Top bar, masthead, league pills (#463)

- **Top bar**: `--top` ground, `--top-fg` text, padding-block 9px, items 22px apart. The
  navigation items (feed, results, preferences, calibration) sit at the inline start. The
  account item sits at the inline end, weight 400.
- **On `ui/next` (#463)**: `components/shell/ProductShell.jsx`, `ProductTopBar.jsx`,
  `ProductDock.jsx`, `MastheadSlot.jsx`, `shell.css`. The masthead owns the wordmark; a page
  renders its own content beneath it (summary line, pills) with `<MastheadSlot>`, which portals
  into the shell's `.signal-ui` scope and collapses when empty. `.sg-gutter` / `.sg-container`
  give the side gutter and the 1180px column. Under 768px the top bar carries a compact
  wordmark and the account, navigation moves to a bottom dock (56px targets), and the masthead
  block shows only slot content. That phone layout is a proposal for #475, not approved design.
- **Masthead**: centred column, gap 10px, padding 30px above and 20px below. The wordmark
  (B4), then the summary line: **"N סיפורים עברו את הסינון שלך · M חשובים"**. N is the number
  of visible stories, M the number of push + high_feed stories, both from the real feed.
- **League pills**: centred, wrapping, gap 10px, 30px below. Fully rounded, padding 7px 16px,
  ground `--t1`…`--t4` cycling in order. Each holds the league name (700) and its count. Pills
  are ordered by count, highest first. In the product they are the feed filters
  (`feedFilters.js`, current filter behaviour kept) and need a selected state with an
  accessible pressed or current indication. The mock does not draw one.

## B7. Lead block (#464)

Rendered **only when the feed contains a push**. The first push is the lead. Further pushes
open the important row, ahead of high_feed. With no push the page goes straight from the pills
to the important row. Nothing is promoted to fill the space.

- Ground `--slab`, text `--slab-fg`, padding 26px 34px (20px under 900px), column gap 18px, 40px
  below. Full content width, no radius.
- **Decoration**: three tall slanted strokes (74px wide, 26px apart; 40px under 900px) in
  `--slab-dim` at 16% opacity, bleeding off the inline-end edge, `aria-hidden`. They stay
  behind the text and never compete with the headline.
- **Label**: a small `--hot` chip with a pulsing dot and the push label "דורש תשומת לב"
  (12px 800).
- **Headline**: the story title, Karantina 700 (B3), linking to the original article. The
  headline is the block. Nothing else may dominate it.
- **One row beneath**, separated by a 3px `--slab-fg` rule with 14px above the text: a grid of
  `1.3fr 1.3fr auto`, gap 8px 36px. In order: the summary (subtitle), "למה אצלך:" + `reason_he`,
  and a meta column with sources · time and a rounded outline "לכתבה" link (1.5px
  `--slab-fg` border). Under 900px the row stacks.

## B8. Important row (#464)

Up to four stories, after the lead's extra pushes, then high_feed in ranked order. Four equal
columns, 44px below. Columns are separated by a 1px `--line` rule at the inline start, 20px
padding. The first column has neither.

Each item: a tag chip (`--acc` text on `--tint`, 13px 700) holding the signal mark and the
league; the headline linking to the article; a meta line "sources · time" in which a cluster
names its member sources ("2 מקורות: ONE · וואלה"). Under 900px the row becomes a list with
top rules. High_feed stories beyond four continue at the top of the stream.

## B9. Results strip (#466)

Between the important row and the band. A 1px `--line` rule above and below, padding-block 14px.

- **Header** at the inline start: "תוצאות" (15px 800) and a link to the results page, "ללוח
  המלא" (13px 700, `--acc`).
- **Games**: a horizontally scrolling row. Each game is at least 176px wide with a 1px
  inline-start rule: a small line "competition · time" (11.5px 700 `--dim`), then one row per
  team, name and score. The winner's row is `--ink` 800, the loser's `--dim`.
- **Data**: the session user's most recent finals (`/api/me/results`). The mock shows the ten
  latest finals before the snapshot time. The public demo needs results added to its snapshot
  without a request the bundle guard forbids. No results means no strip.
- Team names come from the taxonomy's Hebrew names. Some EuroCup teams have none and render in
  English (#466 lists them for the taxonomy workflow), wrapped per A2.

## B10. Stream rows (#464)

Heading above the panel: "עוד בפיד שלך" with the subtitle "מדורג לפי מה שחשוב לך".

The panel: `--card` ground, 1px `--line` border, rows divided by 1px `--line`. Each row,
padding 18px 26px (16px under 900px), gap 5px, is **three lines**:

1. **Meta**: signal mark · "source · time · league" (13.5px `--dim`). Feedback actions sit at
   the inline end in `--acc` 700 (the mock shows "עוד כאלה" and "פחות"; the product keeps its
   existing feedback set via `FeedbackControls`/`feedbackSaveModel`).
2. **Headline**, linking to the original article.
3. **Why**: for a cluster, a badge first ("N מקורות", `--ink` ground, `--card` text, 12px 800),
   then "למה אצלך:" + `reason_he`. The product also exposes the cluster's member sources.

Order is the ranked feed (high_feed beyond the important row, then feed). The page bound and
"show more" follow A5. The mock shows 14 rows and an "ועוד N סיפורים" line. Hover: `--tint`
ground and a 4px `--acc` edge on the inline start. The headline underline grows from the
inline start (2px `--acc`).

The mock hides the feedback actions under 900px. That is not approved: feedback must stay
reachable on a phone. #464: under 900px the actions move below the "why" line, aligned to the
inline end, with 32px tap targets; every placed story (lead, important row, stream, "in
brief") carries them. No large cards, no images (B13).

**As built in #464** (choices the mock left open):

- **Placement in the shell.** `/` is in `SIGNAL_SURFACE_PATHS`. Inside the shell the summary
  line, the pills and the freshness line render through `<MastheadSlot>`; with no slot (the
  lab, the demo until #469) `SignalFeedView` renders them at its top. The view opens its own
  `.signal-ui` scope; nested in a parent scope without `data-ground` it inherits the parent's
  ground.

- **Cluster members.** In the stream the badge is a disclosure button (`aria-expanded`) that
  lists each visible member once (source, time, report title), each linking to its report. In
  the lead and the important row each named source links to its own report.
- **Pill selected state.** `aria-pressed`; the pressed pill takes the `--slab`/`--slab-fg`
  pair and shows a slanted stroke, so colour is not the only cue. A "הכול" pill with the
  total comes first. Pills reuse `feedFilters` (`league:<name>` ids, same toggle semantics);
  the Orbit level and topic chips are not shown in the new feed.
- **Alert colour.** `--hot` is used only for non-text marks (push strokes, the dot in the lead
  label). The lead label itself is `--slab` text on a `--slab-fg` chip (6.7:1 white, 14.8:1
  dark), pending #468.
- **"In brief"** moved into the side column with #465 (B11).

## B11. Side column (#465)

330px wide, `position: sticky` (14px from the top) on desktop, so the side is never empty
next to a long stream. Two boxes, 22px apart. Each box has a `--card` ground, a 1px `--line`
border, a 3px `--acc` top rule, padding 18px 22px 8px, and a 16px 800 title. Items are divided
by 1px rules.

- **"אחרונים" (Latest)**: the newest visible non-low_feed stories by time (eight in the mock),
  each with the headline, then signal mark · time · source. A story under an hour old shows
  its time in `--hot` with a pulsing dot.
- **"בקצרה" (In brief)**: the low_feed stories, headline then time · source.

The column reads the same visible set as the stream. It never adds hidden stories and never
changes the stream's order. It must hold up with 3 and with 40 stories.

**As built in #465:**

- "Latest" is `latestStories` in `feedLayoutModel.js`: it runs on the filtered list (it follows
  the league pills), reads time from `orbitStoryTimestamp` (a cluster's backend update time),
  leaves out stories with no readable time, and keeps rank order on ties. A story may appear
  both in "Latest" and in the lead, important row or stream, as in the mock. "Latest" carries
  no feedback actions; each story has them where it is placed.
- Fresh marker (`isFreshStory`, under an hour): a pulsing `--hot` dot (a mark, not text), with
  the time in `--ink` 800. Small `--hot` text fails contrast (B2). The pulse stops under reduced
  motion.
- Desktop: sticky at `14px + env(safe-area-inset-top)`. The top bar scrolls with the page, so
  its height is not added. A column taller than the viewport is capped at the viewport height
  and scrolls inside, so its end is reachable at any scroll position, not only once the stream
  has ended.
- Phone (under 900px): one column, with the side column after the stream. The other option
  (after the important row) is shown in the #465 PR for Guy to choose.
- "In brief" keeps the bounded page and "show more" of A5.

## B12. Motion (#467)

What the mock has, all using `cubic-bezier(.2, .8, .2, 1)`:

- **Rise**: slanted strokes grow from their base (`scaleY` 0 → 1 under the skew). The lead
  decoration takes 0.7s, staggered 0.08s. Signal marks take 0.5s, staggered 0.06s.
- **Up**: the lead headline enters with opacity 0 → 1 and an 18px upward move over 0.6s.
- **Pulse**: an expanding ring on the fresh-story dot and the push label, 1.8s, looping.
- **Hover**: row ground 0.15s, headline underline 0.25s.

Guy wants more. #467 proposes the set, for example new stories arriving in the stream and in
Latest, results updating, the stream re-flowing on a filter change, feedback acknowledging
itself, pill counts changing. Guy approves it and #467 records it here. Principles that stand
now:

- Motion carries meaning: new, changed, acknowledged. Nothing loops for decoration except the
  fresh-story pulse.
- Bounded as A5: capped stagger, no animated removal, no index-proportional delay.
- No layout shift, no jank on a mid-range phone. Animate `transform` and `opacity`.
- Everything is off under `prefers-reduced-motion` (A6). The page stays fully legible with no
  motion at all.

## B13. Other consumer screens and images

- **Grounds** (#468): a control in the account area or the shell. Every consumer screen must be
  legible in all three grounds. Whether the choice persists per user or per device is decided
  in #468.
- **Preferences, interests, calibration** (#470): the same tokens and type. Calibration headline
  cards read like stream rows, so the user rates what they will see. No behaviour change.
- **Results page** (#471): shares the strip's game row where possible.
- **Account, auth, welcome, 404** (#472) and the **public demo** (#469): the new shell and
  feed. The demo stays feed-only and read-only.
- **Images** (#474): open owner decision, ingestion work before design work. Every layout here
  works without an image and must keep working when a story has none.

## B14. Do not

Guidance from what Guy rejected while choosing:

- No print or poster styling.
- No large empty areas, and no empty side next to a long column.
- No oversized story cards.
- No lead block dominated by anything other than the headline.
- No loud full-bleed yellow.
- No pure-black "night" layout.
- No hero without a push, and no importance invented to fill a slot.
- No Orbit carry-over (B1).

---

# Appendix C — Orbit on main until #473

Orbit (shipped 2026-07-31) is still what main and the demo render. On `ui/next` the Feed page
uses the new feed (#464); the demo still uses `OrbitFeedView` until #469. These facts matter only for
fixing main before the new look replaces it. #473 deletes this appendix together with the code.
Screenshots of Orbit as shipped are in
[`frontend-concepts/orbit/`](./frontend-concepts/orbit/README.md).

- **Code**: `components/feed/orbit/` (`OrbitFeedView`, `OrbitStoryField`, `OrbitLoadingState`,
  `orbit.css`, and the models listed in A9) plus `components/shell/` (`Atmosphere`, `Masthead`,
  `MobileNav`, `ProductNav`, `OpsNav`, `OpsGrid`, `SignalMark`). On main, `EditionEmptyState`
  is the live zero-items state; on `ui/next` it was replaced by `signal/SignalFeedStates.jsx`
  (#464). On `ui/next`, `Masthead` and `MobileNav` are Ops-only (#463), and `Atmosphere` is
  used only by the demo.
- **Presentation contract**: `DECISION_CONFIG[...].orbit` (`queueScale`, `queueDensity`,
  `queueRail`, `queueMuted`) is locked by `decisionConfig.test.js`. The push-only signal rail
  is asserted in markup and in paint.
- **Type scoping**: `--font-display` stays Heebo in `:root`. Ops, auth, 404 and `PageHeader`
  depend on it. The Frank Ruhl Libre serif lives only in `--orbit-serif` on
  `.orbit-feed-view`, used by four rules (`.orbit-feed-heading h1`, `.orbit-core h2`,
  `.orbit-cluster__core h3`, `.orbit-feed-empty h2`). There is no global `h1`–`h3` rule.
- **Cascade warning**: `orbit.css` declares some base rules after their modifiers. Three rules
  repeat their class or restate themselves inside a media query on purpose and are commented
  as load-bearing: `.orbit-queue-story.orbit-queue-story--<tone> h3`, `.orbit-field--solo`
  height in `@media (max-width: 1199px)`, `.orbit-field--solo .orbit-core` in
  `@media (max-width: 767px)`. Do not "simplify" them.
- **Accepted at 320 px**: the signal chip may need a small scroll (the primary action is
  enforced clear of the dock by `assertDockOcclusion`); the field caption shows only its first
  half; auth typography is not reachable in the hermetic harness (`/no-such-route` exercises
  the same utility); `.orbit-feed-empty h2` is not browser-verified.
