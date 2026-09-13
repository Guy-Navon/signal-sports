# Task brief — The LLM answers in 4.4s and we throw the answer away

**Right-sized for a focused coding model (Codex-class), not a frontier reasoning
run.** The diagnosis is already done and is in §2; what remains is instrumentation
and a well-specified fix with clear guardrails.

**Implementers: read §1–§2 for context, then work from the line-level
instructions in "Implementer instructions (Codex)" at the end. This change is
code-reviewed before merge; the review checklist is I6.**

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

## 2. It is NOT a timeout. It is a parse failure. (Answered 2026-09-13)

This section originally asked you to find out whether the failures are timeouts or
parse errors, because the whole fix branches on it. **That question is now answered
from the already-persisted metrics, and the answer narrows this task a great deal.**

Every failing run records its LLM latency:

| run | attempts | successes | `llm_avg_ms` |
|---|---:|---:|---:|
| 2026-07-31T15:22 | 1 | 0 | 4,388.6 |
| 2026-07-31T15:21 | 12 | 0 | 4,388.7 |
| 2026-07-31T15:21 | 4 | 0 | 4,404.1 |
| 2026-07-31T15:20 | 17 | 0 | 4,403.3 |
| 2026-07-24T15:24 | 1 | 0 | 4,416.7 |

**~4.4 seconds against a 30-second ceiling** (`CLASSIFICATION_TIMEOUT_SECONDS=30`,
applied as an httpx read timeout in `providers.py:181`). Nothing is timing out.
The model answers, consistently and quickly, **and the response is then rejected.**

The consistency matters as much as the value: 4,388–4,458 ms across hundreds of
calls is not erratic behaviour, it is the same thing happening every time.

### The leading hypothesis — test it first

`backend/app/classification/providers.py` sends:

```python
"format": "json",
"options": {"temperature": 0, "num_predict": 500},
```

`format: "json"` is already set, so Ollama is constrained to JSON. But
**`num_predict: 500` caps generation at 500 tokens.** If the model's JSON exceeds
that cap it is truncated mid-structure, and truncated JSON fails to parse **every
time, after a consistent generation duration** — which is exactly the signature in
the table above.

That is a hypothesis, not a finding. It is cheap to test and it must be tested
before anything is changed.

### Why the real error is invisible today

```python
except Exception as exc:
    logger.warning("Ollama classify failed for %r: %s", title[:60], exc)
    return None
```

One catch-all swallows an HTTP error, a `KeyError` on the response shape, and a
validation rejection from `parse_and_validate_llm_json` — and the metric records
all of them as `timeout_or_parse`. **Replacing this with typed handlers that record
what actually happened is the first commit**, and on its own it will probably make
the cause obvious.

## 3. Goals

**G1 — Make the real failure visible.** Replace the catch-all with typed handlers;
`timeout`, `http_error`, `bad_response_shape` and `parse_error` become distinct
counters in the #31 per-run metrics, and parse failures capture **what the model
actually returned** (truncated? valid JSON with a wrong shape? not JSON at all?).
Run it and report. Expect ~0 timeouts, per §2.

**G2 — Raise the success rate. Target ≥ 80%**, from today's 33.6%.

Test the `num_predict` hypothesis first (§2) — raise or remove the cap and
re-measure. If that is not the cause, the G1 instrumentation will say what is.
Report what the model was actually returning, because that evidence is the whole
value of this task.

Do not "fix" it by loosening validation to accept malformed output. The validator
rejecting bad input is correct behaviour; the goal is to stop producing bad input.

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

---

# Implementer instructions (Codex)

Line-level instructions. The diagnosis above is done — do not redo it. **This
change will be code-reviewed before merge**, and the review checklist is §I6.

Work on a branch. **Open a PR and stop. Do not merge.**

## I0. Before you touch anything

```bash
# 1. Check Ollama. I2b/I3 need it; I1 does NOT (see I7).
curl -s http://localhost:11434/api/tags        # empty output = not running

# 2. Disable two live-effect flags in backend/.env for the duration, and say
#    in the PR that you did. With SCHEDULER_ENABLED=true, starting the backend
#    runs live ingestion that moves the corpus under your own measurement;
#    with TELEGRAM_NOTIFICATIONS_ENABLED=true the planner can send REAL messages.
SCHEDULER_ENABLED=false
TELEGRAM_NOTIFICATIONS_ENABLED=false

# 3. Baseline the feed gate — it must read the same at the end.
cd backend && .venv/Scripts/python.exe scripts/feed_ground_truth.py gate
# expect: GATE PASSED, Guy 98.3% / 18.0%, casual_deni_fan 91.7% / 0.8%
```

