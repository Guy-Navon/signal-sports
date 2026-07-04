# Signal Sports — Implementation Audit

> **⚠ HISTORICAL SNAPSHOT — SUPERSEDED.** This document was written before *any*
> backend work and before the frontend redesign. It audits the original
> Base44-generated prototype: a pure-frontend app with no backend, no
> database, no tests, mock data only, and a read-only Preferences page. **None
> of that describes the current system.** Since this was written:
> - A full FastAPI backend was built (`backend/app/`) with SQLite persistence,
>   real RSS ingestion (Walla Sport, Israel Hayom Sport), an HTML-scraping
>   pilot (Sport5), a deterministic + LLM classification pipeline, a
>   scheduler, and 1081 pytest tests.
> - The entire frontend UI was rebuilt twice over: first "Court Vision"
>   (PRs 1–6, token system + shadcn/Radix adoption), then "The Edition" +
>   shell/product/ops redesign (PRs A–E) — a from-scratch visual language.
>   Almost every file path named below (`FeedCard.jsx`, `AppLayout.jsx`,
>   `ProfileSwitcher.jsx` under `components/feed/`, etc.) no longer exists.
> - Every specific bug and gap called out below (source-toggle no-op,
>   unwritable Preferences, no tests, no persistence) has been fixed.
> - Real clustering is still **not** implemented (dedup is URL-only) — that
>   part of this audit remains accurate.
>
> **For current, accurate state, read `docs/CURRENT_PROJECT_STATE.md` first.**
> This file is kept only as a historical record of the starting point — do
> not treat anything below as a description of the app today.

---

## Repository Structure

```
signal-sports/
├── src/
│   ├── main.jsx                  # App entry point, routing, providers
│   ├── index.css                 # Global Tailwind CSS + CSS variables (dark theme)
│   ├── context/
│   │   └── AppContext.jsx        # Global state: profiles, articles, scoring, feedback
│   ├── data/
│   │   ├── userProfiles.js       # 2 user profiles (Guy, casual_deni_fan)
│   │   ├── feedSources.js        # 7 news sources (mock, no real fetching)
│   │   └── mockArticles.js       # 41 mock articles + 1 hardcoded cluster
│   ├── engine/
│   │   └── relevanceEngine.js    # Core scoring engine
│   ├── pages/
│   │   ├── Feed.jsx              # Main feed (hidden articles excluded)
│   │   ├── Debug.jsx             # Admin view (all articles including hidden)
│   │   ├── Preferences.jsx       # Topic/entity/mute viewer (partially editable)
│   │   ├── Sources.jsx           # Source manager (toggle has no effect on scoring)
│   │   └── Results.jsx           # Placeholder page (not implemented)
│   ├── components/
│   │   ├── feed/
│   │   │   ├── FeedCard.jsx      # Article/cluster card with reasoning
│   │   │   ├── DecisionBadge.jsx # Visual badge for decision level
│   │   │   └── ProfileSwitcher.jsx
│   │   ├── layout/
│   │   │   └── AppLayout.jsx     # Header + navigation layout
│   │   └── ui/                   # ~60 shadcn/ui components (Radix-based)
│   ├── hooks/
│   │   └── use-mobile.jsx        # Mobile viewport detection
│   └── lib/
│       ├── utils.js              # cn() Tailwind class helper, isIframe
│       ├── query-client.js       # TanStack Query config (unused)
│       └── PageNotFound.jsx      # 404 page
├── CLAUDE.md                     # Product context (authoritative)
├── package.json
└── [config files]                # vite, tailwind, eslint, postcss, jsconfig
```

## Framework and Dependencies

**Core:**
- React 18.2.0 + React Router 6.26.0
- Vite 6.1.0 (bundler)
- Tailwind CSS 3.4.17 (dark theme, custom color scheme)
- shadcn/ui component library (Radix UI primitives)
- Pure frontend — no backend, no database, no API layer

**Actually used:**
- `lucide-react` — icons throughout the UI
- `date-fns` — relative time formatting in FeedCard (Hebrew locale)
- `clsx` + `tailwind-merge` — class merging utility
- `react-router-dom` — client-side routing
- `next-themes` — likely configured but not deeply used
- `sonner` — toast notifications (wired up, may not be visibly used yet)

