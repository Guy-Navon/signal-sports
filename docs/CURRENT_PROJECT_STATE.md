# Signal Sports — Current Project State

Last updated: 2026-07-04 — reflects the **frontend redesign** ("Court Vision", PRs 1–6) plus **PR A ("The Edition")** and its polish passes, **PR B ("atmosphere + brand shell")**, **PR C ("product pages")**, and **PR D ("ops shell variant")** — the full originally-approved redesign plan, all merged to `main` (currently `d209166`+; PR D in progress on branch `feature/frontend-redesign-ops-shell`). The Base44-generated QA-dashboard UI was rebuilt into a premium, Hebrew-first, RTL-first dark product with a design-token system (shadcn/ui + Tailwind + Radix, self-hosted Heebo + Frank Ruhl Libre fonts) and a product-vs-console split. PR A transformed the Feed from a scored card list into a **composed personal edition** (lead story / מבזק bulletins / "במוקד" tier / "עוד מהפיד" rows / "קריאה נוספת" digest, with a clickable signal-spectrum filter and Framer Motion entrance) under the approved "המערכת / The Desk" design concept — codename only, the product name is unchanged. PR B removed the left sidebar on product routes (ops keeps it, unchanged), replaced the plain header with a `Masthead` (wordmark, inline nav, console-entry icon) over a decorative `Atmosphere` backdrop, added a floating mobile pill nav for product routes, and wrapped route changes in a page transition. PR C brought Preferences, Calibration, and Results into the same editorial voice: a new `DeskIntro` line ("מה המערכת יודעת" / "כיול") opens Preferences and Calibration, boxed sections became hairline-divided lists, badge piles became kicker lines — with every hook/handler/`src/engine` call in Calibration's rating flow left verbatim. PR D gave the ops console its own backdrop (`OpsGrid`, a flat blueprint grid replacing the product's `Atmosphere`) and a mono breadcrumb ("המערכת ⁄ קונסולה ⁄ current page") in `OpsNav` — Sources/Debug/LLM QA page content and logic are untouched. **Backend, API contracts, and the frontend data layer (`src/context`, `src/api`, `src/engine`, `src/data`) were unchanged by the redesign** — one exception, explicitly authorized: a subtitle-excerpt fix at the ingestion layer (`backend/app/ingestion/subtitle.py`, PR A follow-up) after a user-reported bug where Walla's RSS `<description>` (the article lede) was being shown as if it were a short deck. See `docs/FRONTEND_DESIGN_SYSTEM.md`. Frontend tests: 341. Backend tests: 1081.

Prior backend state (unchanged by the redesign) reflects PR 13 + PR 13.1 (branch `feature/selective-llm-gating`): entity normalization expanded to 25 canonical entities, generalized post-merge basketball entity enrichment, new signing keywords, Sport5 (ערוץ הספורט) HTML-scraping pilot source (disabled by default, toggleable from the UI), scheduled ingestion loop with process-level ingestion lock (disabled by default), scheduler-status + source-health endpoints, runtime source enable/disable overrides, and the Sources page scheduler/health UI.

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
      subtitle extracted from RSS <description> (HTML stripped, sentence-aware excerpt ≤240 chars)
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
      source URL category hint extracted (extract_source_sport_hint — Israel Hayom paths + Sport5 FolderID=274)
      [Hebrew broad sources only, when CLASSIFICATION_PROVIDER != disabled]:
        should_call_llm_for_article() gate evaluated against rules result
          → sport=unknown / ambiguous_club / conf<0.55 → force call LLM
          → clear league / strong hint+context / high confidence → skip LLM
          → LLM classifier called with title + subtitle [timing measured including failures]
          → JSON validation → confidence check (≥ 0.65)
          → merge with 7 deterministic guardrails → classified_by=llm or llm+rules_guardrail
          → on failure or low confidence: use deterministic result → classified_by=rules_fallback_*
      normalize_league_sport_compatibility() — universal post-merge safety net (both paths)
  → SQLite insert (articles table)
  → relevance engine (per-user scoring: hidden / low_feed / feed / high_feed / push)
  → Feed/Debug UI (React/Vite, backend mode)