## I1. Make the real failure visible — do this first, alone, and commit it alone

**The bug is currently unobservable**, and that is the first thing to fix.
`backend/app/classification/providers.py`, `OllamaProvider.classify_title`
(~lines 188–215) ends with:

```python
        except httpx.ConnectError as exc:
            self.last_failure_was_connect_error = True
            logger.warning("Ollama not reachable for %r: %s", title[:60], exc)
            return None
        except Exception as exc:
            logger.warning("Ollama classify failed for %r: %s", title[:60], exc)
            return None
```

**There are two distinct paths to a failure today and they are indistinguishable:**

1. An exception — `httpx.ReadTimeout`, `raise_for_status()` HTTP error, or a
   `KeyError` on `data["message"]["content"]` — caught by `except Exception`.
2. **No exception at all**: `parse_and_validate_llm_json(raw_content)` returns
   `None` cleanly when the JSON will not parse. This path never raises.

Path 2 is the likely one, because the HTTP call demonstrably completes in ~4.4s.

**Do:**

- Replace the catch-all with typed handlers that record a **distinct failure
  reason** on the provider — alongside the existing
  `last_failure_was_connect_error`, add something like `last_failure_reason`
  taking `connect_error` / `timeout` / `http_error` / `bad_response_shape` /
  `unparseable_json` / `none`. Reset it at the top of `classify_title`, exactly
  as `last_failure_was_connect_error` is reset today (line ~189).
- Distinguish path 2: check the parse result explicitly rather than returning it
  blind, so `unparseable_json` is recorded when it is `None`.
- **Capture what the model actually returned.** `validation.py::_parse_raw`
  already logs `"Could not parse LLM JSON: %r"` with `raw_content[:200]`, which
  is the single most valuable artifact in this task. Make sure that content
  reaches your report — log length too, and whether the string ends mid-token.

**Then carry the reason into the metrics.** `backend/app/ingestion/ingestion_service.py`
~line 487:

```python
                elif cb == "rules_fallback_after_llm_failure":
                    llm_attempts += 1
                    if _LLM_PROVIDER.last_failure_was_connect_error:
                        llm_fallback_connect_error += 1
                    else:
                        llm_fallback_timeout_or_parse += 1
```

Split `llm_fallback_timeout_or_parse` into distinct counters. **Keep the old key
present in the persisted metrics payload** (as the sum, or explicitly zero) —
`metrics` rows are already persisted for 6 historical runs and
`docs/qa/` artifacts read them; do not break their shape. Add a
`schema_version` bump if the existing payload carries one (it does:
`"schema_version": 1`).

**Commit this alone, and run it.** The numbers it produces determine I2. Report
them in the PR before the fix commit.

## I2. Test the leading hypothesis

`providers.py` ~line 198:

```python
"options": {"temperature": 0, "num_predict": 500},
```

**Hypothesis:** the model's JSON exceeds 500 tokens, gets truncated mid-structure,
and then cannot be parsed — every time, after a consistent generation duration.
This matches all four observed facts: ~100% failure, uniform ~4.4s latency, zero
connect errors, and a 30s timeout that is never reached.

It is further supported by the parser's own fallback: `_parse_raw` retries with
`re.search(r"\{.*\}", ...)`, which **requires a closing brace**. Truncated JSON
has none, so both parse attempts fail.

**Test it, do not assume it.** Raise or remove `num_predict`, re-run, and measure.
If the raw content captured in I1 shows complete, well-formed JSON, the hypothesis
is wrong — say so and follow the evidence you actually have.

## I2b. HOW to measure — read this before looking for a harness

**You do not need ingestion, and you must not use the benchmark endpoint.**

⚠️ `POST /api/dev/llm-gating-benchmark` (`routes_dev.py:188`) **deletes all RSS
articles and ingestion runs twice per run, by design.** It refuses to touch the
protected corpus unconditionally. **Do not try to get past that guard.** Setting
`ALLOW_CORPUS_DB_RESET=true` against the real DB would destroy 1,443 articles and
256 hand-ratings. It is the wrong tool for this task regardless.

