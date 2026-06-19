# Signal Sports — Current Project State

Last updated: 2026-06-19 — reflects state after Hebrew MVP narrowing: subtitle-aware deterministic classifier, walla_sport + israel_hayom_sport active only, eurohoops/sportando disabled, translation freeze in frontend (branch: `feature/llm-first-hebrew-classification`).

---

## 1. Product in One Paragraph

Signal Sports is a personalized sports news intelligence feed. The current MVP is Hebrew-only: it ingests Hebrew-native sports news from `walla_sport` and `israel_hayom_sport`, classifies each article (sport, league, entities, event type, importance), and surfaces to each user only the articles that are actually worth their attention. The same article can be `push` for one user and `hidden` for another. Translation of non-Hebrew sources is a post-MVP capability — the backend module is intact but disabled by default. The product goal is not "show all sports news" but "show only what matters to this specific user."

---

## 2. Product Principles

- **Hebrew-first UI.** Every article is displayed with a Hebrew title. For the MVP, all active sources (`walla_sport`, `israel_hayom_sport`) are Hebrew — no translation is needed or used. The translation module is intact in the backend and can be re-enabled post-MVP for English sources.
- **Personalized relevance, not generic RSS.** The feed is per-user. Identical article sets produce different feeds for different profiles.
- **False positives are worse than missed classification.** When the classifier is unsure, it assigns `sport=unknown` and the article lands in debug. It does not guess and pollute the feed.
- **Translation is post-MVP.** `TRANSLATION_PROVIDER=disabled` by default. The `translated_title` DB field, backend translation routes, and the entire `backend/app/translation/` module are intact and ready to be re-enabled, but the frontend no longer shows translation UI or untranslated warnings.
- **Store original title forever.** `original_title` is written once and never overwritten. Retranslation always uses `original_title` as source so no content is lost.
- **Use debug/quality views to inspect classifier mistakes.** The debug feed shows all articles including hidden ones with full reasoning. The quality endpoint shows sport breakdowns and questionable articles.
- **Feed is core; push notifications are later.** Push exists as a decision level in the relevance engine but no device notification system is built.

---

## 3. Current Architecture

```
RSS source
  → RSSSourceAdapter (feedparser)
      subtitle extracted from RSS <description> (HTML stripped, truncated 500 chars)
  → URL/language filter (blocked_url_patterns, allowed_url_patterns, allowed_languages)
  → dedup check (URL-based) — if URL already in DB, skip all downstream work
  → _normalise() [only for new articles]:
      language detection (URL path → Unicode script → Italian heuristic → source default)
      translation (TranslationService → ClaudeProvider | FakeProvider | disabled)
        — Hebrew articles skip translation entirely; non-Hebrew get translated when provider active
        — MVP: TRANSLATION_PROVIDER=disabled (default); translation is post-MVP
      deterministic classifier (title + subtitle) → sport, league, entities, event_type, importance, confidence
        — always runs; subtitle fills gaps when title is ambiguous or produces sport=unknown
        — subtitle never overrides an already-resolved sport value from the title
      [Hebrew broad sources only, when CLASSIFICATION_PROVIDER != disabled]:
        LLM classifier called with title + subtitle
          → JSON validation → confidence check (≥ 0.65)
          → merge with 5 deterministic guardrails → classified_by=llm or llm+rules_guardrail
          → on failure or low confidence: use deterministic result → classified_by=rules_fallback_*
  → SQLite insert (articles table)
  → relevance engine (per-user scoring: hidden / low_feed / feed / high_feed / push)
  → Feed/Debug UI (React/Vite, backend mode)
```

**MVP active sources:** `walla_sport` and `israel_hayom_sport` only. `eurohoops` and `sportando` are
disabled by default and treated as post-MVP / experimental. Hebrew articles are displayed using
their native Hebrew title; translation is not used in the MVP product path.

**Components:**

