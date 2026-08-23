# Signal Sports

Personalized sports news intelligence feed. Surfaces only the stories that matter to a specific user — not a generic sports feed.

## Repository structure

```
signal-sports/
├── frontend/       React + Vite + Tailwind frontend
├── backend/        FastAPI Python backend
├── docs/           Product and architecture documentation
├── .claude/skills/ Project-level Claude Code skills (classification / relevance / taxonomy changes, source onboarding, feed audit, real-data QA, doc truth, PR finish, handoff)
└── CLAUDE.md       Project context for AI-assisted development
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Tests: `npm run test` | Lint: `npm run lint` | Build: `npm run build`

See [frontend/README.md](frontend/README.md) for full details.

## Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
.venv\Scripts\uvicorn app.main:app --reload
```

Tests: `.venv\Scripts\python -m pytest tests/ -v`

See [backend/README.md](backend/README.md) for full details.

## Docs

Start here for orientation (any agent picking up the project cold):

- [CURRENT_PROJECT_STATE.md](docs/CURRENT_PROJECT_STATE.md) — **the authoritative, up-to-date summary**; §13 is a self-sufficient handoff prompt
- [RELEVANCE_CONTRACT.md](docs/RELEVANCE_CONTRACT.md) — umbrella contract for the intelligence pipeline (FACTS → VISIBILITY → PREFERENCE → LEARNING)
- [USER_PLATFORM.md](docs/USER_PLATFORM.md) — **active milestone**: accounts, auth, onboarding, per-user isolation — approved architecture, not yet implemented (Epic #48, issues #49–#55)

Reference:

- [PRODUCT_UNDERSTANDING.md](docs/PRODUCT_UNDERSTANDING.md) — what Signal Sports is and isn't (vision; not an implementation reference)
- [BACKEND_FOUNDATION.md](docs/BACKEND_FOUNDATION.md) — backend architecture and engine design
- [FRONTEND_DESIGN_SYSTEM.md](docs/FRONTEND_DESIGN_SYSTEM.md) — design tokens, product-vs-console split, RTL rules
- [MOBILE_REMOTE_ACCESS.md](docs/MOBILE_REMOTE_ACCESS.md) — private phone access via Tailscale Serve
- [RESULTS.md](docs/RESULTS.md) — personalized game-results feature (provider abstraction, relevance, sync, API)

Historical (kept for record, superseded — do not cite as current behavior):

- [IMPLEMENTATION_AUDIT.md](docs/IMPLEMENTATION_AUDIT.md) — pre-backend snapshot
- [CALIBRATION_V0.md](docs/CALIBRATION_V0.md) / [CALIBRATION_APPLY.md](docs/CALIBRATION_APPLY.md) — superseded by [CALIBRATION_V2.md](docs/CALIBRATION_V2.md)
