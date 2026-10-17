# Upstream provenance — `vercel-react-best-practices`

| | |
|---|---|
| Upstream repository | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) |
| Upstream path | `skills/react-best-practices` |
| Commit | `063bee94c3f4df8453406c830b0a7df0f2860278` (2026-08-28) |
| Tree hash of the path at that commit | `343db72180d05814949fef7d46be96b5c6ee86b3` |
| Imported | 2026-10-17 |
| Local location | `.claude/skills/vercel-react-best-practices/` |

**Files included:** `SKILL.md`, `metadata.json`, `rules/*.md` (all 70 rules plus `_sections.md` and `_template.md`, unmodified)

**Not imported:** `AGENTS.md` (a build output concatenating `rules/`; a nested `AGENTS.md` can also be mistaken for directory instructions by other agents) and `README.md` (contributor notes for the rule build tooling). The `.zip` bundle and the `packages/react-best-practices-build` tooling were not imported.

## License

MIT, as declared by upstream in its README (`## License` → `MIT`) and in the skill's own frontmatter (`license: MIT`). At this
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

- Added a **Signal Sports adaptation** section after the title (it takes precedence over the upstream text where they differ) and replaced the frontmatter `description` with narrower, project-specific triggers. The directory name matches the frontmatter `name` (`vercel-react-best-practices`), which differs from the upstream directory `react-best-practices`.
- The "Full Compiled Document" section now explains why `AGENTS.md` is not vendored.

Reproduce the exact diff: `git clone https://github.com/vercel-labs/agent-skills`, check out `063bee94c3f4df8453406c830b0a7df0f2860278`, and compare `skills/react-best-practices` with this
directory.

## Dependencies and bundled scripts

None. The adaptation maps SWR → TanStack Query, `next/dynamic` → `React.lazy`, and marks server/RSC/hydration and React-19-only rules as not applicable.
