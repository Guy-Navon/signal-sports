# Feed Freshness — the 36-hour visibility window (Milestone 8, #170)

**Status: living contract.** Authoritative for the consumer-feed freshness window, the
publication-timestamp policy, and how freshness composes with clustering, notifications and
physical retention. Created 2026-07-18 (M8-1 #171 / M8-2 #172 / M8-3 #173 / M8-4 #174).

---

## 1. The product rule

Signal Sports is a **current** sports-news feed. An article whose normalized publication time
is older than **36 hours** must not appear in ranked consumer feeds and must not become a
Telegram PUSH notification — for every profile, with one shared rule.

This is a **visibility policy, not deletion**. Expired articles stay in the database under the
separate physical-retention contract (~30 days, `retention.py`, M7-3 #149 — still disabled as
of M8, see §8) and remain fully inspectable in the Debug feed.

Before M8 this horizon was *documented as an assumption* (CLUSTERING.md §5/§14, retention
docstrings) but **never implemented**: on 2026-07-18 the live ranked feed carried 410 of 565
RSS articles (73%) older than 36h, back to July 10. M8 made the horizon real.

## 2. The clock: normalized publication time

Freshness is measured against `articles.published_at` — the **source publication time**,
normalized to UTC at ingestion — never fetch/ingest time. A late-discovered old article ages
by its true publication date and must not look new merely because Signal fetched it recently.

Timestamp policy at ingestion (`_normalise_published_at`, M8-4 #174):

| Case | Behavior | `published_at_meta` |
|---|---|---|
| Source gave a usable timestamp | Normalized to UTC, stored | `NULL` (= source-provided; all pre-M8 rows read this way) |
| Naive (no timezone) timestamp | Treated as UTC (repo convention; adapters already localize known-zone sources) | `NULL` |
| No timestamp (e.g. some Sport5 cards) | **Bounded fallback**: ingest time, fixed at insert — so the article ages out of the window normally; the fallback can never keep an article fresh indefinitely | `{"provenance": "ingest_fallback"}` |
| More than **15 minutes** in the future | **Clamped** to ingest time; raw source value retained for audit | `{"provenance": "clamped_future", "raw": "<iso>"}` |
| Within 15 minutes future | Passed through (clock skew / scheduled-publish quirk; the predicate treats future as fresh) | `NULL` |

The 15-minute tolerance is a code constant (`FUTURE_TOLERANCE_MINUTES`), deliberately not an
env knob. Corpus evidence at M8 time: exactly **one** future-dated row existed (walla_sport,
+40 min) — no source has structurally unusable timestamps, so no per-source exception exists.

Malformed timestamps never reach storage: adapters return `None` when parsing fails, which
lands in the bounded-fallback row above.

## 3. The shared predicate — one implementation, one choke point

`backend/app/services/freshness.py` is **the only** implementation of the cutoff:

- `is_fresh(published_at, now)` — true when `published_at >= now − FEED_MAX_AGE_HOURS`.
  **Boundary rule: exactly at the cutoff is fresh.** Future-dated is fresh.
- `fresh_only(articles)` — batch filter with a single `now` per feed build.

It is applied in exactly one place: `build_feed` (`feed_service.py`), before scoring, for the
consumer path (`include_hidden=False`) only. Consequences, all test-locked
(`tests/test_feed_freshness_m8.py`):

- expired articles are never scored → never count toward tier totals or visible-card limits;
- cluster cards are built from in-window members only (§5);
- the Telegram planner (`enumerate_push_stories`) *invokes `build_feed`* and therefore
  inherits the window with **zero planner-side age logic** (§6) — a source-guard test asserts
  the planner module contains no freshness code;
- feed, notification and API layers cannot drift apart, because none of them reimplements
  the cutoff.

Both permanent profiles (Guy, Casual Deni Fan) — and every future profile — share the policy.

## 4. Configuration

```
FEED_MAX_AGE_HOURS=36          # the window; guarded parse (non-numeric / <1 → 36)
FEED_FRESHNESS_ENABLED=false   # code + .env.example default; production runs true (M8-5)
```

`FEED_FRESHNESS_ENABLED` follows the CLUSTERING_ENABLED activation pattern: merging the
capability changes nothing until the guarded activation gate (M8-5 #175) flips the production
`.env`. **Rollback = flip it back to `false` and restart the API + worker processes.** No
data is touched in either direction.

## 5. Clustering composition

Because expired members are filtered *before* scoring, cluster collapse (`cluster_collapse.py`)
sees only in-window members:

- a cluster is feed-visible only while it has ≥1 fresh, non-hidden member;
- the displayed canonical is always in-window: an expired corpus representative falls back to
  the best fresh member (`displayed_reason="representative_hidden_fallback"`) — an expired
  former canonical never keeps control of the headline/link;
- card `sort_at`, source counts and the members list cover fresh visible members only;
- a cluster whose members are ALL expired produces no card and leaks no members;
- expired members remain attached in the DB for lineage/dedup — nothing is detached.

Worked example (test-locked): cluster `{A: 40h old (representative), B: 2h old}` → one card,
displayed article B, members list `[B]`, sort_at = B's publication time. Cluster
`{A: 40h, B: 50h}` → nothing in the consumer feed; both fully visible in Debug.

## 6. Notification composition

- Expired stories never create notification events (the planner never sees them).
- Enabling/restarting the planner cannot notify about old PUSH stories: they are outside the
  window, on top of the existing watermark protection (M7-10 #156).
- Canonical replacement does not resend: notification lineage
  (`notification_story_members`) is keyed on the **full component membership from the DB**,
  including expired members — a story notified via article A stays `already_notified` when A
  expires and fresh duplicate B becomes the displayed canonical (test-locked).
- A genuinely new in-window PUSH story is planned normally.
- There is **no Telegram-specific age rule** — deliberately.

## 7. Debug and admin surfaces

The Debug feed (`include_hidden=True`) deliberately shows **everything** — hidden and expired
alike — because it exists to explain decisions. `GET /api/articles`, translation/ingest ops
routes and the shadow report likewise operate on the raw corpus, not the ranked feed; that is
intended and unchanged.

## 8. What was deliberately NOT done

- **Physical retention stays disabled** (M8-6 #176). It is not needed to fix visibility, and
  the corpus (oldest row 2026-07-10) is entirely inside the 30-day retention window — cleanup
  would delete zero rows today. Revisit when the corpus approaches 30 days (~2026-08-09);
  activation preconditions are documented in `retention.py` / `.env.example`.
- No per-league / per-source / per-user freshness windows; one product-wide rule.
- No clustering redesign; freshness composes with §9 collapse purely by input filtering.
- The `rss_adapter` `published_parsed` handling was left untouched: changing
  `time.mktime` → `calendar.timegm` would shift stored times for feeds that mislabel local
  time as GMT, and stored corpus times are observed ≈correct on this machine. Revisit only
  with per-source evidence of a systematic offset (none found in M8 inspection).

## 9. Evidence

- Implementation + tests: PR for #171–#174 (`test_feed_freshness_m8.py`, 27 tests; full
  backend + frontend suites green).
- Before/after real-data QA and activation record: `docs/qa/FEED_FRESHNESS_QA_M8.md`
  (M8-5 #175).
