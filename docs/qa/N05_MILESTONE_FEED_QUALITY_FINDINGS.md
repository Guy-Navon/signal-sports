# Feed-quality milestone: census and principled stop

2026-09-11. Base: `66f77f6`. Execution stopped after sequence steps 1–2,
before classifier design or implementation, under the brief's explicit stop condition.
This is an evidence deliverable, not completion of #191 or #192.

## Starting gate and census

`cd backend; .venv/Scripts/python.exe scripts/feed_ground_truth.py gate`
passed without accepts. The working tree started clean on the requested main SHA.
The census reads all 1,427 RSS articles (IDs starting with literal `rss_`),
including hidden rows, using the same repository selection as the gate.
816 are `news` (57.2%). Census results were posted before designing changes.

| Sport | All rows | news |
| --- | ---: | ---: |
| basketball | 349 | 168 |
| football | 842 | 495 |
| tennis | 26 | 12 |
| unknown | 210 | 141 |

| Source | All rows | news |
| --- | ---: | ---: |
| israel_hayom_sport | 358 | 217 |
| sport5_sport | 80 | 24 |
| walla_sport | 704 | 417 |
| ynet_sport | 285 | 158 |

| Classification method | All rows | news |
| --- | ---: | ---: |
| rules | 687 | 293 |
| llm | 74 | 49 |
| llm+rules_guardrail | 188 | 138 |
| rules_fallback_after_llm_failure | 478 | 336 |

This is not exclusively an LLM or rules problem. 336 news rows followed LLM
failure; 293 used rules without an LLM proposal. Among the remaining 187,
86 stored LLM proposals themselves say news and 101 propose another event.
These are provenance counts, **not proof that all 816 are misclassified**.
Eight news rows have a historical trace event.final different from the stored
event_type, so trace history alone cannot establish the current downgrade cause.
The evidence does not justify a blanket backfill or removing abstention.

## Why G4 cannot be fulfilled under the existing contracts

The persisted Deni profile has precisely two always_push rules: player
`player:deni_avdija` with exact event `major_trade` or `injury`.
The scorer requires an exact event match; affinity, importance and learning
cannot create push. See `app/services/preference_engine.py::_override_matches`
and `score_article_v2`, and `docs/RELEVANCE_CONTRACT.md`.

The audit searched the entire RSS corpus using canonical identity OR every
registered Deni alias across title, subtitle, original title and translated title.
It found **29 rows**, including four without canonical Deni identity. All 29
titles/subtitles were reviewed. None reports Deni being traded or injured.
The accompanying [machine-readable evidence](n05_milestone_census.json) records
all candidates, text, ratings when available, actual score contributions, and
the existing validator's trade/injury results. This is stored-corpus evidence;
no claims about the linked publishers' full article bodies are made.

The critical counterexample to the brief's framing is:

* `rss_4c34e0718aadb617f71b`: **דיווח דרמטי: דני אבדיה ופורטלנד עשויים לעבור לאוקלהומה**.
  Subtitle: **הכוכב הישראלי יעביר את ביתו ליעד חדש?**.
  This is the only Deni sample item rated `push` by the owner. It describes a
  possible relocation of Deni **and Portland**, not a player transaction.
  Stored event: news; actual decision: high_feed; matched rule: affinity_score.
  Existing `validate_event_evidence` returns valid=false for both major_trade
  and injury, so neither always_push override matches.
* Related corpus rows `rss_e5aec33af965ca2e02b1`,
  `rss_0d9fc8062280c8a7c90a` and `rss_24168840f962162b3de1` explicitly describe
  the franchise's dispute with the city, potential destinations and ownership.
  They corroborate the relocation interpretation within the stored corpus.
* `rss_2d693144f4586ef3278e` passes lexical major_trade validation because its
  subtitle says **אחרי הטרייד המסקרן על ג'ה מוראנט**. That is Morant's trade;
  the Deni subject is a conditional future contract extension. The owner rated
  this item feed. Promoting it would use another player's transaction to fire
  Deni's override, violating facts versus preference separation.
* `rss_07098f8939b1be430059` passes lexical injury validation with probable
  certainty due to absence vocabulary, but discusses national-team attendance:
  **אם אבדיה היה מגיע - הרוב היו מצטרפים**. It asserts no Deni injury and has
  no canonical Deni identity. Assigning injury to get a notification is unsupported.

The other 27 candidates fail both existing trade/injury evidence checks.
A broad news override would notify on ordinary Deni stories. Relabeling
relocation as major_trade would falsify the event; widening the exact-match
override or relaxing evidence would weaken the contract. None was done.

This does **not** prove relocation can never deserve push—the owner explicitly
rated it push. It proves the existing trade/injury rules cannot express that
preference truthfully on this corpus. A separately stated product decision for
relocation semantics and notification scope, or a real qualifying trade/injury
article, is needed to resume that goal. No new event type was introduced.

## Before → after (no behavior changes)

| Goal / guardrail | Before | After | Status |
| --- | --- | --- | --- |
| Guy shown_precision | 112/114 = 98.2% | same | gate passes |
| G1 Guy false_hide | 18.2% | 18.2% | not attempted; target ≤12% |
| G2 Guy push volume | 17 | 17 | not attempted; target ≤6 |
| G2 Guy push precision | 7/17 = 41.2% | same | not attempted; target ≥70% |
| Approved Guy notifications | 7 rated articles | same | unchanged |
| G3 visible cluster-card coverage | 20/242 = 8.3% | same | not attempted; target ≥20% |
| Deni shown_precision | 22/24 = 91.7% | same | gate passes |
| Deni false_hide | 0.8% | 0.8% | gate passes |
| G4 Deni always_push fires | 0 | 0 | blocked as explained above |
| G4 high_feed rated feed | 15/24 visible | same | not attempted; target ≤8 |

The goal's stop condition takes precedence over continuing steps 3–7 or the
stretch. No classifier, preference, cluster, planner, outbox, profile or live DB
writes occurred. No Telegram sends, baseline ratchet, or gate accepts occurred.
`news` remains reachable under its existing abstention contract; no replacement
design was attempted. #191/#192 and the stretch remain open.

The raw final gate output is [n05_milestone_gate.txt](n05_milestone_gate.txt).
No application code changed; full backend/frontend suites were not run for this
diagnostic stop. Verification is the read-only census, exhaustive candidate
review, actual scoring traces, and repeated ground-truth gate.
