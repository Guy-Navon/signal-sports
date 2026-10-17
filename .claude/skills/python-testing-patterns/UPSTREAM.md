# Upstream provenance — `python-testing-patterns`

| | |
|---|---|
| Upstream repository | [wshobson/agents](https://github.com/wshobson/agents) |
| Upstream path | `plugins/python-development/skills/python-testing-patterns` |
| Commit | `044b4b21f083948e69ec878a7b07c8d0951a6ffa` (2026-10-15) |
| Tree hash of the path at that commit | `87259b0b73d75b3500405c1224fdda5b3263d308` |
| Imported | 2026-10-17 |
| Local location | `.claude/skills/python-testing-patterns/` |

**Files included:** `SKILL.md`, `references/details.md`, `references/advanced-patterns.md` (unmodified)

**Not imported:** —

## License

MIT — Copyright (c) 2024 Seth Hobson. Full text in [LICENSE](LICENSE).

## Local modifications

- Added a **Signal Sports adaptation** section after the title (it takes precedence over the upstream text where they differ) and replaced the frontmatter `description` with narrower, project-specific triggers.

Reproduce the exact diff: `git clone https://github.com/wshobson/agents`, check out `044b4b21f083948e69ec878a7b07c8d0951a6ffa`, and compare `plugins/python-development/skills/python-testing-patterns` with this
directory.

## Dependencies and bundled scripts

None. Examples use freezegun, pytest-cov, hypothesis and pytest-asyncio; the adaptation says not to add them.
