# Backend Foundation — Design Notes

## Why a Backend Was Added

The first three PRs proved the relevance engine is correct, testable, and produces the right per-user decisions. The frontend mock-data model was sufficient to validate the product concept.

But a frontend-only architecture has hard ceilings:

1. **No real data can be ingested.** Real RSS feeds, scraping, and source adapters need a server-side process that runs independently of the browser.
2. **No persistence.** Feedback events, calibration ratings, and profile changes reset on page refresh.
3. **No multi-device.** A user's profile cannot be shared across devices without a backend.
4. **No background processing.** Article classification, clustering, and deduplication need to run continuously, not only when the user has the tab open.

PR 4 creates the backend foundation that all of these future capabilities will build on.

## What Was Built

The backend is a FastAPI application in `backend/` with the following components:

### Data models (`backend/app/models/`)

Python Pydantic v2 models that mirror the frontend data structures:

| Model | Frontend equivalent | Notes |
|-------|-------------------|-------|
| `Article` | `mockArticles` shape | snake_case field names |
| `UserProfile` | `userProfiles` shape | Contains `TopicPreference` list |
| `TopicPreference` | topic object in profile | Includes `entity_event_rules` |
| `DecisionResult` | score object from engine | Includes `reasoning` list |
| `ScoredArticle` | scored feed item | Article + decision + reasoning |
| `FeedbackEvent` | feedback event | stored in-memory only |
| `Source` | `feedSources` shape | |
| `CalibrationHeadline` | `calibrationHeadlines` shape | |

### Relevance engine (`backend/app/services/relevance_engine.py`)

A faithful Python port of the frontend engine at `src/engine/relevanceEngine.js`.

The same scoring semantics are implemented in both:
- 5 decision levels: `hidden`, `low_feed`, `feed`, `high_feed`, `push`
- 6 topic modes: `all`, `followed_entities_only`, `titles_only`, `high_importance_only`, `major_only`, `muted`
- Entity-specific event rule overrides (`entityEventRules`)
- Importance boost capped at `high_feed` — push never auto-escalates
- Event type alias resolution (`major_transfer → major_signing`, etc.)
- Full Hebrew reasoning chain on every decision

The backend engine is independently tested and produces identical decisions to the frontend engine for the same input.

### API endpoints

All endpoints are prefixed `/api/` except `/health`.

**Feed endpoints:**
- `GET /api/feed/{user_id}` — visible feed (hidden articles excluded), sorted by decision priority then date
- `GET /api/debug/feed/{user_id}` — all articles scored, including hidden, with full reasoning

**CRUD endpoints:**
- `GET /api/profiles` / `GET /api/profiles/{user_id}`
- `GET /api/articles` / `GET /api/articles/{article_id}`

**Feedback:**
- `POST /api/feedback` — records a feedback event in-memory

**Calibration:**
- `GET /api/calibration/headlines` — returns seeded calibration headlines

### Seed data

16 articles covering all test scenarios (Maccabi negotiation/signing/injury, NBA Hornets/Wizards, Deni trade/injury, NBA Finals, tennis Grand Slam, early-round tennis, football noise, EuroLeague transfer, European domestic basketball).

Both user profiles (Guy + Casual Deni Fan) are seeded with the same topic/rule structures as the frontend.

### Tests

46 pytest tests across 3 files:

- `tests/test_health.py` — health check
- `tests/test_relevance_engine.py` — unit tests for the engine (23 tests)
- `tests/test_feed_api.py` — integration tests via TestClient (23 tests)

Key test coverage:
- Maccabi negotiation/signing/injury → push for Guy
- Hornets/Wizards → visible for Guy, hidden for Deni Fan
- Deni trade → push for both profiles
- Grand Slam winner → high_feed for Guy
- Early-round tennis → hidden for Guy
- Push does NOT trigger from importance boost alone
- Muted source/topic → hidden
- Disabled source → hidden
- Feedback accepted and validated
- Debug feed includes hidden articles + reasoning

## Current Boundaries Between Frontend and Backend

As of PR 4, the frontend and backend are **independent**. They share the same product model (profiles, topics, event rules, decision levels) but run in parallel.

| Concern | Frontend | Backend |
|---------|----------|---------|
| User profile storage | In-memory React state | In-memory Python dict |
| Article storage | `mockArticles.js` | `seed_articles.py` |
| Relevance scoring | `relevanceEngine.js` | `relevance_engine.py` |
| Feed display | `AppContext` + `Feed.jsx` | `GET /api/feed/{user_id}` |
| Debug display | `Debug.jsx` | `GET /api/debug/feed/{user_id}` |
| Feedback | Context state (unread) | In-memory list (unread) |
| Calibration | `calibrationEngine.js` + `Calibration.jsx` | `GET /api/calibration/headlines` |
| Authentication | None | None |

