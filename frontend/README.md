# Signal Sports Frontend

The Hebrew-first, RTL product UI and admin console for Signal Sports. Built with
React 18, Vite 6, React Router, TanStack Query and Tailwind; JavaScript/JSX is
type-checked through `jsconfig.json`.

Consumer pages and the public read-only demo use Signal UI: a sticky navy
header, a lead block for a push, compact feed rows, a side column and a results
strip. The product supports white, soft and dark backgrounds; the public demo
has a persistent light/dark toggle. Ops retains its own console shell. See the
[design system](../docs/FRONTEND_DESIGN_SYSTEM.md) and
[project state](../docs/CURRENT_PROJECT_STATE.md).

## Local setup

Use Node.js 22 (the version used in CI). Run from `frontend/`:

```powershell
npm ci
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
# Edit .env.local for the desired data mode.
npm run dev
```

On macOS/Linux copy `.env.example` to `.env.local` only if the latter does not
already exist. Browse
[http://localhost:5173](http://localhost:5173). The example selects `backend`
mode, so start the [backend](../backend/README.md) first. For a frontend-only
preview, set `VITE_DATA_MODE=local` instead.

The dev server binds to `127.0.0.1:5173` with `strictPort: true`; an occupied port
fails startup. The same-origin proxy and Tailscale Serve chain depend on that
port. See [mobile/remote access](../docs/MOBILE_REMOTE_ACCESS.md).

## Data modes

| Mode | Data and behavior |
| --- | --- |
| `VITE_DATA_MODE=backend` | Real API, sessions, onboarding, personalized feed, results, feedback and admin operations. The backend owns scoring and authorization. |
| `VITE_DATA_MODE=local` (default when unset) | Mock articles/results/profiles in `src/data/`, scored in the browser by the frozen legacy JS engine. No backend or login required. |
| Public read-only demo | Separate `demo.html` entry and build, reading exported static snapshots. Independent of the app's data-mode setting. |

In backend mode, relative `/api/...` and `/health` requests go through Vite's
proxy to `http://127.0.0.1:8000`. `SIGNAL_API_PROXY` overrides the dev proxy target
for an isolated stack. Leave `VITE_API_BASE_URL` unset for same-origin access;
set it only for deliberate direct cross-origin calls, with matching backend
CORS/CSRF configuration. Vite substitutes `VITE_*` settings at build time:
restart development after changes and rebuild for production. Never put secrets
in frontend environment variables.

Local mocks, profiles and the legacy engine load through `context/localDemo.js`
in a separate chunk that backend sessions do not fetch. Local mode is a UI
preview, not a parity implementation of current backend intelligence or account
flows. Debug's profile comparison tab is available only in local mode.

## Product routes and accounts

| Routes | Purpose |
| --- | --- |
| `/` | Personalized feed with importance/league/source filters, clustered stories, feedback and a results strip |
| `/results` | Personalized results board, followed-team history and available game details |
| `/preferences/:tab?` | Four personalization tabs, including interests, calibration and learned adjustments |
| `/interests`, `/calibration` | Compatibility redirects into Preferences |
| `/account` | Account settings, password and Google linking/unlinking/deletion flows |
| `/welcome` | Signed-in onboarding, outside the product shell |
| `/login`, `/signup`, `/verify-email`, `/forgot-password`, `/reset-password` | Public authentication and email-link flows |
| `/sources`, `/debug`, `/llm-qa` | Admin-only ops console in enforced backend sessions |

`AuthProvider` bootstraps the backend session before authenticated data loads.
`RequireSession` guards product routes and `RequireOpsRole` guards ops. Ordinary
users read their own `/api/me/*` data; admin view-as state is separate. Local and
explicit backend-bypass modes retain the demo access behavior.

Signup visibility, invitations and Google availability come from backend session
configuration. Password signup requires email verification; recovery also uses
email. Configure the mailer and OAuth credentials on the backend, as described
in its [README](../backend/README.md#accounts-and-configuration). For Google,
browse `localhost` when that is the registered callback hostname.

Ops screens load on demand with `React.lazy` and `LazyBoundary`, which supplies
loading and reload/error states. Calibration is hosted inside Preferences.

## Results and box scores

The board and feed strip share result models. The general past-game stream is
limited to a rolling 72 hours, including expiration of cached responses. Directly
followed teams have a separate history of up to four latest finals per team and
eight unique games total, without an age limit. Scheduled games use an
independent upcoming window.

Available stored details open from the board or feed strip in a responsive box
score dialog: player statistics, team totals/comparisons, shooting percentages,
leaders and ranks where the provider supplied them. Wide tables support mouse
drag scrolling while retaining text selection. Escape and an outside click/tap
close the dialog; interaction inside preserves it and closing restores focus.

The backend controls relevance, detail authorization and provider support.
`RESULTS_DETAIL_ENABLED` defaults off on a fresh backend; absent detail or player
statistics must remain unavailable rather than being inferred. Chosen result
players affect extra stat lines only. See [Results](../docs/RESULTS.md).

## Public read-only demo

The public demo is separate from local mock mode. It reads static
`demo-data/feed.json`, `results.json` and `meta.json` exported for the `guy`
profile. It shares feed/results views, followed-team history and stored box
scores, has a snapshot-age banner and saves its light/dark choice in browser
storage. It has no login, preferences, admin console or API write path.

Build it from `frontend/`:

```powershell
npm run build:demo
```

A build alone does not supply snapshot data. With a configured backend virtual
environment and a populated database, export from `backend/`:

```powershell
.venv/Scripts/python scripts/export_demo_snapshot.py --out ../frontend/dist-demo/demo-data
```

The exporter opens the database read-only, includes only allowlisted fields and
does not sync providers. It refuses an empty feed by default. The resulting
files are generated artifacts and must stay out of commits.

Then, from `frontend/`:

```powershell
npm run preview:demo
```

Open `http://127.0.0.1:4174/demo.html`. Data reflects the last successful export;
missing details stay unavailable. The hourly Windows publishing task is separate
from browser reads and uses the main local checkout, not a GitHub fetch.
[Deployment](../docs/DEPLOYMENT.md) documents Firebase publishing and
`scripts/demo-publish.ps1`; building or opening a PR does not publish either site.

## Scripts and verification

Run from `frontend/`:

| Command | Purpose |
| --- | --- |
| `npm run dev` | Product dev server on port 5173 |
| `npm run build` / `npm run preview` | Product build in `dist/` / local preview |
| `npm run test` | Vitest in a Node environment: models, components, API/context contracts and drift guards |
| `npm run lint` / `npm run typecheck` | ESLint with zero warnings / TypeScript over `jsconfig.json` |
| `npm run build:demo` / `npm run preview:demo` | Static demo build in `dist-demo/` / preview on port 4174 |
| `npm run check:demo-bundle` | Guard demo isolation; requires both product and demo builds |
| `npm run lab` / `npm run build:lab` / `npm run preview:lab` | Separate visual labs for feed, filters, motion, navigation and results |
| `npm run capture:ui` | Browser checks for painted layout, typography, focus, motion, RTL, filters, header occlusion and results |

`capture:ui` needs Chrome/Chromium (override discovery with `SIGNAL_CHROME_PATH`)
and selects its own free review port (`SIGNAL_UI_REVIEW_PORT` can override it).
Labs and captures are development tools and are excluded from product/demo entries.

[Repository CI](../.github/workflows/checks.yml) uses `npm ci`, then lint,
typecheck, tests (`--maxWorkers=2`), both builds and the demo-bundle guard. The
guard rejects app/API/auth/write-path code in the public demo and calibrates its
markers against the product build. Tests neutralize a developer's data-mode
setting; tests that need a mode declare it explicitly. Browser captures are a
separate local check, not part of that CI job. See also
[image/smoke checks](../.github/workflows/images.yml).

## Source map and conventions

| Path under `src/` | Responsibility |
| --- | --- |
| `pages/` | Product, auth, onboarding and ops route screens |
| `components/feed/` | Shared story/filter/cluster models and Signal feed/results strip |
| `components/results/` | Board, tiles, rows, game-detail dialog and stat/layout models |
| `components/interests/`, `components/preferences/` | Catalog selection and personalization tabs |
| `components/shell/` | Product/ops shells, navigation, account menu and session/role guards |
| `components/signal-ui/` | Scoped tokens, fonts, backgrounds, wordmark and signal-strength mark |
| `components/debug/`, `components/ops/` | Diagnostics and ingestion/scheduler/provider controls |
| `components/shared/`, `components/ui/` | Shared controls and Radix-based primitives |
| `context/`, `api/` | Auth/app data layer, identity routing, client and normalizers |
| `engine/`, `data/` | Frozen local relevance engine, mocks and taxonomy export |
| `demo/`, `lab/` | Separate public snapshot demo and development labs |
| `main.jsx` | Product routing and provider composition |

Keep relevance decisions in the backend and data access in the context/API
layer. `src/data/taxonomyReach.generated.json` is generated by
`backend/scripts/generate_taxonomy_export.py`; a backend test guards freshness.
`src/data/userProfiles.js` is pinned to `docs/fixtures/profile_parity.json` by a
drift test. UI strings are Hebrew; use logical, RTL-safe layout utilities.

Follow the [repository delivery workflow](../AGENTS.md) for branches and PRs.
The [results/demo delivery record](../docs/archive/FEATURE_DELIVERY_2026-11-16.md)
distinguishes merged source from manual demo publishing.
