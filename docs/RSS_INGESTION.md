# Sources & Ingestion

**Status: living contract** for the configured news sources, the adapters that read
them, and what one ingestion pass does to an item before it becomes an article.
Last updated: 2026-10-12 (truth sweep; absorbed the former `HEBREW_RSS_SOURCE.md`).

Related contracts: scheduling, the worker and the single-flight lease are in
[SCHEDULER.md](SCHEDULER.md). Source-level URL and language filters and the deterministic
classifier changelog are in [RSS_QUALITY_GUARDRAILS.md](RSS_QUALITY_GUARDRAILS.md). The
LLM gate and merge guardrails are in [LLM_CLASSIFICATION.md](LLM_CLASSIFICATION.md). The
facts stage is in [ARTICLE_FACTS.md](ARTICLE_FACTS.md), and story grouping is in
[CLUSTERING.md](CLUSTERING.md).

---

## 1. Configured sources

Code defaults live in `backend/app/ingestion/config.py`. A runtime override in the
`source_overrides` table wins over the code default. Overrides are set from the Sources page
toggle or `PATCH /api/ingest/sources/{source_id}` (body `{"enabled": bool}`), and they survive
restarts. Every runtime consumer resolves the effective state through
`app/ingestion/source_state.py`: run-all ingestion, the scheduler, `GET /api/ingest/sources`
and source health.

| source_id | Display | Type | Code default | **Live state (local DB, 2026-10-12)** | Endpoint |
|---|---|---|---|---|---|
| `walla_sport` | וואלה ספורט | rss | enabled | enabled | `https://rss.walla.co.il/feed/7` |
| `israel_hayom_sport` | ישראל היום ספורט | rss + `/sport/` allowlist | enabled | enabled | `https://www.israelhayom.co.il/rss.xml` |
| `ynet_sport` | ynet ספורט | rss | enabled | enabled | `https://www.ynet.co.il/Integration/StoryRss3.xml` |
| `sport5_sport` | ערוץ הספורט | html_scrape (pilot) | **disabled** | **enabled by override** | `https://www.sport5.co.il/liga.aspx?FolderID=273` |
| `one_sport` | ONE ספורט | html_scrape (public JSON) | enabled | **disabled by override** | `https://api.one.co.il/JSON/v6/Articles/Category/{1,2,3,5,7,155}` |
| `eurohoops` | Eurohoops | rss (English) | disabled | disabled | `https://www.eurohoops.net/feed/` |
| `sportando` | Sportando | rss (English/Italian) | disabled | disabled (override) | `https://sportando.basketball/feed/` |

**The live state differs from the code defaults in two places, and nothing records why.** The
corpus was rebuilt on 2026-07-12 after the #106 wipe. Since then `one_sport` has never run,
so the corpus holds **zero** ONE articles. `sport5_sport` has run on every cycle. It is a
production source in practice, even though the code still labels it a pilot. Re-enabling ONE
needs a live probe first, because its JSON API may have changed. That is an owner decision.

English sources and translation are **post-MVP**: the product is Hebrew-only. Do not re-enable
`eurohoops` or `sportando` as a side effect of other work. The translation path they need is
preserved but disabled ([TITLE_TRANSLATION.md](TITLE_TRANSLATION.md)).

### Per-source notes

- **Walla Sport.** Feed 7 is the sport section (about 30 items per fetch). Article URLs are
  uniformly `sports.walla.co.il/item/<id>` and carry **no category signal**, so Walla can never
  have URL sport hints. Its sport comes from keywords, entities and the gated LLM. Walla
  `<description>` is the article's lede paragraph, and `clean_subtitle()` cuts it at the last
  complete sentence within 240 characters.
- **Israel Hayom Sport.** The feed is a general 100-item news feed, of which about 21 items are
  sport. `allowed_url_patterns=("/sport/",)` keeps only sport items and counts the rest as
  `skipped_filtered`. Because the feed holds only 100 items, the 5-minute cadence is what keeps
  sport items from aging out between fetches.
