# Story Clustering — v1 Contract

> ## ⚠️ STATUS: FULLY IMPLEMENTED — AND DARK-SHIPPED (`CLUSTERING_ENABLED=false`)
>
> Deterministic clustering v1 is **complete**: matcher, persistence, live ingestion stage,
> backfill/QA tooling, feed/API collapse, frontend card and Debug evidence are all built,
> merged and acceptance-tested (#99–#105, Milestone 5).
>
> **It is OFF in production by default, and that is deliberate.**
>
> ### ⚠️ CORRECTION (2026-07-14): the original activation verdict measured the wrong thing
>
> This document previously said clustering stayed off because the corpus had *"too few accepted
> clusters"* — an evidence-availability condition, with every declined near-duplicate declined
> *correctly*. **That was wrong, and the real feed disproved it.**
>
> The Checkpoint-2 QA counted **accepted clusters on the corpus** (it found 1). It **never
> counted duplicate harm in the ranked user feed.** A review of the real feed found it is *full*
> of duplicates — **including THREE PUSH notifications for ONE signing** (Yam Madar → Maccabi,
> from walla + sport5 + ynet).
>
> **We were never short of evidence. We were counting the wrong noun.**
>
> And the misses were not caution — they were **defects with named root causes**:
> - **`release` was never in `CLUSTERABLE_EVENT_STATES`** — a straight gap in this contract (#121).
> - **The coverage paradox reappears at SAGA scale** (#122): the Madar saga has ~13 articles, so
>   `מדר` exceeds `max_story_coverage = 6` and stops being discriminative. *The bigger the story,
>   the less likely we group it* — the same bug fixed at cluster scale in #100, one level up.
> - **Same-source duplicates** are excluded by design, and the real feed falsified that premise (#123).
>
> **The gate is therefore reframed:**
> > **OLD:** "enough accepted clusters on the corpus to judge precision"
> > **NEW:** "the ranked user feed shows each story once and pushes each story once — with zero
> > over-merges"
>
> **Still non-negotiable:** no matcher threshold may be weakened to manufacture merges. Every
> merge must trace to a **named root cause**. Relaxing cross-sport rejection, strict
> same-event-state, unknown-sport strictness, discriminative-token evidence, Jaccard floors,
> one-member-per-source or the coherence rules would convert a *classification error* into a
> *false story cluster the user reads as truth* — strictly worse than showing two cards.
>
> **Activation is gated by #126** (Milestone 6 — Feed De-duplication & Clustering Activation;
> #116 is superseded). `CLUSTERING_ENABLED=false` remains the production default until it passes.
> Regression corpus: `backend/tests/fixtures/feed_dedup_cases.json`.

**Status:** authoritative living contract for Milestone 5 (Real Story Clustering v1).
**Issue:** #99 (C1). Locks the semantics for #100–#105.
**Scope of this document:** what a cluster *is*, how membership is decided, how identity is
assigned, and how a cluster is presented per user. It is the single source of truth; if code
and this document disagree, one of them is a bug.

---

## 0. What problem this solves (and what it does not)

When several sources publish the same real-world story, the user should see **one card**, not
four. That is the whole goal: **less duplicate noise, one push instead of four.**

**Honest sizing.** Clustering is a **feed-quality / polish improvement plus push
de-duplication**. It is *not* a solution to feed noise. On the corpus audited in July 2026 it
collapsed a low-single-digit percentage of cards. The bigger noise lever remains the ~half of
the corpus classified `event_type=news`, which is a separate future track.

**Do not confuse clustering with URL dedup.**

| | URL dedup (`backend/app/ingestion/dedup.py`) | Story clustering (this document) |
|---|---|---|
| Question | "Have I already ingested *this URL*?" | "Do these *different URLs* report the same real-world story?" |
| Mechanism | `sha1(url)` → stable article id | Deterministic multi-signal matching |
| Status | **Unchanged by this milestone** | New |

They are different mechanisms and neither replaces the other.

---

## 1. Architectural position

```
INGEST → FACTS (classification/taxonomy) → [CLUSTERING] → VISIBILITY → PREFERENCE → LEARNING
                    ▲                                          ▲
                    │                                          │
        article facts are AUTHORITATIVE            per-article decisions happen HERE,
        and are NEVER rewritten by clustering      unchanged; clustering only COLLAPSES
                                                   the presentation afterwards
```

Two rules follow, and everything else in this document is downstream of them:

1. **Clusters are corpus-level grouping records, not facts and not user state.** A cluster says
   *"these article rows are about one story"*. It asserts nothing new about the world.
2. **Clustering is a representation layer above per-article decisions, never an input to them.**
   Every member article is scored independently by Preference V2 exactly as it is today.

---

> ## ⚠️ THE ARCHITECTURAL CONCLUSION (2026-07-14, #134)
>
> ### **Rare is not the same as story-identifying.**
>
> The v1 evidence model equates the two, and it is **exactly backwards on the cases that matter**.
> `מדר` — the token that literally *names the subject* of the story — is **not** discriminative
> (df=13, because saturation coverage inflates it). `יאללה` (*yalla*) **is** (df=2). So is `דולר`
> (*dollar*), `פרק` (*chapter*), and the **coach's name**.
>
> Measured consequence: an evidence-primary matcher scored **27/31 with ZERO fixture
> over-merges** — and **21 over-merges across 2,922 real corpus pairs**, merging Bryant's
> contract extension with Otooru's on the strength of *"for three more years"*.
>
> **The Jaccard floor was silently doing all the precision work.** It is not a similarity
> measure here; it is a crutch compensating for an evidence model that cannot tell a name from
> a filler word. That is why removing it is catastrophic and why no threshold value repairs it.
>
> ### **Names are a strong identity signal — but shared identity without shared event semantics must not merge.**
>
> The same player appears in his farewell, his signing, his shirt number and his next fixture.
> A shared name is necessary, never sufficient. Event state, timing and action must still agree.
>
> Tracked in **#135** (candidate-scoped evidence frequency), **#136** (story-identifying named
> anchors), **#137** (transliteration normalization), **#138** (cross-source event-state
> consistency). Full evidence: `docs/qa/CLUSTERING_122_ANALYSIS.md`.
>
> **The fixture negatives cannot certify a mechanism.** Only 4 of the 7 `must_not_cluster`
> groups survive the hard gates. Precision must be measured by **corpus-wide pair enumeration**
> against `tests/fixtures/clustering_adversarial.json` — hand-adjudicated, because an automated
> sweep mislabelled **three genuine duplicates** as over-merges, and freezing those would have
> locked the bug in permanently.

> ## THE THREE DISTINCTIONS (2026-07-15)
>
> ### **A candidate span is not an anchor.**
> ### **A shared anchor is not a duplicate event.**
> ### **A duplicate edge is not yet a safe cluster.**
>
> Each was learned by measurement, and each has its own stage.
>
> **1. A candidate span is not an anchor.** The high-recall generator proposes `נשאר אדום`
> (*"stayed red"*) as a name, because its premise — *"two adjacent non-vocabulary tokens is a
> name"* — holds only as far as the vocabulary is **complete**, and Hebrew is not a closed
> vocabulary. Ordinary verbs, nouns and adjectives satisfy it. So generation favours **recall**
> and **validation** favours **precision and may abstain**. Only **validated** anchors become
> merge evidence. Today the only validator is a canonical taxonomy match — everything heuristic
> abstains. Adding `אדום`/`שיא`/`הכל` to a stoplist would make the fixture pass **without
> fixing the abstraction**.
>
> **2. A shared anchor is not a duplicate event.** The Diarra pair genuinely **does** share the
> subject — and must **not** collapse, because the two reports **contradict** each other (one
> says the club has not given up, the other says he is signing elsewhere). Identity agreement
> cannot establish **interchangeability**. Corrections, reversals and materially changed status
> must remain separately visible; canonical-card selection must never silently discard a
> contradictory update.
>
> **3. A duplicate edge is not yet a safe cluster.** One false edge contaminates a whole
> component. Pair recall is **not** the KPI — a three-article group needs one **connected, pure
> component**, not three edges.
>
> ### The pipeline these imply
>
> | # | stage |
> |---|---|
> | 1 | existing semantic + temporal **hard gates** |
> | 2 | **candidate-scoped evidence** (#135) |
> | 3 | high-recall **anchor candidate generation** (#136) |
> | 4 | conservative **Hebrew anchor validation** ← *the open gap* |
> | 5 | **anchor normalization** (#137) |
> | 6 | **event-state compatibility** |
> | 7 | **material-update / claim compatibility** ← *new stage* |
> | 8 | **edge creation** |
> | 9 | **pure connected-component construction** |
> | 10 | feed-level **canonical selection** + activation evaluation (#124/#126) |

## 2. Invariants (immutable in v1)

These are not tunable. Changing any of them is a new contract, not a config change.

1. **Deterministic only.** No LLM, no embeddings, no vector database, no paid API. The LLM is
   not an "exception path" here — it is simply not used.
2. **Abstention beats incorrect clustering.** A missed cluster is a cosmetic loss. A wrong merge
   tells the user something false. When evidence is insufficient, **do not cluster**.
3. **Article facts are authoritative and immutable.** Clustering never rewrites `sport`,
   `event_type`, `entity_ids`, `importance`, or anything else on a member article.
4. **No cluster-level authoritative facts.** The cluster table stores grouping metadata only.
   Unioned entity ids, max importance, merged event facts — none of these are stored as though
   proven. Derived summaries MAY be returned for UI/Debug but MUST be marked non-authoritative.
5. **Preference V2 scoring semantics are unchanged.** Zero scoring-engine changes.
6. **The frozen JavaScript engine is unchanged.**
7. **Cross-source is a hard requirement.** Two articles from the same source never cluster in v1.
8. **Strict same-event-state.** No cross-state merging (see §5).
9. **Live / in-play articles are excluded from candidacy** (see §5.3).
10. **Shared discriminative-token evidence is mandatory.** Token overlap alone is never enough.
11. **Unknown sport is never a wildcard**; two *proven, different* sports are a hard reject (§6).
12. **Cluster identity is assigned at formation and never churns** (§8).
13. **Feedback, learning, mutes, read state, and decisions remain article-owned** (§10).
14. **No cross-user cluster state.** Clusters are identical for every user; only *presentation*
    differs (§9).
15. **No manual override system.** Repair is by rule change + idempotent recomputation (§11).
16. **No source ranking.** Representative selection uses existing evidence only (§9.1).

---

## 3. Tunables (calibrated, expected to change)

Everything here is a knob. Changing a knob bumps `rule_version` and requires re-running the
Checkpoint-2 corpus gate.

| Tunable | Meaning |
|---|---|
| `max_story_coverage`, `df_ratio_max` | discriminative-token thresholds (§7.3). `max_story_coverage` must be ≥ `max_cluster_size` — enforced in `ClusteringConfig` |
| the generic-token list | what can never be evidence: sports vocabulary + club family names (§7.3) |
| `min_rare_tokens` per tier | how much discriminative evidence each tier demands (§7.3) |
| `jaccard_min` per tier | token-overlap floor per tier (§7.3) |
| time window per event state | how far apart two members may be (§5.2) |
| `max_cluster_size` | suspicious-merge guard (§7.4) |
| `max_cluster_time_span` | global coherence bound (§7.4) |

> **The invariant is "a match requires shared discriminative evidence." The thresholds that
> operationalise it are tunable. Do not confuse the two.**

---

## 4. Data model (metadata only)

```
story_clusters
  id                    TEXT PK   -- formation-time identity, never churns (§8)
  anchor_article_id     TEXT FK   -- founding member; the basis of the id
  event_state           TEXT      -- the single event_type all members share (a GROUPING KEY, not a fact)
  sport                 TEXT NULL -- grouping key only; NULL when members were unknown-sport
  formed_at             DATETIME
  last_member_added_at  DATETIME  -- OPERATIONAL/DEBUG metadata only. NEVER used for feed sort (§9.3)
  method                TEXT      -- "deterministic" (the only value in v1)
  rule_version          INT       -- which rule generation produced this cluster

cluster_edges                     -- ACCEPTED match evidence only; NOT facts
  cluster_id, article_a, article_b,
  jaccard, hours_apart, rare_tokens JSON,
  entity_overlap JSON, competition_overlap JSON,
  gate_applied TEXT               -- which tier accepted this edge
```

Membership lives on the **existing** `articles.cluster_id` column
(`backend/app/db/orm_models.py:30`, currently dormant) → **no `articles` migration.**

**Rejected candidates are NOT persisted.** Near-miss diagnostics are bounded and computed **on
demand** for QA/Debug. Persisting every rejection is an unbounded write amplification with no
proven need.

---

## 5. Event-state compatibility

### 5.1 Strict same-state only

A pair may cluster **only if both articles share the same `event_type`**.

**Clusterable states** — the same real-world event, reported by several sources:

| Group | States | Window |
|---|---|---|
| Transfer cycle | `signing` · `release` · `major_trade` · `negotiation` · `candidate` · `rumor` | 24h |
| Results | `match_result` · `finals_result` · `title_win` · `grand_slam_winner` · `playoff_result` · `regular_season_result` · `early_round_result` | 12h |
| Injury | `injury` | 48h |
| Generic | `news` | 24h |

> **⚠️ THE SILENT-OMISSION TRAP (fixed in #121).** An event type present in **neither**
> `CLUSTERABLE_EVENT_STATES` **nor** `NEVER_CLUSTERED_EVENT_STATES` does **not** "default to
> safe". It falls through the event-state gate and becomes **unclusterable at ANY similarity —
> silently**.
>
> **Seven** event types were in that hole for an entire milestone: `release`, `major_trade`,
> `title_win`, `grand_slam_winner`, `playoff_result`, `regular_season_result`,
> `early_round_result`. In the real feed this produced **four near-identical cards for one
> Maccabi release**, and it is also why the Noskova pair (`grand_slam_winner`) was unmergeable.
>
> **Every event type the classifier can emit MUST be an explicit, deliberate member of exactly
> one set.** `test_every_event_type_is_explicitly_classified` enforces this, so the omission
> cannot recur.

**There is no cross-state compatibility in v1.** Rumor, candidate, negotiation, and signing are
**distinct story developments**, not phases of one object. Collapsing them would tell a user a
deal is *done* when it is *stuck* — see the Halaili fixture, where three articles about one
transfer saga correctly form **three** separate outcomes.

Every true-positive group in the audited corpus was already single-state, so strictness costs
nothing measurable and removes an entire class of risk.

**Never clustered at all:** `schedule`, `preview`, `interview`, `analysis`, `opinion`. These are
*different perspectives*, not duplicates — collapsing them would hide exactly the editorial
variety the product wants to preserve.

### 5.2 Time windows (tunable)

| Event state | Window |
|---|---|
| `signing`, `negotiation`, `candidate`, `rumor`, `news` | 24h |
| `match_result`, `finals_result` | 12h |
| `injury` | 48h |

The window is a **precision instrument, not a convenience**: it is what separates the youth
quarter-final from the semi-final (48.6h apart, jaccard 0.60 — a *very* strong token match that
is nevertheless a different event).

### 5.3 Live / in-play exclusion

Articles that are live match snapshots (`מחצית`, `חי`, an in-progress score shape) are **excluded
from candidacy entirely**. A half-time state and a full-time result are different facts, and
chaining live updates is out of scope for v1.

---

## 6. Sport compatibility

| Situation | Rule |
|---|---|
| Both sports proven and **equal** | proceed (Tier A/B) |
| Both sports proven and **different** | **HARD REJECT** — no amount of token or entity evidence overrides this |
| Either sport `unknown` | **not a wildcard** → escalate to **Tier C** (§7.3) |

**Why unknown must not be permissive:** `unknown` means *we could not prove the sport*, not
*any sport is fine*. Treating it as a wildcard would let the noisiest, least-resolved articles
match the most things — precisely backwards.

**The Maccabi/Hapoel control.** The registry deliberately models cross-sport twins
(`team:maccabi_tlv_bb` / `team:maccabi_tlv_fc`, and the Hapoel equivalents) so a bare club name
stays ambiguous. Two articles that both resolve "מכבי תל אביב" — one to basketball, one to
football — share club tokens, share the event state, and may be minutes apart. **They are a hard
reject.** Separately, a *bare family name* (`מכבי`, `הפועל`) resolves to **no entity** (taxonomy
abstention, locked by #64), so it can never supply Tier-A corroboration and can never be the
thing that carries a match.

---

## 7. Matching contract

Staged, cheapest-and-most-decisive first. A pair must pass **every** stage.

### 7.1 Hard gates (any failure ⇒ reject immediately)

1. different `source` — **same-source pairs never reach this matcher**; since #123 they are
   routed to the dedicated intra-source republish stage (§7.5) instead, under a much stricter
   contract;
2. same `event_type` (§5.1), and it is a clusterable state;
3. neither article is live/in-play (§5.3);
4. within the event-state time window (§5.2);
5. sport-compatible (§6).

### 7.2 Token normalization

Lowercase; strip Hebrew punctuation (`״ ׳ " '`) and general punctuation; drop stopwords **and
headline-template words** (`רשמי`, `דיווח`, `דרמה`, `ממשיכה להתחזק`, `צפו`, `נחשף`, `בלעדי`, …).

Template stripping is not cosmetic — it is a precision mechanism. Hebrew sports headlines are
formulaic, and the audit found two entirely unrelated signings sharing
*"ממשיכה להתחזק: X חתם ב-Y"*.

### 7.3 Discriminative-token evidence — **the precision backbone**

Signal Sports serves a **bounded rolling corpus** (the consumer feed horizon is roughly the
last **36 hours**). The matcher must therefore be correct on a window of *tens* of articles.
**There is no minimum corpus size and no accumulation prerequisite — anywhere.**

```
token_df       = documents in the candidate lookback window containing the token
token_df_ratio = token_df / max(actual_window_size, 1)

token_is_discriminative =
      NOT generic(token)                       # stopword | headline template |
                                               # generic sports vocabulary | club FAMILY name
  AND ( token_df <= max_story_coverage
        OR token_df_ratio <= df_ratio_max )
```

**Invariant:** a match requires **shared discriminative evidence** — *and a story-specific
token must not become non-discriminative merely because multiple sources cover the same
story.*

**Tunable:** `max_story_coverage`, `df_ratio_max`, the per-tier minimum count, and the generic
list. **Defaults:** `max_story_coverage = 6` (aligned with `max_cluster_size`),
`df_ratio_max = 0.01`.

#### The coverage paradox — and why the absolute floor is keyed to story coverage

A story covered by **N sources gives its own defining token a `df` of ≈ N**: "רקנאטי" appears
in exactly the four articles about the takeover. If the absolute floor sat **below** the
cluster size, a story would become **less clusterable the more sources reported it** — exactly
backwards. So the floor is **`max_story_coverage`**, aligned with `max_cluster_size`: *a token
appearing in at most one story's worth of documents is still story-specific by definition.*
`ClusteringConfig` refuses to construct with `max_story_coverage < max_cluster_size`.

#### Where precision comes from on a small window

**Lexically, not statistically.** In a 30-article window "העונה" appears twice and looks
statistically "rare" — a denominator cannot save you. So rarity is established by an explicit
**generic-token** exclusion (`tokens.py`): common sports vocabulary (`חתם`, `חוזה`, `הגארד`,
`האמריקאי`, `ניצחון`, `העונה`, `משחק`, `ליגה`, …) and **club family names** (`מכבי`, `הפועל`,
`עירוני`, `בית"ר`, including single-letter-prefixed forms like `בהפועל`) can contribute to
*similarity* but can **never be the evidence a match is built on**. This is also what enforces
the taxonomy's family-name abstention (#64) at the clustering layer.

`df_ratio_max` is a **secondary rescue for large windows only**, where a genuinely common word
can exceed `max_story_coverage` in absolute terms.

> **Explicitly rejected:** denominator smoothing to an artificial reference corpus, and any
> minimum-window / minimum-corpus gate. Both would make the product wait for data it will never
> have.

**Tiers:**

| Tier | Applies when | `jaccard_min` | `min_rare_tokens` |
|---|---|---|---|
| **A — corroborated** | shared proven **entity** or **competition** | 0.30 | **1** |
| **B — standard** | both sports proven & equal; no entity/competition overlap | 0.35 | **1** |
| **C — strict** | `event_type = news` **OR** either sport `unknown` | 0.35 | **2** |

Tier A is looser *because* it has independent corroboration. Tier C is strictest because it
covers the two weakest evidence situations — and `news` is roughly half the corpus.

**Entity is a confirmer, never a gate.** Several genuine clusters in the audit had
`entity_ids = []` on one or more members. Hard-blocking on shared entity would have abstained on
a large share of true positives. Entity *lowers the bar* (Tier A); its absence never raises a
wall.

### 7.4 Grouping and the coherence invariant

Accepted pairs are grouped by connected components (union-find) — **but plain union-find is NOT
sufficient.** A weak chain `A~B`, `B~C` can drag unrelated `A` and `C` into one cluster.

**Coherence rules:**

1. An initial accepted **pair** may form a cluster (the seed; its earlier member is the anchor).
2. A **late member must match the ANCHOR, OR at least `min_member_matches_to_join` (2) existing
   members.** One weak edge to one *peripheral* member is not enough to join.
3. **ONE MEMBER PER SOURCE** — see below.
4. The resulting cluster must remain **globally compatible**: a single `event_state`, a
   compatible `sport`, a total span within `max_cluster_time_span`, and unique sources.
5. **Backfill applies final coherence validation *after* candidate grouping**, so transitive
   chains formed during batch processing are broken up rather than silently merged.
6. `max_cluster_size` guard: a cluster exceeding it is **flagged as a suspicious merge**, not
   silently accepted.

#### Source uniqueness is a CLUSTER invariant, not merely a pair gate

The cross-source **pair** rule does **not** prevent two articles from the same source landing in
one cluster through a third:

```
A (source X) ~ B (source Y)        both legal pairs …
C (source X) ~ B (source Y)        … yet union-find puts A, B and C together
```

That quietly re-introduces the same-source update chaining v1 declares a non-goal. So for v1:

- a cluster may contain **at most one member per source**;
- a candidate from a source already represented is **rejected from that cluster**;
- the incumbent is **not** automatically replaced — it arrived earlier on at least as strong
  evidence, and silently swapping members would make cluster composition depend on arrival order;
- the rejected article is simply **left unclustered**;
- **no transitive path may bypass this** — it is enforced in the cluster-compatibility check, not
  only at pair level. Even the fact-richest article (which would win the representative ladder)
  cannot join a cluster whose source it duplicates.

> **CONTRACT CORRECTION (#100) — rule 2 originally said "match the current REPRESENTATIVE".
> That was unsafe and is now wrong.**
>
> The representative is a **display** concept chosen by **fact completeness** (§9.1). A bridging
> article is typically the *richest* one — it names both clubs, or both players — so it tends to
> **win the representative ladder**. "Match the representative" would then be satisfied by
> matching *the bridge itself*, admitting exactly the transitive chain the rule exists to block.
> A test written for this reproduced the failure.
>
> Coherence needs a **structural** notion of centrality, not a factual one. The **anchor** is
> that: earliest, part of the seed pair, chosen by publication order — a later, derivative bridge
> can never become it. Keying rule 2 on the anchor blocks the chain **and** admits the genuine
> 4th Recanati source, whose short headline matches the anchor strongly but falls just under the
> jaccard floor against the two longer articles.

When the evidence is ambiguous, **default to precision-first abstention.**

> **#123 REVISION — source uniqueness is now "unless PROVEN republish", and nothing more.**
> A same-source pair may co-exist in a cluster **iff that exact pair carries a tier-I
> intra-source edge** (§7.5) — the near-republish proven under the stricter dedicated contract.
> Same-source co-membership **by transitivity remains banned**: two same-source articles never
> directly proven to be republishes of each other cannot share a cluster, no matter what
> connects them. The admission rule requires a tier-I edge to **every** same-source incumbent.

### 7.5 Intra-source near-republish dedup (#123) — `app/clustering/intra_source.py`

The cross-source gate's premise ("the audit found zero same-source duplicate pairs") was
falsified by the live feed: ynet published the same Wimbledon result twice, 1h45m apart
(Noskova). The fix is **not** blanket same-source clustering — it is a dedicated stage with a
separate, stricter contract:

- **TITLE similarity is the republish signal.** Measured on the frozen corpus: the true
  republish scores `title_jaccard 0.43 / title_containment 0.60 / 7 shared discriminative
  tokens`, while the worst same-source negatives — two *different matches* under the same
  highlights template (`"צפו בתקציר: …"`) — top out at `0.25 / 0.43 / 1`, and reaction-piece
  traps (McGregor, Sinner) share up to **14** discriminative *subtitle* tokens at title jaccard
  ≤ 0.17. Full-text similarity is a trap in both directions; the bar is
  `title_jaccard ≥ 0.40 AND title_containment ≥ 0.55`.
- **`news` is excluded outright** (v1): the catch-all state is where columns, roundups and
  different-angle pieces live — no frozen case needs it and it is where a same-newsroom merge
  is least safe.
- Same event state (a rumour → confirmation sequence is two states), `≤ 6h` window, and the
  same candidate-eligibility as cross-source matching (a live-blog half-time snapshot is
  excluded before any rule runs).
- **Similarity alone is never sufficient**: ≥ 2 shared discriminative tokens (§7.3), the same
  precision backbone as cross-source matching.
- Edges carry **tier `I`** so Debug/QA can always distinguish a republish collapse from a
  cross-source story match.

**Canonical selection** is not re-invented: intra-source edges feed the same components and the
same §9.1 representative ladder (fact completeness → certainty → recency → stable id). Written
rationale: the survivor is the most informative telling; on equal facts the more certain, then
the **newer** one — a republish supersedes its earlier, thinner telling. The deduped sibling
remains listed as an alternate under the card (§9.2), never silently deleted, so a materially
different update is doubly protected: a changed headline fails the containment bar, and even a
collapsed member stays reachable.

### 7.6 Claim compatibility (#142) — `app/clustering/claims.py`

> **A shared anchor is not a duplicate event — and neither is a shared thread.**

The Diarra pair is the frozen proof (`material_update_same_thread`): same subject, same
transfer thread, 12h apart — and the reports **contradict** each other (israel_hayom: the Reds
are still pursuing him; walla: he will not sign). A user shown only one card is told something
false. Such pairs must remain separately visible.

The v1 rule is deterministic and narrow — no claim NLU:

- a bounded list of **outcome-reversal markers** (`"לא יחתום"`, `"בוטלה"`, `"ירד מהפרק"`, …) —
  the #125 negation/cancellation law applied at pair level;
- **title only** — corpus-audited: the israel_hayom member of the frozen Hankins must-merge
  group carries `"לא יגיע"` in its *subtitle* about a different player (incidental secondary
  claim), while every genuine reversal (Diarra, the cancelled Halaili deal) states it in the
  headline;
- a **conditional guard**: `"אם לא יחתום עד שלישי"` is deadline reporting inside an open
  negotiation, not a reversal;
- **asymmetry is the signal**: one side reverses → material update → **no duplicate edge**,
  through any evidence path (lexical, intra-source, or the validated-anchor path when #141
  wires it — the gate runs at stage 2.5, before similarity). Both sides reversing is two
  sources reporting the same collapse — genuine duplicates, still eligible;
- missing a reversal is SAFE (the pair still faces every other gate); falsely detecting one
  would block a genuine merge, which is why the list is title-only, guarded, and frozen-
  corpus-audited (live-corpus blast radius: exactly the Diarra and Halaili-cancellation
  reports).

Additionally decided under #142: **shared validated anchor + the catch-all `news` state is not
sufficient for a duplicate edge** — `news`-state pairs require corroboration from the existing
lexical matcher signal (Tier C). This binds the #141 anchor-edge wiring; no claim-fingerprint
architecture is built unless a frozen must-merge `news` pair fails without it. Thread/saga
identifiers for material updates are deliberately out of v1.

### 7.7 Validated-anchor evidence (#141 + #137) — tier N

> Rare is not story-identifying. A candidate span is not an anchor. A shared anchor is not a
> duplicate event. A duplicate edge is not yet a safe cluster.

The Hebrew-morphology failure mode — true duplicates whose formulaic token sets sit below every
jaccard floor (#122/#132 refutation) — is answered by **persisted, validated story anchors**:

- **Validation runs ONCE, at ingestion** (`run_anchor_enrichment_stage`, always on — fact
  enrichment, not clustering behaviour). The selected validator is V1, the pinned offline
  Hebrew language-frequency resource (`wordfreq==3.1.1`): *rare in the corpus is not rare in
  the language* — `מדר` (zipf 3.25) is a name; `אדום` (4.99) is a word; the band between is
  abstention. Span precision 1.00 / recall 0.68 on the adjudicated ground truth; deterministic;
  fails closed to canonical-taxonomy-only anchors. Full selection evidence:
  `docs/qa/ANCHOR_VALIDATOR_141_REPORT.md`.
- **Pair evaluation READS persisted anchors only** — never a model or analyzer per pair.
- **Tier N is a rescue, never a relabel, and never sufficient by itself.** It fires only after
  EVERY hard gate (incl. §7.6 claim compatibility) has passed, and only when:
  - the state is **person-centric** (`ANCHOR_EVIDENCE_STATES`: transfer cycle, injury,
    personal titles). In RESULT states the story is the MATCH — players, coaches and team
    words recur across every game, preview and colour piece, and the #124 manual review found
    exactly those false merges. Result states keep the lexical tiers; `news` is excluded by
    §7.6;
  - the shared anchor is **title-borne on at least one side** — a story's subject gets
    headlined by someone; incidental mentions (the two unrelated negotiation roundups sharing
    a subtitle club name at jaccard 0.016) live in subordinate clauses.
- **#137 transliteration skeletons** (collapse doubled matres, drop non-initial ו/י) join both
  the anchor match keys and the generation-stage population corroboration, as namespaced
  `translit:` keys that can only match each other — `סטורנסקי`/`סטרונסקי` are one validated
  identity, with zero collisions across the adjudicated names. Normalization operates on
  validated anchors only, by construction: an unvalidated candidate has no keys at all.

---

## 8. Cluster identity — stable at formation

```
cluster_id = "cluster_" + sha1(anchor_article_id)[:16]
anchor     = the founding member: earliest published_at, tie → lowest article id
```

Assigned **once**, when the cluster forms. **Late arrivals append; the id never changes.**

**Explicitly rejected:** content-addressed ids (`sha1(sorted member urls)`). A late-arriving
article would churn the id, breaking every downstream reference. There is **no `superseded_by`**
and no id-churn machinery, because there is no requirement for it.

**Operational idempotency — three required properties:**

1. **Repeated clustering creates no duplicate clusters.**
2. **Repeated clustering churns no existing ids.**
3. **Late arrivals append to the existing cluster atomically.**

**Live ingestion:** a new article is matched against existing clusters in the lookback window
*first*; on a match it is appended (`articles.cluster_id` + `last_member_added_at`) in one
transaction. A new cluster forms only when it matches *unclustered* articles.

**Recomputation / backfill:** recompute groups, then **reconcile to existing rows by maximum
member overlap and preserve the existing id**. Only genuinely new groups mint new ids.

### 8.1 The live ingestion stage (#101) — `app/clustering/ingest_stage.py`

```
fetch → source filtering → URL dedup → classification / Article Facts → insert → [CLUSTERING]
```

Never inside `_normalise()` / classification. The stage is a **thin adapter, not a second
algorithm**: it loads a bounded candidate window and calls the **same** `cluster_articles()`
that backfill (#102) calls, persisting through the **same** `reconcile_scope()`. Live and
backfill cannot drift apart because there is only one implementation to drift.

**Bounded recomputation.** The window spans the largest configured event-state lookback around
the newly-inserted articles — **there is no minimum corpus size** (§7.3). It then **hydrates the
full membership of every existing cluster the window touches**: a cluster whose members fall
partly outside the time window must never be evaluated incompletely, or coherence would be
judging a cluster it cannot see. Clusters wholly **outside** the scope are never touched, and
ids are preserved by overlap reconciliation.

**Rollout — `CLUSTERING_ENABLED`, default `false`.** This reuses the repository's existing
env-flag mechanism (cf. `CLASSIFICATION_LLM_GATING`, `ALLOW_DEV_RESET`) rather than inventing a
new one. **The live scheduler must not cluster the real corpus until the Checkpoint-2 gate
(#102) passes on a frozen copy.**

**Failure semantics — the article wins.** Clustering is a *quality-enhancement* stage and must
never corrupt ingestion. Articles are committed **per item** by `article_repository.insert` —
the existing run-accounting contract, in which one bad item is counted and the run continues.
Clustering follows that same contract: on failure the stage **rolls back, the articles survive
UNCLUSTERED**, and the failure is reported on the run result (`clustering_failed`,
`clustering_error`). Rolling back a correctly classified and inserted article because
*grouping* failed would be strictly worse. The stage commits **exactly once**, so a failure can
never leave partially persisted clusters or edges.

**Accounting** (live response only — no DB migration, following the `skipped_filtered`
precedent): `clustering_ran`, `clusters_created`, `articles_appended_to_clusters`,
`articles_left_unclustered`, `clusters_removed`, `clustering_failed`, `clustering_error`.
These are **separate counters**: clustering is never conflated with URL dedup.

---

## 9. Presentation — corpus cluster vs. user-specific view

**The cluster is global. What a user sees is not.** Three roles exist and **may be three
different articles**.

### 9.1 Corpus representative (global, user-independent)

Deterministic ladder — **no source ranking** (source quality is a separate future contract):

1. **fact completeness** — count of resolved `entity_ids`, `primary_competition`, a non-`news`
   `event_type`;
2. **event certainty** — `confirmed` > `probable`;
3. **publication recency** — newest;
4. **stable article id** — total determinism.

Because rung 1 prefers the most-resolved article, "score the representative" and "use the
strongest facts" converge by construction.

### 9.2 User-specific collapse (after Preference V2, which is unchanged)

- **Every member keeps its own independent decision.** Article-level decisions are byte-identical
  to a world without clustering. **Article-level decision drift must be zero.**
- **Eligibility:** a cluster is eligible for a user when **at least one member is visible**
  (decision ≠ `hidden`).
- **Card decision = MAX(decision) over that user's *visible* members**
  (`push > high_feed > feed > low_feed`).
- **Displayed member** = the corpus representative **if visible for this user**; otherwise the
  **highest-ranked visible member** (ties broken by the §9.1 ladder).
- **Priority member** = the visible member whose decision *set* the card decision. Recorded for
  Debug; may differ from both the representative and the displayed member.
- **Suppressed members** (hidden for this user) are **never resurfaced** in the consumer feed.
  Clustering must not resurrect content a user's preferences suppressed. They appear in Debug only.
- **Source count and "עוד מקורות" list VISIBLE members only.**
- **At most one push per cluster**, attributed to the priority member. This is a genuine *anti*-
  inflation property: four sources pushing one signing becomes one push.

### 9.3 Ordering

```
cluster_card.sort_at = MAX(published_at) among that user's VISIBLE members
```

**A hidden member must never bump a cluster in that user's feed.** The global
`last_member_added_at` is operational/debug metadata and is **never** used for feed ordering.

---

## 10. What clustering does NOT own

Feedback, learning, mutes, read state, and decisions remain **article-owned**:

- **feedback targets the currently displayed article** — the learning service is unchanged and
  feedback rows still reference article ids;
- **mutes** keep their existing article / source / topic contracts;
- **read state** is unchanged;
- **decisions** are per-article (§9.2).

Cluster-level behavioural semantics may be evaluated later. They are **not** in v1.

---

## 11. Repair

There is **no manual override system** and no force-split table. The repository has no generic
*corpus-level* override mechanism to borrow (`source_overrides` / `OverrideRule` are user-
preference constructs), so none is invented.

**The v1 repair contract:**

1. change the deterministic rules;
2. bump `rule_version`;
3. run **dry-run** (the default);
4. inspect the diff;
5. apply an **idempotent recomputation**.

A wrong cluster is a **rule bug**, and is fixed by fixing the rule — never by hand-editing rows.

---

## 12. Testing: frozen fixtures vs. mutable corpus QA

Two distinct, both-required layers.

### 12.1 Frozen contract fixtures — `backend/tests/fixtures/clustering_cases.json`

Committed **data**: the real audited headlines, sources, event types, and entity ids. **Never
queried from the corpus DB.**

> A regression suite that depends on a mutable, ungitted corpus DB is exactly the fragility that
> **destroyed the corpus** (issue #106). Frozen fixtures are reproducible, reviewable in a PR,
> and immune to corpus churn or loss.

These fixtures **must be sufficient to test the matcher (#100) with no corpus access.** Timestamps
are normalized to preserve the *measured pairwise deltas* (the original absolute times were lost
with the corpus) — deltas are the contract, wall-clock is not.

### 12.2 Mutable-corpus QA — #102 (C4), **Checkpoint 2**

Fixtures prove the **contract**; the corpus gate proves it on **live data**. Both required.

**The previous corpus baselines are void and must not be reused or reconstructed** — the
404-article count, the 0/311 drift snapshot, the Guy 8 / Deni 1 push counts, and the projected
404 → 391 clustering result all belonged to the destroyed corpus.

**The Checkpoint-2 QA process (defined now, executed at #102):**

1. **Have enough genuine cross-source examples for a meaningful manual precision review.**
   This is an **evidence-quality** requirement, **not a corpus-size gate** — the matcher itself
   has **no minimum window** (§7.3). We are not waiting for the *matcher* to work; we are waiting
   for enough real duplicate stories to *judge* it.
2. **Make a frozen COPY of the corpus database.** All matcher/backfill QA runs against **the
   copy**, never the live DB.
3. **Record the snapshot header:** timestamp, total articles, per-source counts, event-type
   distribution.
4. **Run matcher/backfill QA against that copy only.**
5. **Manually review every proposed cluster** — no aggregate-count-only sign-off.
6. **Require zero confirmed false positives before #103 (feed wiring) begins.**

Additionally, when a classification change is in play (as in #113), the review must
**distinguish intended upstream fact corrections from unrelated reclassification drift**, and
report them separately. An intended correction is not "drift", and drift must never be
laundered as a correction.

> **The live scheduler may keep rebuilding the corpus, but no clustering quality claim may use
> the moving live DB as a stable baseline.** A number measured against a DB that changes under
> you is not a measurement.

> **NEVER run a full-corpus LLM reclassification as part of clustering QA.** It is
> **nondeterministic** and introduces confounds that have no causal relationship to the change
> under test. This is not hypothetical: during #113 a full reclassification reported **22**
> `(sport, event)` changes, while the isolated, confound-free delta was **8** — the extra rows
> were the LLM re-rolling its own verdicts, plus snapshot-era false positives from a rule that
> had already been removed. Attribution used the isolated delta only.
>
> To measure a classification change: apply **only that change's rules** to the stored facts on
> a **copy**, and report the delta. That answers "what did this change do?" — a full
> reclassification answers a different, useless question.

---

## 14. Article lifecycle — feed visibility ≠ physical deletion

**Documented here, deliberately NOT implemented in #100 or #101.**

The active consumer feed shows roughly the **last 36 hours**. That horizon is a *presentation*
concern and must never be confused with storage:

- **An article being too old for the feed does not mean it should be deleted.**
- Several subsystems need **longer internal retention** than the feed horizon:
  **clustering** (a late source can join a story hours later), **URL dedup** (a purged URL would
  be re-ingested as "new"), **feedback provenance** (feedback rows reference article ids),
  **Debug**, and **QA / decision replay**.
- **Hard deletion / pruning is a separate lifecycle capability.** It must be independently
  specified, safe, and protected — the corpus is not in git and cannot be restored (#106).

Clustering's persistence contract must therefore **not assume the anchor article lives forever**
merely because the cluster id was derived from it (see §8 and the #101 pruning-safety review).
No retention scheduler or destructive cleanup exists in this milestone.

---

## 13. Non-goals (v1)

Embeddings · vector DB · paid APIs · **any LLM call** · cross-state story-line merging ·
same-source update **chaining** (the narrow republish dedup of §7.5 is in since #123; an
evolving-coverage chain — half-time → full-time, rumour → confirmation — remains out) ·
cluster-level authoritative facts · cluster-level feedback / read /
mute semantics · source ranking · manual override machinery · Preference V2 changes · frozen-JS-
engine changes · a cleanup migration for historical rows.
