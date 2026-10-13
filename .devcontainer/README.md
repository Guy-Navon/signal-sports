# Remote development environment

**Status: prepared, never run.** This configuration has passed structural checks and a CI job
that runs its setup script on a plain Linux runner. **No codespace has been created from it**,
and its first real start is still to be validated (checklist at the end). Preparing it does not
choose topology B (HOSTING_PLAN §5); the same `scripts/dev.sh` also serves a dev user on a host.

## What you get

- The Codespaces **default image** (`universal:2`) plus two features pinning the toolchain to
  CI: **Python 3.13** and **Node 22**. Using the default image keeps it out of billed storage
  (HOSTING_PLAN §5.3) [A: confirm on the billing page]. A 2-core / 8 GB machine.
- `post-create.sh` installs the **hash-locked** backend set (`requirements.lock`) and
  `npm ci`, creates an **empty** dev database directory, and writes a dev-only `backend/.env`
  holding a random dev-admin password. It installs the Claude Code CLI too.
- **Nothing starts automatically.** No API, no worker, no Telegram, no LLM call, no download of
  production data.

## Safety, by construction

| Guard | Where |
|---|---|
| `DEPLOY_ENV=dev`: Telegram (flag or secrets) and any production DB path refuse startup; the Telegram sender is never configured; cookie name `signal_dev_session` | `containerEnv`, enforced by `backend/app/core/deploy_mode.py` (#265) |
| The DB is `backend/data/dev/signal_dev.db`, never the canonical `data/signal_sports.db` | `remoteEnv`, and the engine refuses the canonical file in dev |
| LLM `disabled`, scheduler off, results sync off, retention off | `containerEnv`; `scripts/dev.sh` forces the scheduler and Telegram off again |
| No production or deploy credential | nothing in this repo or setup holds one. Do not add any as Codespaces secrets: the only planned dev secrets are a capped LLM evaluation key and the dev-snapshot key (HOSTING_PLAN §9.3, §12.3) |
| Ports stay **private** | Codespaces forwards them privately, behind your GitHub login. Never run `gh codespace ports visibility …:public` |

The codespace's own `GITHUB_TOKEN` can push branches. Branch protection on `main` (PR plus
green CI) is what stops it from changing `main` [A: verify the protection settings].

## Commands

```bash
scripts/dev.sh api        # API on 127.0.0.1:8000 with --reload, empty dev DB, admin from backend/.env
scripts/dev.sh web        # Vite on 127.0.0.1:5173; open the forwarded 5173 port (it proxies /api)
scripts/dev.sh test       # backend suite (hermetic: temp DB, no network)
scripts/dev.sh test-web   # frontend lint, typecheck, tests, build
scripts/dev.sh check      # everything CI's checks.yml runs
scripts/dev.sh gate backend/data/snapshots/<file>.db   # N05 gate on a SANITIZED snapshot
scripts/dev.sh env        # show the effective dev settings
```

In a codespace, `dev.sh` allows exactly the forwarded hostname
(`$CODESPACE_NAME-5173.$GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN`) through
`__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` and adds its https origin to `CSRF_ALLOWED_ORIGINS`.
`vite.config.js` is unchanged and no wildcard host is committed (same approach as
`docs/MOBILE_REMOTE_ACCESS.md`).

**Real-data QA** runs only against a **sanitized dev snapshot** (HOSTING_PLAN §12.3, #270),
copied into `backend/data/snapshots/`. Results are "measured on a snapshot taken at <UTC>".
Writes (`apply_*`) never run in dev.

## What survives what

| Event | Kept | Lost |
|---|---|---|
| **Stop / start** (resume) | everything on disk: the repo, `.venv`, `node_modules`, the dev DB, `backend/.env`, your home directory, the Claude Code login and memory | running processes (API, Vite, tmux) |
| **Rebuild** | only `/workspaces`: the repo with its untracked files (`.venv`, `node_modules`, dev DB, `backend/.env`) and `/workspaces/.persist/` | everything else in the container, including globally installed tools. `post-create.sh` runs again and reinstalls them |
| **New codespace** (or deletion, or the inactivity retention: 30 days by default) | only what was **pushed** | everything else: uncommitted work, the dev DB, the Claude Code login and memory |

**Claude Code.** `CLAUDE_CONFIG_DIR=/workspaces/.persist/claude`, outside the repository, so its
login, settings and project memory live under `/workspaces` and survive a rebuild. They are
never committed. [A] Whether `~/.claude.json` also follows `CLAUDE_CONFIG_DIR` is unverified;
check after the first rebuild (HOSTING_PLAN §18).

**Moving memory into a new codespace** (one-off, from the PC; your memory stays private):

```bash
gh codespace list
gh codespace cp -c <codespace> -r -e \
  "$HOME/.claude/projects/<pc-project-dir>/memory" \
  "remote:/workspaces/.persist/claude/projects/-workspaces-signal-sports/memory"
```

The PC-side folder name depends on the PC path (today
`c--Users-HOME-Documents-signal-sports`); the codespace-side name follows the workspace path
[A: confirm the exact folder name after the first Claude Code start in the codespace].

**Habits that save money:** stop the codespace by hand when you finish (that saves the 30-minute
idle tail), push before you stop, and watch the running hours on GitHub's usage page
(HOSTING_PLAN §5.4).

## First-run checklist (owner, not yet done)

- [ ] Create the codespace from `main` on a 2-core machine; `post-create.sh` ends with "Ready".
- [ ] `scripts/dev.sh api` + `scripts/dev.sh web`; the forwarded 5173 URL shows the login page;
      log in with the dev admin from `backend/.env`.
- [ ] `scripts/dev.sh check` passes.
- [ ] Claude Code logs in; after a **rebuild** it is still logged in and its memory is there.
- [ ] Billing page: the codespace's storage does not include the image.
- [ ] Stop, then resume: files intact, processes gone, as described.
