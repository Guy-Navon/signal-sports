---
name: signal-pr-gate
description: Use BEFORE opening a pull request and BEFORE merging one on Signal Sports — decides whether the PR should exist at all, whether it is ready to open, and whether it may be merged; also for triaging a backlog of open PRs (including Dependabot). Triggers on "open a PR", "merge this", "handle the open PRs", "clean up the PRs", "should we merge", or before any `gh pr create` / `gh pr merge`. Code-level "is the change done" verification lives in signal-pr-finish; this skill calls it.
---

Two gates. A PR passes Gate 1 before `gh pr create` and Gate 2 before `gh pr merge`.
Green CI is necessary, never sufficient: a passing PR that does nothing useful is junk, and
junk gets closed, not merged.

## Gate 0: does this PR deserve to exist? (both gates start here)

Answer in one sentence: **what does this change do for the product or the repo?** It must
match at least one:

- changes behavior a user or operator sees (feed, ingestion, classification, UI, ops), or
  fixes a bug;
- adds a test that would catch a **plausible** regression in real logic (persisted ids,
  relevance decisions, dedup, source state). A test that pins a one-line constant or
  re-asserts framework behavior doesn't count;
- removes real, recurring cost (CI minutes, broken local setup, a manual step done often);
- keeps docs true after a behavior change (`signal-doc-truth`);
- a dependency update that fixes a security issue or a runtime deprecation, or unblocks
  something we need.

**Junk, close it:** boilerplate for a solo repo (CODEOWNERS with the only owner, SECURITY,
CONTRIBUTING, issue or feature templates nobody uses), config that restates a default (for
example `blank_issues_enabled: true`), cosmetic badges, a README line repeating another doc,
filler "housekeeping" batches, a major bump of a dependency that isn't used at runtime, and
floor-only version bumps that change nothing installed.

Never open PRs on your own initiative for housekeeping. One PR per task Guy asked for.

## Gate 1: before opening

1. **Gate 0 passes**, and you can write the one-sentence "why" for the PR body.
2. **One focused change.** One issue = one branch = one PR. Anything in the diff that the
   task doesn't explain gets removed or named explicitly. Branch prefix:
   `feat/ fix/ docs/ chore/ test/ ci/`.
3. **Branch from an up-to-date `main`** (`git fetch` and branch from `origin/main`), never
   commit on `main`.
4. **Run `signal-pr-finish`** for anything beyond a docs typo. That covers tests, the
   artifact and contract gates, docs truth and the real-data diff for feed-affecting
   changes. Quick path: `powershell -File scripts\check.ps1` (`-Backend` / `-Frontend`).
5. **Lockfile rule:** a change to a range in `backend/requirements.txt` ships with a
   regenerated `backend/requirements.lock` in the same PR, otherwise CI fails as "lock is
   stale". Regenerate against the existing pins so only the intended package moves:
   copy the current lock body to a temp file, then
   `uv pip compile requirements.txt --universal --python-version 3.13 --generate-hashes --no-header --no-annotate -o <temp> --upgrade-package <name>`
   and put the header back. If the diff moves more than that package and its new
   dependencies, you resolved without the old pins. Redo it.
6. **PR body = `.github/pull_request_template.md`**: what and why, checks actually run
   (tick only what you ran), notes and risks. Issues that need user-run validation (device,
   phone, LTE) get "Implements #N", never "Closes #N".
7. **No secrets or personal values** in the diff: no `.env`, tokens, chat ids, tailnet
   hostnames, machine names.

## Gate 2: before merging

1. **Gate 0 again, on the actual diff**: `gh pr diff <n>`. Read it, don't trust the title.
   A PR from another session or tool gets the same scrutiny as a stranger's.
2. **CI green on the current head SHA** (`gh pr checks <n>`), after any rebase or push.
   Every job, not "the important ones". A pending check counts as not green.
3. **Facts in the diff are true**: paths, script names, flags, versions and commands that
   a doc or test mentions exist in the repo right now (`ls`, `grep`). Fix the PR branch if
   not.
4. **Product decisions stay with Guy.** A new behavior, a threshold change, enabling a
   source, Telegram or retention, or anything touching the running PC worker: ask first.
   If the PR implements a direction Guy already approved, merge it yourself; don't wait for
   a separate "merge" word.
5. **Merge:** `gh pr merge <n> --merge --delete-branch`, one at a time. After each merge,
   re-check the rest for conflicts. Dependabot PRs: comment `@dependabot rebase`, don't
   hand-edit unless the lock needs regenerating.
6. **After merge:** `git pull` on `main`; if behavior changed, confirm
   `docs/CURRENT_PROJECT_STATE.md` reflects it.

## Dependabot policy

- **GitHub Actions bumps:** merge when CI is green; they keep runners off deprecated Node.
  Check that workflows CI doesn't run (`publish-images.yml`, `images.yml`) only changed the
  version tag.
- **npm patch/minor with a green build:** merge.
- **npm major (React and others):** close with a reason. A major migration is its own
  deliberate PR covering every peer package (`react-dom`, `@types/*`).
- **pip range bumps:** the lock decides what's installed, so a floor-only bump the lock
  already satisfies is noise. Merge only if it brings a real fix, then regenerate the lock
  per Gate 1.5. Majors of packages unused at runtime (for example `anthropic` while
  `TRANSLATION_PROVIDER=disabled`): close.
- `fastapi` stays `<0.137`; see the comment in `requirements.txt`.

## Triaging a backlog ("handle the open PRs")

1. `gh pr list --state open` plus `gh pr checks` for each PR.
2. For each one, `gh pr diff`, then Gate 0, then a verdict: **merge / fix then merge /
   close (reason) / ask Guy**.
3. **Show Guy the table before acting** whenever anything gets closed or a decision is
   his. Then execute, merging one at a time per Gate 2.
4. Close with a one-line reason comment (`gh pr close <n> --comment "…"`).
5. Report each PR's verdict in the final summary. Failures stay failures.

## Do not

- Merge because CI is green.
- Batch unrelated changes into one PR, or split a single change into a stream of filler PRs.
- Force-push to `main`, skip hooks, or merge with failing or pending checks.
- Delete `backend/data/signal_sports.db` or enable retention as part of any PR.
