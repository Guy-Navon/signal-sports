# Signal Sports — Frontend

The Hebrew-first, RTL product UI and the ops console for Signal Sports. React 18 + Vite 6,
JavaScript/JSX (type-checked through `jsconfig.json`).

On `ui/next`, every consumer page and the public read-only demo use **Signal UI**: a lead
block only for a push, compact stream rows, a side column and a results strip. Ops keeps
its existing console shell, base tokens, Heebo and signal-bars logo. Design contract: [`../docs/FRONTEND_DESIGN_SYSTEM.md`](../docs/FRONTEND_DESIGN_SYSTEM.md).
Whole-project state: [`../docs/CURRENT_PROJECT_STATE.md`](../docs/CURRENT_PROJECT_STATE.md).

## Getting started

```bash
npm install
npm run dev
```

It opens on [http://localhost:5173](http://localhost:5173). The port is fixed
(`strictPort: true` in `vite.config.js`): if 5173 is taken, startup fails loudly. The
same-origin proxy and the Tailscale Serve chain depend on that port
([`../docs/MOBILE_REMOTE_ACCESS.md`](../docs/MOBILE_REMOTE_ACCESS.md)).

## Data modes

`VITE_DATA_MODE` (set in `.env.local`) picks one of two modes:

- `local` (default): mock data in `src/data/`, scored in the browser by the **frozen** legacy
  JS engine (`src/engine/relevanceEngine.js`). No backend, no login. It is a demo mode, and it
  gets no new intelligence: the backend is authoritative for every real decision. The mock
  articles, results, demo profiles and engine load through `src/context/localDemo.js`, a
  separate chunk that a backend session never fetches. Debug's profile comparison tab exists
  only here; in backend mode it shows one line saying so.
- `backend`: the real product. Requests go to same-origin relative paths (`/api/...`,
  `/health`), which the Vite dev proxy forwards to `http://127.0.0.1:8000`. Accounts, sessions,
  onboarding, the personalized feed, results, feedback and the admin-only ops console all need
  this mode. `VITE_API_BASE_URL` is an explicit override for direct cross-origin calls only.

```bash
# backend mode (start the backend first — see ../backend/README.md)
echo VITE_DATA_MODE=backend > .env.local
npm run dev
```

## Scripts

- `npm run dev`: dev server · `npm run build`: production build · `npm run preview`: preview the build
- `npm run test`: Vitest (node environment: models, API client, context, engine, drift guard)
- `npm run lint`: ESLint with `--max-warnings=0` · `npm run typecheck`: `tsc` over `jsconfig.json`
- `npm run capture:ui`: a hermetic browser harness that asserts what the browser *paints*
  (placement by level, typography, filter latency, focus, motion, RTL and fixed-header occlusion).
  It uses its own free port; set `SIGNAL_UI_REVIEW_PORT` only to request a specific free port.
- `npm run build:demo`: read-only public demo · `npm run check:demo-bundle`: excludes app/API/write paths

CI runs lint, typecheck, test, build, build:demo and check:demo-bundle on every PR (`.github/workflows/checks.yml`).

## Structure

```
src/
├── pages/            Feed, Preferences, InterestSelection, Calibration, Results, Account,
│                     Login, Signup, Onboarding (/welcome) · ops: Sources, Debug, LlmQa
├── components/
│   ├── feed/         signal/: SignalFeedView, layout/motion/story models, ResultsStrip;
│   │                 shared storyModel, focusModel, queueMotion and their tests;
│   │                 DecisionBadge, DeskVoice, FeedbackControls, SourceMeta, decisionConfig, clusterModel
│   ├── interests/    InterestPicker, InterestsManager, CatalogSearch, FollowChip, EventPresetControls
│   ├── preferences/  TopicCard, LearnedAdjustmentsPanel
│   ├── results/      ResultCard, DayHeading, grouping/format/relevance models
│   ├── debug/        DebugArticleCard, FactsTracePanel, ReasoningTrace, ClusterEvidence, ShadowComparisonPanel
│   ├── ops/          IngestionPanel, SchedulerPanel, NotificationsPanel, SourceToggleCard, HealthCard, BenchmarkPanel
│   ├── shell/        ProductShell, ProductHeader, AccountMenu, MastheadSlot;
│   │                 Ops AppShell, Masthead, MobileNav, ProductNav, OpsNav; session/role guards
│   ├── signal-ui/    scoped tokens, Assistant/Karantina, wordmark and signal-strength mark
│   ├── shared/       DeskIntro, EmptyState, ErrorState, PageHeader, …
│   └── ui/           shadcn/Radix primitives
├── context/          AppContext (the data layer), AuthContext, onboarding flow, data routing
├── api/              client + normalizers (the backend contract)
├── engine/           the frozen legacy relevance engine (local mode only) + taxonomy reach
├── data/             mock data, the demo profiles, the generated taxonomy reach export
└── main.jsx          routes: public auth → session → product AppShell / admin ops AppShell
```

`/sources`, `/debug`, `/llm-qa` and `/calibration` load on demand through `React.lazy`, each
inside `components/shell/LazyBoundary` (loading status, and a reload prompt when the chunk fails
to load or the screen crashes while rendering; only ops also sees the raw error).

`context/`, `api/`, `engine/` and `data/` form the data contract, and UI components never
modify them. `src/data/taxonomyReach.generated.json` is generated by
`backend/scripts/generate_taxonomy_export.py`, and a backend test guards its freshness.
`src/data/userProfiles.js` is pinned to `docs/fixtures/profile_parity.json` by a drift test.
All UI strings are Hebrew; use logical (RTL-safe) Tailwind utilities.
