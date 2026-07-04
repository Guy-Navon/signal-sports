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
4. **Tests executed and results** — re-run them if the current state is at all unclear; do not assume the pass counts in `docs/CURRENT_PROJECT_STATE.md` still hold if backend/frontend code changed this session.
5. **Key technical/product decisions made** — anything a fresh agent would otherwise re-litigate.
6. **Unresolved issues and known risks.**
7. **Remaining work and the recommended next action** — cross-check against `docs/CURRENT_PROJECT_STATE.md` §11 ("Recommended Next Steps"): is the top item still accurate, or did this session change the priority order?
8. **Exact docs to read first** — always `docs/CURRENT_PROJECT_STATE.md`; add the specific doc(s) for whatever area this session touched. Explicitly note: do not treat `docs/IMPLEMENTATION_AUDIT.md` as current state — it is a marked historical snapshot from before the backend and frontend redesign existed.
9. **Commands to reproduce/verify current state** — the exact run/test commands needed (backend uvicorn + pytest, frontend `npm run dev`/`test`/`build`), not "see the README".

## Format

Clearly separate **Verified** (you ran it or read the file this session) from **Suggested**
(inferred, not directly confirmed) — label each bullet or section accordingly. Don't blur the two.

This produces a note to show the user or save wherever they ask; it does not itself rewrite
`docs/CURRENT_PROJECT_STATE.md` unless the user explicitly asks for that.
