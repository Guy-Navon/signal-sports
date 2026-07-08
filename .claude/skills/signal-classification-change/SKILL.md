---
name: signal-classification-change
description: Use when changing how Signal Sports determines what an article IS — entity detection, sport/league inference, event-type detection, importance, LLM gating/merge/guardrails, ArticleFacts validation, or event semantic evidence. Triggers on edits to backend/app/ingestion/classifier.py or backend/app/classification/*, or on "this headline is misclassified". NOT for feed-decision changes (visibility/preference/learning — use signal-relevance-change) and NOT for adding registry entities/competitions (use signal-taxonomy-change).
---

Classification answers "what is this article about"; it must never encode "does a user care"
(**facts ≠ personalization** — a hard invariant from `docs/INTELLIGENCE_ROADMAP.md` §2).
If the classification is correct but the feed decision is wrong, stop — that is
`signal-relevance-change` territory. If the fix is "this club/player/competition is missing or
mis-aliased", stop — that is `signal-taxonomy-change` (registry data, not classifier code).
For investigating an unclear complaint from scratch, run `signal-feed-audit` first to localize.

## The pipeline (own this whole chain — a fix belongs at exactly one stage)

```
classifier.py (deterministic rules, always runs)
  → gating.py (should_call_llm_for_article — call LLM only on residual ambiguity)
  → providers.py + prompt.py + validation.py (LLM proposal, strict enums, conf ≥ 0.65)
  → merge.py (7 deterministic guardrails; see docs/LLM_CLASSIFICATION.md "Merge Strategy")
  → event_evidence.py (semantic evidence contract; doubt → news; event_certainty)
  → facts.py (build_article_facts — evidence-weighted sport authority, sport/entity/competition
    triangle, primary_competition/article_competitions/entity_ids/classification_trace persisted)
  → normalize_league_sport_compatibility() (universal post-merge safety net, both paths)
```

Umbrella map: `docs/RELEVANCE_CONTRACT.md`. Layer contracts: `docs/ARTICLE_FACTS.md`,
`docs/LLM_CLASSIFICATION.md`, `docs/RSS_QUALITY_GUARDRAILS.md`, `docs/TAXONOMY.md`.

## Invariants that bind every change here

1. **THE LLM REDUCES UNCERTAINTY; IT DOES NOT DEFINE TRUTH.** The LLM is the *lowest-weight*
   evidence source and its output always passes normalization + validation. Never give an LLM
   field a bypass around a guardrail or around `facts.py`.
2. **LLM optionality is first-class forever.** The `CLASSIFICATION_PROVIDER=disabled` path must
   produce the same schema (more abstentions, never a different shape). Any new field you add
   must be populated (possibly null) on the no-LLM path too.
3. **Evidence-weight order is declared and enforced in `facts.py`:** source URL hint /
   basketball-only source (100) > explicit sport keyword in title (80) > subtitle (60) >
   competition keyword (55) > entity-derived sport (40) > LLM proposal (20). Only *explicit*
   evidence (the first four) may override an incoming sport. Do not add a new evidence source
   without slotting it into this order deliberately and updating `docs/ARTICLE_FACTS.md`.
4. **Abstention is a success mode.** False positives are worse than `sport=unknown`. On
   abstention entities are cleared; explicit competitions survive. Don't "fix" an abstention by
   guessing.
5. **Bare club-family names (מכבי, הפועל, בית"ר, עירוני) never resolve to a team and are never
   sport evidence.** This is the root fix for the Maccabi Ramat Gan contamination class — do not
   reintroduce it via a new keyword.
6. **`primary_competition` / `article_competitions` = explicit article evidence only.** Team
   membership may inform the legacy display `league`, never these fields. Participant-inferred
   competitions are relevance-time only and never persisted.
7. **Entity truth lives in `backend/app/taxonomy/`.** `classifier._FOOTBALL_MACCABI_KW`,
   `_BASKETBALL_ENRICHMENT_PHRASES`, and `entity_normalizer._ENTITY_ALIASES` are *derived views*
   of the registry — never hand-edit a name into them.
8. **Specific event types require positive semantic evidence** (`event_evidence.py`); on doubt
   fall back to `news`. This applies in BOTH the rules path and the LLM merge path
   (guardrail 4b). `event_certainty` must survive ingestion and backfill.
9. **Metrics denominator honesty:** run metrics (`run_metrics.py`, issue #31) are computed only
   in the normal gated ingestion path. Never make `POST /api/classify/backfill` write
   `ingestion_runs` rows or contribute to call-rate metrics — forced-backfill numbers
   masquerading as production call rate is a regression-tested trap.

## Workflow

1. **Reproduce with the real article first.** `GET /api/debug/feed/{user_id}` returns the stored
   record *including* `classification_trace` (evidence hits, gate decision + reason, LLM
   proposal, normalization actions, conflicts) — read the trace before theorizing. The Debug
   page renders it (FactsTracePanel). `GET /api/ingest/quality` shows questionable /
   `sport=unknown` articles DB-wide.
2. **Locate the stage** using the pipeline above. Common mislocations seen before: an "entity
   bug" that is actually a registry gap (taxonomy), a "classifier bug" that is actually the
   facts stage correctly abstaining, an "LLM bug" that is actually gating skipping the call.
3. **Fix the shape of the mistake, not the headline.** Match the repo's existing generalization
   style (`docs/RSS_QUALITY_GUARDRAILS.md` §6/§8/§9 — e.g. the "אלופת" Unicode-pe fix). No
   one-headline string hacks.
4. **Hebrew sport ambiguity:** any new keyword must be checked against the dual-sport club
   machinery (cross-sport twins abstain; guarded European clubs need basketball evidence;
   `_FOOTBALL_MACCABI_KW` ordering). A keyword that is a football brand name is a false-positive
   risk documented in `docs/TAXONOMY.md`'s coverage audit.
5. **Tests** — add the reported case plus at least one adversarial neighbor (a near-miss that
   must NOT change) in the closest existing file: `test_ingestion_classifier.py`,
   `test_quality_regressions.py`, `test_event_evidence.py`, `test_article_facts.py`,
   `test_llm_gating.py`, `test_llm_classification.py`, `test_entity_resolver.py`.
6. **Run:** `cd backend && .venv\Scripts\python.exe -m pytest tests/ -v` (hermetic — conftest
   forces `CLASSIFICATION_PROVIDER=disabled`; no Ollama/API key needed).
7. **Stored articles don't reclassify themselves.** A classifier change affects only future
   ingestion; existing rows keep their old facts. If the change should apply to the real DB,
   note that `POST /api/classify/backfill` (optionally `?dry_run=true`) is the mechanism —
   see `signal-real-data-qa` before running it against the real corpus.
8. **Real-data check for any non-trivial change:** run the before/after decision-diff procedure
   in `signal-real-data-qa`. Unit tests alone have repeatedly missed interaction effects that
   only real headlines expose.
9. **Docs:** append to `docs/RSS_QUALITY_GUARDRAILS.md` (deterministic rules) and/or
   `docs/LLM_CLASSIFICATION.md` (gating/merge/LLM) in their dated changelog style; update
   `docs/ARTICLE_FACTS.md` if evidence weights, triangle rules, or the trace shape changed.
   Then apply `signal-doc-truth` scope checks.

## Done means

- Failing case reproduced, fixed at the correct stage, regression-tested with adversarial
  neighbors, full backend suite green, and (for behavior-visible changes) a real-DB
  before/after diff showing only intended decision flips for BOTH demo profiles (Guy broad
  basketball; Casual Deni Fan deliberately narrow — a fix for one must not silently widen or
  narrow the other).
