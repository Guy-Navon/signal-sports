# #124 — Integrated Feed De-duplication Evaluation (Milestone 6 gate evidence)

**Verdict: every acceptance bar met on the frozen corpus.** One known, deliberate recall
limitation (news-state pairs) is documented below with its policy source.

Corpus: `data/backups/eval_141_snapshot_v2_20260715.db` — a frozen copy of the live corpus
(257 rss articles, 4 sources) **after** the #138 event-state corrections and with persisted
validated anchors + clusters backfilled through the one-matcher path. All figures below are
from the committed read-only harnesses; raw outputs live next to this report:

- `feed_dedup_eval_124_20260715.txt` — pair + component levels (`scripts/feed_dedup_eval_124.py`)
- `feed_before_after_124_20260715.txt` — ranked feed (`scripts/feed_before_after_124.py`)
- `components_manual_review_124_20260715.txt` — the full component listing manually reviewed

The integrated pipeline under test is the REAL `cluster_articles()`: hard gates → #142 claim
compatibility → #123 intra-source stage → lexical tiers → #141/#137 validated-anchor tier N →
coherence (tier-I-aware source uniqueness) → persisted clusters → #103 user-specific collapse.

## Pair level

| metric | result |
|---|---|
| must-merge pairs recovered | **25/26** |
| must-not-merge pairs violated | **0** |
| material-update pairs preserved separately | **1/1** (Diarra — rejected at stage 2.5, `claim_reversal_mismatch`, before any evidence is weighed) |

Every accepted edge carries its tier and evidence; every rejected truth pair carries its exact
reason (see the raw output). The single miss: `tp_balogun_red_card_decision`, a `news`-state
pair at Tier C 0.19 < 0.35 whose shared anchors may not rescue it — **the #142 decision**
(shared identity + the catch-all state is not sufficient). Two cards for one controversy piece
is the accepted cosmetic cost; weakening it would re-open the roundup false-merge class.

## Component level

| metric | result |
|---|---|
| components | 9 |
| impure components (vs unioned adjudicated groups) | **0** |
| false bridges / transitive expansion | **0** |
| material-update articles inside any component | **0** |
| same-source members without a proven tier-I pair | **0** (structural — coherence requires the direct edge) |

**Manual review of all 9 components: every one is a genuine single story** (Noskova ×2 ynet;
Madar signing ×3; Bryant ×2; McGregor ×2; Storonski ×4 across both spellings; Madar farewell
×4; Otooru ×3; Sinner ×2; Hankins ×4).

The review process itself produced the milestone's last architectural correction: the first
integrated run had 15 components, and manual review found 4 false merges **invisible to
fixture-scoped purity** (the bridged articles live outside the adjudicated groups) — two
England colour pieces on the shared player, a youth-final preview+result+reaction chain on the
team word, a result+reaction on the coach, and two unrelated negotiation roundups on an
incidental subtitle club mention at jaccard 0.016. The fix is a class rule, not a threshold:
anchor evidence is **subject** evidence — person-centric states only (`ANCHOR_EVIDENCE_STATES`)
and title-borne on at least one side (`shared_subject_anchors`). All four classes are frozen as
negatives in `test_anchor_edges_141.py`. This is the standing reason the #126 checklist keeps a
manual sample review: **fixture results certify nothing alone.**

## Ranked-feed level (`guy` — the profile that exposed the failures; engine v2)

| metric | before (flat) | after (collapsed) |
|---|---|---|
| cards | 52 | **39** |
| pushes | 5 | **3** |
| tiers | push 5 / high 17 / feed 26 / low 4 | push 3 / high 13 / feed 19 / low 4 |
| article-level decision drift | — | **0** (collapse is presentation-only) |
| stories lost | — | **0** |

Named product outcomes:

| story | before | after | canonical (displayed) |
|---|---|---|---|
| Yam Madar signing | 3 cards, **3 pushes** | **1 card, 1 push** | sport5 `rss_81f1e1469b` |
| Zach Hankins release | 4 cards | 1 card | israel_hayom `rss_4f41239da2` |
| Otooru extension | 3 cards | 1 card | sport5 `rss_b4f0c3b489` |
| Storonski (both spellings) | 3 visible cards | 1 card | ynet `rss_2e57fdfc5e` |
| Madar farewell (post-#138) | 3 visible cards | 1 card | sport5 `rss_c822881b17` |
| Noskova (same-source) | 2 cards | 1 card | ynet `rss_975426d1a4` (newest — republish supersedes) |
| Diarra contradictory reports | 2 cards | **2 cards** (correct) | — |

`casual_deni_fan`: 1 card before, 1 card after, 0 drift — the narrow profile is untouched.

## Status of the milestone laws, as measured

- *Rare ≠ story-identifying* — V1 validates against the LANGUAGE, and even its rare-ordinary
  leakage is inert under the subject-evidence rule (manual review: 0 false merges).
- *A candidate span is not an anchor* — only validator-accepted, persisted anchors reach the
  matcher; `נשאר אדום` never does (test-locked).
- *A shared anchor is not a duplicate event* — state restriction + titleness + claim gate +
  hard gates precede any anchor edge; Diarra and the Bellingham/roundup classes prove each
  clause.
- *A duplicate edge is not yet a safe cluster* — coherence + tier-I-aware source uniqueness;
  0 impure components corpus-wide.

Closes #124. The remaining activation steps (live backfill, live before/after capture, flag
flip) belong to #126 exclusively.
