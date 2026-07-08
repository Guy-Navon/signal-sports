# Signal Intelligence Architecture v2 — Plan & Near-Future Roadmap

Last updated: 2026-07-08 — **this initiative is COMPLETE** (Epic #27 and Milestone 1 closed; Preference V2 serves the live feed). The §2 invariants below still bind all future work. **The next active milestone is User Platform** — see `docs/USER_PLATFORM.md` and [Milestone 2](https://github.com/Guy-Navon/signal-sports/milestone/2).
**Home page for this (completed) initiative's work: [Milestone 1](https://github.com/Guy-Navon/signal-sports/milestone/1)** · Epic: [#27](https://github.com/Guy-Navon/signal-sports/issues/27)

This document is the standing summary of the approved architecture decision
(full review: architecture plan of 2026-07-05 + LLM addendum of 2026-07-06)
and the execution roadmap. It exists so any session or agent can pick up the
initiative without conversation history.

---

## 1. Why this initiative exists

Ten production screenshot failures exposed three missing architectural layers,
not ten bugs:

1. **No entity registry** → bare "מכבי" resolved to Maccabi Tel Aviv, so
   Maccabi Ramat Gan / Kiryat Gat news received Maccabi-TLV treatment;
   impossible states (football entity + basketball sport) were possible.
2. **No taxonomy linking teams → sport → competitions** → football classified
   as basketball via entity bias; correctly-classified EuroLeague / Israeli
   league articles hidden from a user who broadly follows those leagues
   (73% of stored articles had `league=NULL`).
3. **No semantic contract for decisions** → `low_feed` meant "we had no reason
   to hide it" instead of "relevant but low-value"; event types fired on
   keywords without positive evidence (false `title_win`).

The fix is ordered: **FACTS → VISIBILITY → LEARNING.** Building preference
learning on wrong facts amplifies the wrong facts, so the sequence is not
negotiable.

## 2. Hard architecture invariants

These bind every PR in the initiative:

- **THE LLM REDUCES UNCERTAINTY; IT DOES NOT DEFINE TRUTH.** Deterministic
  evidence (source URL hints, canonical aliases, competition names, taxonomy
  relations) resolves first. The LLM is called only on residual ambiguity, as
  a candidate generator. Its proposals always pass normalization + validation.
  Abstention (`sport=unknown`, no entity) beats guessing.
- **LLM optionality.** The product stays useful with
  `CLASSIFICATION_PROVIDER=disabled`. The no-LLM path is first-class forever.
- **Taxonomy is the gating function.** Registry growth must reduce the LLM
  call rate (measured baseline 2026-07-05: ~60–65% of new articles, ~8s per
  article, fully sequential; target after the Facts PRs: **≤25%**) — but call-rate
  reduction is never bought with accuracy or false-positive control.
- **Facts ≠ personalization.** Classification answers "what is this article
  about"; the relevance engine answers "how much does this user care". User
  preferences never contaminate article facts.
- **Competition model** (three distinct relations):
  - `primary_competition` — what the article is about; explicit evidence only.
  - `article_competitions` — additional explicitly-evidenced competitions; persisted.
  - entity competition **memberships** — taxonomy data only; membership-derived
    reach is computed at scoring time and never persisted per-article.
  - Reach rule: **team-anchored events** (signing/injury/roster…) reach all of
    the team's competitions; **competition-anchored events** (results, titles,
    schedules) reach only explicit competitions — a Maccabi domestic-league game
    is not relevant to a EuroLeague-only follower.
- **Push discipline.** `push` only via explicit rule; boosts cap at `high_feed`.
- **Decision contracts.** `hidden` = no followed scope / explicit exclusion;
  `low_feed` = matched followed scope but low-value story (never reachable
  without a matched scope); `feed`/`high_feed` = normal/boosted within a
  followed scope. "Globally important" is never a visibility reason by itself.
- **Backend is authoritative for intelligence.** The JS engine is frozen at its
  current feature set (local/demo mode only); no taxonomy/affinity/learning port.

## 3. Where we are (done)

> **MILESTONE COMPLETE (2026-07-08).** Every issue in §4 has shipped:
> #28 (PR #38), #30 (PR #37), #29 (PR #39), #40 (PRs #41+#42 — competition
> reach completion: NBA 30/30 + EuroLeague 20/20 taxonomy, participant-set
> inference), #31 (PR #43), #32 (PR #44 — Preference V2 flipped after the
> Fable shadow checkpoint: Guy 96.3%, Deni fan 100% agreement, push parity),
> #33 (PR #45 — Calibration V2), #34 (PR #46 — feedback learning),
> #35 (observability wrap-up). #36 stays deferred — trigger evaluated
> against measured per-run metrics (see the issue). Current truth lives in
> `docs/RELEVANCE_CONTRACT.md` (umbrella), the per-layer contracts, and
> `docs/CURRENT_PROJECT_STATE.md`; the sections below are the original plan,
> kept for history.