**Configured but unused:**
- `@tanstack/react-query` — QueryClient created in main.jsx, wraps the app, but no `useQuery` calls exist anywhere. All data is synchronous mock.
- `react-hook-form` + `zod` — imported in package.json, no forms in the current pages

**Likely unused (Base44 kitchen sink):**
- `@stripe/react-stripe-js` + `@stripe/stripe-js` — payment integration, no business model currently
- `three` — 3D graphics engine, no use in a news feed
- `html2canvas` + `jspdf` — PDF export functionality
- `react-leaflet` — map rendering
- `react-quill` — rich text editor
- `canvas-confetti` — confetti animations
- `recharts` — charting library (statistics exist in Debug but are plain counts, not charts)
- `embla-carousel-react` — carousel
- `input-otp` — OTP authentication inputs (no auth in this app)
- `react-day-picker` — date picker
- `@hello-pangea/dnd` — drag and drop
- `cmdk` — command palette
- `moment` — date library (date-fns is used instead; moment is redundant)

These add significant bundle weight and noise. They are typical of Base44-generated scaffolding.

## Available Scripts

```
npm run dev        # Start Vite dev server
npm run build      # Production build
npm run lint       # ESLint (quiet mode)
npm run lint:fix   # ESLint with auto-fix
npm run typecheck  # TypeScript type checking via jsconfig.json
npm run preview    # Preview production build locally
```

No test runner is configured. No test files exist anywhere in the project.

## Current App Capabilities

What the app can actually do today:

1. **Switch between two user profiles** (Guy and Casual Deni Fan) — profile switching immediately recalculates all scores
2. **Score all mock articles against the active profile** — per-article decision + reasoning
3. **Display the feed** — hidden articles excluded, sorted by decision rank then date
4. **Display the debug panel** — all articles including hidden, searchable, filterable by decision
5. **Compare decisions across profiles** — side-by-side view showing divergences between Guy and Casual Deni Fan
6. **View topic configuration** — expand each topic to see mode, entities, event rules
7. **Toggle mute on topics and sources** (in Preferences) — muting is profile-specific and updates immediately
8. **Toggle source enabled/disabled** (in Sources page) — this changes UI state but has no effect on scoring (see bugs section)
9. **Record user feedback** ("more like this", "not interested") — feedback events are stored in state but never read back to influence anything

What the app cannot do today:

- Edit topic priorities, modes, or event rules through the UI
- Add or remove topics from a profile
- Add or remove entities from a profile
- Compute clusters dynamically from article content
- Persist any state across page refreshes
- Fetch real articles from any source
- Translate article titles
- Convert natural language into preference rules
- Use feedback to adjust the preference profile

## Data Model

### Article

```js
{
  id: string,
  source: string,                // source id matching feedSources
  sourceDisplayName: string,
  url: string,
  title: string,                 // displayed title (Hebrew)
  originalTitle: string | null,  // original title if translated
  translatedTitle: string | null,// translated title
  language: "he" | "en",
  publishedAt: ISO8601 string,
  sport: string,                 // "basketball", "football", "tennis"
  league: string,                // "EuroLeague", "NBA", "Israeli Basketball League", etc.
  entities: string[],            // named entities: teams, players, coaches
  eventType: string,             // "negotiation", "signing", "match_result", "injury", etc.
  importance: "very_low" | "low" | "medium" | "high" | "very_high",
  confidence: 0.0–1.0,
  tags: string[],
  clusterId: string | null       // assigned if article belongs to a cluster
}
```

### Cluster (static, hardcoded)

```js
{
  id: string,
  clusterTitle: string,
  clusterSummary: string,
  articleIds: string[],          // IDs of grouped articles
  firstSeenAt: ISO8601 string
}
```

### User Profile

```js
{
  userId: string,
  displayName: string,
  language: "he" | "en",
  profileType: string,
  topics: Topic[],
  mutedTopics: string[],         // topic IDs to silence
  mutedSources: string[],        // source IDs to silence
  followedEntities: string[]     // entities that trigger boosts
}
```

### Topic (within a profile)

```js
{
  topicId: string,
  label: string,                 // display name (Hebrew)
  sport: string,                 // match by sport
  priority: number,              // 0–100, higher = evaluated first in fallback
  mode: "all" | "major_only" | "followed_entities_only" | "titles_only" | "high_importance_only" | "muted",
  leagues: string[],             // match by league
  entities: string[],            // match by entity (also triggers boost)
  eventRules: { [eventType]: decision }
}
```

