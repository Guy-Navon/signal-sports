# Signal Sports — Guide for AI Sessions

Signal Sports is a personalized, Hebrew-first sports news intelligence feed. It ingests
Israeli sports news, works out what each article is about, and shows each user only what is
worth *their* attention. North star:

> "What sports news is actually worth this user's attention right now?" — not "what sports
> news exists?"

A beautiful generic feed is a failure; a rough feed that filters correctly is closer to success.

**Where the truth lives.** This file is a map, not a status report.
- Current behavior, runtime state and history: [docs/CURRENT_PROJECT_STATE.md](docs/CURRENT_PROJECT_STATE.md)
- Product vision: [docs/PRODUCT_UNDERSTANDING.md](docs/PRODUCT_UNDERSTANDING.md)
- Delivery workflow (branch + PR per feature): [AGENTS.md](AGENTS.md)
- Latest repository audit findings: [AUDIT_REPORT.md](AUDIT_REPORT.md) (2026-11-17); older: [docs/audits/2026-09-05.md](docs/audits/2026-09-05.md)
- When docs and code disagree, the code wins; fix the doc (skill `signal-doc-truth`).

## Product principles (non-negotiable)

- **Facts are user-independent; decisions are per user.** Keep three concerns separate:
  article classification (what is it about) → preference matching (does this user care) →
  final decision. The same article can be `push` for one user and `hidden` for another.
- **Decisions:** `hidden` (debug/ops only) · `low_feed` · `feed` · `high_feed` · `push`.
- **Push is rare and explicit.** It comes only from an explicit `always_push` override behind a
  factual severity gate; a boost or importance score never produces push. Owner rules in force:
  a title win is never a push (`high_feed` at most); injuries are not a push; live in-game score
  updates never appear in the feed for any profile.
- **Abstention beats guessing.** An unsure classifier says `sport=unknown`, no entity, or event
  `news`. A false fact is worse than a missed one.
- **Profiles, not hardcoding.** Demo users (`guy` — basketball power user; `deni` — casual
  Deni Avdija fan) exist only as seed preference profiles; never special-case them in engines.
- **The LLM is optional.** `CLASSIFICATION_PROVIDER=disabled` is a first-class path.
- **Measure against owner ratings** (census gate + N05), reading precision and recall
  separately. Unit tests prove the engine does what it was told, not that it was told the right thing.
- **Hebrew UI, English code.** All user-visible strings are Hebrew/RTL; identifiers and comments English.
- Link to original articles; never copy full article content.

## Data safety (hard rules)

- `backend/data/signal_sports.db` is the irreplaceable real corpus (not in git; carries the
  ids behind the human ratings). Never reset it, never delete from it casually, never run a
  blanket rules-only backfill. Corrections go through id-listed, dry-run-default scripts.
- Never enable retention (`RETENTION_CLEANUP_ENABLED`) on the real corpus — it can delete rated rows.
- Run experiments on a copy (`DATABASE_URL=sqlite:///./data/<copy>.db`). `/api/dev/*` routes are
  double-gated (`ALLOW_DEV_RESET` + admin) and refuse the corpus unless `ALLOW_CORPUS_DB_RESET=true`.
- Never commit `.env*` (except the tracked `*.env.example` templates), databases, logs,
  demo snapshots or builds.

## Architecture

```
Phone/desktop ── Vite dev server :5173 (React; proxies /api, /health)
                       ▼
     API   uvicorn app.main:app :8000   (requests only — NO scheduler)
                       │  shared SQLite (WAL)  backend/data/signal_sports.db
     Worker python -m app.worker        (5-min cycles behind a durable DB lease)
                       │
     LLM provider (optional) · results providers · Telegram (off)
```

- **Ingestion cycle** (`app/ingestion/orchestration.py::orchestrate_cycle`): lease → per source
  fetch → filter → URL dedup → classify (rules → LLM gate → merge guardrails → ArticleFacts →
  event re-validation) → insert → story anchors → clustering → notification plan/dispatch →
  results sync → retention (off) → release lease. Manual runs from the API use the same path.
- **Feed request** (`app/services/feed_service.py`): freshness window (36h, consumer feeds) →
  Preference V2 scoring (visibility tiers → affinity layers → learned adjustments → overrides) →
  per-user cluster collapse (card decision = max over visible members).
