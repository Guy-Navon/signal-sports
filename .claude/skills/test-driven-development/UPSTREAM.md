# Upstream provenance — `test-driven-development`

| | |
|---|---|
| Upstream repository | [obra/superpowers](https://github.com/obra/superpowers) |
| Upstream path | `skills/test-driven-development` |
| Commit | `bb92a77741419a4ab5f06e711a283343f1ada0c3` (2026-10-09) |
| Tree hash of the path at that commit | `847144cf0824095922c0d4875648b9fa74877e1a` |
| Imported | 2026-10-17 |
| Local location | `.claude/skills/test-driven-development/` |

**Files included:** `SKILL.md`, `writing-good-tests.md`

**Not imported:** —

## License

MIT — Copyright (c) 2025 Jesse Vincent. Full text in [LICENSE](LICENSE).

## Local modifications

- Added a **Signal Sports adaptation** section after the title (it takes precedence over the upstream text where they differ) and replaced the frontmatter `description` with narrower, project-specific triggers.
- Rewrote the contradictory absolute rules so the file has one consistent policy: the "When to Use" list now points to the adaptation's conditional scope; "Write code before the test? Delete it" became "prove the test against the pre-change behavior" (matching `signal-pr-open` §6); the Red Flags conclusion, the checklist item "Every new function/method has a test" (→ "Every new behavior that matters"), the checklist footer and the Final Rule were reworded accordingly. In "Common Rationalizations" the two delete-the-code rows were replaced with prove-the-red-step rows, "Existing code has no tests" now limits new tests to the changed behavior, and two Red Flags were replaced to match.
- `writing-good-tests.md`: noted that `superpowers:writing-skills` is not installed.

Reproduce the exact diff: `git clone https://github.com/obra/superpowers`, check out `bb92a77741419a4ab5f06e711a283343f1ada0c3`, and compare `skills/test-driven-development` with this
directory.

## Dependencies and bundled scripts

`writing-good-tests.md` is bundled. The reference to `superpowers:writing-skills` is left as a pointer; that skill is deliberately not installed.