The frontend is not yet connected to the backend. It still uses its own local scoring engine and mock data. This is intentional for PR 4 — the backend should be validated independently before integration.

## What Is Intentionally Not Implemented

| Missing piece | Reason |
|--------------|--------|
| SQLite / database | Deferred to PR 5/6 when real data needs to persist across restarts |
| Frontend integration | Deferred to PR 5 — validate backend independently first |
| Real RSS/scraping | Deferred — correct model first, then real data |
| Authentication | Deferred — not needed until multi-user or production |
| Push notifications | Out of scope |
| LLM calls | Out of scope |
| Article clustering | Deferred — needs a real algorithm |
| Feedback → profile mutation | Feedback stored but not yet applied; requires preference update logic |
| Calibration inference | Frontend has the full inference engine; backend only serves the headlines |

## Topic Scope Guards (PR 4.1)

### Why OR matching was too broad

The original `_find_matching_topics` used OR logic: a topic matched if `article.sport == topic.sport` OR `article.league in topic.leagues` OR any entity intersected. This caused the `maccabi_tel_aviv_basketball` topic (which carries `sport: "basketball"`) to match every basketball article in the world — regardless of which team, league, or entity was involved. A non-Maccabi EuroLeague transfer would resolve via the Maccabi topic's alias chain (`major_transfer → major_signing → push`), incorrectly producing push for a story Maccabi was not part of.

The problem is structural: **sports like basketball contain many smaller topics at different priority levels**. A user may care deeply about Maccabi Tel Aviv, broadly about the NBA, strongly about EuroLeague, moderately about Israeli basketball, and only minimally about European domestic leagues. These are different interests that must not bleed into each other.

### How scope matching works

Each `TopicPreference` now has an optional `scope` field:

| scope | Matching rule | Use case |
|-------|--------------|----------|
| `entity` | `article.entities ∩ topic.entities` must be non-empty | Team or person topics (Maccabi TLV, Deni Avdija) |
| `league` | `article.league ∈ topic.leagues` | Single-league topics (NBA, EuroLeague, Israeli Basketball) |
| `league_group` | `article.league ∈ topic.leagues` (same as league) | Grouped leagues sharing one policy (European domestic basketball) |
| `sport` | `article.sport == topic.sport` | Broad sport topics with restrictive modes (football major_only, tennis titles_only) |
| `None` | Legacy OR matching: sport OR league OR entity | Calibration-generated topics that predate scope guards |

### Assigned scopes in current profiles

| Topic | Scope |
|-------|-------|
| Maccabi Tel Aviv Basketball | `entity` |
| NBA | `league` |
| EuroLeague | `league` |
| Israeli Basketball League | `league` |
| Major European Domestic Basketball | `league_group` |
| Football | `sport` |
| Tennis | `sport` |

### Why this is necessary before real RSS ingestion

When real sources are connected (Sport5, Eurohoops, Sportando), the volume of basketball articles will be high. Without scope guards, a single broad OR match would cause Maccabi-priority rules to fire on unrelated articles. Scope guards ensure that each topic's rules apply only to the articles it is genuinely about. This must be correct before ingesting real data — fixing it after integration would require debugging hundreds of incorrect decisions.

### Calibration-generated scopes

Topics generated by `calibrationEngine.js` now include a `scope` field inferred from the topic's structure:
- `followed_entities_only` mode → `scope: "entity"` (entity-focused interest)
- Specific league → `scope: "league"`
- General/sport-wide → `scope: "sport"`

## Engine Parity

The backend engine (`relevance_engine.py`) and frontend engine (`relevanceEngine.js`) use identical scope-matching semantics. Both implement `doesTopicMatchArticle` / `_does_topic_match_article` with the same scope logic and match reason strings (in Hebrew). Frontend and backend tests cross-validate the same behaviors.

## Next Planned Step: PR 5

Connect the frontend to the backend:
1. Replace `AppContext` local scoring with API calls to `GET /api/feed/{userId}`
2. Replace mock article data source with `GET /api/articles`
3. Keep the frontend engine as a fallback / comparison view during transition
4. Add a first real source adapter (Sport5 RSS or Eurohoops scraper)
5. Add SQLite persistence for profiles and articles