- **Ynet Sport.** Official RSS 2.0, about 30 items per fetch. `description` holds a thumbnail
  block plus a teaser, and the subtitle cleaner keeps the teaser. The non-standard `tags`
  element is not stored.
- **Sport5.** It has no public RSS. The adapter scrapes the basketball category page, a static
  server-rendered page of about 8–12 cards. Article anchors are selected by URL shape
  (`articles.aspx` + `docID=`), not CSS class. Card subtitles and `DD.MM.YY - HH:MM`
  timestamps are parsed, with Israel time converted to UTC. The footer legal folder is blocked
  with `blocked_url_patterns=("folderid=413&",)` (#97). A site redesign degrades the source to 0
  items, which source health shows; it never crashes a run.
- **ONE.** It has no news RSS: the probes return 404, and `sites.one.co.il/rss/video/itunes` is
  podcast media. The adapter reads the public JSON article lists that the ONE homepage calls,
  using `Title.Main` → title, `Title.Secondary` → subtitle, `URL.PC` → URL, and `Date` (Israel
  local time) → UTC. It skips `IsVideo=true` items and never fetches article bodies.

### URL sport hints (`backend/app/classification/source_hints.py`)

A hint is the **first** sport check in the deterministic classifier and overrides an LLM sport
in merge Guardrail 7. Every rule is source-scoped, so there are no generic URL patterns.

| Source | Basketball | Football | Tennis | No hint (falls through) |
|---|---|---|---|---|
| `israel_hayom_sport` | `/sport/israeli-basketball/`, `/sport/world-basketball/` | `/sport/world-soccer/`, `/sport/israeli-soccer/` | — | `/sport/other-sports/`, `/sport/opinions-sport/` |
| `ynet_sport` | `/sport/israelibasketball/`, `/sport/worldbasketball/` | `/sport/worldsoccer/`, `/sport/worldcup…`, `/sport/israelisoccer/` | `/sport/tennis/` | `/sport/article/`, `livegame.ynet.co.il` |
| `sport5_sport` | `FolderID=274` (exact value) | — | — | every other folder (11840/405/416 are deliberately unmapped: too little evidence) |
| `one_sport` | category ids 2, 5 in `/Article/NN-NN/<id>,…` | ids 1, 3, 155 | — | id 7 and generic `/Article/<id>.html` |
| `walla_sport` | — | — | — | always (no category in the URL) |

### Candidates probed and rejected

The probes ran in PR 8 and PR 10 (June 2026). Before probing again, check the history here
and in `backend/scripts/probe_hebrew_rss.py`.

| Source | What was tried | Outcome |
|---|---|---|
| Walla | `feed/1`, `/2`, `/5`, `/7`, `/22`, `/31` | `feed/7` is sport. **Accepted** |
| Israel Hayom | `/rss.xml`, `/rss/sport.xml`, `/sport/rss.xml`, `/sport/?feed=rss2`, `/sport/feed/` | only `/rss.xml` is valid. **Accepted with a URL allowlist** |
| Ynet | `AjaxRSSFeed.aspx?type=1025/1026/1027`, `/sport/rss`, `/sport/feed` | all 404. The official `Integration/StoryRss3.xml` was found later. **Accepted** |
| ONE | `/rss`, `/feed/`, `/sport/rss`, `/rss.xml`, homepage `<link>` scan | no news RSS. **Accepted via the public JSON API** |
| Sport5 | RSS endpoint variants | no public feed. **Scraping pilot** |
| Maariv | sport-category RSS variants | returns general news. Rejected |
| X/Twitter | — | rate-limited, needs auth, short-form. Deferred |

---

## 2. What one ingestion pass does

Every trigger (worker tick, startup catch-up, `POST /api/ingest/run`,
`POST /api/ingest/scheduler/run-now`) goes through `orchestrate_cycle()` in
`app/ingestion/orchestration.py`, behind the durable single-flight lease. Per source,
`run_ingestion()` → `_run_source()` (`app/ingestion/ingestion_service.py`) runs these steps:

```
adapter.fetch()                       adapters/factory.py → rss | sport5 | one; never raises
  → _should_filter()                  blocked_url_patterns → allowed_url_patterns → allowed_languages
  → URL dedup                         article id = rss_<sha1(url)[:20]>; existing URL → skipped_duplicate
  → _normalise()                      new items only:
      language detection              (URL path → Unicode script → Italian heuristic → source default)
      translation                     disabled in the MVP; Hebrew never translates
      published_at normalisation      missing → bounded ingest-time fallback; >15 min future → clamped (#174)
      source URL sport hint
      deterministic classify()        title first; the subtitle only fills gaps
      LLM gate → provider → merge     Hebrew broad sources only, when CLASSIFICATION_PROVIDER != disabled
      league/sport normalisation, basketball entity enrichment
      build_article_facts()           evidence-weighted sport, explicit competitions, entity_ids, trace
      post-facts event re-validation  event semantic evidence; unsupported → news (+ abstention reason)
  → insert (articles)
  → story-anchor enrichment           always on, deterministic (#141)
  → clustering stage                  CLUSTERING_ENABLED; failure leaves articles unclustered
```

After all sources, the cycle runs notification planning, then dispatch (Telegram, when
enabled), then the results sync (when enabled and not throttled), then retention cleanup
(currently disabled). Each stage failure degrades the cycle to `succeeded_with_warnings` and
never invalidates the ingestion. See [SCHEDULER.md](SCHEDULER.md) and
[NOTIFICATIONS.md](NOTIFICATIONS.md).

**Stored rows are never reclassified by ingestion.** A classifier change reaches only newly
ingested articles. Correcting stored rows is a separate, explicit decision: a targeted, reviewed
correction script, or `POST /api/classify/backfill`. Never run a blanket rules-only backfill. It
destroys LLM-assisted facts (F-N05-6 in [qa/N05_FEED_GROUND_TRUTH.md](qa/N05_FEED_GROUND_TRUTH.md)).

### Article fields written at ingestion

| Field | Value |
|---|---|
| `id` | `rss_<sha1_of_url[:20]>`, stable and deterministic |
| `source`, `source_display_name`, `url` | from the config and the item |
| `title` | the raw Hebrew title (the translated title only when translation is active) |
| `original_title`, `translated_title` | `None` for Hebrew-native articles |
| `subtitle` | cleaned `<description>` / card text: HTML stripped, sentence-aware, ≤240 characters |
| `published_at`, `published_at_meta` | normalised publication time, UTC, plus its provenance (NULL = source-provided). This is the feed-freshness clock ([FEED_FRESHNESS.md](FEED_FRESHNESS.md)) |
| `sport`, `league`, `entities`, `event_type`, `event_certainty`, `importance`, `confidence`, `tags` | classification result after merge, facts and event validation |
| `primary_competition`, `article_competitions`, `entity_ids`, `classification_trace`, `taxonomy_version` | ArticleFacts ([ARTICLE_FACTS.md](ARTICLE_FACTS.md)) |
| `classified_by`, `classification_provider`, `classification_reason`, `classification_confidence` | LLM provenance (`rules`, `llm`, `llm+rules_guardrail`, `rules_fallback_*`); a provider label such as `ollama:qwen2.5:3b-instruct` |
| `story_anchors`, `anchor_validator_version`, `cluster_id` | clustering facts ([CLUSTERING.md](CLUSTERING.md)) |

### Deduplication vs clustering

URL dedup (`app/ingestion/dedup.py`) is exact: the same URL is the same article. It is
independent of **story clustering**, which groups different URLs that report one real-world
story, cross-source and intra-source. Clustering is active in production and documented in
[CLUSTERING.md](CLUSTERING.md). The two mechanisms never share state.

---

## 3. Run results and persistence

`POST /api/ingest/run` returns one `SourceIngestResult` per source (`app/models/ingestion.py`):

- **counts:** `fetched`, `inserted`, `skipped_filtered`, `skipped_duplicate`, `failed`, `errors`
- **timing and LLM:** `fetch_ms`, `total_ms`, `llm_attempts`, `llm_successes`, typed
  fallbacks (`connect_error`, `timeout`, `http_error`, `bad_response_shape`, `unparseable_json`,
  `low_confidence`, plus the legacy `timeout_or_parse` sum), `llm_avg_ms`, `llm_p95_ms`,
  `llm_skipped`, and the skip and call reasons
- **clustering:** `clustering_ran`, `clusters_created`, `articles_appended_to_clusters`,
  `articles_left_unclustered`, `clusters_removed`, `clustering_failed`, `clustering_error`

Persisted per source and run in `ingestion_runs`: the counts except `skipped_filtered`,
`status`, `error_message`, `cycle_id`, and the **`metrics` JSON** (the LLM dependency metrics,
schema v2, issue #31; see [LLM_CLASSIFICATION.md](LLM_CLASSIFICATION.md)). Per cycle,
`scheduler_cycles` holds the trigger, status, per-source summary, notification and cleanup
summaries, and a config snapshot.

### Operating endpoints (admin-gated)

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/ingest/run[?source_id=X]` | One cycle, all effectively-enabled sources or one source (a single-source run works even when the source is disabled). Returns 409 `ingestion_already_running` while the lease is held |
| `POST` | `/api/ingest/scheduler/run-now` | Same path as a scheduled tick |
| `GET` | `/api/ingest/sources` | Sources with type, `is_pilot` and the effective `enabled` |
| `PATCH` | `/api/ingest/sources/{source_id}` | Runtime enable/disable (a persisted override) |
| `GET` | `/api/ingest/source-health` | Per-source freshness: `disabled` → `never_run` → `error` → `stale` (latest run older than 2× the interval) → `healthy` |
| `GET` | `/api/ingest/runs`, `/api/ingest/quality` | The run log, and the classification quality report (incl. the `unknown_sport` block, #194) |
| `GET` | `/api/scheduler/health`, `/api/scheduler/cycles` | Worker liveness and cycle history ([SCHEDULER.md](SCHEDULER.md)) |

The Sources page (ops console, backend mode) drives all of these.

---

## 4. Adapters

| Module | Role |
|---|---|
| `adapters/base.py` | `RawSourceItem(source_id, url, title, published_at, summary)` and the `SourceAdapter.fetch()` interface |
| `adapters/factory.py` | `build_adapter(cfg)` maps `source_type` (and, for `html_scrape`, the source id) to an adapter. Everything after `fetch()` is identical for every source type |
| `adapters/rss_adapter.py` | feedparser. Skips entries without a link or title; uses `published_parsed`/`updated_parsed` |
| `adapters/sport5_adapter.py` | httpx + BeautifulSoup (`html.parser`). The fixture-only tests use `tests/fixtures/sport5_category.html` |
| `adapters/one_adapter.py` | the ONE public JSON lists. Malformed items are tolerated one by one |

Every adapter logs failures and returns `[]`, so a source outage never fails the cycle.

## 5. Adding or changing a source

Use the `signal-source-onboarding` skill (`.claude/skills/`). In short: confirm what the site
actually serves, using this doc's probe history. Add an `RSSSourceConfig` entry, with
`allowed_url_patterns` or `blocked_url_patterns` and `allowed_languages` as needed. Add a
source-scoped URL hint only with live-page verification and corpus evidence. Use fixture-based
tests, never the live site. Then update the table in §1 and the sources section of
[CURRENT_PROJECT_STATE.md](CURRENT_PROJECT_STATE.md).
