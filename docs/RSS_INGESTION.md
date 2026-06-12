# RSS Ingestion — PR 7

## Why RSS Comes After SQLite

SQLite persistence (PR 6) is the prerequisite for real ingestion. Without it:

- Articles fetched in one server run are gone on restart.
- Deduplication cannot work without a history of what has been ingested.
- Feedback accumulated across ingestion cycles has nowhere to live.

With SQLite in place, every article ingested from an RSS feed is written to disk,
survives restarts, and can be deduplicated against previously fetched content.

---

## Source Adapter Architecture

```
backend/app/ingestion/
  config.py               — RSS source configuration list
  adapters/
    base.py               — RawSourceItem dataclass + SourceAdapter interface
    rss_adapter.py        — RSSSourceAdapter (uses feedparser)
  classifier.py           — Deterministic keyword classifier
  dedup.py                — URL-based deduplication + stable ID generation
  ingestion_service.py    — Orchestration: fetch → classify → dedup → insert
```

### Base adapter

`SourceAdapter` is a minimal interface:

```python
class SourceAdapter:
    source_id: str

    def fetch(self) -> list[RawSourceItem]:
        ...
```

`RawSourceItem` carries the raw parsed data before classification:
- `source_id`, `url`, `title`, `published_at`, `summary`

### RSS adapter

`RSSSourceAdapter` wraps `feedparser.parse()` and maps entries to `RawSourceItem`.

- Handles network errors gracefully (returns `[]`, logs, does not raise).
- Skips entries missing `link` or `title`.
- Parses `published_parsed` or `updated_parsed` to a UTC `datetime`.
- Falls back to `datetime.now(UTC)` when no date is available.

### Adding a new RSS source

1. Open `backend/app/ingestion/config.py`.
2. Add an `RSSSourceConfig` entry to `RSS_SOURCES`:

```python
RSSSourceConfig(
    source_id="sportando",
    display_name="Sportando",
    feed_url="https://sportando.basketball/feed/",
    language="en",
    allowed_languages=("en",),          # optional — blocks non-English URLs
    blocked_url_patterns=("/tr/", ...),  # optional — explicit path blocklist
),
```

3. That is all. The adapter, classifier, dedup, and endpoints pick it up automatically.

See `docs/RSS_QUALITY_GUARDRAILS.md` for details on how URL and language filters work.

---

## Configured Sources

| source_id      | display_name   | language | feed_url                               |
|----------------|---------------|----------|----------------------------------------|
| `eurohoops`    | Eurohoops     | en       | https://www.eurohoops.net/feed/        |
| `sportando`    | Sportando     | en       | https://sportando.basketball/feed/     |
| `walla_sport`  | וואלה ספורט   | he       | https://rss.walla.co.il/feed/7         |

### English sources (PR 7)

Eurohoops and Sportando are basketball-only English sources. They were chosen because:
- They produce clean RSS.
- The content focus matches the product's current interest areas.
- The classifier can default `sport = "basketball"` for them without any keywords.

### Hebrew source (PR 8)

Walla Sport (`walla_sport`) is the first Hebrew RSS source. Walla feed ID 7 serves the
Walla Sport section — confirmed by all items linking to `sports.walla.co.il/item/...`.

Coverage: Israeli basketball (Maccabi, Winner League, EuroCup, EuroLeague), Israeli football,
international tennis (Grand Slams), NBA, international football events (World Cup, Euros).

See `docs/HEBREW_RSS_SOURCE.md` for the full source selection rationale and verification
results.

---

## Article Normalization

Each `RawSourceItem` is mapped to an `Article` via the classifier:

