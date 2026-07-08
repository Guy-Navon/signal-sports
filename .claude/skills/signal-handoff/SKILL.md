---
name: signal-handoff
description: Use to produce a handoff note for the next Claude Code session, or for handing off to a different tool (e.g. Codex), on Signal Sports — with no assumed conversation history. Triggers on requests like "write a handoff", "summarize for the next session", "prep this for Codex". Not a pre-commit quality gate — use signal-pr-finish for that.
---

The output must stand on its own for an agent with zero prior context — no "as discussed above",
no assuming the reader saw this conversation.

## Produce, from actually inspecting current repo state (not memory)

1. `git status`, `git branch --show-current`, `git log --oneline -15`, and `git diff` for any uncommitted work.
2. **Task goal** — what this session was asked to do.
3. **Completed work** — files/components materially changed (`git diff --stat` against `main` or the prior commit), described in terms of behavior, not a file list dump.
4. **Tests executed and results** — re-run them if the current state is at all unclear; never quote suite counts from docs (they drift — see `signal-doc-truth`), only counts from runs this session.
5. **Key technical/product decisions made** — anything a fresh agent would otherwise re-litigate. Standing decisions the next agent must not "helpfully" reverse: the JS relevance engine is frozen (no v2/taxonomy/learning ports); backend is authoritative for intelligence; LLM optionality (`CLASSIFICATION_PROVIDER=disabled` is first-class); push only via explicit overrides; facts → visibility → preference → learning layer boundaries.
6. **Relevant runtime state** — which engine serves the feed (`GET /api/feed-engine`; `PREFERENCE_ENGINE` env), provider settings in `backend/.env`, and whether the real DB corpus (`backend/data/signal_sports.db`) was modified this session (ingestion, backfill, feedback clicks — these affect future QA diffs; see `signal-real-data-qa`).
7. **Unresolved issues and known risks.**
8. **Remaining work and the recommended next action** — cross-check against `docs/CURRENT_PROJECT_STATE.md` §11 and `docs/INTELLIGENCE_ROADMAP.md` (the v2 milestone is complete; #36 async enrichment stays deferred behind a measured trigger): is the priority order still accurate after this session?
9. **Exact docs to read first** — always `docs/CURRENT_PROJECT_STATE.md` and `docs/RELEVANCE_CONTRACT.md` (the umbrella pipeline map); add the layer contract(s) for whatever this session touched. Warn about historical docs per the topology in `signal-doc-truth` (`IMPLEMENTATION_AUDIT.md`, `CALIBRATION_V0.md`/`CALIBRATION_APPLY.md` are not current state).
10. **Commands to reproduce/verify current state** — exact run/test commands (backend uvicorn + pytest, frontend `npm run dev`/`test`/`build`, data mode setup), not "see the README".

## Format

Clearly separate **Verified** (you ran it or read the file this session) from **Suggested**
(inferred, not directly confirmed) — label each bullet or section accordingly. Don't blur the two.

This produces a note to show the user or save wherever they ask; it does not itself rewrite
`docs/CURRENT_PROJECT_STATE.md` unless the user explicitly asks for that.
