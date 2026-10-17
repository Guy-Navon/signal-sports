---
name: signal-quality-eval
description: Measure Signal Sports product quality with evidence - classification precision/recall/F1, feed-decision agreement with owner ratings, cluster false merges and splits, duplicate or missed push notifications, latency and LLM cost - and compare before/after for prompt, model, threshold, gating or clustering changes. Uses the existing corpus tools on read-only copies, with held-out discipline and explicit sample sizes and uncertainty. Triggers on "how good is X", "did this improve quality", "evaluate the model/prompt/threshold", or any change that claims a quality gain. The mandatory per-change feed gate stays in signal-real-data-qa.
---

# Signal quality evaluation

Turn "it seems better" into a measured, honest claim — or an honest "no detectable change".

**Ownership.** `signal-real-data-qa` owns the mandatory per-change feed gate (N05 ground-truth
gate, decision diff, push discipline): run it, don't re-implement it. This skill owns metric-level
evaluation — what to measure, against which labels, with what uncertainty, without contaminating
the evaluation set. `llm-evaluation` is the generic method reference; `signal-feed-audit` handles
single complaints. Results feed `signal-pr-open` / `signal-pr-merge` evidence, not a separate gate.

## 0. Isolation rules (non-negotiable)

- **Work on copies.** Make a consistent copy with the SQLite backup API from a read-only connection:

  ```
  cd backend
  .venv\Scripts\python -I -c "import sqlite3,sys; s=sqlite3.connect('file:data/signal_sports.db?mode=ro',uri=True); d=sqlite3.connect(sys.argv[1]); s.backup(d); d.close()" <scratchpad>\eval_copy.db
  ```

  Or use `scripts/make_dev_snapshot.py` (sanitized). Tools that import the app get
  `DATABASE_URL=sqlite:///:memory:` so the app engine cannot touch a real file; the evaluation tools
  open their `--db` with `mode=ro`.
- **Never** run ingestion, backfill, retention or dispatch against the live corpus; set
  `TELEGRAM_NOTIFICATIONS_ENABLED`; click feedback buttons; regenerate a baseline
  (`feed_ground_truth.py gate --update-baseline` redefines every future measurement — Guy's
  decision); or edit labels to agree with the engine.
- **Live LLM calls spend money and quota.** Go through `scripts/llm_bakeoff.py`: dry run by default,
  call ceilings, cached responses, read-only corpus. Use `--live` only with Guy's agreement.
- Keep working files in the scratchpad. Commit an evaluation output only when a doc will cite it as
  evidence (house style: dated files under `docs/qa/`).

## 1. Ground truth that exists — and its limits