```

**MVP active sources:** `walla_sport` and `israel_hayom_sport` only. `eurohoops` and `sportando` are
disabled by default and treated as post-MVP / experimental. `sport5_sport` (ערוץ הספורט) is a Hebrew
**HTML-scraping pilot** added in PR 13 — `source_type="html_scrape"`, `is_pilot=True`, disabled by
default; run it manually with `POST /api/ingest/run?source_id=sport5_sport`. Hebrew articles are
displayed using their native Hebrew title; translation is not used in the MVP product path.

**Ingestion triggers (PR 13):** manual `POST /api/ingest/run`, `POST /api/ingest/scheduler/run-now`,
and an optional scheduled loop (`INGESTION_SCHEDULER_ENABLED=true`, default **false** — when false
the app behaves exactly as before). All three share one process-level ingestion lock; concurrent
attempts get a structured 409 (`ingestion_already_running`). The scheduler is process-local — a
future multi-replica deployment needs a single scheduler worker or a distributed lock.

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
| LLM gating | `backend/app/classification/gating.py` — per-article decision on whether to call LLM |
| Source URL hints | `backend/app/classification/source_hints.py` — URL category → sport hint (Israel Hayom paths; Sport5 FolderID=274 → basketball, PR 13) |
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

### Sport5 / ערוץ הספורט (`sport5_sport`) — scraping pilot (PR 13)
- **Language:** Hebrew (`he`); no translation, same as Walla.
- **Type:** `html_scrape` — Sport5 has **no public RSS** (confirmed PR 8/PR 10). The adapter scrapes the basketball category page (`https://www.sport5.co.il/liga.aspx?FolderID=273`, static server-rendered HTML, ~12 articles/fetch) with httpx + BeautifulSoup.
- **Status:** pilot, **disabled by default** (`enabled=False`, `is_pilot=True`). Run manually with `POST /api/ingest/run?source_id=sport5_sport`, or toggle it on from the Sources page ("בריאות מקורות" card) / `PATCH /api/ingest/sources/sport5_sport` — the runtime override persists across restarts and includes it in scheduled/all-source runs (PR 13.1).
- **Classification:** included in the Hebrew broad-source set (gated LLM path); article URLs with `FolderID=274` get a `basketball` source hint.
- **Subtitles:** the card's descriptive paragraph is extracted as the article subtitle (PR 13.2) — cleaned like RSS descriptions, shown in Feed/Debug, and fed to the classifier/LLM as context.
- **Publish time:** parsed from the card's `DD.MM.YY - HH:MM` timestamp (Israel local time → UTC, DST-aware; PR 13.3); cards without a timestamp fall back to ingest time.
- **Known limitations:** scraping is fragile to site redesigns — failures degrade to 0 items and surface in source health, never crash ingestion.
- **ONE / Ynet** still have no accessible RSS; ONE remains the preferred next scraping candidate.

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
| `articles` | All ingested articles; `entities` and `tags` stored as JSON; includes `subtitle` column and 4 LLM classification metadata columns (PR 11) |
| `profiles` | User profiles; `topics` list stored as JSON |
| `sources` | RSS source configuration |
| `feedback_events` | User feedback (persists across restarts) |
| `calibration_headlines` | 16 synthetic preference calibration headlines |
| `ingestion_runs` | Log of every RSS ingestion run |
| `source_overrides` | Runtime source enabled/disabled overrides (PR 13.1); wins over config.py defaults |

**Five soft-migrated columns on `articles` (via `ALTER TABLE ADD COLUMN`, idempotent):**

| Column | Type | Meaning |
|--------|------|---------|
| `subtitle` | TEXT | Cleaned RSS `<description>` text (HTML stripped, sentence-aware excerpt ≤240 chars — cut at the last complete sentence within budget, not mid-sentence; see `docs/LLM_CLASSIFICATION.md`); `null` for old articles and entries with no description |
| `classified_by` | TEXT DEFAULT `'rules'` | `rules`, `llm`, `llm+rules_guardrail`, `rules_fallback_after_llm_failure`, `rules_fallback_low_confidence` (PR 11) |
| `classification_provider` | TEXT | `rules`, `ollama:llama3.2:3b`, `fake`, etc. (PR 11) |
| `classification_reason` | TEXT | LLM's one-sentence explanation of the classification (PR 11) |
| `classification_confidence` | REAL | LLM's self-assessed confidence (0.0–1.0); separate from the deterministic `confidence` field (PR 11) |

On startup: tables are created if missing; soft migrations add new columns to existing databases safely; seed data is inserted only into empty tables (idempotent).

