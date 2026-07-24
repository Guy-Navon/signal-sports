# Signal Sports — Sports Intelligence OS concept exploration

## Status and scope

This document records a visual exploration only. It does not select a winning
direction and it is not a production frontend specification.

The previous **Signal Ledger** direction is rejected and superseded by this
exploration. Its cream/paper palette, serif-led hierarchy, newspaper
composition, print rules, and edition language are not candidates for further
work. Historical artifacts may remain in the repository for traceability, but
they are not design guidance.

The new brief is **Sports Intelligence OS**: a Hebrew-first, RTL-first product
that makes aggregation, clustering, personal rank, explanation, urgency, and
live change feel native to a premium digital system. All three directions use
an obsidian foundation, controlled luminous state, modern Hebrew typography,
opaque layered surfaces, and motion tied to product events.

The concept laboratory is isolated under
`frontend/concepts/sports-intelligence-os/`. It does not import production
components, register a production route, change `frontend/src`, call the
backend, or add a runtime dependency. The existing production UI is untouched.

## Shared content scenario

The three directions deliberately present the same information so that the
comparison is about interaction and visual hierarchy rather than different
data.

The leading cluster is:

> **מכבי ת״א במו״מ מתקדם עם גארד יורוליג**

It develops over a twelve-minute window:

1. `09:02 · ספורט 5 · אות ראשון` —
   `דיווח: מכבי ת״א במו״מ עם גארד יורוליג`.
2. `09:08 · ONE · אימות פרטים` —
   `מכבי ת״א בשלבי משא ומתן עם שחקן מיורוליג`.
3. `09:14 · Sportando · מקור נוסף` —
   `מכבי ת״א בודקת גארד ששיחק ביורוליג העונה`.

The visible explanation is
`התאמה ישירה: מכבי ת״א · משא ומתן מאומת`. When the cluster moves from two
sources to three, its evidence state changes from `מבוסס` to `חזק` and its
feed rank may rise.

All user-facing signal states are qualitative: for example `חדש`, `מתפתח`,
`מבוסס`, and `דחוף`. Source counts and timestamps may remain numeric, but the
concepts do not present confidence, relevance, or signal-strength percentages.
Those percentages resemble betting or prediction language and imply precision
the product cannot responsibly claim.

Supporting stories use realistic material from the existing product fixtures:

- `דני אבדיה עשוי לעבור בעסקת חליפין לקבוצה מהמזרח`
- `שחקן מכבי ת״א יהיה מחוץ לפעילות שלושה שבועות`
- `אולימפיאקוס עולה לחצי הגמר אחרי ניצחון דרמטי`
- `אלקראז זוכה בגראנד סלאם השלישי בקריירה`

This is stable concept data, not a claim that these events are current.

## Direction 1 — Vector Trace / עקבת וקטור

Concept code: **VT-01**.

### Rationale

Vector Trace treats the feed as a directional evidence flow. Every story leaves
a legible trace as sources enter, converge, strengthen its qualitative state,
and change its personal rank. A single forward axis aligns rank, source
convergence, explanation, and time.

Its precision comes from direction, alignment, and change history—not control
panels, gauges, or dense system telemetry. The user reads where a story came
from, what joined it, and where it is moving.

The core visual action is **convergence**: independent reports lock onto one
story, increase its evidence state, and cause a controlled reorder. Geometry is
rectilinear, contrast is high, and every accent denotes an actionable state.

### Desktop personalized feed — 1440px

- A compact top navigation bar contains the Signal mark, the four concept views,
  active scan state, and profile control.
- A narrow RTL direction rail anchors `פיד`, `אותות`, `סיפורים`, and
  `כיוונון`.
- The center is a dense ranked feed. Its introduction says
  `48 דיווחים נסרקו · 12 סיפורים רלוונטיים · 3 אותות התחזקו`, followed
  by direct filters for `הכול`, `מכבי`, `NBA`, and `יורוליג`.
- The lead story is important through a larger trace surface, a directional
  state seam, and visible source convergence. Its
  headline remains compact and scannable rather than becoming a display poster.
