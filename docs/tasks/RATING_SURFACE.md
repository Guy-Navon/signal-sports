# Task brief — a fast rating surface for the fresh-cohort census

> **Status (2026-09-16): delivered.** `backend/scripts/rate_census.py` — `build`
> writes the census (`docs/qa/census_sample.json`), `serve` opens a local
> single-keypress page and writes `docs/qa/census_ratings.json` after every
> rating. Pure logic + tests in `backend/app/qa/census_rating.py` /
> `backend/tests/test_census_rating.py`. The fresh cohort is 91 articles today;
> re-run `build` after more accumulate — rated ids are kept, only unrated ones
> are asked.

Signal Sports is a personalized Hebrew sports-news feed (FastAPI + SQLite backend,
React frontend). Repo root has `CLAUDE.md` and `docs/`. Assume **no prior
conversation history**.

Work on a branch. **Open a PR and stop. Do not merge.**

---

## Why this exists

The project's feed quality is measured against **human ground truth**: the owner
rates real articles, blind to what the engine decided, and the ratings are scored
against engine decisions. That measurement (`docs/qa/N05_FEED_GROUND_TRUTH.md`) is
the instrument every feed change is judged by.

The existing 282 ratings are now **stale**: they describe an older classification
pipeline, on a corpus frozen at 2026-07-31, classified by an LLM that was failing
two calls in three. That LLM is fixed (failures 65% → 3%) and the pipeline has
changed substantially, so the numbers no longer describe the product.

A **fresh cohort** is accumulating now. It needs re-rating, and **the owner's
rating time is the bottleneck for the entire milestone.**

> **Your job is to make rating ~300 articles take about 25 minutes instead of
> hours.** That is the whole deliverable. Everything else is secondary.

---

## The one rule that must not be broken

**The rater must never see the engine's decision.** `feed_ground_truth.py` says it
plainly about the existing sample:

> *"The engine's answer travels with the sample so `score` can compare, but the
> rating surface must NOT show it — a rater who sees the answer is no longer
> ground truth."*

Do not display, hint at, or order by: `engine_decision`, `matched_topic`,
`matched_event_rule`, the feed rank, or anything derived from them. Present the
article as a reader would meet it.

Ordering must not leak the answer either — **shuffle with a fixed seed** so the
run is reproducible but the order carries no signal.

---

## What to build

A local rating tool over the fresh cohort. **A terminal TUI or a tiny local web
page are both fine** — pick whichever you can make genuinely fast. Optimise for
seconds-per-article, not for looks.

### What the rater sees, per article

- **title** (`translated_title` or `title`) — large, readable Hebrew, RTL
- **subtitle** — it carries decisive evidence surprisingly often
- **source** and **published_at**
- progress: `47 / 312`

Nothing else. In particular, no sport, league, event type or entities — those are
engine facts and seeing them biases the rating.

### The rating scale

Exactly these five, which map onto the product's decision ladder:

| key | rating | meaning |
|---|---|---|
| `5` | `push` | interrupt me on my phone |
| `4` | `high` | important, top of the feed |
| `3` | `feed` | normal relevance |
| `2` | `low` | visible but low priority |
| `1` | `hide` | do not show me this |

**Single keypress, no Enter, no mouse.** That is the difference between 25 minutes
and two hours. Add `u` to undo the last rating and `q` to save and quit.

### Requirements

- **Read-only against the corpus.** Never open a write transaction on
  `backend/data/signal_sports.db`, never call `/api/dev/*`, never set
  `ALLOW_CORPUS_DB_RESET`. This tool reads articles and writes its own JSON.
- **Resumable.** Save after every rating. Re-running picks up where it stopped and
  never re-asks a rated article. Interrupting must never lose work.
- **Census, not sample.** Every article in the fresh cohort, no stratification.
- **Fresh cohort = articles published after a cutoff** — `--since`, defaulting to
  `2026-08-01`. The pre-cutoff corpus is the old frozen one and must be excluded.