The preference model is well-designed. It is expressive enough to represent nuanced personal interests. The problem is that it can only be authored by hand in code; there is no UI to edit it.

## Current Relevance Scoring Logic

**File:** `src/engine/relevanceEngine.js`

This is the most important and best-implemented file in the codebase.

**Scoring pipeline:**

1. Check `profile.mutedSources` — if article's source is muted, return hidden
2. Check `profile.mutedTopics` — if article's sport/league matches a muted topic, return hidden
3. Find all profile topics that match the article by sport, league, or entity
4. If no topics match, return hidden
5. Score the article against each matching topic; take the best decision
6. Return the decision with a full Hebrew reasoning chain

**Scoring modes (per topic):**

- `all`: default; apply event rules, then entity boost, then importance boost
- `major_only`: only articles with high/very_high importance OR an explicit event rule are shown
- `followed_entities_only`: article must mention one of the followed entities; no entity match → hidden
- `titles_only`: only articles whose eventType has an explicit non-hidden rule (e.g., grand_slam_winner)
- `high_importance_only`: low importance articles are hidden; then fall through to event rules

**Boosts:**

- Entity boost: if article mentions a topic's primary entity AND the event rule gives "feed" → upgrade to "high_feed"
- Importance boost: if article importance is "very_high" AND current decision > hidden → upgrade by one level; hard capped at "high_feed"

**Push discipline:**

Push is correctly guarded. The importance boost is hard-capped at `high_feed`. Push is only reachable via an explicit `eventRules` entry. This matches the product specification. Push will not inflate even if many articles have high importance.

**Reasoning chain:**

Every decision produces a full Hebrew explanation: profile name, topic matched, mode applied, event rule used or reason for fallback, final decision. This is real — it reflects the actual execution path, not a post-hoc label.

**Assessment:** The relevance engine is genuine, well-architected, and correct. It is the strongest part of the codebase.

## Current Clustering Logic

**Status: Fake / Hardcoded**

There is exactly one cluster in the codebase, defined statically in `mockArticles.js`:

```js
export const mockClusters = [
  {
    id: "cluster_maccabi_negotiation_001",
    clusterTitle: "מו״מ מכבי ת״א עם גארד יורוליג",
    clusterSummary: "...",
    articleIds: ["article_001", "article_002", "article_003"],
    firstSeenAt: "2026-06-11T09:00:00Z"
  }
];
```

The three articles in this cluster have `clusterId: "cluster_maccabi_negotiation_001"` set as a hardcoded field. There is no algorithm that groups articles. The "cluster" is a manually authored fixture.

The `scoreCluster` function in the engine is real: it scores all articles in a cluster and returns the best decision. But it only operates on clusters that already exist. It does not create clusters.

Real clustering would require: shared entity detection, time windowing (articles within N hours), semantic similarity or shared tags, deduplication logic. None of this exists.

## Current Debug Logic

**File:** `src/pages/Debug.jsx`

The debug panel is well-implemented and genuinely useful.

**Capabilities:**
- Shows all articles, including hidden ones (source of truth: `debugItems` from context, which does not filter by decision)
- Decision stats at the top: counts for push, high_feed, feed, low_feed, hidden
- Searchable by title, sport, or league
- Filterable by decision level
- Each row is expandable to show:
  - Full metadata (sport, league, event type, importance, confidence, entities)
  - Matched topic ID and matched rule
  - Full reasoning chain (all lines, not truncated)
- Comparison tab: all articles scored side-by-side against both profiles, divergent rows highlighted

**Assessment:** The debug explanations are real. They come directly from the `score.reasoning` array produced by the relevance engine during actual scoring. They are not static labels or fabricated descriptions. The comparison view is particularly valuable for catching scoring logic errors.

## Current Preferences Behavior

**File:** `src/pages/Preferences.jsx`

The page has three tabs: Topics, Entities, Muted.

**What works:**
- Topics tab displays all topics for the active profile with expandable detail (mode, priority, leagues, entities, event rules)
- Entities tab displays the `followedEntities` array
- Muted tab shows muted topics and sources with toggle buttons
- Muting topics and sources calls `updateProfile()` and immediately affects scoring

**What is read-only:**
- Topic priorities cannot be changed
- Topic modes cannot be changed
- Event rules cannot be edited
- Entities cannot be added or removed
- Topics cannot be added or removed
- There is no free-text input for preferences