- Four supporting stories are aligned as disciplined rows. Topic, time,
  explanation, source, and qualitative state occupy repeatable columns so the
  eye can compare them quickly.
- A slim secondary rail shows `שינויים חיים`: Sportando joining the Maccabi
  cluster, Deni Avdija moving to `חשוב`, and a EuroLeague result
  entering the feed. It is a continuous change trace, not a second content grid.

### Mobile personalized feed — 390px

- Navigation collapses into a floating opaque bottom dock; the active feed
  state remains labeled, not icon-only.
- The lead trace surface becomes one vertical stack: state and topic, title,
  reason, source count, then primary action.
- The directional seam and a plain-language state label replace numeric signal
  strength so they do not compete with the Hebrew headline.
- Supporting rows become compact two-zone cards: story copy on the reading
  edge and source/state at the trailing edge. Nonessential telemetry is
  removed, not shrunk to illegibility.
- Live changes surface as one concise inline update above the affected story.
  The desktop activity rail is not reproduced as a second mobile feed.

### Expanded cluster

The expanded state becomes a precise horizontal event axis. Each source has a
timestamp, source node, state label, headline contribution, and evidence state.
The third source locks into the `09:14` position and is visibly marked as new.

The summary above the axis explains the unified story. A lower decision band
answers two separate questions:

- `למה זה אצלך` — team priority and event relevance.
- `מה השתנה` — the third source changed the evidence state from `מבוסס` to
  `חזק`.

The UI preserves each source as a separate report; convergence does not imply
that the system has invented a new authoritative fact.

### Five-frame source-arrival storyboard

1. **Stable / 0ms** — two source nodes are locked to the event axis; the story
   is labeled `מבוסס`.
2. **Detected / 120ms** — a Sportando node enters 14px from the source edge at
   reduced opacity.
3. **Connect / 280ms** — a restrained trace draws toward the existing
   cluster after entity, event, and time-window overlap are checked; the node
   snaps to the shared trace and the source count changes from two to three.
4. **Strengthen / 460ms** — the seam transitions from amber to mint, the state
   changes to `חזק`, and the explanation updates; only the changed clause is
   highlighted.
5. **Reorder and settle / 720ms** — the story moves to the top using a damped
   layout spring, siblings yield without a viewport jump, and the new-state
   accent decays to rest.

### System rules

**Typography**

- Heebo Variable, weights 430 / 600 / 760.
- Lead title 32px, story title 20px, body/explanation 14px, source/time labels
  11px.
- Tabular numerals for source counts and times; English source names remain
  isolated from Hebrew bidirectional text.

**Color**

- Obsidian `#06090C`
- Carbon `#0E1419`
- Signal Mint `#38D9A0`
- Urgent Amber `#FFB547`
- Ice `#DCE7EC`

Mint denotes verified activity; amber denotes attention. Neither color is used
as sports-outcome language.

**Surface and spacing**

- Three opaque depth levels only, with a quiet 1px border and local shadow under
  the active object.
- 4 / 8 / 12 spacing grid; 12px within a row, 20px between groups, 32px between
  regions.
- Dense information remains separated through alignment and rhythm rather than
  thick rules.

**Iconography and motion**

- Geometric 1.5px line icons; fill and accent color are reserved for active
  state.
- Story arrival 180ms, source connection 220ms, filter response 120ms, and
  feed reorder via a spring around stiffness 260 / damping 30.
- Motion follows the directional convergence axis. No idle scanning effects or decorative
  animation.

## Direction 2 — Orbit Field / שדה מסלולים

### Rationale

Orbit Field turns personal relevance into a calm spatial field. The lead story
is the center of gravity; sources and related context gather around it according
to evidence and recency. The metaphor makes clustering understandable before
the user opens details, while the adjacent queue preserves practical feed
density.

This is the most cinematic and ambient direction. It must remain an
intelligence model—not a decorative network diagram. Position, distance, and
movement always have a stated meaning.

