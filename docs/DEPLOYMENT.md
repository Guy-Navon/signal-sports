# Deployment — the hosted stack

**Status: implemented and validated in CI only.** The images build and pass an isolated smoke
test in GitHub Actions. **Nothing has run on a real host yet**: no server exists, no image has
been published, and the live system still runs on the owner's PC. The decisions still open
(topology A or B, host, LLM, backup target) are in [HOSTING_PLAN.md](HOSTING_PLAN.md) §18; this
file describes only what exists in the repository and is the same for every one of them.

This is the living contract for running Signal outside the PC (milestone 13, #263). The plan
stays the reasoning; this file is the "how".

## 1. Architecture

```
phone / PC ──tailnet──▶ Tailscale Serve (HTTPS, ts.net) ──▶ 127.0.0.1:8080
                                                                  │
                                         ┌────────────────────────┴───────┐
                                         │ web   nginx, uid 101, :8080     │
                                         │   /            SPA (index.html) │
                                         │   /api/, /health ──▶ api:8000   │
                                         └────────────────────────────────┘
                     ┌─────────────────────────┐   ┌─────────────────────────┐
                     │ api  uvicorn, uid 10001  │   │ worker  app.worker,     │
                     │      no scheduler        │   │   uid 10001, profile    │
                     └────────────┬────────────┘   │   "worker", ONE only    │
                                  │                └────────────┬────────────┘
                                  └──── /app/data (bind mount) ─┘
                                        signal_sports.db (+ -wal, -shm)
```

- **One origin.** nginx serves the SPA and proxies `/api/` and `/health`, so the browser
  never makes a cross-origin call. No CORS change is needed (#196 stays irrelevant here).
  `Host`, `Origin` and `Sec-Fetch-*` reach the API unchanged; `CSRF_ALLOWED_ORIGINS` must be
  the exact https origin the browser uses.
- **One published port**, `web`, bound to `127.0.0.1` by default. `api` and `worker` publish
  nothing. Tailscale Serve fronts the loopback port. **Never use Tailscale Funnel.**
- **One database file, one worker.** `api` and `worker` share SQLite on a **local** bind
  mount; WAL must never sit on NFS/SMB or other network storage. The worker is never scaled.
  The durable lease serializes cycles, but only within one DB file (HOSTING_PLAN F9).

## 2. Images

| Image | Built from | Runs as | Contents |
|---|---|---|---|
| backend | `backend/Dockerfile`, context `backend/` | `10001:10001` | `python:3.13-slim-bookworm` (digest-pinned), `requirements.lock` installed with `--require-hashes`, `app/`, `scripts/`, `/app/PIP_FREEZE.txt` |
| web | `frontend/Dockerfile`, context `frontend/` | nginx-unprivileged (uid 101) | `npm ci` + `vite build` with `VITE_DATA_MODE=backend`, served by `nginx-unprivileged:1.28-alpine` (digest-pinned) |

- **What can't enter an image.** Both contexts use an **allowlist** `.dockerignore`: the
  backend context admits only `app/`, `scripts/` and `requirements.lock`; the frontend only
  its build inputs. `.env*`, `data/`, backups, logs, keys, venvs, `node_modules` and `dist`
  never reach the build. The smoke test checks the built images too.
- **One backend image, two commands**: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
  (one process, no `--reload`) and `python -m app.worker`.
- **amd64 only**, matching CI, Codespaces and the planned host (HOSTING_PLAN §8).
- **Health probes**: `python -m app.healthcheck api|worker` (stdlib only; the worker probe
  opens the DB read-only and never runs startup code). The worker is healthy while its
  `worker_status` row is `starting`/`idle` and younger than interval + max run + 120 s, or
  while a cycle's lease heartbeat is younger than 120 s. nginx answers `/healthz` itself.

## 3. Configuration

Two files, both untracked on the host:

| File | Template | Holds | Mode |
|---|---|---|---|
| `deploy/.env` | `deploy/.env.example` | Compose interpolation: image digests, `SIGNAL_ENV_FILE`, `SIGNAL_DATA_DIR`, bind address/port, `COMPOSE_PROFILES` | no secrets |
| e.g. `/etc/signal/prod.env` | `deploy/signal.env.example` | every app setting and secret | `root:root 0600` |

`deploy/signal.env.example` lists every key with **safe empty-DB defaults**: `DEPLOY_ENV=hosted`,
signup closed, Secure cookies, and **no worker, no LLM, no Telegram, no results sync**. Each
external side effect is switched on deliberately; the worker comes last.

`DEPLOY_ENV=hosted` (#265) refuses to start with `ALLOW_DEV_RESET`, `ALLOW_CORPUS_DB_RESET`,
`ALLOW_INSECURE_AUTH_BYPASS` or `CLASSIFICATION_PROVIDER=fake`, and warns when cookies are not
Secure, signup is open, `CSRF_ALLOWED_ORIGINS` is unset or retention is on
([USER_PLATFORM.md](USER_PLATFORM.md)).

`compose.yaml` restates `DATABASE_URL=sqlite:////app/data/signal_sports.db`, so an env file
can't move the corpus off the bind mount. Inside the image that path is also the one the
corpus guard protects (`app/db/corpus_protection.py`).

## 4. Data directory and permissions

| Path (host) | Owner | Mode | Notes |
|---|---|---|---|
| `SIGNAL_DATA_DIR` (e.g. `/srv/signal/prod/data`) | `10001:10001` | `0700` | the corpus and its `-wal`/`-shm`. Root-only is not enough: the non-root service must write its own DB |
| the app env file | `root:root` | `0600` | read by `docker compose` running as root |

- uid/gid `10001` is shared with no login user. A `dev` user (topology A) gets no access to
  the data dir, the env file or the `docker` group (which is root-equivalent).
- Containers run with a **read-only root filesystem** (`/tmp` is a tmpfs), `cap_drop: ALL`
  and `no-new-privileges`. The backend's only writable place is `/app/data`.
- Docker logs rotate: `json-file`, 10 MB × 5 per container.
- `mem_limit` (api 768 MB, worker 1 GB, web 128 MB) and `oom_score_adj: -500` on api and
  worker are estimates [E] from the PC's measured 147 MB worker; re-measure on the host (T3).

## 5. Lifecycle

| Service | Restart | Stop grace | On SIGTERM |
|---|---|---|---|
| web | `unless-stopped` | 10 s | nginx stops |
| api | `unless-stopped` | 30 s | uvicorn drains in-flight requests |
| worker | `unless-stopped` | **300 s** | finishes the **current cycle**, writes `worker_status=stopped`, exits 0 |

**Why 300 s.** Measured cycles on the PC: median 3 s, p95 37 s, max 71 s, with Ollama
(HOSTING_PLAN F4). 300 s is four times the observed maximum and leaves room for the bounded
network stages (LLM, Telegram and results-sync timeouts). An idle worker exits at once.

**If the worker is killed anyway** (a cycle still running at 300 s, an OOM kill, a host
crash): every committed transaction stays committed; the cycle row stays `running`; the lease
stays held until its heartbeat is `SCHEDULER_STALE_AFTER_SECONDS` (1800 s) old. The next
worker then takes the lease over and marks that cycle `abandoned`. Cost: up to ~30 minutes
of skipped cycles. A Telegram message killed between "claimed" and delivery is never resent,
by design (docs/NOTIFICATIONS.md). `init: true` runs tini as PID 1, so signals reach Python.

**The worker is opt-in twice**: the `worker` Compose profile (`COMPOSE_PROFILES=worker`) and
`SCHEDULER_ENABLED=true`. Without the profile it never starts; with the profile but without
the flag it refuses and exits 1 (and `restart` would loop), so set both together.

## 6. CI

| Workflow | Trigger | Does |
|---|---|---|
| `checks.yml` | every PR, push to main | backend suite (installed from the lock), frontend lint/typecheck/tests/build |
| `images.yml` | PRs and pushes touching `backend/`, `frontend/`, `deploy/` | builds both images and runs `deploy/smoke-test.sh`. **Pushes nothing**; `contents: read` only |
| `publish-images.yml` | **manual only** (`workflow_dispatch`, main, type `publish`) | build, smoke test, push to GHCR as `sha-<commit>`, print the digests. Never triggered by a merge |

`deploy/smoke-test.sh <backend-image> <web-image>` runs the stack under its own project name on
an **empty temp DB** on `127.0.0.1:18080` with every side effect off, and checks: non-root
users; no `.env`/DB/key/log/venv in the images; `/health`, the SPA and the `/login` fallback
through nginx; auth enforced and signup closed (403); a cross-origin login refused by CSRF
and a same-origin admin login accepted **through the proxy**; the DB owned by uid 10001; the
worker healthy, stopping on SIGTERM, exiting 0 and recording `stopped` **without running a
cycle** (no source is fetched); and `DEPLOY_ENV=hosted` refusing `ALLOW_DEV_RESET`.

**Publishing (owner decision before the first run).** A new GHCR package under a personal
account starts **private**. Either make it public (the images contain code only, no secrets)
or give the host a token limited to `read:packages`. Deploy by **digest**, never by a moving tag.

## 7. Backups, dev snapshots and restore

**Implemented and rehearsed end to end in CI on a throwaway stack** (`deploy/rehearse-backup-restore.sh`
in `images.yml`: real Docker, real `age`, a local "off-host" directory and a fake monitor).
**Never run against B2, a real host or the real corpus.** The B2 path is tested with mocked
HTTP only [A]. The backup target (B2 or R2) and who keeps the offline key are owner decisions
(HOSTING_PLAN §18).

### 7.1 What runs where

| Step | Tool | Runs as | Notes |
|---|---|---|---|
| 1. Copy | `scripts/backup_db.py` in the backend image (`compose run --no-deps api`) | uid 10001 | sqlite3 **backup API** (consistent while API and worker write), made one self-contained file (`journal_mode=DELETE`), then **verified**: `integrity_check`, `foreign_key_check`, per-table counts. `--manifest` writes sha256, size and counts. Lands in `$SIGNAL_DATA_DIR/backups/` |
| 2. Encrypt | `gzip -9 \| age -R <recipients>` on the host | root | **public** recipients only; the script refuses a file containing `AGE-SECRET-KEY`. The private key stays offline with the owner |
| 3. Upload | `deploy/offsite_upload.py` (stdlib, host `python3`) | root | only `*.age` files leave. `b2:<bucket>` or `local:<dir>` (a second disk, or rehearsals). SHA-1 sent and checked against B2's answer; at most 3 attempts on transient errors |
| 4. Report | `MONITOR_BACKUP_URL` | root | pinged **only after a successful upload**; any failure (a failed command or a refusal) pings `/fail` and exits non-zero |
| 5. Prune | `find -mtime +LOCAL_KEEP_DAYS` | root | **local** copies only (our file-name patterns). Remote cleanup is the bucket's lifecycle rules, so the host never holds a delete permission |

`deploy/backup.sh` runs steps 1–5 under one ops lock (backup, dev snapshot, restore and deploy
never overlap). `deploy/backup.sh --validate` checks the config, recipients, tools, Compose and
the uploader's config **without backing up or uploading anything**. Config: `/etc/signal/backup.env`
(root 0600; the scripts refuse another mode), template `deploy/backup.env.example`. Timers:
`deploy/systemd/signal-backup.{service,timer}` (nightly 01:30 UTC ± 15 min, `Persistent=true`,
idle I/O priority). Object names: `<prefix>/<daily|weekly|monthly>/signal_<UTC>.db.gz.age`, one
tier per night (the 1st of the month: monthly; Sunday: weekly; otherwise daily).

### 7.2 Backblaze B2 setup (owner; nothing was created)

1. A **private** bucket for backups, and a separate one for dev snapshots.
2. **Object Lock** with a default retention (governance or compliance, e.g. 14 days) on the
   backup bucket, set when the bucket is created [A: confirm the B2 options at creation].
3. **Lifecycle rules per prefix**, set once with the owner's own (admin) credentials:
   `prod/daily/` hide after 15 days, `prod/weekly/` after 57, `prod/monthly/` after 190; delete
   hidden versions after 1 day. That keeps 14 daily + 8 weekly + 6 monthly (HOSTING_PLAN §12.2).
   Locked versions are only deleted once their retention expires [A].
4. An **application key restricted to that one bucket**, with `writeFiles` and nothing that can
   destroy or rewrite history. `offsite_upload.py` reads the key's capabilities at authorization
   and **refuses** to upload with `deleteFiles`, `bypassGovernance`, `writeFileRetentions`,
   `writeFileLegalHolds`, `writeBuckets`, `deleteBuckets`, `writeBucketRetentions`, `writeKeys`,
   `deleteKeys`, `writeBucketEncryption` or `writeBucketReplications`, or when the key allows a
   different bucket or more than one.
5. **"Write-only" does not make deletion impossible.** `writeFiles` can still *hide* a file and
   upload a newer version under the same name [A: B2 docs]. What protects history is: unique
   names (a timestamp per object), Object Lock, and lifecycle rules owned by the owner, not by
   the host.

Credentials go only into `/etc/signal/backup.env` on the host (root 0600), never into chat,
issues, git or an image. R2 is not implemented: its tokens can't be write-only (HOSTING_PLAN §12.2);
choosing R2 would need an S3 uploader and a different deletion argument.

### 7.3 Dev snapshots (a separate path)

`deploy/devsnap.sh` (weekly timer `signal-devsnap`) runs `scripts/make_dev_snapshot.py` on a
copy and keeps every id and relation while removing what dev must not have:

| Table / column | In the snapshot |
|---|---|
| `auth_sessions`, `scheduler_lease`, `worker_status` | emptied |
| `users.email` | `user-<id>@example.invalid` (demo users keep `NULL`) |
| `users.password_hash`, `users.last_login_at` | `NULL` |
| `profiles.display_name` of real accounts | `user-<id>` (signup stored the email's local part there); demo profiles unchanged |
| `scheduler_cycles.process_identity` | `NULL` (it held the machine name) |
| everything else (articles, clusters, profiles, feedback, calibration, notifications, runs, results) | unchanged, ids included |

The file is rebuilt with `VACUUM INTO` (deleted values don't survive in free pages) and
**verified before it is kept**: integrity, foreign keys, unchanged counts outside the cleared
tables, no email outside `@example.invalid`, no hash, and **no original email or machine name
anywhere in the file's bytes**. A failure leaves no file. It is encrypted to the **dev** key
(`DEVSNAP_RECIPIENTS_FILE`; the script refuses a file that contains a backup recipient) and
uploaded with **its own** write-only credential to its own target. The plaintext snapshot is
not kept on the host. Dev never holds a key that decrypts a full backup; the CI rehearsal checks
both directions (the dev key can't open a backup, the backup key can't open a dev snapshot).

`restore.sh apply` refuses a file that looks sanitized (all emails rewritten, no hashes): a dev
snapshot must never become production.

### 7.4 Restore (HOSTING_PLAN §12.4)

Decrypt **on the PC** (the backup private key never goes to the host or to dev):
`age -d -i <offline key> signal_<UTC>.db.gz.age | gunzip > restored.db`, then copy
`restored.db` to the host over the admin path.

```bash
deploy/restore.sh verify   restored.db              # integrity, FKs, counts; read-only
deploy/restore.sh rehearse restored.db              # second API on 127.0.0.1:18081 over a scratch copy
deploy/restore.sh rehearse --stop
deploy/restore.sh apply    restored.db --confirm    # the real swap
deploy/restore.sh outbox                            # notification outbox by status
deploy/restore.sh resume                            # normal settings, timers back on
deploy/restore.sh undo     <data>/pre-restore-<UTC> --confirm
```

`apply`: verifies the candidate and refuses a dev snapshot → takes the ops lock → **stops every
writer** (worker, then API; pauses the backup and snapshot timers; refuses if any container still
mounts the data dir or `fuser` sees the files open) → moves `signal_sports.db`, `-wal` and `-shm`
**together** into `pre-restore-<UTC>/` (never deletes them) → installs the candidate (uid 10001,
0600) with no stale `-wal`/`-shm`, re-verifies it in place → starts the API, then the worker,
**with Telegram forced off**, because the restored outbox and watermarks date from the backup.
Watch one cycle, check `outbox`, then `resume`. Record the loss window (everything written after
the backup) and re-apply what can be re-applied. `undo` moves the failed set to
`failed-restore-<UTC>/` and puts the previous set back, again with Telegram off.

The CI rehearsal proves on a throwaway stack: validate uploads nothing; the backup is ciphertext
and the monitor is pinged once, after the upload; a post-backup change disappears after `apply`
and comes back after `undo`; the previous set is kept; a dev snapshot is refused as production;
the dev snapshot has no real email, hash or session.

## 8. Monitoring

**Implemented and tested with fake HTTP only; no monitor account or check exists yet.**
`app/monitoring.py` sends healthchecks.io-style pings (POST `<url>`, or `<url>/fail`) from the
worker after each **finished** cycle. Each signal is its own check, and an unset URL turns it
off; nothing is configured by default.

| Env (app settings file) | Pinged when | `/fail` when | Suggested period / grace | Catches |
|---|---|---|---|---|
| `MONITOR_CYCLE_URL` | a cycle completed (`succeeded` or `succeeded_with_warnings`) | the cycle ended `failed` | 5 min / 15 min | a dead worker, a down host, a stuck cycle (cycles are capped at 900 s, so silence covers "alive but stuck"), failing cycles |
| `MONITOR_SOURCES_URL` | at least one source returned items, **new or not** | no source returned anything | 5 min / 55 min | blocked or unreachable sources, DNS or egress failures. A quiet night still pings, because feeds always list their latest items |
| `MONITOR_FRESH_URL` | at least one **new** article was stored | never | 1 h / 7 h | ingestion that runs but stores nothing; the long grace absorbs natural quiet |
| `MONITOR_BACKUP_URL` | `deploy/backup.sh` **after the off-host upload succeeded** | any backup step failed | 24 h / 6 h | failing or missing backups |

- **A ping never fails or delays a cycle**: one POST with `MONITOR_TIMEOUT_SECONDS` (default 5,
  capped at 10); every error is swallowed and logged by check **name**.
- **The URLs are credentials** (anyone holding one can fake a success): they live in the host's
  env file, are never logged, and the ping body carries only counts and source ids.
- A coalesced tick (another run held the lease) sends nothing; the next tick reports.
- `DEPLOY_ENV=dev` never pings, and its startup check refuses any `MONITOR_*` URL.
- Not monitored by these pings: phone reachability over Tailscale (a manual daily check in T4).

## 9. Source probe

**Implemented and tested with fake adapters; never run from a host.**
`scripts/source_probe.py` answers "can **this** machine read the sources?" before the cutover
(HOSTING_PLAN §14: HTTP 200 alone doesn't count). Inside the image:

```bash
docker compose run --rm -T --no-deps api python scripts/source_probe.py          # the five Hebrew sources
docker compose run --rm -T --no-deps api python scripts/source_probe.py --json   # for the record
```

For each source it runs the **same adapter ingestion uses**, plus one plain GET per endpoint to
name a failure (DNS, connect, TLS, HTTP status), and judges the **content**: items parsed, most
dated, the newest younger than `--max-age-hours` (24), titles in Hebrew, links on the source's
own site. It captures the adapters' error lines instead of returning a bare "0 items". Verdicts:
`ok`, `degraded` (items, but a content check failed), `empty`, `error`; exit 0 only when every
probed source is `ok`. **It never opens the database** (a test proves the module does not even
import it), never changes source enablement and never calls an LLM. It reports the static
config's enablement only; the PC's DB overrides (Sport5 on, ONE off) are not read. Compare one
run with the PC worker's fetches for the same hour.

## 10. Hard rules

1. One worker, one corpus. The PC never runs a worker after the cutover.
2. SQLite on a local filesystem only.
3. No secrets in images, git, issues, PRs or logs. The env file lives on the host only.
4. Only `web` is published, on loopback. No Funnel, no public port.
5. Images are built in CI, never on the host, and deployed by digest.
6. Dev environments hold no production credential (HOSTING_PLAN §9).

## 11. Not yet in this file

These land with their own PRs: deploy/rollback tooling and the cutover runbook (#268, #269).