**Dead code noted:**
Preferences.jsx defines `DECISION_OPTIONS` and `DECISION_LABELS` constants that are never rendered. These appear to be leftover scaffolding from an unfinished inline editing feature.

**Assessment:** The Preferences page is essentially a configuration viewer with a mute toggle. It cannot be used by a real user to define or adjust their interests.

## What Works Well

1. **The relevance engine is real and correct.** It handles 5 scoring modes, entity boosts, importance boosts, event aliases, push discipline, and muted sources/topics. It is testable, deterministic, and explainable.

2. **Per-profile decisions are genuinely different.** The comparison view confirms that articles like "Hornets beat Wizards" → feed for Guy, hidden for Casual Deni Fan. "Deni Avdija traded" → push for both, but for different reasons (NBA broad interest vs. followed entity). The core product idea is implemented correctly in the engine.

3. **Push is rare and intentional.** The hard cap on auto-boost at high_feed means push can only occur when explicitly configured in event rules. The mock data and profiles have been set up with appropriate restraint.

4. **The debug view is honest.** Reasoning chains reflect actual scoring execution. Hidden articles are visible. The comparison tab shows inter-profile divergence. This is exactly what the product needs to tune and validate the engine.

5. **Mock data is high quality.** The 41 articles cover all relevant sports, leagues, event types, and importance levels. They include deliberate edge cases (same entity in different event types, articles designed to diverge between profiles).

6. **Profile switching is instant.** All scoring is in useMemo with profileId + profiles as dependencies. Switching profiles triggers immediate full recalculation with no manual cache invalidation needed.

7. **The preference data model is expressive.** The topic structure (mode + priority + leagues + entities + eventRules) is capable of encoding nuanced, rule-based preferences. It is the right foundation for the scoring engine.

8. **UI is polished.** Dark theme, Hebrew RTL, responsive layout, decision badges with color coding, feed cards with collapsible reasoning. The visual design is production-quality.

## What Is Weak

1. **Clustering is hardcoded.** There is one manually authored cluster. No algorithm groups articles. For a product whose value includes "group duplicate stories," this is a significant gap.

2. **Feedback is a dead end.** `addFeedback()` records events in memory. Nothing reads `feedback` to modify profiles, re-score articles, or produce any observable change. On page refresh, all feedback is lost. The feedback loop — one of the three core personalization paths — is entirely unimplemented.

3. **Preferences are read-only.** A user cannot edit their profile through the UI. The only writeable preference actions are muting a topic or source. Priority, mode, event rules, entity lists — all are locked in code.

4. **The Sources page toggle does not affect scoring.** `toggleSource()` updates the `sources` state in AppContext, but `scoredArticles` is computed from `mockArticles` directly, ignoring the enabled/disabled state of sources. A user disabling "Eurohoops" in the Sources page will still see Eurohoops articles in their feed. This is a silent bug.

5. **The importanceFallback returns low_feed for "low" and "very_low" importance articles with no event rule.** When an article has no event rule match and importance is "low" or "very_low," the fallback returns `low_feed` rather than `hidden`. This means genuinely noisy, low-importance articles with no specific rule can still surface in the feed. The correct behavior is probably `hidden` for very_low and `hidden` or `low_feed` for `low` based on topic priority.

6. **No tests.** There are no test files, no test runner, and no test configuration. The relevance engine is the most critical component and it is entirely untested programmatically. A wrong scoring decision is undetectable without running the full app.

7. **No persistence.** Page refresh resets all state: active profile, source toggles, feedback. This makes experimentation fragile and prevents any real-world testing.

## What Is Generic

- The UI component library (`src/components/ui/`) is entirely shadcn/ui boilerplate. About 60 generic components are present; only a handful are used.
- The layout and navigation structure is standard SPA scaffolding.
- The Results page is a placeholder with no product-specific logic.
- The `src/utils/index.ts` file exists but is empty.
- `src/lib/query-client.js` configures TanStack Query with default options but it is never used.

## What Seems Hardcoded

- Both user profiles are hardcoded in `userProfiles.js`. There is no mechanism to create a new profile through the UI.
- The cluster is hardcoded with `clusterId` fields set directly on articles. Clustering cannot emerge from content analysis.
- Source URLs in `feedSources.js` are real URLs but no fetching occurs. The sources are configuration metadata only.
- Mock article metadata (`eventType`, `importance`, `confidence`, `entities`) is manually assigned. In a real system this would be produced by an article classification pipeline.
- The decision labels in the UI are hardcoded in Hebrew. There is no internationalization layer.

