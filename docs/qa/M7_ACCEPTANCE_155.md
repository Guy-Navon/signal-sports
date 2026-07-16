# M7-9 (#155) — End-to-End Acceptance & Soak Report

**Status: Phases A–B COMPLETE. Soak RUNNING. Phases C–D blocked on Guy's
one-time Telegram setup (the milestone's designed human pause point).**

All timestamps UTC, 2026-07-16.

## Phase A — Baseline and safety ✅

- Working tree clean at the M6 closure state; every M7 branch merged through PRs #158–#165.
- Full backend suite **2328 passed / 1 skipped**; frontend **421 passed**; build green.
- Verified pre-milestone backup `data/backups/pre_m7_baseline_20260716.db` (273=273)
  and pre-Phase-B backup `pre_m7_phaseB_20260716.db` (273=273).
- Clustering remains enabled; M6 outcomes intact (re-verified live below).
- Scheduler + Telegram + retention default **disabled** in dev and tests — conftest now
  pins all four behavior flags hermetically (a real finding: the developer `.env` was
  leaking `CLUSTERING_ENABLED=true` into test ingestion paths nondeterministically).
- `.env` git-ignored (verified via `git check-ignore`).

## Phase B — Scheduler operation on the real topology ✅

Documented two-process launch (docs/SCHEDULER.md): API `uvicorn app.main:app` +
worker `python -m app.worker`, controlled enablement scoped to the worker process
(the `.env` default stays false — activation authority preserved for M7-10).

**Two real defects caught by this phase — the reason acceptance runs on live operation:**

1. **SQLite posture** (PR #164): mid-cycle `database is locked` under the two-writer
   topology; fixed with WAL journal mode + 30s busy timeout; checkpointed backup script
   added (`scripts/backup_db.py`) because bare file copies can miss `-wal` writes.
2. **Missing soft migration** (PR #165): `ingestion_runs.cycle_id` existed in the ORM
   but not on the live table — fresh-schema tests structurally cannot catch a missing
   ALTER. Fixed + locked by `TestMigrationCoverage`, which migrates a legacy-shaped
   table and asserts every ORM column reaches disk.

Both failed cycles behaved exactly per contract while failing: per-article commits
survived, status `failed` with a sanitized error, lease released, worker continued.

**The clean catch-up cycle (`cycle_60351876…`, 296.4s, `succeeded`):**

| source | fetched | inserted | dup-skipped | filtered | failed |
|---|---|---|---|---|---|
| walla_sport | 30 | 0 | **30** | 0 | 0 |
| israel_hayom_sport | 100 | 14 | 0 | 86 | 0 |
| ynet_sport | 30 | 30 | 0 | 0 | 0 |
| sport5_sport | 11 | 10 | 0 | 1 | 0 |

- The 30 walla dup-skips are the articles the first (failed) cycle had inserted —
  **restart + retry produced zero duplicate articles** (the identity contract, proven live).
- Corpus 288 → 342 without any manual trigger; **clustering ran live: 9 → 11 clusters**,
  and the ranked Guy feed now shows a brand-new 2-source cluster card the scheduler
  formed autonomously (Trey King signing) — M6 dedup holding on automated ingestion.
- Notification stages correctly gated (`{"planning": telegram_disabled, "dispatch":
  telegram_disabled}`); cleanup correctly `{"skipped": "disabled"}` — recorded on the
  durable cycle row.
- **Cross-process single-flight proof:** a third process held the lease (fresh
  heartbeat) across the worker's 16:03:48 tick → the worker recorded
  `cycle_eef90253… skipped_active_run` and simply waited for the next interval.
  Coalescing, not queueing, across process boundaries.
- **Restart matrix:** API restarted (migration applied to the live table at startup;
  no scheduler starts in the API — locked by test); worker restarted twice → each time
  ONE `startup_catchup` (stale last-success), never tick replay.
- **Retention dry-run against the live corpus:** 0 candidates (corpus younger than the
  30-day window) — correct no-op, nothing written.
- Admin gate: anonymous `GET /api/scheduler/health` → 401.
- Cycle history explains every attempt: 2 failed (with causes), 1 succeeded, 1 skipped —
  all durable with process identity.

Current live feed state (service-level capture, post-ingestion):
52 cards / 5 pushes / 9 cluster cards — captured in
`docs/qa/feed_live_phaseB_ranked_guy_155_20260716.json` (the capture briefly
overwrote the frozen M6 artifact `feed_live_final_ranked_guy_126_20260715.json`
in the working tree; the M6 baseline was restored from git untouched). Pushes rose 3 → 5 purely from genuinely new
real articles — exactly the historical-PUSH backlog the M7-10 activation watermark
exists to suppress.

## Soak — RUNNING

Worker at `SCHEDULER_INTERVAL_SECONDS=300` continues from cycle `cycle_60351876…`.
The soak report will summarize attempts/successes/skips/durations/inserts/cluster
effects from `scheduler_cycles` at closure. Already banked during Phase B: one
process restart ×2, one manual-overlap coalesce, two honest failures.

## Pre-activation defects found & fixed (during Phase C)

Three defects were caught before Telegram activation and are frozen with tests.

**D-C1 — httpx would log the token-bearing URL (PR #166, merged).** httpx logs
every request URL at INFO and the bot token is IN the Bot API URL path; the
worker runs root logging at INFO, so the first real send would have printed the
token. Fixed by capping httpx/httpcore at WARNING at adapter import. Test-locked.

**D-C2 — status contract reported API config-intent, not worker reality (PR #167,
merged).** The ops header said "Scheduling: disabled" while the worker was alive
and ticking, because both status endpoints derived enabled/next-run/stale from
the API process's `SCHEDULER_ENABLED` env. Worse, stale detection was gated on
that flag, so a dead worker would have read healthy. Fixed with a durable
`worker_liveness()` heartbeat read and three separated signals
(`scheduler_enabled` intent · `worker_running` · `automatic_ingestion_active`).

**D-C3 — the test suite could send REAL Telegram messages (PR #167, merged) —
the headline pre-activation defect.** conftest pinned the ENABLE flag but not the
secrets; `app.main._load_dotenv()` loads the developer `.env` at import, so once
a real token existed locally it leaked into every test process. A planner test
that enables notifications then constructed a configured real `TelegramSender`
and **delivered two identical fixture messages to Guy's chat** (the failing test
ran once in the full suite + once isolated for diagnosis).

Containment evidence (all verified 2026-07-17):

1. **Tests cannot load Telegram creds from `backend/.env`.** conftest sets
   `TELEGRAM_BOT_TOKEN=""`/`TELEGRAM_CHAT_ID=""` BEFORE app import; `_load_dotenv`
   uses `override=False`, so the empty pins win over the real `.env`. Proven by
   `test_conftest_pins_telegram_secrets_empty` (runs inside the suite, which
   loads the real `.env` at import, and still sees empty + `configured()` False).
2. **Test config forces:** notifications disabled by default; empty token/chat id;
   delivery tests inject a `FakeSender`; and an autouse `_block_real_telegram`
   tripwire raises on ANY `api.telegram.org` call — no real network delivery.
3. **Zero real sends after PR #167:** full backend suite re-run **2335 passed /
   1 skipped WITH the network tripwire active** — any real Telegram attempt would
   have failed the run; none did.
4. **Isolated test DB:** conftest points `DATABASE_URL` at a temp `test.db` before
   any app import; the live corpus was never opened by tests — the live DB shows
   **0 rows with test ids** (`rss_t152%`) and **0** test-origin scheduler cycles.
5. **Live notification/outbox tables still empty:** `notification_events`,
   `notification_story_members`, `notification_watermarks` all **0**.
6. **Soak worker unchanged:** `pid=7800` (launcher parent `pid=31508`), start
   **2026-07-16 18:53:51**, uninterrupted — 79 succeeded cycles, no `abandoned`,
   no stuck `running` (the only 2 `failed` are the pre-fix Phase B cycles from
   earlier worker PIDs 6952/30432, already documented above).
7. **Token hygiene:** Guy revoked the original exposed token at BotFather; the
   fresh token validates via a read-only `getMe` (`@signalsportnotify_bot`). No
   Telegram-token pattern exists in the tracked tree, the full **276-commit**
   history, `docs/qa/` artifacts, logs, or the GitHub issue comments — the token
   value exists only in the git-ignored `backend/.env`.

## Phase C/D — BLOCKED on the human-only steps

Everything is prepared; Guy's actions (docs/NOTIFICATIONS.md §One-time setup):
1. @BotFather → `/newbot` → copy the token into `backend/.env` as `TELEGRAM_BOT_TOKEN`.
2. Send the new bot ONE message.
3. `backend> .venv\Scripts\python.exe scripts\resolve_telegram_chat_id.py` → put the
   printed id in `TELEGRAM_CHAT_ID`.
4. (For the HTTP acceptance journey, #157) `backend> .venv\Scripts\python.exe
   scripts\reset_admin_password.py --apply` — resets the admin password to the
   `.env` value; nothing secret is printed.
5. Leave `TELEGRAM_NOTIFICATIONS_ENABLED=false` — activation is M7-10's controlled step
   (guarded watermark initialization first, then enable, then the article-to-phone
   journey, then Guy confirms receipt).

## Phase E — Delivery failure semantics (evidence already banked)

Locked by `test_telegram_dispatch_153.py` via the scripted FakeSender: definite
rejection → bounded retry/final; ambiguous timeout → `unknown`, never auto-resent,
restart-safe, and lineage prevents replacement events; crash-after-claim stays
`claimed`, never auto-reset; Telegram disabled/unconfigured leaves ingestion healthy
(also proven live in every Phase B cycle). No real-chat spam will be performed.

## Phase F — Regression (to run at closure, after C/D)

Full suites; clustering real-data QA; Guy/Deni decision diffs (drift only from new
content); scheduler-disabled mode preserves manual behavior; Telegram-disabled mode
preserves scheduled ingestion (already continuously proven by the running soak).
