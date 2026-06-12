# SQLite Persistence

## Why SQLite Before RSS Ingestion

The backend PR 4 used an in-memory Python dict as its data store. That was the right
choice for initial validation: it kept the architecture simple while we proved the
relevance engine produced correct per-user decisions.

But in-memory data has a hard ceiling. Every backend restart wipes all state — articles,
profiles, feedback, calibration headlines. Before adding real RSS ingestion, we need
data to survive restarts. Otherwise:

- Articles scraped in one run are gone when the server restarts.
- Feedback accumulated over days resets to nothing.
- Deduplication cannot work without a stable history of what has already been ingested.
- Future feedback-to-profile mutation cannot apply if feedback is not stored.

SQLite is the right first step: zero infrastructure, a single file, good enough for local
development and MVP validation. It replaces the in-memory store with a proper persistence
layer while keeping the code simple and not requiring Postgres, Docker, or a separate DB
process.

---

## Database File Location

Default production path (relative to the `backend/` working directory):

```
backend/data/signal_sports.db
```

The `data/` directory is created automatically on startup if it does not exist.

The path is controlled by the `DATABASE_URL` environment variable:

```bash
# Default — SQLite file in backend/data/
DATABASE_URL=sqlite:///./data/signal_sports.db

# Custom absolute path
DATABASE_URL=sqlite:////absolute/path/to/my.db

# In-memory (tests only; not useful for production)
DATABASE_URL=sqlite:///:memory:
```

The `data/` directory and `*.db` files are git-ignored.

---

## Tables

| Table | Pydantic model | Notes |
|-------|---------------|-------|
| `articles` | `Article` | All article fields; `entities` and `tags` stored as JSON |
| `profiles` | `UserProfile` | All profile fields; `topics` list stored as JSON |
| `sources` | `Source` | All source fields |
| `feedback_events` | `FeedbackEvent` | Persisted on POST; read via `GET /api/feedback/{user_id}` |
| `calibration_headlines` | `CalibrationHeadline` | `entities` and `tags` stored as JSON |

### Why topics are stored as JSON

`TopicPreference` objects are deeply nested: they contain `eventRules` dicts, optional
`entityEventRules` dicts, lists of leagues and entities, and a `scope` field. Normalizing
this into separate relational tables would create 4–5 extra tables and JOIN complexity for
no immediate product benefit.

The entire `topics` list for a profile is stored as a JSON column in the `profiles` table.
On read, it is deserialized back to `List[TopicPreference]` via Pydantic's
`model_validate`. This round-trip is tested and reliable.

