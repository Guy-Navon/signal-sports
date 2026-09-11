# Milestone brief — close both measured failures of the feed (#191 + #192)

You are working on **Signal Sports**, a personalized sports-news intelligence
feed (Hebrew-first, FastAPI + SQLite backend, React frontend). The repo root has
`CLAUDE.md` (product context) and `docs/`. Assume **no prior conversation
history** — everything you need is below.

Work on a branch. **Open a PR and stop. Do not merge to `main`.**

---

## 0. The mission, in one sentence

**Epic #188 exists to close two measured failures — recall and push. Close both,
and make the feed story-level instead of article-level.**

That is a genuine product milestone: after it, the feed stops missing a sixth of
what the owner wants, the phone stops buzzing five times about one transfer, and
one story renders as one card with N sources instead of N cards.

---

## 1. What is actually true today (measured, not assumed)

On 2026-09-05 the feed was measured against human ground truth for the first
time: **282 real corpus items, hand-rated by the product owner blind to the
engine's decision**, across two profiles. **Read
`docs/qa/N05_FEED_GROUND_TRUTH.md` in full before doing anything.**

It inverted the project's working assumption. Everyone believed the feed was
noisy. It is not:

| Metric | Guy (basketball power user) | casual_deni_fan |
|---|---|---|
| **Precision on what is shown** | **98.2%** (112/114) | **91.7%** (22/24) |
| **False hide** (weighted) | **18.2%** | 0.8% |
| False show | 0.4% | 0.1% |
| **Push precision** | **41.2%** (7/17) | never fires |

**Display quality is NOT a target.** It is already 92–98%, and Epic #188
explicitly forbids investing in it. Your job is the other two columns.

---

## 2. Your goals — each derived from the data, not invented

Report every one of these as before → after, with the gate output.

### G1 — Recall: `false_hide` 18.2% → **≤ 12.0%** (Guy)

Derived. Breaking the current 31 sampled false-hides down by event type,
**weighted by their sampling weights**:

| event_type | n | contribution to false_hide |
|---|---|---|
| **`news`** | **20** | **11.26 pp** |
| `release` | 1 | 3.91 pp |
| `match_result` | 3 | 0.88 pp |
| `schedule` | 1 | 0.73 pp |
| `signing` | 2 | 0.59 pp |
| `negotiation` | 2 | 0.36 pp |
| `finals_result` | 1 | 0.29 pp |
| `title_win` | 1 | 0.19 pp |

`news` alone is **11.26 of the 18.2 points**. Perfect event-type recovery on
those rows would floor `false_hide` at **≈7.0%**. So 12.0% asks for roughly 55%
of the recoverable ground — ambitious and grounded. 7.0% is the theoretical
floor; do not treat it as the target.

⚠️ **The corpus is frozen** — the newest article is 2026-07-31 and no ingestion
runs during this work. So a goal must never depend on an article that does not
exist in it. That is what made the original G4b unreachable.

⚠️ **Weight granularity matters.** Hidden-football rows carry a sampling weight
of ~55.9, so a *single* football row moves `false_hide` by ~3.9 pp (that is the
whole `release` line above — one article, rated `low`). Do not chase, or claim,
movement that is one football row of noise.

### G2 — Push: volume 17 → **≤ 6**, precision **≥ 70%** (Guy)

And **no approved story may lose its notification**.

### G3 — Story-level feed: cluster coverage of visible items 8% → **≥ 20%**

Today **20 of Guy's 242 visible items carry a cluster card (8%)**, while the
corpus holds 41 clusters and 70 cluster edges. `CLAUDE.md` lists "group duplicate
stories" as required product behaviour, and **the frontend already renders it** —
`frontend/src/components/feed/orbit/OrbitStoryField.jsx` shows
*"N דיווחים מ-M מקורות. סיפור אחד"* when a feed item carries a cluster. The
feature exists end to end and is starved of clusters.

### G4 — Break the flat scale for `casual_deni_fan`

**G4a — over-ranking: 15 of 24** visible items are over-rated (engine
`high_feed`, owner rated `feed`) → **≤ 8**. Independent of G4b; do this either way.

**G4b — make a push fire.** The profile's `push` stratum population is literally
0: no `always_push` rule has ever fired. §2b below records an **authorized product
decision** that makes this reachable. Demonstrate the rule firing on
`rss_4c34e0718aadb617f71b`, with the trace.