**Test suite:** 1076 pytest tests across `backend/tests/` + 286 frontend tests (Vitest).
The test environment is hermetic: `conftest.py` forces `CLASSIFICATION_PROVIDER=disabled` and
`INGESTION_SCHEDULER_ENABLED=false` regardless of the developer's `backend/.env`, so no test
requires Ollama, a real API key, or live Sport5.

**Key API endpoints:**

| Method | Endpoint | Notes |
|--------|----------|-------|
| `GET` | `/health` | Health check |
| `GET` | `/api/ingest/sources` | List configured sources (incl. `type` rss/html_scrape + `is_pilot`) |
| `POST` | `/api/ingest/run` | Run ingestion (all or `?source_id=X`); 409 if a run is active (PR 13) |
| `GET` | `/api/ingest/runs` | Recent ingestion run log |
| `GET` | `/api/ingest/quality` | Classification quality report |
| `GET` | `/api/ingest/scheduler/status` | Scheduler + lock state: enabled, running, next_run_at, last run, active_run (PR 13) |
| `POST` | `/api/ingest/scheduler/run-now` | Immediate ingestion via internal service path + shared lock; 409 when busy (PR 13) |
| `GET` | `/api/ingest/source-health` | Per-source freshness (healthy/stale/never_run/disabled/error), last counts, consecutive failures (PR 13) |
| `PATCH` | `/api/ingest/sources/{source_id}` | Enable/disable a source at runtime; persisted in `source_overrides` table, wins over config.py default (PR 13.1) |
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

**Design system (redesign 2026-07-04 + PR A + PR B):** The UI runs on the "Court Vision" token system — see `docs/FRONTEND_DESIGN_SYSTEM.md` for tokens, component inventory, and RTL rules. Key points: dark navy canvas with a semantic **signal system** (gold=push, green=high_feed, steel-blue=feed, dim=low_feed, red=hidden/errors, cyan=AI), Heebo/Frank-Ruhl-Libre fonts (serif weights 500/700), and a **product-vs-console split**: consumer pages (Feed, Preferences, Calibration, Results — full-width, no sidebar, ambient `Atmosphere` backdrop) vs an ops **console** (Sources, Debug, LLM QA — unchanged sidebar rail + steel-blue instrument panel). `<html lang="he" dir="rtl">` with logical-only Tailwind utilities. Both data modes work on every page. Components live under `src/components/{shared,shell,feed,ops,debug,preferences}`. The redesign, PR A, and PR B preserved every capability below and changed no backend/API/data-layer code (the one authorized exception is the ingestion subtitle fix, noted above).

**Data mode indicator:** `DataModeBadge` in the masthead — a pulsing dot + tooltip ("מצב נתונים: שרת"/"מצב נתונים: מקומי"), shrunk from a labeled pill (PR B) since it's ops-relevant information, not a consumer-facing label.

**Sources page — Ingestion panel:** In backend mode, shows source selector (MVP active sources: וואלה ספורט, ישראל היום ספורט), "הרץ ייבוא עכשיו" button, per-source result breakdown after run, recent runs list (last 5), and "איכות הסיווג" quality toggle. No translation UI — translation is post-MVP and was removed from the Sources page. In local mode, shows a disabled card with instructions to enable backend mode.

**Sources page — "סטטוס ייבוא אוטומטי" panel (PR 13):** In backend mode, shows scheduler enabled/disabled + interval, next run time, last run time + status (הצליח/שגיאה/דולג/טרם רץ), last error, a "הרץ עכשיו" button (disabled with "ייבוא פעיל כרגע" while a run is active or a 409 was received), and per-source health cards: freshness badge (תקין/מיושן/לא רץ עדיין/כבוי/שגיאה), RSS/Scraping type label, "פיילוט" badge for Sport5, last run counts, consecutive failures, and last error. Each health card has a **פעיל/כבוי toggle** (PR 13.1) that calls `PATCH /api/ingest/sources/{id}` — this is how the Sport5 pilot is turned on/off from the UI. Hidden entirely in local mode. The manual ingestion panel is unchanged.

