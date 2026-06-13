# Signal Sports — Current Project State

Last updated: 2026-06-14 — reflects state after PR 10 (branch: `feature/hebrew-rss-sources-expansion`).

---

## 1. Product in One Paragraph

Signal Sports is a Hebrew-first personalized sports news intelligence feed. It aggregates real sports news from multiple RSS sources, classifies each article (sport, league, entities, event type, importance), filters noise per user preference profile, translates non-Hebrew headlines into natural Hebrew, and surfaces to each user only the articles that are actually worth their attention. The same article can be `push` for one user and `hidden` for another. The product goal is not "show all sports news" but "show only what matters to this specific user."

---

## 2. Product Principles

- **Hebrew-first UI.** Every article is displayed with a Hebrew title. Non-Hebrew articles are translated before display. Hebrew is the source language for Walla — no translation needed or stored.
- **Personalized relevance, not generic RSS.** The feed is per-user. Identical article sets produce different feeds for different profiles.
- **False positives are worse than missed classification.** When the classifier is unsure, it assigns `sport=unknown` and the article lands in debug. It does not guess and pollute the feed.
- **Translate once per article, not per user.** `translated_title` is a stored field in SQLite. Translation runs at ingestion time or via backfill. The UI reads the stored value.
- **Store original title forever.** `original_title` is written once and never overwritten. Retranslation always uses `original_title` as source so no content is lost.
- **Use debug/quality views to inspect classifier mistakes.** The debug feed shows all articles including hidden ones with full reasoning. The quality endpoint shows sport breakdowns and questionable articles.
- **Feed is core; push notifications are later.** Push exists as a decision level in the relevance engine but no device notification system is built.

---

## 3. Current Architecture

```
RSS source
  → RSSSourceAdapter (feedparser)
  → URL/language filter (blocked_url_patterns, allowed_languages)
  → language detection (URL path → Unicode script → Italian heuristic → source default)
  → translation (TranslationService → ClaudeProvider | FakeProvider | disabled)
  → deterministic classifier (sport, league, entities, event_type, importance, confidence)
  → dedup check (URL-based, stable rss_<sha1> ID)
  → SQLite (articles table)
  → relevance engine (per-user scoring: hidden / low_feed / feed / high_feed / push)
  → Feed/Debug UI (React/Vite, backend mode)
```

**Components:**

| Layer | Technology |
|-------|-----------|
| Frontend | React + Vite, `src/` |
| Backend | FastAPI (Python 3.13), `backend/app/` |
| Persistence | SQLite via SQLAlchemy 2.0, `backend/data/signal_sports.db` |
| RSS ingestion | `feedparser`, `backend/app/ingestion/` |
| Classifier | Pure deterministic keyword matching, `backend/app/ingestion/classifier.py` |
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
| `articles` | All ingested articles; `entities` and `tags` stored as JSON |
| `profiles` | User profiles; `topics` list stored as JSON |
| `sources` | RSS source configuration |
| `feedback_events` | User feedback (persists across restarts) |
| `calibration_headlines` | 16 synthetic preference calibration headlines |
| `ingestion_runs` | Log of every RSS ingestion run |

On startup: tables are created if missing; seed data is inserted only into empty tables (idempotent).

**Test suite:** 471 pytest tests across `backend/tests/`.

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

**Feed filter:** `GET /api/feed`, `GET /api/debug/feed`, and `GET /api/articles` return only articles whose `id` starts with `rss_`. Seed articles (e.g. `article_001`) are excluded from the feed but accessible via single-item lookup.

---

## 6. Frontend State

**Data mode badge:** Header pill shows "מצב נתונים: שרת" (blue, backend mode) or "מצב נתונים: מקומי" (gray, local mode).

**Sources page — Ingestion panel:** In backend mode, shows source selector, "הרץ ייבוא עכשיו" button, per-source result breakdown after run, recent runs list (last 5), and "איכות הסיווג" quality toggle. In local mode, shows a disabled card with instructions to enable backend mode.

**Translation section in ingestion panel:** `ProviderStatusBadge` (green = claude, amber = fake, gray = disabled). Backfill results show `status: "skipped"` in amber when provider not ready — never false success.