| Layer | Technology |
|-------|-----------|
| Frontend | React + Vite, `src/` |
| Backend | FastAPI (Python 3.13), `backend/app/` |
| Persistence | SQLite via SQLAlchemy 2.0, `backend/data/signal_sports.db` |
| RSS ingestion | `feedparser`, `backend/app/ingestion/` |
| Subtitle extraction | `backend/app/ingestion/subtitle.py` — cleans RSS `<description>` for deterministic + LLM context |
| Deterministic classifier | Keyword matching + subtitle gap-filling, `backend/app/ingestion/classifier.py` |
| LLM classification | Gemini + Ollama providers, `backend/app/classification/` |
| Relevance engine | Python: `backend/app/services/relevance_engine.py`; JS mirror: `src/engine/relevanceEngine.js` |
| Translation | `backend/app/translation/`, provider configured by `.env` |

**Frontend data modes:**

- `local` (default): uses `mockArticles.js` + frontend JS engine, no backend needed.
- `backend`: fetches from FastAPI, backend scores articles, frontend renders only.

---

## 4. Current Data Sources

### Eurohoops (`eurohoops`)
- **Language:** English
- **Feed URL:** `https://www.eurohoops.net/feed/`
- **What it covers:** EuroLeague, EuroCup, European club basketball, transfers, results
- **Quality:** Clean RSS, basketball-only, high relevance for the product's core audience
- **Guardrails:** 10+ non-English language URL patterns blocked (`/tr/`, `/es/`, `/it/`, `/el/`, etc.) + `allowed_languages=("en",)`. Without blocking, every article appears 10× in different languages.

### Sportando (`sportando`)
- **Language:** Intended as English; **actually contains Italian-language articles** — Sportando publishes a mix of English and Italian content without language-path URL markers. The Italian heuristic in `language_detection.py` handles this (keyword list: `tratta`, `panchina`, `stagione`, etc.).
- **Feed URL:** `https://sportando.basketball/feed/`
- **What it covers:** European basketball signings, transfers, NBA, agent deals — narrow but high-quality signal
- **Guardrails:** `allowed_languages=("en",)` as conservative default.

### Walla Sport (`walla_sport`)
- **Language:** Hebrew (`he`)
- **Feed URL:** `https://rss.walla.co.il/feed/7`
- **What it covers:** Israeli basketball (Maccabi TLV, Winner League, EuroCup, EuroLeague), Israeli football, international tennis (Grand Slams), NBA, World Cup / Euros. Typically 30 items per fetch.
- **This is the first Hebrew source.** Articles are stored as-is; `original_title = None`; no translation runs.
- **Known issue:** The broad Walla Sport feed includes a lot of football and generic news. During non-basketball seasons (e.g., FIFA World Cup 2026), the feed is noise-heavy. The classifier correctly downgrades most of this to `hidden` for basketball-focused profiles.

### Israel Hayom Sport (`israel_hayom_sport`)
- **Language:** Hebrew (`he`)
- **Feed URL:** `https://www.israelhayom.co.il/rss.xml` (general RSS filtered by `allowed_url_patterns=("/sport/",)`)
- **What it covers:** Israeli basketball (israeli-basketball subpath), world basketball (NBA/EuroLeague), world football (World Cup, European football), other sports (tennis, etc.), sport opinion pieces.
- **Added in PR 10.** Articles stored as Hebrew-native; `original_title = None`; no translation.
- **Filtering:** The Israel Hayom RSS is a general news feed (100 items, ~21 sport). The `allowed_url_patterns` filter accepts only URLs containing `/sport/`. Non-sport items (politics, opinion, culture) are counted as `skipped_filtered` and never reach the DB.
- **Sport5 / ONE** have no publicly accessible RSS. ONE and Ynet Sport were probed in PR 10 and confirmed unreachable. Category page scraping is deferred.

### Source infrastructure: `allowed_url_patterns` (PR 10)
- New field on `RSSSourceConfig`: `allowed_url_patterns: tuple[str, ...] = ()`
- Analogous to `blocked_url_patterns` (blocklist) but inverted (allowlist)
- Checked in `_should_filter` after `blocked_url_patterns`, before language filter
- Enables accepting sport-only articles from general-news RSS feeds via URL category path

---

## 5. Backend State

The backend is a FastAPI application in `backend/`. All state is persisted in SQLite at `backend/data/signal_sports.db`.

**SQLite tables:**

