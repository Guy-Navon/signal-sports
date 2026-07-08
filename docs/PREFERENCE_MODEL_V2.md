# Preference Model V2 — Affinity Scorer (issue #32)

**Status: ACTIVE.** `GET /api/feed` is served by the v2 engine since
2026-07-08 (post-shadow-checkpoint flip). Rollback path:
`PREFERENCE_ENGINE=legacy` env var — the legacy topic engine remains fully
functional and tested. The JS engine (`frontend/src/engine/relevanceEngine.js`)
is **frozen** at its pre-v2 feature set (local/demo mode only) and receives
no port, by explicit architecture decision.

## The model (`app/models/profile_v2.py`)

`ProfileV2` is a JSON payload on the profiles row (`profile_v2` column, soft
migration), coexisting with legacy `topics`:

- **`scope_affinities`** — graded interest per scope:
  `{scope: sport|competition|team|player, target_id, level, source,
  evidence_count, updated_at}`. Levels: exclude(-2), low(-1), medium(0),
  high(+1), very_high(+2). Targets are canonical taxonomy ids (`comp:*`,
  `team:*`, `player:*`/`coach:*`) or bare sport names — validated.
- **`event_affinities`** — `{scope_ref|null, event_type, delta -2..+2}`.
  A scoped entry beats the global one; event aliases are honored.
- **`overrides`** — `{kind: mute|never_show|always_push, scope, target_id,
  event_type?}`. Explicit-only. **Exact event match — no alias widening**
  (shadow analysis caught the alias map turning NBA `major_trade` into a
  `star_trade` push).

**Provenance contract:** for a duplicate (scope, target), explicit beats
calibration beats learned — a learned entry never overrides an explicit one
(`effective_scope_affinities()`).

## The scorer (`app/services/preference_engine.py`)

Layered, monotonic by construction; every step emits a structured
contribution `{step, scope, effect, detail}` plus a Hebrew reasoning line:

1. **Hard constraints** — disabled/muted sources, legacy muted_topics,
   `mute`/`never_show` overrides. Absolute.
2. **Base visibility** — best matching followed scope. Matching **reuses the
   visibility layer** instead of re-deriving it: competition scopes call
   `relevance_engine.match_competition_names()` (the four-tier #29/#40
   machinery — explicit / legacy / participant_inference / membership, same
   match_kind vocabulary); team/player scopes use the entity_ids-first
   identity contract (with the sport-compatibility guard); sport scopes use
   `article.sport`. Base points: very_high→3, high→2, medium→1, low→0.
   **Max points win** (adding an affinity can never lower a decision); ties
   break toward the broader scope so a followed entity inside a followed
   broad scope reads as base + boost. An **exclude** hides unless a strictly
   more specific matched affinity is non-exclude (team follow beats sport
   exclude; team exclude beats competition follow).
3. **Entity boost** — +1 when base came from a competition/sport scope and a
   followed (level ≥ +1) team/player is on the article.
4. **Event delta** — scoped-then-global lookup, aliases honored.
5. **Importance** — very_high **+1 only when score ≥ 1** (importance
   modulates within legitimate visibility, it never creates it — without
   this gate every very_high World Cup story leaked to low_feed through
   Guy's low-interest football scope); low/very_low −1.
6. **Membership ceiling** — a base matched via diffuse `membership` reach
   with no followed-entity backing caps at feed (legacy #29 parity);
   `participant_inference` and `explicit` are never capped.
7. **Threshold** — ≤0 hidden, 1 low_feed, 2 feed, ≥3 high_feed.
8. **always_push overrides** — **the only path to push**. Fire when the
   target matches the article and nothing above hid it. No boost, delta, or
   importance combination can reach push.

`matched_topic` on v2 results is the **canonical scope id**
(`team:maccabi_tlv_bb`, `comp:euroleague`), not the legacy topic_id — three
old API tests were updated accordingly at the flip.

## Surfaces

- `GET /api/debug/shadow/{user_id}` — both engines score every article;
  returns agreement summary + per-article traces for disagreements.
- `GET /api/feed-engine` — which engine serves the feed.
- `PUT /api/profiles/{user_id}` — the first profile mutation endpoint;
  pydantic validation (levels, target/scope shape, override kinds), path
  user_id authoritative.
- Debug page → "מנוע v2 (shadow)" tab (backend mode) renders the report.
- Seed profiles carry v2 payloads; pre-existing DBs are backfilled on
  startup only when `profile_v2` is NULL (a user-edited profile is never
  overwritten).

## Shadow checkpoint (Fable review, 2026-07-08 — pre-flip)

Real local DB, 241 articles, both demo profiles, after two seed-tuning
iterations driven by the disagreement list:

| Profile | Agreement | Promoted | Demoted | Push legacy/v2 |
|---|---|---|---|---|
| guy | 232/241 (96.3%) | 6 | 3 | 13 / 13 |
| casual_deni_fan | 241/241 (100%) | 0 | 0 | 2 / 2 |

Issues found by the analysis and fixed before the flip:
1. very_high importance created visibility at base-0 scopes (~45 World
   Cup/Wimbledon leaks) → importance gate (layer 5).
2. Maccabi `news` articles rode the very-high base to high_feed (~15) →
   `news` −1 scoped delta in the seed.
3. Event-alias widening let `major_trade` fire the `star_trade` push
   override (2 false pushes) → overrides match exact event types only.

Remaining 9 disagreements — accepted, each explainable:
- 5 promotions low_feed→feed: very_high-importance football `title_win`
  stories (real World Cup titles surface at feed per the product text;
  several are classifier `title_win` false positives — classification
  faults, not preference faults).
- 3 demotions low_feed→hidden: a low-importance Maccabi friendly and two
  low-importance `schedule` items — noise the product wants gone.
- Push discipline: exact parity, both profiles.

## Known deliberate divergences from legacy

- ACB/BSL/Greek/LBA/LNB articles with no matching major-event delta are
  hidden regardless of importance fallback (legacy `high_importance_only`
  gave medium-importance leftovers low_feed) — more selective, per product.
- A Deni signing-type article is visible for the Deni fan (legacy
  `signing: hidden` rule hid it) — judged a legacy bug.
- Low-importance friendlies/schedule items can drop to hidden (legacy
  pinned low_feed).

## Non-goals delivered elsewhere

Calibration inference produces v2 affinities in #33; feedback learning
mutates `source="learned"` entries in #34 (never overriding explicit);
observability wrap-up in #35.