### Desktop personalized feed — 1440px

- The primary area is an asymmetric story field. A compact lead surface sits at
  its center with `אות דחוף`, relevance state, explanation, time, and action.
- Source satellites for Sport 5, ONE, and Sportando occupy stable positions
  around the lead. Their labels state `אות ראשון`, `אימות`, and `חדש`.
- Sparse elliptical guides establish depth without particles or a cyberpunk
  glow field. One low-opacity ambient response belongs to the lead story.
- A dense `במסלול שלך` queue occupies the second column. It contains the same
  supporting stories as the other concepts, with a compact radial signal mark,
  title, reason, and source.
- The composition balances discovery and scanning: one meaningful spatial
  relationship at the center, conventional readable ordering in the queue.

### Mobile personalized feed — 390px

- The lead field becomes a shallow 390px-wide stage rather than attempting to
  preserve the full desktop orbital diagram.
- The central story remains a normal readable surface. Three source satellites
  sit on a single partial arc with text labels outside the tap targets.
- The ranked queue follows immediately beneath the field as a vertical feed.
- Orbit distance is reinforced with labels such as `חדש` and `אימות`; mobile
  comprehension never depends on position alone.
- Navigation uses the shared opaque floating dock. Ambient light remains under
  6% and does not reduce text contrast.

### Expanded cluster

The cluster becomes a dedicated story field. The synthesized story is the
central core. Three source surfaces sit on progressively closer tracks:

- distance from center represents the qualitative degree of corroboration;
- angle represents arrival time;
- a visible connection means the source has passed the cluster relation check;
- the filled new-source marker denotes an unread arrival.

A plain-language caption repeats these semantics. Source surfaces retain their
full title and timestamp, so the field is not the only way to understand the
cluster. The visible change state reads
`+ מקור · מבוסס → חזק · האות התקרב למרכז`.

### Five-frame source-arrival storyboard

1. **Stable field / 0ms** — two sources orbit a core labeled `מבוסס`.
2. **New body / 160ms** — Sportando appears at the outer boundary at 40%
   opacity and a slightly reduced scale.
3. **Trajectory check / 360ms** — a path appears only after entity, event, and
   time overlap are detected.
4. **Lock / 620ms** — the source travels inward and joins the accepted track;
   its text label remains stable, the core changes to `חזק`, and the connection
   becomes solid.
5. **New gravity / 960ms** — the core gains no more than 6% ambient luminance,
   the story advances in the adjacent queue, and all orbital motion stops.

### System rules

**Typography**

- Heebo Variable, weights 420 / 580 / 720.
- Story core 34px, supporting story 19px, explanation 14px, field coordinate
  labels 10px.
- A slightly more generous line height keeps text calm against the spatial
  composition.

**Color**

- Deep Space `#070914`
- Orbit Navy `#111528`
- Mineral Aqua `#7BD7D1`
- Gravity Violet `#8B82E8`
- Warm Alert `#FF8066`

Violet denotes personalized gravity, aqua an accepted connection, and warm
alert an urgent state. Accent is localized to meaningful objects.

**Surface and spacing**

- Content sits on solid navy surfaces; halos live behind important objects and
  never blur the content itself.
- 6 / 12 / 24 spacing grid. The lead field receives generous radial space while
  the ranked queue stays compact.
- Paths use low-contrast 1px strokes. They never become a decorative mesh.

**Iconography and motion**

- Rounded, open 1.4px icons and connection marks; a filled point is reserved for
  an active or newly accepted source.
- Source appearance 160ms, convergence about 460ms, full field transition
  960ms, ambient response capped at 6%.
- Shared-element transition preserves the story core between feed and cluster.
  There is no perpetual orbit.

## Direction 3 — Pulse Stream / זרם דופק

### Rationale

Pulse Stream organizes intelligence as synchronized temporal tracks. Stories
are not a grid of cards; they are events moving through a live stream. Each
source adds a track, each corroboration aligns a beat, and every reorder leaves
a brief legible trace.

