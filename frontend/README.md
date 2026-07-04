# Signal Sports — Frontend

A personalized, Hebrew-first sports news intelligence feed that surfaces only the
stories worth a specific user's attention. React 18 + Vite 6, JavaScript/JSX.

The UI runs on the **"Court Vision" design system** — a premium dark, RTL-first
product with a signal-rail decision system and a product-vs-console split.
See [`../docs/FRONTEND_DESIGN_SYSTEM.md`](../docs/FRONTEND_DESIGN_SYSTEM.md).

## Getting started

```bash
npm install
npm run dev
```

Opens on [http://localhost:5173](http://localhost:5173) (Vite picks the next free
port if taken).

## Data modes

The app runs in two modes via `VITE_DATA_MODE` (in `.env.local`):

- `local` (default) — mock data + the in-browser relevance engine, no backend.
- `backend` — fetches from the FastAPI backend (`VITE_API_BASE_URL`, default
  `http://127.0.0.1:8000`).

```bash
# local mode
VITE_DATA_MODE=local npm run dev
# backend mode (start the backend first — see ../backend)
VITE_DATA_MODE=backend npm run dev
```

## Scripts

- `npm run dev` — start the dev server
- `npm run build` — production build
- `npm run preview` — preview the production build
- `npm run test` — Vitest (node environment; engine, API, and config/module tests)
- `npm run lint` — ESLint
- `npm run typecheck` — `tsc` over `jsconfig.json` (checkJs)

## Structure

```
src/
├── components/
│   ├── ui/           shadcn/Radix primitives
│   ├── shared/       EmptyState, ErrorState, LoadingSkeleton, StatCard, …
│   ├── shell/        AppShell, ProductNav, OpsNav, DataModeBadge, ProfileSwitcher
│   ├── feed/         ArticleCard, SignalRail, DecisionBadge, RelevanceReason, …
│   ├── ops/          SchedulerPanel, IngestionPanel, BenchmarkPanel, HealthCard
│   ├── debug/        DebugArticleCard, ProfileComparisonTable, ReasoningTrace
│   └── preferences/  TopicCard
├── context/          AppContext — the single data layer (frozen)
├── api/              client + normalizers (frozen contract)
├── engine/           relevance/calibration engines (local mode; frozen)
├── data/             mock data (frozen)
├── pages/            Feed, Preferences, Calibration, Results, Sources, Debug, LlmQa
├── index.css         design tokens
└── main.jsx          routes (product / ops AppShell groups)
```

`context/`, `api/`, `engine/`, and `data/` are the data contract — UI components
never modify them. The `useApp()` hook is the only bridge between pages and data.
