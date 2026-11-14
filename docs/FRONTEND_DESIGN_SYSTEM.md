# Signal Sports — Frontend Design System

Last updated: 2026-11-14 (#491 navigation, #473 cleanup; first written 2026-11-13, #461).
This file has two parts:

- **Part A: engineering and accessibility rules.** These hold for any consumer UI, the one on
  main today and the new one. The affected rules were rechecked against `frontend/` on
  `ui/next` on 2026-11-14.
- **Part B: visual language.** On 2026-11-13 Guy approved a new direction from a coded mock
  built on his real feed. Part B describes that direction in full. **Orbit's colours, type,
  shapes and composition are superseded and are not a starting point** for any new work.
**What is implemented on `ui/next`.** All consumer routes, utility screens and the public
demo use Part B's Signal UI. The feed lives in `components/feed/signal/`; the demo uses the
same `SignalFeedView` read-only. #473 removes the unused Orbit views, CSS and serif font,
and moves the shared story, queue and focus models to neutral names under `components/feed/`.
Ops retains its existing shell, base tokens, Heebo and signal-bars logo. Milestone 15,
"A face of its own — new consumer UI" (#461–#475), remains on the integration branch
`ui/next`: merging it to main and deploying the demo need Guy's explicit approval (#475).
This describes the branch's code, not a deployment claim.

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
  `src/index.css`. Consumer tokens are scoped to `.signal-ui` on the consumer shell and
  page body. `productShellModel.pageSurface` always selects Signal UI; every consumer route
  has migrated, so no migration allowlist remains. The unused compatibility branches in
  `ProductShell.jsx` / `shell.css` remain for the separate navigation work (#491).
  Never redefine a shared token to style one surface.
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
- **Reader explanations.** `DeskVoice` / `deskVoiceModel.js`: on every consumer surface, for
  every role (admins and local QA included), the "why it is with you" line is `reason_he` (one
  Hebrew sentence) or nothing; never a score or the engine trace (#497, 2026-11-14). The engine
  trace lives in the Debug console (`/debug`) only.
- **Read-only mode.** The demo renders the feed with `readOnly`: no feedback controls, no engine
  trace, no write path. `npm run check:demo-bundle` enforces this on the built bundle (A7).

## A4. Backend authority vs local hydration

Cluster values are **backend-authoritative**. `ClusterCard` (`docs/CLUSTERING.md` §9) guarantees
that `source_count`, `members`, `displayed_article_id` and `sort_at` are VISIBLE-only and
test-locked server-side, and `api/normalizers.js` maps each one directly.

`prepareFeedItems(items, { isBackendMode, localScoredArticles })` (in
`components/feed/storyModel.js`) owns the split:

- **backend**: items pass through untouched, same array, same object identities. Debug renders
  the same payload, so the two views cannot disagree.
- **local/mock**: clusters are hydrated from the scored catalogue, because local clusters
  carry no `members`.

The render path reads authoritative values too:

- `sourceCount(item, reports)` prefers a finite `item.sourceCount` and deduplicates reports
  only as a local fallback. The cluster badge ("N מקורות") reads it.
- `storyTimestamp(item, reports)` prefers `item.lastUpdatedAt`, deriving from reports only
  as a local/legacy fallback. Story times and the "Latest" ordering read it.
- `latestReportTimestamp(reports)` stays separate on purpose: rendering *reads*
  `lastUpdatedAt` while local hydration *calculates* it. Merging them would make hydration echo
  whatever stale value a mock item already carried.

Adversarial tests build clusters where the backend value and the client derivation
deliberately disagree, so any fallback for a backend item fails. #473 moves these models
and their tests without changing their behaviour or assertions.

## A5. Bounded work

Anything proportional to feed size (animation, layout, rendered nodes) is capped.

- **The ranked list renders a bounded page of 40** with a "show more" control
  (`QUEUE_PAGE_SIZE` in `queueMotion.js`). The heading shows `visible/total` while more
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
- **Decisions are pure functions**: `signal/feedLayoutModel.js` supplies the next-page focus
  index; `focusModel.js` preserves the tested field focus intents and scroll policy for reuse.
  The current feed uses button-based cluster disclosures, keeping focus on the same badge when it
  opens or closes.
- **The owning view focuses its element.** `SignalFeedView` holds the stream and brief refs
  and focuses the first newly revealed headline after "show more". Focusing across component
  boundaries or querying classes for focus is not deterministic.
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
`feedLoadModel`, `deskVoiceModel`, the shared story/queue/focus models). A few `.test.jsx`
files render components with `react-test-renderer` in node (for example
`signal/SignalFeedView.test.jsx`).

**Hermetic browser harness.** `npm run capture:ui` (`scripts/capture-ui-production.mjs`)
drives the real app through Chrome over CDP and asserts what the browser *paints*: distinct
decision signatures, stale rows cleared within a 100 ms budget, the 40-row page bound, focus
transitions under both motion modes, no control occluded by a fixed element (via
`elementFromPoint`), and computed font families per route. It reserves a free ephemeral port,
captures Vite output, refuses a 200 from a dead child, and proves in-page that it is the
local-data instance (local mode issues no `/api/` request). `capture-ui-production.test.mjs`
locks the time it "passed" against another app on a fixed port. Every asserted element must
exist, and an audit with nothing to measure fails. Since #464 it asserts the new feed body:
placement by level (lead only with a push, important row, stream in rank order, "in brief"),
the summary counts, signal-mark fill and colour, the bounded stream page, league-pill filter
latency, pressed state and focus, cluster member links, feedback actions present and
unclipped at 320–390, typography (Assistant, Karantina on the lead only, no serif leak) and
occlusion by fixed chrome (the phone dock until #491, the slim header bar since). Since #465 it
also asserts the side column: "Latest" newest first, never low_feed
or hidden, every story in it placed elsewhere; "in brief" only inside the column; sticky 14px
below the slim header bar halfway down the stream and inside the viewport on desktop; after the stream and
not sticky on a phone, with every visible story painted. Since #467, in both motion passes:
the stream's entrance stagger is capped, the load causes no layout shift, only the
fresh-story pulse is still running once the page settles, and under reduced motion nothing
runs at all. `loadApp` waits for finite animations to finish before it measures. The local corpus puts exactly 40 stories in the stream and its clusters in
the lead and important row, so the multi-page "show more" path and the stream cluster
disclosure are locked by `SignalFeedView.test.jsx` instead, and the harness output says so.
Since #501 it opens the "N מקורות" disclosure on every surface that has one (the important row
must have one in the local corpus): every story that names several sources carries the badge and
no competing name links, the opened list is painted inside its story, keeps focus on the badge,
lists every report with its own headline and a new-tab link, the displayed report first and
marked once, the distinct sources match the badge, and it closes again; at 1440 and on phones.
Since #491 it asserts the consumer header (B6) at 1440/390/375/320 in both motion passes: the
masthead in page flow with all three tabs reachable and unclipped, the slim bar hidden and inert
at the top, fixed and shown once the masthead tabs have left (icon over a visible label on a
phone, every tab and the account at least 44px), the hysteresis band in both directions, zero
layout shift while it collapses and expands, a soft fade (300–500 ms) under normal motion and
no transition under reduced motion, the Tab order (skip link, logo, tabs, account) and the
account menu's keyboard flow (Enter opens with focus inside, arrows move, Escape returns to the
avatar).
Since the milestone-15 accessibility pass (2026-11-14) it also asserts a floor under every header
size (B6) and that `--sg-bar-h` and the anchor `scroll-padding` match the bar's real height; the
results strip's thin scrollbar with its `--sg-off` thumb, spaced off the scores (B9), and the
hit-tested target of its "ללוח המלא" link (at least 24px on desktop, 44px on a phone); and the side
column's scrollbar transparent at rest, with a stable gutter and its bottom-edge fade (B11).
The harness keeps every existing browser assertion through the #473 rename to `capture:ui`.

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

The feed uses the existing pure models; #473 moves the shared models and their tests to neutral names:

```
components/feed/
  decisionConfig.js     levels, labels, rank (drives the signal mark)
  feedFilters.js        level + topic filtering (drives the league pills, #463)
  storyLabels.js        Hebrew kickers, condensed reasoning
  feedLoadModel.js      loading / empty / error states
  deskVoiceModel.js     reader sentence (or nothing)
  feedbackSaveModel.js  feedback action state
  storyModel.js        prepareFeedItems + authority resolvers (A4)
  queueMotion.js       page size + stagger cap (A5)
  focusModel.js        preserved field focus intents and scroll policy (A6)
  signal/feedLayoutModel.js  lead / important / stream / brief, league pills, summary (#464)
  signal/feedMotionModel.js  entrance delays (capped stagger) and refresh arrivals (#467)
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
| 2 | **Structure inspired by Axios**: navy header with navigation and a centred logo (since #491 one navy header that collapses on scroll, B6), a summary line, league pills with counts, a row of up to four important stories | #463, #464, #491 |
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
or treat them as a fallback. #473 removes the unused consumer implementation; the
[historical screenshots](frontend-concepts/orbit/README.md) are not an implementation reference.

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
| `--top` | header (masthead and slim bar) | `#142a66` | `#142a66` | `#0f1422` |
| `--top-fg` | header text, active tab | `#ffffff` | `#ffffff` | `#eef1f7` |
| `--top-dim` | inactive tabs, date line (#491) | `#b9c4e6` | `#b9c4e6` | `#a3adc0` |
| `--top-logo-a` / `-b` | logo bars on the header (blue / green, the app icon's own) | `#6a95d8` `#1fc77c` | same | same |
| `--logo-a` / `-b` | logo bars on the page ground (#491) | `#3a6fc9` `#11995f` | `#3a6fc9` `#0e8753` | `#6a95d8` `#1fc77c` |
| `--top-hover`, `--top-shadow` | avatar ground, slim-bar shadow | translucent white; navy shadow | same | black shadow |
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
(white, dark) and 4.58 (soft). The implementation keeps `--hot` on non-text marks: the lead
label uses the `--slab`/`--slab-fg` pair, and the fresh-time text uses `--ink` at weight 800.

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
| logo (masthead / slim bar) | 46px 800 / 30px, letter-spacing −0.02em (34px / 23px under 768px) (B6, 2026-11-14) |
| tabs | 19px 800 in the masthead, 18px in the slim bar (17px on a phone; 13px label under a 24px icon in the phone's slim bar) (B6, 2026-11-14) |
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

**Logo lockup** (#491, Guy 2026-11-14; replaces the slanted `--acc` stroke): the app icon's
three rounded bars (short blue, tall green, medium blue, as in `public/favicon.svg`) at the
inline start of the word "סיגנל" (800). `SignalWordmark` draws it everywhere (header, auth, 404,
welcome, demo, lab); sized in em (bars 0.78em tall, 0.15em wide, 0.09em apart, 0.28em before
the word), the bars keep the icon's left-to-right order in RTL and are `aria-hidden` (the word
is the text). On the navy header (`.sg-on-top`) the bars take the icon's own colours
(`--top-logo-*`: 4.45 and 6.13 on `#142a66`); on a white or soft ground they take the darker
`--logo-*` pair, because the icon green is 2.2:1 on white. The logo is non-text, so 3:1 applies;
`contrast.test.js` checks every pair on bg, card and band.

## B5. Feed composition

Top to bottom, content width `max-width: 1180px`, centred, side gutter
`max(16px, env(safe-area-inset-*))`:

1. **Header** (B6), full width, navy: masthead, then a slim bar on scroll.
2. **Summary line** (B6), in the page slot directly under the header.
3. **League pills** (B6).
4. **Lead block** (B7), only with a push.
5. **Important row** (B8).
6. **Results strip** (B9), only with results.
7. **Band** (`--band`, padding 36px / 60px, 40px above): a two-column grid,
   `minmax(0, 1fr) 330px`, gap 32px, top-aligned. The start column is the stream (B10), the end
   column is the side column (B11).

Breakpoint in the mock: **900px**. Below it, every grid becomes one column, the side column
stops being sticky and follows the stream, and pills and results scroll horizontally (the
header follows its own 768px breakpoint, B6). Treat that as a starting point, not as approved
phone design (#475). #465 decides where the side column goes on a phone.

## B6. Header, summary line, filter area (#463, navigation #491, filters #483)

Decided by Guy on 2026-11-14 after five rounds on a navigation mock (#491). Rejected: a grey
header ground, a logo-colour stripe, a segmented pill nav, a side rail, a results ticker.

- **One navy header, sticky in effect, navy in both states** (`--sg-top` in every ground).
  - **Sizes, enlarged on 2026-11-14** (Guy: "the menu is too small … on scroll I want it
    thicker; normally I want the text more present"). The harness (`capture:ui`) asserts a floor
    under each size, the bar height against `--sg-bar-h` and the anchor `scroll-padding`.
  - **Expanded (top of page)**: in normal page flow. Large centred logo (46px, 34px under
    768px), the date line under it ("שבת, 14 בנובמבר 2026", Asia/Jerusalem, `--top-dim` 13.5px;
    hidden under 768px), then the tabs centred with words (19px 800, 22px inline padding, 8px
    apart, a 60px row; 17px 800 on a phone, 12px padding, a 52px row). Active tab `--top-fg`
    with a 4px underline rounded at the top; inactive tabs `--top-dim`. The account avatar
    (36px face, 44px target) sits at the inline end of the top row.
  - **Collapsed (on scroll)**: a separate bar, `position: fixed`, 72px (64px on a phone), with
    a soft shadow: a 30px logo at the inline start, tabs centred (18px 800, 20px padding, 4px
    underline), account at the inline end. On a phone each tab is a 24px icon over a 13px 800
    label (an iOS-style compact tab bar), every item at least 44px and all three fitting at
    320px; under 360px the bar's logo keeps its bars only (26px). `--sg-bar-h` (72px / 64px)
    and `html { scroll-padding-block-start }` (bar + 8px) follow the bar.
  - **Motion (softer than the mock)**: the masthead scrolls away by itself; the bar fades in
    with a 12px slide (420ms in, 360ms out, `--sg-ease`) and its logo settles from scale 1.18,
    as if it travelled up from the masthead. The bar is out of flow, so nothing moves (layout
    shift 0, harness-checked). Under reduced motion it swaps instantly.
  - **Trigger**: an IntersectionObserver on the masthead tabs with its root line at the bar's
    bottom edge (no scroll handler). Hysteresis (`productShellModel.nextBarShown`, node-tested):
    the bar shows once the tabs have fully left (ratio 0, above) and hides only once they are
    fully back (ratio 1), so it never flickers at the threshold. A hidden bar is `inert`. Keyboard
    focus or an open menu inside the bar keeps it shown, so focus is never dropped.
- **No bottom dock.** The console entry moved into the account menu.
- **Account menu** (avatar: the email's first letter, a person icon in local mode): "החשבון
  שלי" (email + link), ground (לבן / רך / כהה), an admin-only section "ניהול" (console entry, QA
  view-as profiles, data mode) shown only to visitors who may use them (#54), sign out. The data
  mode dot and the loading spinner are gone from the chrome; while the feed loads a thin
  progress line runs along the header's bottom edge.
- **Icons** (`shell/navIcons.jsx`, consumer header only; the shared `navConfig` icons stay for
  the Ops rail): feed `Newspaper`, results a custom scoreboard on Lucide's 24px grid and 2px
  round stroke (panel, two score blocks, a colon), preferences `SlidersHorizontal`, calibration
  `Target`. Two other scoreboard candidates are in `lab.html?page=nav` for Guy to choose.
- **Code**: `ProductShell.jsx` (shell, page slot), `ProductHeader.jsx` (masthead + bar),
  `AccountMenu.jsx`, `useCollapsedBar.js`, `navIcons.jsx`, `productShellModel.js` (order, icon
  keys, hysteresis, date, menu sections), `shell.css`. The item list stays data-driven from
  `navConfig`, so merging preferences and calibration into one destination needs no header work.
- **Page slot**: a page renders content under the header (summary line, pills) with
  `<MastheadSlot>`, which portals into a `.signal-ui` band in the page flow directly beneath the
  header, never inside the slim bar, and collapses when empty. `.sg-gutter` / `.sg-container`
  give the side gutter and the 1180px column.
- **Public demo**: the expanded navy header with the logo only (no tabs, no account), then its
  banner.
- **Summary line**, 22px under the header: **"N סיפורים עברו את הסינון שלך · M חשובים"**. N is the number
  of visible stories, M the number of push + high_feed stories, both from the real feed.
- **Filter area — Guy's choice, 2026-11-14 (#483).** Variant C replaces A from #496:
  one "סינון" button with an active-filter count, removable chips beside it (importance,
  each league, each source), "נקה סינון" when active, and the existing "מוצגים X מתוך N
  סיפורים" line. The summary above still counts the whole visible feed. Importance and
  league controls appear only after opening. Filters apply live and are never persisted.
  - **Desktop (≥900px):** a full-width horizontal panel directly below the filter row,
    inside the page column and in normal flow. RTL columns: "חשיבות", "ליגות", "מקורות";
    options wrap within their columns. Footer: "נקה הכול" and "סגור". This is a disclosure
    (`aria-expanded`, `aria-controls`), with no modal semantics. A short height/opacity reveal
    uses the existing ease; reduced motion opens immediately. Button, Escape and outside
    click close it. Opening focuses its close control; closing returns to the filter button.
  - **Phone (<900px):** a native modal bottom sheet with background inertness, a focus trap,
    Escape, a close control, "הצג N סיפורים" and safe-area padding. The footer stays reachable
    while the options scroll. Active chips scroll within their row, never the page.
  - **Facets:** הכול / רגיל ומעלה / חשוב ומעלה (push included at every threshold), leagues
    and source display names already used by the feed. Importance AND league AND source;
    several leagues or sources mean any selected value within that facet. **A cluster matches
    any of its visible member sources**, counted once per source. Authoritative members win
    over legacy source arrays. Each option counts under the other active facets; selected
    zero-count options stay removable. Hidden stories never pass or count. League colours
    remain `--sg-t1`…`--sg-t4`, selected `--sg-slab` / `--sg-slab-fg`, with `aria-pressed`.
  - **Empty result:** descriptive text and "הצג את כל הפיד"; the persistently mounted filter
    status announces once per change. Removing a chip or clearing the row returns focus to
    the filter button. The same component works read-only in the public demo.
  - **Lab:** `lab.html?page=filters` renders the shipped C component; A and B were removed.

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
  `--slab-fg` border). Under 900px the row stacks. A multi-source lead opens its reports with
  the inverted "N מקורות" badge, below the row across the slab (B10).

## B8. Important row (#464)

Up to four stories, after the lead's extra pushes, then high_feed in ranked order. Four equal
columns, 44px below. Columns are separated by a 1px `--line` rule at the inline start, 20px
padding. The first column has neither.

Each item: a tag chip (`--acc` text on `--tint`, 13px 700) holding the signal mark and the
league; the headline linking to the article; a meta line "sources · time" in which a cluster
shows the "N מקורות" badge and then names its member sources as plain text ("[2 מקורות ⌄]
ONE · וואלה · לפני שעה"). The badge opens the story's reports inside the column, below the meta
line (B10, "Opening a multi-source story"). Under 900px the row becomes a list with
top rules. High_feed stories beyond four continue at the top of the stream.

## B9. Results strip (#466)

Between the important row and the band. A 1px `--line` rule above and below, padding-block 14px.

- **Header** at the inline start: "תוצאות" (15px 800) and a link to the results page, "ללוח
  המלא" (13px 700, `--acc`), whose hit area extends above and below the line (26px on desktop,
  46px on a phone) without moving the layout.
- **Games**: a horizontally scrolling row with a thin, quiet scrollbar (2026-11-14, replacing the
  ink-dark one that touched the scores): `scrollbar-width: thin`, thumb `--sg-off` (`--sg-dim`
  while hovered or focused), 6px below the scores. Wheel, trackpad, touch and the arrow keys
  (the row is focusable) scroll it. Each game is at least 176px wide with a 1px
  inline-start rule: a small line "competition · time" (11.5px 700 `--dim`), then one row per
  team, name and score. The winner's row is `--ink` 800, the loser's `--dim`.
- **Data**: the session user's most recent finals (`/api/me/results`). The mock shows the ten
  latest finals before the snapshot time. The public demo reads optional `results.json` from
  its static snapshot, with no API request. No results means no strip.
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
   then "למה אצלך:" + `reason_he`. The badge opens the story's reports (below, "Opening a
   multi-source story").

Order is the ranked feed (high_feed beyond the important row, then feed). The page bound and
"show more" follow A5. The mock shows 14 rows and an "ועוד N סיפורים" line. Hover: `--tint`
ground and a 4px `--acc` edge on the inline start. The headline underline grows from the
inline start (2px `--acc`).

The mock hides the feedback actions under 900px. That is not approved: feedback must stay
reachable on a phone. #464: under 900px the actions move below the "why" line, aligned to the
inline end, with 32px tap targets; every placed story (lead, important row, stream, "in
brief") carries them. No large cards, no images (B13).

**As built in #464** (choices the mock left open):

- **Placement in the shell.** All consumer page bodies use Signal UI. Inside the shell the
  summary line, the pills and the freshness line render through `<MastheadSlot>`; with no slot
  (the lab and the public demo) `SignalFeedView` renders them at its top. The view opens its own
  `.signal-ui` scope; nested in a parent scope without `data-ground` it inherits the parent's
  ground.

- **Opening a multi-source story (#501).** One disclosure on every surface that places a
  cluster: the lead, the important row, the stream and "in brief". The control is the
  "N מקורות" badge (a button with a chevron, `aria-expanded`/`aria-controls`; on the lead's slab
  it inverts to `--slab-fg` ground, `--slab` text; on a phone its hit area reaches 32px). In the
  lead, the important row and "in brief" the badge leads the meta line and the source names
  follow as plain text, so they still read as a list but are not a second set of links; in the
  stream it opens the why line, as in the mock. "אחרונים" has no badge: every story in it is
  also placed in the lead, important row, stream or "in brief", where it opens.
  - Opening keeps focus on the badge and renders the list right below the story's meta (in the
    important row inside its own column, which grows; the other columns keep their top
    alignment; in the lead spanning the slab beneath its row, in columns on a wide screen, in
    slab colours). Not a floating panel, so there is nothing to dismiss with Escape; the badge
    closes it.
  - The list holds **every visible report** (`clusterReportList` in `signalStoryModel.js`), not
    one per source, since two reports from one site can differ. When there are more reports
    than sources a caption says so ("4 דיווחים מ־3 מקורות"). Each entry is one link to the
    original (new tab, `useArticleOpened`): source (700 `--ink`) · relative time, then that
    source's own headline (15px 600 `--ink`, Hebrew follows the page, a headline with no Hebrew
    takes `dir="auto"`), then "לדיווח המקורי" (`--acc` 700) with an arrow.
  - Order: the displayed report (the one the headline opens, the backend's
    `displayed_article_id`, else the first visible report as `storyLink` does) first, marked
    "הדיווח המוצג" (`--acc` on `--tint`); then the others oldest first, the story's order of
    arrival; an undated report last.
  - Entries enter on the capped stagger (`enterStyle`), the list drops open (`sg-drop`); both off
    under reduced motion. Closing is immediate.
  - Data: backend members and the public demo snapshot (`MEMBER_FIELDS`) carry source, title,
    url and time for every visible member; local mode hydrates them from the scored catalogue.
    A cluster whose payload holds fewer than two reports shows "N מקורות: names" as text with
    no badge, rather than a list that cannot be filled.
- **Pill selected state.** `aria-pressed`; the pressed pill takes the `--slab`/`--slab-fg`
  pair and shows a slanted stroke, so colour is not the only cue. A "הכול" pill with the
  total comes first. Pills reuse `feedFilters` (`league:<name>` ids, same toggle semantics);
  level and topic filters remain supported by the model; the feed presents league pills.
- **Alert colour.** `--hot` is used only for non-text marks (push strokes, the dot in the lead
  label). The lead label itself is `--slab` text on a `--slab-fg` chip (6.7:1 white, 14.8:1
  dark).
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
  the league pills), reads time from `storyTimestamp` (a cluster's backend update time),
  leaves out stories with no readable time, and keeps rank order on ties. A story may appear
  both in "Latest" and in the lead, important row or stream, as in the mock. "Latest" carries
  no feedback actions; each story has them where it is placed.
- Fresh marker (`isFreshStory`, under an hour): a pulsing `--hot` dot (a mark, not text), with
  the time in `--ink` 800. Small `--hot` text fails contrast (B2). The pulse stops under reduced
  motion.
- Desktop: sticky 14px below the slim header bar (`var(--sg-bar-h) + 14px +
  env(safe-area-inset-top)`, #491; `--sg-bar-h` is 0 where there is no bar, as in the demo). A column taller than the viewport is capped at the viewport height
  and scrolls inside, so its end is reachable at any scroll position, not only once the stream
  has ended. Since 2026-11-14 that inner scroll is unobtrusive: a thin, stable gutter (nothing
  reflows) whose thumb is transparent until the pointer or keyboard focus is in the column, a
  40px fade to `--band` pinned to the column's bottom edge while there is more (scrolled to the
  end it sits over empty band, below the last item), and `scroll-padding` so focus never lands
  under the fade.
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

**Proposed in #467, awaiting Guy's approval.** CSS in `signal-feed.css`; delays and refresh
arrivals in `signal/feedMotionModel.js` (node-tested). Run it in `lab.html?page=motion`.

| Effect | Trigger | Motion |
|---|---|---|
| Load choreography | the feed mounts | summary, pills, lead, important row, results cells, stream rows, side column enter top to bottom (opacity + 10px rise, 360ms). Bases 0–280ms, then 40ms steps capped at 6, so the page settles in under 1s for any length |
| Lead entrance | a lead mounts or changes | slab fades in (300ms), strokes rise (700ms, 80ms apart), label pops, headline comes up (600ms), the row beneath follows |
| Signal marks | their row enters | strokes rise after the row starts (0.5s, 60ms apart) |
| Re-flow | a league pill is pressed | the pill eases to the slab ground (200ms), its stroke rises (280ms), it gives under the finger (scale .96). Rows that stop matching unmount at once; rows that newly match enter with the capped stagger |
| Count tick | a number changes (summary, pill counts, a score) | the new number rises in (280ms). Keyed by value, so only a changed number moves |
| New after a refresh | stories absent from the previous list | a "חדש" mark that pops in, a tint glow on the row that settles (1.6s, paint only, a few rows), one polite screen-reader line. A mostly new list (re-score, other profile) marks nothing |
| Feedback acknowledged | a save starts and is confirmed | the status word and check pop in; on a stream row the accent edge flashes once |
| Cluster disclosure | the badge is pressed | chevron turns (200ms), member list drops open (200ms), items follow (capped). Closing is immediate |
| Hover and focus | pointer over a row, or keyboard focus inside it | tint ground, accent edge grows in from the middle (200ms), headline underline (250ms) |
| Fresh pulse | a story under an hour old in Latest; the lead label | unchanged, the only loop |

Entrances use `animation-fill-mode: backwards`, never `both`: a filled transform makes each row
a stacking context and the feedback menu would paint under the next row. Under reduced motion
every animation and transition in the feed and its head is `none`; the "חדש" word still marks
new stories.

## B13. Other consumer screens and images

- **Grounds** (#468): `AccountMenu` in the consumer header selects white, soft or dark.
  `GroundProvider` persists the choice per device in `localStorage` (`signal.ground`), falls
  back to white if storage is unavailable, and applies no ground to Ops. The demo stays white.
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
