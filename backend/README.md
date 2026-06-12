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

### Feedback actions

Valid `action` values for `POST /api/feedback`:
- `more_like_this`
- `not_interested`
- `never_show`
- `mute_source`
- `always_notify`

Feedback is stored in SQLite (PR 6). It does not mutate profiles yet.

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

## Ingestion (PR 7 + PR 7.1)

Real RSS ingestion is available for English basketball sources (Eurohoops, Sportando).

```bash
# Trigger ingestion via the API:
curl -X POST http://127.0.0.1:8000/api/ingest/run
# Or a single source:
curl -X POST "http://127.0.0.1:8000/api/ingest/run?source_id=eurohoops"
# Check quality of what was ingested:
curl http://127.0.0.1:8000/api/ingest/quality
```

Articles are classified with a deterministic keyword classifier and deduplicated by URL.
New articles appear in `/api/articles` and flow through the same relevance engine as seed articles.

**Quality guardrails (PR 7.1):** Eurohoops serves content in 10+ languages via URL paths
(`/tr/`, `/es/`, `/el/`, etc.); non-English paths are blocked. The classifier now correctly
distinguishes EuroCup from EuroLeague, infers Israeli Basketball League from Maccabi entity +
context keywords, and downgrades generic news (no tracked entity, no event keyword) to
`importance = "low"`.

See `docs/RSS_INGESTION.md` and `docs/RSS_QUALITY_GUARDRAILS.md` for full details.

## Current limitations

- **Hebrew source RSS.** Walla, Sport5, ONE require scraping adapters — not yet implemented.
- **No scheduler.** Ingestion is triggered manually via `POST /api/ingest/run`. A scheduler is planned for PR 8.
- **Classifier is keyword-only.** No LLM, no NLP. Entity detection is limited to Maccabi Tel Aviv and Deni Avdija.
- **No translation.** `translated_title` is always `None` for RSS articles.
- **No fuzzy dedup.** Duplicate headlines from different sources are not merged. URL-based dedup only.
- **Feedback is stored but not applied.** `POST /api/feedback` records events in SQLite; they do not yet mutate profiles.
- **No authentication.** All profiles are publicly accessible by user_id.
- **No clustering.** Articles are not grouped; `cluster_id` exists in the model only.
- **`skipped_filtered` not persisted.** The count of URL/language-filtered items is returned in the live API response but not stored in `ingestion_runs` (would require a DB migration).

## Next step (PR 8)

- Hebrew source adapter (Walla or ONE if RSS exists)
- Scheduled ingestion (APScheduler or cron endpoint)
- Fuzzy title dedup / clustering
- Feedback → profile mutation (`never_show` → hidden event rule)
