# Signal Sports frontend — Signal Ledger

Last updated: 2026-07-24 on `experiment/frontend-reinvention`.

Signal Ledger is the experimental frontend architecture and visual system for
Signal Sports. It replaces the dark “Court Vision” product skin while keeping
the existing API, ranking, clustering, authorization, onboarding, feedback, and
learning contracts intact.

The core idea is **a personalized newsroom ledger**: warm editorial paper,
black ink, compact live telemetry, and a small number of high-signal colours.
It should feel like a sports publication whose front page is assembled for one
reader, not a dashboard whose cards happen to contain articles.

## Product principles

1. **Content is the layout.** `push`, `high_feed`, `feed`, and `low_feed`
   produce different compositions, type scales, density, and reading order.
2. **Personalization is explicit.** The edition names the reader, shows how
   many stories were selected from the scanned pool, and explains “למה אצלך”
   using real backend reasoning.
3. **A cluster is one evolving story.** The canonical headline owns the visual
   slot. Visible member reports expand behind it through `ClusterSources`;
   suppressed members never enter the consumer payload.
4. **Paper for product, instruments for operations.** Consumer routes use the
   warm ledger canvas. Admin and diagnostic routes keep a dense dark console
   theme under `.ops-shell`.
5. **No image dependency.** The hierarchy survives absent, broken, duplicated,
   or low-quality article imagery. No synthetic sports imagery is used.

## Tokens and typography

All semantic tokens live in `frontend/src/index.css` and are mapped through
`tailwind.config.js`.

| System | Product use |
|---|---|
| `background` | warm paper canvas |
| `foreground` | near-black ink, masthead, hard rules |
| `surface-1..3` | paper elevation and controls |
| `signal-push` | live/urgent red; top signal only |
| `signal-high` | strong personalized relevance and healthy state |
| `signal-feed` | regular feed and cluster reporting |
| `signal-low` | low-priority reading |
| `signal-ai` | system reasoning |
| `signal-hidden` | errors, suppression, destructive actions |

Frank Ruhl Libre carries large Hebrew editorial headlines. Heebo carries body,
navigation, controls, and dense metadata. Mono is reserved for sequence
numbers, counts, system labels, and English newsroom annotations.

Radii are intentionally small. The product uses hard rules, start-edge colour
bars, and paper/ink contrast instead of stacks of rounded cards. Reusable
recipes are `.editorial-rule-heavy`, `.ledger-panel`, `.eyebrow`,
`.index-label`, `.product-page`, `.product-shell`, and `.ops-shell`.

## Route and shell structure

Routes remain unchanged:

| Area | Routes |
|---|---|
| Public auth | `/login`, `/signup` |
| Session welcome | `/welcome` |
| Product | `/`, `/preferences`, `/interests`, `/calibration`, `/results`, `/account` |
| Admin/QA | `/sources`, `/debug`, `/llm-qa` |

`RequireSession` and `RequireOpsRole` continue to enforce the same boundaries.
`AppProvider` remains below `AuthProvider`, so consumer `/api/me/*` routing and
admin view-as behavior are unchanged.

`AppShell area="product"` supplies:

- black publication masthead with desktop navigation;
- warm registered-grid canvas;
- edge-to-edge mobile newsroom dock;
- responsive page transition and reduced-motion support.

`AppShell area="ops"` supplies:

- dark console tokens;
- desktop product/console rail and ops breadcrumb;
- dense panels suited to source, scheduler, notification, debug, and LLM QA
  workflows.

Every page route is loaded with `React.lazy`. Rollup vendor groups keep the
consumer entry separate from ops/QA code, motion, date utilities, icons, and
Radix primitives.

## Feed component boundaries

`Feed.jsx` coordinates data, filtering, empty/loading behavior, and the edition
layout. It does not rank or mutate feed decisions.

- `editionComposer.js` performs the stable tier partition.
- `EditionHeader` identifies the personal edition and intake ratio.
- `SignalSpectrum` and `TopicFilters` are the above-fold hierarchy controls.
- `LeadStory` is the front page: headline/action on paper and live context in
  the ink column.