This is the most immediate and information-dense direction. Its energy comes
from time and change, not neon decoration. The waveform-like marks are
deterministic source/state summaries, not audio visualization or random
animation.

### Desktop personalized feed — 1440px

- The header establishes a live clock and stream state alongside the four
  concept views and profile.
- The main column begins with `האותות שלך, עכשיו` and a compact count of active
  and changed stories.
- The lead story spans three coordinated zones: current time, a source track
  labeled `מתחזק` with three named sources, and the Hebrew story copy with
  explanation and action.
- Supporting stories sit on a continuous vertical now-line. Each row aligns
  timestamp, signal marker, title/reason, deterministic activity strip, and
  source.
- A narrow side channel reports stream health, meaningful changes, and the
  controlled ambient response. It does not present business KPIs.

### Mobile personalized feed — 390px

- The live clock simplifies to `עכשיו`; seconds are removed to reduce noise.
- Each story becomes a compact temporal row: time, state trace, title, source.
  The reason remains accessible directly beneath the title.
- The lead retains the named source tracks, but their deterministic bars shorten
  rather than wrapping.
- A sticky `NOW` marker helps the user understand where newly arrived stories
  enter. It is not an auto-scrolling ticker.
- Feed reordering preserves the user's reading anchor; nothing moves while the
  user is actively touching or focusing a row.

### Expanded cluster

The cluster opens as a three-channel source mixer against a shared time scale.
Each channel includes source identity, state, arrival marker, qualitative
evidence state, and source headline. At the bottom, a merge channel explains
the relation:

`שלושה מקורות מתארים אותו אירוע · ישות: מכבי ת״א · אירוע:
משא ומתן · חלון זמן: 12 דקות`

The channels remain separate after merging. Their aligned markers communicate
that the reports describe one event, not that their wording or facts are
identical. The story continues to update without a manual page refresh.

### Five-frame source-arrival storyboard

1. **Two synchronized tracks / 0ms** — Sport 5 and ONE align around a story
   labeled `מבוסס`.
2. **Channel opens / 140ms** — a labeled Sportando track appears in an empty
   lane; it does not yet affect the story.
3. **Pattern aligns / 300ms** — entity, event, and time overlap are shown as an
   aligning marker rather than a celebratory pulse.
4. **Merge and strengthen / 520ms** — the third track locks to the shared
   timeline, the source count changes to three, and the unified state changes
   to `חזק`.
5. **Stream reorders / 780ms** — the cluster moves to the first position with a
   damped spring, a short change trace remains, and the bars become static.

### System rules

**Typography**

- Heebo Variable, weights 450 / 620 / 780.
- Lead signal 30px, stream title 18px, explanation 13px, time/state 10px.
- System times may use a mono face; Hebrew narrative text never does.

**Color**

- Black Current `#050707`
- Track `#121716`
- Pulse Lime `#B9E769`
- Urgent Coral `#FF5F57`
- Time Gray `#87918D`

Lime identifies synchronized live state; coral is reserved for genuine
attention. The palette does not borrow sportsbook green/red outcome language.

**Surface and spacing**

- Most stories are separated by tracks and rhythm rather than containers. A
  full opaque surface is reserved for the active lead story.
- 5 / 10 / 20 spacing cadence: tight within a track, doubled between temporal
  groups.
- Deterministic bars have fixed seeded shapes. They do not animate endlessly.

**Iconography and motion**

- Linear markers for pulse, time, cluster, tuning, and direction. Every icon is
  attached to an action or timestamp; none is decorative.
- Channel opening 140ms, alignment 220ms, merge complete by 520ms, final reorder
  via spring.
- Refresh adds a temporary time marker; filter changes collapse removed tracks
  and use layout animation for the remaining order.

## Direction comparison

