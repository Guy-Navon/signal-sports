# Feed-quality implementation — #191 / #192

2026-09-11. Feature branch based on `87d3170`; no merge or deployment. This
continues the merged census, rather than repeating it. Measurements use the
same 1,427 frozen RSS articles and 282 owner ratings. No ingestion or Telegram
sends occurred. The local corpus received backed-up, reviewed corrections.

## Outcomes and limits

| Goal / measure | Before | After | Outcome |
|---|---:|---:|---|
| G1 Guy false hide | 18.2% | 18.0% | **12% not reached**; event-only lower-bound evidence below |
| Guy shown precision | 112/114, 98.2% | 113/115, 98.3% | Guardrail passes |
| G2 Guy push **articles**, gate units | 17, 7/17 approved | 7, 7/7 approved | **Literal article-volume target of 6 not reached** |
| G2 Guy actual planner **stories** | 15, 5/15 approved | 4, 4/4 approved | Notification target met; all previously approved pushes covered |
| G3 Guy cluster cards / visible articles | 20/242, 8.3% | 21/244, 8.6% | **20% not reached**; unsafe expansion rejected |
| G4a Deni high-feed items rated feed | 15 | 7 | Target met |
| G4b Deni relocation push | 0 | 1 | Target met; same article remains Guy `feed` |
| Deni shown precision / false hide | 91.7% / 0.8% | 91.7% / 0.8% | Guardrails pass |

The gate remains article-based. Neither its denominator nor its policy was
changed to count stories. The brief conflates article pushes with notifications:
the original Madar triplet already had full cluster membership, producing one
notification. Only one member carried the display card. Its actual starting
notification count was therefore 15, not 17. The supplementary measurement uses
the real `enumerate_push_stories`, including learned preferences and full DB
membership. Only freshness is bypassed to replay July's frozen corpus; it never
plans or sends an event. This is historical eligibility, not a claim that July
stories would notify in September.

Evidence: [before](n191_milestone_before.json), [after](n192_milestone_after.json),
[all decision changes and original push traces](n192_decision_diff.json).

## G1: the census lead was tested, and its explanation was refuted

All **101** `news` rows with a non-news historical LLM proposal already used a
valid enum. All 101 fail the existing semantic evidence validator. Restoring
them would bypass the evidence contract, not fix enum parsing.
[Per-row evidence](n191_llm_proposal_audit.json).

`news` remains reachable: genuine abstention is necessary. New ingestion records
the proposed/final event and `abstention_reason`, distinguishing a failed
semantic proposal from no positively supported event. Historical LLM traces are
preserved; this does not pretend to reconstruct every old failure.

An intentionally optimistic event-only oracle tries **every allowed event** on
each of the 31 starting false hides, preserving all other facts and the profile.
Even ignoring semantic validity, the floor is 10.30%. The only additional
football row this can rescue is `rss_479d4247413e00a5dd23`: a Maccabi Haifa radio
discussion about the squad, stored `release`, rated `low`. It becomes visible
only if called `title_win`. That is a false fact. Its weight is 55.8667, or
3.915 percentage points. Excluding that fabricated title win raises the
optimistic floor to **14.217%**, already above 12%. The other football false
hide is irrecoverable under every event type.

This proves a limit of **event-only correction with the existing facts and
visibility rules**, not an impossibility theorem for future taxonomy or product
work. Many remaining rows lack canonical entities or explicit competitions;
the earlier #190 findings explain those coverage and abstention limits. No broad
news affinity, inferred competition, or rules-only backfill was used.
[Reproducible oracle and all weights](n191_recall_bound.json):
`DATABASE_URL=<pre-change backup> python scripts/feed_recall_bound.py --out <report>`.

The justified correction connects the already-existing `analysis` and
`interview` types to positive format evidence and applies the already-shipped
Grand Slam assertion rule to two stored Sinner title-win rows. These editorial
types already existed in profile affinities, frontend labels and the explicit
never-cluster set. **Relocation is the only newly introduced product type.**
All 34 event corrections were reviewed; sport, entity IDs, competition,
confidence and classification method are preserved.
[Exact before/proposals](n191_event_corrections.json).

