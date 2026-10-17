---
name: signal-pr-open
description: Prepare, self-review, and open a focused pull request for Signal Sports. Use when asked to open or prepare a PR, submit implementation work, or before creating a PR through gh, an API, or another tool. Owns scope, code quality, local readiness, and honest PR evidence. Use signal-pr-merge before any merge.
---

# Open a Signal Sports PR

Deliver the simplest correct change that achieves the authorized outcome.
Optimize for a useful, understandable product, not PR counts or elaborate process.

## 1. Establish the task

Read applicable CLAUDE.md instructions, the request, and relevant current code.
Inspect repository state instead of trusting remembered paths or commands.

Identify the requested outcome, observable acceptance criteria, and explicit
limits. Reuse decisions already approved by Guy. A request to implement a
specific behavior authorizes that behavior; do not ask for it again.

Ask only when an unresolved choice materially changes the product, scope,
cost, data policy, or live operations. First finish independent authorized work
and present the smallest concrete decision needed.

Respect "draft only", "open only", "review only", and "do not merge".
Opening a PR is not by itself authorization to merge or deploy.

## 2. Require concrete value and coherent scope

Explain the change's benefit in one sentence. Valid benefits include:
- requested behavior or a bug fix;
- a test catching a plausible application regression;
- removal of specific duplication, complexity, or maintenance risk in active code;
- removal of recurring development or operational friction;
- correction of materially inaccurate documentation;
- dependency maintenance with a concrete security, compatibility, reliability,
  or supported-toolchain reason.

Do not invent housekeeping tasks, unused templates, cosmetic badges, redundant
configuration, trivial tests, or speculative abstractions.

Prefer one PR per coherent outcome that can be reviewed and reverted sensibly.
Keep its code, tests, configuration, and required docs together. Split only at
meaningful boundaries; explain ordering when changes depend on one another.
Do not bundle unrelated fixes discovered during review.

Check for an existing PR for the task. Continue it rather than create duplicates.
If a requested change seems unnecessary, explain why; do not silently discard it.

## 3. Preserve the workspace

Confirm the repository, remote, target branch, task branch, and working-tree state.
For new work, fetch and branch from the current remote target, normally origin/main.
Use feat/, fix/, docs/, chore/, test/, or ci/ as appropriate.

For existing work, preserve the branch and compare against the current target.
Update it when relevant target changes, conflicts, or repository rules require it.
Do not recreate or rebase it just for cosmetic freshness.

Never commit directly to main. Never discard, reset, stash, or overwrite unrelated
work to clean the checkout. Use an isolated worktree when needed.
Inspect staged paths before committing; do not blindly stage the entire workspace.

## 4. Implement for the current product

Follow established conventions unless they cause the problem being fixed.
Prefer explicit control flow, clear names, focused functions, and existing
dependencies. Keep domain logic separate from I/O where that improves clarity.

Use these principles:
- Solve the root cause. Avoid special cases that merely hide the observed symptom.
- Keep one authoritative representation of each fact. Avoid duplicated business
  rules, derived state that can drift, and parallel paths doing the same job.
- Introduce abstractions for a real boundary or demonstrated repetition, not
  hypothetical future consumers. Do not build a framework for one feature.
- Validate at trust boundaries. Make internal invariants explicit rather than
  adding fallback values everywhere.
- Distinguish valid empty results from failures. Do not swallow exceptions,
  silently turn failures into success, or return invented data.
- Catch errors where recovery, useful context, or translation is possible.
  Preserve causes and avoid broad catches that hide programming errors.
- Give external I/O appropriate timeouts and bounded retries. Retry only where
  duplicate effects are prevented or acceptable.
- Keep state transitions, ownership, cleanup, and async behavior understandable.
- Preserve contracts and persisted data unless changing them is explicitly in scope.
- Add logs that help diagnose real failures without leaking secrets or user data.
- Avoid unnecessary queries, full-data scans, repeated work, and unbounded queues.
  Optimize demonstrated costs; do not introduce speculative performance machinery.
- Remove code made obsolete by this change. Do not leave competing implementations,
  stale comments, temporary debug output, or unexplained TODOs.

Apply only relevant principles. Do not expand the task to repair the whole repository.

## 5. Self-review as a reviewer, not the author

After implementation, reread the original request before rereading the solution.
Then inspect the entire diff against the intended base, including new files,
deleted code, tests, locks, configuration, and docs. Inspect surrounding callers
and consumers; a diff alone cannot establish a contract.

Perform three passes:

### A. Requirement and design
Map each acceptance criterion to the implementation.
Look for missing behavior, unnecessary changes, and a simpler adequate design.
Challenge the assumptions that made this implementation seem correct.

### B. Failure and integration
Trace one ordinary flow and the most plausible adverse flow through the affected
boundaries. For a bug fix, trace the original failure as well.
Check relevant edge cases: empty or malformed inputs, missing state, duplicate
events, partial failure, retries, restarts, ordering, and concurrent updates.