### Guardrail — non-negotiable

`shown_precision` may not fall below **98.2%** (Guy) / **91.7%** (Deni), minus
the gate's one-item slack. A change that buys recall by wrecking precision is a
failure, not a trade.

> **If a goal turns out to be unreachable for a principled reason, say so with
> evidence and MOVE ON TO THE NEXT GOAL. Do NOT weaken a contract or an
> invariant to hit a number.** A well-evidenced "12% is not reachable without
> breaking X, here is why, here is what I got instead" is a success. Two of this
> epic's issues were re-scoped or closed on exactly that basis (#190, #193) and
> both saved real work.
>
> **⚠️ A blocked goal stops THAT GOAL, not the run.** The goals are independent:
> G1 (recall), G2 (push) and G3 (story-level) do not depend on G4 in any way. The
> first attempt at this brief read an earlier wording as "stop the whole task" and
> halted after G4, leaving three goals untouched. Do not repeat that. Work each
> goal, record what blocked, and keep going. Only a corrupted corpus or a failing
> gate you cannot explain justifies stopping the run.

---

## 2b. AUTHORIZED product decision — add a `relocation` event type

A first attempt at this brief stopped here, and its finding was correct and sharp:
**the one `casual_deni_fan` article the owner rated `push` is not a trade or an
injury.** Verified independently:

- `rss_4c34e0718aadb617f71b` — title `דיווח דרמטי: דני אבדיה ופורטלנד עשויים לעבור לאוקלהומה`,
  subtitle `הכוכב הישראלי יעביר את ביתו ליעד חדש?` — *his home*, not his team.
- Entities: `player:deni_avdija`, `team:portland_blazers`, `team:okc_thunder`.
- A coherent storyline surrounds it: `עתיד הבלייזרס בפורטלנד בסכנה על רקע משבר האולם`,
  `"לטום דאנדון אין לאן לעבור עם פורטלנד"`, `אין לאן לעבור: פורטלנד ואבדיה נותרו ללא יעד`.

This is **franchise relocation**. Labelling it `major_trade` would be a false
fact, and the first attempt was right to refuse.

**The owner has now decided: `relocation` becomes a real event type.** This is the
explicit decision that §7's "no new event types" invariant requires — you are
authorized to add exactly this one, and no others.

### The evidence that fixes its scope

How each profile rated the relocation storyline:

| Article | Guy | casual_deni_fan |
|---|---|---|
| `דני אבדיה ופורטלנד עשויים לעבור לאוקלהומה` | `feed` | **`push`** |
| `אין לאן לעבור: פורטלנד ואבדיה נותרו ללא יעד` | — | `feed` |
| `עתיד הבלייזרס בפורטלנד בסכנה על רקע משבר האולם` | **`low`** | — |
| `"לטום דאנדון אין לאן לעבור עם פורטלנד"` | **`low`** | — |

Read that carefully, because it is the spec:

- **The same article is `push` for the Deni fan and `feed` for Guy.** This is
  `CLAUDE.md`'s Critical Personalization Principle showing up as measured data:
  *"The same article must be able to produce different relevance decisions for
  different users."*
- **Relocation is only push-worthy when the followed player is its subject.**
  Generic franchise/arena news without Deni is rated `low` by Guy.

So the override must be **entity-scoped**:
`always_push` × `scope=player` × `target_id=player:deni_avdija` ×
`event_type=relocation`. **Guy gets no relocation push rule** — his `push_volume`
must stay 17 and the gate enforces that.

### What adding it requires

1. `relocation` in `ALLOWED_EVENT_TYPES` (`backend/app/classification/validation.py`)
   and in the LLM prompt's type list (`backend/app/classification/prompt.py`).
2. **A clustering event-state decision.** `relocation` must be an explicit member
   of exactly one of `CLUSTERABLE_EVENT_STATES` / `NEVER_CLUSTERED_EVENT_STATES`
   (`backend/app/clustering/config.py`). `tests/test_feed_dedup_121.py::test_every_event_type_is_explicitly_classified`
   enforces this, and #121 documents why: a type in neither set does not "default
   to safe", it becomes **unclusterable at any similarity, silently**. Several
   sources report the same relocation report, so clusterable is very likely
   correct — but state the choice.
3. Event **evidence** for asserting it (`backend/app/classification/event_evidence.py`),
   at the same standard as every other type. Do not special-case it to make G4b pass.