| Dimension | Vector Trace | Orbit Field | Pulse Stream |
| --- | --- | --- | --- |
| Primary metaphor | Direction and convergence | Relevance and gravity | Time and synchronization |
| Desktop structure | Direction rail + ranked trace + change relay | Central field + dense adjacent queue | Temporal main stream + change channel |
| Leading-story emphasis | Directional state seam and source trace | Story core with contextual satellites | Active multi-source track |
| Cluster explanation | Exact event axis | Distance, angle, and accepted paths | Parallel source channels on one time scale |
| Motion character | Fast, restrained, mechanical | Calm, spatial, cinematic | Rhythmic, immediate, event-driven |
| Mobile strength | Highest scan efficiency | Most distinctive focus moment | Clearest sense of live change |
| Primary risk to test | Could feel operational if copy becomes too technical | Spatial semantics could overwhelm small screens | Track density could become visually noisy |
| Best fit if the product should feel like… | A clear, directional evidence flow | A personal relevance environment | A continuously updating live system |

The concepts are intentionally not skins of one layout. Their primary
information structures—axis, field, and stream—remain different on desktop,
mobile, cluster, and motion views.

## Running the concept laboratory

Run the existing Vite development server from the repository root:

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1 --port 5194
```

Then open
`http://127.0.0.1:5194/concepts/sports-intelligence-os/`.

The explorer uses query parameters rather than production routes:

| Parameter | Values | Default | Purpose |
| --- | --- | --- | --- |
| `concept` | `vector`, `orbit`, `pulse` | `vector` | Selects the art direction. |
| `view` | `feed`, `cluster`, `motion`, `system` | `feed` | Selects the concept artifact. |
| `capture` | `1` or omitted | omitted | Removes the laboratory switcher for clean evidence. |

Examples:

- `/concepts/sports-intelligence-os/?concept=vector&view=feed`
- `/concepts/sports-intelligence-os/?concept=orbit&view=cluster`
- `/concepts/sports-intelligence-os/?concept=pulse&view=motion&capture=1`

The mobile feed uses the same `view=feed` URL at a 390px viewport; it is not a
separate static mock or route.

## Screenshot evidence contract

Evidence belongs in `docs/frontend-concepts/sports-intelligence-os/`. Desktop
captures use a 1440px viewport width; mobile captures use 390px. Capture URLs
should include `capture=1`, use a device scale factor of 1, wait for fonts and
layout to settle, and contain no browser or laboratory chrome.

### Vector Trace

- [Desktop personalized feed](./frontend-concepts/sports-intelligence-os/vector-feed-desktop-1440.png)
- [Mobile personalized feed](./frontend-concepts/sports-intelligence-os/vector-feed-mobile-390.png)
- [Expanded cluster](./frontend-concepts/sports-intelligence-os/vector-cluster-expanded-1440.png)
- [Source-arrival storyboard](./frontend-concepts/sports-intelligence-os/vector-motion-storyboard-1440.png)
- [System rules](./frontend-concepts/sports-intelligence-os/vector-system-rules-1440.png)

### Orbit Field

- [Desktop personalized feed](./frontend-concepts/sports-intelligence-os/orbit-feed-desktop-1440.png)
- [Mobile personalized feed](./frontend-concepts/sports-intelligence-os/orbit-feed-mobile-390.png)
- [Expanded cluster](./frontend-concepts/sports-intelligence-os/orbit-cluster-expanded-1440.png)
- [Source-arrival storyboard](./frontend-concepts/sports-intelligence-os/orbit-motion-storyboard-1440.png)
- [System rules](./frontend-concepts/sports-intelligence-os/orbit-system-rules-1440.png)

### Pulse Stream

- [Desktop personalized feed](./frontend-concepts/sports-intelligence-os/pulse-feed-desktop-1440.png)
- [Mobile personalized feed](./frontend-concepts/sports-intelligence-os/pulse-feed-mobile-390.png)
- [Expanded cluster](./frontend-concepts/sports-intelligence-os/pulse-cluster-expanded-1440.png)
- [Source-arrival storyboard](./frontend-concepts/sports-intelligence-os/pulse-motion-storyboard-1440.png)
- [System rules](./frontend-concepts/sports-intelligence-os/pulse-system-rules-1440.png)

