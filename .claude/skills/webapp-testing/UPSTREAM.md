# Upstream provenance — `webapp-testing`

| | |
|---|---|
| Upstream repository | [anthropics/skills](https://github.com/anthropics/skills) |
| Upstream path | `skills/webapp-testing` |
| Commit | `dbd4588f9e1033efb41dad4bef2f7947c8993d44` (2026-10-09) |
| Tree hash of the path at that commit | `5ffb7dc66b9fd4c25c3e400a4c00da99a349b714` |
| Imported | 2026-10-17 |
| Local location | `.claude/skills/webapp-testing/` |

**Files included:** `SKILL.md`, `scripts/with_server.py`, `examples/{console_logging,element_discovery,static_html_automation}.py`, `LICENSE.txt` (only `SKILL.md` modified)

**Not imported:** —

## License

Apache License 2.0 — full text in [LICENSE.txt](LICENSE.txt). Per §4(b), `SKILL.md` carries a notice that it was modified; all other files are unmodified.

## Local modifications

- Added a **Signal Sports adaptation** section after the title (it takes precedence over the upstream text where they differ) and replaced the frontmatter `description` with narrower, project-specific triggers. The adaptation makes the existing `npm run capture:orbit` harness the first choice and keeps Playwright out of the repo's dependencies.

Reproduce the exact diff: `git clone https://github.com/anthropics/skills`, check out `dbd4588f9e1033efb41dad4bef2f7947c8993d44`, and compare `skills/webapp-testing` with this
directory.

## Dependencies and bundled scripts

Playwright for Python is **not** installed by this repo. `scripts/with_server.py` was read before installation: it starts each `--server` command with `subprocess.Popen(shell=True)`, polls the port, runs the given command and terminates the servers. On Windows, terminating the shell may leave the Node child running (documented in the adaptation). The examples use `/tmp` and `/mnt/user-data` paths that must be replaced with scratchpad paths.
