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
`ALLOW_INSECURE_AUTH_BYPASS` or `CLASSIFICATION_PROVIDER=fake`, refuses a named LLM provider whose
settings are incomplete (it would silently run rules-only; `CLASSIFICATION_PROVIDER=disabled` is
the intentional rules-only start), and warns when cookies are not
Secure, signup is open, `CSRF_ALLOWED_ORIGINS` is unset or retention is on
([USER_PLATFORM.md](USER_PLATFORM.md)).

`compose.yaml` restates `DATABASE_URL=sqlite:////app/data/signal_sports.db`, so an env file
can't move the corpus off the bind mount. Inside the image that path is also the one the
corpus guard protects (`app/db/corpus_protection.py`).

### 3.1 Verification email (password signups)

A password signup activates only through an emailed link
([USER_PLATFORM.md](USER_PLATFORM.md#email-verification-password-signups)), so a host that
lets anyone sign up (open signup, or `AUTH_SIGNUP_ALLOWED_EMAILS`) needs a mailer. Without
one, signup answers 503; it never skips verification. Nothing has been configured or bought.

- **Settings** (in `/etc/signal/prod.env`): `MAIL_BACKEND=smtp`, `SMTP_HOST`, `SMTP_PORT=587`,
  `SMTP_USERNAME`, `SMTP_PASSWORD` (secret), `MAIL_FROM`, `APP_PUBLIC_URL` (the https
  origin; the links are built from it, never from `Host`). `DEPLOY_ENV=hosted` refuses
  `MAIL_BACKEND=console|memory`, `SMTP_STARTTLS=false` and a non-https `APP_PUBLIC_URL`.
- **Port.** STARTTLS on 587. Hetzner Cloud blocks outbound 25 and 465 on new servers
  (taken from a forum quote of Hetzner's FAQ; confirm against Hetzner's own docs).
- **Provider and sender domain** (owner's choice). Any transactional SMTP provider works.
  With an own domain, add the provider's SPF and DKIM records and a DMARC record
  (`p=none` to start); Gmail requires SPF or DKIM from every sender. The zero-DNS fallback
  is Gmail SMTP with an app password, which ties delivery to a personal mailbox.
- **Local testing.** Unset `MAIL_BACKEND` means no mailer (signup answers 503).
  `MAIL_BACKEND=console` is the explicit development opt-in that writes the link to the API
  log. For a real inbox,
  run Mailpit (`docker run -p 1025:1025 -p 8025:8025 axllent/mailpit`) and set
  `MAIL_BACKEND=smtp SMTP_HOST=127.0.0.1 SMTP_PORT=1025 SMTP_STARTTLS=false
  MAIL_FROM=dev@localhost`; the messages appear at http://localhost:8025.
- **Delivery check before calling it done** (owner, real inboxes): sign up with a Gmail and
  a non-Gmail address; in "Show original" SPF, DKIM and DMARC pass and the message is not in
  spam; open the link on a phone and on a desktop; `curl` the link (a scanner's GET) and
  confirm the registration is still pending.

### 3.2 Google sign-in

Off until all three of `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` (secret) and
`GOOGLE_OAUTH_REDIRECT_URI` are set ([USER_PLATFORM.md](USER_PLATFORM.md#google-sign-in-gmail-and-workspace)).
Nothing has been created in Google Cloud.

- **Google Cloud project** (owner): an OAuth consent screen with only `openid`, `email` and
  `profile`, and a *Web application* client. Its **Authorized redirect URIs** are exactly
  `<origin>/api/auth/google/callback` for each origin the browser uses (local:
  `http://localhost:5173/...`; the tailnet: `https://<machine>.<tailnet>.ts.net/...`; the host
  later). No JavaScript origins are needed. The browser must use the same host name as the
  redirect URI (`localhost`, not `127.0.0.1`), because the state cookie is per host.
- **Testing vs production.** In *Testing* only the listed test users can sign in, which is
  enough for a first check. Friends beyond that list need the app *In production*; with only
  the basic scopes no Google verification is required. Session-age claims and app
  verification are not prerequisites.
- **Settings.** The secret goes in the untracked `backend/.env` locally and
  `/etc/signal/prod.env` on a host. `DEPLOY_ENV=hosted` refuses a non-https redirect URI
  and warns on a partial configuration or a redirect origin missing from
  `CSRF_ALLOWED_ORIGINS`. A host-name change means adding its redirect URI in the console
  and updating the env.
- **Before reverting Google sign-in**, see the rollback hazard in USER_PLATFORM.md:
  Google-only accounts have no password.

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
| `images.yml` | PRs and pushes touching `backend/`, `frontend/`, `deploy/` | builds both images and runs `deploy/smoke-test.sh`, then the rehearsals (§7, §10, §15). **Pushes nothing**; `contents: read` only |
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

## 10. Deploy and rollback

**Implemented and rehearsed in CI against a local registry** (`deploy/rehearse-deploy.sh` in
`images.yml`): validate, a first deploy on an empty host, a second release, rollback, and the
automatic rollback of a broken release, plus the SSH forced command's allowlist. **Never run on a
host or against GHCR.**

One workflow for A and B (HOSTING_PLAN §9.1): CI builds; the owner publishes a commit's images
(`publish-images.yml`, manual); the owner deploys **from the PC** with a separate SSH identity
whose only power is a forced command. No dev environment holds a production credential.

```bash
ssh deploy@<host> validate <40-hex sha>          # resolve digests + preflight; changes nothing
ssh deploy@<host> deploy   <40-hex sha>          # class 1 (default) or --class 2
ssh deploy@<host> rollback
ssh deploy@<host> status
```

`deploy/signal-deploy.sh` (run as root by the forced command `deploy/host/signal-deploy-ssh`,
through one sudoers line, `deploy/host/sudoers.signal-deploy`):

1. **Resolve** `<SIGNAL_IMAGE_REPO>/signal-{backend,web}:sha-<sha>` to immutable **digests**.
2. **Preflight**: Compose config with the new digests; free disk; data-dir ownership; env-file
   mode; and the **new image's own `DEPLOY_ENV` checks against the real settings**, so a refused
   configuration stops here, before anything changes. `validate` stops after this step; it only
   pulls images into the local cache.
3. **Backup**: a verified local copy (`backups/pre-deploy_<sha12>_<UTC>.db`), or the full
   off-host `backup.sh` for class 3. A first deploy on an empty host has nothing to back up.
4. **Pin** the digests in `deploy/.env` (the previous file is kept as `.env.previous`).
5. **Recreate** api + web, then the worker (it finishes its cycle: 300 s stop grace).
6. **Verify**: health through nginx; the worker's health; and, when the worker runs, **one
   completed cycle after the deploy** (`--no-wait-cycle` skips it).
7. **On failure**: classes 1 and 2 roll back automatically to the previous digests and say so.
   **Class 3** (data semantics, HOSTING_PLAN §12.5) is never rolled back automatically, because
   old code may misread new data: restore the pre-deploy backup or roll forward. Class 3 is not
   allowed through the forced command at all; it needs the admin identity, a written plan and
   `--class 3 --plan-acknowledged`.

Every release, failure and rollback is appended to `deploy/releases.log`. `rollback` returns to
the previous release's digests; a second `rollback` returns to the same release, not back and
forth.

### 10.1 Before reverting Google sign-in

Accounts created through Google have no password; reverting the Google code or unsetting
`GOOGLE_OAUTH_*` locks them out (USER_PLATFORM.md, "Rollback hazard"). Prefer a forward
fix. If the revert must happen, recover them first, on the host, against the production
database (the tool loads the same env as the API):

```bash
python scripts/set_user_password.py --list                    # who has no password
python scripts/set_user_password.py --user <usr_id>           # dry run: what would change
python scripts/set_user_password.py --user <usr_id> --apply   # temporary password, printed once
```

Give each person their temporary password over a private channel and ask them to change it
on the Account page. Only then deploy the revert. On the host the tool runs inside the api
container (`docker compose exec api python scripts/set_user_password.py ...`).

## 11. Host setup checklist (#268; owner-run, nothing done)

Templates are in `deploy/host/` and `deploy/systemd/`; none is installed anywhere. Personal values
(hostnames, tailnet names, IPs, keys) never go into the repository.

1. **Accounts and the VM** (owner): per the topology decision (HOSTING_PLAN §18). Unattended
   security updates on.
2. **Packages**: Docker Engine with the Compose plugin, `age`, `python3`, `curl`, `util-linux`
   (`flock`), `psmisc` (`fuser`). `deploy/host/docker-daemon.json` (log rotation, live-restore)
   and `deploy/host/journald-signal.conf` (a journal size cap).
3. **Layout**: `/opt/signal/deploy/` (this repo's `deploy/` directory), `/etc/signal/`
   (root 0700: `prod.env` from `deploy/signal.env.example`, `backup.env` from
   `deploy/backup.env.example`, the two **public** recipient files), and
   `/srv/signal/prod/data` owned by `10001:10001`, mode 0700. `deploy/.env` from
   `deploy/.env.example`.
4. **Identities**: `admin` (sudo, the owner's key plus an offline emergency key); `deploy`
   (`deploy/host/signal-deploy-ssh` as the forced command for a key that exists **only on the
   PC**, plus `deploy/host/sudoers.signal-deploy`; **not** in the `docker` group). Topology A only:
   a `dev` user with no sudo, no `docker` group, no access to `/srv/signal` or `/etc/signal`, and
   `deploy/host/user-1001.slice.limits.conf`.
5. **Private access**: Tailscale on the host (tagged node); `tailscale serve` HTTPS → 
   `127.0.0.1:8080`; **never Funnel**; a provider firewall with no inbound rules [A: Tailscale
   still connects]. `CSRF_ALLOWED_ORIGINS` = the exact `https://<machine>.<tailnet>.ts.net` origin.
6. **First deploy on an empty DB**: publish the images, then `signal-deploy.sh validate <sha>`
   and `deploy <sha>`. `COMPOSE_PROFILES` empty and `SCHEDULER_ENABLED=false`: **no worker**.
7. **Checks before data arrives**: `/health` and the login page through Serve from the phone;
   `scripts/source_probe.py` from the host (§9); the healthchecks
   checks created (owner) with their URLs in `prod.env` / `backup.env`; `backup.sh --validate`
   and `devsnap.sh --validate`; then enable `signal-backup.timer` and `signal-devsnap.timer`.

## 12. Cutover runbook (#269; owner-run)

**One corpus, one writer**: at no moment may the PC and the host both run a worker or accept
writes against their own copy.

1. **Freeze every local write on the PC.** `powershell -File scripts\worker.ps1 -Stop`; stop the
   local API (uvicorn) and Vite; run no `apply_*`, backfill or QA script that writes. Confirm
   nothing is left: `scripts\worker.ps1 -Status` says not running, and no process command line
   contains `app.worker` or `uvicorn`.
2. **Confirm the host's worker is disabled.** On the host, `COMPOSE_PROFILES` is empty,
   `SCHEDULER_ENABLED=false`, and `signal-deploy.sh status` shows no worker container.
3. **Final consistent backup on the PC**, with every writer stopped:
   `.venv\Scripts\python.exe scripts\backup_db.py data\cutover\final_<UTC>.db --expect-quiescent --manifest`.
   `--expect-quiescent` fails if anything still writes. Keep the PC's corpus and this file
   **read-only** as the archive; encrypt one copy to the backup key and upload it once as the
   pre-cutover archive (HOSTING_PLAN §12.2).
4. **Copy and verify.** Copy `final_<UTC>.db` and its `.manifest.json` to the host over the admin
   path (Tailscale). On the host: `deploy/restore.sh verify final_<UTC>.db final_<UTC>.db.manifest.json`
   must report integrity ok, no foreign-key violations, **the same sha256 and the same row
   count for every table**.
5. **Install and start in order**: `deploy/restore.sh apply final_<UTC>.db --confirm` moves the
   empty staging DB aside, installs the corpus, starts the **API and web first, with Telegram
   off**. Check `/health`, log in from the phone through Serve, open the feed and results.
6. **Start the worker last.** Set `SCHEDULER_ENABLED=true` in `prod.env` and
   `COMPOSE_PROFILES=worker` in `deploy/.env`, then `deploy/restore.sh resume`. The LLM provider
   must already be a hosted one or `disabled` (#262): the host cannot reach the PC's Ollama.
7. **Verify**: the first cycles complete (`signal-deploy.sh status`, `GET /api/scheduler/health`),
   new articles appear, results sync runs, the healthchecks `cycle`, `sources` and `fresh`
   checks go green, the phone reaches the feed. Telegram stays off until #251's preflight.
8. **The PC never runs a worker again.** Remove any local autostart.

**Rollback to the PC** (only if the host must be abandoned), preserving a single writer:

1. On the host: stop the worker **and** the API (`docker compose --profile worker stop worker api`),
   then set `COMPOSE_PROFILES=` and `SCHEDULER_ENABLED=false` so nothing restarts them.
2. Take the host's DB with `backup_db.py --expect-quiescent --manifest` (it is newer than the
   PC's frozen copy if any cycle ran on the host), copy it to the PC, verify it with
   `scripts\verify_db.py <file> --expect <manifest>`.
3. Move the PC's frozen corpus aside (never delete it), put the host's copy in its place.
4. Only then start the PC's API and worker. The host stays stopped.

## 13. Hard rules

1. One worker, one corpus. The PC never runs a worker after the cutover.
2. SQLite on a local filesystem only.
3. No secrets in images, git, issues, PRs or logs. The env file lives on the host only.
4. Only `web` is published, on loopback. No Funnel, no public port.
5. Images are built in CI, never on the host, and deployed by digest.
6. Dev environments hold no production credential (HOSTING_PLAN §9).

## 14. MVP: one reader on a phone (provider-agnostic, nothing done)

Goal: one invited reader (the owner's father) opens the feed on his phone every day. This is
the configuration and the order of steps for **either** path. Nothing here was run, bought
or changed. `[D]` marks a decision that belongs to the owner; `[O]` an owner-run action.

**Two paths, the same app.**

| | A. The owner's PC (interim) | B. A host (HOSTING_PLAN; provider not chosen) |
|---|---|---|
| Runs | uvicorn + Vite dev server + `python -m app.worker`, by hand | §1: Compose, `restart: unless-stopped`, Docker enabled at boot |
| After a reboot | **nothing restarts** (no autostart exists today) | Docker restarts api, web and worker |
| Phone access | Tailscale Serve → Vite `127.0.0.1:5173`. The PC must be on | Tailscale Serve → `127.0.0.1:8080` (§11 step 5) |
| Cost | none | the host `[D]` (HOSTING_PLAN §18) |

**Phone access, precisely.** Vite and uvicorn bind `127.0.0.1` on the PC, and nginx binds
`127.0.0.1:8080` on a host:
- `localhost` on the phone means the phone itself and never reaches either.
- The LAN cannot reach them either.
- The only supported path is Tailscale Serve (HTTPS `https://<machine>.<tailnet>.ts.net`), with the reader's phone in the tailnet. Never Funnel.

On the PC (2026-10-26) Tailscale is installed but logged out (`NoState`) and has no serve config.

**Configuration.** Start from `deploy/signal.env.example` (host) or `backend/.env` (PC) and set
exactly these:

| Key | MVP value | Why |
|---|---|---|
| `CSRF_ALLOWED_ORIGINS` | `https://<machine>.<tailnet>.ts.net` | the exact origin the phone uses |
| `APP_PUBLIC_URL` | the same origin | links in emails, if mail is ever enabled |
| `AUTH_SIGNUP_ENABLED` | `false` | accounts are created by the owner, see below |
| `MAIL_BACKEND` | `smtp` with empty settings | no mailer until #333. Signup stays closed; password reset is unavailable, and the owner resets with `set_user_password.py` |
| `CLASSIFICATION_PROVIDER` … | the `openai_compat` block from the PC (comments in the template) | the approved interim LLM; the key is `[O]` |
| `RESULTS_SYNC_ENABLED` | `true` (worker only) | as on the PC; `RESULTS_RECENT_DAYS` stays unset/0 (#351) |
| `TELEGRAM_NOTIFICATIONS_ENABLED` | `false` | push to the reader is a separate decision (#251) `[D]` |
| `FEED_FRESHNESS_ENABLED` / `FEED_MAX_AGE_HOURS` | `true` / `36` | as on the PC |
| `RETENTION_CLEANUP_ENABLED` | `false` | it would delete rated rows (#255) |
| PC only: `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` | `<machine>.<tailnet>.ts.net` | Vite refuses an unknown Host header without it |

**The reader's account.** `backend/scripts/create_user.py` (#361) creates one regular,
**unverified** account with a generated password, printed once.
- `--confirm-email` is **typo protection, not verification**. The operator types the same
  address twice, and `--apply` refuses a mismatch with nothing written.
- It is evidence only that the operator meant this address. It is not evidence that the reader
  owns it. The account therefore stays unverified (`email_verified_at` empty), exactly as the
  script prints. It becomes verified only by a real proof: a password-reset link, or Google
  sign-in with `email_verified=true`.
- Who may run it: whoever holds a shell on the machine and its DB, which means the owner. It is
  not an API route, it needs no role, and nothing runs it automatically.
- Normal signup and login rules are unchanged:
  - password login never checked verification;
  - signup still requires an emailed proof;
  - Google auto-link still requires Google's `email_verified=true` (#332).

**Checklist (in order).**

1. `[D]` Path A or B, and for B the host (HOSTING_PLAN §18, #267).
2. `[O]` B only: create the host and run §11, then §12 (cutover; the PC stops writing for good).
   A only: nothing to install.
3. `[O]` Tailscale:
   - log the machine in (`tailscale up`);
   - `tailscale serve --bg 5173` (A) or `--bg 8080` (B);
   - write down the ts.net origin.
   `[D]` how the reader joins: invite him to the tailnet, or share only this machine.
4. `[O]` Set the configuration above. On A, restart the API and Vite with the env, and
   **keep the worker as it is unless you decide otherwise**.
5. `[O]` Create the account (dry run first):
   `create_user.py --email <addr> --name "<name>"`, then
   `--apply --confirm-email <addr>`. Hand the password over privately.
6. `[O]` The reader logs in on the phone, completes `/welcome` → `/interests` → `/calibration`,
   and adds the site to the home screen (#354 adds the manifest).
7. Check from the phone:
   - login;
   - the feed shows the freshness line;
   - a source link opens;
   - 👎 saves.
   On A: reboot the PC once and confirm what has to be restarted by hand.
8. `[D]` Push notifications for the reader (#251), and SMTP for password reset (#333).

## 15. Postgres groundwork (not used)

**The app runs on SQLite only and cannot run on Postgres.** This section describes an unused
`db` service and a CI check, added 2026-10 as groundwork for a possible later split into
web / api / worker / db services. Nothing switched over, no driver was added, and nothing on the
PC or a host runs it.

**What exists.**
- `db` in `deploy/compose.yaml`: `postgres:18-alpine` pinned by digest, behind the **`postgres`
  profile**, so the default start (`up -d --wait api web`, and `COMPOSE_PROFILES=worker`) never
  creates it. **Hard rule: nothing connects to it.** No service depends on it, it publishes no
  port, and `x-backend` still forces `DATABASE_URL=sqlite:////app/data/signal_sports.db`. It has
  **no network** (`network_mode: none`, loopback only), so no container can reach it either;
  admin access is `docker compose exec`. A real switch would replace that with a dedicated
  internal network.
- **Start it only with `--profile postgres` on the command line. Never add `postgres` to
  `COMPOSE_PROFILES`** (in `deploy/.env` or the environment): the host scripts would then start
  it too. `restore.sh` resumes the stack with a bare `compose up -d --wait`
  (`deploy/restore.sh:194`), which would start db in the middle of a restore.
  Hardening as for the other services: uid `70:70` (the image's `postgres` user), read-only
  root with tmpfs for `/var/run/postgresql` and `/tmp`, `cap_drop: ALL`, `no-new-privileges`,
  `mem_limit: 256m`, rotated logs, `restart: unless-stopped`, 60 s stop grace. The healthcheck
  is `pg_isready` over loopback TCP, which the image's init-time (socket-only) server does
  not answer. `initdb` runs with `--encoding=UTF8 --locale=C`, because the app compares ISO
  timestamp strings as text.
- `deploy/postgres.env.example`: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` (secret,
  empty). The env file is optional (`required: false`); without a password the image refuses
  to initialize, so a missing file fails safe. Variables: `SIGNAL_POSTGRES_IMAGE`,
  `SIGNAL_POSTGRES_ENV_FILE` (default `./postgres.env`), `SIGNAL_POSTGRES_DATA_DIR` (default
  `./pgdata`). Both defaults are git-ignored.
- `backend/scripts/postgres_schema_ddl.py`: prints the ORM's `CREATE TABLE` / `CREATE INDEX`
  statements compiled for PostgreSQL. It needs no driver and opens no database.

**Starting it by hand** (only to look at it; nothing uses it). Compose interpolates the whole
file, so the backend and web image variables must be set (`deploy/.env`, §3) even though only
db starts. The app env file (`SIGNAL_ENV_FILE`) does **not** have to exist to start db alone,
but `docker compose config` refuses to run without it (the first is rehearsed in CI; the
second was observed in CI with Compose v2.38.2):

```bash
cd deploy
mkdir -p pgdata                 # a LOCAL filesystem, as for SQLite; never NFS/SMB
sudo chown 70:70 pgdata         # the image's postgres uid/gid
sudo chmod 0700 pgdata
install -m 0600 postgres.env.example postgres.env   # then set POSTGRES_PASSWORD (openssl rand -hex 24)
docker compose --profile postgres up -d --wait db
docker compose --profile postgres ps db                       # healthy
docker compose --profile postgres exec db psql -U signal -d signal -c 'SELECT version()'
docker compose --profile postgres stop db                     # stop; the data stays in pgdata/
```

The data dir is mounted at `/var/lib/postgresql`. Postgres 18+ images keep `PGDATA` one level
down, in `18/docker/`, which is why the mount is the parent. To throw it away: stop the
service, `docker compose --profile postgres rm -f db`, then `sudo rm -rf pgdata`. There is no
backup tooling for it (below).

**What CI proves, and what it doesn't.** `deploy/rehearse-postgres.sh` in `images.yml` runs two
separate throwaway Compose projects:
- `signal-pgrh-default`, the normal start path: `compose config` passes with no `postgres.env`;
  `up -d --wait api web` with no profile creates only api and web, and no db container exists
  for the project; `x-backend` still forces the SQLite `DATABASE_URL`; db declares no port and
  `network_mode: none`, and no service depends on it.
- `signal-pgrh-pg`, db alone: an empty data dir prepared as above, a random password and no
  app env file. The service initializes **from scratch** under uid 70 with a read-only root,
  and the database is UTF8 with C collation. Postgres accepts the ORM's DDL (`postgres_schema_ddl.py` from the
  backend image, in one transaction) and then holds exactly the ORM's tables. After
  `down`/`up` on the same dir it skips initialization and keeps them. db is the project's only
  container, publishes no port and is attached to no network.

So CI proves that **the service comes up hardened from scratch and that the models' DDL is
accepted by Postgres**. It does **not** prove that the app, its queries or its data are
compatible with Postgres: no app process ever connects to it, no query runs against it, and no
data is copied.

**Blockers before any real switch** (checked against the code on 2026-10-29; none is
addressed here):
- **Engine setup is SQLite-only.** `app/db/database.py:16-42`: `connect_args`
  (`check_same_thread`, `timeout`) are sqlite3 arguments, and the connect listener sets SQLite
  PRAGMAs (foreign keys, WAL, busy timeout). There is no Postgres driver in
  `requirements.lock`.
- **SQLite-only SQL.** The lease uses `INSERT OR IGNORE` (`app/ingestion/orchestration.py:110`);
  usage counting uses `sqlalchemy.dialects.sqlite.insert` (`app/repositories/usage_repository.py:8`).
- **Health probe.** `app/healthcheck.py` opens the DB with stdlib `sqlite3` and reports the
  worker unhealthy for any non-SQLite `DATABASE_URL`.
- **Safety guards can't see Postgres.** `app/db/corpus_protection.py` and
  `app/core/deploy_mode.py` recognise only SQLite paths, so with a Postgres URL the corpus
  guard on the destructive dev routes and the `DEPLOY_ENV=dev` production-database refusal are
  both blind. Their messages also print the URL in full
  (`active_database_url()` renders it with `hide_password=False`, and `routes_dev.py` puts it
  into a 409 detail and a log line). That is harmless for a SQLite path, but would leak a
  Postgres password once the guard recognises Postgres.
- **Backups, restore and verification are SQLite-only**: `app/ops/sqlite_tools.py`,
  `scripts/backup_db.py`, `scripts/verify_db.py` and the `deploy/*.sh` backup, restore, deploy
  and rehearsal scripts.
- **NULL ordering.** SQLite sorts NULL first ascending and last descending; Postgres the
  opposite. `ORDER BY finished_at DESC LIMIT 1` (`app/ingestion/orchestration.py:175`,
  `app/worker.py:123`) would return a NULL `finished_at` first.
- **Timestamps are ISO strings compared as text.** Correct only under a byte-wise collation
  (hence C); any other collation, or a mix of offsets and formats, changes comparisons.
- **Foreign keys.** SQLite enforces them only per connection (the PRAGMA); a copied corpus
  would need a clean `PRAGMA foreign_key_check` and a table order that Postgres accepts.
- **Soft migrations, no Alembic.** `_apply_migrations` adds columns with SQLite type names:
  `classification_confidence REAL` is single precision on Postgres, while the ORM's `Float`
  (and so a fresh `create_all`) is double precision. A switch needs real migrations (#198's
  migrations half).

## 16. Not done yet

Everything above is repository preparation. Still open: the owner's decisions and accounts
(HOSTING_PLAN §18), the first image publication, the host itself (#268), the hosted LLM
evaluation and switch (#262), the cutover (#269) and the 7-day observation (HOSTING_PLAN §15).
