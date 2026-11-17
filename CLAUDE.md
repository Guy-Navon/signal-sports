# Signal Sports — Guide for AI Sessions

Signal Sports is a personalized, Hebrew-first sports news intelligence feed. It ingests
Israeli sports news, works out what each article is about, and shows each user only what is
worth *their* attention. North star:

> "What sports news is actually worth this user's attention right now?" — not "what sports
> news exists?"

A beautiful generic feed is a failure; a rough feed that filters correctly is closer to success.

**Where the truth lives.** This file is a map, not a status report.
- Current behavior, runtime state and history: [docs/CURRENT_PROJECT_STATE.md](docs/CURRENT_PROJECT_STATE.md); doc index: [docs/README.md](docs/README.md)
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
| Backend | Python 3.13, FastAPI, SQLAlchemy 2 (sync), SQLite only; additive soft migrations at startup. Cookie sessions (argon2), CSRF middleware, Google sign-in |
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
docs/                         contracts (index: docs/README.md); docs/qa = rating evidence (never move/delete); docs/archive = history
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

Targeted runs (cheaper than the full suite while iterating; full suite before a PR):
```powershell
.venv\Scripts\python -m pytest tests/test_article_facts.py -q        # one file (backend/)
.venv\Scripts\python -m pytest tests -q -k "facts and not llm"       # by keyword
npx vitest run src/api/client.test.js                                # one file (frontend/)
```
Use `-q`, not `-v`: the full suite prints thousands of lines under `-v`.

## Gotchas (each one has cost a session before)

- **Vitest + lowercase drive letter.** Started from `c:\...` (VS Code terminals), vitest fails
  *every* file with "failed to find the runner". `cd C:\Users\HOME\Documents\signal-sports\frontend`
  (capital `C:`) first. `scripts\check.ps1` already normalizes this.
- **No branch protection on `main`.** `gh pr merge --auto` merges *immediately*, before CI.
  Wait for checks yourself: `gh pr checks <n> --watch` (CI takes ~4 min), then
  `gh pr merge <n> --squash --delete-branch --match-head-commit <sha>`. History is squash-merged.
- **Large files: never read whole.** `Grep` for the symbol, then `Read` with `offset`/`limit`:
  `backend/app/ingestion/classifier.py` (~1.3k lines), `classification/event_evidence.py` (~1k),
  `ingestion/ingestion_service.py` (~800), `frontend/src/components/feed/signal/SignalFeedView.jsx`
  (~930), `backend/tests/test_llm_classification.py` (~1.3k), `backend/scripts/feed_ground_truth.py`
  (~950), `docs/RSS_QUALITY_GUARDRAILS.md` / `HOSTING_PLAN.md` / `LLM_CLASSIFICATION.md` /
  `RESULTS.md` (~0.9–1.4k). Never open `docs/qa/*.json`, `backend/tests/fixtures/**`,
  `frontend/src/lab/resultsFixtures.json`, `frontend/src/data/mockArticles.js` or
  `taxonomyReach.generated.json` (data, thousands of lines) — query them with a script or `Grep`.
- **Generated artifact.** Any edit under `backend/app/taxonomy/` requires
  `.venv\Scripts\python scripts\generate_taxonomy_export.py` and committing
  `frontend/src/data/taxonomyReach.generated.json` (a freshness test fails otherwise).
- **Profile drift trio.** Legacy topic seeds change in three places together:
  `backend/app/seed/seed_profiles.py`, `frontend/src/data/userProfiles.js`, `docs/fixtures/profile_parity.json`.
- **Frozen JS engine.** `frontend/src/engine/` is local-mode only; never port new intelligence to it.
- **Stored facts don't move.** Classifier/taxonomy changes reach only new rows; N05 and the
  stored-facts census gate show zero change — use `feed_ground_truth.py gate --census --facts rerun`.
- **Live runtime ≠ code defaults.** Source overrides, Telegram and live profiles live in the
  corpus DB and untracked `backend/.env`; check them read-only instead of inferring from `config.py`.
- **New routes** fail `tests/test_authz_inventory.py` until classified there.
- **Never** run anything that writes to `backend/data/signal_sports.db` as incidental validation;
  `pytest` is always safe (conftest uses a temp DB and `CLASSIFICATION_PROVIDER=disabled`).