This decision will be revisited when topic preferences need to be mutated individually
(e.g., updating a single topic's event rules from feedback). At that point, normalizing
topics into their own table becomes worthwhile.

### Datetime storage

`published_at` (articles) and `created_at` (feedback) are stored as ISO-8601 strings
rather than SQLAlchemy `DateTime` columns. This avoids timezone round-trip ambiguity in
SQLite and makes the stored values human-readable in the DB file. They are parsed back
to `datetime` objects on read and timezone-aware datetimes are always UTC.

---

## Seed-on-Empty

On every backend startup, the lifespan function:

1. Creates the `data/` directory if needed.
2. Calls `Base.metadata.create_all()` — creates tables that don't exist; skips existing ones.
3. Calls `seed_all_if_empty(session)` — for each table, counts rows. If the count is zero,
   inserts the static seed data from `app/seed/`.

Seeding is **idempotent by design**:
- If articles already exist, no articles are inserted.
- If profiles already exist, no profiles are inserted.
- Restarting the server does not wipe or re-seed existing data.
- Adding real articles via a future RSS adapter will not be affected by the seed check.

### What is seeded

| Seed file | Count | What it contains |
|-----------|-------|-----------------|
| `seed_articles.py` | 16 articles | All product test scenarios: Maccabi, NBA, Deni, EuroLeague, tennis, football, European domestic basketball |
| `seed_profiles.py` | 2 profiles | Guy (basketball power user) + Casual Deni Fan |
| `seed_sources.py` | 7 sources | Sport5, ONE, Walla, Israel Hayom, Ynet, Sportando, Eurohoops |
| `seed_calibration.py` | 16 headlines | Synthetic preference calibration headlines |

---

## Repository Layer

Each table has a dedicated repository module in `app/repositories/`:

| Repository | Operations |
|-----------|-----------|
| `article_repository` | `get_all`, `get_by_id`, `count`, `insert` |
| `profile_repository` | `get_all`, `get_by_id`, `count`, `insert` |
| `source_repository` | `get_all`, `get_by_id`, `count`, `insert` |
| `feedback_repository` | `get_all`, `get_by_user`, `insert` |
| `calibration_repository` | `get_all`, `count`, `insert` |

Each repository takes a `Session` argument (from `Depends(get_session)` in route
handlers). Services like `feed_service.py` continue to accept `List[Article]` and
`UserProfile` Pydantic models — they are not aware of SQLAlchemy. The repositories
handle the ORM-to-Pydantic conversion.

### `seed_runner.py`

`app/repositories/seed_runner.py` calls each repository's `count` and `insert` functions
with the static seed data. It is called from the lifespan and from tests.

---

## What Is Still Not Persisted or Applied

| Capability | Status | Notes |
|-----------|--------|-------|
| Feedback → profile mutation | Not implemented | Feedback is stored but does not yet modify topic rules. Requires PR 7: profile mutation from feedback. |
| Calibration inference | Local-only | Calibration scoring happens in the frontend. Backend only stores and serves the seed headlines. |
| Sandbox profile | Local-only | The calibrated sandbox profile lives in frontend React state only. |
| Article clustering | Not implemented | `cluster_id` field exists but cluster records are not stored or served. |
| Translation | Not implemented | `translated_title` field exists but no translation engine runs. |
| Profile updates via API | Not implemented | `UserProfile` records can only be read, not modified via API. |

---

## How to Reset the Local Dev Database

Stop the backend, then delete the DB file:

```bash
cd backend
del data\signal_sports.db
```

On next startup, the lifespan will recreate tables and re-seed from scratch.

---

## How Tests Isolate the Database

The test `conftest.py` sets `DATABASE_URL` to a fresh temp file at module level —
before any app code is imported. This ensures `app.db.database` picks up the test URL
when it is first imported inside the fixture:

```python
# conftest.py
import os, tempfile
_tmp_dir = tempfile.mkdtemp(prefix="signal_sports_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"
```

The test fixture then creates the app normally via `create_app()`, which triggers the
lifespan, creates tables in the temp DB, and seeds it. All tests in the session share
this isolated DB. The production `data/signal_sports.db` is never touched by tests.

To verify isolation is working:
```bash
# Run tests — should NOT create or modify data/signal_sports.db
cd backend
.venv\Scripts\python.exe -m pytest tests/ -v
```

---

## New Endpoint: `GET /api/feedback/{user_id}`

Added in PR 6 to support persistence verification and the "restart" test.

Returns all feedback events for a given user. If the user does not exist, returns 404.

This endpoint is useful for:
- Debugging what feedback has been accumulated for a user
- Verifying persistence across restarts
- Future: informing the profile mutation engine

---

## Manual Verification

1. Start the backend:
   ```bash
   cd backend
   .venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

2. Verify seeded articles: `GET http://127.0.0.1:8000/api/articles` → should return 16 articles.

3. Submit feedback:
   ```bash
   curl -X POST http://127.0.0.1:8000/api/feedback \
     -H "Content-Type: application/json" \
     -d '{"user_id": "guy", "article_id": "article_001", "action": "more_like_this"}'
   ```

4. Stop the backend (`Ctrl+C`).

5. Start the backend again.

6. Verify feedback persisted:
   `GET http://127.0.0.1:8000/api/feedback/guy` → should include the event from step 3.

7. Verify feed still works: `GET http://127.0.0.1:8000/api/feed/guy` → should return scored articles.

8. If running frontend in backend mode:
   - `VITE_DATA_MODE=backend` in `frontend/.env.local`
   - `npm run dev` in `frontend/`
   - Feed should load from SQLite-backed backend

---

## Next Step: PR 7

With SQLite in place, the next logical step is:

**PR 7: First Real Source Adapter**

Recommended: Sport5 RSS or Eurohoops scraper.

With persistence working:
- New articles from RSS can be stored in SQLite and survive restarts
- Deduplication can compare against the stored article history
- Feedback events can be accumulated across ingestion cycles

Alternatively:
**PR 7: Feedback → Profile Mutation**

If profile mutation from feedback is prioritized over real data ingestion,
PR 7 could implement a basic mutation rule: `never_show` feedback for an
article creates a `hidden` event rule for that article's `event_type` in the
relevant topic.
