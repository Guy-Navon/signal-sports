---
name: signal-source-onboarding
description: Use when adding a new sports news source (RSS or HTML-scraping) or changing an existing source's config, adapter, fetch/parse behavior, or enablement in Signal Sports. Triggers on requests like "add a new source", "onboard <site>", "why is <source> failing", or edits to backend/app/ingestion/config.py or adapters.
---

Follow the repository's existing source pattern — do not invent a parallel architecture.
Read `docs/RSS_INGESTION.md` ("Adding a new RSS source") and `docs/HEBREW_RSS_SOURCE.md` first;
they document the two source types that already exist. Do not repeat their content here — read them.

## Architecture to reuse

- `backend/app/ingestion/config.py` — `RSSSourceConfig` dataclass, one entry per source in `RSS_SOURCES`.
- `backend/app/ingestion/adapters/factory.py` — `build_adapter(cfg)` maps `source_type` (`"rss"` | `"html_scrape"`) to an adapter. New source types plug in here, not into `ingestion_service.py`.
- `backend/app/ingestion/adapters/rss_adapter.py` (feedparser) vs `sport5_adapter.py` (httpx + BeautifulSoup) — the two existing implementations to model a new adapter on.
- Everything downstream of `fetch()` (filters, dedup, classification, persistence) is source-type-agnostic — do not duplicate it per source.

## Checklist — inspect and handle each as applicable

1. **Config & enablement** — new `RSSSourceConfig` entry; decide `enabled` default (MVP is Hebrew-only: `walla_sport`, `israel_hayom_sport` active; everything else defaults `False` until explicitly promoted). Do not flip an existing source's `enabled` default without being asked.
2. **RSS vs scraping** — pick `source_type` based on whether the site has real RSS (confirm — don't assume; `docs/HEBREW_RSS_SOURCE.md` lists candidates already probed and rejected).
3. **Fetch & parse** — adapter must never raise; on any network/parse failure it returns `[]` and logs (see `sport5_adapter.py` fragility handling). This is a hard invariant, not a nice-to-have.
4. **Title/subtitle extraction** — route the description/card text through `backend/app/ingestion/subtitle.py::clean_subtitle()` (HTML-stripped, sentence-aware, ≤240 chars). Do not write a second subtitle-cleaning path.
5. **Publish timestamps** — RSS: `published_parsed`/`updated_parsed`. Non-RSS (scrape): parse the site's own timestamp format and convert to UTC with a real timezone (see Sport5's `DD.MM.YY - HH:MM` → `Asia/Jerusalem` handling); fall back to ingest time only when no timestamp is parseable.
6. **Hebrew/language handling** — set `language`, `allowed_languages`, and any `blocked_url_patterns`/`allowed_url_patterns` needed (see `docs/RSS_QUALITY_GUARDRAILS.md` §1). The MVP product decision is Hebrew-only, non-Hebrew sources stay disabled — preserve that unless the task explicitly says otherwise.
7. **Source-specific hints** — if the source has a URL/category signal for sport (like Israel Hayom paths or Sport5 `FolderID=274`), add it to `backend/app/classification/source_hints.py::extract_source_sport_hint`, not to the classifier's keyword lists.
8. **Dedup** — URL-based, handled generically in `dedup.py`; a new source needs no source-specific dedup logic.
9. **Classification compatibility** — if the source is a Hebrew broad source that should get the LLM overlay, it must be added to **both** independent `_HEBREW_BROAD_SOURCES` definitions: `backend/app/ingestion/ingestion_service.py` (gates the LLM call during ingestion) and `backend/app/api/routes_classify.py` (scopes the `/api/classify/backfill` endpoint). These two sets are not derived from one another and can drift — check both.
10. **Metrics & observability** — ingestion writes to the `ingestion_runs` table and reports `fetch_ms`/`llm_avg_ms`/`llm_p95_ms` (see `docs/LLM_CLASSIFICATION.md` "Ingestion Timing Instrumentation"); source freshness surfaces via `GET /api/ingest/source-health`. Don't build a parallel metrics path.
11. **Per-source failure isolation** — one source failing must not abort the whole ingestion run; confirm this holds for the new adapter (mirrors point 3).
12. **Backend tests** — add tests following the closest existing file: `test_source_config.py` (config shape), `test_ingestion_rss.py` or `test_sport5_adapter.py` (adapter behavior against a fixture, not the live site — see `backend/tests/fixtures/`), `test_source_hints.py`, `test_source_health.py`.
13. **Frontend visibility** — the Sources page (`frontend/src/pages/Sources.jsx` + `frontend/src/components/ops/{IngestionPanel,HealthCard,SourceToggleCard}.jsx`) derives from the API; a new source normally needs no frontend code change, only a correct `display_name`. Only touch these components if the task changes toggle/health UI behavior itself.
14. **Docs** — update the configured-sources table in `docs/RSS_INGESTION.md` and the source table in `docs/CURRENT_PROJECT_STATE.md` §4.

## Do not

- Do not add real translation, real scraping infra changes, or re-enable English sources (`eurohoops`, `sportando`) as a side effect — that is an explicit, separate, currently-deferred decision (`docs/CURRENT_PROJECT_STATE.md` §9/§11).
- Do not branch `ingestion_service.py` per source; extend the adapter/factory/config pattern instead.