## G2: identity and severity together

All 17 original pushes are traced in `n192_decision_diff.json`, including owner
rating, persisted cluster membership and final factual attention evidence.

- **Madar ×3:** already one cluster and one notification. No planner repair was
  needed: it already runs after clustering and reads full membership.
- **Lundberg ×5:** the July 22/23 agreement pair is close enough but lacked a
  shared validated anchor (Jaccard 0.08 versus 0.30). The first name `איפה` is an
  ordinary Hebrew word, which blocks full-name generation. A surname immediately
  before a transaction verb is now proposed to the **unchanged** lexical
  validator. This recovers `לונדברג`; the two approved articles and another
  source form one cluster. The earlier July 20 agreement is 52.3–55.8 hours away,
  outside the 24-hour negotiation window. The signing-state roundup remains a
  separate development. The July 19 routine negotiation does not merit push.
- **Walker ×3:** the close pair has Jaccard 0.18 and no shared accepted anchor;
  the older report is roughly 193 hours away. All three describe ordinary
  negotiations/departure speculation, so all lose push without forced merging.
- **Six singles:** retrospective/rejected moves, an incidental former club,
  routine departure speculation, or an old injury interview. None is a current
  consequential development for the followed club; all retain normal visibility.

The facts stage records `attention.development` and `subject_entity_ids`.
An explicit signing/major-signing/negotiation/injury push override additionally
requires current agreement/completion, imminent renewal, or current injury;
team/player scopes require the target in the factual subject list. The imminent
renewal case has subtitle evidence that only minor contract-extension details
remain. This preserves the owner's approved Lundberg roundup without pretending
it is a confirmed signing or combining distinct event states.

Existing rows without this metadata retain historical behavior. The targeted
refresh covers every currently push-eligible article in both profiles; future
ingestion writes the evidence for every article. There is no second scorer or
notification-specific preference system. Rollout on another existing corpus
requires its own reviewed evidence refresh.

The four remaining Guy notifications are the Madar signing, two time-separated
Lundberg agreements, and the signing-state Lundberg roundup. All seven formerly
approved push articles remain in notified story membership. Two other owner
push ratings were already uncovered before this work and remain so; they are
reported, not counted as new losses. Outbox uniqueness and dispatcher semantics
are unchanged. Integration tests recover a cluster after sent, retryable failure,
final failure and unknown outcomes, and verify no second event is created.

## G3: safe recovery, with the target still unmet

Do not substitute **45/244 visible cluster members (18.4%)** for the requested
**21/244 cards (8.6%)**. A card is attached to one displayed representative.

The reviewed, applied scope has four membership changes: Lundberg recovery,
Sinner expansion, and removal of two clusters containing newly classified
editorial pieces. Interviews and analyses are explicitly never clustered.
[Exact reconciliation](n192_clusters_applied.json).

A rejected global experiment lowered every tier's Jaccard minimum to 0.10,
keeping other gates. It still produced only 33 visible clusters (13.5%), and
introduced false mergers: **Oturu's extension with Bryant's extension**;
**a player rejecting Hapoel/Maccabi with LeDay signing for Hapoel**; and
**Sharp discussing shooting technique with his game result**.
[All experimental groups](n192_rejected_threshold_experiment.json).
Global document-frequency context differs from bounded ingestion windows, so
this is diagnostic evidence, not a production replay or mathematical bound.

An earlier copy-only whole-window reconciliation also created an unrelated
Glazer/Tsunami Maccabi Haifa pair. It was rejected before any live cluster write.
The final adapter uses the same candidate loader, matcher and persistence code,
but closes its write scope only over affected old/proposed memberships. It
preserves unrelated historical clusters, including their existing defects.

**Stop decision for G3:** the validated recovery does not support 20%. Growing
coverage by merging distinct subjects, expanding story-state windows or treating
editorials as duplicate developments would violate story identity. Those changes
were not shipped. This does not establish that every possible future conservative
anchor improvement is exhausted; the remaining target is explicitly outstanding.

## G4: editorial scale and entity-scoped relocation

