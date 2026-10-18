# Signal Sports — Current Project State

**Last updated: 2026-10-13** (truth sweep 2026-10-12; milestones 10–12 filed 2026-10-13). This is the cold-start orientation
for any agent or human picking the project up with no conversation history. Present-tense
statements were checked against the code and the owner's local runtime on that date. History
is condensed in §14. Closed-milestone QA reports and delivered task briefs were removed from
`docs/` on 2026-10-12; `git log --diff-filter=D --name-only -- docs/` lists them, and the
issue numbers in §14 lead to their evidence.

---

## 0. Status at a glance

| Area | State (2026-10-12) |
|---|---|
| Milestones | 1–9 **closed**. **13 is the top priority: Off the owner's machine (hosted model, backend, frontend).** Then 10–12: Live Pilot, Census #3 & gate, Israeli-basketball recall (see §11). Outside them: #196 #198–#200 (audit debt), #16 #21 #23 (mobile) |
| Runtime (owner's Windows PC) | Scheduler worker **running** (`scripts\worker.ps1 -Status`). **The API and Vite were not running on 2026-10-12, so the app was unreachable from the phone.** LLM: Ollama `qwen2.5:3b-instruct`. Clustering on, 36h freshness on, results sync on. **Telegram push OFF since 2026-09-13** |
| Live sources | Walla, Israel Hayom, Ynet, **Sport5** (a code-default "pilot", enabled by runtime override). **ONE is disabled by override and has never ingested into this corpus** |
| Corpus | 2,715 RSS articles published 2026-07-10 → today. 340 were published after the milestone-9 worker restart (2026-10-10 14:23 UTC) |
| Feed quality (fresh cohort) | Census #2 (804 articles, owner-rated): shown precision 92–95% after the owner's blind re-review. **Feed+ recall 66%** when rated, before milestone 9: about one wanted story in three was hidden. Push recall 1/8, and 2/8 on the rerun after #229 |
| Regression gate | N05 frozen-corpus gate (282 ratings): Guy 98.3% shown / 18.0% false hide / push 7/7. Deni 91.7% / 0.8% / 1/1 |
| **Real usage** | **8 feedback events ever, all in July. No login session since 2026-09-16. 14 Telegram pushes, the last on 2026-07-24.** The learning loop has never run on real usage |
| Next | §11: milestone 13 first. The repository preparation is done and CI-validated ([DEPLOYMENT.md](DEPLOYMENT.md)); what remains needs the owner: the decisions in [HOSTING_PLAN.md](HOSTING_PLAN.md) §18 (LLM path and key, GitHub plan and budget, topology A or B, backup target and offline key), then the hosted-LLM evaluation (#262), the host (#268) and the cutover (#269). Nothing is chosen, bought or deployed. Then milestone 10, with #241 in parallel |

---

## 1. Product in one paragraph

Signal Sports is a personalized, Hebrew-first sports news intelligence feed. It ingests Hebrew
sports news, works out what each article is about (sport, competition, teams, players, event
type, importance), and shows each user only what is worth *their* attention: `hidden`,
`low_feed`, `feed`, `high_feed` or `push`. The same article can be `push` for one user and
`hidden` for another. Push stories reach the owner's phone through a private Telegram pilot.
The north star is in `CLAUDE.md`: *"What sports news is actually worth this user's attention
right now?"* The product vision is in `docs/PRODUCT_UNDERSTANDING.md`.

## 2. Product principles (current)

- **Personalized relevance, not a generic feed.** Article facts are user-independent;
  decisions are per user. Facts ≠ personalization.
- **Abstention beats guessing.** An unsure classifier says `sport=unknown`, no entity, or `news`.
  A false fact is worse than a missed one, because it reaches the feed as truth.
- **Push is rare and explicit.** Push comes only from an explicit `always_push` override, behind
  a factual severity gate. A boost or importance never produces push.
- **Measure against human ground truth.** Unit tests prove the engine does what it was told.
  Owner ratings (the N05 gate and the censuses) prove whether it was told the right thing. Read
  precision and recall separately, never one accuracy number.
- **The corpus is evidence.** `backend/data/signal_sports.db` is not in git, cannot be
  recreated, and carries the human ratings' article ids. It is never reset, and it never gets a
  blanket rules-only backfill.
- **Hebrew UI, English code.** All user-visible strings are Hebrew/RTL; identifiers and comments
  are English.
- **The LLM is optional.** The `CLASSIFICATION_PROVIDER=disabled` path is first-class.

---

## 3. Architecture

**Processes.** Everything runs on one Windows machine.

```
Phone ──Tailscale Serve (HTTPS)──┐
Desktop browser ─────────────────┤
                                 ▼
             Vite dev server :5173 (React app; proxies /api and /health)
                                 ▼
             API  uvicorn app.main:app :8000      (serves requests; NO scheduler)
                                 │ shared SQLite (WAL) backend/data/signal_sports.db
             Worker  python -m app.worker         (5-min cycles behind a durable lease)
                                 │
             Ollama :11434 (qwen2.5:3b-instruct)   TheSportsDB (results)   Telegram Bot API
```

**One ingestion cycle** (`app/ingestion/orchestration.py::orchestrate_cycle`): acquire the
single-flight lease → for each enabled source, fetch → filter → URL-dedup → classify (rules →
LLM gate → merge guardrails → ArticleFacts → event re-validation) → insert → story anchors →
clustering. The cycle then runs notification planning, then dispatch, then the results sync,
then retention (currently disabled), and releases the lease. Details:
[RSS_INGESTION.md](RSS_INGESTION.md), [SCHEDULER.md](SCHEDULER.md).

**One feed request** (`app/services/feed_service.py`): freshness window (36h, consumer feeds
only) → per-article Preference V2 scoring (visibility tiers → affinity layers → learned
adjustments → overrides) → user-specific cluster collapse (card decision = the maximum over
visible members). Details: [RELEVANCE_CONTRACT.md](RELEVANCE_CONTRACT.md).

| Layer | Where |
|---|---|
| Frontend | React 18 + Vite 6, `frontend/src/` ([FRONTEND_DESIGN_SYSTEM.md](FRONTEND_DESIGN_SYSTEM.md)) |
| API + worker | FastAPI, Python 3.13, `backend/app/` (`main.py`, `worker.py`) |
| Persistence | SQLite via SQLAlchemy 2.0. Additive soft migrations at startup |
| Sources & adapters | `app/ingestion/` (feedparser, httpx + BeautifulSoup, ONE JSON) |
| Classification | `app/ingestion/classifier.py` (rules), `app/classification/` (gate, providers, merge, facts, event evidence) |
| Taxonomy | `app/taxonomy/` (the single source of entity truth) |
| Relevance | `app/services/preference_engine.py` (v2, default), `relevance_engine.py` (visibility tiers; the legacy engine is the rollback path) |
| Clustering | `app/clustering/` (deterministic; no LLM or embeddings) |
| Notifications | `app/notifications/` (planner, outbox, dispatcher, Telegram) |
| Results | `app/results/` (TheSportsDB provider + fake) |
| QA tooling | `app/qa/`, `backend/scripts/` (gate, census, rerun-diff, probes, reviewed correction scripts) |

---

## 4. Sources

| Source | Type | Live state | Notes |
|---|---|---|---|
| `walla_sport` | RSS | on | No URL category, so sport comes from keywords, entities and the LLM |
| `israel_hayom_sport` | RSS + `/sport/` allowlist | on | A general 100-item feed, about 21 of them sport |
| `ynet_sport` | RSS | on | URL hints for basketball, football and tennis |
| `sport5_sport` | html_scrape | **on (runtime override)** | The code default says "pilot, disabled", but it has run every cycle since July |
| `one_sport` | html_scrape (public JSON) | **off (runtime override)** | Zero articles in this corpus. A live probe is needed before re-enabling |
| `eurohoops`, `sportando` | RSS, English | off | Post-MVP, together with translation ([TITLE_TRANSLATION.md](TITLE_TRANSLATION.md)) |

Full contract, URL hints and probe history: [RSS_INGESTION.md](RSS_INGESTION.md). The product is
Hebrew-only. Re-enabling English sources or translation is post-MVP and must not happen as a
side effect.

---

## 5. Backend

**Tables:** `articles`, `profiles` (incl. the `profile_v2` JSON), `users`, `auth_sessions`,
`feedback_events`, `calibration_responses`, `calibration_headlines` (legacy, unused),
`sources`, `source_overrides`, `ingestion_runs` (incl. the `metrics` JSON), `scheduler_cycles`,
`scheduler_lease`, `worker_status`, `story_clusters`, `cluster_edges`, `notification_events`,
`notification_story_members`, `notification_watermarks`, `game_results`,
`results_sync_state`. Startup creates missing tables, applies additive column migrations
(fail-loud), seeds empty tables, and creates credential-less demo `users` rows.

**API surface** (the exact inventory is OpenAPI `/docs`; an authz test derives it from the routes):

| Surface | Access |
|---|---|
| `/health` | public |
| `/api/auth/*` (signup, login, logout, session, verification peek/confirm/resend, Google start/callback, Google-signup link peek/start, password forgot/reset) | public; mutating routes CSRF-checked, the Google callback bound to its state cookie |
| `/api/me/*` (profile, feed, results, feedback, learning, never_show, interests, calibration, onboarding, password, account, account deletion through Google, connect/disconnect Google) | the session user's own data |
| `/api/taxonomy/catalog`, `/api/calibration/items`, `/api/calibration/preview`, `/api/articles[/{id}]`, `/api/feed-engine` | any session |
| `/api/feed/{user_id}`, `/api/debug/*`, `/api/profiles/*`, `/api/learning/{user_id}[/reset]`, `/api/feedback[/{user_id}]`, `/api/calibration/apply`, `/api/calibration/responses/{user_id}`, `/api/results/{user_id}`, `/api/results/sync[/state]` | admin (view-as / QA) |
| `/api/ingest/*`, `/api/scheduler/*`, `/api/notifications/*`, `/api/classify/*`, `/api/translations/*`, `/api/dev/*` | admin, router-level fail-closed. `/api/dev/*` also needs `ALLOW_DEV_RESET`, and the corpus guards apply on top |

**Runtime flags** (defaults in `backend/.env.example`; the production values are in the
untracked `backend/.env`):

| Flag | `.env.example` | Production `.env` |
|---|---|---|
| `CLASSIFICATION_PROVIDER` / `_MODEL` / `_TIMEOUT_SECONDS` | disabled / – / 15 | `ollama` / `qwen2.5:3b-instruct` / 30 |
| `CLASSIFICATION_LLM_GATING` | enabled | enabled |
| `CLUSTERING_ENABLED` | true | true |
| `SCHEDULER_ENABLED` (+ `SCHEDULER_INTERVAL_SECONDS`) | false (300) | true (300) |
| `FEED_FRESHNESS_ENABLED` / `FEED_MAX_AGE_HOURS` | false / 36 | true / 36 |
| `TELEGRAM_NOTIFICATIONS_ENABLED` | false | **false since 2026-09-13** (was true from 2026-07-18) |
| `RESULTS_ENABLED` / `RESULTS_SYNC_ENABLED` | true / false | true / true |
| `RETENTION_CLEANUP_ENABLED` | false | false (keep off until `protect_rated_articles.py --apply` has run on the corpus, #255; see §10) |
| `TRANSLATION_PROVIDER` | disabled | disabled |
| `ALLOW_DEV_RESET` / `ALLOW_CORPUS_DB_RESET` / `ALLOW_INSECURE_AUTH_BYPASS` | false | false |
| `PREFERENCE_ENGINE` | (unset = v2) | unset; `legacy` is the rollback |
| `DEPLOY_ENV` (#265) | unset = `local`: no extra checks | unset. `hosted` refuses the `ALLOW_*` flags and the fake classifier; `dev` refuses Telegram and any production DB path |
| `AUTH_SIGNUP_ENABLED` (#265) | true | unset (true). A host sets false |
| `AUTH_SIGNUP_ALLOWED_EMAILS` | empty | unset. Closed signup still admits these addresses (pending until verified) |
| `GOOGLE_OAUTH_CLIENT_ID` / `_CLIENT_SECRET` / `_REDIRECT_URI` | unset = Google sign-in off | unset |
| `MAIL_BACKEND` (+ `SMTP_*`, `MAIL_FROM`, `APP_PUBLIC_URL`) | unset = no mailer (signup 503); `console` = explicit dev opt-in that logs the link | unset. A host needs `smtp` |

Authentication: email/password (Argon2), HttpOnly cookie sessions, origin/fetch-metadata CSRF,
and admin role gating ([USER_PLATFORM.md](USER_PLATFORM.md)). A password signup is only a
pending registration until the emailed link is confirmed with the password; accounts created
before that (and the bootstrap admin) keep `email_verified_at` NULL. "Continue with Google"
signs in or registers Gmail and Workspace addresses (other addresses register through an
emailed link plus a second Google sign-in), and links one to an existing account (regular
or admin) holding the same address; any account can also connect Google explicitly from
the Account page with its password. A Google-only account deletes
itself through a Google confirmation and a separate final DELETE. CSRF origins come from
`CSRF_ALLOWED_ORIGINS`, while the CORS list is hard-coded in `main.py`. That split is #196, and
it matters before any split deployment.

---

## 6. Frontend

**Orbit** (shipped 2026-07-31) has one story at the centre with its sources in orbit and a
ranked queue behind it. The design contract is [FRONTEND_DESIGN_SYSTEM.md](FRONTEND_DESIGN_SYSTEM.md),
and shipped-state screenshots are in `docs/frontend-concepts/orbit/`.

| Route | Page | Area |
|---|---|---|
| `/login`, `/signup`, `/verify-email`, `/forgot-password`, `/reset-password` | auth (emailed links land on `/verify-email` and `/reset-password`) | public |
| `/welcome` | onboarding (interests → calibration → feed) | session |
| `/` | Feed (Orbit) | product |
| `/preferences`, `/interests`, `/calibration`, `/results`, `/account` | product pages | product |
| `/sources`, `/debug`, `/llm-qa` | ops console (ingestion, scheduler, notifications, debug traces, LLM QA) | admin only |

**Data modes** (`VITE_DATA_MODE`): `local` is the default and needs no backend. It renders mock
data through the **frozen** legacy JS engine (`src/engine/relevanceEngine.js`), which gets no new
intelligence. `backend` is the real product: same-origin `/api` via the Vite proxy, and the
server is authoritative for every decision. The Debug page shows every article, including
hidden ones, with its facts trace, contribution trace, cluster evidence and engine badge.

---

## 7. Profiles & relevance

**Decision levels:** `hidden` (no followed scope matched, or excluded; Debug only) ·
`low_feed` (matched, minor) · `feed` · `high_feed` · `push` (explicit override only).
Semantics and invariants: [RELEVANCE_CONTRACT.md](RELEVANCE_CONTRACT.md).

**Engine: Preference V2** ([PREFERENCE_MODEL_V2.md](PREFERENCE_MODEL_V2.md)) scores over
**ProfileV2**. A profile holds scope affinities (sport, competition, team, player, coach), each
with a level from −2 to +2 and a source (explicit, calibration or learned). It also holds
event affinities (global or scoped deltas) and overrides (`always_push`, `never_show`, mute).
Visibility comes from four-tier competition matching
([RELEVANCE_VISIBILITY_CONTRACT.md](RELEVANCE_VISIBILITY_CONTRACT.md)): explicit evidence →
legacy league → participant-set inference → team-membership reach, the last capped at `feed`.
Following `comp:ibl` also follows its cups (#230). Precedence for the same target is explicit >
learned > calibration, and a scoped entry beats a global one.

**Live profiles** are DB rows, so a code change to the seeds does not change them. The owner
applies a live change with a reviewed `backend/scripts/apply_*.py` script, after a backup.

- **`guy`** (the owner): Maccabi TLV basketball +2. EuroLeague, EuroCup, NBA and IBL +1. ACB,
  BSL, Greek, LBA and LNB −1. Football and tennis −1 at sport level. Deni Avdija and Oded Kattash
  +1. 63 explicit event affinities. 12 `always_push` overrides: Maccabi signing, major signing,
  negotiation, injury, title win and `club_governance`; NBA star trade and title win; EuroLeague
  and EuroCup title win; Deni major trade and injury. 3 `never_show` overrides (Maccabi
  pre-match, schedule, generic preview). Recent live mutations: #229 (governance push, which
  fires on a concrete step only) and #237 (`team:maccabi_tlv_bb × candidate −1`,
  `comp:euroleague × news +1`, fitted on census #2 and confirmed on its held-out half).
- **`casual_deni_fan`** (demo): Deni Avdija +2 and nothing else. Pushes on a Deni major trade,
  injury or `relocation`. Relocation is an owner-authorised, entity-scoped rule (#191): the same
  relocation article is `feed` for Guy. This profile must not drift unintentionally; the gate
  enforces that.

**Push discipline.** Push needs an explicit `always_push` match. For signing, major signing,
negotiation, injury and `club_governance`, it also needs factual severity
(`attention.development`: a current agreement or completion, an imminent renewal, a current
injury, or a concrete governance step) and the followed scope as a title subject (#192, #229).
Notifications are planned per **story** (cluster lineage), at most once
([NOTIFICATIONS.md](NOTIFICATIONS.md)).

**How profiles are populated** (the CLAUDE.md "three ways"): explicit interest selection over
the taxonomy catalog ([INTERESTS.md](INTERESTS.md)), interest-aware calibration
([CALIBRATION_V2.md](CALIBRATION_V2.md), dataset v3, 73 items), and feedback learning
([FEEDBACK_LEARNING.md](FEEDBACK_LEARNING.md)). Learning activates at ≥3 net consistent events,
caps at ±1 with a 90-day half-life, never creates an exclude, and is derived at read time. Free-text
preference input was deliberately not built. **Census calibration** (#237) is a fourth, offline
path the owner used: it tunes the live profile from rated articles with a held-out check.

**Legacy topic model.** The pre-v2 profiles (`topics`, `entity_event_rules`, scope guards) still
ship for the rollback engine and the frozen JS engine. `docs/fixtures/profile_parity.json` pins
them, and drift tests on both sides enforce it.

---

## 8. Classification

Pipeline order and contracts: [RELEVANCE_CONTRACT.md](RELEVANCE_CONTRACT.md) (map),
[ARTICLE_FACTS.md](ARTICLE_FACTS.md) (facts stage), [LLM_CLASSIFICATION.md](LLM_CLASSIFICATION.md)
(gate, merge, metrics), and [RSS_QUALITY_GUARDRAILS.md](RSS_QUALITY_GUARDRAILS.md) (the
deterministic rule changelog, §1–§18).

- **Rules first, always.** The title is primary, and the subtitle only fills gaps. *Title-local*
  event types (`title_win`, `grand_slam_winner`, `major_trade`, `schedule`, …) never come from
  the subtitle alone (#223, #224).
- **The LLM is gated.** It is force-called on `sport_unknown`, `ambiguous_club` or low
  confidence, and skipped when the rules are already strong or the article is measured-sufficient
  generic `news` (#217). The call rate is about 28% of eligible articles. Proposals pass the merge
  guardrails and **semantic event evidence** (Guardrail 4b), which rejects most of what it sees,
  and is mostly right to (#218).
- **Event types:** the specific types need positive evidence; `news` is abstention, with a
  recorded reason. Newer types: `relocation` (#191), `club_governance` (#229).
- **Taxonomy** ([TAXONOMY.md](TAXONOMY.md)): 88 entities (79 teams, 3 players, 1 coach,
  5 executives) and 21 competitions, 15 of them selectable. Bare club-family names (`מכבי`,
  `הפועל`) never resolve. Coaches and executives imply their team.

**Structural limits (measured, not fixed):**
- **Person-level coverage.** The registry holds 3 players, all NBA. Israeli-league players and
  coaches are invisible, so a story about them has no entity and often no sport.
- **Cross-sport club deadlock** (#194). `מכבי תל אביב`, `הפועל ת"א` and others without sport
  evidence stay `sport=unknown`. The bucket mixes sports, so defaulting a sport would fabricate
  facts.
- **`news` with no competition.** In census #2, 71 of 76 false hides had no
  `primary_competition` and 34 had no entity. Hapoel TLV basketball narrative stories (13 false
  hides) are a relevance question, not a classification one.

---

## 9. Quality measurement

| Instrument | What it is | How |
|---|---|---|
| **N05 gate** (the only regression gate) | 282 owner ratings on the frozen July corpus, with directional checks: shown precision, false hide, push precision and volume, Deni no-drift | `cd backend; .venv/Scripts/python.exe scripts/feed_ground_truth.py gate`. Local only, since it needs the corpus. The pure rules run in CI. [RELEVANCE_CONTRACT.md](RELEVANCE_CONTRACT.md) §Quality gate, [qa/N05_FEED_GROUND_TRUTH.md](qa/N05_FEED_GROUND_TRUTH.md) |
| **Census #2** | 804 fresh articles (published since 2026-08-01), every one owner-rated, plus a blind re-review of 58 large gaps | [qa/CENSUS_2026-10.md](qa/CENSUS_2026-10.md), `docs/qa/census2_*.json` |
| Rating tool | `scripts/rate_census.py build / serve / review / merge-review`: a local single-keypress page, blind, resumable | usage in the script docstring |
| Rerun diff | `scripts/corpus_rerun_diff.py snapshot / compare`: an in-memory, rules-only rerun of the whole corpus, scored against census ratings; no DB writes | before/after any classification or taxonomy change |
| Census #3 | planned (#241): rate the cohort ingested after milestone 9 | 289 articles since 2026-10-11 (target about 300) |

**Lessons that bind:**
- Read recall and shown precision separately. `false_hide` as a share of the corpus is diluted
  by the hidden majority.
- Owner ratings repeat only about half the time on borderline rows, a noise band of about one
  notch. Re-rate big disagreements before acting, and never calibrate on groups with n<5 or
  without a held-out half.
- Score a taxonomy change against the census, not just the facts: a new competition the
  profile does not follow can *regress* decisions.
- **Never run a blanket rules-only backfill**, because it destroys LLM-assisted facts. Stored
  rows change only through targeted, reviewed, backed-up correction scripts. Under the 36h
  window the live feed only shows fresh articles, so unbackfilled old rows matter for
  measurement, not for the product.
- `pytest … | tail` hides failures. Check the exit code.

---

## 10. Known limitations & risks

**Operational**
- **The stack is not always on.** Nothing starts the API, Vite or the worker at boot, or restarts
  them after a crash. On 2026-10-12 the worker was running but the API and Vite were not, so the
  app was unreachable from the phone. The `scheduler_cycles` history shows the worker absent
  07-24→07-31, 07-31→09-15, 09-20→10-08 and 10-08→10-10. Part of that was deliberate (a frozen
  corpus for measurement); the 09-20 gap went unnoticed for weeks. A stopped worker means a stale
  feed, and nothing alerts anyone. Milestone 13 moves the stack to a host (#268, #269), and #249
  adds a freshness signal.
- **Telegram is off** (since 2026-09-13), so push stories reach nobody.
- **ONE is off**, and **Sport5 runs as an untracked "pilot"**. Neither state is recorded anywhere
  except the `source_overrides` table.
- **Retention cleanup stays disabled.** Since #255 it never deletes an article listed in
  `protected_articles` (N05 and census rated or sampled ids). On the live corpus that table stays
  empty until the owner runs `scripts/protect_rated_articles.py --apply` after a backup. Until
  then, enabling retention at 30 days would delete all 256 N05-rated articles and, by about
  mid-November, all of census #2. On a 2026-10-18 corpus copy the script protected 1,060 ids, and
  a dry run then reported `protected_rated` 773 with no rated id deletable. See
  [FEED_FRESHNESS.md](FEED_FRESHNESS.md) §8.
- Single machine and single SQLite file. On the PC, backups are still manual (`scripts/backup_db.py`,
  WAL-safe and verified). The hosted nightly off-host backup exists in the repository
  ([DEPLOYMENT.md](DEPLOYMENT.md) §7) but runs nowhere until a host exists.

**Product**
- **No real usage yet** (§0). Feedback learning, the third personalization path, has no real
  data. Feedback saves can also fail silently (#197).
- Recall: about one wanted story in three was hidden at census #2 (§8). Milestone 9 raised it on
  reruns (cups 93→100/140, schedule 103→107/140), and census #3 will measure it on real
  ingestion.
- Push recall is low (2/8 on the rerun), and the misses are mostly institutional Maccabi news.
  #242 (venue move) is waiting for more examples.

**Platform / debt** (audit [audits/2026-09-05.md](audits/2026-09-05.md)): #196 the CSRF vs CORS
origin lists, #197 silent feedback failures and results-sync lease, #198 no migration history (the dependency lock landed: `backend/requirements.lock`), #199 bundle weight and unfiltered feed query, #200 signup/login abuse
protection (a **gate before widening access**, not needed while single-user behind Tailscale).

**Mobile** (#16 epic): Tailscale access works when the stack is up. #19 feed touch targets, #20
navigation and safe-area (item 1 done) and #22 PWA-lite install are in milestone 10. #21 (ops
pages) and #23 (a local startup script, optional now that the stack moves to a host) are not.

---

## 11. Next steps — milestone 13 first, then 10–12 (filed 2026-10-13)

**Top priority (owner, 2026-10-13): milestone 13, "Off the owner's machine — hosted model,
backend and frontend".**

**The requirement, clarified on 2026-10-13:** stop depending on the owner's weak PC both for the
running system *and* for development. The PC remains only an access station: editor UI, browser
and SSH. This is urgent **independent of the pilot or product readiness**.

**The plan is a decision document, [HOSTING_PLAN.md](HOSTING_PLAN.md) v3.1, under the owner's
review. No host has been chosen, and its recommendation is a proposal, not an approved
decision.** The preparation shared by every option is implemented and described in
[DEPLOYMENT.md](DEPLOYMENT.md): it is validated in CI only, and **nothing runs on a host yet**.
The plan compares:

- **B (proposed as the reversible start):** a small x86 VM running the live system with Docker
  Compose (Hetzner CX23, €5.99 a month excl. tax), plus GitHub Codespaces for development, which
  is free up to 60 *running* hours a month on GitHub Free
- **A:** one larger VM (CX33, €8.99 a month excl. tax) for both. It wins above ~79 running hours a
  month, or when long unattended agent runs matter more than isolation. B becomes A by a rescale
  that keeps the disk
- **C:** GCP e2-micro (≈ $3.65 a month for its IPv4, not $0, and conditional on a load test) or
  Oracle ($0, reclamation risk)

It also proposes:
- Compose for prod: k3s would fit, but it stays off the critical path
- the `ts.net` address at the cutover, with `guynavon.net` attached afterwards (no DNS change now)
- deploys from the PC with a separate identity
- a write-only backup key and a sanitized dev snapshot
- changes to #261–#270, not yet applied to the issues

**Milestone 13 status (2026-10-13).** "Done" means implemented and tested in the repository
(mocked or CI-rehearsed); nothing has run on a host, against a cloud account or with a real key.

| Item | In the repository | Still needs the owner |
|---|---|---|
| #265 hosted-mode safety | **done** (PR #275): `AUTH_SIGNUP_ENABLED`, `DEPLOY_ENV` checks, dev guards | — |
| dependency lock (#198, lock half) | **done** (PR #276): hash-pinned `requirements.lock`, CI installs from it | — (#198's migrations half stays open) |
| #261 OpenAI-compatible provider | **done** (PR #277), mocked HTTP only | a key, for #262 |
| #262 evaluate + switch | bounded tooling (`llm_failure_probe.py --max-calls --dry-run --ids-file`) | the LLM path and key; stages 0–1; the switch; stopping Ollama |
| #263 images + Compose | **done** (PR #278); CI builds and smoke-tests every change | the first publication (package visibility); amd64 only |
| remote development | devcontainer + `scripts/dev.sh` (PR #279), CI-exercised | the first codespace run (checklist in `.devcontainer/README.md`) |
| monitoring + source probe | PR #281: cycle/sources/fresh/backup pings; fetch-only probe | a healthchecks account and checks; a probe run from the host |
| #266 backups | PR #280: copy → age → off-host → ping, restore/undo, rehearsed end to end in CI | the B2 account, buckets, Object Lock, lifecycle, keys; the offline key; timers on the host; a drill there |
| #270 snapshots | sanitized dev snapshot with a separate key and target (PR #280) | the dev key; moving a snapshot into dev; checking the gate on it |
| #268 provision | deploy/rollback/auto-rollback tooling, host templates, checklist (PR #283), rehearsed in CI | the VM, accounts, Tailscale, identities |
| #269 cutover | runbook, DEPLOYMENT.md §12 | owner-run |
| #267 decisions, #264 k8s | — | the owner's decisions; #264 proposed for deferral |
| `calib.py` (#237 tool) | integrated as `scripts/census_calibration_fit.py` (PR #282) | — |

The issue texts predate the plan; its §17 proposes their amendments (not applied).

Recommended order after milestone 13: milestone 10, with #241 from milestone 11 in parallel (its
cohort is ready and it costs about half an hour of rating), then milestone 12, measured against
milestone 11's gate.

1. **Milestone 10, Live Pilot: Signal runs itself and gets used daily.** It runs on the host from
   milestone 13. #248, the local autostart, was closed as superseded, and #23 left the milestone.
   - #249 freshness signal in the feed
   - #250 record real usage
   - #251 re-enable Telegram after a read-only preflight
   - #252 pilot report
   - #197 honest feedback saves
   - phone UX: #19, #20, #22
   - **#253 owner-run 14-day acceptance**, which no PR may close; its window starts after #269
2. **Milestone 11, Census #3 & a fresh regression gate:**
   - #241 census #3
   - #254 census-based gate (feed+ recall, push recall, noise band)
   - #255 protect rated rows from retention (code landed; owner runs the one-off `--apply`)
   - #242 venue-move vocabulary, if census #3 brings enough examples
3. **Milestone 12, Israeli-basketball recall — people, not only clubs:**
   - #256 measure which people matter (no registry change)
   - #259 register the approved batch, blocked by #256
   - #257 product decision on non-Maccabi club narrative
   - #258 ONE probe and decision

Deliberately not in these milestones: platform hardening (#196, #198–#200), which matters
before wider access or a split deployment, and #21 (mobile ops pages).

---

## 12. How to run locally

```powershell
# Backend API (from backend/)
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000   # /docs = OpenAPI

# Scheduler worker + Ollama (from repo root). Detached; logs to backend\data\worker.log.err
powershell -File scripts\worker.ps1          # start (also starts Ollama if it is down)
powershell -File scripts\worker.ps1 -Status  # run this FIRST in any session that needs fresh ingestion
powershell -File scripts\worker.ps1 -Stop

# Frontend (from frontend/). Backend mode needs frontend/.env.local with VITE_DATA_MODE=backend
npm install; npm run dev                      # http://localhost:5173 (fixed port, strictPort)
```

**Tests and checks** (the same as CI, `.github/workflows/checks.yml`):

```powershell
cd backend;  .venv\Scripts\python.exe -m pytest tests -q            # hermetic: temp DB, LLM off, Telegram creds cleared
cd frontend; npm run lint; npm run typecheck; npm run test; npm run build
cd backend;  .venv\Scripts\python.exe scripts/feed_ground_truth.py gate   # local only: before any relevance/classification change
```

Use the collectors for test counts (`pytest --collect-only -q`); counts copied into docs go stale.

**Remote development (Linux, a codespace or a dev user):** `scripts/dev.sh api|web|test|check|gate`
and the devcontainer in [.devcontainer/README.md](../.devcontainer/README.md). It always runs
`DEPLOY_ENV=dev` on its own empty DB. **Prepared and CI-exercised; no codespace has been created yet.**

**Corpus safety.** Back up before any write: `.venv\Scripts\python.exe scripts/backup_db.py`.
That writes `data/backups/backup_<UTC>.db` through the SQLite backup API, which is WAL-safe, and verifies integrity, foreign keys and counts (`--manifest` records them; `scripts/verify_db.py` re-checks a file). Run
destructive or benchmark work only against a copy (`DATABASE_URL=sqlite:///./data/<copy>.db`).
The benchmark route hard-refuses the real corpus. Never delete `backend/data/signal_sports.db`.

**Container stack** (the future host; CI-validated, not deployed): `deploy/compose.yaml` with the
`backend` and `web` images, and `deploy/smoke-test.sh` for an isolated empty-DB check. See
[DEPLOYMENT.md](DEPLOYMENT.md).

**Manual ingestion** (admin session, or a local bypass): `POST /api/ingest/run[?source_id=X]`,
`POST /api/ingest/scheduler/run-now`. Source health: `GET /api/ingest/source-health`. Mobile:
[MOBILE_REMOTE_ACCESS.md](MOBILE_REMOTE_ACCESS.md).

---

## 13. Handoff prompt for a new agent

> You are working on Signal Sports. Read `CLAUDE.md` (product intent; its "current priorities"
> describe the original prototype phase), then this file fully, then
> `docs/RELEVANCE_CONTRACT.md`, then the contract doc for the layer you will touch (the doc map
> below). Read your issue completely: its non-goals are binding. Before writing code, check
> that the state you rely on is real (run `scripts\worker.ps1 -Status`, read the code, query the
> DB read-only) rather than trusting a doc. Preserve the invariants: the demo profiles do not
> drift unintentionally, push comes only from explicit overrides, the corpus is never reset or
> blanket-backfilled, the JS engine stays frozen, and the UI is Hebrew/RTL with English code.
> Run the full backend suite and the frontend checks if you touch the frontend, plus the N05
> gate for classification or relevance changes. Measure decision changes against the census
> (`corpus_rerun_diff.py`). Update the docs you made stale (`signal-doc-truth` skill). One issue,
> one branch, one PR. Separate automated, manual-desktop and owner-device validation, and never
> claim validation that was not performed.

**Working style that has held:** answer in Hebrew when addressed in Hebrew. Be direct. Keep scope
to what was asked. Merge your own PR once CI is green on the exact head SHA and the work
implements a direction the owner already approved; new product decisions go to the owner first.
Project skills live in `.claude/skills/`: the `signal-*` workflows (classification, relevance and
taxonomy changes, source onboarding, pipeline review, feed audit, real-data QA, quality eval, doc
truth, PR open/finish/merge, handoff) plus adapted upstream skills (debugging, TDD, verification,
review intake, security diff review, UI and React review, browser checks, Python testing/async).
`.claude/skills/README.md` says which skill owns which gate.

**Doc map — which doc is authoritative for what:**

| Topic | Doc |
|---|---|
| Pipeline map, decision semantics, invariants, quality gate | [RELEVANCE_CONTRACT.md](RELEVANCE_CONTRACT.md) |
| Facts stage, evidence, trace | [ARTICLE_FACTS.md](ARTICLE_FACTS.md) |
| Competition matching, reach, feed ceiling | [RELEVANCE_VISIBILITY_CONTRACT.md](RELEVANCE_VISIBILITY_CONTRACT.md) |
| ProfileV2 and the scorer | [PREFERENCE_MODEL_V2.md](PREFERENCE_MODEL_V2.md) |
| Interests / calibration / learning | [INTERESTS.md](INTERESTS.md), [CALIBRATION_V2.md](CALIBRATION_V2.md), [FEEDBACK_LEARNING.md](FEEDBACK_LEARNING.md) |
| Taxonomy registry and coverage audit | [TAXONOMY.md](TAXONOMY.md) |
| LLM gate, merge, metrics | [LLM_CLASSIFICATION.md](LLM_CLASSIFICATION.md) |
| Deterministic rules changelog, source filters | [RSS_QUALITY_GUARDRAILS.md](RSS_QUALITY_GUARDRAILS.md) |
| Sources, adapters, ingestion pass | [RSS_INGESTION.md](RSS_INGESTION.md) |
| Clustering | [CLUSTERING.md](CLUSTERING.md) |
| Freshness window / scheduler / notifications / results | [FEED_FRESHNESS.md](FEED_FRESHNESS.md), [SCHEDULER.md](SCHEDULER.md), [NOTIFICATIONS.md](NOTIFICATIONS.md), [RESULTS.md](RESULTS.md) |
| Accounts, auth, authorization | [USER_PLATFORM.md](USER_PLATFORM.md) |
| Frontend design system | [FRONTEND_DESIGN_SYSTEM.md](FRONTEND_DESIGN_SYSTEM.md) |
| Phone access (Tailscale) | [MOBILE_REMOTE_ACCESS.md](MOBILE_REMOTE_ACCESS.md) |
| Ground truth and census reports | [qa/N05_FEED_GROUND_TRUTH.md](qa/N05_FEED_GROUND_TRUTH.md), [qa/N05_FEED_QUALITY_IMPLEMENTATION.md](qa/N05_FEED_QUALITY_IMPLEMENTATION.md), [qa/CENSUS_2026-10.md](qa/CENSUS_2026-10.md) |
| Product vision / translation (post-MVP) / audit snapshot | [PRODUCT_UNDERSTANDING.md](PRODUCT_UNDERSTANDING.md), [TITLE_TRANSLATION.md](TITLE_TRANSLATION.md), [audits/2026-09-05.md](audits/2026-09-05.md) |

---

## 14. Milestone history

| # | Milestone | Closed | What it delivered | Contract |
|---|---|---|---|---|
| — | Base44 prototype → backend | 2026-06/07 | FastAPI + SQLite, RSS (Walla, Israel Hayom), Sport5 scraping, deterministic + LLM classification, gating, and the frontend redesigns (Court Vision, The Edition) | this file |
| 1 | Signal Intelligence Architecture v2 | 2026-07-08 | Taxonomy + resolver, ArticleFacts, event semantic evidence, visibility tiers, LLM run metrics, Preference V2 (flipped after a shadow check), Calibration V2, feedback learning | RELEVANCE_CONTRACT and the layer docs |
| 2 | User Platform | 2026-07-10 | Accounts, cookie sessions, `/api/me/*`, fail-closed admin, onboarding, account lifecycle | USER_PLATFORM |
| 3 | Classification & Feed Reliability | core 2026-07-10 (closed 2026-10-10) | Champion-vocabulary assertion semantics, LLM-echo provenance, coverage gaps; the golden-17 suite (`tests/test_golden_cases.py`) | RSS_QUALITY_GUARDRAILS |
| 4 | Explicit Interests & Onboarding v2 | 2026-07-11 | Follow/Star interest selection, catalog, calibration dataset v3, decision provenance | INTERESTS |
| — | Corpus wipe and guard (#106) | 2026-07-12 | The real corpus was destroyed by a dev reset. A target-database guard was added, and the corpus was re-ingested from scratch | `app/db/corpus_protection.py` |
| 5 | Real Story Clustering v1 | 2026-07-14 | Deterministic cross-source clustering contract, matcher, persistence, backfill, cluster cards | CLUSTERING |
| 6 | Feed De-duplication & Clustering Activation | 2026-07-18 | Validated story anchors, intra-source republish, claim compatibility, activation with 0 over-merges | CLUSTERING |
| 7 | Automated Live Ingestion & Telegram Push Pilot | 2026-07-18 | Dedicated worker, durable lease, notification identity, outbox, Telegram delivery, a 44.8h soak | SCHEDULER, NOTIFICATIONS |
| — | Feed freshness (36h window) | 2026-07-18 | One shared freshness predicate for feed, cluster canonical choice and push | FEED_FRESHNESS |
| — | Orbit frontend | 2026-07-31 | The current consumer UI | FRONTEND_DESIGN_SYSTEM |
| — | Personalized results (#178) | 2026-08-23 | Results page from the same follows; TheSportsDB sync | RESULTS |
| — | Repository audit (#186) | 2026-09-05 | Reliability fixes F01–F13 and R01–R07; open debt filed as #196–#200 | audits/2026-09-05 |
| 8 | Feed Quality — Recall & Push (N05) | 2026-09-16 | The 282-rating ground truth and gate; former-affiliation fix; Israeli clubs; push 41%→100%; LLM cost −45% (#217); live scoreline (#218); census tool and census #1 | qa/N05_*, LLM_CLASSIFICATION |
| 9 | Census #2 & Classification Truth | 2026-10-10 | Census #2 (804); title-local trade and schedule; Israeli cups; executives; `club_governance` | qa/CENSUS_2026-10, RSS_QUALITY_GUARDRAILS §13–§17 |
| — | First census calibration (#237) + QA tooling | 2026-10-12 | Live-profile calibration with a held-out check; `worker.ps1`, `corpus_rerun_diff.py`, census review/merge-review | PREFERENCE_MODEL_V2 |
