# Automated Ingestion Scheduler — Milestone 7 Contract

**Status:** authoritative living contract for scheduled ingestion (M7-1 #147, M7-2 #148).
**ACTIVE IN PRODUCTION since 2026-07-18 (M7-10 #156):** the production `backend/.env`
runs `SCHEDULER_ENABLED=true` at `SCHEDULER_INTERVAL_SECONDS=300`. The `.env.example`
default stays false so a fresh checkout never polls by accident. Activation evidence:
`docs/qa/M7_SOAK_REPORT_155.md` (44.8h soak) + `docs/qa/M7_ACCEPTANCE_155.md`.

## Topology

```
┌─────────────────────┐        ┌──────────────────────────┐
│  API process        │        │  Scheduler worker        │
│  uvicorn app.main   │        │  python -m app.worker    │
│  (serves requests,  │        │  (owns cadence: catch-up │
│   manual triggers)  │        │   + interval ticks)      │
└─────────┬───────────┘        └────────────┬─────────────┘
          │      one shared SQLite file      │
          └────────────┬─────────────────────┘
                       ▼
        orchestrate_cycle() — ONE implementation
        scheduler_lease  — durable single-flight guard
        scheduler_cycles — durable run history
```

- **The API process runs no scheduler.** The in-process lifespan loop (PR 13) was
  retired by #148: its lifetime was coupled to request-serving reloads, so
  `uvicorn --reload` and every extra worker would each have started their own
  polling loop. The loop-starter functions were deleted, not left default-off —
  a second polling loop is impossible by construction.
- **Every trigger uses the same orchestration** (`app/ingestion/orchestration.py`):
  `scheduled` (worker tick), `startup_catchup` (worker start), `manual`
  (`POST /api/ingest/run`), `run_now` (`POST /api/ingest/scheduler/run-now`).
  A scheduler tick is not a second implementation of ingestion.

## Production-like launch (local, two terminals)

```powershell
# Terminal 1 — API
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — scheduler worker (requires SCHEDULER_ENABLED=true in backend/.env)
cd backend
.venv\Scripts\python.exe -m app.worker
```

Both processes load `backend/.env`. The worker refuses to start (exit 1) when
`SCHEDULER_ENABLED` is not exactly `true` — tests and ordinary development can
never start a real polling loop accidentally.

## Configuration (single source of truth; defaults in `.env.example`)

| Variable | Default | Meaning |
|---|---|---|
| `SCHEDULER_ENABLED` | `false` | The worker loop runs only when exactly `true`. |
| `SCHEDULER_INTERVAL_SECONDS` | `300` | One shared polling cadence (~5 min). Per-source enablement stays in the existing source_overrides toggle. |
| `SCHEDULER_RUN_ON_STARTUP` | `false` | Force one cycle at worker start regardless of staleness. |
| `SCHEDULER_STARTUP_CATCHUP` | `true` | Run ONE catch-up cycle at start iff the last successful cycle is older than one interval. |
| `SCHEDULER_MAX_RUN_SECONDS` | `900` | A cycle exceeding this is flagged (health/M7-4); it is **not** killed — killing mid-transaction is worse than a slow run. |
| `SCHEDULER_STALE_AFTER_SECONDS` | `1800` | Lease-takeover threshold for dead-process recovery. |

## The single-flight guard — the honest contract

`scheduler_lease` is one durable row updated by a single conditional `UPDATE`.
SQLite serializes writers on the database file, so exactly one process can win
that update. The guarantee is precisely this:

> **At most one corpus-mutating ingestion cycle at a time, on this machine,
> across processes sharing this database file.**

It is **not** a distributed lock, provides nothing across machines, and is
never described otherwise. A process-local mutex was rejected because it does
not survive process boundaries (worker + API are separate processes).

- **Acquisition** succeeds when the lease is free **or** the holder's heartbeat
  is older than `SCHEDULER_STALE_AFTER_SECONDS` (dead-process takeover; the dead
  holder's cycle is marked `abandoned`). A live run's heartbeat is refreshed
  every ~10s by a daemon thread on its own session — a live run can never be
  stolen.
- **Release is owner-scoped**: only the cycle that holds the lease can free it,
  so a takeover cannot be clobbered by the dead holder's `finally` block.
- **Busy behavior**: endpoints return the structured 409
  (`ingestion_already_running`, with the durable holder identity — possibly a
  different process); a scheduled tick records a `skipped_active_run` cycle and
  simply waits for the next interval. Overlapping ticks are **coalesced, never
  queued**.

## Durable run history

Every trigger — including skipped ones — writes a `scheduler_cycles` row:
trigger, requested/started/finished timestamps, status (`running`, `succeeded`,
`succeeded_with_warnings`, `failed`, `skipped_active_run`, `abandoned`),
per-source result summaries, sanitized error, process identity and a config
snapshot. Per-source `ingestion_runs` rows (the pre-M7 run log) link to their
parent cycle via `cycle_id` — cycle = parent, source runs = children; there is
no third competing concept.

## Failure & recovery semantics

| Scenario | Behavior |
|---|---|
| Run longer than the interval | Next tick coalesces (`skipped_active_run`); no queueing. |
| Manual trigger during a scheduled run | 409 + a recorded skipped cycle. |
| Worker/API crash mid-run | `running` row remains; heartbeat goes stale; the next acquirer takes over and marks it `abandoned`. |
| Machine sleep / offline period | On worker start: ONE `startup_catchup` cycle iff the last success is stale. Missed ticks are never replayed — URL dedup makes the next fetch idempotent. |
| One source fails | Isolated (existing contract): the cycle continues, ends `succeeded_with_warnings`. |
| Total pipeline failure | Cycle `failed` with a sanitized error; the lease is released on every exit path. |
| Retry/restart | Article identity (`rss_`+sha1(url), per-article commit) makes re-ingestion idempotent — no duplicate articles, clusters, or (M7-5) notifications. |
| Classification/validator unavailable | Existing fail-closed behavior preserved (rules fallback / anchor abstention). |

## SQLite posture (WAL + busy timeout)

The M7 topology is two writer processes (API + worker) plus the lease-heartbeat
thread on one SQLite file. The Phase-B acceptance run caught a mid-cycle
`database is locked` failure under this contention with the sqlite3 default
5-second wait — the fix (#155) is the canonical single-node posture:

- `PRAGMA journal_mode=WAL` — readers and the writer no longer block each other;
- driver `timeout=30` + `PRAGMA busy_timeout=30000` — a writer waits for the
  lock instead of failing.

**Backup consequence (important):** with WAL, the newest writes may live in the
`-wal` sidecar file. A bare file copy of `signal_sports.db` can be behind.
Backups must either checkpoint first or use the sqlite3 backup API:

```powershell
cd backend
.venv\Scripts\python.exe scripts\backup_db.py    # checkpointed, verified copy
```

## Rollback

- **Disable the scheduler without breaking manual ingestion:** set
  `SCHEDULER_ENABLED=false` and stop the worker (Ctrl+C — it stops after the
  current step). Manual `POST /api/ingest/run` keeps working unchanged.
- **Stop the worker safely mid-run:** Ctrl+C; if a cycle was mid-flight its
  `running` row will be recovered as `abandoned` by the next acquirer; articles
  already inserted stay (per-article commit contract).

## Testing discipline

`SCHEDULER_ENABLED` defaults to false; `app.worker.main()` refuses to loop when
it is not exactly `true`; the API lifespan contains no scheduler references
(regression-locked in `tests/test_scheduler.py::TestInProcessSchedulerIsRetired`).
Worker behavior is tested through `worker_loop(max_ticks=…)` and pure decision
functions — no real sleeps, no real fetches.
