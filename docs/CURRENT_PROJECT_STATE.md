# Signal Sports — Current Project State

**Verified 2026-11-17** against `main` (`860c9ac`), the running worker, the live corpus (read
only) and GitHub issues. This is the cold-start orientation for an agent or human with no
conversation history. It states what is true now and points to the contract docs for detail; it
does not repeat them. Product intent and working rules are in [../CLAUDE.md](../CLAUDE.md); the
doc index is [README.md](README.md). The previous, longer version of this file (with the
milestone-13 planning narrative) is archived as
[archive/CURRENT_PROJECT_STATE_2026-11-16.md](archive/CURRENT_PROJECT_STATE_2026-11-16.md).

Runtime facts below carry their verification date. Re-check before relying on them:
`powershell -File scripts\worker.ps1 -Status`, a read-only DB query, `gh issue list`.

---

## 0. Status at a glance

| Area | State (verified 2026-11-17) |
|---|---|
| Where it runs | **The owner's Windows PC**, `DEPLOY_ENV=local`. Phone access over Tailscale Serve ([MOBILE_REMOTE_ACCESS.md](MOBILE_REMOTE_ACCESS.md)). The hosted stack (`deploy/`) is built and CI-rehearsed but runs nowhere ([DEPLOYMENT.md](DEPLOYMENT.md)) |
| Worker | **Running** since 2026-11-15 22:47 (local time), 5-minute cycles succeeding |
| API + Vite | **Not running** at the check (ports 8000/5173 closed), so the authenticated app is unreachable until started. Nothing starts them at boot |
| Public demo | **Live** at signal-sports-demo.web.app (since 2026-11-11). It shows guy's feed and a scores-only results page with box scores, read-only, republished hourly by the Windows task `SignalSportsDemoPublish` ([DEPLOYMENT.md](DEPLOYMENT.md) §17) |
| Consumer UI | Milestone 15 "Signal UI" is **on `main`** (PR #551, merged 2026-11-15). Later results/demo features #557–#566 merged 2026-11-16 |
| LLM | `CLASSIFICATION_PROVIDER=openai_compat`, Groq `openai/gpt-oss-20b` since 2026-10-25 — an interim choice ([qa/LLM_BAKEOFF_2026-10-25.md](qa/LLM_BAKEOFF_2026-10-25.md)). The formal evaluation and switch (#262) is still open. Ollama is no longer the production classifier; `scripts/worker.ps1` still starts it if installed, which is harmless |
| Sources | Walla, Israel Hayom, Ynet, Sport5 (override on), ONE (override on since 2026-11-01). English sources off |
| Corpus | 6,955 RSS articles, 2026-07-10 → today. `protected_articles` holds 1,549 rated/correction ids (#255 backfill applied). Retention stays **off** |
| Telegram push | **Off** since 2026-09-13 (`TELEGRAM_NOTIFICATIONS_ENABLED=false`); 21 notifications ever, the last on 2026-07-24 |
| Real usage | 6 users, 9 feedback events ever (last 2026-10-26), last login session 2026-10-26. The learning loop has effectively no real data |
| Feed quality | Census gate baselines (2026-11-01, stored facts): Guy shown precision 95.9%, feed+ recall 73.9%. Census #3 fit half: 90% / 74%, no demonstrated change; held-out half sealed (§9) |
| Open milestones | 10 Live Pilot (7 open), 11 Census #3 (2), 13 Off the owner's machine (12), 15 New UI (0 open, not yet closed). Which comes next — M13 or M10 — is an open owner decision (#427) |

---

## 1. Product in one paragraph

Signal Sports is a personalized, Hebrew-first sports news intelligence feed. It ingests Israeli
sports news, works out what each article is about (sport, competition, teams, players, event
type, importance), and shows each user only what is worth *their* attention: `hidden`,
`low_feed`, `feed`, `high_feed` or `push`. The same article can be `push` for one user and
`hidden` for another. Vision: [PRODUCT_UNDERSTANDING.md](PRODUCT_UNDERSTANDING.md). Binding
principles (facts vs decisions, rare explicit push, abstention, corpus safety, Hebrew UI /
English code): [../CLAUDE.md](../CLAUDE.md).

---

## 2. Architecture

```
Phone ──Tailscale Serve (HTTPS)──┐
Desktop browser ─────────────────┤
                                 ▼
          Vite dev server :5173  (React app; proxies /api and /health)
                                 ▼
          API     uvicorn app.main:app :8000     (requests only — NO scheduler)
                                 │  shared SQLite (WAL)  backend/data/signal_sports.db
          Worker  python -m app.worker           (5-min cycles behind a durable DB lease)
                                 │
     ┌───────────────┬───────────┴────────┬─────────────────────────┐
     LLM (Groq,      Results providers     Telegram Bot API          News sources
     openai_compat)  (ESPN, EuroLeague,    (delivery off)            (RSS, Sport5 HTML,
                     Winner, Bamboo,                                  ONE JSON)
                     TheSportsDB)

Public demo:  export_demo_snapshot.py (read-only DB) → static JSON → build:demo → Firebase Hosting (hourly)
```

**One ingestion cycle** (`app/ingestion/orchestration.py::orchestrate_cycle`): acquire the
single-flight lease → for each enabled source: fetch → filter → URL dedup → classify (rules →
LLM gate → merge guardrails → ArticleFacts → event re-validation) → insert → story anchors →
clustering; then notification planning and dispatch, results sync (throttled to ≥30 min),
retention (disabled), release the lease. Manual runs from the API (`/api/ingest/*`) use the same
function. Details: [RSS_INGESTION.md](RSS_INGESTION.md), [SCHEDULER.md](SCHEDULER.md).

**One feed request** (`app/services/feed_service.py`): 36h freshness window (consumer feeds) →
per-article Preference V2 scoring (visibility tiers → affinity layers → learned adjustments →
overrides) → per-user cluster collapse (card decision = max over visible members). Details:
[RELEVANCE_CONTRACT.md](RELEVANCE_CONTRACT.md).

| Layer | Where | Contract |
|---|---|---|
| Frontend | React 18 + Vite 6, `frontend/src/` | [FRONTEND_DESIGN_SYSTEM.md](FRONTEND_DESIGN_SYSTEM.md) |
| API + worker | FastAPI, Python 3.13, `backend/app/main.py`, `worker.py` | [SCHEDULER.md](SCHEDULER.md) |
| Persistence | SQLite via SQLAlchemy 2, the only database the app can use; additive soft migrations at startup. An unused Postgres Compose service is groundwork only | [DEPLOYMENT.md](DEPLOYMENT.md) §15 |
| Sources & adapters | `app/ingestion/` | [RSS_INGESTION.md](RSS_INGESTION.md) |
| Classification | `app/ingestion/classifier.py` (rules), `app/classification/` | [ARTICLE_FACTS.md](ARTICLE_FACTS.md), [LLM_CLASSIFICATION.md](LLM_CLASSIFICATION.md), [RSS_QUALITY_GUARDRAILS.md](RSS_QUALITY_GUARDRAILS.md) |
| Taxonomy | `app/taxonomy/` — 117 entities (79 teams, 31 players, 2 coaches, 5 executives), 23 competitions | [TAXONOMY.md](TAXONOMY.md) |
| Relevance | `app/services/preference_engine.py` (V2, default), `relevance_engine.py` (visibility; legacy engine = rollback) | [RELEVANCE_CONTRACT.md](RELEVANCE_CONTRACT.md), [RELEVANCE_VISIBILITY_CONTRACT.md](RELEVANCE_VISIBILITY_CONTRACT.md), [PREFERENCE_MODEL_V2.md](PREFERENCE_MODEL_V2.md) |
| Profile acquisition | interests, calibration, feedback learning | [INTERESTS.md](INTERESTS.md), [CALIBRATION_V2.md](CALIBRATION_V2.md), [FEEDBACK_LEARNING.md](FEEDBACK_LEARNING.md) |
| Clustering | `app/clustering/` (deterministic; no LLM or embeddings) | [CLUSTERING.md](CLUSTERING.md) |
| Freshness | one shared predicate for feed, clusters, push | [FEED_FRESHNESS.md](FEED_FRESHNESS.md) |
| Notifications | `app/notifications/` (planner, outbox, dispatcher, Telegram) | [NOTIFICATIONS.md](NOTIFICATIONS.md) |
| Results | `app/results/` (sync, providers, health, detail, player mapping) | [RESULTS.md](RESULTS.md) |
| Accounts & auth | cookie sessions, Argon2, CSRF, Google sign-in, email verification | [USER_PLATFORM.md](USER_PLATFORM.md) |
| QA tooling | `app/qa/`, `backend/scripts/` | §9 |

---

## 3. Production configuration (the untracked `backend/.env`, verified 2026-11-17)

Only flags that differ from, or matter beyond, the defaults in `backend/.env.example`.

| Flag | Value | Note |
|---|---|---|
| `CLASSIFICATION_PROVIDER` / `_MODEL` / `_BASE_URL` | `openai_compat` / `openai/gpt-oss-20b` / Groq | Interim (#262 open) |
| `TRANSLATION_PROVIDER` | `disabled` | Hebrew-only product; translation is post-MVP ([TITLE_TRANSLATION.md](TITLE_TRANSLATION.md)) |
| `SCHEDULER_ENABLED` / `_INTERVAL_SECONDS` | `true` / `300` | |
| `CLUSTERING_ENABLED` | `true` | |
| `FEED_FRESHNESS_ENABLED` | `true` (36h) | |
| `RESULTS_SYNC_ENABLED` | `true` | |
| `RESULTS_PROVIDER_ROUTES` | `comp:nba=espn_nba`, `comp:euroleague`/`comp:eurocup=euroleague`, `comp:ibl`/`comp:winner_cup`/`comp:il_super_cup=winner`, `comp:ligat_haal=bamboo` | Unrouted competitions use TheSportsDB ([RESULTS.md](RESULTS.md) §3, §12–§15) |
| `RESULTS_DETAIL_ENABLED` | `true` | Box scores, top scorers, chosen-player lines ([RESULTS.md](RESULTS.md) §11) |
| `TELEGRAM_NOTIFICATIONS_ENABLED` | `false` | Off since 2026-09-13; re-enabling is #251 |
| `RETENTION_CLEANUP_ENABLED` | unset (false) | **Never enable on the real corpus** (deletes old rows; rated ones are protected, unrated history is not) |
| `ALLOW_DEV_RESET` / `ALLOW_CORPUS_DB_RESET` | `false` | |
| `MAIL_BACKEND` | `console` | Signup links are logged, not emailed; a real SMTP provider is #333 |
| `DEPLOY_ENV` | unset (`local`) | Local mode on the corpus refuses fake LLM, retention and the auth bypass, and warns on dev-reset flags ([../AUDIT_REPORT.md](../AUDIT_REPORT.md) M2) |
| Source overrides (DB table `source_overrides`) | `sport5_sport` on, `one_sport` on, `sportando` off | Sport5's code default still says "pilot, disabled" (#395) |

---

## 4. Sources

| Source | Type | Live | Articles stored (2026-11-17) |
|---|---|---|---|
| `walla_sport` | RSS | on | 2,727 |
| `israel_hayom_sport` | RSS + `/sport/` allowlist | on | 1,496 |
| `ynet_sport` | RSS | on | 1,219 |
| `one_sport` | public JSON (html_scrape adapter) | on (override, 2026-11-01, #258) | 1,180 |
| `sport5_sport` | HTML scrape | on (override) | 333 |
| `eurohoops`, `sportando` | RSS, English | off | post-MVP, with translation |

A failed RSS fetch is recorded as a failure (#365). Sport5 and ONE still log and swallow fetch
errors, so their runs read "fetched 0, no errors" during an outage (#439). Contract, URL hints,
probe history: [RSS_INGESTION.md](RSS_INGESTION.md).

---

## 5. Backend

**Tables:** `articles`, `profiles` (incl. `profile_v2` JSON), `users`, `auth_sessions`,
`pending_registrations`, `user_identities`, `oauth_pending`, `pending_google_registrations`,
`password_reset_tokens`, `reauth_grants`, `usage_days`, `feedback_events`, `calibration_responses`, `calibration_headlines`
(legacy, unused), `sources`, `source_overrides`, `ingestion_runs` (incl. `metrics` JSON),
`scheduler_cycles`, `scheduler_lease`, `worker_status`, `story_clusters`, `cluster_edges`,
`notification_events`, `notification_story_members`, `notification_watermarks`,
`protected_articles`, `game_results`, `game_details`, `game_player_lines`,
`results_player_mappings`, `results_chosen_players`, `results_sync_state`, `results_sync_lease`,
`results_provider_health`. The ORM is `backend/app/db/orm_models.py`. Startup creates missing
tables, applies additive column migrations (fail-loud) and seeds empty tables. There is no
migration history (#198).

**API surface** (exact inventory: OpenAPI `/docs`; `tests/test_authz_inventory.py` enforces a
gate on every route):

| Surface | Access |
|---|---|
| `/health` | public |
| `/api/auth/*` (signup, login, logout, session, email verification, Google start/callback/link, password forgot/reset) | public; mutating routes CSRF-checked |
| `/api/me/*` (profile, feed, results, feedback, learning, never_show, interests, calibration, onboarding, password, account, Google connect/disconnect) | the session user's own data |
| `/api/taxonomy/catalog`, `/api/calibration/items`, `/api/calibration/preview`, `/api/articles[/{id}]`, `/api/feed-engine` | any session |
| `/api/feed/{user_id}`, `/api/debug/*`, `/api/profiles/*`, `/api/learning/{user_id}[/reset]`, `/api/feedback[/{user_id}]`, `/api/calibration/apply`, `/api/calibration/responses/{user_id}`, `/api/results/{user_id}`, `/api/results/sync[/state]` | admin (view-as / QA) |
| `/api/ingest/*`, `/api/scheduler/*`, `/api/notifications/*`, `/api/classify/*`, `/api/translations/*`, `/api/dev/*` | admin, router-level fail-closed; `/api/dev/*` also needs `ALLOW_DEV_RESET` and refuses the corpus without `ALLOW_CORPUS_DB_RESET` |

Auth details (pending registrations, Google auto-link to existing accounts, limits, the shared
CSRF/CORS origin list): [USER_PLATFORM.md](USER_PLATFORM.md). Known weaknesses: in-process rate
limiters ([../AUDIT_REPORT.md](../AUDIT_REPORT.md) M4; #200); login is limited per account, per
client IP and globally (H1 resolved), but hosted clients still share nginx's IP bucket.

---

## 6. Frontend

The consumer app is the **Signal UI** (approved 2026-11-13, milestone 15, on `main` since
2026-11-15): a navy collapsing header with the tabs הפיד שלי · תוצאות · העדפות; a lead block only
for a push, an important row, compact stream rows, a sticky side column and a results strip; a
filter panel (importance levels, leagues, sources); one `/preferences/:tab?` destination
(following · calibration · learned · muted); and a grouped results page with box-score dialogs.
The ops console (`/sources`, `/debug`, `/llm-qa`, admin only) keeps its own older shell. Visual
contract and engineering rules: [FRONTEND_DESIGN_SYSTEM.md](FRONTEND_DESIGN_SYSTEM.md); the
reference mock is in [design/2026-11-13-feed-direction/](design/2026-11-13-feed-direction/README.md).

| Route | Page | Access |
|---|---|---|
| `/login`, `/signup`, `/verify-email`, `/forgot-password`, `/reset-password` | auth | public |
| `/welcome` | onboarding (interests → calibration → feed) | session |
| `/` | feed | session |
| `/preferences[/calibration\|learned\|muted]`, `/results`, `/account` | product pages (`/interests`, `/calibration` redirect) | session |
| `/sources`, `/debug`, `/llm-qa` | ops console | admin |

**Data modes** (`VITE_DATA_MODE`): `backend` is the real product (same-origin `/api` through the
Vite proxy; the server decides everything). `local` (the default when unset) renders mock data
through the **frozen** legacy JS engine (`src/engine/relevanceEngine.js`) in a lazy chunk; it is a
UI preview, not the product's intelligence.

**Public demo** (`frontend/demo.html` → `src/demo/`, `npm run build:demo` → `dist-demo/`): the
same `SignalFeedView`, read-only, from static snapshots (feed, results, allowlisted public
statistics, box scores, upcoming games). It mounts no router, auth or API client;
`npm run check:demo-bundle` enforces that in CI. Dark/light toggle persisted per device.

**Browser verification:** `npm run capture:ui` (hermetic, needs Chrome). The Vite 500 KB chunk
warning still fires in backend mode (#436 covers the admin debug-feed load).

---

## 7. Profiles & relevance

**Engine:** Preference V2 over **ProfileV2** — scope affinities (sport, competition, team,
player, coach; level −2…+2; source explicit/calibration/learned), event affinities (global or
scoped deltas) and overrides (`always_push`, `never_show`, mute). Visibility comes from four-tier
competition matching (explicit evidence → legacy league → participant inference → membership
reach, the last capped at `feed`) plus closed-league reach for one-club NBA stories (#404,
capped at `feed`, never a push). Precedence: explicit > learned > calibration; scoped beats global.

**Live profiles are DB rows.** Changing seeds does not change them; live changes go through a
reviewed `backend/scripts/apply_*.py` run after a backup.

- **`guy`** (owner): Maccabi TLV basketball +2; EuroLeague, EuroCup, NBA, IBL +1; Hapoel Tel Aviv
  basketball at medium with scoped deltas (#257, applied); ACB/BSL/Greek/LBA/LNB −1; football and
  tennis −1; Deni Avdija and Oded Kattash +1. 69 event affinities. 6 `always_push` (Maccabi
  signing, major signing, negotiation, `club_governance`; NBA star trade; Deni major trade) and
  3 `never_show` (Maccabi pre-match, schedule, generic preview). Owner rules: no injury push
  (2026-11-04), a title is `high_feed` at most (2026-11-06), live in-game score updates are hidden
  for every profile (2026-11-16).
- **`casual_deni_fan`** (demo): Deni Avdija +2 only; pushes on a Deni major trade or relocation.
  Must not drift unintentionally — the gates check it.

**Push discipline:** push needs an explicit `always_push` match, and for signing, negotiation and
`club_governance` also factual severity (a current agreement/completion or a concrete step) with
the followed scope as a title subject (#192, #229). Notifications are planned once per story
(cluster lineage) ([NOTIFICATIONS.md](NOTIFICATIONS.md)).

**Profile acquisition:** explicit interests ([INTERESTS.md](INTERESTS.md)), interest-aware
calibration ([CALIBRATION_V2.md](CALIBRATION_V2.md)), feedback learning
([FEEDBACK_LEARNING.md](FEEDBACK_LEARNING.md); ≥3 net consistent events, capped ±1, 90-day
half-life, derived at read time). Census calibration (#237) is an offline fourth path. Free-text
preference input was deliberately not built.

**Legacy topic model:** pre-V2 profiles still ship for the rollback engine and the frozen JS
engine; `docs/fixtures/profile_parity.json` pins them and drift tests enforce it.

---

## 8. Classification

Rules first, always; the LLM is gated (force-called on unknown sport, ambiguous club or low
confidence; skipped when rules are strong), and its proposals pass merge guardrails and semantic
event evidence. Specific event types need positive evidence; `news` is abstention. Contracts:
[ARTICLE_FACTS.md](ARTICLE_FACTS.md), [LLM_CLASSIFICATION.md](LLM_CLASSIFICATION.md), and the
numbered rule changelog [RSS_QUALITY_GUARDRAILS.md](RSS_QUALITY_GUARDRAILS.md).

**Structural limits (measured, not fixed):**
- **Person coverage:** besides 3 NBA players, only Maccabi and Hapoel Tel Aviv people are
  registered (#259); the roster is season data (#377).
- **Cross-sport clubs** (#194): `מכבי תל אביב`, `הפועל ת"א` without sport evidence stay
  `sport=unknown`; an LLM-proposed club survives only with explicit or corroborated basketball
  evidence (#61, #345).
- **`news` with no competition** dominates false hides (census #2: 71 of 76).
- **LLM failure with no sport** stays hidden (#409, owner decision); counted per run as
  `rules_fallback_unknown_sport`.
- Open classification issues: #380, #381, #382, #387, #388, #401, #403, #405, #408, #418, #441.

---

## 9. Quality measurement

| Instrument | What | How |
|---|---|---|
| **Census gate** (#254) | 804 census #2 owner ratings, directional checks (shown precision, feed+ recall, push precision/recall/volume, ≥2-notch gaps, Deni drift). Two baselines: `stored` facts (relevance/profile changes) and `--facts rerun` (rules-only, for classifier/taxonomy changes) | `cd backend; .venv\Scripts\python scripts/feed_ground_truth.py gate --census [--facts rerun]`. Baselines in `docs/qa/census_gate*_baseline.json`; regenerate only after a reviewed delta ([RELEVANCE_CONTRACT.md](RELEVANCE_CONTRACT.md) §Quality gate) |
| **N05 gate** | 282 ratings on the frozen July corpus | `scripts/feed_ground_truth.py gate` ([qa/N05_FEED_GROUND_TRUTH.md](qa/N05_FEED_GROUND_TRUTH.md)) |
| Census #2 | 804 articles, all owner-rated | [qa/CENSUS_2026-10.md](qa/CENSUS_2026-10.md) |
| Census #3 | 300 articles (#241); fit half reviewed (n=150: precision 90%, feed+ recall 74%); held-out half **sealed** — when to open it is #426 | [qa/CENSUS_3_2026-11.md](qa/CENSUS_3_2026-11.md) |
| Rerun diff | in-memory rules-only rerun of the corpus vs ratings | `scripts/corpus_rerun_diff.py snapshot / compare` |

Binding lessons: read recall and shown precision separately; owner ratings carry about one notch
of noise, so re-rate large gaps before acting and never calibrate on n<5 or without a held-out
half; **never run a blanket rules-only backfill** — stored rows change only through targeted,
reviewed, backed-up correction scripts. Skills: `signal-real-data-qa`, `signal-quality-eval`.

---

## 10. Known limitations & risks

- **Not always on.** Nothing starts the API, Vite or the worker at boot or after a crash, and
  nothing alerts. The feed shows when it was last updated (#249), which is a signal, not an alert.
- **Single machine, single SQLite file.** PC backups are manual (`backend/scripts/backup_db.py`,
  WAL-safe, verified). The hosted nightly off-host backup exists in the repo but runs nowhere.
- **Telegram off**, so push stories reach nobody (#251).
- **No real usage** to train or validate the learning loop (milestone 10).
- **Recall:** roughly one wanted story in four is still hidden (census gate feed+ recall ≈ 74%);
  push recall is low (mostly institutional Maccabi news).
- **Platform debt:** no migration history (#198); signup/login abuse protection is a gate before
  widening access (#200); React 18 (#428; the FastAPI cap was lifted 2026-11-17, audit L9). See
  [../AUDIT_REPORT.md](../AUDIT_REPORT.md) for the 2026-11-17 audit.
- **Local worktree sprawl** on the owner's PC (40+ old worktrees) — housekeeping, not product.

---

## 11. Open work (GitHub, 2026-11-17)

- **Owner decisions:** #427 next milestone (M13 hosting vs M10 pilot); #426 Census #3 held-out
  half; #267 where the stack runs ([HOSTING_PLAN.md](HOSTING_PLAN.md) §18 is the proposal).
- **M13 Off the owner's machine:** #262 hosted-model evaluation, #263 images (built), #266
  backups, #268 provision, #269 cutover (owner-run), #270 snapshots, #200 abuse gate, #319
  backfill/lease coordination, #333 SMTP, #335 Google QA. Repository preparation is done and
  CI-rehearsed ([DEPLOYMENT.md](DEPLOYMENT.md)); nothing is provisioned.
- **M10 Live Pilot:** #22 PWA install (awaits phone check), #251 Telegram, #252 pilot report,
  #253 14-day owner acceptance, #364 clustering over-merges, #439 Sport5/ONE failure recording,
  #527 link results to stories.
- **M11 Census #3:** #423 follow-ups, #426.
- **Unmilestoned:** feed UX (#484, #550, #411), clustering misses (#508), admin load (#436),
  dependency upgrades (#428), and the classification issues in §8.

---

## 12. Running and checking

Setup and commands: [../CLAUDE.md](../CLAUDE.md) §Commands, [../backend/README.md](../backend/README.md),
[../frontend/README.md](../frontend/README.md).

- **Worker on the owner's PC:** `powershell -File scripts\worker.ps1 [-Status|-Stop]` — run
  `-Status` first in any session that depends on fresh ingestion.
- **Preview a branch next to the live stack:** `scripts\preview.ps1 -Worktree <path>` copies the
  corpus into the worktree and starts an isolated API (:8010) and web app (:5180) with
  `DEPLOY_ENV=dev`, no scheduler, no LLM, and provider calls answering 503.
- **Remote development:** `scripts/dev.sh` and `.devcontainer/` (`DEPLOY_ENV=dev`, empty DB);
  CI-exercised, no codespace created yet.
- **Corpus safety:** back up before any write (`backend/scripts/backup_db.py`); run destructive or
  benchmark work only against a copy (`DATABASE_URL=sqlite:///./data/<copy>.db`); never delete
  `backend/data/signal_sports.db`.
- **Demo publish:** `scripts\demo-publish.ps1` (scheduled hourly by `scripts\demo-schedule.ps1`).

---

## 13. Milestone history

| # | Milestone | Closed | Delivered | Contract |
|---|---|---|---|---|
| — | Base44 prototype → backend | 2026-06/07 | FastAPI + SQLite, RSS, Sport5 scraping, rules + LLM classification | — |
| 1 | Signal Intelligence Architecture v2 | 2026-07-08 | Taxonomy, ArticleFacts, event evidence, visibility tiers, Preference V2, Calibration V2, feedback learning | RELEVANCE_CONTRACT and layer docs |
| 2 | User Platform | 2026-07-10 | Accounts, cookie sessions, `/api/me/*`, fail-closed admin, onboarding | USER_PLATFORM |
| 3 | Classification & Feed Reliability | 2026-10-10 | Champion semantics, LLM-echo provenance, golden suite | RSS_QUALITY_GUARDRAILS |
| 4 | Explicit Interests & Onboarding v2 | 2026-07-11 | Follow/Star interests, catalog, calibration dataset v3 | INTERESTS |
| — | Corpus wipe and guard (#106) | 2026-07-12 | Target-database guard after a dev reset destroyed the corpus | `app/db/corpus_protection.py` |
| 5 | Real Story Clustering v1 | 2026-07-14 | Deterministic cross-source clustering | CLUSTERING |
| 6 | Feed De-duplication & Clustering Activation | 2026-07-18 | Story anchors, republish handling, activation with 0 over-merges | CLUSTERING |
| 7 | Automated Ingestion & Telegram Pilot | 2026-07-18 | Dedicated worker, durable lease, notification outbox, Telegram | SCHEDULER, NOTIFICATIONS |
| — | Feed freshness (36h) | 2026-07-18 | One freshness predicate for feed, clusters, push | FEED_FRESHNESS |
| — | Orbit frontend | 2026-07-31 | Consumer UI, superseded by milestone 15 | [archive](archive/frontend-concepts/orbit/README.md) |
| — | Personalized results (#178) | 2026-08-23 | Results page from the same follows | RESULTS |
| — | Repository audit (#186) | 2026-09-05 | Reliability fixes; debt filed as #196–#200 | [audits/2026-09-05.md](audits/2026-09-05.md) |
| 8 | Feed Quality — Recall & Push (N05) | 2026-09-16 | 282-rating ground truth and gate; push precision 41%→100%; LLM cost −45% | qa/N05_* |
| 9 | Census #2 & Classification Truth | 2026-10-10 | Census #2 (804); title-local events; Israeli cups; `club_governance` | qa/CENSUS_2026-10 |
| — | Census calibration (#237) + QA tooling | 2026-10-12 | Live-profile calibration with held-out check | PREFERENCE_MODEL_V2 |
| — | Hosted-stack repository prep (M13 part) | 2026-10-13 → 10-29 | Images, Compose, safety guards, backups, deploy tooling, Postgres groundwork — CI only | DEPLOYMENT |
| — | Auth track | 2026-10-21 | Email verification, Google sign-in, password reset, auto-link | USER_PLATFORM |
| — | Groq interim LLM | 2026-10-25 | Bake-off; production off Ollama onto `gpt-oss-20b` | qa/LLM_BAKEOFF_2026-10-25 |
| 12 | Israeli-basketball recall | 2026-11-01 | Maccabi/Hapoel TLV people (#259), Hapoel for Guy (#257), ONE enabled (#258) | TAXONOMY, PREFERENCE_MODEL_V2 |
| 14 | Implicit state machine fixes | 2026-11-08 | Scheduler takeover, notification claims, calibration clears, results never regress (#444–#450) | SCHEDULER, NOTIFICATIONS, RESULTS |
| — | Public demo (#458) | 2026-11-11 | Read-only Firebase demo of guy's feed, hourly | DEPLOYMENT §17 |
| 15 | New consumer UI (#461–#513) | merged 2026-11-15 (milestone still open) | Signal UI, filters, merged preferences, results redesign | FRONTEND_DESIGN_SYSTEM |
| — | Results providers & detail (#517–#538) | 2026-11-15/16 | ESPN, EuroLeague, Winner, Bamboo; health/fallback; box scores; demo results | RESULTS |