Nine Deni articles move high→feed under existing editorial affinities. Eight
were rated feed; one (`rss_b63e4f5f88329f126a0e`) was rated high and now becomes
under-ranked. This loss is reported alongside the eight corrected over-rankings.
No item becomes hidden. Guy's two recovered Sinner stories become high-feed;
the rated one was wanted at feed, so recall improves with an over-ranking cost.
The ten rejected Guy pushes become high-feed, not necessarily their exact owner
tier. Display-tier perfection was not pursued.

`rss_4c34e0718aadb617f71b` now has `event_type=relocation`, probable certainty,
and `event.subject_entity_ids=["player:deni_avdija"]`. The evidence combines a
coordinated player/franchise headline with a physical home move in the subtitle.
A private home move, ordinary player transfer, arena trouble alone, possessive
player mention, or negated destination does not satisfy this route.

Only Deni's persisted profile and future seed gain
`always_push × player × player:deni_avdija × relocation`.
The trace is `override / player:deni_avdija / push / always_push:relocation`;
Guy has no such rule and stays feed (base +2).
Relocation is explicitly clusterable with a 24-hour, strict same-state window.

## Validation and reproduction

All commands run from `backend`, with `.venv/Scripts/python.exe` as `python`.
`DATABASE_URL` selects a backup for historical reads; correction commands take
`--db` explicitly. No server, live fetch or send is needed.

1. Gate before and after #191: [before](n191_gate_before.json),
   [event corrections](n191_gate_after_events.json).
2. Gate after #192: [live result](n192_gate_after.json). Guy's checks all pass.
   Deni's intentional `no_drift` is accepted per the brief. Its first push also
   requires an explicit `push_volume` acceptance: the baseline's null precision
   cannot satisfy the gate's numeric precision-gain rule. The reason names G4;
   no gate policy is changed.
3. `python scripts/feed_milestone_quality.py --out <report>` records both units,
   story membership and all rated decision traces.
4. Corrections: `apply_191_event_corrections.py`,
   `apply_191_relocation_profile.py`, `apply_192_feed_evidence.py`, and
   `apply_192_clusters.py`. Dry-run defaults; event/evidence/cluster applies
   require exact reviewed reports. Cluster changes commit once, after review
   comparison, or roll back. Live apply also requires the explicit live flag.
5. Consistent SQLite backups preceded live writes: `pre_feed_quality_191.db`,
   `pre_feed_quality_relocation_profile.db`, `pre_feed_quality_192.db`, all under
   `backend/data/backups`. The corpus retains exactly 1,443 rows (including 16
   non-RSS rows). Article IDs are identical. Only event fields, attention traces,
   seven anchor rows and eight article cluster links changed. All notification
   tables are byte-value unchanged. See `n192_decision_diff.json` invariants.

Full checks: **2,529 backend tests passed, 1 skipped** (27 added relative to
2,502); **539 frontend tests passed**, lint/typecheck/build passed. Existing
Starlette deprecations and Vite chunk-size warning remain. All correction
reruns found zero event/evidence/profile changes and zero membership changes.

After the green live gate above, the baseline was ratcheted exactly once to
protect the measured gains. The post-ratchet [gate](n192_gate_ratcheted.json)
passes without acceptances. The baseline write itself completed; its subsequent
console summary hit Windows cp1252 output encoding. It was not rewritten again;
the read-only gate was rerun with UTF-8 output and passed. This records the authorized Deni profile movement,
not completion of the unmet G1/G3 targets. The original before/after gate
artifacts retain the old baseline comparison and explicit acceptance reasons.
The golden C1 podcast fixture now pins interview/probable/medium/feed; its
original negative title-win safety assertion remains unchanged.

UI verification steps (not a visual test claim): run `npm run dev` in frontend,
use backend data mode on `/feed`, and inspect a relocation item's kicker
(`מעבר עיר`). The frozen July corpus requires an explicit historical replay;
do not disable production freshness merely to make it appear.

The #194 stretch was not started: G1 and G3 targets remain unmet. Neither issue
is represented as fully closed by this implementation.
