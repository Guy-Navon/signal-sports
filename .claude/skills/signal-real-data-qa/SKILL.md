---
name: signal-real-data-qa
description: Use to validate a Signal Sports classification/taxonomy/relevance change against the real local article corpus — before/after decision diffs per profile, shadow engine comparison, backfill, push-discipline counts, LLM dependency metrics. Triggers on "check this against real data", "run the QA", "diff the feed", or as the validation gate other signal-* skills point here for. NOT for investigating a user complaint (signal-feed-audit) and NOT a substitute for unit tests.
---

## The corpus is an asset — protect it

`backend/data/signal_sports.db` is the accumulated real ingested corpus (hundreds of articles
including every historical QA case: the Ramat Gan headlines, the Brooklyn–Sacramento hidden-row
case, the World Cup noise wave). It is git-ignored and irreplaceable in the short term.

- **Never delete it as a casual reset.** Deleting it destroys the QA baseline every real-data
  procedure here depends on. If a reset is truly needed, that is a user decision — ask.
- `POST /api/dev/reset-rss-data` (requires `ALLOW_DEV_RESET=true`) wipes RSS articles +
  ingestion runs — same warning applies.
- pytest never touches this DB (conftest uses a temp file) — running tests is always safe.

## Setup

Backend: `cd backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`.
Scoring endpoints need no LLM provider. Confirm the serving engine first: `GET /api/feed-engine`
(v2 unless `PREFERENCE_ENGINE=legacy`). Profiles: `guy`, `casual_deni_fan`.

## Core procedure — before/after decision diff

Scoring is computed at read time, so relevance-layer changes show up without re-ingesting;
classification/taxonomy changes affect only NEW rows until backfilled (step 3).

1. **Before** (on the pre-change code): capture per profile
   `GET /api/debug/feed/guy` and `GET /api/debug/feed/casual_deni_fan`, reduce to
   `article_id → decision` (plus `matched_topic`/match_kind for context). Save to the session
   scratchpad, not the repo.
2. Apply the change.
3. **Classification/taxonomy changes only:** stored rows keep old facts. Use
   `POST /api/classify/backfill?dry_run=true` to preview, then run it for real if the change is
   meant to reach stored rows. Backfill force-calls the LLM when a provider is enabled —
   with `CLASSIFICATION_PROVIDER=disabled` it re-runs the deterministic+facts path only, which
   is usually what QA needs.
4. **After:** capture the same snapshots and diff. For EVERY flipped decision, classify it:
   *intended* (cite the contract/product reason) or *regression* (fix before proceeding).
   Report in the shadow-checkpoint house style: per profile — total articles, agreement count,
   promoted list, demoted list, push count before/after (see `docs/PREFERENCE_MODEL_V2.md`
   "Shadow checkpoint" for the format that has worked).
5. **Push discipline gate:** push counts must stay small and every push must trace to an
   explicit rule/override. A new push without an explicit-override explanation is a blocking
   finding.

## Additional instruments

- **Shadow comparison** `GET /api/debug/shadow/{user_id}` — legacy vs v2 on every article with
  per-article traces for disagreements. Use when the change touches shared matching machinery
  or when validating engine-level work. Known accepted disagreements are documented in
  `docs/PREFERENCE_MODEL_V2.md` — don't re-litigate those.
- **Quality report** `GET /api/ingest/quality` — sport breakdown, questionable articles, and
  `llm_dependency_runs` (per-run call rate vs the ≤25% target, abstention/conflict rates,
  latency, cost).
- **Metrics denominator honesty:** LLM call-rate claims come ONLY from normal gated ingestion
  runs. Backfill force-calls by design and writes no run rows — never quote backfill numbers
  as production call rate.
- **Fresh-ingestion check** (source/classification changes): `POST /api/ingest/run`
  (409 = a run is already active; all triggers share one process lock) then inspect the new
  rows' `classification_trace` in Debug. A live-network run is inherently non-reproducible —
  note fetch counts.
- **Learning interference:** the feed scores learned-augmented profiles. If diffs look
  inexplicable, check `GET /api/learning/{user_id}` and recent feedback events — QA sessions
  that clicked feedback buttons contaminate later diffs. Reset via
  `POST /api/learning/{user_id}/reset` (tombstones, exact restore) only with user awareness.

## Report

State corpus size, engine, what was diffed, flips with per-flip classification, push counts,
and any metric movement. Distinguish **Verified** (endpoints actually hit this session) from
**Expected** (inferred). If zero flips occurred where flips were expected, that is a finding —
the change may not reach the code path you think it does.
