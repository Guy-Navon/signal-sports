# Signal Sports — Current Project State

Last updated: 2026-07-10 (Reliability Sign-off #63 CLOSED — approved; #52 unblocked).

**2026-07-10 (later) — RELIABILITY SIGN-OFF APPROVED; #63 CLOSED; onboarding gate LIFTED.** The product owner approved the sign-off after one requested follow-up (PR #70: silver/bronze medal placement is no longer a title win; gold preserved). Final corpus state @ `6e6fff9`: title_win 19→3 (1 genuine + 2 accepted decision-neutral edge cases), finals_result 63→31, Guy pushes 13→7 (all explicit-override-backed; the 4× Madar duplication is a recorded **clustering/dedup product gap**, not a push-discipline failure), **zero casual_deni_fan drift**. **#52 (onboarding) is unblocked** and depends on #51 only. Reliability leftovers: #64 (open product decisions), #65 (non-gating). The golden-17 suite (`backend/tests/test_golden_cases.py`) is a standing regression contract for any future classification change.

**2026-07-10 — Reliability core fixes LANDED (#59–#62, PRs #66–#69); #63 sign-off pending one human product confirmation.** The golden-17 regression suite is in the tree (`backend/tests/test_golden_cases.py` — all 17 cases positive, real-pipeline replay, both profiles); event-assertion semantics (#60), LLM-evidence circularity provenance (#61), and hint/keyword/taxonomy coverage (#62) are merged. Corpus results (311 articles, replay + persisted backfill with a DB backup at `backend/data/signal_sports.pre_reliability_backfill.backup.db`): title_win 19→4, finals_result 63→31, Guy pushes 13→7 (all seven trace to explicit overrides on verified facts), **zero casual_deni_fan decision changes**, zero newly-visible noise, C2/C8 cross-vendor parity. Snapshots: `docs/qa/reliability_baseline.json` (pre) / `docs/qa/reliability_post_fix.json` (post). §8/§10 known-defect callouts below describe the pre-fix state — the defect classes are now structurally controlled; residual imprecision (final: 3 title_win rows after the PR #70 medal correction, plus finals_result features) is documented in issue #63's evidence. (Superseded by the entry above: #63 has since closed and #52 is unblocked.)

**2026-07-09 (later) — Classification & Feed Reliability investigation completed; second active track opened; onboarding gated.** A 15-case trace-level investigation of real feed failures is committed as **`docs/CLASSIFICATION_RELIABILITY_INVESTIGATION.md`** (canonical evidence — event-assertion semantics defects, LLM-evidence circularity for cross-sport clubs, deterministic-coverage gaps; architecture judged fundamentally sound). Execution home: **[Milestone 3](https://github.com/Guy-Navon/signal-sports/milestone/3) / Epic [#58](https://github.com/Guy-Navon/signal-sports/issues/58)**, issues #59–#65, sequencing principle regression-first (#59 golden fixtures before any fix). **There are now two active tracks that run in parallel:** User Platform (#50 next) and Reliability (#59 next). **Cross-track gate:** User Platform #52 (onboarding) is hard-blocked until the Reliability Sign-off issue [#63](https://github.com/Guy-Navon/signal-sports/issues/63) closes — onboarding/calibration and preference learning must not encode unreliable classification facts. All review checkpoints are now model-independent contracts written in the issue bodies (#52 product review, #54 security/regression review, #63 reliability sign-off) — no future review depends on any specific model or on past conversation history. See §13 for cold-start orientation.

**2026-07-09 — Intelligence Architecture v2 COMPLETE; User Platform PR 1 landed.** The Signal Intelligence Architecture v2 initiative (Epic #27, Milestone 1) is fully landed and closed — the Preference V2 affinity engine serves `/api/feed` (flipped after the shadow checkpoint), Calibration V2 and feedback learning are live, and `docs/RELEVANCE_CONTRACT.md` is the umbrella contract. The active milestone became **User Platform** (since superseded as the *sole* focus — there are now two active tracks; see the entry above). PR #56 / Issue #49 landed the backend Auth Core on main (`users`, `auth_sessions`, `/api/auth/*`, cookie sessions, CSRF, security dependencies, startup ensure-step). Later PRs still own `/api/me/*`, frontend auth, onboarding UX, legacy/ops route gating, explicit test identities, and account lifecycle. The lowest unblocked User Platform issue is #50. Contract in `docs/USER_PLATFORM.md`, execution home [Milestone 2](https://github.com/Guy-Navon/signal-sports/milestone/2) (Epic #48, issues #49–#55). See §13 for cold-start orientation.

The header below this line describes the **frontend redesign completed 2026-07-04**: Court Vision (PRs 1–6) followed by five further PRs (A–E) that rebuilt the product's entire visual layer from the ground up. **All merged to `main` at commit `7e029bc`. No open feature branch.** The Base44-generated QA-dashboard UI is gone; the app is now a premium, Hebrew-first, RTL-first dark product with a design-token system (shadcn/ui + Tailwind + Radix, self-hosted Heebo + Frank Ruhl Libre fonts), a product-vs-console split, and a from-scratch product identity under the approved **"המערכת / The Desk"** design concept (a codename for the visual direction only — the product name is still Signal Sports / סיגנל). Full detail lives in `docs/FRONTEND_DESIGN_SYSTEM.md`; the one-paragraph arc:

- **PR A ("The Edition")** rebuilt the Feed from a scored card list into a composed personal edition — lead story ("הסיפור המרכזי") / מבזק bulletins / "במוקד" tier / "עוד מהפיד" rows / "קריאה נוספת" digest, a clickable signal spectrum, Hebrew kickers, a "desk voice" explaining relevance, and Framer Motion (first real use in the app). A same-PR follow-up fixed a real bug at the **backend ingestion layer** (`backend/app/ingestion/subtitle.py`) — Walla's RSS `<description>` is the article's lede paragraph, not a short deck, and was being shown as if it were one; `clean_subtitle()` now cuts at the last complete sentence within a 240-char budget.
- **PR B ("atmosphere + brand shell")** removed the left sidebar on product routes (Feed/Preferences/Calibration/Results — ops keeps its sidebar, unchanged), replaced the plain header with a `Masthead` (wordmark, inline nav, console-entry icon) over a decorative `Atmosphere` backdrop, added a floating mobile pill nav for product routes, and wrapped route changes in a page transition.
- **PR C ("product pages")** brought Preferences, Calibration, and Results into the Feed's editorial voice — a `DeskIntro` line opens Preferences/Calibration, boxed sections became hairline-divided lists, badge piles became kicker lines. Every hook/handler/`src/engine` call in Calibration's rating flow is untouched.
- **PR D ("ops shell variant")** gave the ops console its own backdrop (`OpsGrid`, a flat blueprint grid) and a mono breadcrumb in `OpsNav` — Sources/Debug/LLM QA page content and logic are completely untouched.
- **PR E ("signature details")**, self-directed rather than requested, fixed real remaining gaps: the site's favicon file didn't exist at all (broken tab icon), the 404 page had never been touched by any redesign PR (it renders outside the app shell entirely), no themed focus rings, no custom scrollbar, and the Feed's empty state used a generic icon.

**Backend, API contracts, and the frontend data layer (`src/context`, `src/api`, `src/engine`, `src/data`) were unchanged by the redesign**, except the one explicitly-authorized subtitle fix above. Test counts have changed since that historical redesign checkpoint; use the current collectors instead of this section for live counts.

**2026-07-06 — Signal Intelligence Architecture v2 started.** PR 1 (branch `feature/taxonomy-entity-resolver`, PR #26) shipped the canonical taxonomy + entity resolver foundation: `backend/app/taxonomy/` is now the single source of entity truth for the deterministic classifier and the LLM normalizer; bare club-family names ("מכבי", "הפועל"…) never resolve to a team; Maccabi Ramat Gan / Maccabi Kiryat Gat exist as distinct entities. See `docs/TAXONOMY.md` for the taxonomy contract and `docs/INTELLIGENCE_ROADMAP.md` for the full initiative plan (Epic #27, Milestone 1 — the home page for all initiative issues). PR 2 (`feature/article-facts`, #28/#38) added evidence-backed `primary_competition`/`article_competitions`/`entity_ids` — see `docs/ARTICLE_FACTS.md`. PR 3 (`feature/relevance-visibility-contract-29`, #29) is the VISIBILITY layer: competition-aware league matching (explicit evidence → legacy fallback → team-membership reach), a membership-only feed ceiling, `entity_ids`-first identity, the `major_only` leak removed, and a Guy/Casual-Deni-Fan profile drift guard — see `docs/RELEVANCE_VISIBILITY_CONTRACT.md`.

Prior backend state (unchanged by the redesign) reflects PR 13 + PR 13.1 (branch `feature/selective-llm-gating`): entity normalization expanded to 25 canonical entities, generalized post-merge basketball entity enrichment, new signing keywords, Sport5 (ערוץ הספורט) HTML-scraping pilot source (disabled by default, toggleable from the UI), scheduled ingestion loop with process-level ingestion lock (disabled by default), scheduler-status + source-health endpoints, runtime source enable/disable overrides, and the Sources page scheduler/health UI.

**Issue #17 ("Same-origin frontend API via Vite proxy + fixed dev port 5173"), part of the Private Mobile Access initiative (#16):** the frontend now defaults to same-origin relative API paths (`/api/...`, `/health`) instead of an absolute `http://127.0.0.1:8000`. `frontend/vite.config.js` gained a `server` block — fixed port `5173` with `strictPort: true` (fails loudly instead of drifting to 5174) and a dev proxy forwarding `/api` and `/health` to `http://127.0.0.1:8000`. `frontend/src/api/client.js`'s `API_BASE_URL` now defaults to `""` via `??` (empty string means same-origin); `VITE_API_BASE_URL` still works as an explicit override for calling a backend directly, cross-origin. No backend or CORS changes. This was the foundation for Tailscale Serve remote access, which has since landed (issue #18, closed; see `docs/MOBILE_REMOTE_ACCESS.md`).

---

## 1. Product in One Paragraph

Signal Sports is a personalized sports news intelligence feed. The current MVP is Hebrew-only: it ingests Hebrew-native sports news from `walla_sport`, `israel_hayom_sport`, `ynet_sport`, and `one_sport`, classifies each article (sport, league, entities, event type, importance), and surfaces to each user only the articles that are actually worth their attention. The same article can be `push` for one user and `hidden` for another. Translation of non-Hebrew sources is a post-MVP capability — the backend module is intact but disabled by default. The product goal is not "show all sports news" but "show only what matters to this specific user."

---

## 2. Product Principles

- **Hebrew-first UI.** Every article is displayed with a Hebrew title. For the MVP, all active sources (`walla_sport`, `israel_hayom_sport`, `ynet_sport`, `one_sport`) are Hebrew — no translation is needed or used. The translation module is intact in the backend and can be re-enabled post-MVP for English sources.
- **Personalized relevance, not generic RSS.** The feed is per-user. Identical article sets produce different feeds for different profiles.
- **False positives are worse than missed classification.** When the classifier is unsure, it assigns `sport=unknown` and the article lands in debug. It does not guess and pollute the feed. *(The 2026-07-09 investigation found violations of this principle — false champion-vocabulary events and LLM-echo sport guesses; fixed and regression-protected by Epic #58, closed 2026-07-10.)*
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
      source URL category hint extracted (extract_source_sport_hint — Israel Hayom paths, Sport5 FolderID=274,
        Ynet sport paths incl. israelisoccer/tennis, ONE category IDs; IH israeli-soccer mapped in #62)
      [Hebrew broad sources only, when CLASSIFICATION_PROVIDER != disabled]:
        should_call_llm_for_article() gate evaluated against rules result
          → sport=unknown / ambiguous_club / conf<0.55 → force call LLM
          → clear league / strong hint+context / high confidence → skip LLM
          → LLM classifier called with title + subtitle [timing measured including failures]
          → JSON validation → confidence check (≥ 0.65)
          → merge with 7 deterministic guardrails → classified_by=llm or llm+rules_guardrail
          → on failure or low confidence: use deterministic result → classified_by=rules_fallback_*
      normalize_league_sport_compatibility() — universal post-merge safety net (both paths)
      post-merge basketball entity enrichment (ambiguous-club titles, once sport resolves)
      build_article_facts() — ArticleFacts consistency stage (#28): weighted sport evidence,
        explicit-only competitions, entity/competition sport invariants, classification_trace
      post-facts event re-validation against the event evidence contract (#30)
  → SQLite insert (articles table)
  → Preference V2 engine (default): per-user scoring hidden / low_feed / feed / high_feed / push
      over ProfileV2 affinities (legacy relevance engine only via PREFERENCE_ENGINE=legacy)
  → Feed/Debug UI (React/Vite, backend mode)
```

**MVP active sources:** `walla_sport`, `israel_hayom_sport`, `ynet_sport`, and `one_sport`. `eurohoops` and `sportando` are
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
| Source URL hints | `backend/app/classification/source_hints.py` — URL category → sport hint (Israel Hayom paths; Sport5 FolderID=274; Ynet sport paths; ONE category IDs) |
| Feed scoring | Preference V2 engine (default): `backend/app/services/preference_engine.py`; legacy engine `relevance_engine.py` (rollback: `PREFERENCE_ENGINE=legacy`); frozen JS engine `src/engine/relevanceEngine.js` (local demo mode only, no v2 port) |
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
- **Known issue:** The broad Walla Sport feed includes a lot of football and generic news. During non-basketball seasons (e.g., FIFA World Cup 2026), the feed is noise-heavy. The classifier downgrades much of this to `hidden` for basketball-focused profiles — but the 2026-07-09 investigation found football noise leaking to `feed`/`push` through false `title_win` events and cross-sport entity errors (Epic #58).

### Israel Hayom Sport (`israel_hayom_sport`)
- **Language:** Hebrew (`he`)
- **Feed URL:** `https://www.israelhayom.co.il/rss.xml` (general RSS filtered by `allowed_url_patterns=("/sport/",)`)
- **What it covers:** Israeli basketball (israeli-basketball subpath), world basketball (NBA/EuroLeague), world football (World Cup, European football), other sports (tennis, etc.), sport opinion pieces.
- **Added in PR 10.** Articles stored as Hebrew-native; `original_title = None`; no translation.
- **Filtering:** The Israel Hayom RSS is a general news feed (100 items, ~21 sport). The `allowed_url_patterns` filter accepts only URLs containing `/sport/`. Non-sport items (politics, opinion, culture) are counted as `skipped_filtered` and never reach the DB.

### Ynet Sport (`ynet_sport`)
- **Language:** Hebrew (`he`)
- **Feed URL:** `https://www.ynet.co.il/Integration/StoryRss3.xml`
- **What it covers:** Broad Israeli sports coverage: football/world football, basketball (including Israeli basketball paths), tennis, live games, and tournament coverage.
- **Added after PR 13.** Ynet is an enabled Hebrew RSS source. The official sport RSS feed returns valid RSS 2.0, typically 30 items, with `title`, `link`, `description`, `pubDate`, `guid`, and a non-standard `tags` element. The generic RSS adapter handles it; no scraping is used.
- **Subtitles:** RSS `<description>` contains a thumbnail HTML block followed by teaser text. The shared subtitle cleaner strips the image markup and stores the teaser as `article.subtitle`.
- **Publish time:** parsed from item `pubDate` (`+0300` in the inspected feed) through feedparser and stored as UTC.
- **Source hints:** `/sport/israelibasketball/` and `/sport/worldbasketball/` hint basketball; `/sport/worldsoccer/` and `/sport/worldcup.../` hint football. Generic `/sport/article/` and `livegame.ynet.co.il` URLs return no hint and fall through to the classifier/LLM.

### ONE Sport (`one_sport`)
- **Language:** Hebrew (`he`)
- **Type:** `html_scrape` adapter path, parsing public ONE JSON article-list endpoints rather than DOM markup.
- **Endpoints:** `https://api.one.co.il/JSON/v6/Articles/Category/{1,2,3,5,7,155}` for Israeli football, Israeli basketball, world football, world basketball, other sports, and lower leagues.
- **Why not RSS:** current public RSS probes still return 404, and the only RSS-like endpoint found (`sites.one.co.il/rss/video/itunes`) is video/podcast media without normal article links. The JSON endpoints are the same public article surfaces used by the ONE homepage.
- **Status:** enabled by default (`enabled=True`, `is_pilot=False`) as a Hebrew broad sports source.
- **Fields:** `Title.Main` becomes the title, `Title.Secondary` becomes `article.subtitle`, `URL.PC` becomes the article URL, and `Date` is parsed as Israel local time and stored as UTC. `IsVideo=true` items are skipped.
- **Classification:** included in the Hebrew broad-source set (gated LLM path). Category IDs embedded in some ONE article URLs (`/Article/26-27/3,...`) hint football for IDs `1`, `3`, `155` and basketball for IDs `2`, `5`; generic `/Article/{id}.html` URLs fall through to classifier/LLM.

### Sport5 / ערוץ הספורט (`sport5_sport`) — scraping pilot (PR 13)
- **Language:** Hebrew (`he`); no translation, same as Walla.
- **Type:** `html_scrape` — Sport5 has **no public RSS** (confirmed PR 8/PR 10). The adapter scrapes the basketball category page (`https://www.sport5.co.il/liga.aspx?FolderID=273`, static server-rendered HTML, ~12 articles/fetch) with httpx + BeautifulSoup.
- **Status:** pilot, **disabled by default** (`enabled=False`, `is_pilot=True`). Run manually with `POST /api/ingest/run?source_id=sport5_sport`, or toggle it on from the Sources page ("בריאות מקורות" card) / `PATCH /api/ingest/sources/sport5_sport` — the runtime override persists across restarts and includes it in scheduled/all-source runs (PR 13.1).
- **Classification:** included in the Hebrew broad-source set (gated LLM path); article URLs with `FolderID=274` get a `basketball` source hint.
- **Subtitles:** the card's descriptive paragraph is extracted as the article subtitle (PR 13.2) — cleaned like RSS descriptions, shown in Feed/Debug, and fed to the classifier/LLM as context.
- **Publish time:** parsed from the card's `DD.MM.YY - HH:MM` timestamp (Israel local time → UTC, DST-aware; PR 13.3); cards without a timestamp fall back to ingest time.
- **Known limitations:** scraping is fragile to site redesigns — failures degrade to 0 items and surface in source health, never crash ingestion.

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
| `articles` | All ingested articles; `entities` and `tags` stored as JSON; includes `subtitle`, `event_certainty`, and 4 LLM classification metadata columns |
| `profiles` | User profiles; `topics` list stored as JSON |
| `sources` | RSS source configuration |
| `feedback_events` | User feedback (persists across restarts) |
| `calibration_headlines` | Legacy V0 seed table — superseded by Calibration V2's code-owned versioned dataset (#33); not used by the current calibration flow |
| `calibration_responses` | Calibration V2 ratings, keyed per (user, item, dataset_version) |
| `ingestion_runs` | Log of every RSS ingestion run |
| `source_overrides` | Runtime source enabled/disabled overrides (PR 13.1); wins over config.py defaults |
| `users` | Auth Core account identity rows; demo profiles have credential-less `role='demo'` rows |
| `auth_sessions` | Auth Core SHA-256-hashed opaque session tokens, FK to `users.id` with ON DELETE CASCADE |

**Soft-migrated columns on `articles` (via `ALTER TABLE ADD COLUMN`, idempotent):**

| Column | Type | Meaning |
|--------|------|---------|
| `subtitle` | TEXT | Cleaned RSS `<description>` text (HTML stripped, sentence-aware excerpt ≤240 chars — cut at the last complete sentence within budget, not mid-sentence; see `docs/LLM_CLASSIFICATION.md`); `null` for old articles and entries with no description |
| `classified_by` | TEXT DEFAULT `'rules'` | `rules`, `llm`, `llm+rules_guardrail`, `rules_fallback_after_llm_failure`, `rules_fallback_low_confidence` (PR 11) |
| `classification_provider` | TEXT | `rules`, `ollama:llama3.2:3b`, `fake`, etc. (PR 11) |
| `classification_reason` | TEXT | LLM's one-sentence explanation of the classification (PR 11) |
| `classification_confidence` | REAL | LLM's self-assessed confidence (0.0–1.0); separate from the deterministic `confidence` field (PR 11) |
| `event_certainty` | TEXT DEFAULT `'confirmed'` | Event evidence grade: `confirmed`, `probable`, or `weak` (issue #30) |
| `primary_competition` | TEXT | Competition id (`comp:*`) the article is explicitly about — explicit article evidence only; NULL when the league is only membership-inferred (#28) |
| `article_competitions` | JSON | Additional explicitly-evidenced competition ids (#28) |
| `entity_ids` | JSON | Canonical taxonomy ids (`team:*`/`player:*`/`coach:*`) for the resolved entities (#28) |
| `classification_trace` | JSON | Evidence hits, LLM gate decision + reason, LLM raw proposal, normalization actions, and conflicts (#28) |
| `taxonomy_version` | INTEGER | Taxonomy registry version that produced the facts (#28) |

On startup: tables are created if missing; soft migrations add new columns to existing databases safely; seed data is inserted only into empty tables (idempotent). Auth Core then idempotently creates credential-less `users` rows for existing profile rows and optionally bootstraps the first admin from `AUTH_ADMIN_EMAIL` / `AUTH_ADMIN_PASSWORD` without resetting existing admin credentials.

**2026-07-06 — Intelligence Architecture v2, PR 2 (ArticleFacts, #28).** A
consistency-validation stage (`backend/app/classification/facts.py`) persists
evidence-backed facts on every article: `primary_competition` /
`article_competitions` (explicit competition evidence only — never team
membership), `entity_ids` (canonical taxonomy ids), a compact
`classification_trace`, and `taxonomy_version`. It enforces the
sport/entity/competition triangle (no entity/competition whose sport differs from
the article; abstain on the unresolvable case), records every conflict, and the
last entity→basketball bias path (bare `מכבי`/`maccabi` as sport evidence) was
removed so a football subtitle signal (`שוער`) can correct a bare-family title.
Membership-derived legacy `league` (a resolved team → its domestic competition)
substantially lowers the `league=NULL` rate. LLM optionality preserved — the
no-LLM path produces the same schema (more abstentions). Contract:
`docs/ARTICLE_FACTS.md`. Backend tests: **1188** (baseline 1165; 3 documented
intentional updates encoding the old bias).

**2026-07-06 — Intelligence Architecture v2, PR 3 (event semantic validation, #30).**
Specific non-news event types now pass a shared semantic evidence contract in
both the deterministic rules path and the LLM merge path. `event_certainty`
survives ingestion and backfill, and the final ArticleFacts trace records the
validated event. On doubt, event type falls back to `news`.

On startup: tables are created if missing; soft migrations add new columns to existing databases safely; seed data is inserted only into empty tables (idempotent). Auth ensure-steps are create-only: existing profile, article, feedback, and calibration data are not rewritten.

**Test suite:** use `pytest tests/ --collect-only -q` and the frontend collector for current counts; do not trust stale counts copied into docs.
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
| `POST` | `/api/auth/signup` | Create account + matching empty ProfileV2 profile atomically; sets HttpOnly session cookie |
| `POST` | `/api/auth/login` | Email/password login; fresh opaque cookie session; rate-limited by account key + global window |
| `POST` | `/api/auth/logout` | Server-side session revocation; clears auth cookie |
| `GET` | `/api/auth/session` | Session bootstrap; current user plus onboarding/calibration summary |

The endpoint table above is a core summary, **not exhaustive** — Calibration V2 (`GET /api/calibration/items`, `POST /api/calibration/preview`, `POST /api/calibration/apply`), learning (`GET /api/learning/{user_id}`, reset), profile mutation (`PUT /api/profiles/{user_id}`), engine/debug surfaces (`GET /api/feed-engine`, `GET /api/debug/shadow/{user_id}`), and the benchmark endpoint are documented in §7 and their contract docs; use `/docs` (OpenAPI) for the live list.

**Feed filter:** `GET /api/feed`, `GET /api/debug/feed`, and `GET /api/articles` return only articles whose `id` starts with `rss_`. Seed articles (e.g. `article_001`) are excluded from the feed but accessible via single-item lookup.

---

## 6. Frontend State

**Design system:** The UI runs on the "Court Vision" token system — see `docs/FRONTEND_DESIGN_SYSTEM.md` for the full tokens, component inventory, and RTL rules (that document is the authoritative reference; this section is a summary). Key points: dark navy canvas with a semantic **signal system** (gold=push, green=high_feed, steel-blue=feed, dim=low_feed, red=hidden/errors, cyan=AI), Heebo/Frank-Ruhl-Libre fonts (serif weights 500/700 — an 800 weight was tried in PR A.1 and dropped for reading too dramatic), and a **product-vs-console split**: product pages (Feed, Preferences, Calibration, Results — full-width, no sidebar, ambient `Atmosphere` backdrop) vs the ops **console** (Sources, Debug, LLM QA — sidebar rail intact, its own flat `OpsGrid` backdrop, steel-blue instrument-panel styling). `<html lang="he" dir="rtl">` with logical-only Tailwind utilities. Both data modes (`local`/`backend`) work on every page. Components live under `src/components/{shared,shell,feed,ops,debug,preferences}`. The entire redesign (Court Vision + PRs A–E) changed no backend/API/data-layer code except the one authorized subtitle fix noted above.

**App shell (PR B):** `AppShell` branches structurally by area, not just style — product routes render no sidebar at all (the feed/page gets the full canvas); ops routes keep `ProductNav`'s desktop rail exactly as it always has. A `Masthead` component (replacing a plain header) carries the "סיגנל" wordmark + `SignalMark` (a three-bar icon reused as the Feed's own SIGNAL-strength instrument), inline product nav or a "חזרה למוצר" link on ops, and — at the far edge — the profile switcher, `DataModeBadge`, and (product only) a console-entry icon. The masthead starts transparent over the atmosphere/grid and gains a glass surface only past a scroll threshold. Mobile product routes get a floating glass pill nav; ops keeps the original edge-to-edge tab bar. Route changes fade+rise via Framer Motion.

**Data mode indicator:** `DataModeBadge` in the masthead — a pulsing dot + tooltip ("מצב נתונים: שרת"/"מצב נתונים: מקומי"), shrunk from a labeled pill since it's ops-relevant information, not a consumer-facing label.

**Sources page — Ingestion panel:** In backend mode, shows source selector (MVP active sources: וואלה ספורט, ישראל היום ספורט, ynet ספורט, ONE ספורט), "הרץ ייבוא עכשיו" button, per-source result breakdown after run, recent runs list (last 5), and "איכות הסיווג" quality toggle. No translation UI — translation is post-MVP and was removed from the Sources page. In local mode, shows a disabled card with instructions to enable backend mode.

**Sources page — "סטטוס ייבוא אוטומטי" panel (PR 13):** In backend mode, shows scheduler enabled/disabled + interval, next run time, last run time + status (הצליח/שגיאה/דולג/טרם רץ), last error, a "הרץ עכשיו" button (disabled with "ייבוא פעיל כרגע" while a run is active or a 409 was received), and per-source health cards: freshness badge (תקין/מיושן/לא רץ עדיין/כבוי/שגיאה), RSS/Scraping type label, "פיילוט" badge for Sport5, last run counts, consecutive failures, and last error. Each health card has a **פעיל/כבוי toggle** (PR 13.1) that calls `PATCH /api/ingest/sources/{id}` — this is how the Sport5 pilot is turned on/off from the UI. Hidden entirely in local mode. The manual ingestion panel is unchanged.

**Sources page — LLM Gating Benchmark panel** (dev/QA only): In backend mode, shows "בנצ׳מרק LLM Gating" section with "הרץ בנצ׳מרק מלא" button. Runs a two-phase benchmark (baseline then gated) and displays a structured report: per-source baseline stats, gated stats, and a comparison row per source showing skip rate, LLM calls saved, time saved, sport_unknown delta, and PASS/FAIL status. Requires ALLOW_DEV_RESET=true and CLASSIFICATION_PROVIDER=ollama. Results are not persisted. Panel hidden in local mode.

**Ops console identity (PR D):** Sources/Debug/LLM QA keep a distinct instrument-panel backdrop (`OpsGrid`, a flat steel-blue blueprint grid at ~5% opacity, replacing the product's floodlit `Atmosphere`) and a mono breadcrumb in `OpsNav` reading "המערכת ⁄ קונסולה ⁄ {current page}". Nothing in these three pages' own content, logic, or API calls changed — only the shell chrome around them.

**Feed ("The Edition", PR A + polish passes A.1–A.4 + PR A.2 naming):** The Feed is no longer a card list. `editionComposer.js` partitions the ranked visible items into tiers rendered as distinct story species: **lead story**, framed as **"הסיפור המרכזי"** (first push, else first high_feed — serif display headline on a full-width hero band with a signal-tinted mesh + half-court arc + SIGNAL strength instrument), **מבזק bulletin strips** (remaining push), **"במוקד"** (high_feed, asymmetric editorial blocks — one major + a two-column grid), **"עוד מהפיד"** (feed, typographic rows with inline expand), and **"קריאה נוספת"** (low_feed, collapsed digest, 4 rows visible by default). A sticky **"לוח הסיגנל" signal board** (xl+ screens) holds a clickable vertical spectrum + topic filters + desk facts; on smaller screens the spectrum sits above the fold. The signal spectrum's level labels are **"לא לפספס"** (push) / **"במוקד"** (high_feed) / **"עוד מהפיד"** (feed) / **"קריאה נוספת"** (low_feed) — display copy only, the decision ids themselves (`push`/`high_feed`/`feed`/`low_feed`/`hidden`) are unchanged and still drive scoring. Decision badges are gone from the product feed. Each story carries a Hebrew **kicker** (entity/league/sport · event type via `storyLabels.js`) and important stories show the **desk voice** ("למה אצלך: …") with the reasoning steps expandable — the full trace stays in Debug. Titles render Hebrew-native: for MVP Hebrew sources `translatedTitle` is always `null` and every species falls back to `title` via the preserved `item.translatedTitle || item.title` logic. The RSS **subtitle is clamped to 2–3 lines** on every surface (lead/bulletins/editorial/stream) — earlier in the redesign this was briefly shown unclamped, which exposed that some sources' ingested subtitle field runs well past a normal deck length (see the backend subtitle fix above); the frontend clamp is now a permanent defensive layer regardless of ingested length. Subtitle is not a translation; there is no original-language block or "לא תורגם" warning. Feedback actions (`more_like_this`/`less_like_this`) are unchanged, offered as text buttons on lead/bulletins/editorial and icons on rows. Entrance/filter motion runs on Framer Motion and honors reduced-motion. The zero-articles empty state (`EditionEmptyState`, PR E) is a bespoke enlarged-`SignalMark` moment, not the generic shared component.

**Preferences / Calibration / Results (PR C):** Brought into the Feed's editorial voice on top of the PR B shell. A shared `DeskIntro` line (kicker + one sentence, no card) opens Preferences ("מה המערכת יודעת" — reads live topic/entity/muted counts off the active profile) and Calibration ("כיול"). Preferences' `TopicCard` is now a hairline-divided expandable row with a kicker line (priority · mode · leagues) instead of a bordered box with separate badges; its "important difference" callout was retoned from push-gold to `signal-ai` cyan (explanatory, not urgent — gold is reserved for push). Calibration's `HeadlineCard` gained a kicker line + serif headline instead of four pill badges; `InferenceDraftPanel`'s nested boxes became hairline dividers. **Every hook, handler, and `src/engine` call in Calibration is unchanged** — `inferPreferenceDraftFromCalibration`, `convertCalibrationDraftToUserProfile`, `scoreArticle`, `applySandboxProfile`/`resetSandboxProfile`, `updateProfile` are all byte-for-byte the same as before the redesign; only JSX/className changed. `PageHeader` itself was deliberately left untouched since it's shared with the ops console. Results (a coming-soon placeholder) was simplified to one centered moment.

**Debug view:** All articles with full scoring reasoning. Each article card shows the subtitle (when available) directly under the title, clamped to 3 lines, to provide classification context during QA. Also shows LLM classification metadata (PR 11): `classified_by` as a color-coded badge (neutral=rules, blue=llm, cyan=llm+rules_guardrail, red=failure, gold=low-confidence — see `classifiedByConfig.js`), `classification_provider` inline, `classification_confidence` as a percentage, and `classification_reason` as an italic line. Since #35 the Debug page also renders the persisted facts trace (sport-evidence chips + weights, LLM gate decision + reason, alias-to-id normalization, rejected LLM mentions, conflicts) and a per-row engine badge (`v2`/`legacy`/`js-local`). Comparison tab always uses local engine (cross-profile comparison not wired to backend).

**Signature details (PR E, self-directed):** The favicon (`public/favicon.svg`, the SignalMark bars motif) previously didn't exist as a file at all despite being referenced in `index.html` — every browser tab showed a broken/default icon through the entire redesign until this was caught and fixed. Also added: a `theme-color` meta + critical-CSS background fallback (kills flash-of-white before CSS loads), a sitewide themed `:focus-visible` ring (using the existing `--ring` token), a custom thin scrollbar, and a rebuilt 404 page ("אין אות" — no signal) — the 404 route renders outside `AppShell` entirely, so it had never been touched by any prior redesign PR and still shipped the original plain "404" box from Court Vision PR 1.

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

**2026-07-06 — Signal Intelligence Architecture v2, PR 3 (Relevance Visibility
Contract, #29).** `league`/`league_group`-scope topics now match through a
three-tier model instead of a single legacy `article.league` string: explicit
competition evidence (`primary_competition`/`article_competitions`, #28) →
legacy fallback (pre-ArticleFacts rows only) → team-membership reach (an
explicit `TEAM_ANCHORED_EVENTS` allowlist — signing/negotiation/release/
injury/trade/etc. — computed at scoring time from taxonomy memberships,
tagged `via_team_membership: comp:*` in the trace; `COMPETITION_ANCHORED_EVENTS`
events like `match_result`/`title_win`/`schedule` require explicit evidence
only, and an unlisted event type gets no membership reach — fail-closed, not
"everything not competition-anchored"). Membership reach is authoritative
through canonical `entity_ids` on post-ArticleFacts rows (never the legacy
display string); a match via membership alone, with no independent topic/
profile entity backing, is capped at `feed` (never `high_feed`/`push`) — a
ceiling, not a rank subtraction, so a Maccabi Ramat Gan signing still lands
`feed` via the Israeli Basketball League follow while a Deni Avdija trade
(entity-backed) still reaches `push`. The `major_only` mode's
`major_importance_fallback` → `low_feed` leak (any high-importance article
with no matched scope) was removed from both engines. Frontend consumes a
**generated** taxonomy artifact (`frontend/src/data/taxonomyReach.generated.json`,
produced by `backend/scripts/generate_taxonomy_export.py` from
`backend/app/taxonomy/`, freshness-guarded by a backend test) rather than a
hand-maintained JS mirror. See `docs/RELEVANCE_VISIBILITY_CONTRACT.md` for
the full contract, the sport=unknown decision, and the feed-ceiling
reasoning.

**2026-07-07 — Signal Intelligence Architecture v2, #40 (competition-reach
completion).** Part A (PR #41): taxonomy coverage expanded — NBA 30/30 teams,
EuroLeague 2025-26 20/20 clubs, IBL 15 clubs (+ Hapoel Haifa FC twin for
cross-sport alias safety); ACB/BSL/Greek/LBA/LNB audited and deliberately
left EL-clubs-only (audit table + season-uncertainty notes in
`docs/TAXONOMY.md`). Part B: the league match model is now **four-tier** —
a new **participant-set competition inference** tier sits between the legacy
fallback and membership reach: for competition-anchored events (except
`friendly_match`), the intersection of the participating *team* entities'
memberships identifies the event's competition **only when it is a
singleton** (Lakers ∩ Celtics = {NBA} → infer; Maccabi ∩ Hapoel TLV =
{IBL, EuroLeague} → abstain). Fail-closed by shape (extra teams only shrink
the intersection), relevance-time only (never persisted into ArticleFacts
fields), `match_kind: participant_inference`, trace
`via_participant_inference: comp:*`, exempt from the membership feed ceiling
(genuine event evidence), push discipline unchanged. Real-DB QA: the two
hidden NBA game results (Hornets–Wizards mock, Brooklyn–Sacramento real row)
flip hidden → feed for Guy; zero changes for Casual Deni Fan.

**2026-07-08 — Signal Intelligence Architecture v2, #32 (Preference Model
V2).** The backend feed is now scored by a layered **affinity engine**
(`app/services/preference_engine.py`) over `ProfileV2` (scope affinities
-2..+2 with explicit/calibration/learned provenance, scoped event deltas,
mute/never_show/always_push overrides — JSON on the profiles row).
Visibility is **consumed, not re-derived**: competition scopes call the same
four-tier `match_competition_names()` machinery as the legacy engine. Push
exists only via explicit `always_push` overrides (exact event match, no
alias widening). Every decision carries a structured contribution trace.
Flip performed after the Fable shadow checkpoint (241 real articles: Guy
96.3% agreement, Deni fan 100%, push parity exact); rollback:
`PREFERENCE_ENGINE=legacy`. The JS engine is frozen (local mode only, no v2
port). New surfaces: `GET /api/debug/shadow/{user_id}`, `GET /api/feed-engine`,
`PUT /api/profiles/{user_id}` (first mutation endpoint), Debug "מנוע v2"
shadow tab. `matched_topic` now returns canonical scope ids
(`team:*`/`comp:*`) instead of legacy topic_ids. Full contract + checkpoint
report: `docs/PREFERENCE_MODEL_V2.md`.

**2026-07-08 — Signal Intelligence Architecture v2, #33 (Calibration V2).**
Calibration is backend-owned end to end: one versioned 24-item dataset
(`app/calibration_v2/dataset.py`, factorial + contrast pairs), hierarchical
additive inference (median-based levels, support >=2, one answer can never
create an exclude, contradictions widen uncertainty toward neutral),
persistent apply through the ProfileV2 mutation path (`source="calibration"`
entries only — explicit/learned never touched, overrides never written),
ratings persisted per (user, item, dataset_version). New API:
`GET /api/calibration/items`, `POST /api/calibration/preview`,
`POST /api/calibration/apply`, `GET /api/calibration/responses/{user_id}`.
Both stale datasets deleted (backend 16-row seed, frontend 43-headline file
+ JS inference); the Calibration page is a thin backend client (local mode:
backend-required notice). See `docs/CALIBRATION_V2.md`.

**2026-07-08 — Signal Intelligence Architecture v2, #34 (Feedback
Learning).** Feedback events now carry click-time context (decision +
most-diagnostic attribution from the v2 contribution trace, captured
server-side) and drive **derived** learned adjustments — a pure function of
the non-retracted event log: activation at >=3 net consistent events,
magnitude cap +/-1, 90-day half-life decay, learned floor -1 (never an
exclude). Signal hierarchy: explicit > learned > calibration. Dismissing
actions hide that article from the feed immediately (per-article, not
profile). Scoped explicit suppression via
`POST /api/profiles/{user_id}/never_show` (most specific scope on the
article). Inspect/undo: `GET /api/learning/{user_id}`,
`POST /api/learning/{user_id}/reset` (tombstones — restores prior state
exactly); Preferences "נלמד" tab with per-row reset. `article_opened` is a
logged passive slot with no learning effect. See
`docs/FEEDBACK_LEARNING.md`.

**Note on the profile descriptions below (added 2026-07-09):** they document the
**legacy topic model**, still shipped for the legacy engine and the parity fixture
(`docs/fixtures/profile_parity.json`). The engine actually serving `/api/feed` is
**Preference V2** over `ProfileV2` payloads (#32 entry above;
`backend/app/seed/seed_profiles.py`, `docs/PREFERENCE_MODEL_V2.md`) — e.g. Guy's v2
profile expresses football/tennis as level -1 sport scopes with event deltas rather
than a `titles_only` mode, and push exists only via explicit `always_push` overrides.
The "Scope guards" and "Entity event rules" paragraphs below likewise describe the
legacy engine's mechanics.

**Demo profile: Guy (basketball power user)**
- Maccabi Tel Aviv Basketball: `entity` scope, very high priority — signing/negotiation/injury → `push`
- NBA: `league` scope, high priority, mode `all` — most events visible
- EuroLeague: `league` scope — high priority; `leagues: ["EuroLeague", "EuroCup"]` on both engines (#29 drift fix); non-Maccabi transfers → `high_feed` not `push`
- Israeli Basketball League: `league` scope — high priority; non-Maccabi teams (Maccabi Ramat Gan, Hapoel Holon, …) are visible via this broad follow, via membership reach when the article has no explicit league text
- European domestic basketball (ACB, BSL, Greek, LBA, LNB): `league_group` scope — moderate priority
- Football: `sport` scope, mode `titles_only` — **one authoritative policy** (#29 drift fix) applied identically on both engines: `major_transfer`/`title_win` → `low_feed`, everything else hidden (was `titles_only`/all-hidden on backend vs a leaky `major_only` on frontend)
- Tennis: `sport` scope, mode `titles_only` — only Grand Slam winners/finals visible

**Demo profile: Casual Deni Fan**
- Deni Avdija: `entity` scope, very high priority — trade/injury → `push`
- NBA: `league` scope, `followed_entities_only` mode — only articles mentioning Deni are visible
- Other basketball: `hidden` unless Deni is present

**Scope guards** prevent topic rules from bleeding across articles. A `maccabi_tel_aviv_basketball` topic (entity scope) only matches when the article's entities include Maccabi TLV — not all basketball articles. Without this, Maccabi-level `push` rules would fire on unrelated EuroLeague transfers.

**Entity event rules** (`entityEventRules`) allow per-entity overrides. Example: within the EuroLeague topic, a Maccabi TLV signing → `push`, but a non-Maccabi EuroLeague signing → `high_feed`.

**Profile drift guard (#29):** `docs/fixtures/profile_parity.json` is a canonical, hand-checked snapshot of every relevance-driving field on every shipped topic for both profiles. `backend/tests/test_profile_drift_guard.py` and `frontend/src/data/userProfiles.drift.test.js` each independently assert their profile normalizes to this file — either side drifting fails that side's test. Building this caught one additional pre-existing drift beyond football/EuroCup: `euroleague.schedule` was `low_feed` on backend, `hidden` on frontend; aligned to backend's `low_feed`.

**`less_like_this` feedback fix (#29):** `FeedbackControls.jsx` emits `less_like_this`, but it was missing from both `AppContext.jsx`'s `BACKEND_VALID_ACTIONS` and the backend's `routes_feedback.py` `VALID_ACTIONS` — the POST was silently dropped in backend mode. Added as its own action on both sides (persisted only, like every other feedback action today — no scoring effect until #34).

---

## 8. Classification State

### 8a. Deterministic Classifier (`backend/app/ingestion/classifier.py`)

The deterministic classifier is keyword-matching only — no NLP, no LLM. It always runs first, for all sources. For English basketball-only sources (`eurohoops`, `sportando`), it is the sole classifier. For Hebrew broad sources, its result is used as guardrail input when LLM is enabled.

**What it detects reliably:**
- Maccabi Tel Aviv Basketball (full English + Hebrew name forms; **standalone "מכבי" no longer resolves to any team** — the taxonomy PR made bare club-family names non-resolving to stop Maccabi Ramat Gan / Kiryat Gat contamination; see `docs/TAXONOMY.md`)
- Deni Avdija ("דני אבדיה", "אבדיה", "avdija", "deni")
- Oded Kattash ("קטש", "עודד קטש") as a strong Maccabi TLV basketball signal — since the taxonomy PR this is a registry data fact (`coach:oded_kattash` → `team:maccabi_tlv_bb`), not a code rule
- Israeli Basketball League: direct keywords ("ווינר סל", "ליגת העל סל", "הפועל תל אביב") + context inference (known domestic league opponents + Maccabi entity)
- NBA Hebrew nicknames (וויזארדס, הורנטס, בלייזרס, ניקס, סלטיקס)
- EuroCup vs EuroLeague disambiguation (EuroCup checked first)
- Football Maccabi clubs blocked before basketball keywords (`_FOOTBALL_MACCABI_KW`: מכבי חיפה, מכבי נתניה, מכבי פ"ת, מכבי יפו, etc.)
- Hapoel Tel Aviv disambiguation: resolved to basketball or football based on sport context; `ambiguous_club` tag when no context
- Hebrew event types: negotiation before signing (prevents "על סף חתימה" from misfiring as signing)
- Generic news with no entity → `importance=low` (prevents filler from polluting feed)
- **PR 11 fix:** `"אלופת"` and `"אלופות"` added to unambiguous championship keywords. These use regular pe (פ U+05E4) unlike "אלוף" (final pe ף U+05E3) — the Python `in` operator returned `False` for `"אלוף" in "אלופת"`. This fixes "ניו יורק אלופת ה-NBA" → `event_type=title_win`.
- **PR 11 fix:** `"mvp"` added to `_BASKETBALL_KW`. "MVP" is unambiguously basketball in Israeli sports context.
- **Issue #30 fix:** event types now pass through a shared semantic evidence contract (`classification/event_evidence.py`) in both rules and LLM merge paths. Specific non-news events require positive evidence; on doubt they fall back to `news`. `title_win` no longer accepts bare "title" language ("wants/dreams of a title"), `candidate`/`negotiation` block false `signing`, `schedule` blocks false `match_result`, and `release` is now a first-class event type with hospital/negation blockers.
- **Post-QA fix:** `_GRAND_SLAM_KW` expanded to include specific tournament names (roland garros, רולאן גארוס, wimbledon, וימבלדון, us open, australian open). "אלקאראז זוכה ברולאן גארוס" now correctly fires `grand_slam_winner`.
- **Post-QA fix:** `source_sport_hint` parameter added — pre-computed URL category hint flows through `classify()` → `_detect_sport()` as the first check before all keyword logic.

**Known classification defects (2026-07-09 investigation — FIXED by #60/#61/#62 on 2026-07-10; kept for history, see the header entry and issue #63 evidence):**
- False `title_win`/`finals_result` from champion-vocabulary evidence: champion epithets ("האלופה", "אלופת איטליה"), competition names containing champion words ("אלוף האלופים", "ליגת האלופות"), and aspirational win phrases ("לזכות באליפות") currently validate as confirmed events (~15 of 17 persisted `title_win` rows were false). Issue #60.
- LLM-echo sport circularity: for cross-sport club titles with no explicit evidence, a wrong LLM sport guess can be laundered into `entity_derived` evidence via post-merge enrichment and locked in. Issue #61.
- Evidence-coverage gaps (Israel Hayom `/sport/israeli-soccer/` hint, football transfer-market vocabulary, taxonomy entries). Issue #62.
Evidence and full traces: `docs/CLASSIFICATION_RELIABILITY_INVESTIGATION.md`.

**Confidence scoring:** 0.40 base + 0.15 (sport) + 0.05 (basketball-only source) + 0.15 (league) + 0.15 (entity) + 0.10 (non-news event type); capped at 0.95.

**`ambiguous_club` behavior:** When a full-name club phrase is present but no sport context resolves it, the article gets `sport=unknown`, `entities=[]`, tag `ambiguous_club`, and shows up as questionable in the quality endpoint.

**Known gaps (require LLM):** Multi-sport entities (Olympiacos, Hapoel TLV without context), unfamiliar Hebrew proper nouns (player/coach names not in keyword lists), NBA league context from player name alone (e.g., Brunson → NBA).

### 8b. LLM Classification (`backend/app/classification/`)

LLM classification is an opt-in overlay for Hebrew broad sources only. It does not change feed decision logic — the relevance engine still reads stored metadata deterministically.

**When it runs:** `source_id in {"walla_sport", "israel_hayom_sport", "ynet_sport", "one_sport", "sport5_sport"}` AND `CLASSIFICATION_PROVIDER != disabled`. (Sport5 is a disabled-by-default pilot; Ynet is an enabled RSS source; ONE is an enabled public-JSON source. Gating logic itself is unchanged.)

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
   - Guardrail 4: rules found specific event_type but LLM says "news" → use rules, then validate semantic evidence
   - Guardrail 4b: semantic event evidence contract rejects unsupported specific event types (title_win/signing/release/schedule/result/etc.) → fall back to validated rules event or news
   - Guardrail 5: importance never downgraded (rules high → LLM low: keep high)
   - Guardrail 6: league-sport incompatibility (EuroLeague + football → basketball; etc.) — fires before entity pruning
   - Guardrail 7: source URL category hint overrides LLM sport (Israel Hayom paths; Sport5 FolderID=274 since PR 13)
7. Entities: rules entities pruned for sport compatibility (basketball club entities removed when final sport ≠ basketball); LLM entities normalized through alias map and appended
8. Defense-in-depth (all paths): `normalize_league_sport_compatibility()` called for both rules-only and LLM-merge paths — no Article can be stored with an impossible sport/league combination
9. Defense-in-depth (relevance engine): entity scope matching checks `topic.sport` vs `article.sport` — a football article cannot match a basketball entity topic even if entities contain a stale basketball club name

**Per-run circuit breaker:** The first `httpx.ConnectError` (Ollama not running) opens a circuit for the rest of that ingestion run. Remaining articles use rules immediately (~2s total overhead, not 30 × 2s). Timeouts do not open the circuit. The circuit resets on the next `POST /api/ingest/run`.

**Backfill endpoint:** `POST /api/classify/backfill` reclassifies existing articles. Updates all 12 classification fields (sport, league, entities, event_type, event_certainty, importance, confidence, tags, classified_by, classification_provider, classification_reason, classification_confidence). Use after enabling Ollama on a database with existing articles.

See `docs/LLM_CLASSIFICATION.md` for full architecture details.

---

## 9. Translation Pipeline State (Post-MVP — Preserved, Not Active)

Translation is not used in the current MVP. All active sources (`walla_sport`, `israel_hayom_sport`, `ynet_sport`, `one_sport`) are Hebrew-native — no translation is needed. `TRANSLATION_PROVIDER=disabled` is the default and the correct MVP setting.

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
**Not translation** — current next actions are owned by the two active GitHub epics (#48 User Platform, #58 Reliability); see §13. Translation quality verification is a post-MVP concern for when English sources are re-enabled.

---

## 10. Current Known Limitations

- **Scheduler is opt-in and process-local (PR 13).** `INGESTION_SCHEDULER_ENABLED=false` by default — ingestion then runs only on `POST /api/ingest/run` / `run-now`. When enabled, an asyncio loop in the FastAPI lifespan ingests enabled sources every `INGESTION_SCHEDULER_INTERVAL_MINUTES`. Multi-replica deployments need a single scheduler worker or a distributed lock.
- **No fuzzy dedup / clustering.** Deduplication is URL-only. The same story from Eurohoops and Walla appears as two separate articles. `cluster_id` field exists in the model but is never populated.
- **Feedback learning is derived, not rule-mutating (by design — #34, live).** Feedback events drive bounded **learned** adjustments computed from the non-retracted event log at read time (activation at >=3 net consistent events, magnitude cap +/-1, decay, never an exclude); explicit topic/event rules and overrides are never silently mutated. See `docs/FEEDBACK_LEARNING.md` and §7.
- **Classification reliability defects (2026-07-09) — FIXED 2026-07-10** by #60 (event-assertion semantics), #61 (LLM-evidence provenance), #62 (coverage); protected by the golden-15 suite. Final residual imprecision (3 title_win rows — 1 genuine + 2 decision-neutral epithet/preview edge cases — and finals_result feature contamination, all invisible or near-invisible to both demo profiles) is documented in issue #63, which closed 2026-07-10 with the approved sign-off; the golden-17 suite protects the behavior.
- **User Platform PR 1 is landed; later surfaces remain future work.** Backend Auth Core (`users`, `auth_sessions`, `/api/auth/*`, current-user dependencies, CSRF middleware, fail-closed bypass config) is main-branch behavior. Existing consumer product flows still use legacy `{user_id}` routes until `/api/me/*` and frontend auth land in later PRs. Legacy/ops routes are not admin-gated yet.
- **No push notifications.** `push` is a decision level in the engine; no device notification delivery.
- **No body translation or summaries.** Only titles are translated. Article bodies are not ingested.
- **Limited source coverage.** MVP active sources: Walla Sport, Israel Hayom Sport, Ynet Sport, and ONE Sport. Eurohoops and Sportando are disabled (post-MVP). Sport5 is a scraping pilot (PR 13, disabled by default — no public RSS exists).
- **LLM classification runs on a small local model and is a known quality liability.** Production-style ingestion has used `ollama` + `qwen2.5:3b-instruct` (Gemini's 20-req/day free tier is insufficient; default remains `disabled`, and the no-LLM path is fully functional). The model hallucinates on some Hebrew headlines and the few-shot prompt is basketball-skewed — provider/prompt evaluation is reliability issue #65; pipeline robustness to wrong guesses is issue #61. Timing is instrumented (`fetch_ms`, `llm_avg_ms`, `llm_p95_ms`, fallback counts in `POST /api/ingest/run` responses).
- **Entity coverage is registry-bound (taxonomy PR).** ~45 canonical entities in `backend/app/taxonomy/entities.py` (all Winner League clubs incl. Maccabi Ramat Gan / Kiryat Gat, Israeli family-name football clubs, EuroLeague/EuroCup clubs, NBA teams/players, coach Kattash) with Hebrew + English aliases; cross-sport names abstain without sport evidence. Entities not in the registry are discarded from `article.entities`, but since #28 (landed) every rejected LLM mention is recorded in the classification trace (`rejected_llm_mentions`). Budućnost was added by #62; remaining registry policy questions (nickname strategy, volatile player entities) are product decisions tracked in #64.
- **Translation not active in MVP.** `TRANSLATION_PROVIDER=disabled` is correct for Hebrew-only MVP. Backend module, DB fields, and API routes are preserved for post-MVP re-enablement. Translation quality validation is a post-MVP concern.

---

## 11. Recommended Next Steps

> **Historical note:** an earlier version of this section pointed to the Signal Intelligence Architecture v2 roadmap — that initiative is **complete and closed** (Epic #27, Milestone 1; see `docs/INTELLIGENCE_ROADMAP.md` for its history). The authoritative execution order now lives in the two GitHub epics referenced below. The numbered list at the end of this section is a **non-authoritative operational backlog** kept for reference — verify each item against the epics and current code before acting.

> **Active track (2026-07-10): User Platform** — real accounts, authentication, onboarding, and per-user data isolation wrapped around the existing FACTS → VISIBILITY → PREFERENCE → LEARNING pipeline; contract `docs/USER_PLATFORM.md`; canonical graph in Epic #48. The Classification & Feed Reliability core track is **complete** (#59–#63 closed, Epic #58; the former #52 gate cleared 2026-07-10); its leftovers #64/#65 are open and non-blocking, and the golden-17 suite is a standing regression contract. **Canonical next actions: User Platform #50 (primary; then #51 → {#52 ∥ #53} per Epic #48). Reliability track core COMPLETE (#59–#63 closed); #64/#65 remain open, non-blocking.**

Non-authoritative operational backlog (historical numbering preserved):

1. ~~Re-run the LLM gating benchmark~~ — **historical**: the `feature/selective-llm-gating` branch merged long ago (PR 13 era; no open feature branch exists). The benchmark tooling still works from the Sources page (`ALLOW_DEV_RESET=true` + `CLASSIFICATION_PROVIDER=ollama`) and may inform reliability issue #65.
2. **LLM provider/prompt evaluation** — now owned by reliability issue **#65** (non-gating). The Ollama/Qwen setup steps in §12 remain valid; quality evidence so far is in `docs/CLASSIFICATION_RELIABILITY_INVESTIGATION.md`.
3. ~~Expand entity normalization map~~ — **done in PR 13** (25 canonical entities; see `docs/RSS_QUALITY_GUARDRAILS.md` §10a). Player/coach names still missing from the *deterministic* keyword lists remain open.
4. ~~Scheduled ingestion~~ — **done in PR 13** (asyncio loop in lifespan, `INGESTION_SCHEDULER_ENABLED`, disabled by default).
5. **Validate Sport5 pilot** — Run `POST /api/ingest/run?source_id=sport5_sport` against the live site, review classification quality in the debug view, then enable it from the Sources page toggle (or `PATCH /api/ingest/sources/sport5_sport`) if quality holds.
6. **Feed clustering / fuzzy dedup** — Use `difflib.SequenceMatcher` on titles across sources; populate `cluster_id`. Show one card per story.
7. ~~Feedback → profile mutation~~ — **done** (#34): feedback learning derives bounded adjustments from the event log at read time; scoped `never_show` exists via `POST /api/profiles/{user_id}/never_show`. See `docs/FEEDBACK_LEARNING.md`.
8. ~~More Hebrew sources — ONE Sport~~ — **done**: ONE Sport is onboarded and enabled (public JSON article endpoints; see §4). No further source onboarding is currently scheduled.
9. ~~Better relevance for LLM-classified articles~~ — **superseded** by the Classification & Feed Reliability track (Epic #58), which owns classification/feed decision quality end-to-end with regression-first sequencing.
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
AUTH_COOKIE_SECURE=false
AUTH_ADMIN_EMAIL=
AUTH_ADMIN_PASSWORD=
ALLOW_INSECURE_AUTH_BYPASS=false
CSRF_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174,http://localhost:5175,http://127.0.0.1:5173,http://127.0.0.1:5174,http://127.0.0.1:5175
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
Set `AUTH_COOKIE_SECURE=true` when serving the browser over HTTPS through Tailscale Serve; keep it `false` for plain localhost HTTP.
Set `CSRF_ALLOWED_ORIGINS=https://<machine>.<tailnet>.ts.net` as a local value when using Tailscale Serve HTTPS; never commit a real personal hostname.
Set `ALLOW_INSECURE_AUTH_BYPASS=true` only for explicit local legacy/ops development. Startup refuses this flag when `AUTH_COOKIE_SECURE=true`; `/api/auth/*` is never bypassed.
Set `INGESTION_SCHEDULER_ENABLED=true` to run ingestion automatically every `INGESTION_SCHEDULER_INTERVAL_MINUTES` (default 15). Disabled by default — the app then behaves exactly as before PR 13. Verify from the Sources page ("סטטוס ייבוא אוטומטי") or `GET /api/ingest/scheduler/status`.

### Frontend in backend mode
Create `frontend/.env.local`:
```
VITE_DATA_MODE=backend
```
Then:
```bash
cd frontend
npm run dev
```
App runs at http://localhost:5173 (fixed port, `strictPort: true` — fails loudly if 5173 is
already taken instead of drifting to 5174). API calls are same-origin relative paths
(`/api/...`, `/health`) proxied by Vite to `http://127.0.0.1:8000` — no `VITE_API_BASE_URL`
needed. Header badge shows "מצב נתונים: שרת".

Set `VITE_API_BASE_URL=http://127.0.0.1:8000` in `.env.local` only to bypass the proxy and
call the backend directly, cross-origin (e.g. for debugging the proxy itself).

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
# Use pytest collection for the current count. No test requires Ollama, a real API key,
# or live Sport5; conftest forces CLASSIFICATION_PROVIDER=disabled +
# INGESTION_SCHEDULER_ENABLED=false.
# Note: test_reset_returns_403_when_disabled requires ALLOW_DEV_RESET unset or =false in .env
```

### Manual RSS ingestion
```
POST http://127.0.0.1:8000/api/ingest/run                                        # MVP active sources only
POST http://127.0.0.1:8000/api/ingest/run?source_id=walla_sport                  # Hebrew — active
POST http://127.0.0.1:8000/api/ingest/run?source_id=israel_hayom_sport           # Hebrew — active
POST http://127.0.0.1:8000/api/ingest/run?source_id=ynet_sport                   # Hebrew — active
POST http://127.0.0.1:8000/api/ingest/run?source_id=one_sport                    # Hebrew — active, public JSON article API
POST http://127.0.0.1:8000/api/ingest/run?source_id=sport5_sport                 # Hebrew — scraping pilot, disabled by default (manual run works)
# POST http://127.0.0.1:8000/api/ingest/run?source_id=eurohoops                  # disabled — set enabled=True in config.py to re-enable
# POST http://127.0.0.1:8000/api/ingest/run?source_id=sportando                  # disabled — set enabled=True in config.py to re-enable

POST http://127.0.0.1:8000/api/ingest/scheduler/run-now                          # same as scheduled run (enabled sources), shared lock
GET  http://127.0.0.1:8000/api/ingest/scheduler/status                           # scheduler + lock state
GET  http://127.0.0.1:8000/api/ingest/source-health                              # per-source freshness/health
```
`POST /api/ingest/run` (no source_id) only runs sources with `enabled=True` in `config.py`.
For MVP this means `walla_sport` + `israel_hayom_sport` + `ynet_sport` + `one_sport`. All ingestion triggers share
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

> ⚠️ **Never do this to the real corpus DB.** `backend/data/signal_sports.db` holds the real
> ingested article corpus that serves as regression/replay evidence for the reliability track
> (Epic #58) — protecting it is a standing invariant in both active epics. Only ever reset a
> **scratch** database: point `DATABASE_URL` at a different file first, then delete that file.

```bash
cd backend
# ONLY for a scratch DB configured via DATABASE_URL — never data\signal_sports.db
del data\scratch.db
# Restart backend — tables and seed data recreated automatically
```

---

## 13. Handoff Prompt for a New Chat / New Tool

This section is written to be self-sufficient for **any** coding agent picking up
this project cold — Claude, Codex, or a human — with no prior conversation
history. Read `docs/CURRENT_PROJECT_STATE.md` fully first; it is the
authoritative, up-to-date summary. Do not trust `docs/IMPLEMENTATION_AUDIT.md`
as current state — it is an explicitly-marked historical snapshot from before
the backend and the frontend redesign existed.

**Where things stand (2026-07-09):** Backend is a working FastAPI + SQLite app
with real Hebrew RSS ingestion (Walla, Israel Hayom, Ynet, ONE active; Sport5 a
disabled-by-default scraping pilot), a deterministic classifier with an
optional LLM overlay, and a large green pytest suite (run
`pytest tests/ --collect-only -q` for the current count — do not trust numbers
quoted in docs). The **Signal Intelligence Architecture v2** initiative is
COMPLETE and closed (Epic #27, Milestone 1): the Preference V2 affinity engine
serves `/api/feed`, Calibration V2 is backend-owned, feedback learning derives
bounded adjustments from the event log, and `docs/RELEVANCE_CONTRACT.md` is
the umbrella contract for FACTS → VISIBILITY → PREFERENCE → LEARNING. The
frontend completed a full visual rebuild earlier (Court Vision + PRs A–E) —
see `docs/FRONTEND_DESIGN_SYSTEM.md`.

**There are two active tracks (2026-07-09), designed to run in parallel:**

1. **User Platform** (Milestone 2, Epic #48, issues #49–#55) — real accounts,
   authentication, onboarding, and strict per-user isolation, wrapped around
   the intelligence pipeline without changing it. Issue #49 / PR #56 landed
   backend Auth Core on main; auth/session infrastructure exists, but product
   flows are not yet migrated to `/api/me/*` and legacy/ops route gating has
   not landed (`user_id` remains caller-supplied on legacy routes). Contract:
   `docs/USER_PLATFORM.md`. **The canonical dependency graph, issue states,
   and review gates live in Epic #48 — trust it over any doc snapshot.**
   Next unblocked issue: #50.
2. **Classification & Feed Reliability** (Milestone 3, Epic #58, issues
   #59–#65) — regression-first hardening of classification facts, driven by
   the 15-case investigation `docs/CLASSIFICATION_RELIABILITY_INVESTIGATION.md`.
   **The canonical dependency graph lives in Epic #58.** State 2026-07-10:
   **core track COMPLETE** — #59–#63 closed (PRs #66–#70), sign-off approved,
   all 17 golden cases positive. Open: #64 (product decisions), #65
   (non-gating LLM eval). Next unblocked work is User Platform #50.

**Cross-track gate: CLEARED (2026-07-10).** Reliability Sign-off #63 closed
with the full evidence bundle and product approval — #52 (onboarding) now
depends on #51 only. The golden-17 suite plus the committed QA snapshots
(`docs/qa/reliability_baseline.json`, `docs/qa/reliability_post_fix.json`)
are the standing regression contract for classification behavior.

**Review gates are model-independent contracts written in the issue bodies**
(#52 Product Review — human product judgment; #54 Security/Authorization
Review + Regression Gate; #63 Reliability Sign-off). No review step depends
on any specific model, tool, or past conversation. Each issue body is a
self-contained contract with scope, non-goals, acceptance criteria, required
tests, verification, and a handoff requirement for the finishing PR.

The two seeded demo profiles (`guy`, `casual_deni_fan`) have credential-less
demo `users` rows and remain permanent QA fixtures; zero unintended decision
drift for either profile is a standing regression requirement across both
tracks.

**Reusable startup prompt for any implementing agent** (Claude Code, Codex,
or other — no prior context assumed):

> You are working on Signal Sports. Read `docs/CURRENT_PROJECT_STATE.md`
> fully (especially §13), then the epic for your track (GitHub #48 for User
> Platform, #58 for Reliability) to find the canonical dependency graph, then
> read your assigned issue completely, including its architecture-contract
> links (`docs/USER_PLATFORM.md` or
> `docs/CLASSIFICATION_RELIABILITY_INVESTIGATION.md` +
> `docs/RELEVANCE_CONTRACT.md`). Before writing code: verify the issue's
> dependencies are actually closed and that no blocker section says
> "do not start". Implement only what the issue scopes — its Non-goals
> section is binding; if you believe scope must grow, comment on the issue
> instead of expanding silently. Preserve the standing invariants: the two
> demo profiles' decisions must not drift unintentionally, positive
> regression cases must stay green, push happens only via explicit overrides,
> the corpus DB is never reset, and the frozen JS engine stays frozen. Run
> the issue's required tests plus the full backend suite (and frontend
> test/lint/build when touched). Update docs the issue names. Open a PR that
> reports against the issue's Handoff requirement section: what changed, what
> was preserved, test evidence, replay/QA deltas where required, and known
> gaps. If your issue has a review-gate section, request that review
> explicitly and do not merge without it.

**Working-style rules that have held throughout this project** (confirm they
still apply, but they've been consistent):
- Respond in Hebrew when the conversation is in Hebrew.
- Be direct and practical; don't pad answers.
- Don't assume the state of the code — if unclear, read the actual files or
  ask, rather than guessing from a doc that might have drifted.
- Don't change code without being asked. For audits/reviews, be honest and
  specific about what's weak, generic, or fake — don't soften findings.
- `backend/`, `src/context`, `src/api`, `src/engine`, `src/data` are treated
  as a stable contract during frontend-only work; changes there need
  explicit authorization (though it has been granted before, e.g. the
  ingestion subtitle fix in §1, when a real bug's root cause lived there).
- Every meaningful change: run the relevant test suite, lint, and build
  before calling it done. For frontend UI work, verify live in a running
  browser (both `local` and `backend` data modes), not just unit tests.

**Still-open items outside the User Platform milestone** (operational backlog,
see §11):
1. LLM provider/prompt evaluation — now reliability issue #65 (non-gating).
   Gemini's free tier (20 requests/day) proved too limited for even one
   ingestion run; the current provider is local Ollama + `qwen2.5:3b-instruct`,
   a known quality liability. See `docs/LLM_CLASSIFICATION.md` and the
   investigation report.
2. Feed clustering / fuzzy dedup — still URL-only; `cluster_id` exists but is
   never populated. This is the single most-repeated "still fake" finding
   across every audit pass of this project.
3. ~~Feedback → profile mutation~~ — **done** (issue #34): feedback learning
   derives bounded adjustments from the event log at read time; see
   `docs/FEEDBACK_LEARNING.md`.
4. Base44 dependency cleanup (Stripe, three.js, react-leaflet, etc. still in
   `package.json`, unused) — explicitly scoped as separate from any redesign
   or feature PR; never scheduled.
5. Private Mobile Access backlog (#16–#23) — Tailscale flow works; mobile UX /
   PWA-lite issues remain open. Auth Core now adds same-origin cookie sessions
   designed for this chain; use explicit `AUTH_COOKIE_SECURE=true` when serving
   through Tailscale HTTPS.

---