Live ingestion is also the wrong tool: it hits the network, is non-reproducible,
and adds rows to the corpus while you are measuring it.

**What you actually need is far simpler.** The thing under test is one function —
`OllamaProvider.classify_title` — so call it directly on real titles, read-only:

```python
# backend/scripts/llm_failure_probe.py  (write this; it is part of the deliverable)
# READ-ONLY. Opens no write transaction, triggers no ingestion, sends nothing.
import sys; sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv(".env", override=False)
from app.db.database import SessionLocal
from app.repositories import article_repository
from app.classification.service import ...      # build the configured provider

with SessionLocal() as session:
    articles = article_repository.get_rss_articles(session)

# A fixed, reproducible slice — same articles before and after the fix.
sample = sorted(articles, key=lambda a: a.id)[:60]
for article in sample:
    result = provider.classify_title(
        title=article.translated_title or article.title,
        language="he",
        subtitle=article.subtitle,
    )
    # record: result is None or not, provider.last_failure_reason, latency,
    # and for unparseable_json the RAW CONTENT and its length
```

Report the outcome histogram over that fixed slice, before and after. Because the
slice is fixed and `temperature=0`, the comparison is meaningful.

**Requirements for the probe:**

- Read-only. It must never open a write transaction against
  `backend/data/signal_sports.db`, and must never call anything in `routes_dev.py`.
- Deterministic slice — same article ids each run, so before/after is comparable.
- Capture the **raw model output** for every parse failure, with its length. That
  artifact is the point of the whole task.
- Commit it. The next person needs to reproduce your numbers.

Ollama must be running (`curl -s http://localhost:11434/api/tags`). If it is not,
you will get `connect_error` for everything — a different failure from the one
under investigation, and the data says connect errors are currently **zero**.

## I3. Fix

Target: **LLM success rate ≥ 80%** (from 33.6%). Report before/after from a real run.

**Forbidden fixes — these will fail review:**

- **Do NOT loosen `parse_and_validate_llm_json` or `_parse_raw` to accept
  malformed output.** The validator rejecting bad input is correct behaviour. The
  goal is to stop producing bad input. Note it already falls back to safe defaults
  for every invalid *enum* and only returns `None` for genuinely unparseable JSON —
  that boundary is right, leave it.
- **Do NOT make the model guess more confidently.** Abstention is a designed
  success mode in this project; a confidently wrong fact reaches the preference
  layer as truth, while `unknown` does not.
- **Do NOT touch `gating.py`.** The call rate is 51.9% against a ≤25% target and
  that is real, but tuning the gate while two thirds of calls fail would bake
  today's brokenness into the thresholds. It is explicitly out of scope here.
- **Do NOT change the prompt's semantics** to shorten output unless you show that
  output length is the cause AND that the shortened prompt does not change what
  the model classifies. Prompt content is #65's scope.

## I4. ⛔ The trap that will fail this task outright

**NEVER run a blanket re-classification or backfill of the corpus.**

`docs/qa/N05_FEED_GROUND_TRUTH.md` finding **F-N05-6**: of 34 measured false-hides
re-run through fresh rules-only classification, **12 were degraded** — `sport` fell
from `basketball` to `unknown` — because those rows carry LLM-assisted facts a
rules-only pass cannot reproduce. **The stored row is often better than what a
re-run would write.**

`backend/data/signal_sports.db` is irreplaceable replay evidence: **1,443 articles,
256 of them hand-rated**, and the #189 gate baseline stores per-item decisions
keyed by those article ids. A backfill would silently invalidate every measurement
this project has made.

**This fix must change NEW ingestion only.** Stored rows stay exactly as they are.
If you want to see the fix working on real articles, ingest **into a copy**:

```bash
cd backend
.venv/Scripts/python.exe scripts/backup_db.py     # then point DATABASE_URL at the copy
```

## I5. Verification — all four are required in the PR

1. **Failure-reason breakdown** over the fixed I2b slice, before and after.
2. **Success rate** before and after, with attempt counts, from the same slice.
   State explicitly that no ingestion ran and no network article fetch occurred.