| Asset | Labels | n | Use it as |
|---|---|---|---|
| `docs/qa/n05_ratings.json` + `n05_sample.json` | Owner feed ratings (hide/low/feed/high/push), stratified with weights | guy 185, casual_deni_fan 97 | **The active gate.** Every change since 2026-09 was measured against it, so treat it as a *development* set. Population estimates need its weights (`feed_ground_truth.py score`). |
| `docs/qa/census2_ratings.json` (+ `census2_review_ratings.json`, `census2_sample.json`) | Owner ratings, Guy only, cohort since 2026-08-01, one stratum (weight 1) | 804 | The best broad sample. Has a seeded fit/held-out split (#237, `census_calibration_fit.py`). The held-out half already confirmed #237, so it is partly spent. Borderline rows carry about one notch of rating noise (owner review: 28 of 58 re-rated rows changed). |
| `backend/tests/fixtures/golden_cases.json` | 15 reliability cases (pinned vs desired) | 15 | Regression contract, not a metric sample. |
| `backend/tests/fixtures/clustering_cases.json`, `clustering_adversarial.json`, `feed_dedup_cases.json` | True-positive groups, must-not-cluster pairs, duplicate-harm cases | small | Frozen contract the matcher was developed against — not an unbiased precision estimate. |
| `docs/qa/n190_entity_corrections.json`, `n191_event_corrections.json` | Reviewed fact corrections | 24, 34 | Regression checks only: today's rules-only replay scores 34/34 on n191 *because the rules were built from those rows*. |
| `docs/qa/components_*_review_*.txt`, `cluster_backfill_live_126_*.json` | Manual cluster reviews | — | Point-in-time evidence. |

**There is no large human-labeled set for article facts** (sport, event type, entities,
competitions). A classification precision/recall/F1 claim needs new labels (§5). Never derive
"labels" from LLM output or from the engine's own decisions.

## 2. Choose the instrument for the change

| Change | Instrument (existing) | Ground truth | Report |
|---|---|---|---|
| Relevance, preference, thresholds | `signal-real-data-qa` gate + `scripts/corpus_rerun_diff.py` snapshot/compare + `eval_stats.py census` | N05 (gate), census #2 (held-out half for anything tuned) | shown precision **and** false hide / feed+ recall, push counts, flips |
| Deterministic classification rules | `corpus_rerun_diff.py` before/after (rules-only, LLM off) | Manual review of changed facts; census #2 for decisions | every changed fact, decision flips, P/R/F1 only against independent labels |
| Prompt, model, provider | `scripts/llm_bakeoff.py` (dry run → smoke → accuracy) | Owner ratings; baselines on the *same rows* (stored facts, rules-only) | decision agreement with intervals; tokens, latency and cost marked as estimates |
| LLM gating thresholds | Run metrics from normal gated runs (`GET /api/ingest/quality` → `llm_dependency_runs`: `llm_call_rate`, fallbacks) + decision impact as above | — | call rate vs the ≤25% target; never quote backfill as call rate |
| Clustering matcher or tunables | Frozen fixture tests; `scripts/feed_dedup_eval_124.py <snapshot-with-anchors>` (pair: must-merge recovery, must-not-merge rejection, material-update preservation; component purity, false bridges); `scripts/clustering_diagnostics.py`; Checkpoint-2 manual review on a copy | Adjudicated pairs/groups + manual review of **every** proposed cluster | false merges (must be zero confirmed), false splits, `RULE_VERSION` bump (`docs/CLUSTERING.md` §3, §12.2) |
| Notifications | Identity/planner/dispatch/watermark tests; on a copy: push decisions per profile per day; outbox rows per story lineage | Owner `push` ratings | duplicate pushes (lineage), push precision/recall — census #2 has only 7 owner pushes, so say how thin that is |
| Latency and cost | `ingestion_runs` metrics: `llm_avg_ms`, `llm_p95_ms`, `total_ms`, `articles_per_minute`, `llm_tokens`, `estimated_cost_per_run` (estimate from `cost_per_call`) | — | normal gated runs only, with run count and date range |

Rules-only replays (`corpus_rerun_diff.py`, `census_calibration_fit.py`) approximate production,
which also uses the LLM. Say so whenever you quote their numbers.

## 3. Before/after protocol

1. **Freeze inputs:** one DB copy. Record its path, timestamp, row count and per-source counts.
   Both sides are measured on the same rows (`corpus_rerun_diff compare` uses common ids only).
2. **Baseline from the base commit, candidate from the working tree,** with identical flags (use a
   worktree or `git stash`; follow `signal-real-data-qa` for the stash dance).
3. **Diff:** list every decision flip and classify it as intended (cite the reason) or regression.
4. **Statistics** with the bundled helper (stdlib only, read-only):

   ```
   python -I .claude/skills/signal-quality-eval/scripts/eval_stats.py census <after.json> --before <before.json> --ratings docs/qa/census2_ratings.json --split heldout
   python -I .claude/skills/signal-quality-eval/scripts/eval_stats.py census <after.json> --ratings docs/qa/n05_ratings.json --profile casual_deni_fan --slice source --db <copy.db>
   python -I .claude/skills/signal-quality-eval/scripts/eval_stats.py prf <pairs.json> --slice source
   python -I .claude/skills/signal-quality-eval/scripts/eval_stats.py selftest
   ```

   `census` reuses `corpus_rerun_diff.census_metrics` (definitions can't drift), adds Wilson 95%
   intervals, and with `--before` runs an exact McNemar test on rows whose visibility error or
   exact-notch agreement changed. Report the discordant counts (got worse / got better), not only
   the p-value. Slices and metrics with n below `--min-n` (default 10) are printed as "not
   estimated".
5. **Gate:** `scripts/feed_ground_truth.py gate` (exit 0 = clean) — owned by `signal-real-data-qa`.
6. **Interpret honestly:** few discordant rows plus overlapping intervals means **no demonstrated
   change** — don't call it an improvement. Always pair precision with recall: `casual_deni_fan`
   scores ~98% exact while hiding almost everything, and a past "recall fix" cut false hides from
   19.4% to 11.4% while shown precision fell to 83.5%.

## 4. Held-out discipline — don't tune on the evaluation set

- **Decide before looking** which rows are for development (inspect failures, tune) and which are
  for confirmation. Write it in the report.
- **N05 is a development set** by now. A change tuned on N05 failures needs confirmation on the
  census #2 held-out half (`--split heldout`) or a fresh sample.
- **Census #2:** find biases on `--split fit`, confirm on `--split heldout` (this reproduces
  `census_calibration_fit.py`'s seeded #237 split exactly). Every reuse of the held-out half erodes
  it; for a major tuning effort, ask Guy for a fresh rated sample (census #3 is milestone 11).
- **Data a fix was built from is never an accuracy estimate:** golden cases, n190/n191 corrections,
  clustering fixtures, rows quoted in the issue.
- **Small groups don't carry a calibration** (n < 5 per group per the census protocol); a large
  engine–owner disagreement is re-rated blind by Guy before anyone acts on it.

## 5. When ground truth is missing

- Say so in the report ("unavailable: no labels for X"). Don't substitute engine output, LLM output
  or your own judgment as labels.
- **Feed decisions:** draw a stratified sample with `scripts/rate_census.py build` /
  `feed_ground_truth.py sample` (record the seed and weights). Guy rates blind — no engine decision
  shown. Store it under `docs/qa/` with a date.
- **Facts (sport, event type, entities):** no labeling tool exists. Propose a small file (`id`,
  title, field, label) for Guy to fill, sized for the claim: about 30+ labeled examples per class
  before reporting that class on its own; otherwise report the pooled number only.
- **LLM-as-judge** may triage which rows to inspect, or explain a disagreement. It is supporting
  evidence only — never a label, never the tie-breaker against Guy's rating.
- **Hebrew edge cases to include deliberately** (history in `docs/RSS_QUALITY_GUARDRAILS.md` and
  `docs/LLM_CLASSIFICATION.md`; cases in `test_quality_regressions.py`, `golden_cases.json`): bare
  club-family names (מכבי, הפועל, בית"ר, עירוני) that must not resolve to a team; cross-sport twin
  clubs; championship vocabulary used as an epithet for a third party ("מול אנגליה אלופת העולם");
  "הניף" without a trophy; Deni Avdija mentioned in passing or as a former affiliation, not as the
  subject; interview vs news; rumor vs negotiation vs official signing; live scorelines (in-play);
  English names inside Hebrew headlines; gershayim abbreviations; a regular-season NBA result,
  which should differ for Guy and the Deni fan.

## 6. Report

```
Question / change:            what is being evaluated; base SHA → candidate SHA
Data:                         DB copy (timestamp, rows, per-source); label sets with n and role (dev/eval);
                              replay mode (rules-only vs LLM); filters
Results:                      metric | before | after | n | 95% CI   (+ paired: worse / better / p)
Flips:                        each one, classified intended / regression
Push:                         counts per profile; every push traced to an explicit rule/override
Latency / cost:               source, run count, "estimate" where it is one
Missing ground truth & checks: passed / failed / skipped / unavailable (verification-before-completion)
Verdict:                      improvement demonstrated | no detectable change | regression — with the uncertainty
```

Never fabricate labels, baselines, thresholds or results. Never quote accuracy alone, a rules-only
replay as production behavior, or LLM-judge agreement as accuracy.