## Where to look first

| Task | Start at | Tests to extend | Skill |
|---|---|---|---|
| Headline misclassified (sport/entity/event) | `classification/facts.py`, `ingestion/classifier.py`, `classification/event_evidence.py` | `test_article_facts.py`, `test_ingestion_classifier.py`, `test_event_evidence.py`, `test_quality_regressions.py` | `signal-classification-change` |
| LLM gate / merge / provider | `classification/gating.py`, `merge.py`, `providers.py` | `test_llm_gating.py`, `test_llm_classification.py` | `signal-classification-change` |
| Missing club/player/competition | `taxonomy/entities.py`, `taxonomy/competitions.py` | `test_taxonomy_integrity.py`, `test_entity_resolver.py` | `signal-taxonomy-change` |
| Wrong feed decision for a user | `services/preference_engine.py`, `relevance_engine.py` (`match_competition_names`) | `test_preference_engine_v2.py`, `test_relevance_visibility_contract.py` | `signal-feed-audit` → `signal-relevance-change` |
| Learning / calibration | `services/learning_service.py`, `calibration_v2/` | `test_feedback_learning.py`, `test_calibration_v2.py` | `signal-relevance-change` |
| Source failing / new source | `ingestion/config.py`, `ingestion/adapters/` | `test_*_adapter.py`, `test_source_config.py` | `signal-source-onboarding` |
| Cycle / worker / lease | `ingestion/orchestration.py`, `worker.py` | `test_orchestration*.py`, `test_worker*.py` | `signal-pipeline-review` |
| Story clustering | `clustering/` (contract `docs/CLUSTERING.md`) | `test_clustering*.py`, `test_anchor*.py` | `signal-pipeline-review` |
| Results / scores page | `results/`, `frontend/src/pages/Results.jsx` | `test_results*.py` | — |
| Auth / sessions / CSRF | `services/auth_service.py`, `core/csrf.py`, `core/security_deps.py` | `test_auth*.py`, `test_authz_inventory.py` | `differential-review` |
| Hosted-unsafe flag | `core/deploy_mode.py` | `test_deploy_mode_265.py` | `differential-review` |
| Feed UI | `frontend/src/components/feed/signal/`, `frontend/src/api/` | co-located `*.test.jsx` | `web-design-guidelines`, `webapp-testing` |
| Public demo export | `backend/scripts/export_demo_snapshot.py`, `frontend/src/demo/` | `test_demo_*.py`, `npm run check:demo-bundle` | — |

Backend paths above are relative to `backend/app/` unless they start with `backend/` or `frontend/`.
Test filenames are relative to `backend/tests/`. Skill ownership: [.claude/skills/README.md](.claude/skills/README.md).

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

## Docs

[docs/README.md](docs/README.md) is the single index: one authoritative contract per subsystem,
plus evidence (`docs/qa/`, `docs/fixtures/` — read by tests and scripts, never move them) and the
archive ([docs/archive/](docs/archive/README.md), historical only). Start with
[docs/CURRENT_PROJECT_STATE.md](docs/CURRENT_PROJECT_STATE.md). Frequently needed contracts:
[RELEVANCE_CONTRACT](docs/RELEVANCE_CONTRACT.md) · [RSS_INGESTION](docs/RSS_INGESTION.md) ·
[LLM_CLASSIFICATION](docs/LLM_CLASSIFICATION.md) · [CLUSTERING](docs/CLUSTERING.md) ·
[RESULTS](docs/RESULTS.md) · [USER_PLATFORM](docs/USER_PLATFORM.md) ·
[FRONTEND_DESIGN_SYSTEM](docs/FRONTEND_DESIGN_SYSTEM.md) · [DEPLOYMENT](docs/DEPLOYMENT.md).

Source comments cite many docs by path, so keep active docs at their paths; when a doc is
superseded, move it to `docs/archive/` only if nothing in code references it.
`docs/IMPLEMENTATION_AUDIT.md` was retired on 2026-10-12 (it audited the pre-backend Base44
prototype); do not recreate it.
