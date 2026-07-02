# Frontend ↔ Backend Integration

## Overview

PR 5 connects the React frontend to the FastAPI backend while keeping the existing local
mock engine as a safe fallback. The app can run in two data modes controlled by an environment
variable. In `local` mode the app behaves exactly as before PR 5 (no backend required). In
`backend` mode all feed data and profiles come from the API and the backend performs scoring.

---

## Data Modes

| Mode | Source of profiles | Source of feed / debug | Who scores | Calibration / sandbox |
|------|--------------------|------------------------|-----------|----------------------|
| `local` | `userProfiles.js` | `mockArticles.js` + frontend engine | Frontend (`relevanceEngine.js`) | Fully local |
| `backend` | `GET /api/profiles` | `GET /api/feed/{userId}` / `GET /api/debug/feed/{userId}` | Backend (`relevance_engine.py`) | Headlines from `GET /api/calibration/headlines`; inference and sandbox apply remain local-only |

---

## Environment Variables

Create a `.env.local` file inside the `frontend/` directory (git-ignored):

```env
VITE_DATA_MODE=backend
VITE_API_BASE_URL=http://127.0.0.1:8000
```

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_DATA_MODE` | `local` | `local` or `backend`. Defaults to `local` so the app works with no backend running. |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Base URL of the FastAPI backend. |

If `VITE_DATA_MODE` is missing or set to anything other than `backend`, the app runs in
`local` mode automatically — it will not break if the backend is not running.

---

## How to Run

### Backend

```bash
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive API docs: http://127.0.0.1:8000/docs

### Frontend in local mode (default)

```bash
cd frontend
npm run dev
```

No `.env.local` needed. The app uses mock data and the frontend engine.

### Frontend in backend mode

1. Start the backend (see above).
2. Create `frontend/.env.local`:

```env
VITE_DATA_MODE=backend
VITE_API_BASE_URL=http://127.0.0.1:8000
```

3. Start the frontend:

```bash
cd frontend
npm run dev
```

The header badge will show **מצב נתונים: שרת** when backend mode is active.

---

## Architecture

### API Client (`frontend/src/api/client.js`)

Central module for all backend requests. All `fetch` calls go through `apiFetch` which:
- Prefixes every path with `VITE_API_BASE_URL`
- Throws a descriptive error on network failure or non-2xx response
- Parses the FastAPI `detail` field from error responses

Exported functions:

| Function | Endpoint |
|----------|----------|
| `getHealth()` | `GET /health` |
| `getProfiles()` | `GET /api/profiles` |
| `getProfile(userId)` | `GET /api/profiles/{userId}` |
| `getArticles()` | `GET /api/articles` |
| `getFeed(userId)` | `GET /api/feed/{userId}` |
| `getDebugFeed(userId)` | `GET /api/debug/feed/{userId}` |
| `submitFeedback(payload)` | `POST /api/feedback` |
| `getCalibrationHeadlines()` | `GET /api/calibration/headlines` |
| `getIngestSources()` | `GET /api/ingest/sources` |
| `runIngestion(sourceId?)` | `POST /api/ingest/run` or `POST /api/ingest/run?source_id=X` |
| `getIngestRuns(limit?)` | `GET /api/ingest/runs?limit=N` |
| `getIngestQuality()` | `GET /api/ingest/quality` |
| `getSchedulerStatus()` (PR 13) | `GET /api/ingest/scheduler/status` |
| `runSchedulerNow()` (PR 13) | `POST /api/ingest/scheduler/run-now` (409 when a run is active) |
| `getSourceHealth()` (PR 13) | `GET /api/ingest/source-health` |
| `setSourceEnabled(sourceId, enabled)` (PR 13.1) | `PATCH /api/ingest/sources/{id}` — runtime source toggle |
| `backfillTranslations({ limit?, sourceId?, dryRun? })` | `POST /api/translations/backfill` |

`isIngestionBusyError(err)` (PR 13, `client.js`) detects the shared-ingestion-lock 409
(`ingestion_already_running`) so the UI can show "ייבוא פעיל כרגע" instead of a raw error.
Note: `POST /api/ingest/run` can also return 409 since PR 13 — manual, scheduled, and
run-now ingestion share one process-level lock.

### Scheduler status panel (PR 13, `SchedulerStatusPanel.jsx`)

