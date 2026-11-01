# Relevance Contract — Decision-Level Semantics (issue #35)

**2026-09-11 - Feed-quality changes (#191/#192).** Explicit transfer/injury
push overrides now require factual attention evidence on newly ingested or
reviewed rows: current agreement/completion, imminent renewal, or current injury,
with the followed team/player as a title subject. Historical rows lacking this
metadata retain their old behavior. Normal visibility and affinities remain
separate. Relocation player overrides additionally require factual participant
IDs; only Deni's profile gains the authorized relocation rule. See
[implementation, gate results and unmet targets](qa/N05_FEED_QUALITY_IMPLEMENTATION.md).
The N05 gate still counts push ARTICLES; actual planner STORIES are reported
separately. No semantic threshold or gate policy was relaxed.

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
  → freshness window (consumer feeds only: published_at within
    FEED_MAX_AGE_HOURS=36; expired articles never scored, Debug unaffected)  [docs/FEED_FRESHNESS.md]
  → visibility matching (four-tier competition matching, entity_ids-first)   [docs/RELEVANCE_VISIBILITY_CONTRACT.md]
  → preference scoring (ProfileV2 affinity layers, contribution trace)       [docs/PREFERENCE_MODEL_V2.md]
  → learned adjustments (derived from feedback events at read time)          [docs/FEEDBACK_LEARNING.md]
  → DECISION: hidden | low_feed | feed | high_feed | push
```

## Architecture invariants (bind every change)

These were set by the Signal Intelligence Architecture v2 initiative (Epic #27, closed
2026-07-08; its roadmap document was retired on 2026-10-12, and its history is in git and on
Milestone 1).

- **The LLM reduces uncertainty; it does not define truth.** Deterministic evidence resolves
  first: source URL hints, canonical aliases, competition names, taxonomy relations. The LLM
  is called only on residual ambiguity, as a candidate generator, and its proposals always pass
  normalisation and semantic validation. Abstention (`sport=unknown`, no entity, `news`) beats
  guessing.
- **LLM optionality.** The product stays useful with `CLASSIFICATION_PROVIDER=disabled`. The
  no-LLM path is first-class.
- **Facts ≠ personalization.** Classification answers "what is this article about", and the
  relevance engine answers "how much does this user care". User preferences never
  contaminate article facts.
- **Competition model, three distinct relations.** `primary_competition` is what the article
  is about, from explicit evidence only. `article_competitions` holds additional explicitly
  evidenced competitions. Entity **memberships** are taxonomy data only: membership reach is
  computed at scoring time and never persisted per article. Team-anchored events (signing,
  injury, roster) reach all of a team's competitions. Competition-anchored events (results,
  titles, schedules) reach explicit competitions only.
- **Push discipline.** `push` comes only from an explicit rule, and boosts cap at `high_feed`
  (detail below).
- **Decision contracts.** "Globally important" is never a visibility reason by itself (see
  the decision semantics below).
- **The backend is authoritative for intelligence.** The JS engine
  (`frontend/src/engine/relevanceEngine.js`) is frozen at its legacy feature set for local
  demo mode. No taxonomy, affinity or learning work is ported to it.
- **Taxonomy growth should reduce LLM dependency**, but a lower call rate is never bought with
  accuracy or false-positive control.

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

## Unknown event type (issue #79 — decision-contract lock)

`event_type="news"` is the abstention value (event semantic validation
downgrades unsupported proposals to it). The contract, locked by
`backend/tests/test_decision_contract.py`:

- **Unknown event is NOT a negative signal.** Direct scope matches are
  never event-gated: a followed sport, a followed team/player on the
  article, and tier-1 explicit competition evidence all keep their base
  visibility regardless of event type. The event-affinity delta simply
  resolves to none (personalization precision drops; relevance does not).
- **Unknown event gets no diffuse reach.** `news` is in neither reach
  allowlist (tiers 3/4), so entity-only or membership-based spread to
  followed competitions does not happen (#64 Q2 decision: keep it that way;
  explicit sport/competition follows are the intended coverage floor).
- **Promotion stays capped.** A broad sport follow (level 0) surfaces
  unknown-event articles at `low_feed`; nothing about event uncertainty can
  reach push (override-only, unchanged).

## Event-preference precedence (issue #79 lock)

Two orthogonal rules resolve event affinities, in this order:

1. **Specificity**: a *scoped* entry for the base scope beats a *global*
   entry — even when the scoped entry is calibration-derived and the global
   one is explicit. Scoped calibration nuance intentionally refines broad
   explicit gestures (the one place calibration outranks an explicit value,
   and only across different targets).
2. **Authority**: for the SAME `(scope_ref, event_type)` target,
   source authority wins: explicit > learned > calibration.

## Push discipline

Push requires an explicit rule: legacy `event_rules`/`entity_event_rules`
declaring push, or a v2 `always_push` override. Boosts cap at high_feed.
Calibration and learning can never write push rules.

Measured against human ratings:

- **2026-09-05, frozen corpus** ([qa/N05_FEED_GROUND_TRUTH.md](qa/N05_FEED_GROUND_TRUTH.md)):
  17 Guy pushes at 41% precision. The rejected pushes were mostly rated `feed`, not `hide`:
  real stories that do not deserve a phone buzz.
- **2026-09-11, after #191/#192** ([qa/N05_FEED_QUALITY_IMPLEMENTATION.md](qa/N05_FEED_QUALITY_IMPLEMENTATION.md)):
  7 push articles, all approved, forming 4 notification stories. Push overrides on
  transfer/injury/governance events additionally require factual severity
  (`attention.development`) and the followed scope as a title subject.
- **2026-10-10, fresh cohort, census #2** ([qa/CENSUS_2026-10.md](qa/CENSUS_2026-10.md)):
  the remaining failure is push **recall**. Of 8 owner-rated pushes the engine pushed 1, and 6
  of the 8 were Maccabi institutional stories. `club_governance` (#229) raised this to 2/8 on
  the census rerun.

Push volume and push precision are both gated (see below). Volume may not rise without a
precision gain.

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
  on every Debug row. Since #84, `base_scope` and `event_affinity`
  contributions carry an additive `source` field
  (explicit | calibration | learned — the entry that actually FIRED after
  authority resolution), the Hebrew lines carry the matching label
  (בחירה מפורשת / מכויל / נלמד), and an `event_affinity` step with
  `detail=unknown_event_fallback` makes event abstention explicit in the
  trace. Structured contributions remain the machine-readable contract;
  the narrative is presentation built from them.
- **Shadow comparison**: `GET /api/debug/shadow/{user_id}`.
- **Learning**: `GET /api/learning/{user_id}` explains every learned
  adjustment and its evidence.
- **LLM dependency**: per-run persisted metrics (`docs/LLM_CLASSIFICATION.md`,
  issue #31) — normal gated ingestion only, never forced backfill.

The consumer product surface keeps only the one-line desk voice; full
traces stay in Debug/ops.

## Quality gate — run this before landing a relevance change (issue #189)

The suite proves the engine does what it was told. It does not prove that what
it was told is any good. Two gates answer that question: the N05 gate below, over 282
hand-rated real corpus items ([qa/N05_FEED_GROUND_TRUTH.md](qa/N05_FEED_GROUND_TRUTH.md)),
and the [census gate](#census-gate-254) over every article of an owner-rated census. Run both:

```
cd backend
.venv/Scripts/python.exe scripts/feed_ground_truth.py gate
```

Exit 0 = no regression; exit 1 = blocked, with the failing check named. It
needs the live corpus DB, so it is **local-only — it cannot run in CI.** The
rules it enforces are pure and ARE covered in CI
(`backend/tests/test_feed_quality_gate.py`).

**Read two numbers, never one.** Overall accuracy is dominated by the hidden
majority: `casual_deni_fan` scores 98% exact agreement while hiding 98.3% of
the corpus, so agreeing with "hidden" on football scores well and says nothing.
The gate reports and enforces both directions instead:

| Check | Rule | Slack |
|---|---|---|
| `shown_precision` | of what the user sees, how much did they want? | one rated shown item (`1/n`) |
| `false_hide` | how much did they want and never see? | **none** |
| `push_precision` | were the interruptions justified? | one rated push (`1/n`) |
| `push_volume` | may not rise | **none**, unless precision improved |
| `<profile>.no_drift` | `casual_deni_fan` must not move | **none** |

Baseline: `docs/qa/n05_gate_baseline.json`, generated at `87d3170` (2026-09-11) on the frozen
1,427-article corpus. Guy: 98.3% shown precision / 18.0% false hide / push 7/7. Deni:
91.7% / 0.8% / push 1/1. It was ratcheted forward twice (#190, #192) from the first
measurement (98% / 19.4% / 41%). Regenerating it is a deliberate act
(`gate --update-baseline`) and needs its own justification in the commit, because it redefines
what every later change is measured against.

**Baselines are change detectors, not proof the result is correct (owner rule, 2026-11-01).**
A baseline is never regenerated to absorb a change before that change's delta against the
**previous** baseline has been recorded and reviewed. Otherwise a regression is laundered
into the new reference. So, for every gate:

1. Run the gate on the change against the current baseline and record its per-check delta
   (before → after for every check) and every rated row whose decision moved, with the
   owner's rating.
2. Have that delta reviewed: on the PR, or by Guy for anything that moves push or a canary.
3. Only then run `--update-baseline`. The commit that rewrites a baseline must cite the delta:
   before → after per check, and which rated rows changed.

The census gate enforces this. `gate --census [--facts rerun] --update-baseline` first runs
the gate against the previous baseline, on the census that baseline was built on. That census
is rebuilt from the ratings the baseline stores, so it is independent of the files on disk.
The update prints two deltas:

- **decisions**: before → after per check, and every rated row whose decision moved;
- **ratings**: rows re-rated (old → new), added and removed, and the metrics of the current
  decisions under the previous ratings and under the new ones. A re-label moves every metric
  while no decision moves, so a decision-only delta would hide it.

It **refuses to write** when the gate fails, the comparison is invalid, any already-rated row
was re-rated or removed (a new `--review` file, or a ratings file edited in place), or there
is no previous baseline (a first baseline, or a new `--baseline` path). New rows, such as
census #3 joining, are allowed. A failing check that was reviewed and argued passes with
`--accept <check_id> --reason`, and the update message says so. Everything else needs
`--force-update --reason`, citing the review. The deltas, the accepts and any forced reason
are stored in the new baseline's `previous` block. N05's `--update-baseline` does not enforce
the rule (its code is out of scope here), so for N05 it is followed by hand.

**N05 is one of two gates.** The census gate below runs alongside it. N05 stays until the
census gate has gated at least two real changes; then the keep-or-retire decision on N05 is
recorded here (#254).

A change that genuinely needs to regress a check says so explicitly:

```
gate --accept guy.false_hide --reason "cost of the #193 mention-vs-subject fix; argued there"
```

That records the override and its argument in the artifact. A stale `--accept`
naming a check that no longer fails is itself a gate failure.

**`false_show` is reported but not separately gated** — within the visible set
it is the complement of `shown_precision`, which is gated.

### `false_hide_by_sport` — read this before targeting recall (#208)

The gate also reports false hide **per sport**, because the headline figure can
no longer resolve recall work:

| sport | one rated row is worth |
|---|---|
| football | **3.91 pp** (15 of 838 hidden rows sampled) |
| unknown | 0.73 pp |
| basketball | **0.29 pp** (30 of 126 sampled) |
| tennis | 0.19 pp |

A **13×** difference. Measured on the current corpus, **two** football rows are
43% of Guy's remaining false hide while **23** basketball rows are 36%. So fixing
nine Israeli-basketball articles he actually wants moves the total by ~2.4pp —
less than a single football rater disagreement.

Report the per-sport line whenever you claim a recall change, or you may be
reporting sampling noise. It is **not gated**: a per-sport threshold would need
its own evidence and its own baseline.

### Census gate (#254)

```
cd backend
.venv/Scripts/python.exe scripts/feed_ground_truth.py gate --census                # stored facts
.venv/Scripts/python.exe scripts/feed_ground_truth.py gate --census --facts rerun  # rules-only rerun
```

**Pick the facts source by the kind of change, and run both when unsure.** Each source has
its own baseline, and the gate refuses to compare across them:

| `--facts` | decisions come from | use it for | baseline |
|---|---|---|---|
| `stored` (default) | the facts persisted in the corpus, as ingested (LLM-assisted where the LLM ran) | relevance, profile and scoring changes: what the product serves for these rows | `census_gate_baseline.json` |
| `rerun` | a rules-only reclassification of the census rows in memory (LLM and translation off, no writes), the same path as `corpus_rerun_diff.py` | **classifier and taxonomy changes**. Stored rows change only through a backfill, so the stored gate cannot see them | `census_gate_rerun_baseline.json` |

The two sources disagree a lot. 131 of census #2's 804 rows have a different stored
sport, event or competition than a rerun of main gives: rows keep the facts of the pipeline
that ingested them, and blanket backfills are forbidden. The profile makes no difference
(persisted and seed Guy give identical metrics). The first real change through the gate
was #398, a classifier vocabulary change. It moved nothing on stored facts (N05 also stayed
flat). On the rerun it took push precision 2/3 → 3/4 and push recall 2/7 → 3/7, and passed.

Same contract as N05: local-only, exit 0 / 1, `--accept <check_id> --reason`, a stale accept
fails. The pure rules are `app/qa/census_gate.py`, covered in CI by
`backend/tests/test_census_gate.py`. It scores the live engine over every census article
(census #2: 804 articles published since 2026-08-01, all rated by the owner, weight 1.0;
[qa/CENSUS_2026-10.md](qa/CENSUS_2026-10.md)). Because every row is rated, it reads **recall
directly** instead of `false_hide`, which the 74% hide base rate dilutes:

| Check | Rule | Slack |
|---|---|---|
| `guy.shown_precision` | of the rows shown, how many were rated low or better | one shown row (`1/n`) |
| `guy.feed_plus_recall` | of the rows rated feed or better, how many are shown | **none** |
| `guy.push_precision` | of the pushes, how many were rated push | one push (`1/n`) |
| `guy.push_recall` | of the rows rated push, how many are pushed | **none** |
| `guy.push_volume` | may not rise | **none**, unless push precision improved |
| `guy.two_notch` | count of disagreements of **≥2 notches** may not rise | **none** |
| `casual_deni_fan.no_drift` | the canary's decisions over the census ids may not move (it needs no ratings) | **none** |

**The noise band.** Census ratings repeat only about half the time on borderline rows: in
census #2's blind re-rate, 28 of 58 large disagreements changed, 26 toward the engine, mostly
by one notch. So the disagreement check ignores one-notch gaps: a change that opens only
one-notch gaps cannot fail it, while a new two-notch gap does. Exact agreement is not gated.
Re-rate large disagreements before treating them as engine errors.

**Known gap: same-direction one-notch drift (#402).** Ignoring one-notch gaps row by row also
means no check sees a *systematic* one-notch move away from the owner's ratings. Replayed on
the stored baseline, demoting all 69 owner-`feed` rows shown at `feed`/`high_feed` to
`low_feed` passes every check, and so does hiding up to 21 of the 39 shown owner-`low` rows.
#402 proposes a directional check: one-notch moves away from the rating vs toward it, with a
slack or a sign test. Until it lands, review the decision delta for one-direction drift by eye.

**Why both directions are needed.** Replayed on census #2, "surface everything" (every hidden
row to `low_feed`) takes feed+ recall to 100% and *lowers* the ≥2-notch count from 48 to 17;
only shown precision (95.9% → 25.9%) catches it. "Hide more" (`low_feed` and `feed` to hidden)
takes shown precision to 100%; feed+ recall (73.9% → 12.3%) and the ≥2-notch count catch it.
Both replays are CI tests on both committed baselines.

**Inputs.** By default the gate reads the files its baseline records. Census #2 alone today:
`census2_ratings.json` + `census2_sample.json`, plus `census2_review_ratings.json` (the blind
review). A review rating wins over a census rating. Census #2's review is already folded into
`census2_ratings.json`, so it changes 0 rows; it is listed so the baseline records it. To add
census #3 (#241), pass each pair in order and regenerate deliberately. The update is checked
against the previous baseline on census #2 alone, and the new rows join only after that:

```
gate --census --update-baseline \
  --ratings ../docs/qa/census2_ratings.json --sample ../docs/qa/census2_sample.json \
  --ratings ../docs/qa/census3_ratings.json --sample ../docs/qa/census3_sample.json \
  --review ../docs/qa/census2_review_ratings.json
```

Censuses are deduplicated by article id. Two censuses that rate the same article differently
are an error unless a review file settles it. The baseline stores a content hash of the
merged ratings and of the article id set, so a re-rated or regrown census is an invalid
comparison, not a score.

Baselines, generated on 2026-11-01 against a frozen copy of the live corpus (3,868 RSS
articles) by this PR's gate code at `d82e161` (clean tree, recorded in `meta.git_sha`). Its
engine, classifier and relevance code are identical to main at `a0c3477`; the PR changes only
the gate. A `-dirty` suffix on `meta.git_sha` means uncommitted `backend/` changes at
generation time:

| | shown precision | feed+ recall | push precision | push recall | ≥2-notch | Deni (804 ids) |
|---|---:|---:|---:|---:|---:|---|
| stored | 95.9% (141/147) | 73.9% (102/138) | 1/3 | 1/7 | 48 | 792 hidden |
| rerun | 94.0% (173/184) | 89.1% (123/138) | 2/3 | 2/7 | 27 | 790 hidden |

Regenerating either (`gate --census [--facts rerun] --update-baseline`) follows the rule
above: delta against the previous baseline first, reviewed, then cited in the commit. The
rerun baseline measures the classifier code, so a merged classifier or taxonomy change leaves
it behind main. It is brought forward only after that change's reviewed delta, never as a
formality. The stored baseline moves only with a profile change, a relevance change, or a
reviewed correction script, under the same rule.

The delta to review before the rerun baseline absorbs #398, measured against the current
baselines: push precision 2/3 → 3/4, push recall 2/7 → 3/7, push volume 3 → 4 (allowed,
precision improved), ≥2-notch 27 → 26, and nothing else moved (stored facts and N05 stay flat).
The only rated row that changed is the Cyprus move, `rss_60dbc2f4aa7316584e2d`: feed → push,
rated push.

**`push_precision` is redundant on a census.** Every row is rated, so its numerator (rows
both pushed and rated push) is the same count as push recall's. Push precision can fall only
if push recall falls (zero slack) or push volume rises without a precision gain (zero slack),
so its one-push slack cannot let a regression through on its own. It is kept for continuity
with N05, where the push stratum is a census but the rest is sampled.

**The rerun is rules-only.** Production also calls the LLM on gated rows, so the rerun
approximates what new ingestion would produce. Say so when quoting its numbers.
