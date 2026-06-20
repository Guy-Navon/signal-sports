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
  ingestion_service.py    — Orchestration: fetch → filter → dedup → normalise/classify → insert
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

| source_id             | display_name        | language | MVP | feed_url                                    |
|-----------------------|---------------------|----------|-----|---------------------------------------------|
| `walla_sport`         | וואלה ספורט         | he       | ✓ active | https://rss.walla.co.il/feed/7         |
| `israel_hayom_sport`  | ישראל היום ספורט    | he       | ✓ active | https://www.israelhayom.co.il/rss.xml  |
| `eurohoops`           | Eurohoops           | en       | disabled (post-MVP) | https://www.eurohoops.net/feed/ |
| `sportando`           | Sportando           | en       | disabled (post-MVP) | https://sportando.basketball/feed/ |

**MVP active sources:** `walla_sport` and `israel_hayom_sport` only. `eurohoops` and `sportando` have
`enabled=False` in `config.py` and are not fetched by default. They remain in the codebase for easy
re-enabling post-MVP.

**ONE Sport and Ynet Sport** were investigated in PR 10 and rejected for MVP:
- ONE Sport: no public RSS (all endpoints 404)
- Ynet Sport: SPA frontend with no RSS links (harder to scrape)

If a third Hebrew source is added post-MVP, ONE is the preferred candidate (traditional HTML, less brittle than a SPA).

### English sources (PR 7, post-MVP)

Eurohoops and Sportando are basketball-only English sources. They were chosen because:
- They produce clean RSS.
- The content focus matches the product's current interest areas.
- The classifier can default `sport = "basketball"` for them without any keywords.

### Hebrew sources (PR 8, PR 10)

**Walla Sport** (`walla_sport`) is the first Hebrew RSS source. Walla feed ID 7 serves the
Walla Sport section — confirmed by all items linking to `sports.walla.co.il/item/...`.

Coverage: Israeli basketball (Maccabi, Winner League, EuroCup, EuroLeague), Israeli football,
international tennis (Grand Slams), NBA, international football events (World Cup, Euros).

**Israel Hayom Sport** (`israel_hayom_sport`) is added in PR 10. Israel Hayom publishes a
general news RSS at `rss.xml` that mixes sport with politics, opinion, and culture. Sport articles
are identified by `/sport/` in the URL (subpaths: `israeli-basketball`, `world-basketball`,
`world-soccer`, `other-sports`, `opinions-sport`). The `allowed_url_patterns=("/sport/",)` filter
retains only sport items; all others are counted as `skipped_filtered`.

See `docs/HEBREW_RSS_SOURCE.md` for full source discovery rationale and the candidates rejected in PR 10.

### Adding a source with URL allowlist filtering (PR 10)

For sources that mix sport and non-sport content, use `allowed_url_patterns` to accept only
items whose URL matches at least one pattern. Items that do not match are counted as
`skipped_filtered` and never reach the DB — analogous to `blocked_url_patterns` (blocklist),
but inverted (allowlist).

```python
RSSSourceConfig(
    source_id="israel_hayom_sport",
    display_name="ישראל היום ספורט",
    feed_url="https://www.israelhayom.co.il/rss.xml",
    language="he",
    allowed_languages=("he",),
    allowed_url_patterns=("/sport/",),   # only sport-path URLs accepted
)
```

---

## Article Normalization

Each `RawSourceItem` is mapped to an `Article` via the classifier:

| Article field     | Value |
|------------------|-------|
| `id`             | `rss_<sha1_of_url[:20]>` — stable, deterministic |
| `source`         | source_id from config |
| `language`       | detected from URL path or title Unicode script; falls back to source config |
| `original_title` | raw RSS title for non-Hebrew sources; `None` for Hebrew articles |
| `translated_title` | Hebrew translation if provider is configured; `None` if noop/disabled |
| `title`          | Hebrew translation when available; raw RSS title otherwise |
| `sport`          | From classifier (deterministic) or LLM + guardrails (Hebrew broad sources, PR 11) |
| `league`         | From classifier or LLM |
| `entities`       | From classifier or LLM (canonical entity names only) |
| `event_type`     | From classifier or LLM |
| `importance`     | From classifier or LLM (never downgraded by LLM) |
| `confidence`     | From classifier (deterministic confidence score) |
| `tags`           | From classifier |
| `subtitle`       | Cleaned RSS `<description>` / `<summary>` text (HTML stripped, entities unescaped, truncated to 500 chars); `None` when RSS entry has no description |
| `classified_by`  | `rules`, `llm`, `llm+rules_guardrail`, `rules_fallback_after_llm_failure`, `rules_fallback_low_confidence` (PR 11) |
| `classification_provider` | Which provider classified this article: `rules`, `ollama:llama3.2:3b`, `fake` (PR 11) |
| `classification_reason` | LLM's one-sentence explanation of the classification (PR 11) |
| `classification_confidence` | LLM's self-assessed confidence 0.0–1.0; separate from deterministic `confidence` (PR 11) |
| `published_at`   | From RSS entry; falls back to `datetime.now(UTC)` |