Rendered on the Sources page in backend mode only (hidden in local mode; the existing
IngestionPanel already explains how to enable backend mode). Shows the "סטטוס ייבוא אוטומטי"
section: scheduler enabled/interval/next-run/last-run/last-error from
`GET /api/ingest/scheduler/status`, a "הרץ עכשיו" button (disabled with "ייבוא פעיל כרגע"
while a run is active or after a 409), and per-source health cards from
`GET /api/ingest/source-health` — freshness badge (תקין / מיושן / לא רץ עדיין / כבוי / שגיאה),
RSS/Scraping type label, and a "פיילוט" badge for `is_pilot` sources (Sport5).
Each health card also has a פעיל/כבוי toggle (PR 13.1) calling `setSourceEnabled()` — this is
how the Sport5 pilot is enabled/disabled from the UI; the override persists in the backend DB.
Normalizers: `normalizeSchedulerStatusFromApi`, `normalizeSourceHealthFromApi`,
`freshnessBadge`, `sourceTypeLabel` in `normalizers.js`.

### RSS-only article filter

`GET /api/articles`, `GET /api/feed/{userId}`, and `GET /api/debug/feed/{userId}` all return
only articles whose `id` starts with `rss_` — i.e., articles ingested via the RSS pipeline.
Seed articles (ids like `article_001`) are stored in the database for testing and single-item
lookups (`GET /api/articles/{id}`) but do not appear in the feed or article list. This ensures
the UI shows only real, dynamically fetched content.

The filter lives in `article_repository.get_rss_articles()` which uses a SQL `LIKE 'rss_%'`
predicate. Backend tests that need feed/scoring coverage use the `rss_seeded` pytest fixture
(in `tests/conftest.py`) which inserts `rss_`-prefixed copies of the key seed articles.

---

### Normalizers (`frontend/src/api/normalizers.js`)

The backend returns snake_case field names (Python convention). The frontend UI and engine
use camelCase throughout. Normalizers translate once at the API boundary so no component
ever needs to know about the backend naming style.

| Normalizer | Input | Output |
|-----------|-------|--------|
| `normalizeArticleFromApi` | `Article` (snake_case) | article object (camelCase) |
| `normalizeProfileFromApi` | `UserProfile` (snake_case) | profile object (camelCase) |
| `normalizeScoredArticleFromApi` | `ScoredArticle` (nested) | flat feed item with `score` sub-object |
| `normalizeCalibrationHeadlineFromApi` | `CalibrationHeadline` (snake_case) | headline object (camelCase) |

Key mapping: the backend field `matched_event_rule` normalizes to `matchedRule` (not
`matchedEventRule`) to match the shape that the frontend engine has always returned and
that `Debug.jsx` reads via `item.score?.matchedRule`.

### AppContext (`frontend/src/context/AppContext.jsx`)

`AppContext` detects `VITE_DATA_MODE` at module load time. Both modes share the same
React context shape so no consumer component needs to branch on the mode.

**Local mode:** identical to pre-PR-5. All existing behavior is preserved.

**Backend mode:**
- On mount: loads profiles from `GET /api/profiles`
- On `activeProfileId` change: loads `GET /api/feed/{userId}` and `GET /api/debug/feed/{userId}` in parallel
- `addFeedback`: records locally **and** posts to `POST /api/feedback` for actions the backend accepts (`more_like_this`, `not_interested`, `never_show`, `mute_source`, `always_notify`). The action `less_like_this` (used in `FeedCard`) is tracked locally only.
- `refreshFeed()`: re-triggers the feed fetch in backend mode
- `refreshProfiles()`: re-fetches the profile list in backend mode
- Loading state exposed via `isLoading`
- Errors exposed via `apiError`

**Comparison tab** in the Debug page always uses the local engine for cross-profile
comparison. This is intentional — computing per-profile comparisons requires running
the scoring engine against all profiles, which the backend does not currently support
as a single request.

**Sandbox profile** is local-only in both modes. Calibration inference and the "apply to
sandbox" flow remain entirely in the frontend. There is no backend endpoint for profile
mutation yet.

### UI changes

- **Data mode badge** in the top-left header: small pill showing "מצב נתונים: שרת" (blue)
  or "מצב נתונים: מקומי" (gray). Spinning refresh icon while loading.
- **Error banner**: if backend mode has an API error, a red banner appears below the header
  with the error detail, the expected backend URL, and a "נסה שוב" retry button.
- **Ingestion panel** on the Sources page: shows RSS ingestion controls in backend mode.
  In local mode, shows a disabled message with a hint on how to enable backend mode.

### Ingestion panel (`IngestionPanel.jsx`)

Located at `src/components/ingestion/IngestionPanel.jsx`. Rendered at the top of the
Sources page.

**Backend mode:** Shows:
1. Source selector buttons (כל המקורות, Eurohoops, Sportando, וואלה ספורט) — populated from
   `GET /api/ingest/sources`.