| Table | Content |
|-------|---------|
| `articles` | All ingested articles; `entities` and `tags` stored as JSON; includes 4 LLM classification metadata columns (PR 11) |
| `profiles` | User profiles; `topics` list stored as JSON |
| `sources` | RSS source configuration |
| `feedback_events` | User feedback (persists across restarts) |
| `calibration_headlines` | 16 synthetic preference calibration headlines |
| `ingestion_runs` | Log of every RSS ingestion run |

**Four new columns on `articles` (PR 11, soft-migrated via `ALTER TABLE ADD COLUMN`):**

| Column | Type | Meaning |
|--------|------|---------|
| `classified_by` | TEXT DEFAULT `'rules'` | `rules`, `llm`, `llm+rules_guardrail`, `rules_fallback_after_llm_failure`, `rules_fallback_low_confidence` |
| `classification_provider` | TEXT | `rules`, `ollama:llama3.2:3b`, `fake`, etc. |
| `classification_reason` | TEXT | LLM's one-sentence explanation of the classification |
| `classification_confidence` | REAL | LLM's self-assessed confidence (0.0–1.0); separate from the deterministic `confidence` field |

On startup: tables are created if missing; soft migrations add new columns to existing databases safely; seed data is inserted only into empty tables (idempotent).

**Test suite:** 636 pytest tests across `backend/tests/` + 215 frontend tests (Vitest).

**Key API endpoints:**

| Method | Endpoint | Notes |
|--------|----------|-------|
| `GET` | `/health` | Health check |
| `GET` | `/api/ingest/sources` | List configured RSS sources |
| `POST` | `/api/ingest/run` | Run ingestion (all or `?source_id=X`) |
| `GET` | `/api/ingest/runs` | Recent ingestion run log |
| `GET` | `/api/ingest/quality` | Classification quality report |
| `GET` | `/api/feed/{user_id}` | Scored feed (RSS articles only, hidden excluded) |
| `GET` | `/api/debug/feed/{user_id}` | All articles scored with full reasoning |
| `GET` | `/api/articles` | All RSS articles in DB |
| `GET` | `/api/articles/{id}` | Single article (includes seed articles) |
| `GET` | `/api/profiles` | All user profiles |
| `GET` | `/api/profiles/{user_id}` | Single profile |
| `POST` | `/api/feedback` | Submit feedback event |
| `GET` | `/api/feedback/{user_id}` | All feedback for user |
| `GET` | `/api/translations/status` | Current translation provider state |
| `POST` | `/api/translations/backfill` | Translate untranslated articles in DB |
| `GET` | `/api/calibration/headlines` | Synthetic calibration headlines |
| `GET` | `/api/classify/status` | Current classification provider state |
| `POST` | `/api/classify/backfill` | Reclassify existing articles with current LLM provider |

**Feed filter:** `GET /api/feed`, `GET /api/debug/feed`, and `GET /api/articles` return only articles whose `id` starts with `rss_`. Seed articles (e.g. `article_001`) are excluded from the feed but accessible via single-item lookup.

---

## 6. Frontend State

**Data mode badge:** Header pill shows "מצב נתונים: שרת" (blue, backend mode) or "מצב נתונים: מקומי" (gray, local mode).

**Sources page — Ingestion panel:** In backend mode, shows source selector (MVP active sources: וואלה ספורט, ישראל היום ספורט), "הרץ ייבוא עכשיו" button, per-source result breakdown after run, recent runs list (last 5), and "איכות הסיווג" quality toggle. No translation UI — translation is post-MVP and was removed from the Sources page. In local mode, shows a disabled card with instructions to enable backend mode.

**Feed card:** Renders the Hebrew-native article title directly. For MVP Hebrew sources, `translatedTitle` is always `null` and the card falls back to `title` (the raw Hebrew RSS title). No original-language metadata block, no untranslated badge, no "לא תורגם" warning. The title fallback logic (`item.translatedTitle || item.title`) is preserved so the card works correctly when English sources are re-enabled post-MVP.