- `BulletinStrip` handles additional push stories.
- `EditorialTier` handles `high_feed`.
- `StreamRow` handles regular `feed`.
- `BriefsDigest` compresses `low_feed`.
- `ClusterSources` expands visible reporting behind any lead, bulletin,
  editorial, or stream treatment.
- `DeskVoice`, `SourceMeta`, and `FeedbackControls` preserve reasoning,
  attribution, article opening, learning feedback, and never-show behavior.
- `SignalBoard` is a desktop reading-order index, not a duplicate dashboard.

No component derives a new decision. `AppContext`, API normalizers, and the
backend remain the source of truth.

## Responsive strategy

Desktop and mobile are separate compositions:

- **Desktop (`lg+`)**: full-width lead, editorial column, sticky reading index,
  inline masthead navigation.
- **Tablet**: single editorial column with above-fold spectrum and filters.
- **Mobile**: one-column front page; the lead’s black context column stacks
  below the headline; metadata wraps; the mobile dock is edge-to-edge and
  reserves bottom content padding.

The app has a 320px minimum supported width. `min-w-0`, wrapping metadata, and
logical alignment prevent long Hebrew headlines, cluster sources, and profile
controls from widening the document.

## RTL and accessibility

- `frontend/index.html` sets `lang="he"` and `dir="rtl"` at the document root,
  including Radix portals.
- New layout code uses logical `start/end`, `s/e`, and `text-start/end`
  utilities.
- Numerics use `MonoValue` where direction isolation is needed.
- Focus uses the global high-contrast `--ring`; controls retain semantic
  labels, `aria-expanded`, `aria-pressed`, and external-link safety.
- Motion is short, y-axis based, and disabled through
  `prefers-reduced-motion`/`useReducedMotion`.
- Interactive elements keep mobile tap targets and suppress accidental
  horizontal viewport growth.

## Data flow

```text
AuthContext session
      ↓
AppContext identity routing
      ↓
local engine fixtures OR existing FastAPI client
      ↓
API normalizers (snake_case → UI shape)
      ↓
Feed tier composition / route presentation
      ↓
existing feedback, interests, calibration, account, and ops calls
```

There are no backend changes in this experiment. It does not alter ranking,
visibility, freshness, clustering, push policy, ingestion, or authorization.

## Validation strategy

Required frontend gates:

```bash
cd frontend
npm run test
npm run lint
npm run typecheck
npm run build
```

Baseline on 2026-07-24:

- tests: 423 passed;
- lint: passed;
- typecheck: failed with 11 existing checkJs errors;
- build: passed with a 743 kB monolithic JS chunk warning.

The experiment fixes the checkJs failures and route-splits the bundle. Visual
checks use the real local relevance fixtures through the supported local data
mode; backend mode continues to use same-origin API routes.

Final validation on 2026-07-24:

- frontend: 424 tests passed, lint passed, typecheck passed, build passed;
- backend integration contracts: 180 tests passed (auth/session, acceptance
  journey, identity isolation, `/api/me`, interests, calibration, clustered
  feed, and feedback learning);
- build: largest chunk 216.26 kB, app entry 144.25 kB; no size warning;
- backend changes: none.

## Automated visual review

The final review set is generated from the running React application with:

```bash
cd frontend
npm run capture:visual
```

`frontend/scripts/capture-signal-ledger.mjs` uses the installed Chrome binary
through the Chrome DevTools Protocol; it adds no browser-test dependency. The
harness starts an isolated Vite server on port 5175, uses CDP device-metric
emulation at device-scale factor 1, waits for fonts and route data, asserts
that the document does not overflow horizontally, verifies each PNG's IHDR
dimensions, and removes its temporary browser profile and backend database.

Backend-mode captures start the local FastAPI app on port 8000 with enforced
auth, a disposable SQLite database, reserved `example.com` fixture identities,
and scheduler/Telegram notifications disabled. The login form is empty and no
password, cookie, token, or private address appears in the images.

