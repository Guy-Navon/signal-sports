# Signal Sports Backend

FastAPI, Pydantic v2 and SQLAlchemy on SQLite. The backend ingests sports news,
extracts article facts, scores relevance per reader, groups related stories and
serves personalized feeds and game results. It owns the product's relevance and
authorization decisions; the frontend renders the responses.

## Local setup

Use Python 3.13 (the version used in CI). Run from `backend/`; relative SQLite
paths resolve against this directory:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install --require-hashes -r requirements.lock
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env for your local configuration before starting.
.venv/Scripts/python -m uvicorn app.main:app --reload
```

On macOS/Linux use `.venv/bin/python`; copy `.env.example` to `.env` only if
the latter does not already exist. The API listens
on `http://127.0.0.1:8000`; `/docs` serves OpenAPI and `GET /health` is the public
liveness probe. Startup creates missing tables, applies additive migrations and
seeds empty tables. A fresh checkout contains seed data, not the owner's corpus.

The optional `.env` is loaded before application configuration; existing shell
environment variables take precedence. Keep `.env`, credentials, databases and
generated exports outside version control. Install from the hash-pinned
`requirements.lock`; `requirements.txt` declares ranges, and the lock header
describes how to update it.

For the full product, start the [frontend](../frontend/README.md) in `backend`
mode and browse `http://localhost:5173`. Its same-origin dev proxy forwards
`/api` and `/health` to this API.

## Accounts and configuration

Cookie sessions are HttpOnly. Mutating requests pass origin/fetch-metadata CSRF
checks; `CSRF_ALLOWED_ORIGINS` also supplies the credentialed CORS allowlist.
Consumer requests use the signed-in identity under `/api/me/*`; admin view-as
requests use separate routes.

- **First admin:** set both `AUTH_ADMIN_EMAIL` and `AUTH_ADMIN_PASSWORD` before
  startup. Bootstrap creates an admin only when none exists; these settings are
  not a password-reset mechanism. Seeded demo profiles have no login password.
- **Password signup and recovery:** configure a mail backend. For local work,
  `MAIL_BACKEND=console` explicitly prints email links in the API log; SMTP can
  use a local Mailpit inbox. Without a mailer, password signup returns 503 rather
  than bypassing verification. Set `APP_PUBLIC_URL` to the frontend origin for
  email links. `AUTH_SIGNUP_ENABLED` controls open signup;
  `AUTH_SIGNUP_ALLOWED_EMAILS` permits selected addresses when signup is closed.
- **Google sign-in:** requires all three backend settings:
  `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` and
  `GOOGLE_OAUTH_REDIRECT_URI`. Use the same browser hostname as the registered
  callback (locally, `http://localhost:5173/api/auth/google/callback`). Linking,
  unlinking and Google-only account deletion have separate account flows.
- **Deployment:** `DEPLOY_ENV=hosted` or `dev` enables environment-specific
  startup guards. Configure `AUTH_COOKIE_SECURE=true` and the real browser
  origin in `CSRF_ALLOWED_ORIGINS` for hosted use. The local
  `ALLOW_INSECURE_AUTH_BYPASS` escape hatch defaults off.

See [.env.example](.env.example), [User Platform](../docs/USER_PLATFORM.md) and
[Deployment](../docs/DEPLOYMENT.md) for the complete contracts and setup.

## API and worker processes

The API does **not** start an ingestion scheduler. Run a separate worker from
`backend/` for scheduled work:

```powershell
.venv/Scripts/python -m app.worker
```

The worker and API must use the same database and configuration. Manual and
scheduled ingestion share a durable single-flight lease. `SCHEDULER_ENABLED`
defaults to false; enable it deliberately to poll sources. Results sync,
retention and Telegram delivery have separate opt-ins. Translation and LLM
classification default to disabled; deterministic classification still runs.
Clustering defaults off in code; the example environment explicitly enables it.
Feed freshness defaults off (a 36-hour window when enabled).

On the owner's Windows checkout, run `powershell -File scripts\worker.ps1` from
the repository root to manage the detached worker and Ollama (`-Status`,
`-Stop`). This helper is separate from the portable worker command. Check its
status after a reboot. See [Scheduler](../docs/SCHEDULER.md) for settings,
ownership and recovery, and [Notifications](../docs/NOTIFICATIONS.md) for delivery.

## API surfaces

| Surface | Purpose / access |
| --- | --- |
| `/health` | Public liveness check |
| `/api/auth/*` | Session bootstrap, login/logout, verified signup, password recovery and Google sign-in |
| `/api/me/*` | Session user's profile, feed, results/details/player choices, interests, calibration, feedback, learning and account lifecycle |
| `/api/feed/{user_id}`, `/api/results/{user_id}` | Admin view-as reads, including stored game details under the results route |
| `/api/profiles/*`, `/api/debug/*` | Admin profile and diagnostic operations |
| `/api/ingest/*`, `/api/scheduler/*`, `/api/notifications/*` | Admin ingestion and operational observability |
| `/api/classify/*`, `/api/translations/*`, `/api/dev/*` | Admin maintenance; destructive operations have additional guards |

