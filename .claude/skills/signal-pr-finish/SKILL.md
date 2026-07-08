---
name: signal-pr-finish
description: Use to verify a substantial Signal Sports change is actually done before presenting it — checks scope, runs the relevant test suites, verifies generated artifacts and contracts, and confirms docs match reality. Triggers on requests like "is this ready", "finish this up", "wrap up this change" at the end of implementation work. Not for cross-session handoffs — use signal-handoff for that.
---

This is a pre-presentation quality gate for work just completed in this session, not a handoff
document (see `signal-handoff`) and not a commit/push action.

## Workflow

1. **Inspect the actual diff**: `git status` and `git diff` (against `main`/the base branch).
   Read the real change, don't rely on memory of what you intended.
2. **Match implementation to the stated task.** Anything touched that isn't explained by the
   task gets called out explicitly — scope creep is named, not silently left in.
3. **Backend tests if `backend/` changed**:
   `cd backend && .venv\Scripts\python.exe -m pytest tests/ -v` (hermetic; no Ollama/API key).
   Do NOT trust hard-coded suite counts in docs — they drift. The gates are: zero failures, and
   the collected count did not *decrease* versus the base branch (a decrease means tests were
   deleted or stopped being collected — explain it or fix it).
4. **Frontend checks if `frontend/` changed**:
   `cd frontend && npm run test && npm run lint && npm run typecheck && npm run build`.
5. **Contract & artifact gates** (run the ones the diff makes relevant):
   - Touched `backend/app/taxonomy/` → the generated artifact
     `frontend/src/data/taxonomyReach.generated.json` must be regenerated and committed
     (`test_taxonomy_export_freshness.py` enforces it; see `signal-taxonomy-change`).
   - Touched legacy profile seeds (backend or frontend) → the drift trio must agree:
     `backend/app/seed/seed_profiles.py`, `frontend/src/data/userProfiles.js`,
     `docs/fixtures/profile_parity.json` (both drift-guard tests enforce this).
   - Touched relevance/preference/visibility/learning behavior → a real-data decision diff per
     `signal-real-data-qa` is part of "done", including the push-discipline count.
   - Touched `frontend/src/engine/relevanceEngine.js` → stop and justify: the JS engine is
     FROZEN by architecture decision (local/demo mode only, no v2/taxonomy/learning ports).
     A change there needs an explicit product reason, not "keeping it in sync".
   - Changed an API response shape → check the frontend consumer (`frontend/src/api/client.js`
     and the consuming page/component) in the same change.
6. **Missing regression coverage.** A behavior change or bug fix without a new/updated test in
   the matching suite is incomplete — the area skills (`signal-classification-change`,
   `signal-relevance-change`, `signal-taxonomy-change`, `signal-source-onboarding`) name the
   right test files.
7. **Docs describe actual behavior, not intent.** Run the diff-driven scope procedure in
   `signal-doc-truth` — `docs/CURRENT_PROJECT_STATE.md` is almost always affected, plus the
   layer contract for the area touched. Re-read each updated section against the code once more.
8. **For UI changes, give manual verification steps** (`npm run dev`, which route, which data
   mode — `local` vs `backend` — and what to look for) rather than asserting visual correctness
   from code alone. Product pages and the ops console have different shells — check the right one.
9. **Summarize**: what changed, tests run + results, artifacts/contracts verified, docs touched,
   known risks/remaining limitations. Keep it short. Report failures as failures.

## Do not

Do not commit, push, merge, `git reset`, delete data (including `backend/data/signal_sports.db`
— the real QA corpus), or otherwise perform destructive/shared-state operations as part of this
skill — those require explicit user instruction.
