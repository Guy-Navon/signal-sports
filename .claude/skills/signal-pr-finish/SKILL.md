---
name: signal-pr-finish
description: Use to verify a substantial Signal Sports change is actually done before presenting it — checks scope, runs the relevant test suites, and confirms docs match reality. Triggers on requests like "is this ready", "finish this up", "wrap up this change" at the end of implementation work. Not for cross-session handoffs — use signal-handoff for that.
---

This is a pre-presentation quality gate for work just completed in this session, not a handoff
document for a new session (see `signal-handoff` for that) and not a commit/push action.

## Workflow

1. **Inspect the actual diff**: `git status` and `git diff` (against `main`/the base branch if on a feature branch). Read the real change, don't rely on memory of what you intended to do.
2. **Match implementation to the stated task.** Flag anything touched that isn't explained by the task — scope creep gets called out explicitly, not silently left in.
3. **Run backend tests if `backend/` changed**: `cd backend && .venv\Scripts\python.exe -m pytest tests/ -v`. The known-good baseline is documented in `docs/CURRENT_PROJECT_STATE.md` (currently 1081 tests) — a lower pass count needs an explanation, not a shrug.
4. **Run frontend checks if `frontend/` changed**: `cd frontend && npm run test`, `npm run lint`, `npm run typecheck`, `npm run build`.
5. **Run both suites when the change is cross-cutting** — e.g. anything touching the relevance engine (`backend/app/services/relevance_engine.py` has a JS mirror at `frontend/src/engine/relevanceEngine.js`) or a shared API contract.
6. **Check for missing regression coverage.** A behavior change or bug fix without a new/updated test in the matching suite is incomplete — see `signal-classification-change` for where classification/relevance tests belong.
7. **Update affected docs and confirm they describe actual behavior, not intent.** `docs/CURRENT_PROJECT_STATE.md` is almost always affected by any real behavior change; also update the specific doc for the area touched (`RSS_QUALITY_GUARDRAILS.md`, `LLM_CLASSIFICATION.md`, `RSS_INGESTION.md`, `FRONTEND_DESIGN_SYSTEM.md`, etc.). Re-read the updated section against the code once more — a doc that restates the old intent instead of the new behavior is worse than no doc update.
8. **For UI changes, give manual verification steps** (`npm run dev`, which route, which data mode — `local` vs `backend` — and what to look for) rather than asserting visual correctness from the code alone.
9. **Summarize**: what changed, tests run + results, docs touched, known risks/remaining limitations. Keep it short.

## Do not

Do not commit, push, merge, `git reset`, delete data, or otherwise perform destructive/shared-state
operations as part of this skill — those require explicit user instruction, per the repo's normal
git safety rules.
