# Relevance Visibility Contract — Competition-Aware Matching

Part of **Signal Intelligence Architecture v2** (issue #29, the VISIBILITY
layer, depends on ArticleFacts — see `docs/ARTICLE_FACTS.md`).

Before this issue, the relevance engine matched `league`/`league_group`-scope
topics purely on the legacy `article.league` string — a single field that
conflates explicit article evidence, membership-inferred display convenience,
and simple absence of data. This caused under-matching (a team's non-domestic
competition membership was invisible unless the article happened to name it)
and over-matching (`major_only` mode's importance fallback surfaced any
high-importance article with no real matched scope as `low_feed`).

Location: `backend/app/services/relevance_engine.py` (Python authority),
mirrored in `frontend/src/engine/relevanceEngine.js` (local-mode engine).

## Core contract

Broad competition interest creates visibility; specific entity preference
creates additional boost; nothing surfaces without a matched followed scope.

## Event-reach allowlists (explicit, fail-closed)

```
TEAM_ANCHORED_EVENTS = {
  signing, major_signing, negotiation, candidate, release, injury,
  major_trade, star_trade, major_transfer,
}
COMPETITION_ANCHORED_EVENTS = {
  match_result, regular_season_result, playoff_result, finals_result,
  title_win, schedule, pre_match, generic_preview,
  generic_regular_season_result, friendly_match, final_four,
  major_match_result, match_summary,
}
```

An event type in **neither** set gets no membership-derived reach at all —
it can still match via explicit competition evidence (or the legacy
fallback), just never via "the team also plays in X". This is a positive
allowlist, not `team-anchored = everything else`: a denylist would silently
grant a forgotten future event type cross-competition reach. `interview` is
deliberately in neither set — a generic interview shouldn't spread through
every competition a team happens to belong to.

## Three-tier league/league_group matching

Applies only to `scope in ("league", "league_group")` — entity/sport scopes
are unchanged.

1. **Explicit** — `{primary_competition, *article_competitions}` (ids, from
   ArticleFacts) → `display_en` → intersect with `topic.leagues`. Works for
   *any* event type; the only path a competition-anchored event can match
   through.
2. **Legacy fallback** — only when `taxonomy_version is None` (the article
   predates ArticleFacts): fall back to `article.league ∈ topic.leagues`,
   exactly as before. Every pre-existing seed/mock article has
   `taxonomy_version=None`, so this makes the change 100% backward
   compatible.
3. **Membership-derived reach** — only when `event_type` is in
   `TEAM_ANCHORED_EVENTS` and neither of the above matched.

## entity_ids-first identity (canonical, not display-string)

Both membership reach and entity backing (whether a topic/profile-followed
entity is present, which drives entity_event_rules and exempts a match from
the feed ceiling below) are tiered identically:

- **Post-ArticleFacts rows** (`taxonomy_version is not None`): resolve
  *only* through `entity_ids` — canonical taxonomy ids. This is the
  authoritative, rename-proof path; a changed or emptied legacy `entities`
  display string does not break it.
- **Legacy rows** (`taxonomy_version is None`): fall back to the legacy
  `entities` display strings. Compatibility path only — never merged with
  the canonical path on post-facts rows.

`topic.entities` / `profile.followed_entities` remain legacy-string fields in
today's profile schema (Preference V2 is out of scope here); the *comparison*
against a post-facts article resolves those legacy names to ids via
`entity_by_legacy_name()` before comparing.

The reasoning trace tags a membership match `via_team_membership: comp:<id>`.

## The membership-only feed ceiling ("one tier below explicit")

A topic match via `membership` reach, **when the topic has no independent
entity-level backing**, caps the final decision at `feed` — never
`high_feed`, never `push`. Explicit/legacy matches are never capped. A
membership match *with* an entity hit (e.g. Deni Avdija, Maccabi Tel Aviv
Basketball) is never capped either — that's "entity preference creates
additional boost."

This is a **ceiling, not a decrement**. A flat one-rank subtraction would
turn a Maccabi Ramat Gan signing's `feed` event-rule result into `low_feed`,
contradicting the product contract (Ramat Gan must land `feed`/`high_feed`
via the IBL follow alone, never `low_feed`, never hidden). The ceiling
satisfies every worked example: Ramat Gan signing stays `feed`; a Deni
Avdija trade (entity-backed) still reaches `push` via `entity_event_rules`;
push discipline holds (membership alone can never exceed `feed`, so it can
never manufacture push); `low_feed` still means "matched a real scope, just
a minor story," never "no reason, bottom of the pile."

## sport=unknown handling

On sport abstention (ArticleFacts, #28), `primary_competition` /
`article_competitions` **survive** — they're explicit article-level evidence
and inherently sport-typed, so no extra sport guard is needed for them to
keep driving league-topic visibility. `entities`/`entity_ids` are always
**cleared** on abstention. Net effect, with no special-case code: an
abstained article can still match a league topic via explicit evidence, but
never via membership reach (nothing survives to resolve memberships from).
Conservative and consistent with "abstention is a success mode, not a guess."

## `major_only` mode — the leak is removed, not the mode

`major_only`'s `major_importance_fallback` branch (any high-importance
article with no matching event rule → `low_feed`) is deleted from both
engines. What remains is behaviorally identical to `titles_only`. The mode
name is kept only for backward compatibility with any already-persisted
profile referencing it; no shipped profile uses `major_only` anymore.

