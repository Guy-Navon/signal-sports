---
name: signal-relevance-change
description: Use when changing how Signal Sports decides what a USER sees — visibility/competition matching, the Preference V2 affinity engine, seed profiles or ProfileV2 payloads, feedback learning, calibration inference/dataset, or feed decision thresholds. Triggers on edits to backend/app/services/{relevance_engine,preference_engine,learning_service,feed_service,calibration_service}.py, backend/app/calibration_v2/*, backend/app/models/profile_v2.py, backend/app/seed/seed_profiles.py, or requests like "change the scoring", "tune the profile", "adjust learning". NOT for "what is this article about" (use signal-classification-change).
---

This layer consumes persisted article facts; it must never alter them, and article facts must
never be contaminated by user preferences (**facts ≠ personalization**). If the fix is really
"the article's sport/event/competition is wrong", stop — that is `signal-classification-change`.

## Read first (the contracts this layer implements)

`docs/RELEVANCE_CONTRACT.md` (umbrella — decision semantics, pipeline map) →
`docs/RELEVANCE_VISIBILITY_CONTRACT.md` (four-tier matching, reach allowlists, feed ceiling) →
`docs/PREFERENCE_MODEL_V2.md` (ProfileV2, scorer layers, shadow checkpoint) →
`docs/FEEDBACK_LEARNING.md` (derived adjustments, signal hierarchy) →
`docs/CALIBRATION_V2.md` (dataset, inference, apply path).

## The engine landscape (do not blur these)

- **Active:** `backend/app/services/preference_engine.py` (v2) scores `GET /api/feed` over
  `ProfileV2` (JSON `profile_v2` column). Rollback: `PREFERENCE_ENGINE=legacy` env var.
- **Legacy:** `backend/app/services/relevance_engine.py` — kept fully functional and tested
  (rollback + shadow comparison). It ALSO owns `match_competition_names()`, the single
  four-tier competition-matching implementation that the v2 engine imports. A matching change
  goes there once and is consumed by both engines — never re-derive matching inside v2.
- **Frozen:** `frontend/src/engine/relevanceEngine.js` — local/demo mode only. By explicit
  architecture decision it receives NO port of v2/taxonomy/learning features. It is not a
  second implementation target; do not "keep it in sync" with new intelligence. The only JS
  artifacts that track the backend are the generated taxonomy export and the legacy-profile
  drift fixture below.

## Invariants (each one is regression-tested; violating them is how this layer breaks)

1. **Push discipline.** `push` exists only via explicit `always_push` overrides (v2) or explicit
   legacy push rules, with **exact event match — no alias widening** (the alias map once turned
   `major_trade` into a `star_trade` push; that was a pre-flip bug). No boost, delta,
   importance, calibration, or learned adjustment may ever produce push. Boosts cap at
   `high_feed`.
2. **Decision semantics.** `hidden` = no matched followed scope or an exclusion fired.
   `low_feed` = matched a real scope, minor story — NEVER "no reason, bottom of the pile"
   (the `major_importance_fallback` leak was removed in #29; don't reintroduce a global
   importance fallback in any form).
3. **Importance modulates within visibility, never creates it.** very_high importance adds +1
   only when the score is already ≥ 1 (removing this gate leaked ~45 World Cup/Wimbledon
   stories pre-flip).
4. **Membership feed ceiling.** A base match via diffuse `membership` reach with no
   followed-entity backing caps at `feed` — a *ceiling*, not a rank subtraction (a subtraction
   wrongly demotes the Maccabi Ramat Gan signing case). `explicit` and `participant_inference`
   matches are never capped.
5. **Signal hierarchy: explicit > learned > calibration.** Learned entries never override
   explicit ones; calibration apply touches only `source="calibration"` entries; hard
   mute/never_show overrides beat everything.
6. **Learning bounds.** Activation ≥ 3 net consistent decayed events per feature; cap ±1;
   90-day half-life; learned floor −1 (learning never creates an exclude); `article_opened` is
   never evidence; learned state is *derived at read time* from the non-retracted event log —
   never written into the stored profile row; tombstone retraction restores prior state exactly.
7. **Calibration safety.** One `never_show` answer can never create a −2 exclude; contradictions
   widen toward neutral; calibration never writes overrides.
8. **Monotonicity.** Adding an affinity can never lower a decision (max-points-win base).
9. **Reach allowlists are positive and fail-closed.** An event type in neither
   `TEAM_ANCHORED_EVENTS` nor `COMPETITION_ANCHORED_EVENTS` gets no membership reach. Adding a
   new event type to an allowlist is a product decision — record the reasoning in
   `docs/RELEVANCE_VISIBILITY_CONTRACT.md`.
10. **Identity is entity_ids-first** on post-facts rows (`taxonomy_version is not None`); legacy
    display strings are a compatibility path for old rows only — never merge the two paths.
11. **Relevance-time inference is never persisted.** Participant-inferred competitions must not
    be written into `primary_competition`/`article_competitions`.

## Profile changes specifically

- Legacy topic seeds live in `backend/app/seed/seed_profiles.py` AND
  `frontend/src/data/userProfiles.js`, guarded by `docs/fixtures/profile_parity.json` via
  `backend/tests/test_profile_drift_guard.py` + `frontend/src/data/userProfiles.drift.test.js`.
  Changing a legacy topic means updating **all three** (both seeds + fixture) or the guards fail
  — that failure is the system working; never "fix" it by weakening the test.
- V2 payloads (`PROFILE_V2_SEEDS` in `seed_profiles.py`) have no JS mirror. Seed backfill writes
  `profile_v2` only when NULL — a user-edited profile is never overwritten on startup; don't
  change that.
- Profile mutations at runtime go through `PUT /api/profiles/{user_id}` (pydantic-validated)
  or the scoped `POST /api/profiles/{user_id}/never_show` — not ad-hoc DB writes.
- DB schema additions use the soft-migration list in `backend/app/db/database.py`
  (`_apply_migrations`): nullable/defaulted `ALTER TABLE ADD COLUMN`, old rows load as
  None-equivalents, idempotent on startup. Follow that pattern; no migration framework exists.

## Validation gates (all required for a behavior change)

1. Targeted suites: `cd backend && .venv\Scripts\python.exe -m pytest tests/test_preference_engine_v2.py tests/test_relevance_visibility_contract.py tests/test_participant_inference.py tests/test_feedback_learning.py tests/test_calibration_v2.py tests/test_relevance_engine.py tests/test_profile_drift_guard.py -v`
   then the full suite.
2. **Real-data decision diff** (`signal-real-data-qa`): before/after decisions for BOTH demo
   profiles on the real DB. Every flipped decision must be classified intended/regression —
   this is exactly how the pre-flip shadow checkpoint caught the importance leak, the Maccabi
   `news` inflation, and the alias-widening push. Relevance scoring is read-time: no re-ingest
   needed to see effects.
3. **Push parity check:** push counts per profile before vs after; any new push needs an
   explicit-override explanation.
4. If both engines were touched (matching machinery), check legacy/v2 agreement via
   `GET /api/debug/shadow/{user_id}` — new disagreements need individual justification.
5. Frontend suite (`cd frontend && npm run test`) if the drift fixture, generated taxonomy
   export, or any `src/` file changed.

## Docs

Update the specific layer contract you changed (see Read-first list) and
`docs/CURRENT_PROJECT_STATE.md` §7; then run `signal-doc-truth` scope checks. A worked example
(like the Ramat Gan ceiling case or the Lakers–Celtics inference case) is the house style for
explaining a semantics change.

## Done means

Contracts updated, all suites green, real-DB diff reviewed with every flip explained, push
discipline verified, and rollback intact (`PREFERENCE_ENGINE=legacy` still serves a working
feed if the engine itself was touched).
