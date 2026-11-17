# Archived docs

Historical documents kept for context. **None of these describe current behavior.** For what
is true now, start at [../CURRENT_PROJECT_STATE.md](../CURRENT_PROJECT_STATE.md) and the active
contracts listed in [../README.md](../README.md).

Files keep their original names; a file that lived in a subdirectory of `docs/` keeps that
relative path under `archive/`. Links inside them were rewritten to resolve from here. Their
statements are as of the date in the file name or header, and may name branches, open issues,
runtime state or plans that have since changed.

| File | What it is | Archived because |
|---|---|---|
| [CURRENT_PROJECT_STATE_2026-11-16.md](CURRENT_PROJECT_STATE_2026-11-16.md) | The long-form state document as of 2026-11-16, including the milestone-13 planning narrative and status table, the per-flag runtime table and the detailed `ui/next` frontend notes | Replaced on 2026-11-17 by a shorter, verified cold-start doc; its §0 and §3 had drifted (dated 2026-10-12, Ollama in the diagram) |
| [FEATURE_DELIVERY_2026-11-16.md](FEATURE_DELIVERY_2026-11-16.md) | Record of how the results/demo changes were split into PRs #557–#561 and merged | A one-off delivery record; the standing workflow is in [../../AGENTS.md](../../AGENTS.md) |
| [frontend-concepts/orbit/](frontend-concepts/orbit/README.md) | Screenshots and verification data of the Orbit consumer UI (2026-07-31) | Orbit was superseded by the Signal UI (milestone 15) and its code removed in #473 |

## Kept in place elsewhere (historical, but not moved)

Some historical material stays at its original path because code, tests or scripts read it, or
because source comments cite it by path:

- [`../audits/2026-09-05.md`](../audits/2026-09-05.md) (+ `.html`, `.json`, `.csv`, screenshots):
  the September 2026 repository audit. `scripts/generate_audit_report.py` writes there. The
  current audit is [`../../AUDIT_REPORT.md`](../../AUDIT_REPORT.md).
- `../qa/`: dated QA reports and the owner-rating evidence (census, N05, bake-off, week sample).
  Tests and retention protection read the rating files there; **never move or delete them**.
- [`../HOSTING_PLAN.md`](../HOSTING_PLAN.md): a dated proposal (v3.1, 2026-10-13) that is still
  awaiting the owner's decisions (#267), so it remains active.

Documents retired before 2026-11-17 (for example `IMPLEMENTATION_AUDIT.md`, `CALIBRATION_V0.md`,
the closed-milestone QA reports) were deleted and live only in git history:
`git log --diff-filter=D --name-only -- docs/`.
