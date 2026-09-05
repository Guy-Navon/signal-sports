# Signal Sports Backend

FastAPI + Pydantic v2 + SQLAlchemy/SQLite. The backend ingests sports news,
classifies article facts, scores relevance per user, groups related stories,
and serves personalized feeds and game results.

## Setup

Run from `backend/` (relative SQLite paths resolve against this directory):

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --reload
```

On macOS/Linux use `.venv/bin/python`. Configuration examples are in
[.env.example](.env.example); `.env` is optional and must not be committed.
The API listens on `http://127.0.0.1:8000`; OpenAPI is at `/docs`.

## Tests

```powershell
.venv/Scripts/python -m pytest tests -q
```

`tests/conftest.py` selects a disposable SQLite database before application
imports, disables external processing stages, and clears Telegram credentials.
Provider tests inject fakes. Do not point tests or benchmarks at the live corpus.

## Runtime processes

The API process does **not** start an ingestion scheduler. For scheduled work,
run a separate worker with the appropriate opt-in settings:

```powershell
.venv/Scripts/python -m app.worker
```

The API and worker share a durable ingestion lease and the same SQLite file.
See [SCHEDULER.md](../docs/SCHEDULER.md) for flags, ownership and recovery.
Results synchronization, retention and Telegram delivery have separate flags.

## API surfaces

| Surface | Purpose / access |
| --- | --- |
| `/health` | Public health check |
| `/api/auth/*` | Signup, login, logout and session bootstrap |
| `/api/me/*` | Authenticated user's profile, feed, results, interests, calibration, feedback and account lifecycle |
| `/api/feed/{user_id}`, `/api/results/{user_id}` | Admin view-as access |
| `/api/profiles/*`, `/api/debug/*` | Admin profile and diagnostic operations |
| `/api/ingest/*`, `/api/scheduler/*`, `/api/notifications/*` | Admin ingestion and operational observability |
| `/api/classify/*`, `/api/translations/*`, `/api/dev/*` | Admin maintenance; destructive operations have additional guards |

The generated OpenAPI schema is the exact route inventory. Cookie sessions are
HttpOnly; mutating requests pass origin/fetch-metadata CSRF checks. The explicit
`ALLOW_INSECURE_AUTH_BYPASS` flag is a local development escape hatch, default off.
See [USER_PLATFORM.md](../docs/USER_PLATFORM.md) for the authorization contract.

## Implemented pipeline

1. Configured RSS/API/HTML adapters ingest source items and deduplicate URLs.
2. Deterministic classification runs; configured LLM providers may refine facts
   under evidence and taxonomy guardrails.
3. Article facts and provenance persist independently of user preferences.
4. Preference V2 (default) scores each article for the requested profile; the
   legacy scorer remains a rollback/demo path.
5. Freshness filters consumer feeds when enabled; debug retains historical items.
6. Enabled clustering groups stories after per-article scoring.
7. Feedback derives bounded learned adjustments; explicit preferences retain priority.

The results subsystem stores normalized provider games and filters them by
followed teams/competitions. It is separate from article classification.
Translation is implemented but disabled by default. Source activation is
configuration-driven with persisted overrides; inspect the Sources console
instead of relying on a static list in a README.

## Persistence and maintenance

The default corpus is `backend/data/signal_sports.db`, outside version control.
Startup creates missing tables and applies additive migrations. Existing columns
are skipped; migration failures stop startup instead of being silently ignored.

**Do not delete the corpus to reset development data.** Use a separate disposable
database. Destructive benchmarks refuse the canonical corpus; resetting it has
an additional explicit corpus-specific guard. The guard checks the active engine.

SQLite uses WAL. Use [scripts/backup_db.py](scripts/backup_db.py) and review its
arguments before backups; copying only the `.db` file can omit recent WAL writes.

## References and remaining work

- [Current project state](../docs/CURRENT_PROJECT_STATE.md)
- [September 2026 audit and next steps](../docs/audits/2026-09-05.md)
- [Relevance contract](../docs/RELEVANCE_CONTRACT.md)
- [Clustering](../docs/CLUSTERING.md), [freshness](../docs/FEED_FRESHNESS.md)
- [Results](../docs/RESULTS.md), [notifications](../docs/NOTIFICATIONS.md)

Backend dependency versions still use mostly lower bounds rather than a tested
lock file. Production restore drills, real-provider QA and broader browser
journeys remain separate from the offline unit/integration suite.