## What Is Unnecessary

**Code that should be removed:**

- `src/pages/Results.jsx` — placeholder with no product value; remove or replace with real functionality
- `DECISION_OPTIONS` and `DECISION_LABELS` constants in `Preferences.jsx` — dead code from unfinished editing feature
- `src/utils/index.ts` — empty file

**Dependencies that should be removed:**

- `@stripe/react-stripe-js` + `@stripe/stripe-js` — no payment use case for this product
- `three` — 3D graphics, no use case
- `html2canvas` + `jspdf` — PDF export, no use case
- `react-leaflet` — maps, no use case
- `react-quill` — rich text editor, no use case
- `canvas-confetti` — no use case
- `embla-carousel-react` — no use case
- `input-otp` — no auth, no OTP
- `react-day-picker` — no date selection needed
- `@hello-pangea/dnd` — no drag-and-drop yet
- `cmdk` — no command palette
- `moment` — `date-fns` is already in use; moment is redundant
- `@tanstack/react-query` — not used; can be removed until real data fetching exists

These add 2–5 MB to the bundle and signal that this scaffold was generated generically rather than for this specific product.

## What Is Missing Compared to the Intended Product

| Intended feature | Current status |
|---|---|
| Dynamic article clustering | Not implemented — 1 hardcoded cluster |
| Real source ingestion (RSS/scraping) | Not implemented — mock data only |
| Feedback-driven preference learning | Not implemented — feedback recorded but ignored |
| Editable preference rules in UI | Not implemented — Preferences is read-only |
| Natural language preference input | Not implemented |
| Synthetic headline calibration | Not implemented |
| Backend / persistence layer | Not implemented |
| Article translation engine | Partial — fields exist (originalTitle, translatedTitle) but no translation occurs |
| Multi-source topic explanation | Not implemented — debug shows matched rule but no NLP explanation |
| Per-user article visibility control | Not implemented — only profile-level muting |
| "More like this" / "Never show this" feedback actions in UI | Partial — buttons exist in FeedCard but only record events, produce no change |
| Source-toggle wired to scoring | Bug — toggle updates UI state but not scoring pipeline |

## Whether the Current Architecture Can Support Future Onboarding and Personalization

**Can it support natural language preference input?**
The profile data structure is ready to receive structured preferences. An LLM conversion step that maps free text → topics array → eventRules can feed directly into `updateProfile()`. The engine requires no changes. What is missing is the conversion layer and the UI to enter the text.

**Can it support synthetic headline calibration?**
The calibration concept maps well to the existing scoring model. Each synthetic headline would be pre-tagged with the same fields articles use (sport, league, entities, eventType, importance). The user's ratings produce rules that can be compiled into topics and eventRules. The scoring engine would consume these rules unchanged. A new `CalibrationPage` would need to be built.

**Can it support feedback-driven learning?**
Feedback events are already being recorded with the right structure (`userId`, `articleId`, `action`). What is missing is a preference mutation layer: a function that reads feedback events and adjusts topic priorities, event rules, or muted topics. The context already has `updateProfile()`, so this is a matter of implementing the mutation logic.

**Conclusion:** The architecture is sound for future personalization. The preference model is expressive, the scoring engine is correct, and `updateProfile()` is the right hook for all three onboarding paths. None of the three paths require major architectural changes — only new features built on the existing foundation.

## Recommended Next Steps

Listed in order of product impact:

1. **Fix the source toggle bug.** `scoredArticles` must filter articles by enabled sources before scoring, or respect `profile.mutedSources` when a user disables a source globally. Currently the Sources page is misleading — the toggles appear to do something but have no effect.

2. **Fix the importanceFallback for very_low importance.** Articles with no event rule and `importance: "very_low"` should return `hidden`, not `low_feed`. Articles with `importance: "low"` and a low-priority topic should also likely return `hidden`. This is a noise leak.

3. **Add tests for the relevance engine.** The engine is the product's core. Its scoring decisions are not currently validated programmatically. A test suite covering each profile × article combination, each scoring mode, and each boost condition would make future changes safe. No test runner is configured — add Vitest (compatible with Vite).