| Article field     | Value |
|------------------|-------|
| `id`             | `rss_<sha1_of_url[:20]>` — stable, deterministic |
| `source`         | source_id from config |
| `language`       | from config (`en` or `he`) |
| `original_title` | RSS title for English sources; `None` for Hebrew |
| `translated_title` | Always `None` (translation deferred) |
| `title`          | RSS title (always) |
| `sport`          | From classifier |
| `league`         | From classifier |
| `entities`       | From classifier |
| `event_type`     | From classifier |
| `importance`     | From classifier |
| `confidence`     | From classifier |
| `tags`           | From classifier |
| `published_at`   | From RSS entry; falls back to `datetime.now(UTC)` |

---

## Classification

`backend/app/ingestion/classifier.py` is a pure deterministic function.

```python
result = classify(title, source_id="eurohoops", language="en")
```

### What it detects

| Field        | How detected |
|-------------|-------------|
| `sport`      | Basketball/football/tennis keyword lists; basketball-only sources default to basketball; entity-based inference if sport still unknown |
| `league`     | Sport-specific keyword lists ordered: **EuroCup** (before EuroLeague) → NBA → EuroLeague → Israeli Basketball League → ACB → BSL → Greek → LBA → LNB → Wimbledon → Roland Garros → etc. Israeli Basketball League also inferred from Maccabi entity + context keywords (Holon, Eilat, Hapoel Jerusalem, etc.) |
| `entities`   | Maccabi Tel Aviv Basketball (Hebrew + English keywords); Deni Avdija (Hebrew + English) |
| `event_type` | Ordered keyword matching: grand_slam_winner → finals_result → signing → negotiation → candidate → injury → major_trade → playoff_result → early_round_result → regular_season_result → schedule → match_result → news |
| `importance` | Rule table: very_high for titles/finals/grand slam; high for signing/negotiation/injury/trade involving a tracked entity or major league; low for schedule/early rounds; **low for generic news (event_type=news) with no tracked entity** |
| `confidence` | Additive: 0.40 base + 0.15 for sport + 0.05 for basketball-only source + 0.15 for league + 0.15 for entity + 0.10 for non-news event type; capped at 0.95 |

### Classifier limitations (known)

- **No NLP or LLM.** Keyword matching only.
- **Hebrew entity detection is limited** to Maccabi Tel Aviv Basketball and Deni Avdija.
- **No player name extraction** beyond the two above.
- **No translation.** `translated_title` is always `None`.
- **No summary analysis.** Only the title is classified.
- **No team name extraction** for NBA teams from article content — only direct name keyword hits.
- **Ambiguous keywords** (e.g., "ליגת העל" = both Israeli football and basketball league) are resolved by context keywords in the same title; may misclassify if context is absent.
- **Generic news articles** (no sport keyword, no entity) are classified as `sport=unknown` — this is intentional precision-over-recall behavior.

---

## Deduplication

URL-based deduplication only. Rules:

- Article ID is derived as `rss_<sha1_of_url[:20]>`.
- Before inserting, `url_already_exists(session, url)` queries the `articles` table.
- If the URL already exists, the item is counted as `skipped_duplicate`.
- Running ingestion twice for the same feed returns `inserted=0, skipped_duplicate=N` on the second run.

**TODO:** Fuzzy title dedup — near-duplicate headlines from different sources should
be grouped into clusters. This requires a similarity algorithm and the `cluster_id` field,
which is already in the `Article` model but not yet populated.

---

## Testing RSS from the UI (PR 8.1)

The Sources page includes a full ingestion control panel when running in backend mode.
No need to use FastAPI `/docs` or curl to trigger ingestion.

### Steps

1. Start the backend:

