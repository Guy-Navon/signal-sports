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

## 7. Monitoring

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

## 8. Source probe

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

## 9. Hard rules

1. One worker, one corpus. The PC never runs a worker after the cutover.
2. SQLite on a local filesystem only.
3. No secrets in images, git, issues, PRs or logs. The env file lives on the host only.
4. Only `web` is published, on loopback. No Funnel, no public port.
5. Images are built in CI, never on the host, and deployed by digest.
6. Dev environments hold no production credential (HOSTING_PLAN §9).

## 10. Not yet in this file

These land with their own PRs: deploy/rollback tooling, off-host backups and restore, the
cutover runbook (#266, #268, #269).
