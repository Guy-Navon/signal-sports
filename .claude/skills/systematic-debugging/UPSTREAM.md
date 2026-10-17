# Upstream provenance — `systematic-debugging`

| | |
|---|---|
| Upstream repository | [obra/superpowers](https://github.com/obra/superpowers) |
| Upstream path | `skills/systematic-debugging` |
| Commit | `bb92a77741419a4ab5f06e711a283343f1ada0c3` (2026-10-09) |
| Tree hash of the path at that commit | `108961c080a6837ad8a188a553e593cc5e6df62d` |
| Imported | 2026-10-17 |
| Local location | `.claude/skills/systematic-debugging/` |

**Files included:** `SKILL.md`, `root-cause-tracing.md`, `defense-in-depth.md`, `condition-based-waiting.md`, `condition-based-waiting-example.ts`, `find-polluter.sh` (unmodified except `SKILL.md`)

**Not imported:** `CREATION-LOG.md`, `test-academic.md`, `test-pressure-{1,2,3}.md` — authoring and pressure-test material for developing the skill, not used at runtime.

## License

MIT — Copyright (c) 2025 Jesse Vincent. Full text in [LICENSE](LICENSE).

## Local modifications

- Added a **Signal Sports adaptation** section after the title (it takes precedence over the upstream text where they differ) and replaced the frontmatter `description` with narrower, project-specific triggers.
- `superpowers:test-driven-development` / `superpowers:verification-before-completion` references now point to the local skills of the same name.

Reproduce the exact diff: `git clone https://github.com/obra/superpowers`, check out `bb92a77741419a4ab5f06e711a283343f1ada0c3`, and compare `skills/systematic-debugging` with this
directory.

## Dependencies and bundled scripts

Refers to `test-driven-development` and `verification-before-completion` (both installed here). `find-polluter.sh` was read before installation: it loops over test files running `npm test <file>` and checks for a pollution path; it makes no network calls and writes nothing itself.
