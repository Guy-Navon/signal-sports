# M7-9 (#155) — Scheduler Soak Report

**Window:** 2026-07-16 15:42:28Z → 2026-07-18 12:28:56Z+ (**44.8 hours**, still
running at report time — target was ≥24h, preferred 48h).
**Configuration:** `SCHEDULER_INTERVAL_SECONDS=300`, WAL journal mode, 30s busy
timeout, clustering enabled, Telegram disabled throughout (activation authority
reserved for M7-10), retention cleanup disabled (verified separately by dry-run
in Phase B).

All numbers below are computed from the durable `scheduler_cycles` table —
nothing here relies on process memory or logs.

## Headline numbers

| metric | value |
|---|---|
| total cycle records | **524** |
| succeeded | **521** |
| failed | 2 (both pre-fix Phase B defects — see below) |
| skipped_active_run (coalesced overlap) | 1 |
| triggers | 521 scheduled · 3 startup_catchup |
| worker processes across the soak | 3 (pid 6952 → 30432 → **7800** for the final 522 cycles) |
| items fetched from sources | **89,080** |
| articles inserted | **240** (corpus 288 → **544**) |
| duplicate-skipped (identity contract holding) | **45,544** |
| source-level failures | **0** |
| cycles inserting new articles | 148 |
| clean no-new-item cycles | 373 |
| avg / max / min cycle duration | 8.2s / 296.4s / 1.2s |
| median inter-cycle gap | ~302s (cadence held) |
| gaps > 600s (restart/offline/stale periods) | **0** |
| story clusters | 9 → **15** (all formed autonomously) |
| notification planning/dispatch | `telegram_disabled` on **all 521** successes |

## The two failures (both explained, both fixed, both frozen by tests)

Both occurred in the first 8 minutes of live operation and are the reason this
acceptance runs on the real topology:

1. `cycle_aaf628c5…` (pid 6952) and `cycle_d108f8cf…` (pid 30432) failed with
   `ingestion_runs has no column named cycle_id` — the missing soft migration
   (fixed in PR #165, locked by `TestMigrationCoverage`). The earlier
   `database is locked` class was fixed by WAL + busy timeout (PR #164).
2. Both failed cycles behaved per contract while failing: per-article commits
   survived (the successor cycle dup-skipped exactly the survivors), status
   `failed` with a sanitized error, lease released, worker continued.

**Zero failures in the subsequent 521 cycles / 44+ hours.**

## Soak-plan checklist

- multiple successful no-new-item runs — **373** ✅
- multiple runs inserting articles — **148** ✅
- duplicate multi-source story — Trey King 2-source cluster formed
  autonomously in Phase B; clusters 9 → 15 over the soak ✅
- ≥1 process restart — worker restarted twice (three pids), one
  `startup_catchup` each, never tick replay ✅ (plus two API restarts with no
  scheduler duplication)
- ≥1 simulated source failure — Phase B (isolated; others succeeded) ✅
- ≥1 manual-overlap attempt — `cycle_eef90253… skipped_active_run`,
  cross-process coalescing proven ✅
- ≥1 Telegram PUSH — **deliberately impossible during the soak**
  (`telegram_disabled` on every cycle); the article-to-phone proof is Phase D,
  after watermark initialization ✅ by design

## Pre-activation defects found during the soak window (fixed before activation)

Recorded in detail in `M7_ACCEPTANCE_155.md` §Pre-activation defects:
**D-C1** httpx token-URL logging (PR #166) · **D-C2** scheduler status derived
from API env instead of worker heartbeat (PR #167) · **D-C3** test suite could
send real Telegram messages — two fixture messages reached the real chat before
the conftest secret-pinning + network tripwire landed (PR #167, #168; suite
re-verified 2335 passed with the tripwire active, zero sends).

## Activation-gate verdict (scheduler)

Every scheduler gate condition of the milestone contract is met with live
evidence: one worker; no reload duplication; overlap coalescing across
processes; shared guard for manual triggers; startup catch-up (never replay);
source-failure isolation; zero duplicate articles under restart/retry
(45,544 dup-skips, 0 duplicate inserts); clustering/personalization unchanged
except intended new content; retention verified by dry-run; durable cycle
history explains every attempt; stale detection re-keyed to the worker
heartbeat (PR #167) and verified live.

**The scheduler is approved for production-default enablement.
Telegram activation proceeds under M7-10's controlled sequence.**