4. **A profile mutation**, because profiles are DB rows and not re-seeded from code
   (§8.2). Update the seed for future environments *and* mutate the live
   `casual_deni_fan` profile, or G4b cannot be demonstrated on this corpus.
5. A guard that relocation does **not** leak into Guy's push surface.

---

## 3. The two root causes

### 3.1 `news` is the absence of a classification (#191)

`event_type` is the load-bearing axis of the whole decision model: every
preference affinity, every `always_push` override, and every clustering time
window is keyed on it. And it is degenerate.

- **86 of Guy's 185 rated items are `news`** (46%), and **20 of his 34
  false-hides**.
- For `casual_deni_fan` it is the entire story: **19 of his 24 visible items are
  `news`**. His visible feed is `news`×19, `signing`×3, `release`×1,
  `negotiation`×1 — nothing else.

The consequence is verifiable. That profile **already has the right rules**
(`backend/app/seed/seed_profiles.py`):

```python
OverrideRule(kind="always_push", scope="player", target_id="player:deni_avdija", event_type="major_trade"),
OverrideRule(kind="always_push", scope="player", target_id="player:deni_avdija", event_type="injury"),
```

They have never fired, because **no article was ever both resolved to Deni and
classified `major_trade` or `injury`.** A report of a possible move to Oklahoma
and a jab from Ja Morant both land in `news` and both come out `high_feed`.
`CLAUDE.md` demands exactly that distinction (`deni_trade` → push, `deni_news` →
high_feed) and the event layer cannot express it.

A competing hypothesis — that those items were entity *mentions* wrongly treated
as subjects — was tested in #193 and **refuted**: only 2 of the 24 were unwanted,
and two of the three headlines cited as evidence turned out to be items the owner
actively wants. The over-ranking is an event-type problem.

### 3.2 Push is article-level and indiscriminate (#192)

Guy's 17 pushes, with the owner's rating and the stored event type:

| Rating | event_type | Headline (abridged) |
|---|---|---|
| high | negotiation | ריאל מדריד מנהלת מגעים לצירופו של **לוני ווקר** |
| feed | negotiation | **לוני ווקר** במו"מ עם קבוצה ענקית מהיורוליג |
| feed | negotiation | סעיף היציאה פג, הסאגה עוד לא: **לוני ווקר** יעזוב? |
| **push** | negotiation | נשאר צהוב: **לונדברג** סיכם לשנתיים נוספות |
| **push** | negotiation | **לונדברג** סיכם על חוזה חדש במכבי תל אביב |
| **push** | negotiation | בשורה אדירה: **לונדברג** סיכם על חוזה חדש |
| **push** | signing | השוק הנוסף שמכבי בוחנת, ומתי **לונדברג** |
| high | negotiation | מתקרב: הצטמצמו הפערים בין מכבי ו**לונדברג** |
| **push** | signing | מכבי ת"א הציגה את **ים מדר** |
| **push** | signing | היקר בתולדותיה: **ים מדר** חתם רשמית *(the only clustered push)* |
| **push** | signing | **ים מדר** חתם: "מבטיח לתת את הכל" |
| feed | signing | התקדם ממכבי: התפקיד המפתיע של דורון פרקינס |
| feed | negotiation | כל הפרטים: כך פוספס הקאמבק של ג'וש ניבו |
| feed | signing | "במכבי תל אביב האמינו שיגיע" |
| feed | signing | כבר חתם: כוכב היורוליג דחה את הפועל ומכבי |
| feed | negotiation | יעד מפתיע: הכישרון של מכבי מתקרב לקבוצה חדשה |
| low | injury | "יכולתי להיות הרבה יותר טוב במכבי, אם לא הפציעה" |

**Three sagas (Lundberg ×5, Madar ×3, Walker ×3) plus 6 singles.** All 17 come
from `always_push:*` on `team:maccabi_tlv_bb` (5 rules: signing, major_signing,
negotiation, injury, title_win). Only **1 of 17** carries a cluster card despite
`CLUSTERING_ENABLED=true`.

---

## 4. ⚠️ The trap that will fail your gate run

**De-duplication ALONE makes push precision WORSE.** Work it through with the
table above:

The duplicates are the **approved** pushes (Lundberg: 4 of 5 rated `push`; Madar:
3 of 3). The **singles** are all rated `feed`/`low` — none push-worthy. So
collapsing sagas removes justified notifications and leaves the unjustified ones
behind:

