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

## Start here: the two ground-truth gates (issues #189, #254)

Before the endpoint-diffing procedure below, run **both** gates. Each answers "did this change
make it worse?" in one command:

```
cd backend
.venv\Scripts\python.exe scripts/feed_ground_truth.py gate            # N05: 282 stratified ratings, frozen July corpus
.venv\Scripts\python.exe scripts/feed_ground_truth.py gate --census   # census: every census #2 row (804), stored facts
.venv\Scripts\python.exe scripts/feed_ground_truth.py gate --census --facts rerun   # census on a rules-only rerun
# exit 0 = clean, 1 = blocked
```

Read-only; needs no server. Both read the DB through `DATABASE_URL`. To run against a frozen
corpus copy instead of the live DB, copy it to a scratch file first (opening it switches the
file to WAL) and set `DATABASE_URL=sqlite:///<copy>`. Decisions come from the profiles stored
in that DB, so a copy taken before an owner `apply_*` run measures the profile without it.
Run them **before** the change to confirm a clean start, and again after. If either fails, the
failing check is named and the change is not ready — do not proceed to interpreting decision
diffs, and do not regenerate a baseline to make it pass.

**The census gate** (`app/qa/census_gate.py`, baseline `docs/qa/census_gate_baseline.json`)
reads recall directly because every row is rated: report **shown precision, feed+ recall,
push precision, push recall** and the **≥2-notch disagreement count**. One-notch gaps are
rating noise (census #2's blind re-rate changed 28 of 58 large gaps) and are not gated. A change
that hides wanted rows fails `feed_plus_recall`; one that surfaces noise fails
`shown_precision`, even though it *lowers* the ≥2-notch count. Census #3 (#241) joins by passing
`--ratings/--sample` pairs (and `--review` files, whose ratings win) with
`--census --update-baseline`; details in `docs/RELEVANCE_CONTRACT.md` §Census gate. N05 stays as a
second gate until the census gate has gated two real changes.

**Stored facts cannot see a classifier change.** N05 and `gate --census` score the facts
persisted in the corpus, and stored rows change only through a backfill. A classifier or
taxonomy change therefore passes them with zero movement, which happened with #398. For those
changes, the gate that counts is `gate --census --facts rerun`: a rules-only reclassification of
the census rows in memory, with its own baseline. After such a change merges, that baseline is
behind main. Bring it forward only once the change's delta against it has been reviewed (below).

**From N05, report both numbers it gives you, always.** Overall accuracy is a trap here: `casual_deni_fan`
scores 98% exact agreement while hiding 98.3% of the corpus. The pair that describes the product
is `shown_precision` (of what the user sees, how much did they want) and `false_hide` (how much
they wanted and never saw). A change that improves one by wrecking the other is not progress —
a synthetic "recall fix" once took false_hide 19.4% → 11.4% while shown precision fell to 83.5%.

A regression the change genuinely needs is declared, not hidden:
`gate --accept <check_id> --reason "<why>"`. Regenerating the baseline
(`gate --update-baseline`, or `gate --census --update-baseline`) redefines what every future change is measured against — that is a
user-facing decision, so ask rather than doing it to clear a red gate.

**A baseline is a change detector, not proof the result is correct.** Never regenerate one to
absorb a change before its delta against the PREVIOUS baseline is recorded and reviewed:
before → after per check, plus every rated row whose decision moved, with its rating. Otherwise a
regression is laundered into the reference. The commit that rewrites a baseline cites that delta.
The census gate's `--update-baseline` enforces this: it prints the delta, refuses to write on a
failing or invalid comparison, and stores the delta in the new baseline. Override with
`--accept <check> --reason` (an argued regression) or `--force-update --reason`. N05's update does
not enforce it; follow the rule by hand there. Rule and procedure: `docs/RELEVANCE_CONTRACT.md`
§Quality gate.

Rules and baselines: `docs/RELEVANCE_CONTRACT.md` §Quality gate and §Census gate,
`docs/qa/n05_gate_baseline.json`, `docs/qa/census_gate_baseline.json`.

## Setup

Backend: `cd backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`.
Scoring endpoints need no LLM provider. Confirm the serving engine first: `GET /api/feed-engine`
(v2 unless `PREFERENCE_ENGINE=legacy`). Profiles: `guy`, `casual_deni_fan`.

## Fastest classification check — in-memory corpus rerun (no server, no writes)

For a classifier/taxonomy/evidence change, `backend/scripts/corpus_rerun_diff.py` re-runs the
deterministic ingestion path over EVERY corpus row in memory (LLM + translation disabled),
scores both seed profiles, and diffs two snapshots: changed facts, every decision flip (with
the owner's census rating), push/visible counts, census metrics. Snapshot the working tree,
`git stash`, snapshot main, `git stash pop`, `compare old new --ratings
../docs/qa/census2_ratings.json`. This is how every milestone-9 change was measured. It is
rules-only — an approximation of production; say so when quoting numbers. Stored rows still
need the procedure below (or a backfill) to change.

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

## Metric-level evaluation

This skill owns the per-change gate. For intervals, held-out splits, classification
precision/recall, cluster merge/split quality, prompt/model bake-offs or latency/cost, use
`signal-quality-eval`; it builds on this gate rather than replacing it.

## Report

State corpus size, engine, what was diffed, flips with per-flip classification, push counts,
and any metric movement. Distinguish **Verified** (endpoints actually hit this session) from
**Expected** (inferred). If zero flips occurred where flips were expected, that is a finding —
the change may not reach the code path you think it does.
