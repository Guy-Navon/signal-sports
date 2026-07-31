# Orbit B3 + B4 — the single-source field, and mobile field resilience

Second improvement scope on the Orbit feed. Captures are the real application
(`VITE_DATA_MODE=backend`) against the real corpus — 198 stories in Guy's feed,
RTL Hebrew. `before/` predates this scope; `after/` is the same state once done.

Capture conditions are unchanged from
[`../orbit-b1-b2/`](../orbit-b1-b2/README.md): `FEED_FRESHNESS_ENABLED=false`
(the corpus is older than the 36h window) and `ALLOW_INSECURE_AUTH_BYPASS=true`
(the documented local-only bypass), both process-level, no file changed.

## The single-source field is now a primary state

About **95% of real feed items carry exactly one source** — 41 clusters in a
1,356-article corpus, and only 11 inside a 36-hour window. The field was
nevertheless composed for clusters, so the dominant state rendered as a
multi-source layout with its satellites missing: one lone chip in a large empty
ellipse, repeating the source name the core's own meta line already showed.

`OrbitStoryField` now marks these `orbit-field--solo` and composes for them:

| | before | after |
|---|---|---|
| desktop field height | 680 px | **560 px** |
| satellites rendered | 1 (redundant) | **0** |
| composition | core off-centre, chip top-left | core and signal meter on **one vertical axis** |
| mobile 390 field height | 443 px | **399 px** |

Multi-source fields are untouched — `after/02-desktop-multisource-field.png`
shows the 3-source field with its satellites, geometry and 680 px height
identical to before. The expanded 4-source field is not modified at all.

## Mobile shows relevance again

`.orbit-field__strength` was `display: none` below 767 px, so the one element
that encodes relevance visually — rather than in words — was absent on mobile
entirely. (The Phase A note called this clipping by `overflow: hidden`; it was
an explicit `display: none`.)

The desktop meter is an absolutely-positioned circle that cannot survive the
narrow field, so on mobile it becomes a horizontal chip in normal flow beneath
the core. `strengthVisible` measures `false` → **`true`** at both 390 and 320.

## Mixed RTL/LTR truncation no longer splits tokens

The DeskVoice reason line used `truncate` — `white-space: nowrap` plus an
ellipsis, which cuts at whatever character lands on the boundary. In this
mixed-direction string that sliced the LTR run mid-token and rendered
`(negotiation)` as `egotiation)`.

It is now a one-line clamp, so the text wraps first and the break lands between
tokens: `white-space` `nowrap` → **`normal`**, `-webkit-line-clamp` `none` →
**`1`**. The line now ends `…חוק push מפורש:` with a clean ellipsis.

## Bottom navigation

### Queue content — verified, not changed

The fixed dock covers no queue content or control at 320 or 390, including the
short-content case where it cannot be scrolled away:

| viewport | last card bottom | dock top | clearance | covered |
|---|---|---|---|---|
| 390 × 844 | 703 px | 777 px | 74 px | 0 |
| 320 × 640 | 499 px | 573 px | 74 px | 0 |
| 390 × 2200 (filtered short) | 2051 px | 2133 px | 82 px | 0 |
| 320 × 2200 (filtered short) | 2051 px | 2133 px | 82 px | 0 |

The existing `pb-28` on the product shell is sufficient. Evidence:
`after/06-dock-390-normal.png`, `after/06-dock-320-normal.png`.

### The core's primary action — fixed

A horizontal-bounds check could not see this, and the first pass of this scope
wrongly reported "no controls covered". `elementFromPoint` across the real
interaction sequence found that at **320 the primary action rested partially
under the dock**: the button spanned y 557–601 with the dock starting at 573, so
**28 of its 44 px were covered**, leaving roughly a 16 px tap target. It stayed
*reachable* only because its top edge protruded, and scrolling cleared it fully.

Fixed with spacing alone — `.orbit-field--solo .orbit-field__compact`
`padding-top` 62 px → 26 px, with the absolutely-positioned caption brought up to
match. Nothing was hidden and the field was not redesigned.

| viewport | action at rest | dock top | clearance |
|---|---|---|---|
| 390 × 844 | 481–525 px | 777 px | 252 px |
| 320 × 640 | 521–565 px | 573 px | **8 px** |