**Sources page — LLM Gating Benchmark panel** (dev/QA only): In backend mode, shows "בנצ׳מרק LLM Gating" section with "הרץ בנצ׳מרק מלא" button. Runs a two-phase benchmark (baseline then gated) and displays a structured report: per-source baseline stats, gated stats, and a comparison row per source showing skip rate, LLM calls saved, time saved, sport_unknown delta, and PASS/FAIL status. Requires ALLOW_DEV_RESET=true and CLASSIFICATION_PROVIDER=ollama. Results are not persisted. Panel hidden in local mode.

**Feed ("The Edition", PR A + A.2 naming polish):** The Feed is no longer a card list. `editionComposer.js` partitions the ranked visible items into tiers rendered as distinct story species: **lead story**, framed as **"הסיפור המרכזי"** (first push, else first high_feed — serif display headline on the canvas with a signal aura), **מבזק bulletin strips** (remaining push), **"במוקד"** (high_feed, asymmetric editorial blocks), **"עוד מהפיד"** (feed, typographic rows with inline expand), and **"קריאה נוספת"** (low_feed, collapsed digest). The signal spectrum's general level labels are **"לא לפספס"** (push) / **"במוקד"** (high_feed) / **"עוד מהפיד"** (feed) / **"קריאה נוספת"** (low_feed) — display copy only, the decision ids themselves (`push`/`high_feed`/`feed`/`low_feed`/`hidden`) are unchanged and still drive scoring. A clickable **signal spectrum** (segment widths proportional to level counts) plus quiet topic toggles replace the old counts strip and filter chips; decision badges are gone from the product feed. Each story carries a Hebrew **kicker** (entity/league/sport · event type via `storyLabels.js`) and important stories show the **desk voice** ("למה אצלך: …") with the reasoning steps expandable — the full trace stays in Debug. Titles render Hebrew-native: for MVP Hebrew sources `translatedTitle` is always `null` and every species falls back to `title` via the preserved `item.translatedTitle || item.title` logic, so English sources keep working when re-enabled post-MVP. The RSS subtitle still appears under lead/major headlines (clamped) and inside expanded stream rows; it is not a translation, and there is no original-language block or "לא תורגם" warning. Feedback actions (`more_like_this`/`less_like_this`) are unchanged, offered as text buttons on lead/bulletins/editorial and icons on rows. Entrance/filter motion runs on Framer Motion and honors reduced-motion.

**Debug view:** All articles with full scoring reasoning. Each article card shows the subtitle (when available) directly under the title, clamped to 3 lines, to provide classification context during QA. Also shows LLM classification metadata (PR 11): `classified_by` as a color-coded badge (neutral=rules, blue=llm, cyan=llm+rules_guardrail, red=failure, gold=low-confidence — see `classifiedByConfig.js`), `classification_provider` inline, `classification_confidence` as a percentage, and `classification_reason` as an italic line. Comparison tab always uses local engine (cross-profile comparison not wired to backend).

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
- Football: `sport` scope, mode `titles_only`, empty event rules — all football is `hidden` for Guy (prevents major_importance_fallback leakage)
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
- **PR 11 fix:** `"אלופת"` and `"אלופות"` added to unambiguous championship keywords. These use regular pe (פ U+05E4) unlike "אלוף" (final pe ף U+05E3) — the Python `in` operator returned `False` for `"אלוף" in "אלופת"`. This fixes "ניו יורק אלופת ה-NBA" → `event_type=title_win`.
- **PR 11 fix:** `"mvp"` added to `_BASKETBALL_KW`. "MVP" is unambiguously basketball in Israeli sports context.
- **Post-QA fix:** `title_win` hardened — Hebrew win verbs "זכה/זכתה/זכו/זוכה" no longer trigger `title_win` standalone. Now require: unambiguous championship word (`אלוף`, `אלופת`, `הניפה/הניף`, `champion`, etc.) OR compound `win-verb + championship-context` (`זכה + בגביע/בתואר/באליפות`). Fixes false positives: "זכה לביקורת", "זכו ברגע המביך", "צפו ברגע".
- **Post-QA fix:** `_GRAND_SLAM_KW` expanded to include specific tournament names (roland garros, רולאן גארוס, wimbledon, וימבלדון, us open, australian open). "אלקאראז זוכה ברולאן גארוס" now correctly fires `grand_slam_winner`.
- **Post-QA fix:** `source_sport_hint` parameter added — pre-computed URL category hint flows through `classify()` → `_detect_sport()` as the first check before all keyword logic.

