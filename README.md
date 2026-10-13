# Signal Sports

A personalized, Hebrew-first sports news intelligence feed. It surfaces only the stories that
matter to a specific user, so they do not have to read seven sports sites to find them.

## Repository structure

```
signal-sports/
├── frontend/        React + Vite + Tailwind (Hebrew/RTL product UI + ops console)
├── backend/         FastAPI + SQLite: ingestion, classification, relevance, clustering, push, results
├── scripts/         repo-level tools (worker.ps1 start/stop/status, audit report generator)
├── docs/            contracts, current state, QA evidence
├── .claude/skills/  project skills for Claude Code (classification / relevance / taxonomy changes,
│                    source onboarding, feed audit, real-data QA, doc truth, PR finish, handoff)
└── CLAUDE.md        product intent for AI-assisted development
```

## Quick start

```powershell
# backend (from backend/)
python -m venv .venv
.venv\Scripts\python -m pip install --require-hashes -r requirements.lock
.venv\Scripts\python -m uvicorn app.main:app --reload        # http://127.0.0.1:8000/docs

# scheduler worker (from the repo root; needs SCHEDULER_ENABLED=true in backend/.env)
powershell -File scripts\worker.ps1 -Status

# frontend (from frontend/)
npm install
npm run dev                                                 # http://localhost:5173
```

Checks (the same as CI): `cd backend; .venv\Scripts\python -m pytest tests -q` and
`cd frontend; npm run lint; npm run typecheck; npm run test; npm run build`.
Details: [backend/README.md](backend/README.md), [frontend/README.md](frontend/README.md).

## Docs

Start here (cold start, no history needed):

- [docs/CURRENT_PROJECT_STATE.md](docs/CURRENT_PROJECT_STATE.md): **the authoritative current
  state**. Status at a glance, architecture, open work, next-milestone candidates, how to run,
  a handoff prompt and a doc map.
- [docs/RELEVANCE_CONTRACT.md](docs/RELEVANCE_CONTRACT.md): the umbrella contract (pipeline map,
  decision semantics, architecture invariants, quality gate).
- [CLAUDE.md](CLAUDE.md) and [docs/PRODUCT_UNDERSTANDING.md](docs/PRODUCT_UNDERSTANDING.md):
  product intent and vision.
- [docs/HOSTING_PLAN.md](docs/HOSTING_PLAN.md): **the plan under review** for moving the model,
  backend and frontend off the owner's machine (milestone 13, the top priority).

Layer contracts: [ARTICLE_FACTS](docs/ARTICLE_FACTS.md) ·
[RELEVANCE_VISIBILITY_CONTRACT](docs/RELEVANCE_VISIBILITY_CONTRACT.md) ·
[PREFERENCE_MODEL_V2](docs/PREFERENCE_MODEL_V2.md) · [INTERESTS](docs/INTERESTS.md) ·
[CALIBRATION_V2](docs/CALIBRATION_V2.md) · [FEEDBACK_LEARNING](docs/FEEDBACK_LEARNING.md) ·
[TAXONOMY](docs/TAXONOMY.md) · [LLM_CLASSIFICATION](docs/LLM_CLASSIFICATION.md) ·
[RSS_QUALITY_GUARDRAILS](docs/RSS_QUALITY_GUARDRAILS.md) · [RSS_INGESTION](docs/RSS_INGESTION.md) ·
[CLUSTERING](docs/CLUSTERING.md) · [FEED_FRESHNESS](docs/FEED_FRESHNESS.md) ·
[SCHEDULER](docs/SCHEDULER.md) · [NOTIFICATIONS](docs/NOTIFICATIONS.md) ·
[RESULTS](docs/RESULTS.md) · [USER_PLATFORM](docs/USER_PLATFORM.md) ·
[FRONTEND_DESIGN_SYSTEM](docs/FRONTEND_DESIGN_SYSTEM.md) ·
[MOBILE_REMOTE_ACCESS](docs/MOBILE_REMOTE_ACCESS.md) · [TITLE_TRANSLATION](docs/TITLE_TRANSLATION.md) (post-MVP)

Evidence: [docs/qa/](docs/qa/) holds the N05 ground truth and gate baseline, census #2, and
their data files. [docs/audits/2026-09-05.md](docs/audits/2026-09-05.md) is the September
repository audit snapshot, with an [interactive Hebrew version](docs/audits/2026-09-05.html).
Superseded docs, closed-milestone QA reports and delivered task briefs were removed on
2026-10-12 and remain in git history.
