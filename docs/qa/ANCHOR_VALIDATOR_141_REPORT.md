# #141 — Hebrew Anchor Validation: Comparison & Selection (FINAL)

**Decision: V1 (`LexicalFrequencyValidator`) ships as the default production validator.
V2 does not ship. V3 fails its retention conditions and remains default-off reference code.**

Evaluation: `backend/scripts/anchor_validator_eval.py` against the frozen post-#138 snapshot
`data/backups/eval_141_snapshot_v2_20260715.db` (§12.2 discipline — never the moving live DB).
Raw output: `docs/qa/anchor_validator_eval_141_20260715.txt`.

## The insight V1 rests on (recorded for the contract)

> RARE IN THE CORPUS is not RARE IN THE LANGUAGE.
> `מדר` is common in our corpus (df=13; saturation coverage) and rare in Hebrew (zipf 3.25) —
> a NAME. `אדום` is rare in our corpus and common in Hebrew (zipf 4.99, "red") — a WORD.
> Corpus document frequency could never separate these; a Hebrew language-frequency resource
> can. Calibrated bands: ordinary ≥ 4.4 zipf; name-like ≤ 3.4; between them V1 ABSTAINS.
> Prefixed ordinary words (`בצהוב`) are judged by their MOST ORDINARY reading across candidate
> forms, the same way the matcher will read them.

## Results — deterministic validators, full corpus scope (257 articles, 9,687 candidates)

### Span level (hand-adjudicated ground truth; never auto-derived)

| validator | precision | recall | abstain | TP | FP | FN | אדום / שיא / הכל |
|---|---|---|---|---|---|---|---|
| V0 taxonomy (baseline) | 0.00 | 0.00 | 100% | 0 | 0 | 137 | abstained ×3 |
| **V1 lexical frequency** | **1.00** | 0.68 | 8% | 93 | **0** | 44 | **rejected ×3** |

Zero false accepts on the adjudicated set; every killer word rejected **without a stoplist**.
The recall gap is dominated by abstention-zone spans and candidate-generation variance, not
misrejections.

### Pair + component level (diagnostic anchor-only edges over hard gates)

| validator | must-merge | over-merges | material-update | edges | impure | latency/article |
|---|---|---|---|---|---|---|
| V0 | 0/24 | 0 | 0 | 14 | 0 | 0.2 ms |
| **V1** | 18/24 | **0** | 1 (Diarra — detected) | 89 | 1 | 2.1 ms |

Two readings matter:
- This diagnostic measures **anchor evidence alone** (over the hard gates). The single impure
  component is result-state bridging on a shared person/team word — exactly the class the
  SHIPPING rule excludes (`ANCHOR_EVIDENCE_STATES` + title-borne requirement, adopted after
  the #124 manual component review). The integrated pipeline measures **0 impure components,
  0 over-merges, 25/26 must-merge** (`docs/qa/feed_dedup_eval_124_20260715.txt`).
- The Diarra material-update edge is *detected* here and *blocked* in the shipping pipeline by
  the #142 claim gate at stage 2.5 — anchors never even get consulted for it.

### Precision-limit finding (recorded honestly)

V1 accepts rare-in-language non-names: rare Hebrew vocabulary (`תפגוש`, `התפרעויות`), non-person
entities (`נורבגיה`, `העתודה`), and apostrophe fragments (`וד` from `ג'וד`). On the frozen corpus
these are **inert** under the subject-evidence rule (person-centric states + titleness): the
manual review of all persisted components found **every component a genuine single story**. The
class is contained structurally, not by vocabulary patches — and the #126 live sample re-checks.

### Operational

- V1: deterministic (3-run probe STABLE), offline, pinned (`wordfreq==3.1.1`), 2.1 ms/article,
  fail-closed to abstention when the resource is missing (test-locked; canonical taxonomy
  anchors still persist — degraded V0 behaviour, feed unaffected).
- **V2/V3: operationally disqualified on the deployment hardware.** Measured evidence: ~9.5 s
  for a trivial pinned generate call; three evaluation attempts (full-scope, then truth-scoped
  with a 15 s call timeout) accumulated hours of wall time at near-zero model throughput and
  never completed. Operational failure mode is a first-class comparison axis in the closeout
  plan — a validator that cannot complete its own evaluation on the hardware it would ship to
  has answered the operational question.

## Decision, against the binding selection rule

- **V1 ships.** Span precision 1.00 with zero over-merges deterministically; the integrated
  pipeline meets every #124 bar. Nothing contradicts the plan's default.
- **V2 rejected** (as pre-committed): it could displace V1 only by avoiding a V1 precision
  failure — V1 has none — and it fails operationally regardless.
- **V3 fails retention.** Conditions (b) full-scope component purity and (c) low viable call
  rate are UNPROVEN/FAILED: unmeasured means unproven by the plan's own rule, and the measured
  call latency makes the escalation path non-viable. It remains in the codebase as evaluated,
  default-off reference (`HybridValidator`), fail-closed to V1 behaviour by construction.

## What shipped with the selection (the #141 wiring, on this branch)

1. Always-on ingestion enrichment persists validated anchors (`articles.story_anchors` +
   `anchor_validator_version`); pair evaluation reads persisted anchors only — no model, no
   analyzer, ever, per pair.
2. Matcher tier-N: shared persisted validated anchor rescues a below-floor pair ONLY after
   every hard gate (incl. #142 claim compatibility) passes, ONLY in person-centric states
   (`ANCHOR_EVIDENCE_STATES`), ONLY when the shared anchor is title-borne on at least one side,
   and NEVER for `news` (#142).
3. #137 transliteration skeleton: namespaced `translit:` match keys + generation-stage
   population corroboration — `סטורנסקי`/`סטרונסקי` resolve to one validated identity
   (Storonski 4→1), zero collisions across the adjudicated set, validated anchors only by
   construction.
4. Guarded backfill (`scripts/backfill_story_anchors.py`): dry-run default, #106 protection,
   idempotent per validator version.
5. `CLUSTERING_ENABLED` remains **false**; only #126 flips it.

Closes #141 and #136 (the PR-#140 boundary stops failing closed); the #137 acceptance and the
deterministic #142 rule land with the same PR.
