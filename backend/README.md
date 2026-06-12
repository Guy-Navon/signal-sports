# Signal Sports Backend

FastAPI backend for Signal Sports. Implements the relevance engine, user profiles, article feed, and feedback API.

## Stack

- Python 3.11+
- FastAPI 0.100+
- Pydantic v2
- SQLAlchemy 2.0 + SQLite (added in PR 6)
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
| GET | `/api/articles` | List all seeded articles |
| GET | `/api/articles/{article_id}` | Get a specific article |
| GET | `/api/feed/{user_id}` | Scored feed (hidden articles excluded, sorted by decision+date) |
| GET | `/api/debug/feed/{user_id}` | Full scored feed including hidden, with reasoning |
| POST | `/api/feedback` | Submit a feedback event |
| GET | `/api/feedback/{user_id}` | List all feedback events for a user |
| GET | `/api/calibration/headlines` | List calibration headlines |

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

## Current limitations

- **No real article ingestion.** Articles are seeded manually. No RSS/scraping adapters yet.
- **Feedback is stored but not applied.** `POST /api/feedback` records events in SQLite; they do not yet mutate profiles.
- **No authentication.** All profiles are publicly accessible by user_id.
- **No clustering.** Articles are not grouped; cluster-related fields exist in the model only.
- **No translation engine.** `translated_title` / `original_title` fields exist but translation is not performed.

## Next step (PR 7)

Options:
- **PR 7a: First real source adapter** — Sport5 RSS or Eurohoops scraper. With SQLite in place, new articles survive restarts and deduplication against stored history is possible.
- **PR 7b: Feedback → profile mutation** — `never_show` feedback creates a `hidden` event rule for that article's event type in the matching topic.