This is a summary; generated OpenAPI is the exact inventory. Authorization and
account-isolation tests guard the route contract.

## News pipeline

1. Configured RSS/API/HTML adapters ingest items and deduplicate URLs.
2. Deterministic classification extracts facts; a configured LLM may refine them
   under evidence and taxonomy guardrails.
3. Facts and provenance persist independently of user preferences.
4. Preference V2 scores articles for the requested profile. The legacy scorer
   remains a rollback path and powers the separate local frontend demo.
5. Optional freshness filtering limits consumer reads without deleting history.
6. Enabled clustering collapses related reports after per-article scoring.
7. Feedback derives bounded learned adjustments; explicit preferences retain priority.

Source activation combines configuration with persisted overrides. Use the
Sources console for current enablement instead of a static source list.

## Personalized results and game details

Results are stored independently of news classification. Reads use followed
teams, players/coaches and competitions; following a sport alone does not
populate a generic scoreboard. Selected result-player lines are a separate
display preference and do not change feed or game relevance.

- General past results and their details use a rolling **72-hour maximum**
  (`RESULTS_WINDOW_DAYS`, default 3 and capped at 3).
- Directly followed teams also get a separate history: up to four latest finals
  per team, eight unique games total, without an age limit. Eligible stored
  details remain accessible for those games.
- `RESULTS_DETAIL_ENABLED` defaults off. When enabled, the sync stage can store
  box scores, leaders, player lines, team statistics and ranks where supported.
  Scheduled games use a separate `RESULTS_UPCOMING_DAYS` window (default 7).
  Reads serve stored data and never trigger provider requests.

`RESULTS_ENABLED` defaults on; scheduled refresh requires
`RESULTS_SYNC_ENABLED=true`. The default provider is `thesportsdb`.
`RESULTS_PROVIDER_ROUTES` can select `winner` (Israeli basketball), `euroleague`
(EuroLeague/EuroCup), `espn_nba` (NBA) or `bamboo` (Israeli football) per
competition. `fake` supplies offline test data. Detail coverage depends on the
provider; enabling the UI does not manufacture missing statistics.

Provider health, disable switches, per-provider rate limits and optional backup
sync support fallback to the default provider. Reads select one serving provider
per competition to avoid duplicates. See [Results](../docs/RESULTS.md) for routing
examples, settings, detail access rules and provider limitations.

## Public demo exports

[scripts/export_demo_snapshot.py](scripts/export_demo_snapshot.py) opens SQLite
read-only and exports the `guy` profile's feed, results, followed-team history,
upcoming games and allowlisted stored details as `feed.json`, `results.json` and
`meta.json`. It performs no provider sync or database writes. These snapshots
power the separate public frontend demo; they are not the frontend's mock-data
mode. See the [frontend demo instructions](../frontend/README.md#public-read-only-demo)
and [Deployment](../docs/DEPLOYMENT.md) for export and publishing.

## Persistence and maintenance

The default corpus is `backend/data/signal_sports.db`, outside version control.
Startup migrations skip existing columns and stop startup on migration failure;
schema changes still use startup migrations rather than a versioned migration
framework.

**Do not delete the corpus to reset development data.** Use a disposable database.
Destructive benchmarks refuse the canonical corpus; resetting it requires an
additional corpus-specific opt-in, checked against the active engine.

SQLite uses WAL. Use the backup API rather than copying only the `.db` file:

```powershell
.venv/Scripts/python scripts/backup_db.py --manifest
```

The default destination is `data/backups/backup_<UTC timestamp>.db`. The script
verifies integrity, foreign keys and row counts; see its `--help` and
[Deployment](../docs/DEPLOYMENT.md) for restore and deployment procedures.

## Tests and checks

From `backend/`:

```powershell
.venv/Scripts/python -m pytest tests -q
```

`tests/conftest.py` selects a disposable SQLite database before application
imports, disables external stages and clears Telegram, SMTP and OAuth settings.
Provider tests inject fakes or saved fixtures. Do not point tests or benchmarks
at the live corpus.

[Repository checks](../.github/workflows/checks.yml) install the hash-pinned lock,
verify it matches the declared dependency ranges and run the backend suite on
Python 3.13. [Image checks](../.github/workflows/images.yml) separately build images
and rehearse smoke, backup/restore and deployment flows using throwaway stacks.
These checks do not establish live provider availability or deploy production.

## Further reading

- [Current project state](../docs/CURRENT_PROJECT_STATE.md): status and documentation map
- [Relevance contract](../docs/RELEVANCE_CONTRACT.md) and [Preference V2](../docs/PREFERENCE_MODEL_V2.md)
- [Sources and ingestion](../docs/RSS_INGESTION.md), [LLM classification](../docs/LLM_CLASSIFICATION.md)
- [Clustering](../docs/CLUSTERING.md), [freshness](../docs/FEED_FRESHNESS.md)
- [Frontend design system](../docs/FRONTEND_DESIGN_SYSTEM.md)
- [Feature delivery workflow](../AGENTS.md) and [results/demo delivery record](../docs/FEATURE_DELIVERY_2026-11-16.md)