4. **Make the Preferences page editable.** Users should be able to change topic priority and mode, and eventually edit event rules. Even a simplified version (priority slider + mode dropdown per topic) would make the app demonstrable as a real product.

5. **Build the synthetic headline calibration screen.** This is the fastest path to a compelling user-facing personalization demo. A set of pre-tagged synthetic headlines + a rating UI produces a functional preference profile without requiring real article ingestion or NLP.

6. **Wire feedback to preference updates.** The feedback data structure is correct. Implement a preference mutation function: "not interested" → downgrade that eventType's rule for that topic. "More like this" → upgrade or add rule. This closes the feedback loop.

7. **Implement real clustering.** Group articles by shared entities + time window. Start with a simple rule-based approach (same primary entity + same eventType + within 24 hours = cluster). Replace the hardcoded cluster fixture.

8. **Remove unused dependencies.** Clean the `package.json` of the 12+ unused Base44 dependencies. This reduces bundle size and makes the codebase easier to reason about.

## Suggested First Refactor

**Priority: Fix the source toggle → Preferences editable → Add tests**

The biggest trust issue with the current app is that the Sources page appears functional but is a no-op. Fix this first so the UI is truthful.

The biggest product gap is that preferences cannot be edited. Building even a minimal preference editor (priority + mode per topic) turns the app from a demo into something that can actually be tested with users.

Tests should follow immediately after. The relevance engine is complex enough that untested changes will introduce bugs.

Do not refactor the relevance engine itself. It is the strongest part of the codebase and should be treated as stable until there are tests covering it.

---

## PR 1 Changes

**Date:** 2026-06-11

### Test runner added

- Installed `vitest` as a dev dependency.
- Added `test` script to `package.json`: `vitest run`.
- Added `test` configuration block to `vite.config.js` (`environment: "node"`).
- No separate config file needed — vitest reads from `vite.config.js`.

### Engine tests added

New file: `src/engine/relevanceEngine.test.js`

20 test cases covering:

| Test group | Cases |
|---|---|
| Maccabi basketball (Guy) | negotiation → push, injury → push, candidate → high_feed (not push), schedule → hidden |
| NBA profile divergence | Hornets/Wizards visible for Guy, hidden for Casual Deni Fan; Deni trade push for both profiles |
| Tennis titles_only | Grand Slam winner → high_feed, early-round result → hidden |
| Generic content | Pre-match schedule → hidden, NBA preview → low_feed for Guy / hidden for Casual Deni Fan |
| Muting | Muted source → hidden, muted topic → hidden, disabled source (new) → hidden |
| Push discipline | Finals result (very_high importance) caps at high_feed; title_win via explicit rule → push |
| importanceFallback | very_low with no event rule → hidden; low + low-priority topic → hidden |

### Source toggle behavior fixed

**Problem:** The Sources page toggle updated `sources` state in context but `scoredArticles` was computed from `mockArticles` directly, ignoring whether sources were enabled. Disabling a source had no visible effect on the feed.

**Solution:** Added optional `options` parameter `{ disabledSourceIds: Set<string> }` to `scoreArticle`, `scoreAllArticles`, and `scoreCluster`. Disabled source IDs are checked at the top of `scoreArticle`, before muted-source and topic checks, returning `hidden` with `matchedRule: "disabled_source"` and a Hebrew reasoning entry: `"מקור כבוי (Sources page): <id>"`.

AppContext now computes `disabledSourceIds` from `sources` state and passes it to all three scoring calls (articles, clusters, comparison). Disabled-source articles are visible in the debug panel as `hidden` with the correct reason.

Files changed:
- `src/engine/relevanceEngine.js` — added `options` param and `disabled_source` check
- `src/context/AppContext.jsx` — added `disabledSourceIds` memo, passed to all scoring calls

### importanceFallback noise leak fixed

**Problem:** The fallback branch (no matching event rule) returned `low_feed` for articles with `very_low` or `low` importance, regardless of topic priority. Noise articles with no specific rule still appeared in the feed.

**Fix:** Changed the final `else` branch:
- `low` importance + topic priority ≥ 70 → `low_feed` (unchanged behavior for high-priority topics)
- `low` importance + topic priority < 70 → `hidden` (new)
- `very_low` importance → `hidden` (was `low_feed`)