2. "הרץ ייבוא עכשיו" button — calls `POST /api/ingest/run` (or with `?source_id=X`).
3. Result summary after a run — per-source breakdown of fetched/inserted/skipped/failed.
4. Success message: "הייבוא הסתיים — נוספו X כתבות חדשות" or "...לא נוספו כתבות חדשות".
5. Recent runs list (last 5, from `GET /api/ingest/runs`).
6. "איכות הסיווג" toggle — lazy-loads `GET /api/ingest/quality` and shows sport breakdown,
   event type breakdown, and top 5 questionable articles.

After a successful run, `onFeedRefresh` is called (wired to `AppContext.refreshFeed()`), so
the feed and debug view update with newly ingested articles without a full browser reload.

**Local mode:** Shows a disabled card with the text:
- "ייבוא RSS זמין רק במצב שרת"
- "מצב מקומי פעיל — כדי לראות RSS אמיתי הפעל VITE_DATA_MODE=backend"

---

## What Remains Local-Only

| Capability | Why it stays local |
|-----------|-------------------|
| Calibration inference (`calibrationEngine.js`) | No backend endpoint for preference inference yet |
| Sandbox profile apply (`draftToProfile.js`) | No backend profile mutation endpoint yet |
| Profile comparison tab | Requires multi-profile scoring in one request; backend not wired for this |
| Demo sources list toggle (bottom of Sources page, `feedSources.js`) | Local demo data only. **Real ingestion sources are no longer local-only:** since PR 13.1 the source-health cards toggle them via `PATCH /api/ingest/sources/{id}`, persisted in the backend `source_overrides` table |
| `less_like_this` feedback | Not in the backend's valid actions set |

---

## Why the Frontend Engine Is Kept

The frontend engine (`relevanceEngine.js`) is not removed in PR 5 for two reasons:

1. **Local mode fallback**: running without a backend should still produce a full working
   experience. Real data ingestion (RSS, scraping) is a later milestone.
2. **Engine parity testing**: having both engines output decisions from the same mock data
   makes it easy to catch divergences before they affect production data.

The frontend engine can be removed once the backend is the sole data source and local mode
is no longer needed.

---

## Validation Checklist

After starting both servers with `VITE_DATA_MODE=backend`:

- [ ] Header badge shows "מצב נתונים: שרת"
- [ ] Profiles load from backend (Guy + Casual Deni Fan in the switcher)
- [ ] Feed loads for Guy — Maccabi negotiation articles appear with `push`
- [ ] Switching to Casual Deni Fan → feed changes (Hornets/Wizards disappears)
- [ ] Debug tab shows all articles including hidden ones
- [ ] Real Madrid EuroLeague transfer article shows `matchedTopic = euroleague`, `decision = high_feed` (not `push`)
- [ ] Thumbs up / thumbs down sends `POST /api/feedback` (visible in backend logs)
- [ ] Stopping the backend and reloading shows the red error banner
- [ ] "נסה שוב" button retries the feed fetch
- [ ] Setting `VITE_DATA_MODE=local` and reloading restores local mode, no backend required

---

## Backend Tests

```bash
cd backend
.venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: **1076 tests pass** (as of PR 13.1 — see `docs/CURRENT_PROJECT_STATE.md` for the authoritative current count). Run all tests: `.venv\Scripts\python.exe -m pytest tests/ -q`.

## Frontend Tests

```bash
cd frontend
npm run test
npm run lint
npm run build
```

New test files added in PR 5:
- `src/api/normalizers.test.js` — 4 describe blocks, covers all four normalizers
- `src/api/client.test.js` — covers success, HTTP error, network error, feedback POST

---

## What Changed in PR 6

PR 6 replaced the in-memory data store with SQLite persistence (SQLAlchemy 2.0).

- Articles, profiles, sources, calibration headlines, and feedback events are all stored in `backend/data/signal_sports.db`.
- Feedback events survive backend restarts.
- New endpoint: `GET /api/feedback/{user_id}` — returns all feedback events for a user.
- 18 new persistence tests added; backend test suite was 86 tests at that point (historical PR 6 count).

See `docs/SQLITE_PERSISTENCE.md` for details on the database design, seed-on-empty behavior, test isolation, and reset instructions.

## Next Step: PR 7

With SQLite in place, the next options are:

1. **PR 7a: First real source adapter** — Sport5 RSS or Eurohoops scraper. New articles will be stored in SQLite and survive restarts, enabling meaningful deduplication.
2. **PR 7b: Feedback → profile mutation** — `never_show` feedback creates a `hidden` event rule in the matching topic. Requires in-place profile updates via the repository.
