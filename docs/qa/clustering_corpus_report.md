# Clustering — Checkpoint 2 corpus QA (#102)

**Verdict: Checkpoint 2 DOES NOT PASS — for lack of evidence, not for lack of precision.**
There were **zero false positives** (there were zero clusters), and the corpus contains too
few genuine cross-source duplicates to judge precision at all. **No thresholds were lowered
to manufacture clusters.**

---

## Snapshot

| | |
|---|---|
| Snapshot taken | 2026-07-13 |
| Source DB | `backend/data/signal_sports.db` (**read-only**; sha1 `e0e35cff4ce071db`, 1 073 152 B) |
| Frozen copy QA ran against | `backend/data/qa_snapshot_102.db` |
| Live corpus after QA | **byte-identical** — sha1 `e0e35cff4ce071db`, 0 clusters, 0 `cluster_id` set |
| Total articles | 273 (**257 rss** + 16 seed) |
| Per source | walla 118 · israel_hayom 66 · ynet 52 · sport5 21 |
| Rule version | 1 |
| Matcher config | `max_story_coverage=6`, `df_ratio_max=0.01`, tiers A(0.30/1) B(0.35/1) C(0.35/2), `max_cluster_size=6`, `max_cluster_time_span=72h` |

## Result

| | |
|---|---|
| Proposed clusters | **0** |
| Members | 0 |
| Cards before → after | **273 → 273** (no change) |
| Created / retained / changed / removed | 0 / 0 / 0 / 0 |
| **Manually confirmed false positives** | **0** |
| Near-miss reasons | `event_state_incompatible` 12 027 · `same_source` 8 028 · `below_threshold` 2 512 · `outside_time_window` 2 118 · `cross_sport` 1 421 |

## Manual review — every near-duplicate in the corpus

The corpus contains **only 3** cross-source pairs with title-token Jaccard ≥ 0.30. All three
are genuinely the same story. All three were rejected — and **not one was rejected by a
clustering rule that is wrong.**

| # | Story (2 sources) | Rejected as | Assessment |
|---|---|---|---|
| 1 | **Gal Raviv** — "רצינו שזה ייגמר אחרת…" (Israel youth women's Euro final) | `cross_sport: football / basketball` | **Upstream classification bug.** It is a basketball story; one source's article is classified `football`. The matcher correctly refuses to merge two articles whose *proven* facts contradict each other on sport. |
| 2 | **Yam Madar leaves Hapoel TLV** — "עוזב בראש מורם" | `event_state_incompatible: signing / news` | **Upstream classification disagreement.** Same event, two different `event_type`s. Strict same-state does exactly what it promised. |
| 3 | **McGregor UFC comeback** | `event_state_incompatible: match_result / injury` (sports also disagree: `unknown` / `football`) | **Upstream classification disagreement.** MMA is an untracked sport; the two sources disagree on both sport and event. |

**The matcher behaved exactly per contract in all three cases.** Merging any of them would
have required ignoring proven-but-contradictory article facts — i.e. propagating a *wrong*
fact into a cluster. Abstention is correct.

## The real finding

> **Clustering recall is hostage to cross-source classification consistency.**

Clustering can only group articles whose **facts agree**. Today the classifier frequently
assigns a *different* `sport` or `event_type` to the *same story* across sources, and the
cross-sport hard reject + strict same-state gates then (correctly) refuse to merge them.

This is a **classification-reliability** problem, not a clustering problem, and it is the
single largest blocker to clustering delivering value. Tracked separately.

**We must not "fix" this by relaxing clustering.** Loosening the sport/event gates would make
clustering merge articles that disagree on the facts — silently laundering a misclassification
into a cluster the user sees as one story. That is strictly worse than showing two cards.

## Fixtures

All frozen contract fixtures still hold (unit suite, corpus-independent):
- all 10 true-positive groups still cluster;
- all 7 must-not-cluster controls still separated;
- in-play still excluded.

## Safety

- `--apply` **refuses** the protected live corpus (asserted in `test_clustering_backfill.py`).
- Dry-run is the **default** and runs the *real* backfill against a scratch copy, so it is
  exact rather than an approximation, and writes nothing to the target.
- The live corpus was **never opened for write**: byte-identical before and after.
- `CLUSTERING_ENABLED` remains **false**, so the live scheduler is not clustering.

## Recommendation

1. **Do not begin #103 (feed wiring).** There is nothing to wire: zero clusters on real data.
2. **Fix cross-source fact consistency first** (new issue). Re-run this QA afterwards — the
   tooling is complete and ready; it needs no changes.
3. Let the corpus keep accumulating. The bar for Checkpoint 2 is **enough genuine cross-source
   overlap to judge precision**, not an article count.
