# Signal Sports — Frontend Design System ("Court Vision")

Last updated: 2026-07-04 — the frontend redesign (PRs 1–6, branch
`feature/frontend-redesign-foundation`) that turned the Base44-generated QA
dashboard into a premium, Hebrew-first, RTL-first dark product, plus
**PR A ("The Edition", same branch, commit `f23d023`)** which rebuilt the Feed
from a card list into a composed personal edition under the approved
"המערכת / The Desk" design concept (codename only — the product name is
unchanged).

This document is the reference for the design system: the tokens, the component
inventory, the product-vs-console split, and the hard RTL rules. Read it before
adding any new UI.

---

## 1. Design language

**"The more a story matters to *you*, the more light it emits."** Relevance is
the brand. On a calm near-black navy canvas, relevance is encoded as **light and
shape**, never as loud card borders or badge rows.

Since PR A the Feed is **"The Edition" (המהדורה)**: the ranked visible items are
partitioned per reader into five visual species — the lead story, framed as
**"הסיפור המרכזי"** (serif display headline directly on the canvas,
signal-tinted aura + court-line arc, breathing gold for push), **מבזק**
bulletin strips (remaining push — the general push-level label is **"לא
לפספס"**), the asymmetric **"במוקד"** tier (high_feed), typographic **"עוד
מהפיד"** rows (feed), and the collapsed **"קריאה נוספת"** digest (low_feed).
These are display copy only (PR A.2) — the underlying decision ids (`push`,
`high_feed`, `feed`, `low_feed`, `hidden`) are unchanged. Decision badges and
the old signal-rail edge bar are gone from the product feed — position, type
scale, and light do that work (`DecisionBadge` survives as a console
affordance in Debug/LLM-QA/Preferences, using its own label set). Two
readers' editions differ in *shape*, not just ordering.

Two visual areas share one token system:

- **Product** (Feed, Preferences, Calibration, Results) — editorial, green
  accents, serif display headlines. The flagship experience.
- **Console** (Sources, Debug, LLM QA) — a polished developer instrument panel:
  denser, steel-blue actions, monospace values. Reached via the "קונסולה" nav
  group; ops routes render `AppShell area="ops"` which adds the `OpsNav` strip.

The split is deliberate: the consumer feed must never feel like a dashboard, and
the dev tools must feel like a first-class console rather than the whole app.

---

## 2. Stack

- **React 18 + Vite 6**, JavaScript/JSX (checkJs via `jsconfig.json` — no TS).
- **Tailwind 3.4 + shadcn/ui + Radix** primitives (`src/components/ui/`). The
  redesign is the *first real adoption* of these primitives — earlier code was
  hand-rolled Tailwind.
- **Fonts** (self-hosted, `@fontsource`): **Frank Ruhl Libre** (Hebrew serif
  display) + **Heebo** (UI/body). System mono for numerics.
- **Motion**: `framer-motion` (first adopted in PR A, Feed only): staggered
  edition entrance, blur headline reveal, `AnimatePresence`/`layout` filter
  recomposition. Variants live in `components/feed/motionPresets.js`, are
  **y-axis-only** (sidesteps RTL mirroring), and every factory takes the result
  of `useReducedMotion()`. CSS keyframes (`fade-up`, `shimmer`, `pulse-soft`,
  `breathe`) remain for micro/looping effects; prefer CSS unless a layout
  animation genuinely requires framer.

---

## 3. Tokens

All tokens live in **`src/index.css`** as HSL custom properties and are exposed
to Tailwind in **`tailwind.config.js`**. **Feature components must use semantic
tokens — never raw Tailwind palette colours** (`gray-*`, `blue-*`, `amber-*`…).

### Surfaces (elevation ladder)
| Token | Use |
|---|---|
| `--background` / `bg-background` | app canvas (near-black navy) |
| `surface-1` | cards, panels |
| `surface-2` | elevated / hover / inset cells |
| `surface-3` | chips, inputs, strongest inset |
| `--border` | hairline (subtle, replaces visible gray borders) |

Recipes (in `index.css` `@layer components`): `.surface-glass` (sticky header +
mobile tab bar only), `.elevation-1` (background-step + hairline + shadow),
`.glow-push` (gold inner hairline + soft glow — **push only, never ad-hoc**).

### Text
`text-foreground` (primary) · `text-text-secondary` · `text-text-dim` (muted).

### Signal system (decision levels = the brand)
| Token | Meaning | Where |
|---|---|---|
| `signal-push` (gold) | push / attention | **push cards + critical alerts + console warnings only** |
| `signal-high` (electric green) | high_feed | also: primary product actions, active nav, healthy status |
| `signal-feed` (steel blue) | feed | also: the console action colour |
| `signal-low` (dim gray) | low_feed | — |
| `signal-hidden` / `--destructive` (red) | hidden | also: errors, destructive actions |
| `signal-ai` (cyan) | AI/intelligence moments | relevance-reason spark, guardrail badge, disagreement, pilot |

**Colour discipline:** gold is scarce (push only) — this is why the feed reads as
gold at the top (push stories sort first) then transitions to green/blue as
relevance drops. Red is errors/hidden only.

### Type scale
Display serif (Frank Ruhl Libre 500/700/**800** — 800 added in PR A) carries the
edition: lead headline 2rem→3rem at weight 800, bulletin/editorial headlines
~1.35–1.75rem bold, serif section headings ("במוקד", "עוד מהפיד", "קריאה נוספת")
at 1.125rem with a hairline rule. Heebo semibold for stream-row headlines
(~1.05rem) and all UI/body text — serif still must **not** be used below
~1.1rem (the high-contrast face reads thin/grey). Kickers/meta 10–12.5px.
Numerics use `MonoValue`.

---

## 4. Component inventory

### `components/shared/` — cross-area primitives
`EmptyState` · `ErrorState` (strip + page variants) · `LoadingSkeleton`
(card/row/stat shimmer) · `StatCard` (mono-izes only numeric values — Hebrew
text stays in body font) · `PageHeader` (serif title + optional icon + actions
slot) · `SectionCard` (titled console panel) · `GhostChip` (quiet metadata) ·
`PulseDot` (tone dot, optional pulse) · `MonoValue` (LTR numerics inside RTL).

### `components/shell/` — app frame
`AppShell` (`area="product"|"ops"`) · `ProductNav` (desktop rail, מוצר/קונסולה
groups) · `OpsNav` (console strip) · `DataModeBadge` (pulsing pill) ·
`ProfileSwitcher` (Radix dropdown, sandbox "בדיקה" tag) · `navConfig.js`
(+ tests — area resolution, llm-qa backend gate, mobile nav).

### `components/feed/` — the flagship ("The Edition", PR A)
**Story species:** `LeadStory` (aura + court-arc + serif display headline) ·
`BulletinStrip` (מבזק / "לא לפספס" level, gold start-edge bleed) · `EditorialTier` (asymmetric
major/minor blocks) · `StreamRow` (typographic row; inline expand; relevance-
scaled type + level dot in filtered mode) · `BriefsDigest` (collapsed low_feed
one-liners).
**Edition frame:** `EditionHeader` (date line + "המהדורה של X") ·
`SignalSpectrum` (proportional level bar; segments + legend are the level
filters; grows in on mount) · `SignalBoard` (PR A.1 — sticky side board on xl:
vertical spectrum, quick topic filters, desk facts derived from page data) ·
`TopicFilters` (quiet text toggles, inline or vertical) · `SectionHeading`
(small tracked Heebo label + hairline rule — serif is reserved for story
headlines) · `EditionSkeleton` (edition-shaped loading).
**Desktop composition (PR A.1):** the lead is a full-width hero band (layered
signal mesh, half-court SVG that draws in on mount, signal-strength
instrument); below it the editorial column runs beside the sticky signal board
in an `xl:grid-cols-[1fr_280px]`. Serif weight tops out at 700 (the 800 import
was dropped); the edition title stays smaller than the lead headline.
**Voice & actions:** `DeskVoice` ("למה אצלך" + expandable margin note; full
trace stays in Debug) · `FeedbackControls` (`variant="icons"|"text"` — emits
`more_like_this`/`less_like_this` unchanged) · `SourceMeta`.
**Logic modules (+tests):** `editionComposer.js` (stable partition into tiers) ·
`storyLabels.js` (Hebrew kicker maps: entity/league/sport · event type;
`condensedReason`) · `feedFilters.js` (level + topic filters) ·
`motionPresets.js`. `DecisionBadge` + `decisionConfig.js` remain (Hebrew labels
cross-locked to `DECISION_LABELS_HE` by test) — consumed by Debug, LLM QA,
Preferences, and `StreamRow`'s level dots; no longer rendered as feed badges.
Removed in PR A: `ArticleCard`, `FeedHero`, `FeedHeader`, `FilterChips`,
`SignalRail`, `EntityChips`, `RelevanceReason`.

### `components/ops/` — console (renamed from `ingestion/`)
`SchedulerPanel` · `IngestionPanel` · `BenchmarkPanel` · `HealthCard` ·
`SourceToggleCard` (letter-avatar rows) · `consoleStyles.js` (`consoleButton`
steel-blue, `consoleToggle`, `consoleAlert`).

### `components/debug/`
`DebugArticleCard` · `ProfileComparisonTable` · `ReasoningTrace` (numbered chain
as a console trace) · `ClassifiedByBadge` (+ `classifiedByConfig.js` + tests —
llm=blue / guardrail=cyan / failure=red / low-conf=gold).

### `components/preferences/`
`TopicCard`.

**JS-side variant config and pure logic live in plain modules**
(`decisionConfig.js`, `classifiedByConfig.js`, `navConfig.js`, `feedFilters.js`,
`editionComposer.js`, `storyLabels.js`, `motionPresets.js`) so they stay
testable in the Vitest `node` environment without a DOM.

---

## 5. RTL rules (hard requirements)

- `<html lang="he" dir="rtl">` is set in `frontend/index.html`. This is what
  makes Radix portals (dropdowns/dialogs render into `document.body`) inherit
  RTL — a div-level `dir` does **not** reach them.
- **Logical utilities only** in new code: `ms-/me-/ps-/pe-`, `start-/end-`,
  `text-start/text-end`, `border-s/border-e`, `rounded-s/rounded-e`. **Never**
  `ml-/mr-/pl-/pr-/left-/right-/text-left/text-right`.
- Prefer `gap` over `space-x-*` (the latter needs `space-x-reverse` in RTL).
- Numbers/times/IDs render LTR inside RTL flow via `MonoValue` (`dir="ltr"`).
- Directional icons: "forward/next" is `ChevronLeft` in RTL; flip
  external-link/open glyphs with `rtl:-scale-x-100` where the direction is
  semantic.
- Audit before shipping: the tight grep
  `(?<![\w-])(m[lr]-[0-9]|p[lr]-[0-9]|left-[0-9]|right-[0-9]|space-x-[0-9]|rounded-[lr]-|border-[lr]-|text-(left|right))`
  over `src` (excluding `ui/`) must return nothing.

---

## 6. Conventions & gotchas

- **Optional props need defaults.** Destructuring a prop without a default
  (e.g. `className`) makes checkJs infer it as *required* and flags every call
  site that omits it — including existing pages. Always default optional props
  (`className = ""`).
- **`StatCard` values**: numeric only get the mono/LTR treatment; a Hebrew
  string value must not be forced LTR (it garbles). `StatCard` detects this.
- **Frozen layers**: `src/context`, `src/api`, `src/engine`, `src/data` and the
  entire `backend/` are the contract. UI never modifies them. The `useApp()`
  surface is the only bridge between pages and data.
- **Two data modes**: `VITE_DATA_MODE=local` (mock data + JS engine) and
  `backend` (FastAPI). Every page must work in both; backend-only panels
  (scheduler/health/benchmark/LLM-QA) render an explanation or hide in local.
- **shadcn primitives under checkJs** emit type-noise (untyped forwardRef). Only
  adopt a `ui/*` primitive when it earns its keep; a lightweight inline
  alternative (e.g. the inline expand in `RelevanceReason` instead of a Radix
  popover) is often cleaner and avoids the noise.

---

## 7. Bundle

Baseline (pre-redesign) JS ≈ 114 kB gz. After the full redesign ≈ 154 kB gz.
The ~40 kB increase is fonts + the one-time Radix/floating-ui chain from the
first dropdown adoption; subsequent Radix usage adds little. Base44 leftover
dependencies (Stripe, three.js, react-leaflet, react-quill, jspdf, html2canvas,
moment, lodash, …) are still installed and pruning them is a **separate**
post-redesign cleanup (see the redesign plan §8) — never mixed into a
visual/product PR.