| Scenario | Volume | Justified | Precision |
|---|---|---|---|
| today | 17 | 7 | **41%** |
| de-dup only (same-state collapse) | ~10 | 3 | **~30%** ❌ |
| de-dup **+ severity** | ~3 | 3 | **~100%** ✓ |

The #189 gate blocks a precision drop. **So you must ship story-level identity
and severity together, or the gate will correctly reject the change.**

### And note the interaction with #191

- `"לונדברג סיכם על חוזה חדש"` is stored as **`negotiation`** although `סיכם`
  means *agreed*. That looks like an event-type error — i.e. #191 work — and
  fixing it changes **both** which `always_push` rules fire **and** what
  same-state clustering can merge.
- Clustering is **strict same-state by design**: `signing`, `negotiation`,
  `candidate` and `rumor` are DISTINCT developments, and
  `docs/CLUSTERING.md` is explicit that collapsing them "would tell a user a deal
  is done when it is stuck". Lundberg is 4×negotiation + 1×signing, so a correct
  collapse gives **2** notifications, not 1.
  **Do not weaken the same-state contract to hit G2 or G3.** If severity is what
  is needed, fix severity.

This interaction is why the two issues are in one brief: doing them separately
means re-baselining twice and re-diagnosing #192 after #191 moves the event types.

---

## 5. The gate — your self-verification instrument

This is what makes an unattended run safe. A directional regression gate scores
the engine against those 282 human ratings:

```bash
cd backend
.venv/Scripts/python.exe scripts/feed_ground_truth.py gate      # exit 0 / 1
```

Run it **before you start** and after every behaviour-changing step. Full rules:
`docs/RELEVANCE_CONTRACT.md` §"Quality gate".

| Check | Rule | Slack |
|---|---|---|
| `shown_precision` | of what the user sees, how much did they want? | one rated item (`1/n`) |
| `false_hide` | how much did they want and never see? | **none** |
| `push_precision` | were the interruptions justified? | one rated push (`1/n`) |
| `push_volume` | may not rise | **none**, unless precision improved |
| `casual_deni_fan.no_drift` | the canary profile must not move | **none** |

**⚠️ The metric trap.** Never lead with overall accuracy. It is dominated by the
hidden majority: `casual_deni_fan` scores 98% exact agreement while hiding 98.3%
of the corpus, so agreeing with "hidden" on football scores beautifully and says
nothing. **Always report `shown_precision` and `false_hide` together.** The gate
exists because a synthetic "improve recall" change once took `false_hide` 19.4% →
11.4% while `shown_precision` collapsed to 83.5%; a recall-only check would have
passed it.

**`casual_deni_fan.no_drift` WILL fail here, by design** — G4 changes that
profile deliberately. Use
`gate --accept casual_deni_fan.no_drift --reason "<why>"`. Never regenerate the
baseline to clear a red gate; ratchet it only at the very end, only once green,
with the justification in the commit.

---

## 6. Sequence

1. **Gate before.** Confirm a clean start and record the numbers.
2. **The census is ALREADY DONE and merged — do not redo it.** See
   `docs/qa/N05_MILESTONE_FEED_QUALITY_FINDINGS.md` and
   `docs/qa/n05_milestone_census.json`. Independently reproduced: **816 of 1,427
   rows are `news` (57.2%)**.

   Its findings are your starting leads:

   | Classification method | all rows | `news` |
   |---|---:|---:|
   | `rules_fallback_after_llm_failure` | 478 | **336** |
   | `rules` | 687 | 293 |
   | `llm+rules_guardrail` | 188 | 138 |
   | `llm` | 74 | 49 |

   - **It is both a rules gap and an LLM gap.** 336 `news` rows followed an LLM
     *failure*; 293 used rules with no LLM proposal at all.
   - **101 rows stored `news` while the LLM had proposed a different event.**
     That is the sharpest lead in the census: something is *downgrading* proposals.
     One hypothesis worth testing — `validation.py:89` reads
     `event_type if event_type in ALLOWED_EVENT_TYPES else "news"`, so any
     proposed type outside the allowed set silently becomes `news`. I probed for
     this and my guess at the trace shape returned nothing, so treat it as an
     unconfirmed hypothesis; the previous attempt extracted those 101 and knows
     how to read the traces.
   - Also recorded: 8 `news` rows whose historical `trace event.final` differs
     from the stored `event_type`, so trace history alone cannot establish the
     current cause.

   The census explicitly does **not** prove all 816 are misclassified. Keep that
   discipline: #190 was scoped on an assumption about its root cause and the
   diagnosis proved it wrong — 24 of 25 rows failed for a completely different
   reason than the ticket claimed.