In practice this rarely triggers for the current mock data (most articles have explicit event rules), but it is the correct default for unanticipated article types hitting low-priority topics.

File changed: `src/engine/relevanceEngine.js` — `importanceFallback` function.

### Entity-specific push override in scoreAllMode

**Problem:** Guy's NBA topic had `major_trade: "high_feed"` as a generic rule, but per the product spec a trade involving Deni Avdija should be `push` for Guy even in `all` mode (not just for `followed_entities_only` mode). There was no mechanism to differentiate entity-specific overrides in `all` mode.

**Solution:** Added a pre-check in `scoreAllMode`: when the article's entity matches a primary topic entity and the event type is push-eligible, look for an `<entity_key>_trade` rule in `eventRules`. If found, that rule takes precedence over the generic event rule. Added `deni_avdija_trade: "push"` to Guy's NBA topic `eventRules`.

This mirrors the existing pattern in `scoreFollowedEntitiesOnly` and is consistent with how the engine handles entity-specific trade rules.

Files changed:
- `src/engine/relevanceEngine.js` — entity-specific override block in `scoreAllMode`

### PR 2.6: entityEventRules — explicit per-entity event overrides

**Problem with `deni_avdija_trade` hack:** The prior entity-specific mechanism stored rules like `deni_avdija_trade: "push"` inside the generic `eventRules` object. The engine constructed these keys at runtime using `${entityKey}_trade` and triggered them for ANY event type listed in `PUSH_ELIGIBLE_EVENT_TYPES` (which includes `injury`, `signing`, `major_trade`, `star_trade`, etc.). This meant:

1. The key name `deni_avdija_trade` was misleading — it fired for injuries and signings, not only trades.
2. Adding a new followed entity would require manually adding a `<entity_key>_trade` key to `eventRules`, polluting the event rules namespace with hidden conventions.
3. The `PUSH_ELIGIBLE_EVENT_TYPES` gating was a workaround for the absence of a real per-entity, per-event rule model.
4. Calibration-generated profiles would need to reproduce this naming convention, which would be fragile.

**Solution:** Replaced both hacks with a first-class `entityEventRules` field on topics.

**New data model:**
```js
{
  topicId: "nba",
  entityEventRules: {
    "Deni Avdija": {
      major_trade: "push",   // overrides generic major_trade: "high_feed"
      injury: "push"         // overrides generic injury: "feed"
    }
  },
  eventRules: {
    major_trade: "high_feed",  // applies when Deni is NOT the entity match
    injury: "feed",
    ...
  }
}
```

**Engine behavior:** In both `scoreAllMode` and `scoreFollowedEntitiesOnly`, if the article has an entity match, the engine checks `topic.entityEventRules[entityMatch][eventType]` before checking the generic `eventRules`. Alias resolution reuses `getEventDecision`, so `star_trade` → `major_trade` alias lookups work consistently for both generic and entity-specific rules. If a rule is found, it is applied with `applyImportanceBoost` and returned immediately.

**Why this matters for calibration:** When `inferPreferenceDraftFromCalibration` eventually applies a generated profile, it can express "Deni Avdija injury → push" as a structured `entityEventRules["Deni Avdija"].injury = "push"` entry rather than relying on a naming convention buried inside `eventRules`. The calibration inference engine can be taught to write `entityEventRules` directly.

**`PUSH_ELIGIBLE_EVENT_TYPES` removed:** This constant was only used to gate the entity-specific `_trade` key lookup. With `entityEventRules` being explicit and covering any event type, the gate is no longer needed. The push decision comes from the rule value itself, not from a list of permitted event types.

Files changed:
- `src/engine/relevanceEngine.js` — removed `PUSH_ELIGIBLE_EVENT_TYPES`, replaced entity hacks in both scoring functions
- `src/data/userProfiles.js` — added `entityEventRules` to Guy's NBA topic and Casual Deni Fan's NBA topic; removed `deni_avdija_trade` and `deni_avdija_news` keys
- `src/engine/relevanceEngine.test.js` — added 9 tests covering entity-specific rule behavior, profile data integrity, and divergence between entity rules and generic fallbacks
- `src/engine/datasetCoverage.test.js` — updated Deni Fan's article_047 expectation from `feed` to `high_feed` (entityEventRules now upgrades Deni's game result)
- `src/data/userProfiles.js` — added `deni_avdija_trade: "push"` to Guy's NBA eventRules
