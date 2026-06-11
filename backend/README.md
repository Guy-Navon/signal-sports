# Signal Sports Backend

FastAPI backend for Signal Sports. Implements the relevance engine, user profiles, article feed, and feedback API.

## Stack

- Python 3.11+
- FastAPI 0.100+
- Pydantic v2
- In-memory data store (no database in PR 4)
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
| GET | `/api/calibration/headlines` | List calibration headlines |

### Feedback actions

Valid `action` values for `POST /api/feedback`:
- `more_like_this`
- `not_interested`
- `never_show`
- `mute_source`
- `always_notify`

Feedback is stored in-memory only. It does not mutate profiles in PR 4.

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

**Known engine quirk (matches frontend behavior):** Topics match articles via OR logic (sport OR league OR entity). The `maccabi_tel_aviv_basketball` topic has `sport: "basketball"`, so it matches ALL basketball articles. This causes non-Maccabi EuroLeague events to resolve via Maccabi's event rules (e.g., `major_transfer → major_signing alias → push`). This is intentional faithfulness to the frontend; a future PR can add topic scope guards.

## Seed data

Located in `app/seed/`. Loaded on startup via FastAPI lifespan.

- `seed_profiles.py` — Guy (basketball power user) + Casual Deni Fan
- `seed_articles.py` — 16 representative articles covering all test scenarios
- `seed_sources.py` — 7 news sources (Sport5, ONE, Walla, Israel Hayom, Ynet, Sportando, Eurohoops)
- `seed_calibration.py` — 16 synthetic calibration headlines

## Current limitations

- **In-memory store only.** All data resets on server restart. No SQLite/Postgres yet.
- **No real article ingestion.** Articles are seeded manually. No RSS/scraping adapters yet.
- **Feedback is stored but not applied.** `POST /api/feedback` records events; they do not yet mutate profiles.
- **No authentication.** All profiles are publicly accessible by user_id.
- **No clustering.** Articles are not grouped; cluster-related fields exist in the model only.
- **No translation engine.** `translated_title` / `original_title` fields exist but translation is not performed.
- **Frontend not connected.** The frontend still uses its own local-state engine. Integration is PR 5.

## Next step (PR 5)

Connect the frontend to the backend:
- Replace `AppContext` local scoring with `fetch("/api/feed/{userId")`
- Replace mock article data with `GET /api/articles`
- Replace profile data with `GET /api/profiles`
- Keep the frontend engine as fallback during transition
- Add a first real source adapter (Sport5 RSS or Eurohoops scraper)