Worst case measured too: focusing the longest headline in the corpus (68 chars)
leaves 245 px of clearance at 320, because focusing a story scrolls the field
into view. The tight 8 px case is specific to the at-rest first paint.

`assertDockOcclusion` in the capture harness now fails if the primary action is
covered by the dock at rest, so the 8 px margin cannot silently erode.

### Known residuals at 320 × 640

Reported rather than forced, because fixing either would mean redesigning the
field rather than adjusting spacing:

- The restored signal chip sits at y 599–633 with the dock at 573–634, so at
  **320 it is behind the dock at rest** and needs a small scroll. It is fully
  visible at rest at 390 (556–590, dock at 777). At 320 × 640 there is simply not
  enough height for core, action and chip above the dock.
- The field caption renders only its first half (`הסיפור שמוביל כרגע`, without
  `דיווח אחד`) at 320. This is **pre-existing** — identical in the `before/`
  capture — and is not a regression from this scope.

## Preserved

Keyboard navigation and reduced motion are asserted by the capture harness on
every run: focus moves to the core on focus, to the close control on expand, and
is restored on collapse — under both motion preferences. Reduced motion at 390
renders identically to normal motion
(`after/05-mobile-390-reduced-motion.png`).

## The capture harness is now hermetic

A harness run in this scope "passed" while testing a **different application**: a
leftover backend-mode server owned the fixed port 5199, `--strictPort` made the
harness's own Vite exit, and the foreign server kept answering 200 — which the
readiness poll accepted. It reported 197 backend stories as if they were the 47
local ones.

Four changes, in `scripts/capture-orbit-production.mjs`:

- **No fixed port.** The harness reserves a free ephemeral port from the OS. An
  explicitly requested `ORBIT_REVIEW_PORT` is preflighted and refused if taken.
- **Vite output is captured.** Both stdout and stderr are collected and included
  in every failure, so a bind error explains itself instead of becoming a
  silent timeout.
- **A 200 is never readiness on its own.** The spawned process must still be
  alive when the response arrives; a 200 from a dead child is reported as coming
  from another server.
- **Ownership is proven in the page.** Local mode never calls the backend, so the
  resource timeline is a behavioural fingerprint a shared codebase cannot fake —
  any request whose *path* starts with `/api/` means this is a backend-mode
  instance, and the run aborts. (Matching the substring rather than the path is
  wrong: Vite serves the app's own modules from `/src/api/…`.)

`scripts/capture-orbit-production.test.mjs` locks this with 8 tests, including
the regression itself: a real HTTP server is bound to a port, and the harness
must **reject** it rather than proceed. Verified end-to-end as well — running
against an occupied 5199 now exits 1 with
`Port 5199 is already in use, so this harness cannot own it.`

## Two cascade bugs caught by measuring, not reading

Both were valid-looking CSS that silently lost the cascade, and neither would
have been caught by config-level tests:

1. `.orbit-field--solo .orbit-core` is `(0,2,0)` and **beat** the mobile
   `.orbit-core` reset, dragging the core back into desktop absolute positioning
   and pushing it off-screen at 390 px. Fixed by restating the reset at matching
   specificity inside the mobile query.
2. `.orbit-field--solo` height ties with `.orbit-field` inside the ≤1199 px
   query, which is declared later and would win. Fixed by restating the solo
   height inside that query.

This is the same failure family as the B1 type-scale collapse, which is why the
capture harness now asserts *rendered* computed styles.

## Index

| state | before | after |
|---|---|---|
| Desktop, single-source field | `before/01-desktop-solo-field.png` | `after/01-desktop-solo-field.png` |
| Desktop, 3-source field (preserved) | `before/02-desktop-multisource-field.png` | `after/02-desktop-multisource-field.png` |
| Mobile 390 field | `before/03-mobile-390-field.png` | `after/03-mobile-390-field.png` |
| Mobile 320 field | `before/03-mobile-320-field.png` | `after/03-mobile-320-field.png` |
| Reduced motion, 390 | `before/05-mobile-390-reduced-motion.png` | `after/05-mobile-390-reduced-motion.png` |
| Dock clearance 390 | — | `after/06-dock-390-normal.png` |
| Dock clearance 320 | — | `after/06-dock-320-normal.png` |