**Feed card:** Translated articles show Hebrew title as primary; original-language metadata in gray below (`שפת מקור: איטלקית · כותרת מקור: <original>`). Untranslated articles show original title with amber `לא תורגם` marker.

**Debug view:** All articles with full scoring reasoning. Comparison tab always uses local engine (cross-profile comparison not wired to backend).

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

## 8. Hebrew Classifier State

The classifier (`backend/app/ingestion/classifier.py`) is purely deterministic — keyword matching only, no NLP, no LLM.

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

**Confidence scoring:** 0.40 base + 0.15 (sport) + 0.05 (basketball-only source) + 0.15 (league) + 0.15 (entity) + 0.10 (non-news event type); capped at 0.95.

**`ambiguous_club` behavior:** When a full-name club phrase is present but no sport context resolves it, the article gets `sport=unknown`, `entities=[]`, tag `ambiguous_club`, and shows up as questionable in the quality endpoint.

**Honest limitations:**
- Standalone "מכבי" is still risky for non-basketball Maccabi clubs not yet in `_FOOTBALL_MACCABI_KW`.
- Limited player/entity extraction — only Maccabi TLV, Deni Avdija, Kattash.
- No player name extraction for NBA teams beyond direct name keyword hits.
- No title summarization or body analysis — title only.
- Walla broad feed produces many `sport=unknown` articles during football-heavy news cycles (World Cup 2026). This is correct precision-over-recall behavior, not a bug.

---

## 9. Translation Pipeline State

### Display rule
Every article in the feed shows a Hebrew title as primary. Non-Hebrew articles are translated; Hebrew articles are stored as-is.

### Article fields

| Field | Meaning |
|-------|---------|
| `title` | Hebrew title (primary display) |
| `original_title` | Raw RSS title (written once, never overwritten) |
| `translated_title` | Same as `title` after translation; `None` if not yet translated |
| `language` | Detected source language (`en`, `it`, `he`, etc.) |

### Providers

| `TRANSLATION_PROVIDER` | Behavior |
|------------------------|----------|
| `disabled` (default) | No translation; articles show original title |
| `fake` | Dev stub — known titles get realistic Hebrew, others get `"תרגום בדיקה: <original>"` |
| `claude` | Anthropic Claude API (requires `TRANSLATION_API_KEY`) |

### dotenv loading
`backend/.env` is loaded in `app/main.py` **before all other imports** via `python-dotenv`. This is critical because `TRANSLATION_PROVIDER` and `DATABASE_URL` are read at module import time.

### Language detection priority
1. URL path segment (`/it/` → Italian, `/he/` → Hebrew)
2. Unicode script of title characters
3. Italian keyword heuristic (for Sportando which has no `/it/` path)
4. Source config default (`"en"` for Eurohoops, `"he"` for Walla)

### Translation quality (PR 9.3)
The Claude provider uses a prompt that instructs "natural Hebrew sports headline an Israeli editor would publish" — not literal translation. It includes:
- **Sports glossary** (basketball + transfer terms: `accordo → סיכום`, `panchina → תפקיד המאמן`, EuroLeague → יורוליג, etc.)
- **Few-shot examples** (5 Italian → Hebrew pairs) to anchor style
- **Post-translation quality checks:**
  1. Empty / whitespace → rejected
  2. Identical to original → rejected
  3. Model explanation prefix (`"Here is the translation:"`) → rejected
  4. Latin-ratio > 60% → rejected (model returned original English)
  5. Length > 3× original → rejected (model added commentary)
  When rejected, article keeps original title with `לא תורגם` marker.

### Fake translation detection (PR 9.2)
`include_fake=true` on the backfill endpoint re-translates articles whose `title` or `translated_title` starts with `"תרגום בדיקה:"`. Uses `original_title` as source; skips if `original_title` is missing.

### Next manual step needed
After configuring `TRANSLATION_PROVIDER=claude` and `TRANSLATION_API_KEY` in `backend/.env`, run:
```
POST /api/translations/backfill?source_id=sportando&limit=5&force=true
```
Then inspect the feed or debug view for real Italian → Hebrew quality. Italian Sportando articles should have natural Hebrew headlines. No `תרגום בדיקה:` prefix.

---