```bash
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

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

4. Open the app (http://localhost:5173 or the port shown) and navigate to **מקורות** (Sources).

5. The **ייבוא כתבות RSS** panel appears at the top. It lists the configured sources
   (Eurohoops, Sportando, וואלה ספורט) loaded from the API.

6. Select a source or leave "כל המקורות" selected. Click **הרץ ייבוא עכשיו**.

7. The panel shows a loading state, then a per-source result summary:
   - נמצאו (fetched), נוספו (inserted), דולגו ככפולים (skipped_duplicate), סוננו (skipped_filtered), נכשלו (failed)
   - Green highlight if any articles were inserted.

8. The feed and debug view refresh automatically after a successful run — new articles
   appear immediately in the Feed and Debug pages without a browser reload.

9. Run ingestion again on the same source — the panel should show "לא נוספו כתבות חדשות"
   with inserted=0, skipped_duplicate=N. This confirms deduplication works.

10. Click **איכות הסיווג** at the bottom of the panel to see:
    - Total RSS articles, low-confidence count, questionable article count
    - Sport breakdown (basketball, football, unknown)
    - Event type breakdown
    - Top 5 questionable articles (those with sport_unknown, low_confidence, or generic_news)

### In local mode

If the app is running in local mode (`VITE_DATA_MODE=local` or no `.env.local`), the
ingestion panel shows a disabled state with the message:
- "ייבוא RSS זמין רק במצב שרת"
- "מצב מקומי פעיל — כדי לראות RSS אמיתי הפעל VITE_DATA_MODE=backend"

Local mode continues to work fully with mock data. No backend is required.

---

## How to Run Ingestion Manually (API)

Start the backend:

```bash
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open the interactive docs: `http://127.0.0.1:8000/docs`

Run all configured sources:
```
POST /api/ingest/run
```

Run a single source:
```
POST /api/ingest/run?source_id=eurohoops
```

Check what ran:
```
GET /api/ingest/runs
```

Check inserted articles:
```
GET /api/articles
```

Check feed with new articles:
```
GET /api/feed/guy
GET /api/debug/feed/guy
```

Run again and confirm duplicates are skipped — `inserted` should be 0, `skipped_duplicate` should equal `fetched`.

---

## Ingestion Run Log

Every ingestion attempt is persisted in the `ingestion_runs` SQLite table.

| Column | Type | Notes |
|--------|------|-------|
| `id` | string | UUID |
| `source_id` | string | |
| `started_at` | ISO-8601 string | |
| `finished_at` | ISO-8601 string | |
| `status` | string | `ok` or `error` |
| `fetched_count` | int | |
| `inserted_count` | int | |
| `skipped_duplicate_count` | int | |
| `failed_count` | int | per-item errors |
| `error_message` | string | first error if any |

Readable via `GET /api/ingest/runs` (most recent first, default limit 50).

---

## API Compatibility

Existing endpoints are unchanged and continue to work:

| Endpoint | Behavior after PR 7 |
|----------|-------------------|
| `GET /api/articles` | Returns seed articles + any RSS-ingested articles |
| `GET /api/feed/{user_id}` | Scores all articles including ingested ones |
| `GET /api/debug/feed/{user_id}` | Shows all articles + reasoning, including ingested |

---

## Why No Scraping / X / Scheduler Yet

**Scraping (Sport5, ONE, Israel Hayom):** These sources don't have clean RSS. Scraping
requires browser automation or HTML parsing, which introduces fragility and maintenance
burden. Deferred to a future PR.

**X/Twitter:** Rate-limited API, requires auth, produces short-form content that needs
different classification. Deferred.

**Scheduler:** Running ingestion on a cron is valuable but adds operational complexity.
For MVP validation, the manual endpoint (`POST /api/ingest/run`) is enough. A scheduler
(APScheduler or a cron endpoint) should be added after the classification quality is
validated with real data.

---

## Next Steps

1. Add scheduled ingestion (e.g., every 15 minutes via APScheduler).
2. Fuzzy title dedup via `difflib.SequenceMatcher` or similar.
3. `translated_title` generation using a translation API or local model.
4. Feedback → profile mutation: `never_show` creates a `hidden` event rule for the matched topic.
5. Cluster seeding: group articles with the same core story into a `cluster_id`.
6. Additional Hebrew sources: Sport5 or ONE via category page adapters if RSS is unavailable.
