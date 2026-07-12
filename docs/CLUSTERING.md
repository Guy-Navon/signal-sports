# Story Clustering — v1 Contract

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
| `df_abs_floor`, `df_ratio_max` | discriminative-token thresholds (§7) |
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

A pair may cluster **only if both articles share the same `event_type`**:

`signing~signing` · `negotiation~negotiation` · `candidate~candidate` · `rumor~rumor` ·
`injury~injury` · `match_result~match_result` · `finals_result~finals_result` · `news~news`

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

1. different `source`;
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

Computed over the **candidate lookback window**, never a frozen global corpus, so the rule
scales with volume:

```
df_ratio(token) = documents_in_lookback_containing(token) / total_documents_in_lookback

token is DISCRIMINATIVE  ⇔  absolute_df(token) <= df_abs_floor
                            OR df_ratio(token) <= df_ratio_max
```

**Invariant:** a match requires **shared discriminative tokens**.
**Tunable:** `df_abs_floor`, `df_ratio_max`, and the per-tier minimum count.
**Initial calibrated default:** `df_abs_floor = 3`, `df_ratio_max = 0.01` — the values that
reproduced the audited behaviour with zero false positives.

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

#### The coverage paradox — a hard constraint on the window (established in #100)

A story covered by **N sources has `df == N` for its own defining tokens**: "רקנאטי"
appears in exactly the four articles about the Recanati takeover, and essentially nowhere
else.

So if the discriminative threshold falls **below** the cluster size, a story becomes
unclusterable **because it is widely covered** — the more sources report it, the less likely
we group it. Exactly backwards. This silently dropped the 4-source flagship cluster during
implementation.

Therefore:

```
df_ratio_max × window_size   >   max_cluster_size
```

Because `df_ratio_max` is a ratio, this is really a constraint on the **candidate window**: a
lookback window that is too small **cannot support clustering at all** — DF there is not merely
imprecise, it is *inverted*. `ClusteringConfig.min_window_for_valid_df()` computes the floor and
`df_supports_full_size_cluster(n)` checks it. With the calibrated defaults
(`df_ratio_max = 0.01`, `max_cluster_size = 6`) the window must hold **≥ 700** eligible articles.

Never evaluate DF on a toy window; the statistic is meaningless below that floor.

### 7.4 Grouping and the coherence invariant

Accepted pairs are grouped by connected components (union-find) — **but plain union-find is NOT
sufficient.** A weak chain `A~B`, `B~C` can drag unrelated `A` and `C` into one cluster.

**Coherence rules:**

1. An initial accepted **pair** may form a cluster (the seed; its earlier member is the anchor).
2. A **late member must match the ANCHOR, OR at least `min_member_matches_to_join` (2) existing
   members.** One weak edge to one *peripheral* member is not enough to join.
3. The resulting cluster must remain **globally compatible**: a single `event_state`, a
   compatible `sport`, and a total span within `max_cluster_time_span`.
4. **Backfill applies final coherence validation *after* candidate grouping**, so transitive
   chains formed during batch processing are broken up rather than silently merged.
5. `max_cluster_size` guard: a cluster exceeding it is **flagged as a suspicious merge**, not
   silently accepted.

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

1. **Wait for adequate multi-source accumulation.** A corpus from a single ingest cycle has too
   little cross-source same-story overlap to prove anything.
2. **Make a frozen COPY of the corpus database.** All matcher/backfill QA runs against **the
   copy**, never the live DB.
3. **Record the snapshot header:** timestamp, total articles, per-source counts, event-type
   distribution.
4. **Run matcher/backfill QA against that copy only.**
5. **Manually review every proposed cluster** — no aggregate-count-only sign-off.
6. **Require zero confirmed false positives before #103 (feed wiring) begins.**

> **The live scheduler may keep rebuilding the corpus, but no clustering quality claim may use
> the moving live DB as a stable baseline.** A number measured against a DB that changes under
> you is not a measurement.

---

## 13. Non-goals (v1)

Embeddings · vector DB · paid APIs · **any LLM call** · cross-state story-line merging ·
same-source update chaining · cluster-level authoritative facts · cluster-level feedback / read /
mute semantics · source ranking · manual override machinery · Preference V2 changes · frozen-JS-
engine changes · a cleanup migration for historical rows.
