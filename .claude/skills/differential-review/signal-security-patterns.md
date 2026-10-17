# Signal Sports security patterns

> This file is original Signal Sports content, not derived from the Trail of Bits material. It
> sits in this directory so the adapted `differential-review` skill can find it.

Read it before [patterns.md](patterns.md). Every item names the code that holds the invariant today,
so a diff can be checked against it rather than against a generic list. Verify each reference
against the current code: the codebase moves faster than this file.

## 1. Authorization: every route is classified, and the classification is the code

- **Invariant:** each registered route is declared in the POLICY inventory of
  `backend/tests/test_authz_inventory.py`, and the `require_admin` / `require_session` /
  `require_user` dependency actually attached must match it (the test introspects the route table).
- **Check in a diff:** a new or changed route; a moved dependency; a route-level dependency replaced
  by a check inside the handler (invisible to the inventory); a list or filter endpoint that takes a
  `user_id` or `profile_id` from the request instead of the session (`test_identity_isolation.py`
  covers cross-user reads); an admin action that skips `log_admin_mutation`.
- **Watch the guard itself:** the inventory walks `app.routes`. `requirements.txt` caps FastAPI
  `<0.137` because 0.141 stopped flattening routers and the inventory would pass while proving
  nothing. A FastAPI bump, or a change to how routers are included, is a HIGH-risk change to the
  authorization *test*.
- `ALLOW_INSECURE_AUTH_BYPASS` exists for local development only, and `DEPLOY_ENV=dev|hosted`
  refuses to start with it (`app/core/deploy_mode.py`). A diff that reads it somewhere new, or
  widens what it bypasses, is HIGH.

## 2. Sessions and credentials

- Session tokens are stored hashed (`auth_service.token_hash`). Raw tokens appear only in the
  cookie. Never log or persist them.
- Cookie flags (`routes_auth.py`): `httponly=True`, `samesite="lax"`, `secure` from
  `AUTH_COOKIE_SECURE` (which must be true on the host). Check any new `set_cookie`.
- Password change and account deletion revoke other sessions (`revoke_other_sessions`,
  `delete_account`); keep that true for any new credential-changing path.
- Login rate limits are in-process fixed windows (`FixedWindowLimiter`: per account + global). They
  reset on restart and don't span processes — acceptable for one node, and worth noting if a change
  assumes otherwise.
- Unknown-email logins call `verify_dummy_password` so timing doesn't reveal which emails exist;
  keep error messages uniform.
- Signup is controlled by `AUTH_SIGNUP_ENABLED` (true locally and in tests; the hosted example sets
  false).

## 3. CSRF and CORS

- `app/core/csrf.py`: mutating methods require `Sec-Fetch-Site` of `same-origin`/`none`, or
  `same-site` *with* an allowlisted `Origin`; any `Origin` present must be in
  `CSRF_ALLOWED_ORIGINS`.
- The `same-site` widening (audit F10) was kept deliberately because split deployment is the
  intended direction. Known gap **N07**: CORS `allow_origins` in `app/main.py` is a hardcoded list
  while CSRF reads `CSRF_ALLOWED_ORIGINS`, so the two can drift. A change to either list should keep
  them consistent.
- Red flags: a state-changing `GET`; a new origin added to one list only; `allow_credentials=True`
  combined with a wildcard or reflected origin.

## 4. Deployment boundaries

- `DEPLOY_ENV` ∈ {unset/local, dev, hosted}; anything else refuses startup. `dev` must never open
  the production corpus or deliver a real notification; `hosted` refuses the development flags
  (`ALLOW_DEV_RESET`, `ALLOW_CORPUS_DB_RESET`, `ALLOW_INSECURE_AUTH_BYPASS`, …).
  `assert_database_allowed()` also runs when the engine is created.
- Corpus protection (`app/db/corpus_protection.py`): destructive dev routes check the *target
  database*, not just a flag. A corpus reset needs `ALLOW_CORPUS_DB_RESET` on top of
  `ALLOW_DEV_RESET`, and benchmarks refuse the corpus outright.
- Check in a diff: a new startup path (script, worker mode, CLI) that opens the DB without going
  through `app.db`; a new escape-hatch flag missing from the refused list; a default that flips
  safe → unsafe; compose/env examples that ship real values.

## 5. Secrets

- Never committed (`SECURITY.md`); `.env.example` files carry names only. Report presence/absence,
  never values — `scripts/llm_bakeoff.py` shows the pattern.
- **The Telegram bot token is in the request URL** (`notifications/telegram.py`). The module raises
  the `httpx` logger to WARNING because httpx logs request URLs at INFO. Regressions to look for:
  removing or bypassing that, logging `str(exc)` or `exc.request.url` from an httpx error (httpx
  error messages can include the URL), or sending the URL to monitoring.
- Provider keys (`CLASSIFICATION_API_KEY`, `TRANSLATION_API_KEY`, the bake-off's `GROQ_API_KEY` /
  `GEMINI_API_KEY` / `OPENAI_API_KEY`) belong in env only; check for keys in error
  messages, `classification_trace`, cached bake-off responses under `backend/data/`, and debug
  endpoints.
- `scripts/make_dev_snapshot.py` must keep clearing sessions, credentials and personal fields; a
  schema change that adds a personal column needs a matching scrub plus its verification.

## 6. Untrusted input

Everything a source returns is untrusted: RSS XML, Sport5 HTML, ONE JSON, titles, subtitles, URLs
and dates.
- Adapters must never raise and must return `[]` on any fetch/parse failure, with timeouts
  (`_FETCH_TIMEOUT_SECONDS`). A crash or hang is a denial of service against the whole cycle.
- Text reaches the UI as text: React escapes by default, so look for new `dangerouslySetInnerHTML`
  (the only existing use is the shadcn chart style block in `components/ui/chart.jsx`),
  `href` values built from source data (block `javascript:`), and Telegram messages (sent as plain
  text — keep `parse_mode` unset unless input is escaped).
- **LLM prompt injection:** article titles and subtitles go into the classification prompt. The
  defense is architectural — strict enums, confidence floor, normalization against the taxonomy,
  and the deterministic merge guardrails (`docs/LLM_CLASSIFICATION.md`). Any change that lets
  free-text LLM output reach persistence, the UI or a decision without passing `validation.py` and
  `merge.py` is HIGH.
- **Outbound requests built from data (SSRF shape):** source URLs come from `ingestion/config.py`,
  not user input. A change that lets an API caller supply a URL or provider base URL for the server
  to fetch is HIGH.
- Request bodies: Pydantic models at the boundary; check new free-form `dict` fields, unbounded
  list sizes, and raw SQL built with string formatting (the codebase uses bound parameters —
  `text(...)` with `:params`).

## 7. CI and supply chain

- `checks.yml` runs with `permissions: contents: read`. `publish-images.yml` is
  `workflow_dispatch`-only, restricted to `main`, needs a typed confirmation, and holds
  `packages: write`. A diff that adds `pull_request_target`, widens permissions, exposes secrets to
  PR-controlled code, or makes publishing automatic is HIGH (also see `signal-pr-merge` §8:
  merge-triggered automation).
- Action version bumps change executable code. Check the upstream changelog for input, permission
  and runtime changes.
- Python installs use `--require-hashes` against `requirements.lock`; a change that drops hashes or
  installs outside the lock weakens supply-chain integrity.
