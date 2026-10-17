# Upstream provenance — `differential-review`

| | |
|---|---|
| Upstream repository | [trailofbits/skills](https://github.com/trailofbits/skills) |
| Upstream path | `plugins/differential-review/skills/differential-review` |
| Commit | `5c99c03fb8a9ea568432ecbcba5d86e9f4ac2bf0` (2026-10-15) |
| Tree hash of the path at that commit | `09ff02c96f84ad4b98184bcd5efae5b218caa910` |
| Imported | 2026-10-17 |
| Local location | `.claude/skills/differential-review/` |

**Files included:** `SKILL.md`, `methodology.md`, `adversarial.md`, `reporting.md`, `patterns.md` (only `SKILL.md` modified)

**Not imported:** `agents/openai.yaml` and `assets/trail-of-bits-mark.svg` (Codex UI metadata and its icon); from the plugin: `.claude-plugin/plugin.json`, `commands/diff-review.md` (a slash-command wrapper) and `agents/adversarial-modeler.md` (the subagent — Phase 5 is done inline from `adversarial.md` instead).

## License

**CC BY-SA 4.0** (Creative Commons Attribution-ShareAlike 4.0 International) — full text in [LICENSE](LICENSE) (canonical: https://creativecommons.org/licenses/by-sa/4.0/). Original work: "differential-review" by Omar Inuwa / [Trail of Bits](https://www.trailofbits.com/), from https://github.com/trailofbits/skills/tree/5c99c03fb8a9ea568432ecbcba5d86e9f4ac2bf0/plugins/differential-review. **This is an adapted version**; the changes are listed below. Under the ShareAlike term, the adapted files in this directory (`SKILL.md`, `methodology.md`, `adversarial.md`, `reporting.md`, `patterns.md`) are distributed under CC BY-SA 4.0. `signal-security-patterns.md` is original Signal Sports content, not derived from the upstream material. No warranties are given (see the license's disclaimer).

## Local modifications

- Added a **Signal Sports adaptation** section after the title (it takes precedence over the upstream text where they differ) and replaced the frontmatter `description` with narrower, project-specific triggers. The adaptation adds repo-specific risk triggers and routes findings into `signal-pr-open` / `signal-pr-merge` instead of a separate gate.
- Removed `allowed-tools: Read Write Grep Glob Bash` from the frontmatter, so the skill does not pre-approve unrestricted Bash and Write for itself.
- Replaced references to the uninstalled `differential-review:adversarial-modeler` agent and the `audit-context-building` / `issue-writer` skills with manual equivalents; reworded "always generate a report file" (principle 5, checklist, tips) to "record findings" — a report file in the scratchpad only for HIGH-risk reviews (also the "I'll explain verbally" rationalization row); the decision tree lost its agent branch.
- Added `signal-security-patterns.md` (original content).

Reproduce the exact diff: `git clone https://github.com/trailofbits/skills`, check out `5c99c03fb8a9ea568432ecbcba5d86e9f4ac2bf0`, and compare `plugins/differential-review/skills/differential-review` with this
directory.

## Dependencies and bundled scripts

None remaining. `audit-context-building`, `issue-writer` and the adversarial-modeler agent are intentionally not installed.