- **PR 1 — taxonomy + entity resolver foundation** ([PR #26](https://github.com/Guy-Navon/signal-sports/pull/26)):
  `backend/app/taxonomy/` (~45 entities, competitions with membership+season
  slots, longest-match resolver, family-name abstention, integrity validation);
  classifier + LLM normalizer rewired to one source of entity truth; 1165
  backend tests green (baseline 1129); Ramat Gan / Kiryat Gat contamination
  fixed and verified on real stored headlines. Contract: `docs/TAXONOMY.md`.

- **PR 2 — ArticleFacts: competition evidence + consistency validation + trace**
  ([#28](https://github.com/Guy-Navon/signal-sports/issues/28)): 5 soft-migrated
  columns (`primary_competition`, `article_competitions`, `entity_ids`,
  `classification_trace`, `taxonomy_version`); a consistency-validation stage
  (`backend/app/classification/facts.py`) enforcing the sport/entity/competition
  triangle with recorded conflicts and abstention; last entity→basketball bias
  path removed; subtitle can now correct sport by joint weighted evidence;
  membership-derived legacy league drops the `league=NULL` rate; backfill extended.
  Contract: `docs/ARTICLE_FACTS.md`. 1188 backend tests green (baseline 1165).

## 4. Near-future roadmap (dependency order)

| Order | Issue | What it delivers | Depends on | Agent | Parallel |
|---|---|---|---|---|---|
| 2 | [#28 ArticleFacts](https://github.com/Guy-Navon/signal-sports/issues/28) | Evidence-backed competitions + entity IDs + conflicts + classification trace on articles; consistency-validation stage; weighted evidence (subtitle can correct sport); backfill | PR #26 | Opus (+ Fable design review) | A |
| 3 | [#30 Event validation](https://github.com/Guy-Navon/signal-sports/issues/30) | Table-driven positive-evidence validation for event types; `event_certainty`; `release` type; doubt → `news` | PR #26 (soft) | Sonnet | A (∥ #28) |
| 4 | [#29 Relevance visibility contract](https://github.com/Guy-Navon/signal-sports/issues/29) | Competition-aware matching incl. membership reach; leak removal (`major_importance_fallback` gone); profile-drift alignment; `less_like_this` fix | #28 | Sonnet (+ Fable feed-diff review) | B |
| 5 | [#31 LLM dependency metrics](https://github.com/Guy-Navon/signal-sports/issues/31) | Call rate / abstention / conflict rates persisted per run; quality endpoint + Sources UI trends | #28 | Sonnet | B (∥ #29) |
| 6 | [#32 Preference model v2](https://github.com/Guy-Navon/signal-sports/issues/32) | Affinity layers + layered scorer + contribution trace + `PUT /api/profiles/{id}`; shadow mode, flip after review | #29 | Opus (+ Fable shadow review) | C |
| 7 | [#33 Calibration v2](https://github.com/Guy-Navon/signal-sports/issues/33) | Backend-owned versioned ~24-example dataset (5-level scale), hierarchical additive inference → affinities, persistent apply | #32 | Sonnet | D (∥ #34) |
| 8 | [#34 Feedback learning](https://github.com/Guy-Navon/signal-sports/issues/34) | Trace-based attribution, bounded derived adjustments over the event log, scoped `never_show`, safety invariants | #32 | Opus | D (∥ #33) |
| 9 | [#35 Observability & docs](https://github.com/Guy-Navon/signal-sports/issues/35) | Debug evidence/conflict/rejected-scope panels; `RELEVANCE_CONTRACT.md`; doc truth sweep | rolling | Sonnet | rolling |
| — | [#36 Async enrichment](https://github.com/Guy-Navon/signal-sports/issues/36) | **Deferred.** Insert-first + async LLM enrichment. Build only if LLM time per run stays >2–3 min after the Facts PRs, or a <5-min freshness requirement lands | #28, #31 | — | deferred |

Hard sequencing: #29 not before #28 · #32 not before #29 · #33/#34 not before #32.

**Fable review checkpoints:** #28 validation-stage design (pre-merge) ·
#29 feed-semantics before/after diff · #32 shadow-mode disagreement analysis
before the engine flip.

## 5. What the product looks like when this lands

For Guy (basketball power user): the feed shows Israeli league / EuroLeague /
NBA stories broadly because he follows the leagues — with Maccabi Tel Aviv
stories boosted on top, not required for visibility. A Maccabi Ramat Gan
signing appears as a normal Israeli-league story. Generic international noise
is hidden, not parked in low_feed. Every item can explain itself in one
sentence ("כי אתה עוקב אחרי הליגה הישראלית" / "מכבי תל אביב — עדיפות מיוחדת").
A new user answers ~24 calibration cards and gets a working personalized feed
persisted server-side; more/less feedback nudges the profile safely (one click
never mutes anything). The debug console shows the full evidence → facts →
decision chain for any article, and the LLM call rate is a dashboard number
that goes down every time the taxonomy grows.

## 6. Explicitly NOT being built now

Adaptive calibration question selection · passive-behavior learning ·
clustering/fuzzy dedup · new sources · model upgrades/shopping · ingestion
concurrency or queues (see #36 trigger) · cloud-provider migration ·
embeddings as a personalization mechanism · any JS-engine port of new
intelligence.

## 7. Measured baselines to beat (2026-07-05, local DB)

| Metric | Baseline | Target |
|---|---|---|
| LLM call rate (eligible new articles) | ~60–65% | ≤25% after #28 |
| `league=NULL` rate | 73% | Substantially lower after #28 backfill (report actual) |
| Ingestion wall-clock (fresh ~88 articles, Ollama) | ~12 min | Falls with call rate; #36 only if still >2–3 min LLM time/run |
| Backend tests | 1165 | Grows every PR; screenshot cases stay as named regressions |
