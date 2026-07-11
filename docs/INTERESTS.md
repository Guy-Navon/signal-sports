# Explicit Interests — Preference Acquisition Contract (issue #77)

The authoritative contract for how a user explicitly declares WHAT they
follow. First layer of the approved model:

```
EXPLICIT INTEREST SELECTION → CALIBRATION → CONTINUOUS LEARNING
```

Explicit interests are deterministic and taxonomy-backed. No LLM is involved
at any point: a selected sport / competition / team / player is a canonical
taxonomy id, not an interpretation.

## Where interests live

Explicit interests are **ordinary ProfileV2 entries** with
`source="explicit"` (`backend/app/models/profile_v2.py`). There is no
parallel preference system:

- a follow = a `ScopeAffinity(source="explicit", level ≥ 0)`
- a global event preference = an `EventAffinity(scope_ref=None,
  source="explicit", delta=±1)`

They flow through the existing scoring pipeline untouched
(`preference_engine.score_article_v2`), compose with calibration and
learning through the existing source-authority rules
(explicit > learned > calibration, same-target), and are protected by the
decision-contract locks (`backend/tests/test_decision_contract.py`, #79).

## Follow / Star semantics — tier → level mapping

Two user-facing gestures, kind-sensitive levels ("broad scopes stay quiet,
narrow scopes get loud"):

| Scope kind        | Follow | Star ("אל תפספס לי") |
|-------------------|--------|-----------------------|
| sport             | 0      | +1                    |
| competition       | +1     | +2                    |
| team / player     | +1     | +2                    |

Decision rationale (checkpoint 1, measured behavior — see
`TestBroadSportFollow` in `test_decision_contract.py`):

- **Sport Follow = level 0**: broad coverage at `low_feed`, with
  very_high-importance stories lifting to `feed` and low-importance filler
  dropping out. This is "coverage, not noise" — the product's core promise.
  Sport Follow = +1 would put every routine article in the sport at `feed`.
- **Star = one step up**, uniformly. A starred sport is a deliberate
  "this sport is a top interest" (feed for everything).
- Competition/team Follow at +1 (`feed`) and Star at +2 (`high_feed` base)
  reproduce exactly the shape of the seed profiles (Guy's comps at +1,
  Maccabi at +2), which are the living proof of the target archetypes.

Not following = hidden (`no_matching_scope`), by design. Onboarding creates
no negative levels: −1 (low) and −2 (exclude) remain calibration /
future-preferences tools.

**Push is out of scope**: onboarding and the interests surface never create
`always_push` overrides. Starred interests top out at `high_feed`. Push
configuration is a future notifications capability.

## Global event preferences — product presets

The user can set ~5 grouped event preferences, each `less | normal | more`.
**Groups are product presets that expand server-side into existing
`EventAffinity` entries over the canonical event-type taxonomy.** They are
NOT new event types and must not collapse, alias, or replace the underlying
taxonomy.

| Preset group          | Expands to event types                                        |
|-----------------------|---------------------------------------------------------------|
| `transfers_rumors`    | signing, negotiation, candidate, release, major_trade         |
| `injuries`            | injury                                                        |
| `results`             | match_result, playoff_result, finals_result, title_win, grand_slam_winner |
| `interviews_features` | interview                                                     |
| `schedules_previews`  | schedule, pre_match, generic_preview                          |

Mapping: `less` → delta −1, `more` → delta +1, `normal` → no entry. Each
expanded entry is a **global** (`scope_ref=None`) explicit `EventAffinity`.
The engine's alias map (`_EVENT_ALIASES`) extends coverage to variants
(major_signing, star_trade, regular_season_result, …) at match time.

Precedence (locked in #79 and documented in `docs/RELEVANCE_CONTRACT.md`):

1. **Specificity**: a *scoped* event entry for the base scope beats a
   *global* one — even a scoped **calibration** entry refines a global
   **explicit** preset. Scoped nuance is calibration's job; the presets are
   broad gestures.
2. **Authority**: for the same `(scope_ref, event_type)` target,
   explicit > learned > calibration.

## Managed explicit subset — PUT replacement semantics

`PUT /api/me/interests` is a **full replace of exactly the subset this
surface manages**, and nothing else:

**Managed (replaced on every PUT):**
- `ScopeAffinity` entries with `source="explicit"` and `level ≥ 0`
  (the Follow/Star space)
- `EventAffinity` entries with `source="explicit"` and `scope_ref=None`
  (the global presets)

**Never touched (must survive every PUT byte-for-byte):**
- calibration-sourced scope/event entries
- learned-sourced scope/event entries
- **scoped** explicit event affinities (`scope_ref != None`) — seed
  profiles and future advanced editing own these
- explicit scope affinities with **negative levels** (−1 low / −2 exclude)
  — not expressible as Follow/Star, so not managed by this surface
  (seed-profile nuance like Guy's `comp:acb −1` survives)
- overrides of any kind (mute / never_show / always_push)
- legacy `muted_topics` / `muted_sources` / `topics`

Validation: every target id must exist in the taxonomy AND be selectable
per the shared policy (`backend/app/taxonomy/policy.py`); the tier→level
mapping is applied server-side; request bodies are `extra="forbid"` (an
injected `user_id` is a 422, never silently ignored).

## Selectable policy (shared with the catalog, #78)

Defined once in `backend/app/taxonomy/policy.py`, consumed by both the
interests validation and the catalog endpoint:

- **Sports**: basketball, football, tennis — selectable.
- **Competitions**: selectable except the ones the classifier cannot prove
  (zero member clubs + `ALLOWED_LEAGUES` gap): `comp:epl`, `comp:la_liga`,
  `comp:bundesliga`, `comp:ucl`. Tennis Grand Slams ARE selectable
  competition-only (tier-1 explicit competition evidence matches any event
  type; no tennis entities needed).
- **Entities**: every taxonomy team/player/coach is selectable
  ("abstention beats guessing" — if it's in the taxonomy, the classifier
  can prove it).

**No implicit parents**: following a team never creates its sport or
competition follow. Parent scopes may be *suggested* by the UI, never
auto-created (archetype B — Hapoel TLV bb + IBL without broad basketball —
depends on this).

## Interest-stage process state

`users.interests_completed_at` (nullable ISO string, soft migration) is
**explicit process state, separate from preference data**:

| State | `interests_completed_at` | `onboarding_completed_at` | Behavior |
|---|---|---|---|
| never reached          | NULL | NULL | funnel routes to interest selection |
| completed w/ selections| set  | any  | ACTIVE-ward; interests editable in Preferences |
| intentionally skipped  | set  | any  | same — stamp survives, zero follows is valid |
| selections later removed | set | any | no re-funnel; empty-feed CTA |
| **legacy user**        | NULL | set  | **treated as complete, never re-funneled**; interests reachable via Preferences |

Effective completion: `interests_completed_at IS NOT NULL OR
onboarding_completed_at IS NOT NULL`. `PUT /api/me/interests` stamps
completion idempotently (declaring interests completes the stage);
`POST /api/me/interests/complete` is the explicit skip path.

## API

### `GET /api/me/interests` (require_user)

```json
{
  "follows": [
    {"scope": "sport", "target_id": "basketball", "starred": false},
    {"scope": "competition", "target_id": "comp:euroleague", "starred": false},
    {"scope": "team", "target_id": "team:maccabi_tlv_bb", "starred": true}
  ],
  "event_preferences": {"transfers_rumors": "more", "schedules_previews": "less"},
  "completed": true,
  "selected": 3
}
```

`follows` reflects the managed explicit subset only. `event_preferences`
includes only non-`normal` groups whose expansion matches the stored global
explicit deltas.

### `PUT /api/me/interests` (require_user)

Body: `{"follows": [...], "event_preferences": {...}}` (`extra="forbid"`).
Replaces the managed subset per the semantics above, stamps
`interests_completed_at` (idempotent), returns the GET shape. 422 on
unknown/non-selectable targets, duplicate targets, or unknown preset
groups/states.

### `POST /api/me/interests/complete` (require_user)

Explicit skip: stamps `interests_completed_at` (idempotent) without writing
any preference data. Returns `{"completed": true, "selected": n}`.

### Session bootstrap

`GET /api/auth/session` → `onboarding.interests = {"completed": bool,
"selected": n}` (drives the frontend state machine's
`SELECTING_INTERESTS` stage).

## Invariants

- explicit interests are ordinary ProfileV2 data — the scoring engine is
  unchanged (frozen; #79 locks)
- no cross-user state: identity from the session only, `/api/me/*` pattern
- demo profiles (guy / casual_deni_fan) are permanent fixtures; the drift
  guard remains authoritative — editing them through this surface trips it
  by design
- persistence survives logout/login/restart (profile row + users columns)
- corpus DB discipline: all schema changes are additive nullable columns