**Confidence scoring:** 0.40 base + 0.15 (sport) + 0.05 (basketball-only source) + 0.15 (league) + 0.15 (entity) + 0.10 (non-news event type); capped at 0.95.

**`ambiguous_club` behavior:** When a full-name club phrase is present but no sport context resolves it, the article gets `sport=unknown`, `entities=[]`, tag `ambiguous_club`, and shows up as questionable in the quality endpoint.

**Known gaps (require LLM):** Multi-sport entities (Olympiacos, Hapoel TLV without context), unfamiliar Hebrew proper nouns (player/coach names not in keyword lists), NBA league context from player name alone (e.g., Brunson → NBA).

### 8b. LLM Classification (`backend/app/classification/`)

LLM classification is an opt-in overlay for Hebrew broad sources only. It does not change feed decision logic — the relevance engine still reads stored metadata deterministically.

**When it runs:** `source_id in {"walla_sport", "israel_hayom_sport", "sport5_sport"}` AND `CLASSIFICATION_PROVIDER != disabled`. (Sport5 pilot added to the set in PR 13; gating logic unchanged.)

**Provider options (`CLASSIFICATION_PROVIDER` env var):**

| Provider | Behavior |
|----------|---------|
| `disabled` (default) | LLM path skipped entirely; behavior identical to pre-PR 11 |
| `fake` | Pre-set results for known test headlines; unknown headlines → rules fallback |
| `gemini` | Google Gemini API via `google-genai` SDK; requires `CLASSIFICATION_API_KEY` (Google AI Studio key). Free tier: 20 requests/day (`gemini-2.5-flash-lite` preview) — not enough for production ingestion. Retries once on 429. |
| `ollama` | Calls local Ollama instance; no GPU required; recommended model `qwen2.5:3b-instruct` |

**LLM pipeline:**
1. Deterministic classifier runs first (always)
2. Subtitle extracted from RSS `<description>` via `subtitle.py` (HTML stripped, entities unescaped, sentence-aware excerpt ≤240 chars)
3. LLM called with Hebrew title + optional subtitle (as `Headline: …\nSubtitle: …`) + 6-shot prompt
4. JSON response validated against strict enum sets (`ALLOWED_SPORTS`, `ALLOWED_LEAGUES`, `ALLOWED_EVENT_TYPES`, `ALLOWED_IMPORTANCES`)
5. If `confidence < 0.65` → `classified_by = "rules_fallback_low_confidence"`, rules result kept
6. If confidence ≥ 0.65 → merge with 7 deterministic guardrails:
   - Guardrail 1: football Maccabi clubs detected → sport = football, LLM overruled
   - Guardrail 2: LLM sport=unknown → use rules sport
   - Guardrail 3: LLM league=null → use rules league
   - Guardrail 4: rules found specific event_type but LLM says "news" → use rules
   - Guardrail 4b: LLM title_win with no championship evidence in title → reject; use rules event_type
   - Guardrail 5: importance never downgraded (rules high → LLM low: keep high)
   - Guardrail 6: league-sport incompatibility (EuroLeague + football → basketball; etc.) — fires before entity pruning
   - Guardrail 7: source URL category hint overrides LLM sport (Israel Hayom paths; Sport5 FolderID=274 since PR 13)
7. Entities: rules entities pruned for sport compatibility (basketball club entities removed when final sport ≠ basketball); LLM entities normalized through alias map and appended
8. Defense-in-depth (all paths): `normalize_league_sport_compatibility()` called for both rules-only and LLM-merge paths — no Article can be stored with an impossible sport/league combination
9. Defense-in-depth (relevance engine): entity scope matching checks `topic.sport` vs `article.sport` — a football article cannot match a basketball entity topic even if entities contain a stale basketball club name

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

