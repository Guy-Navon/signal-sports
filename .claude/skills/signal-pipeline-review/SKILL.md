---
name: signal-pipeline-review
description: Review Signal Sports changes to the ingestion, classification, clustering, persistence, scheduling and notification pipeline for idempotency, duplicate articles or notifications, updated-vs-new stories, wrong cluster merges/splits, partial failure and timeouts, overlapping jobs, transaction boundaries, timestamps and time zones, replay/backfill safety, and diagnosability. Triggers on diffs touching backend/app/ingestion/, clustering/, notifications/, worker.py, retention, results sync, backfill/apply scripts, or pipeline ORM tables. Supplies findings to signal-pr-open/signal-pr-merge; it is not a separate approval gate, and classification-rule correctness belongs to signal-classification-change.
---

# Signal pipeline review

A focused reviewer's pass for changes to the corpus-mutating pipeline. It produces **concrete
findings with code evidence**; `signal-pr-open` §5 (or `signal-pr-merge` §3–4) owns the verdict,
and `signal-pr-finish` owns which checks run. Don't add a second approval round, and don't demand
infrastructure the product doesn't need (distributed locks, queues, Postgres, a workflow engine).
The current design is honest single-node SQLite; review against *that* contract.

**Scope.** Use this skill when a diff touches `backend/app/ingestion/` (adapters, dedup,
orchestration, `ingestion_service.py`, retention, source state, run metrics),
`backend/app/clustering/`, `backend/app/notifications/`, `backend/app/worker.py`,
`backend/app/results/sync_service.py`, backfill or `apply_*` scripts in `backend/scripts/`, the
pipeline tables in `app/db/orm_models.py`, or the backfill/ingest routes. Otherwise hand off:
"is this headline classified right" → `signal-classification-change`; "is this decision right" →
`signal-relevance-change`; source config and adapters → also `signal-source-onboarding`; security
(tokens, untrusted input) → also `differential-review`; measuring cluster quality →
`signal-quality-eval`.

## 1. The pipeline and its contracts (read the code; these are the anchors)

```
worker tick / POST /api/ingest/run / scheduler run-now / startup catch-up
  → orchestrate_cycle()                      app/ingestion/orchestration.py
      acquire scheduler_lease (one conditional UPDATE; stale-heartbeat takeover → old cycle 'abandoned')
      → run_ingestion(): per enabled source  app/ingestion/ingestion_service.py
          adapter.fetch()  (never raises; [] on failure; 10 s timeouts)  adapters/*.py
          → per item: URL/language filter → URL dedup → _normalise (rules → LLM gate → merge → facts)
            → article_repository.insert (commits per article)
          → anchor enrichment stage → clustering stage (one commit; rollback on failure)  clustering/ingest_stage.py
      → notification planning (own session; feed-eligible PUSH cards → outbox lineage)  notifications/planner.py, outbox.py
      → notification dispatch (claim committed BEFORE send; timeout = 'unknown', never resent)  notifications/dispatcher.py
      → results sync (throttled, own session)  results/sync_service.py
      → retention cleanup (LAST; disabled by default)  ingestion/retention.py
      → finalize scheduler_cycles row in finally → release lease (only our own)
```

Stage order is a contract (orchestration docstring). Planning must see the full window before
retention; delivery never runs inside the ingestion transaction; failures after ingestion degrade
the cycle to `succeeded_with_warnings` and never undo inserted articles. Authoritative docs:
`docs/SCHEDULER.md`, `docs/RSS_INGESTION.md`, `docs/CLUSTERING.md` (§2 invariants, §8 identity,
§11 repair, §12 QA, §14 lifecycle), `docs/NOTIFICATIONS.md`, `docs/FEED_FRESHNESS.md`.

## 2. Review checklist — apply what the diff touches

For each concern: the invariant that holds today, where it lives, and what to look for.

### Idempotency across repeated runs and retries
- **Holds today:** article id = `rss_` + sha1(url)[:20] (`dedup.article_id_from_url`), the primary
  key; URL dedup before insert; cluster ids fixed at formation (`cluster_` + sha1(anchor)) and
  preserved by max-overlap reconcile; notification lineage
  `UNIQUE(profile_id, policy_version, article_id)`; the worker's startup catch-up runs one cycle
  rather than replaying missed ticks.
- **Look for:** new writes not keyed on a stable id; insert-or-fail where a second run needs an
  upsert or a skip; counters (`skipped_duplicate`, `inserted`) that double-count on rerun; a backfill
  whose second `--apply` changes anything. **Test it:** run the operation twice over the same
  fixture and assert the second run is a no-op.

