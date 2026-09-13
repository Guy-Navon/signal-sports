# Task brief — Two thirds of every LLM call produces nothing. Find out why, then fix the economics.

Signal Sports is a personalized sports-news intelligence feed (Hebrew-first,
FastAPI + SQLite, React). Repo root has `CLAUDE.md` and `docs/`. Assume **no prior
conversation history**.

Work on a branch. **Open a PR and stop. Do not merge.**

---

## 1. The measurement that motivates this

Classification calls a local LLM (ollama `qwen2.5:3b-instruct`). Aggregated over
every ingestion run that persisted per-run metrics (issue #31):

| | |
|---|---:|
| LLM attempts | **718** |
| LLM successes | **241** (33.6%) |
| Fallbacks | **477** |
| — of which `connect_error` | **0** |
| — of which `timeout_or_parse` | **477** (100%) |
| `CLASSIFICATION_TIMEOUT_SECONDS` | **30** |

And across the stored corpus (1,427 RSS rows):

| classified_by | rows | share |
|---|---:|---:|
| `rules` (LLM skipped) | 687 | 48.1% |
| `rules_fallback_after_llm_failure` | **478** | **33.5%** |
| `llm+rules_guardrail` | 188 | 13.2% |
| `llm` | 74 | 5.2% |

**The LLM is called on 51.9% of articles** — more than double the ≤25% target
recorded in #31 — **and roughly two thirds of those calls fail.** Every failure is
a timeout or a parse error; none is a connection error, so Ollama is reachable and
answering. At a 30-second ceiling, 477 failed calls is up to ~4 hours of
wall-clock waiting that produced nothing.

**The failure rate is uniform across every reason the gate calls:**

| gate_reason | called | used | failed | fail rate |
|---|---:|---:|---:|---:|
| `hebrew_broad_source_unclear` | 467 | 165 | 302 | 64.7% |
| `sport_unknown` | 218 | 80 | 138 | 63.3% |
| `ambiguous_club` | 55 | 17 | 38 | 69.1% |

That uniformity is the important part. There is **no low-failure bucket to prefer**,
so this cannot be fixed by making the gate smarter about *which* articles to send.
The failure is a property of the call, not of the article selection.

---

## 2. The one question that decides everything

`fallback_timeout_or_parse` **conflates two completely different faults**, and the
entire fix branches on which it is:

- **Timeout** — the model is too slow (a 3B model on CPU). Fixes live in model
  choice, prompt length, or failing fast instead of waiting 30 seconds.
- **Parse** — the model answers in time but returns something the parser rejects.
  Fixes live in output formatting — Ollama supports constrained JSON output — and
  are typically small and very high-leverage.

**Step 1 is to separate them.** It is cheap, it is decisive, and nothing else in
this brief should be attempted before it is answered with real numbers. If the
answer is "95% parse errors", this task is probably a one-day fix that triples the
success rate. If it is "95% timeouts", it is a capacity and model-selection
question with an entirely different shape.

Do not guess which. Instrument, run, and report.

---

## 3. Goals

**G1 — Split the metric and report the true breakdown.** `timeout` and
`parse_error` become distinct counters in the #31 per-run metrics, with the parse
failures carrying enough detail to characterise them (what did the model actually
return?). Then produce the numbers on a real run.

**G2 — Raise the success rate, or stop paying for failure.** Whichever the
diagnosis supports:

- if parse-dominated → fix the output contract; target **success rate ≥ 80%**
- if timeout-dominated → fail fast and/or change the model; target **median
  wasted wall-clock per run reduced by ≥ 70%**

State which branch you are on and why, with the evidence.

**G3 — Re-tune the gate, but only afterwards.** The call rate is 51.9% against a
≤25% target. **Do not touch the gate before G2.** Tightening it while two thirds of
calls fail optimises the wrong thing and would bake today's brokenness into the
thresholds. Once the LLM actually works, re-measure what it adds and tune from
that.

**G4 — Answer the standing product question with data.** Given the real
success rate and cost, *should the LLM be enabled by default for new ingestion at
all?* The LLM-optional invariant (§5) means the rules-only path must stay fully
functional regardless, so this is a live option, not a hypothetical. Answer it with
the measured value the LLM adds, not with a preference.

---

## 4. What the LLM is actually worth — measure before you cut

This is where the task gets genuinely subtle, and the trap is real.

`docs/qa/N05_FEED_GROUND_TRUTH.md` finding **F-N05-6**: of 34 measured false-hides
re-run through a fresh **rules-only** classification, **12 were degraded** —
`sport` fell from `basketball` to `unknown` — because those rows carried
LLM-assisted facts a rules-only pass cannot reproduce. **The stored row is often
better than what rules alone would write.**

So the LLM *does* add real value when it succeeds. The question is not "is the LLM
useful" (it is) but "what is the success-weighted value per second spent".

Two further findings already quantify the cost of its failures:

- **172 of 210** `sport=unknown` rows followed an LLM failure (#194).
- **336 of 816** `news` rows followed an LLM failure (#191).

Both blind spots are substantially *manufactured by failed LLM calls* falling back
to a weaker deterministic answer. That means fixing the failure rate is not only a
cost saving — it is likely the largest single lever on classification quality
currently available.

**Quantify it:** of the 241 successful calls, how many actually changed the stored
facts versus agreeing with what rules already had? That number is the LLM's real
contribution and it has never been measured.

---

## 5. Hard invariants

- **⛔ NEVER run a blanket rules-only backfill of the corpus** (F-N05-6). This is
  the sharpest trap in this task: a tempting way to "measure the LLM's value" is to
  re-classify everything without it and diff. **That would destroy LLM-assisted
  facts on 1,427 rows.** Measure on a **copy**, or by replaying against stored
  traces. The live corpus DB (`backend/data/signal_sports.db`) is irreplaceable
  replay evidence — never reset it, back up before any write
  (`backend/scripts/backup_db.py`), and keep corrections targeted,
  dry-run-by-default, idempotent and hand-verified.
- **The LLM-optionality invariant holds**: the LLM-disabled path must remain fully
  functional, and no change may make the product depend on a provider being up.
- **Abstention is a designed success mode.** Do not "fix" failures by making the
  model guess more confidently. A confidently wrong fact reaches the preference
  layer as truth; `unknown` does not.
- **No new hard dependency on a paid API without an explicit human decision** —
  cost is a product decision. Local-first is the current constraint; the Gemini
  free tier was already evaluated and found insufficient (`docs/LLM_CLASSIFICATION.md`).
- **No feed regression.** Verify with the gate (§6) and report both directions.

---

## 6. Verification

A directional regression gate scores the engine against 282 hand-rated real corpus
items:

```bash
cd backend
.venv/Scripts/python.exe scripts/feed_ground_truth.py gate      # exit 0 / 1
```

Run it **before you start** and after any behaviour-changing step. Current state:
Guy `shown_precision` **98.3%** / `false_hide` **18.0%**; `casual_deni_fan` 91.7% /
0.8%. Rules in `docs/RELEVANCE_CONTRACT.md` §"Quality gate".

**⚠️ Never lead with overall accuracy** — it is dominated by the hidden majority
(`casual_deni_fan` scores 98% exact agreement while hiding 98.3% of the corpus).
Always report `shown_precision` and `false_hide` together.

Most of this task should be **decision-neutral**: fixing an LLM that currently
fails does not change already-stored facts. If the gate moves, explain why.

Suites: backend `pytest tests -q` (baseline **2,549 passed, 1 skipped**), frontend
`npm run test && npm run lint && npm run typecheck && npm run build` (**539
passed**).

---

## 7. Notes that will save you time

- **Ollama must be running** for any live measurement (`CLASSIFICATION_PROVIDER=ollama`).
  With it down you get connection errors, which is a *different* failure than the
  one under investigation — and the data says connection errors are currently zero.
- The corpus is **frozen**: newest article 2026-07-31, and no ingestion runs during
  this work. Live-network ingestion is inherently non-reproducible; if you trigger
  a run, say so and record fetch counts.
- ⚠️ `backend/.env` has `SCHEDULER_ENABLED=true` and
  `TELEGRAM_NOTIFICATIONS_ENABLED=true`. If you start the backend server, the
  scheduler will run live ingestion and move the corpus under your own
  measurement, and the notification path can send **real messages**. Set both to
  `false` for the duration, and say in the PR that you did.
- **A blocked goal stops THAT GOAL, not the run.** G1–G4 are largely independent.
  Record what blocked and keep going.
- **A well-evidenced refutation is a success.** If the numbers contradict this
  brief's framing, say so plainly — three issues in this project (#190, #193, #208)
  were re-scoped or closed on exactly that basis, and each saved real work.

Skills encode the house workflow: `signal-classification-change`,
`signal-real-data-qa`, `signal-doc-truth`, `signal-pr-finish`.

## 8. Orientation

| Path | What |
|---|---|
| `docs/LLM_CLASSIFICATION.md` | Providers, gating, merge guardrails, run metrics |
| `docs/qa/N05_FEED_GROUND_TRUTH.md` | The measurement; F-N05-6 lives here |
| `backend/app/classification/gating.py` | The per-article call/skip decision |
| `backend/app/classification/prompt.py` | The few-shot prompt |
| `backend/app/classification/validation.py` | Response validation and enums |
| `backend/app/ingestion/classifier.py` | Classification entry point |
| `backend/app/qa/unknown_sport.py` | The `sport=unknown` blind spot metric (#194) |
| `GET /api/ingest/quality` | Sport breakdown, questionable rows, `llm_dependency_runs`, `unknown_sport` |

Related issues: **#65** (LLM provider/prompt evaluation — this task largely
supersedes its scope item 4), **#36** (async enrichment, deferred; its trigger is
sustained LLM time per run, which this task directly addresses), #191, #194.