- **Scheduler is opt-in and process-local (PR 13).** `INGESTION_SCHEDULER_ENABLED=false` by default — ingestion then runs only on `POST /api/ingest/run` / `run-now`. When enabled, an asyncio loop in the FastAPI lifespan ingests enabled sources every `INGESTION_SCHEDULER_INTERVAL_MINUTES`. Multi-replica deployments need a single scheduler worker or a distributed lock.
- **No fuzzy dedup / clustering.** Deduplication is URL-only. The same story from Eurohoops and Walla appears as two separate articles. `cluster_id` field exists in the model but is never populated.
- **No feedback → profile mutation.** Feedback events are stored in SQLite but do not yet modify topic rules or event rules in user profiles.
- **No auth / multi-user.** User profiles are seeded statically. No login, no registration.
- **No push notifications.** `push` is a decision level in the engine; no device notification delivery.
- **No body translation or summaries.** Only titles are translated. Article bodies are not ingested.
- **Limited source coverage.** MVP active sources: Walla Sport, Israel Hayom Sport. Eurohoops and Sportando are disabled (post-MVP). Sport5 is a scraping pilot (PR 13, disabled by default — no public RSS exists). ONE has no clean public RSS; Ynet has no sport-specific RSS. ONE is the preferred next scraping candidate.
- **LLM classification not yet benchmarked at production scale.** Two providers are implemented: `gemini` (fast, cloud, but only 20 requests/day free tier — exhausted in one ingestion run) and `ollama` (local, uncapped, needs Ollama installed and `qwen2.5:3b-instruct` pulled). Default is `disabled`. Hebrew articles use deterministic classification until a provider is configured. Timing is now instrumented — `fetch_ms`, `llm_avg_ms`, `llm_p95_ms`, and fallback counts appear in `POST /api/ingest/run` responses.
- **Entity normalization map is conservative (expanded in PR 13).** 25 canonical entities (Israeli basketball clubs, EuroLeague/EuroCup clubs, NBA teams/players) with Hebrew + English aliases; multi-sport European clubs are sport-guarded. Entities not in `_ENTITY_ALIASES` are still silently discarded from `article.entities` even when the LLM identifies them correctly.
- **Translation not active in MVP.** `TRANSLATION_PROVIDER=disabled` is correct for Hebrew-only MVP. Backend module, DB fields, and API routes are preserved for post-MVP re-enablement. Translation quality validation is a post-MVP concern.

---

## 11. Recommended Next Steps

Priority order:

1. **Re-run the LLM gating benchmark (validation task)** — Gating and the benchmark UI shipped with PR 12; the PR 13 quality fixes are in place. From the Sources page (requires `ALLOW_DEV_RESET=true` + `CLASSIFICATION_PROVIDER=ollama`), run "הרץ בנצ׳מרק מלא" and compare `llm_attempts`, `llm_skipped`, `total_ms`, and `sport=unknown` against baseline. Target ≥40% LLM call reduction with no regression (last measured: israel_hayom PASS 41.4%, walla FAIL 26.7% before the quality fixes). Review results before merging the `feature/selective-llm-gating` branch.
2. **LLM classification benchmark** — Install Ollama, pull `qwen2.5:3b-instruct`, set `CLASSIFICATION_PROVIDER=ollama` + `CLASSIFICATION_MODEL=qwen2.5:3b-instruct` + `CLASSIFICATION_TIMEOUT_SECONDS=30`, re-ingest Walla + Israel Hayom, compare `sport=unknown` count and Guy's feed visibility before/after. Check `fetch_ms`, `llm_avg_ms`, and `llm_fallback_*` counts in the ingest response for performance baseline. Run `POST /api/classify/backfill?source_id=walla_sport` on existing articles. If quality is poor, try `qwen3:4b`.
3. ~~Expand entity normalization map~~ — **done in PR 13** (25 canonical entities; see `docs/RSS_QUALITY_GUARDRAILS.md` §10a). Player/coach names still missing from the *deterministic* keyword lists remain open.
4. ~~Scheduled ingestion~~ — **done in PR 13** (asyncio loop in lifespan, `INGESTION_SCHEDULER_ENABLED`, disabled by default).
5. **Validate Sport5 pilot** — Run `POST /api/ingest/run?source_id=sport5_sport` against the live site, review classification quality in the debug view, then enable it from the Sources page toggle (or `PATCH /api/ingest/sources/sport5_sport`) if quality holds.
6. **Feed clustering / fuzzy dedup** — Use `difflib.SequenceMatcher` on titles across sources; populate `cluster_id`. Show one card per story.
7. **Feedback → profile mutation** — `never_show` feedback creates a `hidden` event rule for the article's `event_type` in the matched topic. Requires in-place profile update via the repository.
8. **More Hebrew sources** — ONE Sport via category page HTML adapter is the preferred next source (traditional HTML, no SPA; Sport5 is already covered by the scraping pilot). Ynet is harder (SPA).
9. **Better relevance for LLM-classified articles** — Some LLM-classified articles land in Guy's feed as `feed` when they deserve `high_feed` or `push`. The relevance engine's topic rules may need tuning once LLM entity extraction surfaces more entities (e.g., New York Knicks → Knicks entity → entity_event_rules fires).
10. **Re-enable English sources + translation** (post-MVP) — Set `eurohoops.enabled=True` in `config.py` (or via the Sources page toggle), configure `TRANSLATION_PROVIDER=claude` + API key, run translation backfill, verify Italian → Hebrew quality.

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
CLASSIFICATION_LLM_GATING=enabled
ALLOW_DEV_RESET=false
INGESTION_SCHEDULER_ENABLED=false
INGESTION_SCHEDULER_INTERVAL_MINUTES=15
INGESTION_SCHEDULER_INITIAL_DELAY_SECONDS=30
```
Set `TRANSLATION_PROVIDER=fake` for dev testing without an API key.
Set `TRANSLATION_PROVIDER=claude` with a real `TRANSLATION_API_KEY` for production-quality translation.
Set `CLASSIFICATION_PROVIDER=ollama` after running `ollama pull qwen2.5:3b-instruct` to enable LLM classification for Hebrew broad sources.
Set `CLASSIFICATION_PROVIDER=gemini` with a `CLASSIFICATION_API_KEY` (Google AI Studio key) for cloud-based LLM classification. Note: free tier is 20 requests/day for `gemini-2.5-flash-lite` — not suitable for production ingestion at scale.
Set `CLASSIFICATION_PROVIDER=fake` to test the LLM classification path in dev without Ollama installed.
Set `ALLOW_DEV_RESET=true` only for local QA sessions (enables `POST /api/dev/reset-rss-data`). Never enable in production.
Set `INGESTION_SCHEDULER_ENABLED=true` to run ingestion automatically every `INGESTION_SCHEDULER_INTERVAL_MINUTES` (default 15). Disabled by default — the app then behaves exactly as before PR 13. Verify from the Sources page ("סטטוס ייבוא אוטומטי") or `GET /api/ingest/scheduler/status`.

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
# 1076 tests — all should pass (no test requires Ollama, a real API key, or live Sport5;
# conftest forces CLASSIFICATION_PROVIDER=disabled + INGESTION_SCHEDULER_ENABLED=false)
# Note: test_reset_returns_403_when_disabled requires ALLOW_DEV_RESET unset or =false in .env
```