- **Public demo** (signal-sports-demo.web.app): `backend/scripts/export_demo_snapshot.py` exports
  guy's feed read-only to static JSON; `scripts/demo-publish.ps1` builds `frontend` `build:demo`
  and deploys to Firebase Hosting (hourly Windows task). The demo bundle must stay read-only and
  scores-only — CI enforces it with `npm run check:demo-bundle`.
- **Runtime today** is the owner's Windows PC (`DEPLOY_ENV=local`). Hosted deployment (Docker
  Compose, `deploy/`) is prepared and CI-rehearsed; see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Stack

| Layer | Tech / location |
|---|---|
| Backend | Python 3.13, FastAPI (pinned `<0.137`, see `backend/requirements.txt`), SQLAlchemy 2 (sync), SQLite only; additive soft migrations at startup. Cookie sessions (argon2), CSRF middleware, Google sign-in |
| Frontend | React 18, Vite 6, React Router 6, TanStack Query 5, Tailwind 3, Radix primitives, framer-motion; JS with `jsconfig` type-checking (no TS sources) |
| Tests | pytest (`backend/tests`, ~180 files), Vitest 4 (co-located `*.test.js(x)`), Chrome capture harness (`npm run capture:ui`) |
| CI | `.github/workflows/checks.yml` (backend lock check + pytest; frontend lint, typecheck, test, build, demo build + bundle guard), `images.yml`, `publish-images.yml`, `lock-refresh.yml`, `devcontainer.yml` |

## Repository map

```
backend/app/
  main.py, worker.py          API factory (routers, CORS+CSRF) · scheduler worker
  api/routes_*.py             HTTP routes (ops routers admin-gated in main.py)
  core/                       config, csrf, deploy_mode (DEPLOY_ENV local|dev|hosted), security deps
  ingestion/                  sources config, adapters (RSS, Sport5 HTML, ONE JSON), classifier.py (rules), orchestration
  classification/             LLM gate/providers (disabled|fake|gemini|ollama|openai_compat), merge, facts, event evidence
  taxonomy/                   canonical entities, competitions, resolver — the single source of entity truth
  services/                   preference_engine (V2, default), relevance_engine (visibility; legacy rollback), feed, learning, calibration, auth
  calibration_v2/             synthetic-headline calibration dataset/inference
  clustering/                 deterministic story clustering (no LLM/embeddings)
  notifications/              planner, outbox, dispatcher, Telegram
  results/                    results sync + providers (TheSportsDB default; opt-in Winner, EuroLeague/EuroCup, ESPN NBA, Bamboo)
  qa/, ops/, monitoring.py    census/N05 gates, ops health
  db/, repositories/, models/ ORM, data access, pydantic models; seed/ seed profiles & articles
backend/scripts/              QA gates, census, probes, demo export, reviewed correction scripts
backend/tests/                pytest suite + fixtures
frontend/src/
  pages/, components/         app screens; feed/signal, results, shell, preferences, ops, debug
  api/                        client.js + normalizers (backend mode)
  context/                    AppContext; localDemo.js lazy-loads mocks + frozen legacy JS engine (local mode only)
  demo/                       public read-only demo entry (demo.html)
  lab/                        dev-only design lab (vite.lab.config.js)
  engine/, data/              legacy JS relevance engine + mocks — local mode only, not product logic
deploy/                       Compose stack, backup/restore, rehearsal scripts, systemd units
scripts/                      check.ps1 (local CI), worker.ps1, preview.ps1, demo-publish.ps1, dev.sh
docs/                         living contracts (see below); docs/qa = rating evidence (never delete)
.claude/skills/               project skills — prefer them for matching tasks
```

## Commands

