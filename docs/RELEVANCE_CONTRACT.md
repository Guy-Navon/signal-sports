# Relevance Contract — Decision-Level Semantics (issue #35)

The umbrella contract for how an article becomes a feed decision. Layer
detail lives in the per-layer docs; this file is the map.

## The pipeline

```
RAW ITEM (RSS)
  → deterministic classification (classifier.py: sport/league/event/entities)
  → LLM gate (gating.py: call only on residual ambiguity; CLASSIFICATION_PROVIDER=disabled is first-class)
  → merge + guardrails (merge.py)
  → ArticleFacts validation (facts.py: evidence-weighted sport, explicit
    competitions, canonical entity_ids, conflicts, full trace persisted)     [docs/ARTICLE_FACTS.md]
  → event semantic validation (event_evidence.py; corrected → news)
  → PERSISTED ARTICLE (facts + classification_trace)
  → visibility matching (four-tier competition matching, entity_ids-first)   [docs/RELEVANCE_VISIBILITY_CONTRACT.md]
  → preference scoring (ProfileV2 affinity layers, contribution trace)       [docs/PREFERENCE_MODEL_V2.md]
  → learned adjustments (derived from feedback events at read time)          [docs/FEEDBACK_LEARNING.md]
  → DECISION: hidden | low_feed | feed | high_feed | push
```

## Decision semantics

- `hidden` — no legitimate relevance scope matched, an exclude/override
  fired, or the score fell to 0. Visible only in Debug.
- `low_feed` — matched a real scope, minor story. NEVER "no reason, bottom
  of the pile" (the importance-fallback leak was removed in #29; in v2 a
  base-0 scope surfaces only through event deltas).
- `feed` — normal relevance for a followed scope.
- `high_feed` — elevated: very-high affinity base, entity boost, positive
  event delta or very_high importance *within* existing visibility.
- `push` — ONLY via explicit `always_push` overrides (exact event match).
  No boost, delta, importance or learned adjustment can produce push.

## Reach rules (visibility layer)

Four-tier competition matching (issues #29 + #40), single implementation in
`relevance_engine.match_competition_names()` consumed by BOTH the legacy
topic engine and the v2 scorer:

1. explicit competition evidence (`primary_competition`/`article_competitions`)
2. legacy `article.league` string — pre-ArticleFacts rows only
3. participant-set inference — competition-anchored events (not
   `friendly_match`), ≥2 team entities, singleton membership intersection;
   fail-closed by shape; never persisted
4. team-membership reach — team-anchored events only; capped at `feed`
   without entity backing

Identity is entity_ids-first everywhere; legacy display strings are a
compatibility path for pre-taxonomy rows only. sport=unknown articles can
match only via explicit evidence (entities are cleared on abstention).

## Push discipline

Push requires an explicit rule: legacy `event_rules`/`entity_event_rules`
declaring push, or a v2 `always_push` override. Boosts cap at high_feed.
Calibration and learning can never write push rules. Measured on the real
feed (Fable checkpoint): 13 pushes for Guy, 2 for the Deni fan, identical
across both engines.

## Signal hierarchy (learning layer)

explicit > learned > calibration > (passive — future, no effect today).
Hard mutes/never_show overrides beat everything. Learned adjustments:
threshold ≥3 net consistent events, cap ±1, 90-day half-life, floor -1.

## Observability

Every decision must be explainable without reading code:

- **ArticleFacts trace** (persisted `classification_trace`): sport evidence
  chips, explicit/dropped competitions, alias→id normalization, rejected
  LLM mentions, gate decision + reason, LLM proposal, event validation
  (incl. `corrected`), conflicts — rendered in Debug (FactsTracePanel).
- **Personalization trace**: v2 contribution chain
  `{step, scope, effect, detail}` incl. `scopes_considered` (rejected
  scopes); Hebrew reasoning lines; engine badge (`v2`/`legacy`/`js-local`)
  on every Debug row.
- **Shadow comparison**: `GET /api/debug/shadow/{user_id}`.
- **Learning**: `GET /api/learning/{user_id}` explains every learned
  adjustment and its evidence.
- **LLM dependency**: per-run persisted metrics (`docs/LLM_CLASSIFICATION.md`,
  issue #31) — normal gated ingestion only, never forced backfill.

The consumer product surface keeps only the one-line desk voice; full
traces stay in Debug/ops.