## 10. Current Known Limitations

- **No scheduler.** Ingestion runs only on `POST /api/ingest/run`. APScheduler deferred.
- **`source_id` filter in translation backfill is accepted but not applied.** The `?source_id=X` query param exists in the endpoint signature but the implementation calls `get_rss_articles(session)` unconditionally and never filters by source. The `limit` param still applies, so `?source_id=sportando&limit=5` will process the first 5 articles from any source, not just Sportando.
- **No fuzzy dedup / clustering.** Deduplication is URL-only. The same story from Eurohoops and Walla appears as two separate articles. `cluster_id` field exists in the model but is never populated.
- **No feedback → profile mutation.** Feedback events are stored in SQLite but do not yet modify topic rules or event rules in user profiles.
- **No auth / multi-user.** User profiles are seeded statically. No login, no registration.
- **No push notifications.** `push` is a decision level in the engine; no device notification delivery.
- **No body translation or summaries.** Only titles are translated. Article bodies are not ingested.
- **Limited source coverage.** Eurohoops, Sportando, Walla Sport, Israel Hayom Sport. Sport5 and ONE have no clean public RSS; Ynet has no sport-specific RSS.
- **Classifier is keyword-based.** No NLP, no LLM-based classification. Entity extraction is limited to Maccabi TLV, Deni Avdija, Kattash, and three new entity values (Maccabi TLV Football, Hapoel TLV Basketball, Hapoel TLV Football).
- **Translation quality not yet validated with real API key.** PR 9.3 built the quality guardrails; real-world output quality requires a live Claude API key and a manual review run.

---

## 11. Recommended Next Steps

Priority order:

1. **Manual translation quality verification** — Configure `TRANSLATION_PROVIDER=claude` + real API key, run `POST /api/translations/backfill?source_id=sportando&limit=5&force=true`, inspect feed quality.
2. **Fix `source_id` filter in translation backfill** — The parameter is accepted but never used. Filter `all_rss` list by `article.source == source_id` before building candidates.
3. **Scheduled ingestion via APScheduler** — Poll `POST /api/ingest/run` every 15–30 minutes. Add to `app/main.py` lifespan.
4. **Feed clustering / fuzzy dedup** — Use `difflib.SequenceMatcher` on titles across sources; populate `cluster_id`. Show one card per story.
5. **Translation cache / batch translation** — Avoid re-calling the API for articles already translated; the current flow is safe but explicit batching would allow rate-limit-aware processing.
6. **Feedback → profile mutation** — `never_show` feedback creates a `hidden` event rule for the article's `event_type` in the matched topic. Requires in-place profile update via the repository.
7. **More Hebrew sources** — Sport5 via category page HTML adapter (no RSS available). ONE and Ynet have no usable RSS and were rejected in PR 10.
8. **Better entity extraction** — Extend `_MACCABI_KW`, add more Israeli coaches and players, add NBA player names for entity-specific scoring.

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
```
Set `TRANSLATION_PROVIDER=fake` for dev testing without an API key.
Set `TRANSLATION_PROVIDER=claude` with a real `TRANSLATION_API_KEY` for production-quality translation.

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
# 409 tests — all should pass
```

### Manual RSS ingestion
```
POST http://127.0.0.1:8000/api/ingest/run              # all sources
POST http://127.0.0.1:8000/api/ingest/run?source_id=eurohoops
POST http://127.0.0.1:8000/api/ingest/run?source_id=sportando
POST http://127.0.0.1:8000/api/ingest/run?source_id=walla_sport
POST http://127.0.0.1:8000/api/ingest/run?source_id=israel_hayom_sport
```
Expected for `israel_hayom_sport`: `fetched=100, inserted≈21, skipped_filtered≈79, failed=0`.
Second run: `inserted=0, skipped_duplicate≈21`.

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

המשימה הבאה (אלא אם אני אגיד אחרת): אימות איכות התרגום אחרי PR 9.3.
שלב ראשון: להגדיר `TRANSLATION_PROVIDER=claude` עם מפתח API אמיתי ב-`backend/.env`,
להריץ `POST /api/translations/backfill?source_id=sportando&limit=5&force=true`,
ולבדוק את איכות התרגום בפיד.

---