Backend (run from `backend/`; relative SQLite paths resolve there):
```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --require-hashes -r requirements.lock
.venv\Scripts\python -m uvicorn app.main:app --reload     # API :8000, /docs, GET /health
.venv\Scripts\python -m app.worker                        # scheduler (SCHEDULER_ENABLED=true to poll)
.venv\Scripts\python -m pytest tests -q                   # full suite
```
Frontend (run from `frontend/`):
```powershell
npm ci
npm run dev            # VITE_DATA_MODE=backend for the real API; unset/local = browser mocks
npm run lint           # eslint, --max-warnings=0
npm run typecheck      # tsc -p jsconfig.json
npm test               # vitest run
npm run build; npm run build:demo; npm run check:demo-bundle
npm run lab            # design lab
npm run capture:ui     # browser harness (needs Chrome)
```
Repo root: `powershell -File scripts\check.ps1` (backend tests + frontend lint/typecheck/test/build;
CI additionally runs the lock check and the demo build/guard). Owner's machine:
`powershell -File scripts\worker.ps1 -Status` before touching the worker.

Dependencies: `requirements.txt` holds ranges; installs use the hash-pinned `requirements.lock`
(CI fails if they drift — regenerate per the lock header, in its own PR).

## Conventions

- **Tests first** for behavior changes (skill `test-driven-development`); behavioral tests with
  deterministic fixtures, not mirrors of the implementation. Classification/relevance changes
  also need the real-data gates (skills `signal-real-data-qa`, `signal-quality-eval`).
- Use the area skills: classification (`signal-classification-change`), relevance
  (`signal-relevance-change`), taxonomy (`signal-taxonomy-change`), sources
  (`signal-source-onboarding`), pipeline review, feed complaints (`signal-feed-audit`), PRs
  (`signal-pr-open` / `signal-pr-merge`), docs (`signal-doc-truth`).
- Keep scoring separate from UI and ingestion separate from scoring; small, testable functions.
- New config flags default to off/safe; hosted-unsafe flags belong in
  `core/deploy_mode.py::HOSTED_FORBIDDEN_FLAGS`.
- Every new route needs an explicit auth gate; `tests/test_authz_inventory.py` enforces the inventory.
- Frontend follows [docs/FRONTEND_DESIGN_SYSTEM.md](docs/FRONTEND_DESIGN_SYSTEM.md): Signal UI
  tokens, RTL, 320–390 px phones, 44 px touch targets, reduced motion.
- Delivery: one branch + one PR per feature off current `origin/main`; report actual check
  results; opening a PR is not deploying (see [AGENTS.md](AGENTS.md)).

## Living docs by subsystem

Ingestion [RSS_INGESTION](docs/RSS_INGESTION.md) · guardrails [RSS_QUALITY_GUARDRAILS](docs/RSS_QUALITY_GUARDRAILS.md) ·
LLM [LLM_CLASSIFICATION](docs/LLM_CLASSIFICATION.md) · facts [ARTICLE_FACTS](docs/ARTICLE_FACTS.md) ·
taxonomy [TAXONOMY](docs/TAXONOMY.md) · relevance [RELEVANCE_CONTRACT](docs/RELEVANCE_CONTRACT.md),
[RELEVANCE_VISIBILITY_CONTRACT](docs/RELEVANCE_VISIBILITY_CONTRACT.md), [PREFERENCE_MODEL_V2](docs/PREFERENCE_MODEL_V2.md) ·
learning [FEEDBACK_LEARNING](docs/FEEDBACK_LEARNING.md) · calibration [CALIBRATION_V2](docs/CALIBRATION_V2.md) ·
interests [INTERESTS](docs/INTERESTS.md) · clustering [CLUSTERING](docs/CLUSTERING.md) ·
freshness [FEED_FRESHNESS](docs/FEED_FRESHNESS.md) · scheduler [SCHEDULER](docs/SCHEDULER.md) ·
notifications [NOTIFICATIONS](docs/NOTIFICATIONS.md) · results [RESULTS](docs/RESULTS.md) ·
users/auth [USER_PLATFORM](docs/USER_PLATFORM.md) · translation [TITLE_TRANSLATION](docs/TITLE_TRANSLATION.md) ·
deploy [DEPLOYMENT](docs/DEPLOYMENT.md), [HOSTING_PLAN](docs/HOSTING_PLAN.md) (proposal), [MOBILE_REMOTE_ACCESS](docs/MOBILE_REMOTE_ACCESS.md) ·
frontend [FRONTEND_DESIGN_SYSTEM](docs/FRONTEND_DESIGN_SYSTEM.md).

`docs/IMPLEMENTATION_AUDIT.md` was retired on 2026-10-12 (it audited the pre-backend Base44
prototype); do not recreate it.