- Rate for **`guy`** only by default. `casual_deni_fan` is a synthetic demo persona
  and doubling the work is not worth it; add `--profile` if it is cheap, but do not
  make it the default path.

---

## Output format — must drop straight into the existing tooling

Two files, matching what `backend/scripts/feed_ground_truth.py` already consumes,
so no conversion step is ever needed.

**1. Ratings** — same shape as `docs/qa/n05_ratings.json`:

```json
{"generated": "<iso>", "seed": <int>,
 "ratings": {"guy": {"rss_abc123": "feed", "rss_def456": "hide"}}}
```

**2. A census "sample"** — same shape as `docs/qa/n05_sample.json`, because `score`
reads strata and weights from it. A census has no sampling, so emit **one stratum
with `weight: 1.0`**:

```json
{"meta": {"seed": <int>, "corpus_articles": <n>, "generated_at": "<iso>"},
 "profiles": {"guy": {
    "strata": {"census": {"population": <n>, "sampled": <n>, "weight": 1.0}},
    "items": [{"id": "...", "stratum": "census", "engine_decision": "...",
               "matched_topic": null, "matched_event_rule": null,
               "title": "...", "original_title": "...", "source": "...",
               "sport": "...", "league": null, "event_type": "...",
               "published_at": "...", "url": "..."}]}}}
```

Populate `engine_decision` and the fact fields from the engine **for the scorer's
use** — just never show them to the rater.

**Verify the integration yourself**: after producing both files, run

```bash
cd backend
.venv/Scripts/python.exe scripts/feed_ground_truth.py score \
  --ratings <your_ratings.json> --sample <your_census.json> --live
```

and paste the output in the PR. If it does not run clean, the format is wrong.

**Weights are 1.0 on purpose.** The old stratified sample gave one hidden-football
row a weight of ~55.9 against ~4.2 for basketball — a 13x difference that made the
headline number unable to resolve basketball work at all. A census removes
weighting entirely, and that is a large part of why we are re-rating.

---

## ⛔ Do not

- **Write to the corpus DB.** It is irreplaceable replay evidence — 1,518 articles.
- **Overwrite `docs/qa/n05_ratings.json`, `n05_sample.json` or
  `n05_gate_baseline.json`.** Those are the existing gate's substrate; this is a
  **new, separate** measurement. Write new files.
- **Change any classification, relevance or scoring logic.** This is a tool, not a
  product change. The feed gate must read identically before and after:
  `scripts/feed_ground_truth.py gate` → `GATE PASSED`, Guy 98.3% / 18.0%.
- Show the rater anything the engine concluded.

---

## Verification for the PR

- [ ] Gate unchanged (paste the output)
- [ ] Backend suite green — baseline **2,549 passed, 1 skipped**
- [ ] `score --live` runs clean on your two output files (paste it)
- [ ] Corpus untouched: article count and last-ingestion timestamp identical
- [ ] Demonstrate resume: rate a few, kill it, restart, confirm it continues and
      re-asks nothing
- [ ] State your measured **seconds per article** on a short self-test run

Tests: the file I/O, resume logic and the rating→tier mapping are pure and should
be covered. `backend/tests/conftest.py` pins a temp DB and
`CLASSIFICATION_PROVIDER=disabled` — keep it that way; no test may reach the live
corpus.

## Orientation

| Path | What |
|---|---|
| `backend/scripts/feed_ground_truth.py` | `baseline` / `sample` / `score --live` / `gate` — read `cmd_sample` for the item shape and the blind-rating rationale |
| `docs/qa/n05_ratings.json`, `n05_sample.json` | The formats to match |
| `docs/qa/N05_FEED_GROUND_TRUTH.md` | What the measurement is for |
| `backend/app/repositories/article_repository.py` | `get_rss_articles(session)` |
| `backend/app/services/feed_service.py` | `build_feed(...)` for `engine_decision` |

Run the backend suite with
`cd backend && .venv/Scripts/python.exe -m pytest tests -q`.
