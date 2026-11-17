---
description: Two-phase feature workflow — research into FEATURE_PLAN.md, then /clear and implement, check, PR, merge
argument-hint: <feature description or issue number>
---

# New feature: $ARGUMENTS

Two phases, separated by `/clear` so that implementation starts from a small, written plan
instead of a long research transcript. Decide which phase applies:

- `FEATURE_PLAN.md` missing at the repo root, or written for a different feature → **Phase 1**.
- `FEATURE_PLAN.md` present for this feature and approved → **Phase 2**.

## Phase 1 — Research and plan (read-only; no production edits)

1. If `$ARGUMENTS` is an issue number, read it once: `gh issue view <n> --comments`.
2. Route through the **Where to look first** table in `CLAUDE.md`: pick the matching row(s),
   load the named skill, and open only the files and tests it lists. Large files: `Grep` for the
   symbol, then `Read` with `offset`/`limit`. Never open the data files that `CLAUDE.md` forbids.
   Use one `Explore` agent only if the routing table has no row for this area.
3. Read only the contract doc for the subsystem (index: `docs/README.md`). Docs and code
   disagree → the code wins; note the drift in the plan.
4. Write `FEATURE_PLAN.md` at the repo root (untracked scratch; never commit it), at most ~60 lines:
   - **Goal**: one sentence, plus the user-visible outcome.
   - **Files**: each path to change, with what changes (functions/symbols, not prose).
   - **Tests first**: the test file(s) to extend and the failing cases to write.
   - **Gates**: targeted test commands; real-data gates if classification or relevance changes
     (`signal-real-data-qa`); taxonomy export if `backend/app/taxonomy/` changes; authz
     inventory if a route is added; profile trio if seed topics change.
   - **Risks and non-goals**: product principles touched (push rules, abstention, profiles
     not hardcoding, Hebrew UI), data-safety concerns, and what is explicitly out of scope.
   - **Open questions**: only real owner decisions. Speculative trade-offs → follow-up ticket.
5. Stop. Show the plan summary and tell the user: approve, then run `/clear` and
   `/new-feature $ARGUMENTS` again to start Phase 2.

## Phase 2 — Implement, check, ship

1. Read `FEATURE_PLAN.md`; it is the whole brief. Do not repeat the research; open only the files it lists.
2. Branch off current main: `git fetch origin; git switch -c <type>/<slug> origin/main`.
3. Tests first (skill `test-driven-development`): write the failing tests, watch them fail,
   implement, watch them pass. Iterate with targeted runs (`pytest tests/<file>.py -q` in
   `backend/`, `npx vitest run <file>` from `C:\...\frontend` with a capital drive letter).
4. Run the plan's gates, then the full local check from the repo root:
   `powershell -File scripts\check.ps1`. Fix every failure; never skip hooks.
5. Update the contract doc if behavior changed (skill `signal-doc-truth`).
6. Open the PR (skill `signal-pr-open`): focused diff, real check results in the body,
   `Closes #<n>` when applicable. Don't commit `FEATURE_PLAN.md`.
7. Merge (skill `signal-pr-merge`). `main` has no branch protection, so never use `--auto`:
   ```powershell
   gh pr checks <n> --watch
   gh pr merge <n> --squash --delete-branch --match-head-commit <sha>
   git switch main; git pull --ff-only
   ```
8. Delete `FEATURE_PLAN.md`. Report: PR link, merge commit, checks passed, anything skipped.
   Merging is not deploying: restarting the worker/API is a separate step
   (`scripts\worker.ps1 -Status` first).
