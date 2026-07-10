# Signal Sports Backend

FastAPI backend for Signal Sports. Implements the relevance engine, user profiles, article feed, and feedback API.

## Stack

- Python 3.11+
- FastAPI 0.100+
- Pydantic v2
- SQLAlchemy 2.0 + SQLite (added in PR 6)
- feedparser 6.0+ for RSS ingestion (added in PR 7)
- pytest + httpx for tests

## Setup

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\pip install -r requirements.txt
# macOS / Linux
.venv/bin/pip install -r requirements.txt
```

## Run the server

```bash
# Windows
.venv\Scripts\uvicorn app.main:app --reload

# macOS / Linux
.venv/bin/uvicorn app.main:app --reload
```

Server starts at `http://localhost:8000`.

Interactive docs: `http://localhost:8000/docs`

## Run tests

```bash
# Windows
.venv\Scripts\python -m pytest tests/ -v

# macOS / Linux
.venv/bin/python -m pytest tests/ -v
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health check |
| GET | `/api/profiles` | List all user profiles |
| GET | `/api/profiles/{user_id}` | Get a specific profile |
| GET | `/api/articles` | List all articles (seed + ingested) |
| GET | `/api/articles/{article_id}` | Get a specific article |
| GET | `/api/feed/{user_id}` | Scored feed (hidden articles excluded, sorted by decision+date) |
| GET | `/api/debug/feed/{user_id}` | Full scored feed including hidden, with reasoning |
| POST | `/api/feedback` | Submit a feedback event |
| GET | `/api/feedback/{user_id}` | List all feedback events for a user |
| GET | `/api/calibration/headlines` | List calibration headlines |
| GET | `/api/ingest/sources` | List configured RSS ingest sources |
| POST | `/api/ingest/run` | Run ingestion (all sources or `?source_id=X` for one) |
| GET | `/api/ingest/runs` | Recent ingestion run records |
| GET | `/api/ingest/quality` | Quality summary for all ingested RSS articles (sport/league/event breakdowns, questionable list) |
| GET | `/api/classify/status` | Current LLM classification provider state |
| POST | `/api/classify/backfill` | Reclassify existing articles with LLM (`source_id`, `limit`, `dry_run`, `force`) |
| GET | `/api/translations/status` | Translation provider state (preserved, disabled by default) |
| POST | `/api/translations/backfill` | Translate untranslated article titles (disabled by default) |

### Feedback actions

Valid `action` values for `POST /api/feedback`:
- `more_like_this`
- `not_interested`
- `never_show`
- `mute_source`
- `always_notify`

Feedback is stored in SQLite and drives derived learned adjustments at scoring time (issue #34; see `docs/FEEDBACK_LEARNING.md`).

## Data model

All models are defined in `app/models/`. Key types:

- `Article` — scored content item
- `UserProfile` — user with topics, muted sources/topics, followed entities
- `TopicPreference` — sport + leagues + entities + eventRules + entityEventRules + mode
- `DecisionResult` — decision (hidden/low_feed/feed/high_feed/push) + reasoning chain
- `ScoredArticle` — article + decision + reasoning
- `FeedbackEvent` — user × article × action × timestamp
- `CalibrationHeadline` — synthetic headline for preference calibration

## Relevance engine

`app/services/relevance_engine.py` is a faithful Python port of the frontend engine at `src/engine/relevanceEngine.js`.

Scoring pipeline:
1. Check disabled sources
2. Check muted sources (profile preference)
3. Check muted topics (by sport/league)
4. Find matching profile topics (OR logic: sport, leagues, or entities)
5. Score against each matching topic; take best decision
6. Return decision + full reasoning chain

Topic modes: `all`, `followed_entities_only`, `titles_only`, `high_importance_only`, `major_only`, `muted`

Push discipline: importance boost is hard-capped at `high_feed`. Push requires an explicit `eventRules` or `entityEventRules` declaration.

**Topic scope guards (PR 4.1):** Each `TopicPreference` has an optional `scope` field that controls which articles it matches:
- `entity` — match only if `article.entities ∩ topic.entities` is non-empty (prevents sport-wide over-matching for team/person topics)
- `league` — match only if `article.league ∈ topic.leagues`
- `league_group` — same as `league`, for groups of related leagues
- `sport` — match only if `article.sport == topic.sport` (used with restrictive modes)
- `None` — legacy OR matching (backward compat for calibration-generated topics)

This ensures the Maccabi topic only fires for Maccabi articles, the NBA topic only fires for NBA articles, and so on — even when multiple basketball topics coexist in the same profile.

## Seed data

Located in `app/seed/`. Loaded on startup via FastAPI lifespan.

- `seed_profiles.py` — Guy (basketball power user) + Casual Deni Fan
- `seed_articles.py` — 16 representative articles covering all test scenarios
- `seed_sources.py` — 7 news sources (Sport5, ONE, Walla, Israel Hayom, Ynet, Sportando, Eurohoops)
- `seed_calibration.py` — 16 synthetic calibration headlines

## Data persistence

All data is persisted in SQLite at `backend/data/signal_sports.db` (created automatically on first run). Tables are seeded from `app/seed/` on startup if empty; restarting the server does not wipe data.

To reset to a clean state, stop the server and delete `data/signal_sports.db`.

See `docs/SQLITE_PERSISTENCE.md` for full details.

## Ingestion (PR 7 + PR 7.1 + PR 8 + PR 10 + PR 11 + post-QA fixes)

Two Hebrew sources are active by default. English sources are disabled (post-MVP).

| source_id           | display_name       | language | status    |
|---------------------|--------------------|----------|-----------|
| `walla_sport`       | וואלה ספורט        | he       | active    |
| `israel_hayom_sport`| ישראל היום ספורט   | he       | active    |
| `eurohoops`         | Eurohoops          | en       | disabled  |
| `sportando`         | Sportando          | en       | disabled  |

```bash
# Trigger ingestion via the API:
curl -X POST http://127.0.0.1:8000/api/ingest/run
# Or a single source:
curl -X POST "http://127.0.0.1:8000/api/ingest/run?source_id=walla_sport"
# Check quality of what was ingested:
curl http://127.0.0.1:8000/api/ingest/quality
```

The `POST /api/ingest/run` response includes per-source timing fields: `fetch_ms`, `total_ms`,
`llm_avg_ms`, `llm_p95_ms`, `llm_attempts`, `llm_successes`, `llm_fallback_connect_error`,
`llm_fallback_timeout_or_parse`, `llm_fallback_low_confidence`.

**Classification pipeline:**

1. **Deterministic keyword classifier** — always runs for all sources. Detects sport, league, entities, event type from title + subtitle (RSS `<description>` HTML-stripped, truncated to 500 chars).
2. **Source URL category hints** (`source_hints.py`) — Israel Hayom URLs like `/sport/israeli-basketball/` are pre-classified as basketball before the deterministic step even runs.
3. **LLM classification** (Hebrew broad sources only, when `CLASSIFICATION_PROVIDER != disabled`) — Gemini or Ollama provider adds entity-to-league inference and proper noun resolution. 7 guardrails merge LLM with deterministic result.
4. **`normalize_league_sport_compatibility()`** — universal safety net called for all paths; no article can be stored with an impossible sport/league combination (e.g., `sport=football, league=EuroLeague`).

**Quality guardrails:** Language + URL filtering; EuroCup vs EuroLeague disambiguation; Israeli Basketball League context inference; generic news importance downgrade; title_win hardening (loose Hebrew win verbs require championship context); LLM title_win evidence check; league-sport compatibility check.

See `docs/RSS_INGESTION.md`, `docs/RSS_QUALITY_GUARDRAILS.md`, `docs/HEBREW_RSS_SOURCE.md`, and `docs/LLM_CLASSIFICATION.md` for full details.

### Classification endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/classify/status` | Current provider, model, ready state |
| POST | `/api/classify/backfill` | Reclassify existing articles (`source_id`, `limit`, `dry_run`, `force`) |