3. **Feed gate unchanged**: `scripts/feed_ground_truth.py gate` → `GATE PASSED`,
   Guy 98.3% / 18.0%, `casual_deni_fan` 91.7% / 0.8%. This change is
   **decision-neutral by design** — it does not touch stored facts, so any gate
   movement means something unintended happened. Investigate rather than accept it.
4. **Suites green**: backend `pytest tests -q` (baseline **2,549 passed, 1
   skipped**); frontend only if you touched it (**539 passed**).

Add tests for the new failure-reason classification — each branch
(`timeout`, `http_error`, `bad_response_shape`, `unparseable_json`,
`connect_error`) with a mocked provider response. The house pattern is pure
logic + mocked transport; `backend/tests/` has many examples. **Never let a test
reach the live corpus or a real Ollama** — `conftest.py` pins
`CLASSIFICATION_PROVIDER=disabled` and a temp DB; keep it that way.

## I7. Running this unattended

This may be run overnight with nobody watching. **Never block waiting for input,
and never end the night with nothing committed.**

### Definition of done, in order

| | Deliverable | Needs Ollama? |
|---|---|---|
| **Minimum** | I1 committed: typed failure reasons, split metrics, tests | **No** |
| **Good** | I2b probe committed + the before-measurement, including the raw failing output | Yes |
| **Ideal** | I3 fix + after-measurement showing the success rate | Yes |

**I1 is pure code work and needs no Ollama, no network and no running server.**
Do it first, always. It is the commit that makes the bug observable, and it has
standalone value even if nothing else lands.

### If Ollama is not running

**Do not wait for it and do not try to start it.** Complete I1 in full — including
its tests — commit it, open the PR, and say plainly in the description that I2b
and I3 could not be measured because the provider was unavailable. That is a
successful night, not a failed one.

### If the I2 hypothesis is wrong

The `num_predict` theory is a hypothesis, not a finding. If the raw output
captured in I1/I2b turns out to be complete, well-formed JSON, then truncation is
not the cause.

**That is a result, not a blocker.** The raw failing output plus the failure-reason
breakdown is the single most valuable artifact this task can produce, because it
tells the next person exactly what is wrong. Commit it, report it, and stop before
inventing a fix for a cause you have not established.

### Rules for an unattended run

- **Never** set `ALLOW_CORPUS_DB_RESET`, call any `/api/dev/*` endpoint, or write
  to `backend/data/signal_sports.db`. There is no situation in this task where
  any of those is the right move.
- **Do not expand scope to fill time.** If I1–I3 finish early, stop. Do not start
  on `gating.py`, the prompt, or the call rate — all explicitly out of scope (I3),
  and all much easier to get wrong without review.
- **Do not merge.** Open the PR and stop.
- Leave `SCHEDULER_ENABLED=false` and `TELEGRAM_NOTIFICATIONS_ENABLED=false` in
  place for the duration, and state in the PR what you set and whether you
  restored it.
- Commit incrementally. A night that ends mid-task should still leave reviewable
  commits behind.

## I6. What the code review will check

State each of these in the PR description so review is fast:

- [ ] I1 committed **separately** from the fix, with its measured output
- [ ] Failure reasons are distinct and each is covered by a test
- [ ] The persisted metrics payload stays backward-compatible for the 6 existing runs
- [ ] `_parse_raw` / `parse_and_validate_llm_json` **not loosened**
- [ ] `gating.py` **untouched**
- [ ] **Zero writes to `backend/data/signal_sports.db`** — no backfill, no reclassify, no reset
- [ ] Gate output pasted, unchanged
- [ ] Before/after success rate with attempt counts, from a real run
- [ ] The raw model output that was failing to parse, quoted in the PR
- [ ] `SCHEDULER_ENABLED` / `TELEGRAM_NOTIFICATIONS_ENABLED` handling stated
- [ ] The I2b probe committed, read-only, over a fixed reproducible slice
- [ ] `ALLOW_CORPUS_DB_RESET` never set; `/api/dev/*` never called

**If the hypothesis in I2 is wrong, that is a fine outcome** — report what the
evidence actually shows rather than guessing at a fix. Three issues in this
project (#190, #193, #208) were re-scoped or closed on well-evidenced refutations,
and each saved real work.

**A blocked step stops THAT STEP, not the run.** See I7.
