# Signal Sports

Personalized sports news intelligence feed. Surfaces only the stories that matter to a specific user — not a generic sports feed.

## Repository structure

```
signal-sports/
├── frontend/       React + Vite + Tailwind frontend
├── backend/        FastAPI Python backend
├── docs/           Product and architecture documentation
├── .claude/skills/ Project-level Claude Code skills (source onboarding, classification changes, feed audit, PR finish, handoff)
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

- [PRODUCT_UNDERSTANDING.md](docs/PRODUCT_UNDERSTANDING.md) — what Signal Sports is and isn't
- [IMPLEMENTATION_AUDIT.md](docs/IMPLEMENTATION_AUDIT.md) — current state vs intended product
- [BACKEND_FOUNDATION.md](docs/BACKEND_FOUNDATION.md) — backend architecture and engine design
- [CALIBRATION_V0.md](docs/CALIBRATION_V0.md) — calibration flow design
- [CALIBRATION_APPLY.md](docs/CALIBRATION_APPLY.md) — applying calibration to sandbox profile
- [MOBILE_REMOTE_ACCESS.md](docs/MOBILE_REMOTE_ACCESS.md) — private phone access via Tailscale Serve
