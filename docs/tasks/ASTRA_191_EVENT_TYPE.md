# Task brief — Make event-type classification actually discriminate (issue #191)

You are working on **Signal Sports**, a personalized sports-news intelligence feed
(Hebrew-first, FastAPI + SQLite backend, React frontend). Repo root contains
`CLAUDE.md` (product context) and `docs/`. Assume **no prior conversation
history** — everything you need to start is below.

Work on a branch. **Open a PR and stop. Do not merge to `main`.**

---

## 1. Why this task is the highest-leverage work in the project

On 2026-09-05 the feed's quality was measured against human ground truth for the
first time: **282 real corpus items, hand-rated by the product owner blind to the
engine's decision**, across two profiles. Read
`docs/qa/N05_FEED_GROUND_TRUTH.md` in full before starting.

The measurement **inverted the project's working assumption.** Everyone believed
the feed was noisy. It is not:

| Metric | Guy (basketball power user) | casual_deni_fan |
|---|---|---|
| **Precision on what is shown** | **98.2%** (112/114) | **91.7%** (22/24) |
| **False hide** (weighted) | **18.2%** | 0.8% |
| False show | 0.4% | 0.1% |
| Push precision | **41.2%** (7/17) | never fires |

The failures are **recall** and **push**, not noise.

### The root cause you are fixing

`event_type` is the load-bearing axis of the entire decision model. Every
preference affinity, every `always_push` override, and every clustering time
window is keyed on it. And it is **degenerate**: the classifier's generic bucket,
`news`, swallows most of the corpus.

- **86 of Guy's 185 rated items are `news`**, and **20 of his 34 false-hides**.
- For `casual_deni_fan` it is the whole story: **19 of his 24 visible items are
  `news`**. His visible feed is `news`×19, `signing`×3, `release`×1,
  `negotiation`×1. Nothing else.

The consequence is precise and verifiable. `casual_deni_fan`'s profile
**already contains the right rules** (`backend/app/seed/seed_profiles.py`):

```python
OverrideRule(kind="always_push", scope="player", target_id="player:deni_avdija", event_type="major_trade"),
OverrideRule(kind="always_push", scope="player", target_id="player:deni_avdija", event_type="injury"),
```

Those have **never fired on the real corpus** — the `push` stratum population is
literally 0. Not because the rules are wrong, but because **no article was ever
both resolved to Deni and classified `major_trade` or `injury`.** A report of a
possible move to Oklahoma and a jab from Ja Morant both land in `news` and both
come out `high_feed`. `CLAUDE.md` requires exactly that distinction
(`deni_trade` → push, `deni_news` → high_feed) and the event layer cannot express
it.

> **`news` is not a classification of an event. It is the absence of one.**
> Because every downstream layer is keyed on event type, the generic bucket
> silently disables all of them.