These 15 files are the complete expected review set. The system-rules captures
hold the typography, color, surface, spacing, iconography, and motion references
for each direction.

### Automated capture and visual review

Regenerate the complete evidence set from `frontend/` with:

```powershell
npm run capture:concepts
```

The dependency-free Node 22 harness starts an isolated Vite server, drives the
locally installed Chrome over the DevTools Protocol, waits for Heebo and the
concept shell to settle, captures at device scale factor 1, and fails on
horizontal overflow or a non-RTL document. It uses deterministic local concept
fixtures only; no screenshot calls the backend or production ranking.

Exact viewports are:

- desktop feed, expanded cluster, storyboard, and system rules: `1440 × 1000`;
- mobile feed: `390 × 844`.

All 15 final captures were opened and visually inspected after the last
regeneration. The review checked Hebrew wrapping, RTL order, feed density,
desktop/mobile visibility, dock overlap, font loading, contrast, cluster
legibility, and clipped content.

The review found and fixed:

- a Windows-specific shell launch failure in the first capture harness pass;
- a temporary Chrome Crashpad lock that could incorrectly fail cleanup after a
  successful run;
- a logical-positioning error that placed the mobile dock partly off-canvas;
- system-rule grids whose motion panels fell below the 1000px evidence frame;
- an over-broad mobile selector that hid the Pulse profile icon;
- numeric importance/confidence treatments that felt too close to betting or
  generic analytics;
- a decorative Vector radar that weakened the evidence-trace rationale.

### Validation record

- `npm run capture:concepts` — passed; 15/15 exact-size screenshots, DPR 1,
  RTL confirmed, no horizontal overflow.
- `npm run lint` — passed.
- `npm test -- --run` — passed; 23 files and 423 tests.
- `npm run build` — passed; the existing production bundle warning above
  500kB remains unchanged.
- `npm run typecheck` — reports exactly 11 errors on this concept branch and
  exactly the same 11 errors on `main`; the error-set delta is zero. The errors
  are confined to untouched `frontend/src` files (`ImportMeta.env`, ops
  component prop names, and existing API/context shape errors). No typed source
  or TypeScript configuration file differs from `main`.

## Accessibility and reduced motion

The concept phase must not defer basic accessibility:

- The document is `lang="he"` and `dir="rtl"`. Layout uses logical reading
  order; visual positioning must not reorder the accessibility tree.
- Hebrew headlines and explanations remain real text. English source names and
  numbers are isolated so mixed-direction lines remain intelligible.
- Text and essential controls target WCAG AA contrast. Ambient light sits behind
  opaque surfaces and never replaces contrast.
- Color, distance, a waveform, or a strength segment is never the sole state
  carrier. Every important state has a text equivalent such as `מקור חדש`,
  `אימות`, `מתחזק`, a timestamp, and source count.
- Interactive targets are at least 44×44px on touch screens. Focus indication
  must be visible against every surface; hover is never required to reveal
  essential information.
- Live arrivals use a polite announcement such as
  `מקור נוסף הצטרף לסיפור מכבי תל אביב`. Feed reordering is not repeatedly
  announced as separate noise.
- Source order and cluster evidence remain available as a linear list even in
  Orbit Field. The spatial field is an enhancement, not the only explanation.

For `prefers-reduced-motion: reduce`:

- Vector removes node travel and spring reordering; qualitative state labels
  update directly with a short opacity transition and focus remains anchored.
- Orbit removes path interpolation, scale, and ambient change; the accepted
  source appears at its final position with its textual state.
- Pulse freezes waveform bars, removes channel sweep, and inserts the new
  timestamped row directly.
- Shared across all concepts, looping animation stops, transitions stay under
  120ms, and no information is lost when motion is absent.

## Decision boundary

The review should select or combine principles only after evaluating all 15
captures at real desktop and mobile widths. Any later production phase must
translate the chosen direction into the existing application architecture,
real data states, keyboard behavior, performance budgets, and automated tests.
Nothing in this visual laboratory authorizes replacing the production
frontend.