**Debug view:** All articles with full scoring reasoning. Each article card shows LLM classification metadata (PR 11): `classified_by` as a color-coded badge (grey=rules, blue=llm, yellow=llm+rules_guardrail, red=failure, orange=low-confidence), `classification_provider` inline, `classification_confidence` as a percentage, and `classification_reason` as an italic line. Comparison tab always uses local engine (cross-profile comparison not wired to backend).

**Local mode:** Remains fully functional with mock data. No backend required. The frontend engine (`relevanceEngine.js`) is kept.

---

## 7. User Profiles / Relevance Logic

**Decision levels:**

| Level | Meaning |
|-------|---------|
| `hidden` | Not shown in feed; visible only in debug |
| `low_feed` | Visible but low priority |
| `feed` | Normal relevance |
| `high_feed` | Important, elevated |
| `push` | Urgent — "stop and read this" |

Push must be rare. If more than a handful of articles per day reach push, the engine is too aggressive.

**Demo profile: Guy (basketball power user)**
- Maccabi Tel Aviv Basketball: `entity` scope, very high priority — signing/negotiation/injury → `push`
- NBA: `league` scope, high priority, mode `all` — most events visible
- EuroLeague: `league` scope — high priority, non-Maccabi transfers → `high_feed` not `push`
- Israeli Basketball League: `league` scope — high priority
- European domestic basketball (ACB, BSL, Greek, LBA, LNB): `league_group` scope — moderate priority
- Football: `sport` scope, mode `major_only` — most football is `hidden`
- Tennis: `sport` scope, mode `titles_only` — only Grand Slam winners/finals visible

**Demo profile: Casual Deni Fan**
- Deni Avdija: `entity` scope, very high priority — trade/injury → `push`
- NBA: `league` scope, `followed_entities_only` mode — only articles mentioning Deni are visible
- Other basketball: `hidden` unless Deni is present

**Scope guards** prevent topic rules from bleeding across articles. A `maccabi_tel_aviv_basketball` topic (entity scope) only matches when the article's entities include Maccabi TLV — not all basketball articles. Without this, Maccabi-level `push` rules would fire on unrelated EuroLeague transfers.

**Entity event rules** (`entityEventRules`) allow per-entity overrides. Example: within the EuroLeague topic, a Maccabi TLV signing → `push`, but a non-Maccabi EuroLeague signing → `high_feed`.

---

## 8. Classification State

### 8a. Deterministic Classifier (`backend/app/ingestion/classifier.py`)

The deterministic classifier is keyword-matching only — no NLP, no LLM. It always runs first, for all sources. For English basketball-only sources (`eurohoops`, `sportando`), it is the sole classifier. For Hebrew broad sources, its result is used as guardrail input when LLM is enabled.

