# Upstream provenance — `web-design-guidelines`

| | |
|---|---|
| Upstream repository | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) |
| Upstream path | `skills/web-design-guidelines` |
| Commit | `063bee94c3f4df8453406c830b0a7df0f2860278` (2026-08-28) |
| Tree hash of the path at that commit | `3116f3e62dbd02b44a598b1aa690d2a8938e8f89` |
| Imported | 2026-10-17 |
| Local location | `.claude/skills/web-design-guidelines/` |

**Files included:** `SKILL.md`; plus `guidelines.md` = `command.md` from [vercel-labs/web-interface-guidelines](https://github.com/vercel-labs/web-interface-guidelines) at commit `434b7f91364665f2f733b310ec54809bf8f37937` (2026-10-05, blob `3eb3a212b7b89493922ea418489d4c6f67ae8bd5`), unmodified; its MIT license (Copyright (c) 2025 Vercel Labs) is in `LICENSE-web-interface-guidelines`.

**Not imported:** —

## License

MIT, as declared by upstream in its README (`## License` → `MIT`). At this
commit the upstream repository ships no LICENSE file and no copyright line, so there is no copyright
notice to reproduce; the material is attributed to Vercel (vercel-labs/agent-skills). The standard
MIT permission notice, under which it is used:

> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
> associated documentation files (the "Software"), to deal in the Software without restriction,
> including without limitation the rights to use, copy, modify, merge, publish, distribute,
> sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions: The above copyright notice and this
> permission notice shall be included in all copies or substantial portions of the Software.
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
> NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
> NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
> OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
> CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Local modifications

- Added a **Signal Sports adaptation** section after the title (it takes precedence over the upstream text where they differ) and replaced the frontmatter `description` with narrower, project-specific triggers.
- **Pinned rules instead of a runtime fetch.** Upstream tells the agent to WebFetch `command.md` from the `main` branch on every review. That makes reviews non-reproducible and lets remote text change agent instructions, so the file is vendored as `guidelines.md`, and "How It Works", "Guidelines Source" and "Usage" were rewritten to read it locally. To update: re-vendor deliberately and record the new commit here.

Reproduce the exact diff: `git clone https://github.com/vercel-labs/agent-skills`, check out `063bee94c3f4df8453406c830b0a7df0f2860278`, and compare `skills/web-design-guidelines` with this
directory.

## Dependencies and bundled scripts

`guidelines.md` (vendored).