## Current limitations

- **Scheduler is opt-in.** Ingestion runs manually via `POST /api/ingest/run` or on a loop with `INGESTION_SCHEDULER_ENABLED=true` (default false).
- **LLM classification not benchmarked at scale.** The deterministic classifier runs by default (`CLASSIFICATION_PROVIDER=disabled`). LLM is opt-in; quality must be validated with Ollama + Qwen before relying on it. Timing fields are now instrumented in the `POST /api/ingest/run` response.
- **No translation.** `translated_title` is always `None` for Hebrew RSS articles. The translation module is intact but disabled by default (`TRANSLATION_PROVIDER=disabled`). Post-MVP.
- **No fuzzy dedup.** Duplicate headlines from different sources are not merged. URL-based dedup only.
- **Feedback drives derived learning (#34).** Events persist in SQLite and produce bounded learned adjustments at scoring time (explicit > learned > calibration); explicit rules are never silently mutated. See `docs/FEEDBACK_LEARNING.md`.
- **Authentication is live (User Platform).** Email/password accounts with HttpOnly cookie sessions (`/api/auth/*`); the consumer product uses the session-derived `/api/me/*` surface; explicit `{user_id}` and ops routes are the fail-closed admin/QA surface (`require_admin`; `ALLOW_INSECURE_AUTH_BYPASS=true` reopens them for local dev only). See `docs/USER_PLATFORM.md`.
- **No clustering.** Articles are not grouped; `cluster_id` exists in the model only.
- **`skipped_filtered` not persisted.** The count of URL/language-filtered items is returned in the live API response but not stored in `ingestion_runs` (would require a DB migration).
- **Sport5 / ONE have no public RSS.** These sources require category page adapters or scraping — not yet implemented.

## Next steps

1. LLM classification benchmark — Ollama + `qwen2.5:3b-instruct`; check `llm_avg_ms`, `llm_p95_ms`, and `sport=unknown` count
2. Expand entity normalization map (`entity_normalizer.py`) based on benchmark findings
3. Scheduled ingestion (APScheduler or cron endpoint)
4. Fuzzy title dedup / clustering
5. Feedback → profile mutation (`never_show` → hidden event rule)
6. Additional Hebrew sources (ONE via category page adapter — preferred; no public RSS)
