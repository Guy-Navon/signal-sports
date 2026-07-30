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

## Bottom navigation — verified, not changed

Measured rather than assumed. The fixed dock covers **no** queue content or
control at 320 or 390, including the short-content case where the dock cannot be
scrolled away:

| viewport | last card bottom | dock top | clearance | covered |
|---|---|---|---|---|
| 390 × 844 | 703 px | 777 px | 74 px | 0 |
| 320 × 640 | 499 px | 573 px | 74 px | 0 |
| 390 × 2200 (filtered short) | 2051 px | 2133 px | 82 px | 0 |
| 320 × 2200 (filtered short) | 2051 px | 2133 px | 82 px | 0 |

The existing `pb-28` on the product shell is sufficient. No change was made, and
this scope did not regress it. Evidence: `after/06-dock-390-normal.png`,
`after/06-dock-320-normal.png`.

## Preserved

Keyboard navigation and reduced motion are asserted by the capture harness on
every run: focus moves to the core on focus, to the close control on expand, and
is restored on collapse — under both motion preferences. Reduced motion at 390
renders identically to normal motion
(`after/05-mobile-390-reduced-motion.png`).

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