3. **Decide explicitly whether `news` stays reachable**, and state the trade-off
   in the PR. A classifier that cannot say "I don't know" is worse than one that
   can — abstention is a *designed success mode* here. But an escape hatch that
   swallows 46% of the items is not abstention, it is a default. Acceptable: a
   genuine last resort that records *why*. Not acceptable: an unexplained default,
   or forcing confident guesses to move a number.
4. **Ship #191.** Gate. Report both directions.
5. **Trace all 17 pushes** and establish why only one clustered. The event-state
   gate is *not* the cause — `signing`, `negotiation` and `news` are all
   clusterable. Candidates to test, not assume: clustering ran after the push
   decision; the planner's member-lineage identity (#151) never consults cluster
   membership; anchor/similarity did not merge them; or the saga exceeds the
   per-state time window. **Re-run this diagnosis after step 4** — #191 changes
   event types and therefore clustering.
6. **Ship #192**: story-level notification identity **and** severity, together
   (§4). Preserve at-most-one delivery semantics (#153: sent / definite failure /
   unknown) and the outbox DB uniqueness (#151).
7. **Gate, full suites, docs, PR.** Do not merge.

---

## 7. Hard invariants — violating any of these fails the task

- **⛔ NEVER run a blanket rules-only backfill of the corpus.** Of 34 measured
  false-hides re-run through fresh rules-only classification, **12 were degraded**
  (`sport`: `basketball` → `unknown`), because 15 of them were originally
  classified with LLM assistance a rules-only pass cannot reproduce. **The stored
  row is often better than what a backfill would write.**
- **The live corpus DB (`backend/data/signal_sports.db`) is irreplaceable replay
  evidence.** Never reset or delete it. Back up before any write
  (`backend/scripts/backup_db.py`). Corrections must be targeted,
  dry-run-by-default, idempotent and hand-verified — copy the pattern in
  `backend/scripts/apply_190_entity_corrections.py`.
- **FACTS → VISIBILITY → PREFERENCE → LEARNING separation**
  (`docs/RELEVANCE_CONTRACT.md`). A failure caused by a wrong *fact* is fixed in
  classification, **not** compensated for in the preference layer. Do not add
  broad `news` affinity rules to a profile to paper over a classification gap —
  that re-admits the noise the 98% precision currently earns.
- **Do not loosen event-semantic evidence or certainty thresholds**
  (`backend/app/classification/event_evidence.py`) to make event types fire. That
  reintroduces the false-push failure mode the #58 reliability epic existed to
  fix.
- **Do not weaken strict same-state clustering** (§4).
- **Entity abstention is a designed success mode.** Bare family names (`בהפועל` —
  which Hapoel?), cross-sport aliases (`מכבי תל אביב` is both a football and a
  basketball club) and guarded entities correctly resolve to nothing.
- **Push stays rare**, and volume may never rise without a measured precision gain.
- **`primary_competition` is explicit-evidence-only** (#28). Never populate it from
  inference — that opens the RC-4 hazard of promoting a background mention.
- **No new event types** without an explicit, stated decision. **`relocation` is
  that decision and the only one authorized (§2b).** Everything else routes to
  existing types.
- **No live Telegram sends.** Work at planner/outbox level only.

---

## 8. Mechanisms that will otherwise cost you hours

Established the hard way this week. Trust them.

1. **Membership reach reads canonical `entity_ids` ONLY.** The v2 scorer matches
   competitions through four tiers (`match_competition_names` in
   `backend/app/services/relevance_engine.py`): explicit → legacy → participant
   inference → membership. The **legacy** tier requires `taxonomy_version is
   None`, and **no corpus row qualifies** — all 1,427 are post-ArticleFacts. So
   writing the legacy `entities` names, or `article.league`, produces **zero**
   decision changes. Only `entity_ids` moves anything.
2. **Profiles are DB rows, not code.** `seed_all_if_empty` means editing
   `backend/app/seed/seed_profiles.py` does **not** reach the live corpus. A
   profile change needs a mutation through the service layer. Budget for it if
   your design requires one — and note that G4 may not need one at all, since the
   rules already exist and are simply never satisfied.
3. **A full resolver/classifier re-run over the corpus touches ~173 rows** for
   reasons unrelated to any one change. Scope every corpus correction to exactly
   what your change touches, or you are running the banned blanket backfill.
4. **Title vs subtitle is strong evidence about subject-hood.** Title evidence
   proved a reliable proxy for "what the story is about"; subtitle-only matches
   were opponents, former clubs and incidental mentions. Useful when scoping
   corpus writes.
5. **Scoring is computed at read time**, so relevance-layer changes appear without
   re-ingesting. Classification changes affect only **new** rows until stored rows
   are corrected.
6. `score --live` scores the ratings against **current** engine decisions instead
   of the ones frozen into the sample — that is what answers "did my change
   improve things?".

---

## 9. Stretch goal — only if everything above is green

**#194 — `sport=unknown` is a silent sink.** 210 of 1,427 rows (14.7%) carry
`sport=unknown` and **209 of them are hidden**, in both profiles. Five of Guy's
false-hides are such rows. The danger is the silence:
`relevance_engine.py` lets `unknown` pass the sport check, so those rows simply
match nothing — **a classification failure becomes a hiding decision with no
error, no log line, and no metric that complains.**

Minimum valuable outcome: a **census** (by source and classification method), a
hand-reviewed sample split into *correct abstention* vs *real gap*, and a
persisted `unknown`-rate metric with a threshold guard test. Correct abstention is
a perfectly good answer — if most of the 210 are that, instrumentation is the
right deliverable and a classifier change is not.

**If time runs out, stop and say so.** A clean #191 + #192 with an honest "did not
start the stretch" beats three half-finished pieces.

---

## 10. Process

- Project skills encode the house workflow — use them:
  `signal-classification-change`, `signal-relevance-change`,
  `signal-real-data-qa` (before/after decision diffs on the real corpus),
  `signal-doc-truth` (which doc is authoritative), `signal-pr-finish`.
- Keep docs true. `docs/RELEVANCE_CONTRACT.md`,
  `docs/CURRENT_PROJECT_STATE.md`, `docs/CLUSTERING.md`, `docs/NOTIFICATIONS.md`
  and `docs/qa/N05_FEED_GROUND_TRUTH.md` are living contracts; superseded docs are
  history and must not be "fixed".
- **Report honestly and specifically.** Every claim in your PR should be something
  you actually ran. Distinguish *verified* from *expected*. If the census in step 2
  contradicts the framing in §3, say so — that is a result, not a setback.
- Open a PR describing what moved, in both directions, with the gate output for
  both profiles. **Do not merge.**

---

## 11. Orientation

| Path | What it is |
|---|---|
| `CLAUDE.md` | Product context and principles |
| `docs/qa/N05_FEED_GROUND_TRUTH.md` | **The measurement. Read first.** |
| `docs/RELEVANCE_CONTRACT.md` | Decision semantics + the quality gate |
| `docs/CLUSTERING.md` | Clustering contract (incl. strict same-state) |
| `docs/NOTIFICATIONS.md` | Push planner, outbox, delivery semantics |
| `docs/CURRENT_PROJECT_STATE.md` | Cold-start orientation |
| `backend/app/ingestion/classifier.py` | Classification entry point (>1000 lines) |
| `backend/app/classification/` | Facts, event evidence, validation, LLM prompt |
| `backend/app/clustering/` | Anchors, matcher, config, event states |
| `backend/app/notifications/` | Push planner + outbox |
| `backend/app/services/preference_engine.py` | The v2 scorer (`score_article_v2`) |
| `backend/app/services/relevance_engine.py` | Visibility + competition matching |
| `backend/app/seed/seed_profiles.py` | The two demo profiles (seed values) |
| `backend/scripts/feed_ground_truth.py` | `baseline` / `sample` / `score --live` / `gate` |
| `docs/qa/n05_gate_baseline.json` | The frozen reference the gate compares to |
| `frontend/src/components/feed/orbit/` | The Orbit feed, incl. the story-field card |

Suites: `cd backend && .venv/Scripts/python.exe -m pytest tests -q`
(baseline **2502 passed, 1 skipped**) · `cd frontend && npm run test && npm run
lint && npm run typecheck && npm run build` (baseline **539 passed**).
