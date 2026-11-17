# Codebase Audit Report — 2026-11-17

Scope: `main` at `5c42759` (backend `app/`, `scripts/`, frontend `src/`, `deploy/`, CI,
repo hygiene). The audit was read-only: no application code was changed, and the test suites
were not run as part of it (CI runs them on this PR). Line numbers refer to `5c42759`.

**Overall.** The codebase is in good shape. There are no `TODO`/`FIXME` markers in
application code. A pattern scan for API keys, bot tokens and private keys found no secrets in
tracked files. Outbound HTTP calls have explicit timeouts. Destructive dev routes are
double-gated and refuse the real corpus. Hosted startup refuses dev-only flags. The findings
below are mostly about defense in depth, robustness at scale and documentation drift, not
active defects. There are no Critical findings.

| Impact | Count |
|---|---|
| High | 2 |
| Medium | 5 |
| Low | 9 |

---

## High

### H1. One global login limiter lets any client lock every user out of password login
- **Where:** [backend/app/services/auth_service.py:339](backend/app/services/auth_service.py#L339) (`_global_login_limiter.check("global")`), limits at lines 23–25 (100 attempts / 300 s).
- **Problem:** Every failed login from any client counts against one shared bucket. About 100
  bad requests in 5 minutes, for example a script posting random emails, block password login
  for **every** account, including the owner's admin account, until the window ends. The attacker
  can keep the lockout going indefinitely. Google sign-in still works, but email/password
  accounts don't.
  The signup-attempt limiter has the same shape:
  [backend/app/services/email_verification.py:232](backend/app/services/email_verification.py#L232).
- **Fix:** Keep the per-account limiter. Replace the single global bucket with a per-client-IP
  bucket (behind a proxy, read the client IP from a trusted `X-Forwarded-For` hop and run uvicorn
  with `--proxy-headers --forwarded-allow-ips=<proxy>`). Keep a much higher global ceiling as a
  circuit breaker only. Add a test showing that one client's failed attempts don't block another
  client's valid login.

### H2. `docs/CURRENT_PROJECT_STATE.md` — the cold-start doc — has a stale status table and architecture diagram
- **Where:** [docs/CURRENT_PROJECT_STATE.md](docs/CURRENT_PROJECT_STATE.md) §0 "Status at a glance" (dated 2026-10-12) and the §3 process diagram.
- **Problem:** This is the document every new agent session is told to read first.
  - §0 still says milestone 13 is the top priority and that the API and Vite are not running.
    It predates the live public demo (2026-11-11), the milestone 14 fixes, the milestone 15 UI
    and the results providers.
  - The §3 diagram still shows `Ollama :11434 (qwen2.5:3b-instruct)`, while §0 records Groq
    `gpt-oss-20b` since 2026-10-25.
  - The 2026-11-16 delivery banner at the top contradicts the table under it.

  Agents acting on §0 will start from wrong priorities.
- **Fix:** Run a truth sweep (skill `signal-doc-truth`). Re-date §0 with verified runtime facts,
  replace the LLM node in the diagram with "configured LLM provider (see §0)", and move the
  dated banners into §14 history.

## Medium

### M1. A silent fallback can quietly turn off a clustering false-merge guard
- **Where:** [backend/app/clustering/anchors.py:70-90](backend/app/clustering/anchors.py#L70-L90).
- **Problem:** `_known_competition_tokens()` imports the private
  `app.classification.facts._COMPETITION_KEYWORDS` inside `try/except Exception: pass`. If that
  symbol is ever renamed or its shape changes, `_COMPETITIONS` becomes an empty set with no log
  and no failing test. Competition words then act as person anchors again, which brings back
  the false merge the docstring describes (Bryant/Otooru).
- **Fix:** Import at module level and let an `ImportError` fail loudly. Better, expose a public
  `competition_keywords()` from `facts.py`. Add a test asserting that `_COMPETITIONS` is
  non-empty and contains a known token such as "יורוליג".

### M2. The live runtime skips every deploy-safety check
- **Where:** [backend/app/core/deploy_mode.py:256](backend/app/core/deploy_mode.py#L256) (`if mode == LOCAL: return []`), [backend/app/core/deploy_mode.py:145-148](backend/app/core/deploy_mode.py#L145-L148).
- **Problem:** The real user-facing instance is the owner's PC, reached from the phone through
  Tailscale. It runs as `DEPLOY_ENV=local`, so `ALLOW_DEV_RESET`, `ALLOW_CORPUS_DB_RESET`
  and `CLASSIFICATION_PROVIDER=fake` are never refused. `ALLOW_INSECURE_AUTH_BYPASS` is
  refused only together with a secure cookie. In `hosted` mode, an insecure cookie or open
  signup only produces a warning.
- **Fix:** In local mode, log a startup warning for each dev flag that is on when the corpus
  DB (`is_protected_corpus_db()`) is active. In hosted mode, make `AUTH_COOKIE_SECURE != true`
  an error, because hosted sessions are HTTPS by contract (DEPLOYMENT.md).

### M3. No index on `articles.published_at` or `articles.cluster_id`
- **Where:** [backend/app/db/orm_models.py:23](backend/app/db/orm_models.py#L23) and [:35](backend/app/db/orm_models.py#L35); queried in [backend/app/clustering/ingest_stage.py:121-136](backend/app/clustering/ingest_stage.py#L121-L136) and through `get_rss_articles(published_at_floor=…)` ([backend/app/repositories/article_repository.py:95](backend/app/repositories/article_repository.py#L95)).
- **Problem:** The freshness prefilter (#199), the clustering candidate window and the
  cluster-membership hydration all filter on these columns, so each one scans the whole table.
  That is fine at ~3–4k rows, but the corpus is never pruned (retention stays off by policy), so
  every feed request and every 5-minute cycle gets linearly slower.
- **Fix:** Add `CREATE INDEX IF NOT EXISTS ix_articles_published_at ON articles(published_at)`
  and `ix_articles_cluster_id` to the existing additive soft-migration path, and declare
  `index=True` on the ORM columns. Both are additive and safe on the corpus.

### M4. Rate limiters live in process memory
- **Where:** `FixedWindowLimiter` in [backend/app/services/auth_service.py:59-130](backend/app/services/auth_service.py#L59-L130), [backend/app/services/email_verification.py:61-66](backend/app/services/email_verification.py#L61-L66).
- **Problem:** Every API restart resets all login, signup and confirmation budgets, and so
  would a crash loop under Compose's `restart: unless-stopped`. If the API ever runs more than
  one uvicorn worker, each worker gets its own budget, which multiplies the limits.
  The Dockerfile pins one worker today ([backend/Dockerfile:55](backend/Dockerfile#L55)), but
  nothing enforces it.
- **Fix:** Document the single-worker invariant next to the limiters, and add a hosted startup
  error if `WEB_CONCURRENCY`/`--workers` > 1. If multiple workers ever become necessary, move the
  buckets into an SQLite table.

### M5. Plaintext `.env` backups and old runtime logs sit in the working tree
- **Where (untracked, ignored):** `backend/.env.backup-20260913-preCodex`, `backend/.env.bak-20261115T204639Z`, `backend/.env.bak.pre106`; root `worker_stdout.log` (3.5 MB, July), `worker_stderr.log`, `api_stdout.log`, `frontend_dev.log`, 18 `audit-*.log` files (2026-09-05).
- **Problem:** Git ignores these files (`.env.*`, `*.log`), so they can't be committed. But
  they are extra plaintext copies of credentials and old logs. The backups set non-empty
  `CLASSIFICATION_API_KEY`, `TRANSLATION_API_KEY`, `AUTH_ADMIN_PASSWORD`, `TELEGRAM_BOT_TOKEN`,
  `THESPORTSDB_API_KEY`, and in the newest one `GOOGLE_OAUTH_CLIENT_SECRET` and `GROQ_API_KEY`, and every new tool or agent session reads past them. Each backup also
  holds older keys that may still be valid.
- **Fix:** Rotate any key that appears in an old backup and is no longer the live one. Then
  delete the backups or move them outside the repo, and delete or archive the root logs. Nothing
  in the repo depends on them.

## Low

### L1. The RSS fetch timeout changes a process-wide default
- **Where:** [backend/app/ingestion/adapters/rss_adapter.py:37-45](backend/app/ingestion/adapters/rss_adapter.py#L37-L45).
- **Problem:** `socket.setdefaulttimeout()` affects every thread in the process. Manual runs
  call `orchestrate_cycle` inside the API's request threadpool
  ([backend/app/api/routes_ingest.py:118](backend/app/api/routes_ingest.py#L118), [:198](backend/app/api/routes_ingest.py#L198)), so concurrent requests briefly inherit a 10 s default socket timeout. This is harmless today because every httpx call passes an explicit timeout.
- **Fix:** Fetch the feed bytes with `httpx.get(url, timeout=…)` and pass the bytes to
  `feedparser.parse()`. This removes the global mutation and makes RSS handle HTTP errors the
  same way as the other adapters.

### L2. Frontend requests have no timeout
- **Where:** [frontend/src/api/client.js:17-38](frontend/src/api/client.js#L17-L38).
- **Problem:** `apiFetch` has no `AbortController`. If the backend accepts the connection and
  then hangs (for example a long SQLite write lock during a cycle, or a stalled tunnel), screens
  spin forever. `res.json()` would also throw on an empty 204 body. No route returns 204 today,
  but nothing prevents one.
- **Fix:** Wrap fetches with `AbortSignal.timeout(15000)`, combined with any caller signal, and
  return `null` for 204 and for `content-length: 0`.

### L3. `scripts/check.ps1` says it mirrors CI, but it skips two CI gates
- **Where:** [scripts/check.ps1](scripts/check.ps1) (header: "Runs the same checks as CI").
- **Problem:** It doesn't run the `requirements.lock` drift check, `npm run build:demo` or
  `npm run check:demo-bundle`. A change can pass locally and still fail the demo-bundle guard in CI.
- **Fix:** Add `npm run build:demo` and `npm run check:demo-bundle` to the frontend block, or
  correct the header.

### L4. A docstring points to the wrong env template
- **Where:** [backend/app/core/security_deps.py:25](backend/app/core/security_deps.py#L25).
- **Problem:** It says hosted sets `AUTH_SIGNUP_ENABLED=false` in "deploy/.env.example".
  The setting is in `deploy/signal.env.example:19`; `deploy/.env.example` holds Compose
  variables only.
- **Fix:** Change the docstring reference to `deploy/signal.env.example`.

### L5. The optional lexical validator turns itself off silently
- **Where:** [backend/app/clustering/anchor_validators.py:167-174](backend/app/clustering/anchor_validators.py#L167-L174).
- **Problem:** If `wordfreq` fails to import, the validator records `"unavailable"` and is
  skipped with no log line, which changes clustering behavior. `wordfreq` is pinned, so the risk
  is a broken environment rather than code.
- **Fix:** Log a single warning when the validator is unavailable.

### L6. Many stale git worktrees and branches remain locally
- **Where:** `git worktree list` shows 43 extra worktrees: 13 under `.claude/worktrees/` (three
  locked) and 30 sibling directories (`../signal-sports-46x`, `../sig-wt/*`,
  `../preview-overnight`, …). Many are on branches that are already merged.
- **Problem:** They use disk space, keep old branches alive, and confuse tools that scan the
  repo. A recursive grep over the main checkout also walks `.claude/worktrees/`.
- **Fix:** For each merged branch, run `git worktree remove <path>`, then `git worktree prune`
  and `git branch -d`. Keep any worktree a running preview depends on.

### L7. The frontend still carries a second, frozen relevance engine and mock data
- **Where:** [frontend/src/engine/relevanceEngine.js](frontend/src/engine/relevanceEngine.js) (684 lines), [frontend/src/data/mockArticles.js](frontend/src/data/mockArticles.js) (1,529 lines), loaded only through [frontend/src/context/localDemo.js](frontend/src/context/localDemo.js).
- **Problem:** Local mode scores in the browser with a legacy engine that no longer matches
  backend Preference V2. The README already calls it "not a parity implementation". It costs
  maintenance and drift tests, and it can mislead anyone who debugs relevance in local mode.
  The public demo has made it redundant as a preview.
- **Fix:** Decide whether local mode is still needed (owner decision, so file it as an issue).
  If not, delete `engine/`, `data/mockArticles.js` and `localDemo.js`, and make
  `VITE_DATA_MODE=backend` the default.

### L8. Very large modules concentrate risk
- **Where:** [backend/app/ingestion/classifier.py](backend/app/ingestion/classifier.py) (1,266 lines), [backend/app/classification/event_evidence.py](backend/app/classification/event_evidence.py) (1,030), [backend/app/ingestion/ingestion_service.py](backend/app/ingestion/ingestion_service.py) (795), [frontend/src/components/feed/signal/SignalFeedView.jsx](frontend/src/components/feed/signal/SignalFeedView.jsx) (932).
- **Problem:** Classification rules, guardrails and event logic are hard to review in diffs of
  this size. Most recent classification fixes (#403, #406, #407, #413) touched these files.
- **Fix:** No big-bang refactor. When one of these files is next changed, extract the touched
  rule family into its own module, with its tests moved alongside.

### L9. The FastAPI version cap is deliberate debt
- **Where:** [backend/requirements.txt](backend/requirements.txt) (`fastapi>=0.100.0,<0.137`).
- **Problem:** The authz inventory test walks `app.routes`, and that broke in FastAPI 0.141.
  The cap blocks security updates to FastAPI/Starlette.
- **Fix:** Rewrite `_registered_routes_checked` in `tests/test_authz_inventory.py` to collect
  routes through the routers it registers (or `app.router.routes`, recursively). Then lift the
  cap in a lock-refresh PR.

---

## Checked and found clean
- **Secrets:** a pattern scan of tracked files for Anthropic/OpenAI/Groq/Google/GitHub/Slack
  keys, Telegram bot tokens and private keys found nothing. Only `*.env.example` templates are
  tracked.
- **Auth:** ops routers are admin-gated in `main.py`. `/api/dev/*` is double-gated and refuses
  the corpus. Cookies are `httponly` and `samesite=lax`. CSRF checks `Origin` and
  `Sec-Fetch-Site` against the CORS allowlist.
- **Outbound HTTP:** every `httpx` call and every results provider client sets a timeout.
  Results providers catch transport, parse and rate-limit errors per competition.
- **Timestamps:** adapters normalize `published_at` to UTC before storage.
- **Public demo:** Firebase CSP and headers are strict. CI guards that the demo bundle stays
  read-only and scores-only.
- **Stale TODOs:** none in `backend/app`, `backend/scripts`, `frontend/src`, `deploy` or `scripts`.