---

## Classification

Classification runs in two stages: deterministic first (always), then optionally LLM for Hebrew broad sources.

### Deterministic classifier

`backend/app/ingestion/classifier.py` is a pure deterministic function.

```python
result = classify(title, source_id="walla_sport", language="he", subtitle=subtitle)
```

`subtitle` is optional (`None` when the RSS entry has no `<description>`). It is used as a gap-filler only — title is always the primary signal. Subtitle fills `sport=unknown`, empty entities, missing league, and generic `event_type="news"` when the title context is insufficient. Subtitle never overrides an already-resolved sport value from the title. Football Maccabi disambiguation (the `_FOOTBALL_MACCABI_KW` blocklist) applies equally to subtitle text.

| Field        | How detected |
|-------------|-------------|
| `sport`      | Basketball/football/tennis keyword lists; basketball-only sources default to basketball; entity-based inference if sport still unknown; subtitle fills `sport=unknown` when title is ambiguous |
| `league`     | Sport-specific keyword lists ordered: **EuroCup** (before EuroLeague) → NBA → EuroLeague → Israeli Basketball League → ACB → BSL → Greek → LBA → LNB → Wimbledon → Roland Garros → etc. Israeli Basketball League also inferred from Maccabi entity + context keywords (Holon, Eilat, Hapoel Jerusalem, etc.) |
| `entities`   | Maccabi Tel Aviv Basketball (Hebrew + English keywords); Deni Avdija (Hebrew + English) |
| `event_type` | Ordered keyword matching: grand_slam_winner → finals_result → signing → negotiation → candidate → injury → major_trade → playoff_result → early_round_result → regular_season_result → schedule → match_result → news |
| `importance` | Rule table: very_high for titles/finals/grand slam; high for signing/negotiation/injury/trade involving a tracked entity or major league; low for schedule/early rounds; **low for generic news (event_type=news) with no tracked entity** |
| `confidence` | Additive: 0.40 base + 0.15 for sport + 0.05 for basketball-only source + 0.15 for league + 0.15 for entity + 0.10 for non-news event type; capped at 0.95 |

### LLM classifier (Hebrew broad sources, PR 11)

When `CLASSIFICATION_PROVIDER=ollama` (or `fake`), Hebrew broad source articles go through a second classification pass using a local LLM. The LLM result is merged with the deterministic result using guardrails. The final article fields reflect the merged decision.

For English basketball-only sources (`eurohoops`, `sportando`), the deterministic classifier is the only path — LLM is never called.

### Selective LLM gating (PR 12)

Before calling the LLM, `should_call_llm_for_article()` in `gating.py` evaluates the deterministic result and decides whether the LLM call is worth making. Articles are skipped when the rules already produced a strong result (clear league, strong source URL hint with context, high-confidence sport+league). LLM is always called for `sport=unknown`, `ambiguous_club`, or low-confidence results.

- `CLASSIFICATION_LLM_GATING=enabled` (default): gating active
- `CLASSIFICATION_LLM_GATING=disabled`: always call LLM; reproduces pre-gating behavior

`run_ingestion()`, `_run_source()`, and `_normalise()` all accept `llm_gating_enabled_override: Optional[bool] = None`. When not None, overrides the env-level flag for that call only — the module-level `_GATING_ENABLED` is never mutated. Used by the benchmark endpoint to run both phases in one backend process.

### Dev/QA benchmark endpoint (`POST /api/dev/benchmark/llm-gating`)

Runs a two-phase benchmark: baseline (gating disabled via override) then gated (gating enabled via override). Resets RSS data between phases. Returns per-source stats for both phases plus a comparison with PASS/FAIL status. Requires `ALLOW_DEV_RESET=true` and an active provider. Results are not persisted. Accessible from the Sources page "בנצ'מרק LLM Gating" panel in backend mode.

