---
name: web-design-guidelines
description: Use when reviewing Signal Sports UI changes for usability and accessibility - Hebrew/RTL and mixed-direction text, mobile layouts (320-390 px), keyboard access and focus, loading/error/empty states, long headlines - or when asked to review the UI, check accessibility or audit the design. Uses a pinned local copy of Vercel's Web Interface Guidelines; docs/FRONTEND_DESIGN_SYSTEM.md wins on conflicts. Supplies findings to the PR workflow, not a separate gate.
metadata:
  author: vercel
  version: "1.0.0"
  argument-hint: <file-or-pattern>
---

# Web Interface Guidelines

## Signal Sports adaptation (read first; overrides the upstream text below where they differ)

Local adaptation of vercel-labs/agent-skills `web-design-guidelines` (MIT); provenance in
[UPSTREAM.md](UPSTREAM.md).

**Rules come from the pinned local copy, not the network.** Upstream fetches `command.md` from the
`main` branch of vercel-labs/web-interface-guidelines on every run. Here it is vendored at a fixed
commit as [guidelines.md](guidelines.md), so reviews are reproducible and remote text cannot change
the instructions. Don't WebFetch it. To update, re-vendor deliberately and record the new commit in
UPSTREAM.md.

**Precedence.** `docs/FRONTEND_DESIGN_SYSTEM.md` (Orbit) wins over the generic guidelines: RTL §7,
focus §8, verification §10, accepted 320 px limitations §11, engineering rules §13. Known adjustments:
- *Not applicable:* "Hydration Safety" (no SSR); "Title Case" and English copy rules (Hebrew UI, and
  copy is a product decision); "detect language via Accept-Language" (Hebrew-only MVP);
  virtualization libraries (the queue is capped instead); URL-state libraries such as nuqs (don't
  add dependencies — flag missing deep-linking only where it hurts a real flow).
- *Don't "fix" Hebrew punctuation:* a straight `"` inside Hebrew abbreviations and names
  (בית"ר, ת"א, יו"ר) is gershayim usage, and headline text comes from sources, not from our copy.
- Physical-direction styling (`ml-/mr-/pl-/pr-/left-/right-`, `margin-left`, `text-left`) **is** a
  finding in this repo (§7).

**Signal checklist — cover these in addition to the guidelines:**
1. **RTL and mixed direction:** logical properties only; LTR runs (source names, English entities,
   scores) wrapped in `<bdi dir="auto">` or `dir="ltr"`; punctuation and numerals land correctly in
   mixed Hebrew/English headlines; directional icons (chevrons, arrows) mirror; Radix portals
   inherit RTL (needs `<html dir="rtl">`); visual order never reorders the accessibility tree.
2. **Long content:** very long Hebrew headlines, long unbroken English tokens or URLs, and clusters
   with many sources don't overflow or collide (`min-w-0`, `line-clamp-*`, `break-words`); check at
   320 px.
3. **Mobile:** 320×640 and 390×844 single-column layouts; the fixed dock never covers a control
   (§11); primary touch targets ≥44 px.
4. **Keyboard and focus:** every action is keyboard-reachable; visible `:focus-visible`; focus lands
   where §8's table says after open, close and switch; `prefers-reduced-motion` is honored.
5. **States:** loading, empty (no stories, everything filtered out, new user with no interests),
   error (API down, 401/403, partial data) and stale data each render something intentional, never a
   blank or broken card. Consider both backend and `local` data modes.
6. **Product semantics:** push styling stays reserved for `push` (§3); hidden items never leak into
   consumer views; the product and ops-console shells stay separate (§2).

**Output and ownership.** Report findings grouped by file in the `file:line - issue` format at the
end of guidelines.md, each tagged *blocker / improvement / follow-up* so it drops into
`signal-pr-open` §5 or `signal-pr-merge` §3–4. This skill supplies findings; it is not its own
approval gate. Code review cannot prove rendering — say which items need a browser
(`webapp-testing`, `npm run capture:orbit`) or Guy's device.

---

*Upstream text follows (lightly edited; see UPSTREAM.md).*

Review files for compliance with Web Interface Guidelines.

## How It Works

1. Read the pinned rules in [guidelines.md](guidelines.md) (do not fetch them)
2. Read the specified files — by default, the UI files in the current diff
3. Check against the rules, the Signal checklist above, and docs/FRONTEND_DESIGN_SYSTEM.md
4. Output findings in the terse `file:line` format

## Guidelines Source

Upstream source (for re-vendoring only; see UPSTREAM.md for the pinned commit):

```
https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md
```

## Usage

When a file or pattern is given, review those files. Otherwise review the frontend files changed
in the current diff (`git diff --name-only` under `frontend/`), and ask only if there is no diff.