A separate measured finding confirms this is the real problem for that profile:
**15 of his 24 visible items are over-ranked** (engine `high_feed`, owner rated
`feed`). A previous investigation (#193) tested the competing hypothesis — that
those items were entity *mentions* wrongly treated as subjects — and **refuted
it**: only 2 of the 24 were unwanted, and two of the three headlines cited as
evidence turned out to be items the owner actively wants. The over-ranking is an
event-type problem, not an attribution problem.

---

## 2. Your objective

**Event-type classification discriminates the developments the product exists to
distinguish — above all transfer/trade *movement* versus routine coverage — so
that the preference rules that already exist can act.**

Measured by **rule-firing on the real corpus**, not by classifier self-report.

---

## 3. The gate — your self-verification instrument

This is why this task can run unattended. A directional regression gate scores
the engine against those 282 human ratings:

```bash
cd backend
.venv/Scripts/python.exe scripts/feed_ground_truth.py gate      # exit 0 / 1
```

Run it **before you start** (confirm a clean baseline) and after every
behaviour-changing step. Read `docs/RELEVANCE_CONTRACT.md` §"Quality gate" for
the full rules. Summary:

| Check | Rule | Slack |
|---|---|---|
| `shown_precision` | of what the user sees, how much did they want? | one rated item (`1/n`) |
| `false_hide` | how much did they want and never see? | **none** |
| `push_precision` | were the interruptions justified? | one rated push (`1/n`) |
| `push_volume` | may not rise | **none**, unless precision improved |
| `casual_deni_fan.no_drift` | the canary profile must not move | **none** |

**⚠️ The metric trap.** Never report overall accuracy. It is dominated by the
hidden majority: `casual_deni_fan` scores 98% exact agreement while hiding 98.3%
of the corpus, so agreeing with "hidden" on football scores beautifully and says
nothing. **Always report `shown_precision` and `false_hide` together.**

The gate exists because this exact failure mode is easy to hit: a synthetic
"improve recall" change once took `false_hide` 19.4% → 11.4% while
`shown_precision` collapsed to 83.5%. A recall-only check would have passed it.

**`casual_deni_fan.no_drift` will fail for this task, and that is expected** —
you are deliberately changing that profile's outcomes. Use
`gate --accept casual_deni_fan.no_drift --reason "<why>"` and state the
justification. Do **not** regenerate the baseline to clear a red gate.

---

## 4. Scope

### 4.1 Measure the bucket first — post the census before designing

Across the **whole corpus** (1,427 scored RSS rows, not just the 282-item sample): how many
rows are `news`, broken down by **sport**, by **source**, and by
**classification method** (`rules` / `llm` / `llm+rules_guardrail` /
`rules_fallback_after_llm_failure`). Establish whether `news` is a rules gap, an
LLM gap, or both.

**Do this first and write it down.** A sibling issue (#190) was scoped on an
assumption about its root cause, and the diagnosis proved the assumption wrong —
24 of 25 rows failed for a completely different reason than the ticket claimed.
Diagnose, then design.

### 4.2 Sub-classify what is recoverable

The event types needed for the Deni case **already exist** in the taxonomy
(`major_trade`, `injury`, `rumor`, `candidate`, `negotiation`, `release`, …) —
see `backend/app/classification/validation.py` and
`backend/app/classification/prompt.py`. The question is why headlines reporting
them land in `news` instead. Expect a mix of:

- **Hebrew transfer/trade/rumour vocabulary coverage** in the deterministic rules.
- **The LLM prompt offering `news` as a free escape.** `prompt.py:16` presents a
  flat list of 15 event types with `news` among them and no guidance discouraging
  it as a default. This is the cheapest hypothesis to test and it is already
  recorded on issue #65.

### 4.3 Decide explicitly whether `news` should remain reachable

**This is the design decision at the heart of the task. State it in the PR with
its trade-off.**

The tension is real and you must not resolve it by accident:

- A classifier that cannot say "I don't know" is worse than one that can.
  **Abstention is a designed success mode in this project**, not a bug (see the
  invariants in §6).
- But an escape hatch that swallows 46% of one profile's items is not abstention,
  it is a default.

Acceptable outcomes include: keeping `news` as a genuine last resort that records
*why* it was chosen; or making it unreachable for headlines that carry
recoverable evidence. What is **not** acceptable is leaving it as an unexplained
default, or forcing confident guesses to make the number go down.

### 4.4 Respect event semantic evidence

New event assertions need real evidence
(`backend/app/classification/event_evidence.py`). **Do not loosen assertion
semantics or certainty thresholds to make event types fire** — that reintroduces
the false-push failure mode that an earlier reliability epic (#58) was created to
fix. If an event type cannot be asserted on the available evidence, that is a
finding to report, not an obstacle to route around.

### 4.5 Check the clustering interaction — do not discover it by surprise

`news` **is** in `CLUSTERABLE_EVENT_STATES`
(`backend/app/clustering/config.py`), under strict same-state matching. Moving
articles out of `news` into specific states **will** change clustering.

Measure cluster counts before and after, per profile, and explain any change.
This is likely relevant to the push-duplication problem (§8) and must not be
stumbled into there.

---

## 5. Acceptance criteria

- [ ] Corpus-wide `news` census posted (by sport, source, classification method)
      **before** implementation
- [ ] The `news` design decision stated explicitly, with its trade-off
- [ ] **At least one `always_push` rule on `casual_deni_fan` demonstrably fires
      on a real corpus article that deserves it.** This is the concrete proof the
      flat scale is fixed — name the article and show the trace
- [ ] Gate: **`false_hide` drops** and **`shown_precision` does not**. Report both
      numbers for both profiles, before and after
- [ ] `casual_deni_fan` over-ranking (15 of 24 visible were over-rated)
      measurably improves
- [ ] Push volume for Guy does **not** rise without a precision gain
- [ ] Cluster counts before/after reported, with any change explained
- [ ] Golden-15 fixtures, `docs/fixtures/profile_parity.json`, and the event
      semantics tests all green
- [ ] Full backend suite green (baseline: **2502 passed, 1 skipped**); frontend
      `npm run test`, `lint`, `typecheck`, `build` green if you touch it

---

## 6. Hard invariants — violating any of these fails the task

- **⛔ NEVER run a blanket rules-only backfill of the corpus.** Of 34 measured
  false-hides re-run through fresh rules-only classification, **12 were
  degraded** (`sport`: `basketball` → `unknown`), because 15 of those rows were
  originally classified with LLM assistance a rules-only pass cannot reproduce.
  **The stored row is often better than what a backfill would write.**
- **The live corpus DB (`backend/data/signal_sports.db`) is irreplaceable replay
  evidence.** Never reset or delete it. Back up before any write
  (`backend/scripts/backup_db.py`). Corrections must be **targeted**,
  dry-run-by-default, idempotent, and hand-verified — follow the pattern in
  `backend/scripts/apply_190_entity_corrections.py`.
- **FACTS → VISIBILITY → PREFERENCE → LEARNING separation**
  (`docs/RELEVANCE_CONTRACT.md`). A recall failure caused by a wrong *fact* is
  fixed in classification, **not** compensated for in the preference layer. Do
  not add broad `news` affinity rules to a profile to paper over a classification
  gap — that would re-admit the noise the 98% precision currently earns.
- **Entity abstention is a designed success mode.** Bare family names
  (`בהפועל` — which Hapoel?), cross-sport aliases (`מכבי תל אביב` is both a
  football and a basketball club), and guarded entities correctly resolve to
  nothing. Do not weaken this.
- **Push stays rare.** No change may increase push volume without a measured
  precision improvement.
- **`primary_competition` is explicit-evidence-only** by contract (#28). Do not
  populate it from inference — that opens the RC-4 hazard of promoting a
  background mention to the article's competition.
- **No new event types** in the taxonomy without an explicit, stated decision.
  Prefer routing to existing types.

---

## 7. Mechanisms that will otherwise cost you hours

These were established the hard way. Trust them.

1. **Membership reach reads canonical `entity_ids` ONLY.** The v2 scorer matches
   competitions through four tiers (`match_competition_names` in
   `backend/app/services/relevance_engine.py`): explicit → legacy → participant
   inference → membership. The **legacy** tier requires `taxonomy_version is
   None`, and **no corpus row qualifies** — all 1,427 are post-ArticleFacts. So
   setting the legacy `entities` names, or `article.league`, produces **zero**
   decision changes. Only `entity_ids` moves anything.
2. **Profiles are DB rows, not code.** `seed_all_if_empty` means editing
   `backend/app/seed/seed_profiles.py` does **not** reach the live corpus. A
   profile change requires a mutation through the API/service layer. Budget for
   this if your design needs one.
3. **A full resolver/classifier re-run over the corpus touches ~173 rows** for
   reasons unrelated to any one change. Scope every corpus correction to exactly
   what your change touches, or you are running the blanket backfill that is
   banned above.
4. **Title vs subtitle is strong evidence about subject-hood.** When correcting
   stored rows, title evidence proved a reliable proxy for "this is what the
   story is about"; subtitle-only matches were opponents, former clubs, and
   incidental mentions. Consider it when scoping writes.
5. **Scoring is computed at read time**, so relevance-layer changes show up
   without re-ingesting. Classification changes affect only **new** rows until
   stored rows are corrected.
6. The `score --live` subcommand scores the ratings against **current** engine
   decisions rather than the ones frozen into the sample — that is what answers
   "did my change improve things?".

---

## 8. Stretch goal — diagnosis only, do not implement

If #191 lands cleanly and time remains, produce a **diagnosis** (not a fix) for
the push-duplication problem, issue #192:

Guy received **22 push notifications covering roughly 8 stories**. Lundberg
appears in 5 separate pushes, Yam Madar in 4, Lonnie Walker in 3 — **12 of 22
notifications were 3 stories.** Only **1 of the 22 carried a cluster card**,
despite `CLUSTERING_ENABLED=true`.

Note what this is **not**: the event-state gate is not the cause — `signing`,
`negotiation` and `news` are all clusterable. Candidate explanations to test
rather than assume: clustering ran after the push decision; the planner's
member-lineage identity (#151) does not consult cluster membership; anchor or
similarity did not actually merge these articles; or the saga spans days beyond
the per-state time window.

Trace all 22 and post which stage is responsible. **Do not build the fix** — and
re-diagnose rather than reusing this analysis if your #191 work changed
clustering (§4.5).

If time does **not** remain, stop and say so. A clean #191 with an honest "did
not start the stretch goal" is a better outcome than two half-finished pieces.

---

## 9. Process

- Project skills encode the house workflow — use them:
  `signal-classification-change` (the primary one here),
  `signal-real-data-qa` (before/after decision diffs on the real corpus),
  `signal-doc-truth` (which doc is authoritative for which subsystem),
  `signal-pr-finish` (the completion check before presenting).
- Keep the docs true. `docs/RELEVANCE_CONTRACT.md`,
  `docs/CURRENT_PROJECT_STATE.md`, `docs/ARTICLE_FACTS.md` and
  `docs/qa/N05_FEED_GROUND_TRUTH.md` are living contracts; superseded docs are
  history and must not be "fixed".
- **Ratchet the gate baseline only at the very end**, only if the gate passes
  cleanly, and record the justification in the commit — it redefines what every
  future change is measured against.
- **Report honestly.** If part of this is blocked, or if the diagnosis in §4.1
  contradicts the framing in §1, **say so plainly and explain what you found**
  rather than forcing the scope. A well-evidenced refutation is a valuable
  result — #193 was closed on exactly that basis, and it saved building the wrong
  thing.
- Open a PR describing what moved, in both directions, with the gate output.
  **Do not merge.**

---

## 10. Orientation

| Path | What it is |
|---|---|
| `CLAUDE.md` | Product context and principles |
| `docs/qa/N05_FEED_GROUND_TRUTH.md` | **The measurement. Read first.** |
| `docs/RELEVANCE_CONTRACT.md` | Decision semantics + the quality gate |
| `docs/CURRENT_PROJECT_STATE.md` | Cold-start orientation |
| `docs/audits/2026-09-05.md` | Repository audit (findings N01–N07) |
| `backend/app/ingestion/classifier.py` | Classification entry point (>1000 lines) |
| `backend/app/classification/` | Facts, event evidence, validation, LLM prompt |
| `backend/app/services/preference_engine.py` | The v2 scorer (`score_article_v2`) |
| `backend/app/services/relevance_engine.py` | Visibility + competition matching |
| `backend/app/seed/seed_profiles.py` | The two demo profiles (seed values) |
| `backend/scripts/feed_ground_truth.py` | `baseline` / `sample` / `score --live` / `gate` |
| `backend/app/qa/feed_quality_gate.py` | The gate's pure comparison logic |
| `docs/qa/n05_gate_baseline.json` | The frozen reference the gate compares to |

Run the backend suite with:
`cd backend && .venv/Scripts/python.exe -m pytest tests -q`