Gating metrics are returned in the live `POST /api/ingest/run` response as `llm_skipped`, `llm_skip_reasons`, and `llm_call_reasons`. These are not persisted to the DB.

See `docs/LLM_CLASSIFICATION.md` for full gating design details.

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

5. The **ייבוא כתבות RSS** panel appears at the top. It lists the enabled MVP sources
   (וואלה ספורט, ישראל היום ספורט) loaded from the API.

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

Run a single MVP source:
```
POST /api/ingest/run?source_id=walla_sport
POST /api/ingest/run?source_id=israel_hayom_sport
```

Run a disabled source (must first set `enabled=True` in `config.py`):
```
# POST /api/ingest/run?source_id=eurohoops   — disabled by default (post-MVP)
# POST /api/ingest/run?source_id=sportando   — disabled by default (post-MVP)
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

## Ingestion Run Response (`SourceIngestResult`)

The `POST /api/ingest/run` response contains a `sources` array. Each element is a `SourceIngestResult` with:

**Counts (also persisted in `ingestion_runs` DB table):**

| Field | Notes |
|-------|-------|
| `source_id` | |
| `fetched` | Items returned by RSS adapter |
| `inserted` | New articles added to DB |
| `skipped_duplicate` | URL already in DB |
| `skipped_filtered` | Blocked by URL/language filter (live response only — not in DB) |
| `failed` | Per-item errors |

**Timing fields (live response only — not persisted):**

| Field | Notes |
|-------|-------|
| `fetch_ms` | RSS adapter fetch time |
| `total_ms` | Full source run wall time |
| `llm_attempts` | Total LLM calls (including failures) |
| `llm_successes` | Calls resulting in `llm` or `llm+rules_guardrail` |
| `llm_fallback_connect_error` | Ollama refused connection |
| `llm_fallback_timeout_or_parse` | Timeout, HTTP error, or JSON parse failure |
| `llm_fallback_low_confidence` | LLM responded but `confidence < 0.65` |
| `llm_avg_ms` | Average LLM call latency across all attempts |
| `llm_p95_ms` | p95 LLM call latency |

The **Sources page** displays these timing fields immediately after clicking "הרץ ייבוא עכשיו" — no need to open logs or DevTools. Under each source result card a `ביצועים:` row shows: fetch time, total time, LLM success ratio, avg/p95 latency, and fallback counts. If LLM is disabled (`llm_attempts === 0`), the row shows `LLM לא הופעל` instead. Non-zero fallbacks are highlighted in amber.

A detailed INFO log line is also emitted to the backend logger at the end of each source run.

## Ingestion Run Log (persisted)

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

Readable via `GET /api/ingest/runs` (most recent first, default limit 50). Note: timing fields are **not** in this table — they exist only in the live `POST /api/ingest/run` response.

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

**Additional Hebrew sources (Sport5, ONE, Ynet):** These sources don't have clean RSS.
Israel Hayom is already active via its general RSS + `/sport/` allowlist. Sport5, ONE, and
Ynet require scraping or category-page parsing, which introduces fragility and maintenance
burden. Deferred to a future PR. ONE is the preferred next candidate (traditional HTML;
less brittle than Ynet's SPA).

**X/Twitter:** Rate-limited API, requires auth, produces short-form content that needs
different classification. Deferred.

**Scheduler:** Running ingestion on a cron is valuable but adds operational complexity.
For MVP validation, the manual endpoint (`POST /api/ingest/run`) is enough. A scheduler
(APScheduler or a cron endpoint) should be added after the classification quality is
validated with real data.

---

## Next Steps

1. Validate LLM classification quality — run `POST /api/classify/backfill?source_id=walla_sport` with Ollama enabled, inspect debug view for Guy.
2. Expand entity normalization map in `entity_normalizer.py` after LLM benchmark shows which entities are recognized but not canonicalized.
3. Add scheduled ingestion (e.g., every 15 minutes via APScheduler).
4. Fuzzy title dedup via `difflib.SequenceMatcher` or similar.
5. Feedback → profile mutation: `never_show` creates a `hidden` event rule for the matched topic.
6. Cluster seeding: group articles with the same core story into a `cluster_id`.
7. Additional Hebrew sources: Sport5 or ONE via category page adapters if RSS is unavailable.
