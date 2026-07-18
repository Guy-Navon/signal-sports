# M8-5 (#175) — Feed Freshness Real-Data QA & Activation Record

Date: 2026-07-18. Frozen corpus: `backend/data/qa_freshness_m8_frozen.db`
(sqlite backup-API copy of the production DB taken 2026-07-18 ~19:26 UTC; the
live corpus was never touched by QA). Raw metrics:
`docs/qa/feed_freshness_m8_report.json`. Script:
`backend/scripts/feed_freshness_qa_m8.py` — runs the exact production consumer
path (learned profile, dismissed filtering, `include_hidden=False`, cluster
collapse, Preference V2) with `FEED_FRESHNESS_ENABLED` off vs on, plus the
planner's canonical push enumeration, for both permanent profiles. Read-only.

## Baseline (the bug, quantified)

Corpus at freeze: 565 rss_ articles — 155 within 36h, 145 at 36–72h, 240 at
3–7d, 25 at 7–30d (oldest 2026-07-10). **73% of the corpus was older than 36h
and every bit of it was fed into ranking**, because no freshness filter
existed anywhere (`build_feed` scored everything `get_rss_articles` returned).
One future-dated row existed (walla_sport, +40 min — inside the 15-min-plus
skew the M8-4 clamp tolerates at that magnitude going forward it would be
kept; nothing clamps retroactively).

## Before / after — consumer feed (window off → on)

| Metric | Guy | Casual Deni Fan |
|---|---|---|
| Visible cards | 85 → **21** | 7 → **5** |
| Oldest visible article | 202.4h → **35.4h** | 169.9h → **35.4h** |
| Cards removed (all >36h) | 64 | 2 |
| Removed per tier | push 6, high_feed 20, feed 31, low_feed 7 | high_feed 2 |
| Removed per source | israel_hayom 26, sport5 16, ynet 11, walla 11 | walla 1, israel_hayom 1 |
| Clusters hidden (all members expired) | 10 | 0 |
| Canonical replaced (mixed-age cluster) | 0 — see note | 0 |
| **Decision drift among fresh articles** | **0** | **0** |
| **Fresh cards lost** | **0** | **0** |
| After: age distribution | 0-12h: 5, 12-24h: 3, 24-36h: 13 | 0-12h: 1, 12-24h: 1, 24-36h: 3 |
| After: tier distribution | push 2, high_feed 4, feed 10, low_feed 5 | high_feed 5 |

Mixed-age-canonical note: the frozen corpus contained no cluster straddling
the cutoff at freeze time (cluster spans are bounded at 72h and current
components are tight), so the canonical-replacement path shows 0 live
instances. The behavior itself is test-locked
(`test_expired_representative_yields_inwindow_canonical` — expired
representative → fresh member displayed, `representative_hidden_fallback`).

## Notification surface

Planner push enumeration (the exact surface `plan_cycle_notifications` reads):

- Guy: 8 push stories → **2**. The **6 suppressed stories are precisely 6 of
  the 7 historical PUSH stories the M7-10 watermark already suppressed**
  (verified by canonical id against `notification_events`): the freshness
  window now makes the old-story flood *structurally impossible* rather than
  only watermark-suppressed. The 2 surviving in-window push stories are the
  two already-`sent` events (probe + first genuine story) — planning them
  again yields `already_notified`, creating nothing.
- Casual Deni Fan: 0 → 0 (no push-tier stories in corpus; profile has no
  notification pilot anyway).
- Notification lineage untouched (QA is read-only); `already_notified`
  protection verified separately by the planner test suite, including the
  expired-canonical-replacement case.

## Acceptance journey mapping (#170)

1–3: captured above + in the JSON (per-card ages; every >36h card survived
because no filter existed). 4–7: window applied; oldest visible 35.4h;
zero drift; tier counts recomputed post-filter (no pagination exists in the
API — the feed returns the filtered ranked list). 8: test-locked (no live
instance at freeze). 9: 10 live all-expired clusters disappeared. 10–12:
planner section above. 13: verified live post-activation (below). 14: backend
2366 passed / 1 skipped; frontend 423 passed. 15–16: this document.

## Activation (production default flip)

- `backend/.env`: `FEED_FRESHNESS_ENABLED=true`, `FEED_MAX_AGE_HOURS=36`
  (flipped 2026-07-18 after PR #177 merged).
- API + dedicated worker restarted; first post-activation scheduler cycle
  verified clean (see `CURRENT_PROJECT_STATE.md` activation record).
- **Rollback:** set `FEED_FRESHNESS_ENABLED=false` in `backend/.env`, restart
  API + worker. No data is written or deleted by the window in either
  direction; the flag flip is the entire rollback.

## What was deliberately not activated

Physical retention (`RETENTION_CLEANUP_ENABLED`) stays **false** (M8-6 #176):
the corpus (oldest row 2026-07-10) is entirely inside the 30-day retention
window — cleanup would delete zero rows today and is not needed for the
visibility fix. Revisit ~2026-08-09.
