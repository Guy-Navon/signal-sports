# Upstream provenance — `llm-evaluation`

| | |
|---|---|
| Upstream repository | [wshobson/agents](https://github.com/wshobson/agents) |
| Upstream path | `plugins/llm-application-dev/skills/llm-evaluation` |
| Commit | `044b4b21f083948e69ec878a7b07c8d0951a6ffa` (2026-10-15) |
| Tree hash of the path at that commit | `e22e2e6a15c1851f7dfba1a8cef13b2a3963d819` |
| Imported | 2026-10-17 |
| Local location | `.claude/skills/llm-evaluation/` |

**Files included:** `SKILL.md`, `references/details.md` (unmodified)

**Not imported:** —

## License

MIT — Copyright (c) 2024 Seth Hobson. Full text in [LICENSE](LICENSE).

## Local modifications

- Added a **Signal Sports adaptation** section after the title (it takes precedence over the upstream text where they differ) and replaced the frontmatter `description` with narrower, project-specific triggers. The description deliberately routes Signal Sports evaluations to `signal-quality-eval`.

Reproduce the exact diff: `git clone https://github.com/wshobson/agents`, check out `044b4b21f083948e69ec878a7b07c8d0951a6ffa`, and compare `plugins/llm-application-dev/skills/llm-evaluation` with this
directory.

## Dependencies and bundled scripts

None (examples import numpy, bert-score, LangSmith; not used here).
