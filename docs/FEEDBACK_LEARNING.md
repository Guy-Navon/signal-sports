# Feedback Learning (issue #34)

**Status: ACTIVE.** Feedback events now drive bounded, explainable, derived
preference adjustments. Nothing here mutates the stored profile row —
learned state is recomputed from the event log at read time.

## The pipeline

1. **Click-time context.** `POST /api/feedback` scores the article with the
   same effective (learned-augmented) v2 profile the feed used and stores
   `{decision, matched_scope, event_type, attribution}` on the event
   (`feedback_events.context`, soft migration). Attribution is read off the
   contribution trace — never rebuilt from titles later.
2. **Most-diagnostic-feature attribution.** An entity that backed the
   decision (entity base scope or entity boost) → attribute to that
   team/player. Otherwise → the (matched scope, event_type) pair, i.e. the
   scoped event affinity: three interview-downvotes in the NBA lower
   NBA-interview affinity — not the NBA, not global interviews.
3. **Pure derivation** (`app/services/learning_service.py`): learned
   adjustments are a pure function of the non-retracted event log —
   activation at |decayed net| ≥ 3 consistent events per feature; magnitude
   cap ±1 level/delta (entity levels move ±1 from the highest-authority
   non-learned base); 90-day half-life decay; learned scope levels floor at
   -1 (**learning never creates an exclude**; broad suppression is never
   inferred). `article_opened` is logged (passive slot) but is NEVER
   evidence.
4. **Signal hierarchy** (SOURCE_AUTHORITY, enforced by the scorer):
   **explicit > learned > calibration** — learned refines calibration but
   never overrides an explicit follow; explicit mutes/overrides beat
   everything.
5. **Immediate dismissal.** `less_like_this` / `not_interested` /
   `never_show` hide THAT article from the feed at once (per-article
   effect, not a profile change; Debug still shows it).
6. **Scoped never_show** (`POST /api/profiles/{user_id}/never_show`): the
   only feedback flow that creates an EXPLICIT override — targeted at the
   most specific scope on the article (team/player entity → entity rule;
   else event-in-competition; else event-in-sport). The UI popover offers
   "פחות כאלה" (learned negative) vs "אל תראה לי יותר" (this endpoint).
7. **Undo.** `POST /api/learning/{user_id}/reset` tombstones the events
   behind one feature (or all learning); the log stays append-only and
   derivation restores prior state exactly.

## Surfaces

- `GET /api/learning/{user_id}` — derived adjustments + Hebrew explanations,
  including inactive features' progress toward the threshold.
- Preferences page → "נלמד" tab: active adjustments with per-row reset,
  accumulating features below.
- Feed/Debug scoring runs on the learned-augmented profile copy
  (`with_learned`), so the Debug trace shows learned contributions.

## Safety invariants (all regression-tested)

- One less_like_this changes nothing durable.
- Scoped attribution: event feedback adjusts (scope, event), entity
  feedback adjusts the entity — never the whole sport/competition.
- Cap ±1; learned floor -1; threshold ≥3 net consistent; mixed signals
  cancel; stale evidence decays out (~90-day half-life).
- Explicit follow survives repeated learned negatives; hard mute beats
  learned positives.
- Retraction restores prior state exactly.