### Manual RSS ingestion
```
POST http://127.0.0.1:8000/api/ingest/run                                        # MVP active sources only
POST http://127.0.0.1:8000/api/ingest/run?source_id=walla_sport                  # Hebrew — active
POST http://127.0.0.1:8000/api/ingest/run?source_id=israel_hayom_sport           # Hebrew — active
POST http://127.0.0.1:8000/api/ingest/run?source_id=sport5_sport                 # Hebrew — scraping pilot, disabled by default (manual run works)
# POST http://127.0.0.1:8000/api/ingest/run?source_id=eurohoops                  # disabled — set enabled=True in config.py to re-enable
# POST http://127.0.0.1:8000/api/ingest/run?source_id=sportando                  # disabled — set enabled=True in config.py to re-enable

POST http://127.0.0.1:8000/api/ingest/scheduler/run-now                          # same as scheduled run (enabled sources), shared lock
GET  http://127.0.0.1:8000/api/ingest/scheduler/status                           # scheduler + lock state
GET  http://127.0.0.1:8000/api/ingest/source-health                              # per-source freshness/health
```
`POST /api/ingest/run` (no source_id) only runs sources with `enabled=True` in `config.py`.
For MVP this means `walla_sport` + `israel_hayom_sport` only. All ingestion triggers share
one process-level lock — a second concurrent call returns 409 `ingestion_already_running`.

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

אחרי ריצת ה-benchmark, בדוק גם בתגובת ה-API (`SourceIngestResult`):
- `fetch_ms` — זמן שליפת ה-RSS
- `llm_avg_ms`, `llm_p95_ms` — זמן ממוצע ו-p95 לקריאת LLM
- `llm_successes`, `llm_fallback_*` — כמה הצליחו מול כמה נפלו

תיעוד: `docs/LLM_CLASSIFICATION.md` מכיל את כל הפרטים הטכניים של מודול הסיווג ו-7 ה-guardrails (כולל 4b, 6, 7 שנוספו ב-QA fixes).

---
