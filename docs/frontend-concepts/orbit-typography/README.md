# Orbit typography — product-only display serif

Frank Ruhl Libre returns as a **display face on consumer product surfaces only**.
Captures are the real application (`VITE_DATA_MODE=backend`) against the real
corpus, RTL Hebrew, with `document.fonts.ready` awaited before every measurement
and screenshot so a pending download can never be mistaken for a fallback.

Capture conditions are unchanged from the earlier scopes:
`FEED_FRESHNESS_ENABLED=false` and `ALLOW_INSECURE_AUTH_BYPASS=true`, both
process-level, no file changed.

## Where the serif applies — and where it must not

| surface | face |
|---|---|
| Orbit feed H1 (`.orbit-feed-heading h1`) | **Frank Ruhl Libre 500** |
| focused story headline (`.orbit-core h2`) | **Frank Ruhl Libre 500** |
| expanded cluster central headline (`.orbit-cluster__core h3`) | **Frank Ruhl Libre 500** |
| consumer feed empty-state heading (`.orbit-feed-empty h2`) | **Frank Ruhl Libre 500** |
| queue story titles, level labels, filters | Heebo |
| body copy, DeskVoice, metadata, timestamps, source names | Heebo |
| buttons, controls, navigation | Heebo |
| expanded cluster *section* heading and source cards | Heebo |
| Auth, Ops / Debug / LLM-QA, Results, Preferences, account, 404, PageHeader | Heebo |

## Scoping

`--font-display` is **unchanged** — still the Heebo stack in `:root`. That token
is what Ops, Auth, 404 and `PageHeader` use, so leaving it alone is what keeps
those surfaces untouched.

The serif lives in its own token, `--orbit-serif`, declared on
`.orbit-feed-view` — the consumer feed container. Only four rules consume it,
each targeting a specific element. There is no global `h1`/`h2`/`h3` rule and no
`.font-display` override, so nothing can pull the face onto another route.

Only **weight 500** is imported. `@fontsource/frank-ruhl-libre/500.css` carries
each subset gated by `unicode-range`, so the Hebrew face is the only one fetched
for Hebrew copy; the built bundle contains exactly:

```
frank-ruhl-libre-hebrew-500-normal.woff2
frank-ruhl-libre-latin-500-normal.woff2
frank-ruhl-libre-latin-ext-500-normal.woff2
```

The dependency is retained, as required.

## Hebrew tuning

Frank Ruhl Libre carries more vertical detail than Heebo, so the sans's tight
tracking closes its counters. Tracking was relaxed and leading opened slightly.
**Type sizes are unchanged** — this is a metric adjustment, not shrinking to hide
the swap.

| surface | before | after |
|---|---|---|
| feed H1 | Heebo 650, `-0.035em`, lh 1.15 | Frank Ruhl Libre 500, `-0.012em`, lh 1.22 |
| core headline | Heebo 650, `-0.035em`, lh 1.16 | Frank Ruhl Libre 500, `-0.012em`, lh 1.24 |
| expanded core | Heebo 640, `-0.03em`, lh 1.2 | Frank Ruhl Libre 500, `-0.01em`, lh 1.26 |
| core headline ≤767px | lh 1.19 | lh 1.21 |

Weight 500 rather than a bolder cut: on the near-black canvas a heavier serif
reads ornamental, which is the opposite of the intent. The sans/serif split is
what carries the editorial identity — not weight.

## No new overflow

Longest real headline in the corpus (71 chars) at 1440:

| | before | after |
|---|---|---|
| lines | 3 | 3 |
| core height | 377 px | 385 px |
| clearance inside field | 142 px | 138 px |

Headline clamps are unchanged.

## Verification

The hermetic CDP harness asserts **computed** font families, not source CSS,
under both reduced and normal motion. Every asserted element must exist — a
missing element fails rather than skipping, so a pass cannot be vacuous.

- three serif surfaces resolve to Frank Ruhl Libre;
- eight consumer sans surfaces resolve to Heebo (queue headline, level label,
  filter chip, core metadata, DeskVoice, primary action, navigation, queue
  heading), plus the expanded view's section heading, source cards and close
  control;
- `/debug`, `/results`, `/preferences` and `/no-such-route` each render their
  heading in Heebo and contain **zero** elements computing to the serif;
- `--font-display` is asserted to still resolve to the sans stack on every one
  of those routes.

A redirect now fails the audit explicitly: `/login` and `/account` bounce to `/`
in local mode, where the feed's serif H1 would otherwise have been measured and
reported as a leak. That guard caught exactly that during this work.

**Two coverage gaps, stated rather than papered over:**

- **Auth** (`/login`, `/signup`) is unreachable in the harness by design —
  `main.jsx` redirects those routes away in local/bypass mode, which is the mode
  the harness runs for hermeticity. Auth's headings use the `font-display`
  Tailwind utility, the same mechanism `PageNotFound` uses, so `/no-such-route`
  exercises that exact code path, and every audited route additionally asserts
  `--font-display` is still sans.
- **The consumer feed empty state** (`EditionEmptyState`) renders only when zero
  items are visible, which the real corpus cannot produce. The rule is in place
  and scoped, but it is not asserted in the browser. `07-consumer-empty-state`
  captures the reachable filter-empty state, whose body copy correctly stays sans.

## Index

| state | before | after |
|---|---|---|
| Desktop, single-source field | `before/01-desktop-solo-field.png` | `after/01-desktop-solo-field.png` |
| Desktop, 3-source field | `before/02-desktop-3-source-field.png` | `after/02-desktop-3-source-field.png` |
| Expanded 4-source field | `before/03-expanded-4-source-field.png` | `after/03-expanded-4-source-field.png` |
| Mobile 390 | `before/04-mobile-390.png` | `after/04-mobile-390.png` |
| Mobile 320 | `before/05-mobile-320.png` | `after/05-mobile-320.png` |
| Long Hebrew headline | `before/06-long-headline.png` | `after/06-long-headline.png` |
| Consumer empty state | `before/07-consumer-empty-state.png` | `after/07-consumer-empty-state.png` |
| Ops (Debug) — no leakage | `before/08-ops-debug.png` | `after/08-ops-debug.png` |

Raw computed-family measurements for both runs are in `before/fonts.json` and
`after/fonts.json`.
