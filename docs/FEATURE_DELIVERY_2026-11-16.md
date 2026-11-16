# Results and demo feature delivery — 2026-11-16

The owner requested that each feature be committed, pushed and represented by its
own PR, rather than existing only in a local checkout or manually published demo.
The existing changes were split from current `origin/main` at
`12ee2f68231f27bf09d471598d9c8b3a72faa597` (merged PR #556). The original
implementation was backed up before splitting, and personal local settings were
excluded. Each feature was validated at its own branch head.

## Feature stack

| Order | PR | Branch | Scope |
| --- | --- | --- | --- |
| 1 | [#557](https://github.com/Guy-Navon/signal-sports/pull/557) | `codex/demo-results-details` | Allowlisted static details, leaders, ranks, player lines and upcoming games; shared read-only demo board |
| 2 | [#558](https://github.com/Guy-Navon/signal-sports/pull/558) | `codex/results-three-day-window` | General results/detail access and cached rendering capped at 72 hours; independent upcoming window |
| 3 | [#559](https://github.com/Guy-Navon/signal-sports/pull/559) | `codex/box-score-dismiss-backdrop` | Outside click/tap closes the box score; table interaction and cross-boundary dragging preserve it |
| 4 | [#560](https://github.com/Guy-Navon/signal-sports/pull/560) | `codex/followed-team-history` | Four latest finals per directly followed team, eight unique games total, without an age limit, including selected historical details |
| 5 | [#561](https://github.com/Guy-Navon/signal-sports/pull/561) | `codex/box-score-statistics` | Expanded player statistics, weighted shooting percentages, totals, leaders, team comparisons and responsive dialog |

The first PR targets main. Each following PR initially targets the preceding
branch so its diff includes only that feature. Merge in the listed order; after
each dependency lands, retarget its successor to main and inspect the diff/checks.
A regular merge preserves shared commit ancestry. If using squash or rebase,
update dependent branches to avoid presenting already merged feature changes again.
The workflow documentation is delivered separately on `codex/feature-pr-workflow`,
initially based on the last feature branch.

## Validation

| Branch | Local verification |
| --- | --- |
| Demo details | 28 backend tests; 54 frontend/demo/guard tests; lint, typecheck, both builds and bundle guard |
| Three-day window | 84 backend tests; 138 frontend tests; lint and typecheck |
| Outside dismissal | 16 existing board/dialog tests; lint and typecheck; native pointer behavior also verified in the combined browser check |
| Followed-team history | 102 backend tests; 151 frontend tests; lint, typecheck, both builds and bundle guard |
| Expanded statistics / combined implementation | All 77 frontend test files: 981 tests; all results/demo backend tests: 437; lint, typecheck, both builds and bundle guard |

`git diff --check` passed for each feature. The bundle guard found all 16 forbidden
markers absent from the demo and confirmed 15 calibrated markers in the main build.
GitHub Actions runs repository-wide checks and image/smoke rehearsals independently;
the PR checks are the source of truth for their current status.

The combined production demo build was served locally with the existing static
snapshot and checked in headless Chrome at 1440, 390 and 320 px. Checks covered
an older followed-team card and its box score, expanded columns, leader cards,
team comparisons, shooting percentages, sticky player column and scrolling,
outside mouse/touch dismissal, dragging across the popup edge, Escape,
focus restoration and body scroll restoration. There was no page overflow,
browser error, API request or write request.

## Repository and deployment status

At preparation, all five feature PRs were pushed and open. Main still pointed to
#556; opening these PRs did not merge them or deploy the authenticated application.
Use the live PR states and merge commits to determine subsequent integration.

The public Firebase demo had already been manually published and verified earlier
on 2026-11-16. Its hourly Windows task reads files/build artifacts from the primary
checkout; it does not fetch or merge GitHub branches. A live demo therefore cannot
prove that its source has reached main or the authenticated website. Future
deployment reports must identify the target and revision separately from PR status.

The standing workflow is in [AGENTS.md](../AGENTS.md). Functional contracts remain
in [RESULTS.md](RESULTS.md); demo publishing is described in
[DEPLOYMENT.md](DEPLOYMENT.md#17-public-read-only-demo-458).