## Football profile — one authoritative policy

Applied byte-identical to `backend/app/seed/seed_profiles.py` and
`frontend/src/data/userProfiles.js`:

```
mode: titles_only, leagues: [], entities: []
event_rules: { major_transfer: low_feed, title_win: low_feed }
```

Everything else is hidden (omitted rule + `titles_only` semantics). This is
"an explicit low-interest sport scope gated to genuinely major events" —
neither the old backend all-hidden `titles_only` nor the old frontend
`major_only`-with-leaked-fallback. `euroleague`'s `leagues` is aligned to
`["EuroLeague", "EuroCup"]` on both sides.

## Profile drift guard

`docs/fixtures/profile_parity.json` is the canonical, hand-generated
snapshot of every relevance-driving field (`sport`, `scope`, `priority`,
`mode`, `leagues`, `entities`, `event_rules`, `entity_event_rules`) on every
shipped topic for both profiles (all 7 Guy topics + Casual Deni Fan's `nba`
topic). `backend/tests/test_profile_drift_guard.py` and
`frontend/src/data/userProfiles.drift.test.js` each independently assert
their profile normalizes to this file — either side drifting from it fails
that side's test. This full-coverage comparison (not just the two known
drift points) caught one additional pre-existing drift while building this
issue: `euroleague.schedule` was `low_feed` on backend, `hidden` on frontend;
aligned to backend's `low_feed`.

## Taxonomy sharing: generated artifact, not a hand-maintained JS mirror

`backend/app/taxonomy/` stays the single canonical source. There is no
second, hand-authored JS copy of entity/competition data:

- `backend/app/taxonomy/export.py` (`build_taxonomy_export()`) is the one
  conversion function, canonical-id-first (`entities` keyed by taxonomy id;
  `legacy_name_to_id` is a secondary compatibility index — `legacy_name` is
  never the primary key).
- `backend/scripts/generate_taxonomy_export.py` writes it to
  `frontend/src/data/taxonomyReach.generated.json`. Re-run after any change
  to `backend/app/taxonomy/entities.py` or `competitions.py`:
  ```
  cd backend
  .venv/Scripts/python.exe scripts/generate_taxonomy_export.py
  ```
- `backend/tests/test_taxonomy_export_freshness.py` regenerates the same
  structure in-memory and asserts it deep-equals the committed JSON —
  fails loudly if the registry changed without regenerating.
- `frontend/src/engine/taxonomyReach.js` is a thin, derived lookup layer over
  the generated JSON (no membership data of its own).

## `less_like_this` persistence fix

`FeedbackControls.jsx` emits `less_like_this`, but neither
`AppContext.jsx`'s `BACKEND_VALID_ACTIONS` nor the backend's
`routes_feedback.py` `VALID_ACTIONS` included it — the POST was silently
dropped in backend mode. Added as its own first-class action on both sides
(not remapped to `not_interested` — the product model distinguishes the two
signals). Every feedback action today is inert-but-persisted (no scoring
effect yet — that's #34, feedback learning), so this is a pure
persistence-parity fix, no learning logic involved.

## Known limitations

**Competition-anchored events with no explicit competition evidence can
remain hidden — including from broad competition followers.** Because
competition-anchored events (`match_result`, `regular_season_result`,
`playoff_result`, `finals_result`, `title_win`, `schedule`, …) match *only*
through explicit competition evidence, a game-result story whose competition
is not named in the text — and is only derivable from the participating
teams' taxonomy memberships — gets no reach and is hidden on post-facts rows.

Taxonomy membership alone is **intentionally insufficient** for ordinary
competition-anchored reach: single-team membership is diffuse (a team plays
in all its competitions), so allowing it would let, e.g., a Maccabi
domestic-league game reach a EuroLeague-only follower. That fail-closed
behavior is deliberate and correct as a conservative default, but it
**under-serves broad competition followers for game-result stories** (a
"NBA: all" follower can miss a plain Lakers-vs-Celtics result that never
prints the word "NBA").

The planned fix is **uniqueness-gated participant-set competition inference at
relevance time** (issue #40): for a competition-anchored event, intersect the
*participating* entities' memberships and accept the result **only when it
resolves to exactly one competition** (`Lakers {NBA} ∩ Celtics {NBA} = {NBA}`;
`Maccabi {IBL, EuroLeague} ∩ Real Madrid {ACB, EuroLeague} = {EuroLeague}`).
An **ambiguous or empty intersection must abstain**
(`Maccabi {IBL, EuroLeague} ∩ Hapoel TLV {IBL, EuroLeague}` → abstain), which
reproduces the exact guarantee this contract already enforces. Participant
inference is taxonomy-derived, not text-explicit, so it **must not populate
`primary_competition` or `article_competitions`** (those stay explicit-article
evidence only, per #28); it is a scoring-time computation surfaced in the
reasoning trace, and explicit competition matches always outrank it. See
issue #40 (sequenced after #29, before #32), which also covers the taxonomy
coverage gap that compounds this (most NBA teams are not yet registered, so
the participating entities don't even resolve).

## Non-goals (this issue)

Affinity scoring / Preference Model v2 (#32); learned adjustments;
calibration; any JS-engine feature growth beyond the matching change
described here; redesigning classification (#28/#30's territory) or
`event_certainty` (#30, unrelated to this contract); participant-set
competition inference and taxonomy coverage expansion (#40).
