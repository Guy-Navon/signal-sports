---
name: signal-source-onboarding
description: Use when adding a new sports news source (RSS or HTML-scraping) or changing an existing source's config, adapter, fetch/parse behavior, or enablement in Signal Sports. Triggers on requests like "add a new source", "onboard <site>", "why is <source> failing", or edits to backend/app/ingestion/config.py or adapters.
---

Follow the repository's existing source pattern — do not invent a parallel architecture.
Read `docs/RSS_INGESTION.md` ("Adding a new RSS source") and `docs/HEBREW_RSS_SOURCE.md` first;
they document the source types that already exist. Do not repeat their content here — read them.

## Architecture to reuse

- `backend/app/ingestion/config.py` — `RSSSourceConfig` dataclass, one entry per source in `RSS_SOURCES`.
- `backend/app/ingestion/adapters/factory.py` — `build_adapter(cfg)` maps `source_type` (`"rss"` | `"html_scrape"`) to an adapter. New source types plug in here, not into `ingestion_service.py`.
- Existing implementations to model on: `rss_adapter.py` (feedparser), `sport5_adapter.py` (httpx + BeautifulSoup DOM scraping), and the ONE adapter (public JSON article endpoints under the `html_scrape` type).
- Everything downstream of `fetch()` (filters, dedup, classification, ArticleFacts, persistence, relevance) is source-type-agnostic — a new source gets the full facts pipeline automatically; do not duplicate any of it per source.

## Checklist — inspect and handle each as applicable

1. **Config & enablement** — new `RSSSourceConfig` entry; decide `enabled` default. MVP is Hebrew-only with four active sources: `walla_sport`, `israel_hayom_sport`, `ynet_sport`, `one_sport` (+ `sport5_sport` as a disabled-by-default pilot). Everything new defaults `False` until explicitly promoted. Do not flip an existing source's `enabled` default without being asked. Runtime overrides live in the `source_overrides` table (via `PATCH /api/ingest/sources/{id}`) and win over config defaults.
2. **RSS vs scraping vs public JSON** — confirm what the site actually serves; don't assume. `docs/HEBREW_RSS_SOURCE.md` lists candidates already probed and rejected (`backend/scripts/probe_hebrew_rss.py` is the probing tool); ONE's RSS probes 404'd, which is why it uses its public JSON endpoints.
3. **Fetch & parse** — adapter must never raise; on any network/parse failure it returns `[]` and logs (see `sport5_adapter.py`). This is a hard invariant. One source failing must never abort the whole ingestion run.
4. **Title/subtitle extraction** — route description/card text through `backend/app/ingestion/subtitle.py::clean_subtitle()` (HTML-stripped, sentence-aware, ≤240 chars). Do not write a second subtitle-cleaning path — the subtitle feeds the classifier, the LLM, and the facts evidence weights (subtitle = weight 60).
5. **Publish timestamps** — RSS: `published_parsed`/`updated_parsed`. Non-RSS: parse the site's own format and convert to UTC with a real timezone (see Sport5's `DD.MM.YY - HH:MM` → `Asia/Jerusalem`, DST-aware); fall back to ingest time only when nothing is parseable.
6. **Hebrew/language handling** — set `language`, `allowed_languages`, `blocked_url_patterns`/`allowed_url_patterns` (see `docs/RSS_QUALITY_GUARDRAILS.md` §1). The MVP decision is Hebrew-only; non-Hebrew sources (`eurohoops`, `sportando`) stay disabled — preserve that unless the task explicitly says otherwise.
7. **Source-specific hints** — a URL/category sport signal (like Israel Hayom paths, Sport5 `FolderID=274`, Ynet sport paths, ONE category IDs) goes in `backend/app/classification/source_hints.py::extract_source_sport_hint` — not into classifier keyword lists. Source hints are the *highest-weight* sport evidence (100) in the facts stage, so a wrong hint is worse than no hint.
8. **Dedup** — URL-based, handled generically in `dedup.py`; no source-specific dedup logic.
9. **LLM gating membership** — if the source is a Hebrew broad source that should get the LLM overlay, add it to **both** independent `_HEBREW_BROAD_SOURCES` frozensets: `backend/app/ingestion/ingestion_service.py` (gates the LLM call) and `backend/app/api/routes_classify.py` (scopes backfill). They are not derived from one another and drift — existing tests assert membership in both (see `test_one_adapter.py` / `test_ynet_rss.py` for the pattern to copy).
10. **Taxonomy impact** — a new source surfaces new clubs/players. Unregistered entities raise the LLM call rate and lower entity recall. After the first real ingestion, review `GET /api/ingest/quality` (questionable articles, `llm_dependency_runs` call rate) and hand recurring unregistered entities to `signal-taxonomy-change` — with real-coverage evidence, per its rules.
11. **Metrics & observability** — ingestion writes `ingestion_runs` rows with the #31 metrics dict automatically; freshness surfaces via `GET /api/ingest/source-health`. Don't build a parallel metrics path.
12. **Backend tests** — model on the closest existing file: `test_source_config.py` (config shape), `test_ingestion_rss.py` / `test_sport5_adapter.py` / `test_one_adapter.py` / `test_ynet_rss.py` (adapter against a fixture in `backend/tests/fixtures/`, never the live site), `test_source_hints.py`, `test_source_health.py`.
13. **Frontend visibility** — the Sources page derives from the API; a new source normally needs no frontend change beyond a correct `display_name`. Only touch `frontend/src/components/ops/*` if the task changes toggle/health UI behavior itself.
14. **Real-data validation** — run one manual ingestion (`POST /api/ingest/run?source_id=<id>`), then inspect the new rows' classification quality in Debug per `signal-real-data-qa` before recommending enablement.
15. **Docs** — update the configured-sources table in `docs/RSS_INGESTION.md` and `docs/CURRENT_PROJECT_STATE.md` §4; then `signal-doc-truth` scope checks.

## Do not

- Do not add real translation or re-enable English sources (`eurohoops`, `sportando`) as a side effect — explicitly deferred (`docs/CURRENT_PROJECT_STATE.md` §9/§11).
- Do not branch `ingestion_service.py` per source; extend the adapter/factory/config pattern.
- Do not scrape a site that has working RSS, and do not onboard a source the probe script already rejected without re-probing.