For Signal Sports, where touched, inspect:
- stable persisted identifiers and backward compatibility;
- dedup and clustering across ingestion runs and restarts;
- relevance/classification fallback and uncertain model output;
- source state advancement after partial failures;
- notification eligibility and duplicate-send risks;
- DB transactions, migrations, retention, and data loss;
- API/frontend agreement, loading, empty, and error states;
- local/dev/hosted separation and accidental real-world side effects.

Do not require every case for every PR. Choose cases justified by the actual diff.

### C. Tests and simplification
Read assertions as critically as production code.
Ask whether a broken implementation could still pass, especially through excessive
mocking, snapshots of incidental output, or expected values copied from the code.
Check whether code can be deleted or simplified without losing required behavior.

Record concrete findings with file/location, failure scenario, impact, and remedy.
Classify:
- blocker: incorrect behavior, data/security risk, broken contracts, unmet acceptance;
- improvement: worthwhile within-scope simplification or clarity;
- follow-up: genuine issue outside this task.

Fix blockers and worthwhile in-scope improvements, then review the resulting diff.
Do not manufacture findings or claim an independent reviewer inspected the work.
Do not stop after listing problems you can safely fix within scope.

## 6. Validate behavior with proportionate evidence

Read and apply signal-pr-finish for substantive changes. It owns the repo's
implementation checks, artifact/contract gates, docs truth, and real-data
comparisons. Read signal-doc-truth when applicable.

If a required skill is missing, inspect documented checks and CI, disclose the
gap, and perform equivalent checks where possible. Do not claim the skill ran.
Block readiness if required evidence cannot be established.

Use current repository commands and supported environments. Verify scripts and
flags before use. Do not invent commands from memory.

For bug fixes, add a focused regression test when practical. Confirm it detects
the original failure by running against the prior behavior or demonstrating the
specific failing assertion. If this is unsafe or impractical, explain the limit.
For new logic, test observable outcomes and relevant invariants.
Use integration or contract tests when the risk crosses boundaries.

Do not add tests solely to increase counts or coverage. Do not test framework
behavior, pin trivial constants, or mirror private implementation details.
A prose typo does not need a test suite; executable documentation needs verification.

Run checks required by repository policy plus those justified by the diff.
Reuse valid evidence for unchanged code and inputs. Rerun affected checks after fixes.
Separate passed, failed, not run, and pending. Never weaken checks to get green.

Use isolated databases and fixtures. No real Telegram sends, live DB writes,
worker restarts, or production credentials as incidental validation.
If realistic feed evaluation is required, use the repository's safe snapshot process.

## 7. Review dependencies and documentation

Keep manifests and lockfiles consistent using the current repository resolver
workflow. Preserve existing pins where possible and use targeted updates.
Explain additional resolution changes; existing transitive dependencies may
legitimately need to move.

If manifest regeneration produces no lock change, verify and explain why.
A lower-bound-only bump needs a concrete supported scenario, not a version goal.
Respect current compatibility caps and their comments. Do not silently change
Python, Node, resolver versions, or dependency policy.

Update docs in the same PR when claims become false. Verify commands, paths,
defaults, and behavior. Distinguish implemented behavior from actually deployed
behavior in docs/CURRENT_PROJECT_STATE.md when applicable.
Do not churn docs that remain accurate.

## 8. Present and open the PR

Recheck the final diff, intended commits, and staged files. Exclude secrets,
personal values, machine-specific configuration, local DBs, and generated noise.
If a secret entered commits being published, removing it only from the final
tree is insufficient; stop publication and address the exposure.

Use .github/pull_request_template.md if present. Otherwise include:
- problem and concrete benefit;
- resulting behavior and scope;
- checks actually run and results;
- concise self-review evidence: paths/flows examined, meaningful findings fixed,
  and material remaining limitations;
- risks and any outstanding acceptance checks;
- related issues.

Keep the review summary specific and short; do not dump this checklist.
Use "Closes #N" only when the issue's acceptance criteria are complete.
Otherwise use "Implements #N" or "Related to #N" and identify remaining validation.

For multiline gh bodies, use a file with --body-file and safe shell quoting.

Push the intended branch and open with explicit base and head.
A ready PR may have CI pending, provided local readiness gates pass and the
pending status is stated honestly. Do not claim merge readiness.
Open a draft only when requested or useful to share incomplete work; list blockers.

Verify the created URL, base, head SHA, and actual diff.
Report the link, useful outcome, validation, and remaining blockers.
Proceed to signal-pr-merge only when existing task scope authorizes it.

## Boundaries

Never bypass protections or hooks, force-push main, delete
backend/data/signal_sports.db, or enable retention as housekeeping.
Do not deploy, restart, or reconfigure the running PC worker incidentally.
This skill governs PR opening; signal-pr-merge governs the final merge decision.