### Duplicate articles and duplicate notifications
- **Holds today:** dedup is by **exact URL string**. Variants of one page (tracking query strings,
  http/https, trailing slash, mobile/AMP paths) produce different ids. Same-source near-republishes
  are grouped by the intra-source stage (#123) and cross-source copies by clustering; neither
  deletes rows. Notifications: one story = its member lineage, so expansion, cluster-id churn,
  canonical change and merges of notified stories create no second message; activation is
  watermarked.
- **Look for:** any change to URL normalization or the id function — it re-keys every future
  article, breaks `test_article_id_golden.py`, and detaches notification lineage (HIGH; needs a
  migration story). A notification path that keys on cluster id, headline, URL or canonical
  article (all explicitly forbidden in `outbox.py`). Any code that resets `claimed` or `unknown`
  events to `pending`. Planning outside the watermark and `TELEGRAM_NOTIFICATIONS_ENABLED` gates.

### Updated articles vs genuinely new stories
- **Holds today:** a re-fetched URL is skipped as a duplicate — the stored title and facts stay as
  first seen; there is no update path. A material development published under a new URL (for
  example, rumor → official signing) is a new article; clustering keeps event states strict
  (`docs/CLUSTERING.md` §5) and claim compatibility (#142) so it isn't absorbed into the old story.
- **Look for:** a change that starts updating stored rows on refetch (facts drift, notification
  re-eligibility, cluster anchor changes); a change that merges cross-state articles; a new
  "update" signal that silently re-notifies a story the user already got.

### Incorrect cluster merges and unnecessary splits
- **Holds today:** abstention beats a wrong merge; cross-source only; strict same event state;
  in-play excluded; shared discriminative-token evidence mandatory; unknown sport is never a
  wildcard; size and time-span coherence guards (`docs/CLUSTERING.md` §2, §7). Clustering never
  rewrites article facts. Repair is rule change + `rule_version` bump + dry run + idempotent
  recompute — never hand-editing rows (§11).
- **Look for:** a threshold or tunable change without a `RULE_VERSION` bump and a Checkpoint-2
  review on a **copy** (§12.2: every proposed cluster reviewed; zero confirmed false merges); new
  matcher evidence that bypasses the hard gates; frozen fixtures (`tests/fixtures/clustering_*.json`,
  `feed_dedup_cases.json`) edited to make a change pass. Measure with `signal-quality-eval`.

### Partial failures, unavailable sources, malformed input, timeouts
- **Holds today:** adapters return `[]` and log on any fetch/parse error; each item is wrapped in
  try/except and counted in `failed`; sources are isolated from each other; anchor and clustering
  stages fail safe (rollback, articles survive unclustered); post-ingestion stages degrade the
  cycle. A cycle is `failed` only when nothing was fetched or inserted and errors exist.
- **Look for:** a new raise path outside the per-item guard; one source's failure leaking into the
  next; a valid empty result (`fetched=0`, no error) conflated with a failure, or the reverse; an
  external call without a timeout; a broad `except` that hides programming errors as "source
  down".
- **Shared-session isolation:** the source loop shares one SQLAlchemy session across items and
  stages. After any failed flush or commit, that session is unusable until `rollback()`, so
  "per-item isolation" holds only if every `except` that can follow a failed write rolls back
  before the next use — including paths that write nothing themselves, such as stage early
  returns and the run-record write. When a diff touches this loop, check that a failure on one
  item cannot fail the next item, the next stage, or the next source, and test it by forcing a
  flush error mid-loop with and without an earlier successful insert. Known gap at the time of
  writing: #318 (verify current state before citing).

### Concurrent or overlapping jobs
- **Holds today:** one durable lease row; acquisition is a single conditional UPDATE that SQLite
  serializes; a heartbeat thread (own session, every 10 s) keeps a live run from being stolen;
  stale after `SCHEDULER_STALE_AFTER_SECONDS` (default 1800); overlapping triggers are recorded as
  `skipped_active_run` and coalesced; the manual API run gets 409 while one is active.
- **Look for:** a new corpus-mutating entry point that bypasses `orchestrate_cycle()` or the lease.
  Check whether a new or changed writer coordinates with live cycles: SQLite serialization
  prevents corruption, not logical interference (facts rewritten under the clustering stage, a
  recompute reconciling against rows being appended). Whether existing backfills must take the
  lease is an open question (#319); until it is decided, check
  `GET /api/ingest/scheduler/status` before applying anything to the live corpus, and ask Guy
  before pausing the worker. Also look for
  sessions shared across threads, or a lease release that could clear someone else's lease (it
  must stay conditional on our `cycle_id`).

### Transaction boundaries and recovery after interruption
- **Holds today:** per-article commits; clustering commits once at the end; `plan_story` writes the
  event and its lineage atomically (an `IntegrityError` rolls back the whole attempt); the
  dispatcher commits the claim before the network call; the cycle row is finalized in `finally`;
  a crash leaves a `running` row whose stale heartbeat lets the next acquirer mark it `abandoned`.
- **Look for:** network or LLM calls made while holding an open write transaction (SQLite has one
  writer; the API and worker block each other); a multi-row invariant split across commits so that
  a crash in between leaves it half-applied; a new stage inserted before planning that deletes or
  hides rows; recovery logic that "helpfully" retries non-idempotent effects.

### Publication timestamps, time zones, out-of-order arrivals
- **Holds today:** `published_at` is stored as an ISO-8601 **string** normalized to UTC
  (`_normalise_published_at`). SQL compares those strings lexicographically (the clustering candidate
  window in `ingest_stage.py`, retention cutoffs, lease heartbeats), which is correct only while every
  value is UTC ISO; Python-side freshness (`services/freshness.py`) parses them into aware datetimes. A missing timestamp falls back
  to ingest time with `published_at_meta.provenance = "ingest_fallback"`; a future timestamp beyond
  tolerance is clamped (`clamped_future`, raw kept). Site-local times are parsed as
  `Asia/Jerusalem` with DST via `zoneinfo` (Sport5, ONE); the fixed UTC+2 fallback applies only
  when tzdata is missing. Cluster windows use published-time deltas; the cluster anchor is the
  earliest member.
- **Look for:** naive datetimes, local-time `isoformat()` with a non-UTC offset, or `datetime.now()`
  without `tz` reaching storage or a comparison; a new parser that assumes UTC for site-local
  strings; freshness computed from ingest time; the case where an *earlier* article arrives
  *later* (it can change a recompute's anchor — one reason notifications key on lineage, not
  cluster ids).

### Safe replay and backfill
- **Holds today:** the backfill/apply scripts dry-run by default and need `--apply` plus
  `--i-know-this-is-the-live-corpus` for the real DB. `POST /api/classify/backfill` (admin-only)
  **writes by default**; pass `dry_run=true` to preview. Backfill never writes `ingestion_runs`
  (metrics honesty), and the corpus is protected (`app/db/corpus_protection.py`).
- **Look for:** a backfill without dry run, or without a report of what it would change; a backfill
  that isn't idempotent. **Standing rules:** never run a blanket rules-only backfill over the live
  corpus (it replaces LLM-derived facts with poorer ones), and never enable retention (it deletes
  rows that the census and ground-truth gate depend on). **Interaction hazard:** a backfill that
  makes in-window stories newly push-eligible will notify them in the next cycle *if Telegram is
  enabled* — the watermark only covers stories eligible at activation. Check
  `TELEGRAM_NOTIFICATIONS_ENABLED` and the feed window before applying.

### Diagnostics: can we explain a missing article or an unexpected notification?
- **Holds today:** `scheduler_cycles` (status, per-source results, notification and cleanup
  summaries, error summary); `ingestion_runs` (fetched / filtered / duplicate / failed + metrics);
  `classification_trace` on every article; `published_at_meta` provenance; notification events
  with status, attempt count, `last_error_class` and lineage notes; source health; on-demand
  clustering rejection reasons (never persisted).
- **Look for:** a new skip, drop or suppress path with no counter or reason; errors swallowed
  without a trace; reasons that can't distinguish "not push", "no watermark", "Telegram disabled",
  "already notified" and "send unknown"; secrets or personal data in error strings (the Telegram
  token is in the request URL).

## 3. Evidence and proportionate fixes

- **Every finding names the code** (file:line or function), a **realistic scenario** (inputs and
  state → wrong outcome), its **impact** (data loss, duplicate push, missed story, stuck cycle,
  misleading diagnostics) and the **smallest adequate fix**. Classify it as blocker / improvement /
  follow-up exactly as `signal-pr-open` §5 does.
- Prefer a regression test that reproduces the scenario (`test-driven-development`): a second
  run, a raised exception mid-loop, a stale lease, a duplicate URL, a timeout result from a fake
  sender. Closest existing suites: `test_orchestration_147.py`, `test_worker_148.py`,
  `test_scheduler*.py`, `test_ingestion_rss.py`, `test_dedup_url_db.py`, `test_intra_source_123.py`,
  `test_clustering_{ingestion,persistence,backfill,fixtures,adversarial}.py`,
  `test_notification_identity_151.py`, `test_push_planner_152.py`, `test_telegram_dispatch_153.py`,
  `test_watermark_init_156.py`, `test_retention_149.py`, `test_feed_freshness_m8.py`,
  `test_run_metrics.py`, `test_source_health.py`, `test_article_id_golden.py`.
- Real-data behavior is checked on **copies** (`scripts/make_dev_snapshot.py`, `mode=ro` reads,
  `DATABASE_URL` pointed at a copy) — never by running ingestion, backfill, retention or dispatch
  against the live corpus, and never by sending a real notification.
- Don't report hypotheticals as findings. If you can't construct the failing scenario from the
  code, it's a question, not a finding — say so.

## Output

A short section for the PR self-review: the pipeline paths examined, findings in the format above
(or "no findings" plus what was checked), tests added or run, and residual risks that need Guy's
decision. Keep it to what the diff touches.