| Evidence | Exact viewport | Data mode |
|---|---:|---|
| [Feed, desktop](frontend-screenshots/signal-ledger-final/feed-desktop-1440.png) | 1440 × 1000 | local fixtures |
| [Feed, tablet](frontend-screenshots/signal-ledger-final/feed-tablet-1024.png) | 1024 × 900 | local fixtures |
| [Feed, mobile 390](frontend-screenshots/signal-ledger-final/feed-mobile-390.png) | 390 × 844 | local fixtures |
| [Feed, mobile 375](frontend-screenshots/signal-ledger-final/feed-mobile-375.png) | 375 × 812 | local fixtures |
| [Feed, mobile 320](frontend-screenshots/signal-ledger-final/feed-mobile-320.png) | 320 × 640 | local fixtures |
| [Expanded cluster, desktop](frontend-screenshots/signal-ledger-final/feed-cluster-expanded-desktop.png) | 1440 × 1000 | local fixtures |
| [Expanded cluster, mobile](frontend-screenshots/signal-ledger-final/feed-cluster-expanded-mobile.png) | 390 × 844 | local fixtures |
| [Login](frontend-screenshots/signal-ledger-final/login-desktop.png) | 1440 × 1000 | FastAPI |
| [Onboarding interests](frontend-screenshots/signal-ledger-final/onboarding-interests-desktop.png) | 1440 × 1000 | FastAPI |
| [Onboarding calibration](frontend-screenshots/signal-ledger-final/onboarding-calibration-mobile.png) | 390 × 844 | FastAPI |
| [Preferences](frontend-screenshots/signal-ledger-final/preferences-desktop.png) | 1440 × 1000 | FastAPI |
| [Account](frontend-screenshots/signal-ledger-final/account-mobile.png) | 390 × 844 | FastAPI |
| [Operations sources](frontend-screenshots/signal-ledger-final/ops-sources-desktop.png) | 1440 × 1000 | FastAPI |
| [Operations debug](frontend-screenshots/signal-ledger-final/ops-debug-desktop.png) | 1440 × 1000 | local fixtures |
| [Empty feed](frontend-screenshots/signal-ledger-final/empty-feed-mobile.png) | 390 × 844 | FastAPI |
| [Backend error](frontend-screenshots/signal-ledger-final/error-state-desktop.png) | 1440 × 1000 | FastAPI failure path |
| [Not found](frontend-screenshots/signal-ledger-final/not-found-mobile.png) | 390 × 844 | local fixtures |

The local debug fixture is intentional: a newly seeded backend database has no
live-ingested `rss_` corpus, so its real debug feed is correctly empty. Sources
remains a backend integration capture; debug uses the supported local relevance
fixtures to exercise the populated console without manufacturing backend data.

Every final PNG was opened and inspected after the final generation. The
review covered overflow, Hebrew/RTL order and wrapping, fixed mobile navigation,
responsive visibility, metadata contrast, cluster expansion, empty/error
states, and desktop/mobile spacing. It found and corrected three material
evidence defects:

- local cluster scoring did not populate the visible-member presentation
  contract, leaving the expansion control unreachable in fixture mode;
- the first expanded-cluster captures toggled a below-fold component without
  scrolling it into evidence;
- a retained route scroll position clipped the top of the account capture.

Useful historical comparisons remain available:

- [Before — desktop feed](frontend-screenshots/before-feed-desktop.png)
- [Before — mobile feed](frontend-screenshots/before-feed-mobile.png)
- [Earlier after — desktop feed](frontend-screenshots/after-feed-desktop.png)
- [Earlier after — mobile feed](frontend-screenshots/after-feed-mobile.png)

## Known limitations

- The Results route is still intentionally a transparent coming-soon state;
  it does not fabricate live scores.
- No article-image field exists in the current normalized feed contract, so the
  design deliberately relies on type and reporting context.
- Full auth/onboarding persistence requires a running backend configured for
  enforced auth. The automated review starts that isolated backend for login,
  onboarding, preferences, account, and empty-feed evidence; local mode remains
  the deterministic presentation and populated-debug fixture.
- Native Windows window sizing is not used as mobile evidence. CDP viewport
  emulation captures and dimension-checks real 390px, 375px, and 320px
  viewports at device-scale factor 1.

## Migration and rollback

This work is isolated on `experiment/frontend-reinvention`. `main` remains the
rollback: closing the experiment or reverting its frontend commits restores
Court Vision without a data migration. No database, API, or backend rollback
is needed. Screenshots are review artifacts and may be removed independently.