**What it detects reliably:**
- Maccabi Tel Aviv Basketball (English + Hebrew forms, including standalone "מכבי")
- Deni Avdija ("דני אבדיה", "אבדיה", "avdija", "deni")
- Oded Kattash ("קטש", "עודד קטש") as a strong Maccabi TLV basketball signal
- Israeli Basketball League: direct keywords ("ווינר סל", "ליגת העל סל", "הפועל תל אביב") + context inference (known domestic league opponents + Maccabi entity)
- NBA Hebrew nicknames (וויזארדס, הורנטס, בלייזרס, ניקס, סלטיקס)
- EuroCup vs EuroLeague disambiguation (EuroCup checked first)
- Football Maccabi clubs blocked before basketball keywords (`_FOOTBALL_MACCABI_KW`: מכבי חיפה, מכבי נתניה, מכבי פ"ת, מכבי יפו, etc.)
- Hapoel Tel Aviv disambiguation: resolved to basketball or football based on sport context; `ambiguous_club` tag when no context
- Hebrew event types: negotiation before signing (prevents "על סף חתימה" from misfiring as signing)
- Generic news with no entity → `importance=low` (prevents filler from polluting feed)
- **PR 11 fix:** `"אלופת"` and `"אלופות"` added to `_WINNER_SUFFIX_KW`. These use regular pe (פ U+05E4) unlike "אלוף" (final pe ף U+05E3) — the Python `in` operator returned `False` for `"אלוף" in "אלופת"`. This fixes "ניו יורק אלופת ה-NBA" → `event_type=title_win`.
- **PR 11 fix:** `"mvp"` added to `_BASKETBALL_KW`. "MVP" is unambiguously basketball in Israeli sports context.

**Confidence scoring:** 0.40 base + 0.15 (sport) + 0.05 (basketball-only source) + 0.15 (league) + 0.15 (entity) + 0.10 (non-news event type); capped at 0.95.

**`ambiguous_club` behavior:** When a full-name club phrase is present but no sport context resolves it, the article gets `sport=unknown`, `entities=[]`, tag `ambiguous_club`, and shows up as questionable in the quality endpoint.

**Known gaps (require LLM):** Multi-sport entities (Olympiacos, Hapoel TLV without context), unfamiliar Hebrew proper nouns (player/coach names not in keyword lists), NBA league context from player name alone (e.g., Brunson → NBA).

### 8b. LLM Classification (`backend/app/classification/`)

LLM classification is an opt-in overlay for Hebrew broad sources only. It does not change feed decision logic — the relevance engine still reads stored metadata deterministically.

**When it runs:** `source_id in {"walla_sport", "israel_hayom_sport"}` AND `CLASSIFICATION_PROVIDER != disabled`.

**Provider options (`CLASSIFICATION_PROVIDER` env var):**

| Provider | Behavior |
|----------|---------|
| `disabled` (default) | LLM path skipped entirely; behavior identical to pre-PR 11 |
| `fake` | Pre-set results for known test headlines; unknown headlines → rules fallback |
| `gemini` | Google Gemini API via `google-genai` SDK; requires `CLASSIFICATION_API_KEY` (Google AI Studio key). Free tier: 20 requests/day (`gemini-2.5-flash-lite` preview) — not enough for production ingestion. Retries once on 429. |
| `ollama` | Calls local Ollama instance; no GPU required; recommended model `qwen2.5:3b-instruct` |

**LLM pipeline:**
1. Deterministic classifier runs first (always)
2. Subtitle extracted from RSS `<description>` via `subtitle.py` (HTML stripped, entities unescaped, truncated to 500 chars)
3. LLM called with Hebrew title + optional subtitle (as `Headline: …\nSubtitle: …`) + 6-shot prompt
4. JSON response validated against strict enum sets (`ALLOWED_SPORTS`, `ALLOWED_LEAGUES`, `ALLOWED_EVENT_TYPES`, `ALLOWED_IMPORTANCES`)
5. If `confidence < 0.65` → `classified_by = "rules_fallback_low_confidence"`, rules result kept
6. If confidence ≥ 0.65 → merge with 5 deterministic guardrails:
   - Guardrail 1: football Maccabi clubs detected → sport = football, LLM overruled
   - Guardrail 2: LLM sport=unknown → use rules sport
   - Guardrail 3: LLM league=null → use rules league
   - Guardrail 4: rules found specific event_type but LLM says "news" → use rules
   - Guardrail 5: importance never downgraded (rules high → LLM low: keep high)
7. Entities: rules entities pruned for sport compatibility (basketball club entities removed when final sport ≠ basketball); LLM entities normalized through alias map and appended
8. Defense-in-depth: relevance engine entity scope matching checks `topic.sport` vs `article.sport` — a football article cannot match a basketball entity topic even if entities contain a stale basketball club name

**Per-run circuit breaker:** The first `httpx.ConnectError` (Ollama not running) opens a circuit for the rest of that ingestion run. Remaining articles use rules immediately (~2s total overhead, not 30 × 2s). Timeouts do not open the circuit. The circuit resets on the next `POST /api/ingest/run`.

**Backfill endpoint:** `POST /api/classify/backfill` reclassifies existing articles. Updates all 11 classification fields (sport, league, entities, event_type, importance, confidence, tags, classified_by, classification_provider, classification_reason, classification_confidence). Use after enabling Ollama on a database with existing articles.

See `docs/LLM_CLASSIFICATION.md` for full architecture details.

---

## 9. Translation Pipeline State (Post-MVP — Preserved, Not Active)

Translation is not used in the current MVP. All active sources (`walla_sport`, `israel_hayom_sport`) are Hebrew-native — no translation is needed. `TRANSLATION_PROVIDER=disabled` is the default and the correct MVP setting.

The translation module is preserved intact for post-MVP re-enablement when English sources (eurohoops, sportando) are added back. No translation code was deleted.

### What is preserved

| Component | Status |
|-----------|--------|
| `backend/app/translation/` | Intact — ClaudeProvider, FakeProvider, NoopProvider |
| `backend/app/api/routes_translation.py` | Intact — `/api/translations/status` and `/api/translations/backfill` routes still respond |
| `articles.original_title`, `articles.translated_title` | DB fields intact |
| All existing translation tests | Pass unchanged |

### What was removed (frontend translation freeze)

- `TranslationSection` component in `IngestionPanel.jsx` (backfill UI)
- `ProviderStatusBadge` in `IngestionPanel.jsx`
- Original-language metadata block in `FeedCard.jsx` ("שפת מקור", "כותרת מקור", "לא תורגם")
- `backfillTranslations()` and `getTranslationStatus()` exports from `client.js`

### Article title fields

| Field | MVP behavior |
|-------|-------------|
| `title` | Raw Hebrew RSS title (same as the original) |
| `original_title` | `None` for Hebrew-native articles |
| `translated_title` | `None` — provider is disabled |
| `language` | `"he"` for all active MVP sources |

### Language detection priority (preserved for post-MVP)
1. URL path segment (`/it/` → Italian, `/he/` → Hebrew)
2. Unicode script of title characters
3. Italian keyword heuristic (for Sportando which has no `/it/` path)
4. Source config default (`"en"` for Eurohoops, `"he"` for Walla)

### Next manual step
**Not translation** — the next manual step is the LLM classification benchmark with Ollama/Qwen. See Section 11 and the handoff prompt in Section 13. Translation quality verification is a post-MVP concern for when English sources are re-enabled.

---

## 10. Current Known Limitations

- **No scheduler.** Ingestion runs only on `POST /api/ingest/run`. APScheduler deferred.
- **No fuzzy dedup / clustering.** Deduplication is URL-only. The same story from Eurohoops and Walla appears as two separate articles. `cluster_id` field exists in the model but is never populated.
- **No feedback → profile mutation.** Feedback events are stored in SQLite but do not yet modify topic rules or event rules in user profiles.
- **No auth / multi-user.** User profiles are seeded statically. No login, no registration.
- **No push notifications.** `push` is a decision level in the engine; no device notification delivery.
- **No body translation or summaries.** Only titles are translated. Article bodies are not ingested.
- **Limited source coverage.** MVP active sources: Walla Sport, Israel Hayom Sport. Eurohoops and Sportando are disabled (post-MVP). Sport5 and ONE have no clean public RSS; Ynet has no sport-specific RSS. If a third Hebrew source is added post-MVP, ONE is the preferred candidate.
- **LLM classification not yet validated at production scale.** Two providers are implemented: `gemini` (fast, cloud, but only 20 requests/day free tier — exhausted in one ingestion run) and `ollama` (local, uncapped, needs Ollama installed and `qwen2.5:3b-instruct` pulled). Default is `disabled`. Hebrew articles use deterministic classification until a provider is configured.
- **Entity normalization map is conservative.** Only explicitly listed canonical aliases are mapped. New players, coaches, clubs not yet in `_ENTITY_ALIASES` are silently discarded from `article.entities` even when LLM identifies them correctly. Expand `entity_normalizer.py` to cover new entities.
- **Translation not active in MVP.** `TRANSLATION_PROVIDER=disabled` is correct for Hebrew-only MVP. Backend module, DB fields, and API routes are preserved for post-MVP re-enablement. Translation quality validation is a post-MVP concern.

---

## 11. Recommended Next Steps

Priority order:

1. **LLM classification benchmark** — Install Ollama, pull `qwen2.5:3b-instruct`, set `CLASSIFICATION_PROVIDER=ollama` + `CLASSIFICATION_MODEL=qwen2.5:3b-instruct` + `CLASSIFICATION_TIMEOUT_SECONDS=30`, re-ingest Walla + Israel Hayom, compare `sport=unknown` count and Guy's feed visibility before/after. Run `POST /api/classify/backfill?source_id=walla_sport` on existing articles. If quality is poor, try `qwen3:4b`.
2. **Expand entity normalization map** — Add recognized Israeli basketball players, coaches, EuroLeague club names to `backend/app/classification/entity_normalizer.py` after LLM benchmark reveals which entities are being identified but discarded.
3. **Scheduled ingestion via APScheduler** — Poll `POST /api/ingest/run` every 15–30 minutes. Add to `app/main.py` lifespan.
4. **Feed clustering / fuzzy dedup** — Use `difflib.SequenceMatcher` on titles across sources; populate `cluster_id`. Show one card per story.
5. **Feedback → profile mutation** — `never_show` feedback creates a `hidden` event rule for the article's `event_type` in the matched topic. Requires in-place profile update via the repository.
6. **More Hebrew sources** — ONE Sport via category page HTML adapter is the preferred next source (traditional HTML, no SPA). Sport5 has no clean RSS. Ynet is harder (SPA).
7. **Better relevance for LLM-classified articles** — Some LLM-classified articles land in Guy's feed as `feed` when they deserve `high_feed` or `push`. The relevance engine's topic rules may need tuning once LLM entity extraction surfaces more entities (e.g., New York Knicks → Knicks entity → entity_event_rules fires).
8. **Re-enable English sources + translation** (post-MVP) — Set `eurohoops.enabled=True` in `config.py`, configure `TRANSLATION_PROVIDER=claude` + API key, run translation backfill, verify Italian → Hebrew quality.

---

## 12. How to Run Locally

### Backend
```bash
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Interactive API docs: http://127.0.0.1:8000/docs

### Backend `.env` (create at `backend/.env`)
```
DATABASE_URL=sqlite:///./data/signal_sports.db
TRANSLATION_PROVIDER=disabled
TRANSLATION_API_KEY=
TRANSLATION_MODEL=claude-haiku-4-5-20251001
CLASSIFICATION_PROVIDER=disabled
CLASSIFICATION_MODEL=qwen2.5:3b-instruct
CLASSIFICATION_API_KEY=
CLASSIFICATION_OLLAMA_BASE_URL=http://localhost:11434
CLASSIFICATION_TIMEOUT_SECONDS=30
ALLOW_DEV_RESET=false
```
Set `TRANSLATION_PROVIDER=fake` for dev testing without an API key.
Set `TRANSLATION_PROVIDER=claude` with a real `TRANSLATION_API_KEY` for production-quality translation.
Set `CLASSIFICATION_PROVIDER=ollama` after running `ollama pull qwen2.5:3b-instruct` to enable LLM classification for Hebrew broad sources.
Set `CLASSIFICATION_PROVIDER=gemini` with a `CLASSIFICATION_API_KEY` (Google AI Studio key) for cloud-based LLM classification. Note: free tier is 20 requests/day for `gemini-2.5-flash-lite` — not suitable for production ingestion at scale.
Set `CLASSIFICATION_PROVIDER=fake` to test the LLM classification path in dev without Ollama installed.
Set `ALLOW_DEV_RESET=true` only for local QA sessions (enables `POST /api/dev/reset-rss-data`). Never enable in production.

### Frontend in backend mode
Create `frontend/.env.local`:
```
VITE_DATA_MODE=backend
VITE_API_BASE_URL=http://127.0.0.1:8000
```
Then:
```bash
cd frontend
npm run dev
```
App runs at http://localhost:5173. Header badge shows "מצב נתונים: שרת".

### Frontend in local mode (default, no backend needed)
```bash
cd frontend
npm run dev
```
No `.env.local` needed. Uses mock data and frontend engine.

### Running tests
```bash
cd backend
.venv\Scripts\python.exe -m pytest tests/ -v
# 636 tests — all should pass (no test requires Ollama running or a real API key)
# Note: test_reset_returns_403_when_disabled requires ALLOW_DEV_RESET unset or =false in .env
```

### Manual RSS ingestion
```
POST http://127.0.0.1:8000/api/ingest/run                                        # MVP active sources only
POST http://127.0.0.1:8000/api/ingest/run?source_id=walla_sport                  # Hebrew — active
POST http://127.0.0.1:8000/api/ingest/run?source_id=israel_hayom_sport           # Hebrew — active
# POST http://127.0.0.1:8000/api/ingest/run?source_id=eurohoops                  # disabled — set enabled=True in config.py to re-enable
# POST http://127.0.0.1:8000/api/ingest/run?source_id=sportando                  # disabled — set enabled=True in config.py to re-enable
```
`POST /api/ingest/run` (no source_id) only runs sources with `enabled=True` in `config.py`.
For MVP this means `walla_sport` + `israel_hayom_sport` only.

Expected for `israel_hayom_sport`: `fetched=100, inserted≈21, skipped_filtered≈79, failed=0`.
Second run: `inserted=0, skipped_duplicate≈21`.

### Manual classification backfill (LLM)
```
# Check current classification provider state
GET http://127.0.0.1:8000/api/classify/status

# Reclassify Walla articles not yet classified by LLM (requires CLASSIFICATION_PROVIDER=ollama)
POST http://127.0.0.1:8000/api/classify/backfill?source_id=walla_sport

# Dry run preview (see which articles would be reclassified)
POST http://127.0.0.1:8000/api/classify/backfill?source_id=walla_sport&dry_run=true

# Force reclassify ALL Walla articles regardless of classified_by value
POST http://127.0.0.1:8000/api/classify/backfill?source_id=walla_sport&force=true
```

### Manual translation backfill
```
# Dry run preview
POST http://127.0.0.1:8000/api/translations/backfill?dry_run=true

# Translate untranslated articles
POST http://127.0.0.1:8000/api/translations/backfill

# Re-translate fake stubs after switching to real provider
POST http://127.0.0.1:8000/api/translations/backfill?include_fake=true

# Force re-translate 5 Sportando articles for quality check
POST http://127.0.0.1:8000/api/translations/backfill?source_id=sportando&limit=5&force=true
```

### Reset local database
```bash
cd backend
del data\signal_sports.db
# Restart backend — tables and seed data recreated automatically
```

---

## 13. Handoff Prompt for a New Chat

Copy-paste this into a new conversation:

---

אנחנו ממשיכים את פרויקט Signal Sports.

קרא את הקובץ `docs/CURRENT_PROJECT_STATE.md` — הוא מכיל סיכום מדויק של מצב הפרויקט.

כמה כללים לשיח:
- ענה בעברית.
- היה ישיר ומעשי.
- אל תניח הנחות לגבי מצב הקוד — אם לא ברור, שאל לפני שאתה ממשיך.
- אל תשנה קוד בלי שביקשתי.

המשימה הבאה (אלא אם אני אגיד אחרת): בנצ'מארק של סיווג LLM עם Ollama + Qwen.

שלבים:
1. להתקין Ollama (אם לא מותקן) ולהריץ `ollama pull qwen2.5:3b-instruct`
2. להגדיר ב-`backend/.env`:
   ```
   CLASSIFICATION_PROVIDER=ollama
   CLASSIFICATION_MODEL=qwen2.5:3b-instruct
   CLASSIFICATION_TIMEOUT_SECONDS=30
   ```
3. למחוק את ה-DB: `del backend\data\signal_sports.db`
4. להריץ ייבוא: `POST /api/ingest/run?source_id=walla_sport` ו-`POST /api/ingest/run?source_id=israel_hayom_sport`
5. לבדוק את `GET /api/ingest/quality` — כמה `sport=unknown` נשארו?
6. לפתוח את ה-Debug view עבור Guy — אילו כתבות עכשיו נראות שלא היו נראות קודם?
7. לבדוק שלא יש false positives (כתבות כדורגל שסווגו כסל)
8. אם האיכות לא מספיקה — לנסות `qwen3:4b` כחלופה

הקשר: ניסינו Gemini בתחילה אבל גירסת ה-preview (`gemini-2.5-flash-lite`) מוגבלת ל-20 בקשות ביום בחינמית — לא מספיק לאפילו ריצת ייבוא אחת של 28 כתבות. עברנו ל-Ollama+Qwen שלא מוגבל.

תיעוד: `docs/LLM_CLASSIFICATION.md` מכיל את כל הפרטים הטכניים של מודול הסיווג.

---
