# User Platform — Architecture Contract

**Status: MILESTONE COMPLETE (2026-07-10).** All seven PRs are merged to main:
Auth Core (#49, PR #56), the session-derived `/api/me/*` consumer surface
(#50, PR #71), the frontend auth shell (#51, PR #72), fail-closed admin
gating with the AppContext consumer/QA split and ops view-as (#53, PR #73),
the onboarding flow (#52, PR #74 — Product Review approved), enforcement
verification with fresh per-test explicit identities and the route-derived
authorization inventory (#54, PR #75 — two independent-review rounds'
findings corrected in full), and account lifecycle + hardening (#55, PR #76).
The milestone acceptance journey (signup → session → onboarding → calibration
→ personalized feed → feedback → logout → login → identical persisted state,
plus password change, account deletion, admin view-as, and horizontal-
isolation denials) is verified end-to-end. Recorded follow-up: the owner's
physical phone/Tailscale pass (checklist in `docs/MOBILE_REMOTE_ACCESS.md`).

**Execution home:**
[GitHub Milestone 2 "User Platform"](https://github.com/Guy-Navon/signal-sports/milestone/2)
· Epic [#48](https://github.com/Guy-Navon/signal-sports/issues/48) · issues #49–#55
(one PR per issue). **Epic #48 holds the canonical dependency graph and issue states —
this document deliberately does not duplicate it.** The former cross-track gate on #52
(Classification & Feed Reliability sign-off,
[#63](https://github.com/Guy-Navon/signal-sports/issues/63)) **cleared 2026-07-10** —
#52 depends on #51 only.
Review gates are model-independent contracts defined in the issue bodies: **#52**
(Product Review — Onboarding), **#54** (Security/Authorization Review + Regression
Gate); #49's architecture review completed 2026-07-08. An implementation agent picking
up this milestone cold should read this document fully, then take the lowest unblocked
issue per Epic #48 — each issue body is a self-contained contract.

## What this milestone is

Signal Sports today is a sophisticated personalized system with two seeded demo profiles
(`guy`, `casual_deni_fan`) addressed by a free-string `user_id` in URL paths and request
bodies, with zero authentication. This milestone turns it into a real multi-user product:
identity, accounts, sessions, first-run onboarding, and strict user-data isolation.

The auth layer **wraps around** the intelligence stack. Nothing in
FACTS → VISIBILITY → PREFERENCE → LEARNING changes:

- articles, ArticleFacts, classification, and taxonomy stay **global article truth**, never
  user-owned;
- ProfileV2 stays the personalization state;
- explicit > learned > calibration precedence is unchanged;
- learning stays derived from feedback events, never silently mutating explicit preferences;
- push discipline (explicit `always_push` overrides only) is unchanged;
- LLM optionality is unchanged;
- the JS relevance engine stays frozen (local demo only);
- the real article corpus remains a protected QA asset.

The per-user vs global boundary is already drawn correctly in the data model
(`profiles.profile_v2`, `feedback_events`, `calibration_responses` are `user_id`-keyed;
everything upstream of the persisted article is global). What this milestone adds is
**identity** (who is this `user_id`), **account lifecycle**, and **enforcement** (nothing
today stops one caller reading another user's data by editing a path parameter).

## Executive decisions

- **Identity model**: a new `users` table **separate from `profiles`**, with `users.id` an
  opaque string (`usr_<ulid>`) that **equals `profiles.user_id`** (1 account = 1 profile).
  Demo profiles get credential-less `users` rows with their existing ids (`guy`,
  `casual_deni_fan`, `role='demo'`) — zero data migration; all existing feedback,
  calibration, and profile rows stay valid as-is.
- **Auth**: **application-owned email + password** (argon2id via `argon2-cffi`),
  **server-side opaque session tokens** (SHA-256-hashed at rest in a new `auth_sessions`
  table), delivered as an **HttpOnly SameSite=Lax cookie**. No JWT, no OAuth, no magic links
  (rejections below).
- **Authorization**: a `get_current_user` FastAPI dependency; new **`/api/me/*` consumer
  routes** derive identity from the session; existing `{user_id}` routes become the
  **permanent admin/QA surface** (`role='admin'`); ops routes (`/api/ingest`, `/classify`,
  `/translations`, `/dev`) become admin-gated. Enforcement is **fail-closed by default**;
  the only escape hatch is the explicitly dangerous **`ALLOW_INSECURE_AUTH_BYPASS`** flag
  (default false, legacy/ops surface only, refused at startup in deployed configurations).
- **Onboarding**: signup → welcome → **existing Calibration V2** (skippable, resumable via
  existing `calibration_responses`) → personalized feed. Profile row (empty-but-valid
  ProfileV2) created at signup. Onboarding state = one nullable timestamp + derivation.
  **Explicit product decision**: skipping calibration yields an intentionally empty feed
  with a strong persistent calibrate CTA — no generic fallback feed.
- **Frontend**: new `AuthContext` bootstrapped from `GET /api/auth/session`; login/signup/
  onboarding as product-side routes outside AppShell; the ProfileSwitcher leaves the
  consumer Masthead and becomes an admin "QA view-as" picker in the ops console;
  `VITE_DATA_MODE=local` stays fully authless.

## Constraints that shaped the design

- **SQLite + soft migrations only** (`_apply_migrations()` = idempotent
  `ALTER TABLE ADD COLUMN`; no Alembic). SQLite cannot ALTER-add FKs/UNIQUE to existing
  tables → new tables get real constraints via `create_all`; ownership on existing tables
  stays app-enforced. This milestone needs **zero soft-migration entries** — only new
  tables.
- **Same-origin everywhere**: Vite proxies `/api` → uvicorn in dev AND via Tailscale Serve
  for phone access → cookie auth works with no CORS-credentials work. Consequence:
  cross-origin `VITE_API_BASE_URL` mode becomes unsupported once auth is enforced
  (accepted; the relative-`/api` contract is the product contract).
- **The Secure cookie flag cannot be auto-detected** (Tailscale Serve terminates HTTPS
  before Vite/uvicorn; the scheme at FastAPI is always `http`) → explicit
  `AUTH_COOKIE_SECURE` env.
- **The real corpus DB is sacred**; every startup step in this milestone is
  create-only/idempotent.

## Identity and account model

A **User** is an account identity: stable opaque id, credentials, role, lifecycle
timestamps. A **Profile** remains pure personalization state (ProfileV2 + legacy topics).
They are separate tables; identity concerns never enter `profiles`.

- **1 account : 1 profile**, joined by id-equality (`profiles.user_id == users.id`).
  Accepted constraint: a future multi-profile account would need a real `profile_id`
  separation (table rebuild) — deliberately out of scope.
- **Account identity data**: email, password hash, role, created_at,
  onboarding_completed_at, last_login_at. **Personalization data**: everything already in
  `profiles` / `feedback_events` / `calibration_responses`.
- **Demo profiles remain normal database rows**, now with matching `users` rows:
  `role='demo'`, `email=NULL`, `password_hash=NULL` ⇒ can never log in, can never be
  deleted. They stay the permanent QA fixtures; the seed + drift guards
  (`seed_profiles.py`, `userProfiles.js`, `docs/fixtures/profile_parity.json`) are
  untouched.
- Lifecycle: signup creates `users` + `profiles` rows in one transaction (profile gets
  `topics=[]`, empty mute lists, `profile_type="self_serve"`, and an **empty-but-valid
  ProfileV2 payload constructed through the pydantic model** — same discipline as the seed
  backfill). Deletion is a hard delete (below).

## Auth and session model

- **Email + password**: argon2id (library defaults), emails normalized (lowercase/trim),
  uniqueness enforced by a real UNIQUE constraint (new table, so real constraints are
  available).
- **Sessions**: `secrets.token_urlsafe(32)` opaque token; only its SHA-256 is stored
  (`auth_sessions.token_hash` PK). Cookie: HttpOnly, SameSite=Lax, Path=/, `Secure` per
  `AUTH_COOKIE_SECURE`.
- **Expiry contract (single, precise): fixed 30-day absolute expiry — activity never
  extends `expires_at`.** `last_seen_at` is updated for observability only (throttled to at
  most ~once/hour). Expired session ⇒ 401 ⇒ re-login. Logout deletes the session row (true
  server-side revocation). A fresh token is minted on every login.
- **Admin bootstrap**: a startup ensure-step reads `AUTH_ADMIN_EMAIL` /
  `AUTH_ADMIN_PASSWORD` from `.env`; creates the admin (plus an empty profile row, stamped
  onboarded) only if no admin exists; never resets an existing password. Idempotent,
  corpus-safe.

**Rejected alternatives**:

- *External IdP (Auth0/Clerk/etc.)* — external dependency + cost for a solo, cost-sensitive
  project; awkward on a private tailnet; overkill for the threat model.
- *OAuth/social login* — requires registered public redirect URIs, hostile to
  localhost/tailnet deployment; adds provider coupling before there are users.
- *Passwordless email-link* — no email-sending infrastructure exists; email delivery would
  become the hardest and most expensive part of the milestone.
- *JWT / token-in-JS* — same-origin cookies are strictly simpler and safer here: no
  XSS-readable storage, trivial revocation via row delete, and **zero signing secrets** in
  the architecture.

## Authorization boundary

`app/core/security_deps.py`: `get_current_user` (cookie → session row → user),
`require_user`, `require_admin`. **Enforcement is the default and fails closed**:

- `/api/auth/*` and `/api/me/*`: **always** enforce real sessions, in every configuration,
  from day one. No flag ever opens them.
- Legacy `{user_id}` + ops routes: `require_admin` by default from the moment gating
  exists. The only escape hatch is **`ALLOW_INSECURE_AUTH_BYPASS=true`** (deliberately
  alarming name, same convention as `ALLOW_DEV_RESET`; default false; read at request time
  for testability; affects only the legacy/ops surface).
- **Startup guard**: the app **refuses to start** when `ALLOW_INSECURE_AUTH_BYPASS=true`
  and `AUTH_COOKIE_SECURE=true` (Secure cookies are the "deployed behind HTTPS" signal —
  the bypass is a localhost/tailnet-dev affordance only). When the bypass is active on
  plain HTTP, a loud warning banner is logged at startup. An ordinary config mistake (unset
  flag) therefore yields *more* security, never less.
- `/me` routes never accept a user id from the caller (`POST /api/me/feedback` rejects a
  body `user_id`); identity comes only from the session. Horizontal access by editing a
  path parameter becomes structurally impossible on the consumer surface.
- Explicit target `user_id` stays legitimate **only** on the admin/QA/debug surface —
  that is where "inspect Guy's feed" lives.
- **CSRF middleware** on mutating methods: reject when `Sec-Fetch-Site` is present and not
  `same-origin`/`none`; when `Origin` is present it must match the allowlist. Combined with
  SameSite=Lax and the audited absence of state-changing GETs (keep it that way), this is
  proportionate for a same-origin-only product. (TestClient sends neither header → tests
  unaffected.)

## Onboarding state machine

Storage: **`users.onboarding_completed_at` (nullable) + existing `calibration_responses`;
all states derived** — no state enum to drift.

| State | Derived from | User sees | Exit |
|---|---|---|---|
| UNAUTHENTICATED | no valid session | login/signup (product-styled, outside AppShell); product routes redirect here | signup/login → session |
| NEEDS_ONBOARDING | session + timestamp NULL + 0 calibration responses | welcome screen → CTA into Calibration V2; skip available | rate an item → CALIBRATING; skip → ACTIVE |
| CALIBRATING | session + timestamp NULL + ≥1 response | Calibration V2 resumed at first unanswered item (per-item upsert = free persistence) | `POST /api/me/calibration/apply` applies inference **and stamps the timestamp** → ACTIVE; or skip via `POST /api/me/onboarding/complete` |
| ACTIVE | timestamp set | normal feed; if skipped/empty ProfileV2 → empty-feed state + persistent "calibrate your feed" banner; calibration re-enterable forever | — |

- ProfileV2 row created **at signup** with an empty-but-valid payload. Empty affinities ⇒
  everything hidden ⇒ the uncalibrated feed is the onboarding prompt, not noise.
- Calibration is **skippable and resumable**; abandonment loses nothing; cross-device
  resume works because state is server-side. The empty-feed copy communicates that feedback
  will keep improving personalization.
- **Skipped-calibration UX — explicit product decision**: a user who skips calibration gets
  an **intentionally empty feed** with a strong, persistent "calibrate your feed" state
  (full-canvas explanation + CTA). We deliberately do **not** ship a generic fallback feed
  or a second lightweight onboarding: the product's north star says "a beautiful generic
  feed is a failure" — unpersonalized noise would contradict the core thesis, and any
  minimal fallback would grow into a duplicate of Calibration V2. Skip exists as an escape
  (never trap the user), not as an equal path; the empty state doubles as the clearest
  possible explanation of what the product is. Calibration remains one tap away forever.
- `GET /api/auth/session` returns
  `{auth_enforced, user|null, onboarding: {completed, calibration: {answered, total}}}` —
  the single frontend bootstrap.
- **Demo users** never enter this machine (they cannot log in).

## Demo / development / QA separation

- **Real users**: email+password, `/me` surface.
- **Demo profiles**: credential-less `role='demo'` rows; reachable only through admin-gated
  `{user_id}` routes. Guy-vs-Deni QA comparison, shadow reports, real-data decision diffs,
  and learning tests against demo fixtures all keep working through the same endpoints as
  today, now behind an admin session.
- **Local frontend mode** (`VITE_DATA_MODE=local`): untouched and authless — pure frontend
  + frozen JS engine + `userProfiles.js`.
- **Dev workflow**: `ALLOW_INSECURE_AUTH_BYPASS=true` in `backend/.env` reproduces today's
  open legacy/ops surface for local/tailnet development and is the operational rollback
  lever — one explicit env line, impossible to reach in a Secure-cookie deployment.
- **Ops console** gets the "QA view-as" picker (the moved ProfileSwitcher) driving the
  admin `{user_id}` routes; the consumer product shows an account menu instead.

## Schema

### New table `users` (via `create_all` — real constraints allowed)

| column | type | constraints | notes |
|---|---|---|---|
| id | TEXT | PK | `usr_<ulid>`; literal `guy`/`casual_deni_fan` for demo rows; equals `profiles.user_id` |
| email | TEXT | UNIQUE, nullable | normalized; NULL for demo (SQLite UNIQUE permits multiple NULLs) |
| password_hash | TEXT | nullable | argon2id; NULL ⇒ login impossible |
| role | TEXT | NOT NULL DEFAULT 'user' | `user` \| `admin` \| `demo` (single column by design) |
| created_at | TEXT | NOT NULL | ISO-8601 (project convention) |
| onboarding_completed_at | TEXT | nullable | the only onboarding state column |
| last_login_at | TEXT | nullable | ops visibility |

### New table `auth_sessions` (via `create_all`)

| column | type | constraints | notes |
|---|---|---|---|
| token_hash | TEXT | PK | SHA-256 of the opaque token; raw token exists only in the cookie |
| user_id | TEXT | NOT NULL, indexed, **FK → users.id ON DELETE CASCADE** | real DB constraint — both tables are new. Requires enabling `PRAGMA foreign_keys=ON` per connection via an engine event listener — safe because no other FKs exist anywhere in the schema |
| created_at / expires_at | TEXT | NOT NULL | ISO-8601; fixed 30-day absolute expiry — never extended by activity |
| last_seen_at | TEXT | nullable | observability only (throttled updates); does not affect expiry |
| user_agent | TEXT | nullable | phone-vs-desktop QA nicety |

### Migration path

- **Zero soft-migration entries** in `database.py` — both tables are new; `init_db()`'s
  `create_all` picks them up. No ALTERs on existing tables → no SQLite constraint
  landmines, full rollback safety.
- **Startup ensure-step** (in the lifespan, after `seed_all_if_empty`), idempotent:
  1. For every `profiles.user_id` lacking a `users` row → insert
     `users(id=user_id, role='demo', email=NULL, password_hash=NULL)`. Covers both demo
     profiles and any stray QA profile deterministically.
  2. Admin bootstrap from env (create-only; never resets).
- **Existing data**: `profiles`, `feedback_events`, `calibration_responses` untouched —
  demo profiles, the real QA corpus, feedback history, and calibration history all survive
  unchanged. Rollback = revert code; two unused tables remain (harmless).

### Deletion semantics

`DELETE /api/me/account` (requires current password), one transaction: `feedback_events` →
`calibration_responses` → `profiles` → `users` (the `users` delete cascades `auth_sessions`
at the DB level via the FK; the legacy tables have no FKs, so their cleanup stays
app-level). Guards: `role='demo'` undeletable; the last remaining admin cannot self-delete.
Hard delete (soft-delete/retention deferred).

## API transition map

Authz legend — **Consumer**: session-derived identity; **Admin**: `role='admin'` (enforced
by default once gating lands; bypassable only via `ALLOW_INSECURE_AUTH_BYPASS`); **System**:
public by design. `/me` routes are thin wrappers resolving `current_user.id` and delegating
to the same repositories/services as the `{user_id}` routes — one seam, no service changes.

| Current | Target | Authz | Compat |
|---|---|---|---|
| `GET /health` | unchanged | System | permanent |
| — | `POST /api/auth/signup` / `login` / `logout`, `GET /api/auth/session` | Public (login rate-limited); logout=Session | permanent |
| — | `POST /api/me/password`, `DELETE /api/me/account` | Consumer (password re-entry) | permanent |
| — | `POST /api/me/onboarding/complete` | Consumer | permanent (skip path) |
| `GET /api/profiles` (lists all) | stays | **Admin** | permanent (QA list); frontend product stops calling it |
| `GET/PUT /api/profiles/{user_id}` | + `GET/PUT /api/me/profile` | Admin / Consumer | both permanent — `{user_id}` = QA view-as surface |
| `POST /api/profiles/{user_id}/never_show` | + `POST /api/me/never_show` | Admin / Consumer | both permanent |
| `GET /api/feed/{user_id}` | + `GET /api/me/feed` | Admin / Consumer | both permanent |
| `GET /api/debug/feed/{user_id}`, `GET /api/debug/shadow/{user_id}` | stay | Admin | permanent (QA) |
| `POST /api/feedback` (body user_id) | + `POST /api/me/feedback` (server sets user_id; body user_id rejected) | Admin / Consumer | both permanent — admin variant writes learning events against demo fixtures |
| `GET /api/feedback/{user_id}` | + `GET /api/me/feedback` | Admin / Consumer | both permanent |
| `GET /api/learning/{user_id}`, `POST .../reset` | + `GET /api/me/learning`, `POST /api/me/learning/reset` | Admin / Consumer | both permanent |
| `GET /api/calibration/items`, `POST /api/calibration/preview` | unchanged | Session (any role) | permanent |
| `POST /api/calibration/apply` (body user_id) | + `POST /api/me/calibration/apply` (stamps onboarding) | Admin / Consumer | both permanent |
| `GET /api/calibration/responses/{user_id}` | + `GET /api/me/calibration/responses` | Admin / Consumer | both permanent |
| `GET /api/calibration/headlines` | stays | Admin | deprecation candidate (out of scope) |
| `GET /api/articles`, `/{id}` | unchanged | Session (any role) | permanent |
| `/api/ingest/*`, `/api/translations/*`, `/api/classify/*` | unchanged paths | Admin | permanent |
| `/api/dev/*` | unchanged | Admin **AND** `ALLOW_DEV_RESET=true` (double gate) | permanent |
| `GET /api/feed-engine` | unchanged | Session | permanent |

Deliberately **not** mechanically `/me`-converted: debug/shadow/profile-list (admin-only,
need explicit targets), calibration items/preview (global/stateless), ops/system routes.

## Frontend product flow

- **Signed out**: `/login` and `/signup` as product-styled routes rendered **outside both
  AppShell groups** in `main.jsx` (PageNotFound precedent); compose `shared/` primitives +
  shadcn `input`/`label`/`form`; Hebrew RTL with logical utilities; product (editorial)
  styling — never console styling.
- **Bootstrap**: new `src/context/AuthContext.jsx` calls `GET /api/auth/session` on load;
  exposes `{authEnforced, user, onboarding}`. When the backend reports
  `auth_enforced: false` (bypass active) or `VITE_DATA_MODE=local` → render exactly today's
  UI (ProfileSwitcher intact) — the frontend is runtime-adaptive, no new env flags.
- **First run**: welcome screen (confirm display name, product explanation) → Calibration
  V2 (existing page, resume-aware) → apply → first personalized feed. Skip available at
  every step; skipping lands on the empty-feed onboarding state with a persistent calibrate
  banner.
- **Returning user**: session cookie → straight to feed with persisted state;
  mid-calibration users resume at the first unanswered item (cross-device).
- **Account/preferences**: account menu in the product Masthead (replaces ProfileSwitcher)
  → account page (email display, password change, logout, delete account); `/preferences`
  continues to show explicit + learned preference state via `/me` routes.
- **Session expiry / logout**: `apiFetch` translates 401 into an auth-expired event →
  AuthContext clears user → redirect to `/login` (with a gentle "session expired" note).
  Logout = `POST /api/auth/logout` + local state clear.
- **Ops console**: gains the QA view-as picker feeding the admin `{user_id}` debug routes;
  ops pages require an admin session in backend mode.
- **AppContext split** (highest-risk refactor of the milestone): product data flows move to
  `/me/*`; ops/debug flows keep `{user_id}` calls driven by the view-as picker; the
  local-mode branch is untouched.

## Security model

Threats tied to this architecture, with mitigations:

| Threat | Mitigation |
|---|---|
| SQLite file leak (disk/backup) | sessions stored as SHA-256; passwords argon2id — a leaked DB yields no usable credentials or session tokens |
| XSS steals session | HttpOnly cookie (no JS-readable token). Residual same-origin acting risk: audit that RSS-sourced titles are never rendered via `dangerouslySetInnerHTML` (React default escaping otherwise covers) |
| CSRF | SameSite=Lax + `Sec-Fetch-Site`/`Origin` middleware on mutating methods + audited absence of state-changing GETs; same-origin-only contract ⇒ no CORS-credentials surface |
| Brute force / stuffing | argon2id cost + an in-process fixed-window limiter that is **deliberately IP-independent**: behind the real chain (Tailscale Serve → Vite proxy → uvicorn) `request.client.host` is always the proxy/localhost address, so IP keying would silently collapse all clients into one bucket. Instead: per-account-key limit on the normalized submitted email (~10 attempts / 5 min → 429, applies whether or not the account exists) + a coarse **global** login limiter (~100 attempts / 5 min process-wide) as the distributed-attempt backstop. In-memory is correct for single-worker uvicorn |
| Insecure-bypass misconfiguration | fail-closed design: enforcement is the code default; only `ALLOW_INSECURE_AUTH_BYPASS=true` opens the legacy/ops surface, and startup **refuses to run** with bypass + `AUTH_COOKIE_SECURE=true` (the deployed-HTTPS signal) |
| Account enumeration | login: uniform "invalid email or password" + dummy-hash verify for unknown emails (timing-uniform). Signup deliberately reveals "email in use" — accepted for a private product (the fix requires email infra) |
| Session fixation / staleness | fresh token every login; logout deletes the row; fixed 30-day expiry; password change revokes all other sessions |
| Debug/ops exposure | entire ops surface `require_admin`; `/api/dev/*` keeps the extra `ALLOW_DEV_RESET` env gate; the tailnet still bounds network exposure; `/docs` stays unproxied to phone |
| Secrets | zero signing keys by design (opaque tokens). Only secrets: `AUTH_ADMIN_PASSWORD` in gitignored `.env` (create-only) and the DB file |
| Admin view-as abuse | admin `{user_id}` routes can mutate any user — acceptable solo-dev; log a warning breadcrumb on admin mutations of non-demo users |
| Cookie over Tailscale | `AUTH_COOKIE_SECURE=true` when fronted by Tailscale Serve HTTPS (explicit env — the scheme is not auto-detectable behind the Vite proxy) |

**Deliberately deferred** (with un-defer triggers): email verification (→ public signup
exposure); password reset via email (→ first locked-out real user; interim: admin reset
endpoint/CLI); trusted forwarded-IP contract + IP-keyed rate limiting (→ first real
reverse-proxy deployment, where `X-Forwarded-For` handling is defined and tested as part of
that milestone); shared-store rate limiting (→ multi-worker); 2FA/device management/audit
log (→ multiple admins); OAuth (→ real signup friction post-launch); soft-delete/retention
(→ compliance need); CSP/full security headers (→ first real hosting, belongs to
reverse-proxy config).

## Milestone decomposition

Seven PRs. Linear dependency chain except PR 4 ∥ PR 5 (both depend on PR 3). Every PR
passes the standing gates: full backend pytest green (non-decreasing count), frontend
test/lint/typecheck/build when touched, docs truth sweep, corpus DB never reset.
Authoritative per-issue detail lives in the GitHub issues: PR 1 = #49, PR 2 = #50,
PR 3 = #51, PR 4 = #52, PR 5 = #53, PR 6 = #54, PR 7 = #55 (Epic #48, Milestone 2).

1. **Auth core (backend)** ⭐ architecture review (completed) — **complete on main via PR #56 / Issue #49**:
   users/auth_sessions tables (FK + pragma), auth service + `/api/auth/*`, security
   deps, bypass flag + startup guard, CSRF middleware, ensure-step (demo users
   backfill + admin bootstrap). Legacy routes untouched.
2. **Consumer `/api/me/*` surface (backend)** — full consumer API, always session-gated;
   signup creates the profile row; onboarding block in the session payload.
3. **Frontend auth shell** — AuthContext, login/signup pages, account menu, 401 handling;
   runtime-adaptive (bypass ⇒ today's UI exactly).
4. **Onboarding flow** ⭐ Product Review gate — the state machine end-to-end: welcome, calibration
   resume-awareness, empty-feed prompt + calibrate banner, routing guards.
   The former cross-track reliability blocker (#63) cleared 2026-07-10 with the
   sign-off approval — this PR depends on PR 3 only.
5. **Admin gating + ops view-as** — legacy `{user_id}` + ops routes gain `require_admin`,
   enforced by default from this PR (fail closed); ProfileSwitcher moves to the ops console
   as QA view-as; AppContext split. Transitional, time-boxed compat: conftest + dev `.env`
   set `ALLOW_INSECURE_AUTH_BYPASS=true` explicitly until PR 6.
6. **Enforcement verification + explicit test identities** ⭐ Security/Regression review gate — remove the
   transitional bypass; replace the single implicit test client with explicit
   `anonymous_client` / `user_client` / `admin_client` fixtures (one shared app instance,
   separate cookie jars); migrate legacy tests to the right fixture per route contract;
   docs truth sweep; `signal-real-data-qa` before/after diff for both demo profiles must
   show **zero decision changes**.
7. **Account lifecycle + hardening** — password change (revokes other sessions), account
   deletion cascade + account page, expired-session pruning, limiter tuning,
   admin-mutation logging.

**Review gates** (model-independent — the reviewer may be a human or any capable agent
that is not the implementer; the full entry criteria / evidence / approval contracts
live in the issue bodies): PR 1 auth/session/identity architecture review (completed
2026-07-08); PR 4 (#52) Product Review — Onboarding, a genuine human product-judgment
gate; PR 6 (#54) Security/Authorization Review + Regression Gate. PR 4's former reliability
gate (#63) cleared 2026-07-10.

## Risks

1. `AppContext.jsx` refactor (PR 5) — it conflates product state, ops view-as, and
   local-mode engine state. Mitigation: AuthContext is additive; AppContext changes only
   re-point data fetching; the local-mode branch is untouched and tested first.
2. Test-identity migration (PR 6) — many legacy test files change to explicit fixtures.
   Mitigation: purely mechanical fixture substitution; the payoff is that no authorization
   regression can hide behind implicit cookie state.
3. Phone/Tailscale cookie path — the first Secure-cookie exercise for this app; an explicit
   manual-QA item in PR 3 and PR 6, never assumed.
4. Real corpus DB — every startup step is create-only/idempotent; PR 1 manual QA proves
   both demo feeds unchanged against the real DB before anything else lands.

## Non-goals (must not enter this milestone)

Email infrastructure of any kind (verification, reset mails); OAuth/social/magic
links/JWT; multi-profile accounts, sharing, teams; Alembic adoption (zero migrations
needed); rate-limiting sophistication beyond in-process; push-notification delivery; real
hosting/reverse proxy (separate milestone; this design slots into it); any
relevance/scoring/classification change; rewriting the demo-fixture system; touching the
frozen JS engine.

## Project skills impact

A future **`signal-user-boundary-change`** skill becomes worthwhile **after PR 6**, once
these invariants are stable enough to encode: (a) the consumer-vs-admin route split (`/me`
never accepts caller ids; `{user_id}` is admin-only); (b) the
`get_current_user`/`require_admin` dependency pattern; (c) demo users are credential-less
and undeletable; (d) sessions are opaque+hashed, cookie-delivered, fixed-expiry; (e) the
fail-closed `ALLOW_INSECURE_AUTH_BYPASS` semantics; (f) the explicit
`anonymous_client`/`user_client`/`admin_client` test-identity pattern. Trigger to create
it: the first post-milestone change that touches ownership or auth surfaces.

Existing skills needing updates as the milestone lands (mostly in PR 6's truth sweep):
**signal-doc-truth** (this doc joins the living contracts; the "Authentication: None"
claims in BACKEND_FOUNDATION / PRODUCT_UNDERSTANDING / CURRENT_PROJECT_STATE §10 and the
MOBILE_REMOTE_ACCESS security-model paragraph get corrected only when behavior actually
changes); **signal-real-data-qa** (demo diffs will require an admin session);
**signal-pr-finish** (new API surfaces must update the frontend consumer);
**signal-relevance-change** (profile mutation paths gain `PUT /api/me/profile`);
**signal-handoff** (new standing decisions: auth model, ownership boundary, fail-closed
bypass semantics).

## Changelog

- 2026-07-10 (milestone completion) — #54 merged (PR #75) after two independent-review
  rounds (consumer learning identity boundary, route-derived authz inventory with
  coverage + dependency-truth guards, fresh unique per-test identities with 10 direct
  isolation proofs, frontend ops-role boundary, README/doc truth). #55 merged (PR #76):
  password change with other-session revocation, transactional account deletion
  (demo-undeletable, last-admin guard), expired-session pruning on login,
  admin-mutation breadcrumbs, product account page. Milestone acceptance journey
  verified on a corpus copy (19 steps). Milestone 2 closed.

- 2026-07-10 (User Platform execution) — PR #71 (#50): session-derived `/api/me/*`
  consumer surface with delegation parity; the product-surface gating bullet moved to
  PR 5 (documented issue-internal contradiction). PR #72 (#51): frontend auth shell
  (AuthContext, login/signup, session guard, account menu). PR #73 (#53): fail-closed
  admin gating of the legacy/ops surface, `require_session` product surface, AppContext
  consumer/QA split, ProfileSwitcher → ops QA view-as. PR #74 (#52): onboarding state
  machine + welcome + resumable calibration + intentionally-empty-feed CTA —
  **merged; Product Review APPROVED by the product owner (2026-07-10)**.
  PR #75 (#54): transitional test bypass removed; explicit anonymous/user/admin
  identity fixtures; docs truth sweep — **open, awaiting independent
  security/regression review + the owner's phone/Tailscale pass**. Note: #52 was executed after #53 (order allowed
  by the graph) so onboarding lands on the session user's own /me feed.

- 2026-07-08 — Architecture approved (design revision pass: fail-closed
  `ALLOW_INSECURE_AUTH_BYPASS`; fixed 30-day session expiry; real FK on
  `auth_sessions.user_id`; IP-independent login rate limiting; explicit test identities;
  skipped-calibration empty-feed decision). At approval time, implementation had not
  yet landed on main.
- 2026-07-09 — PR #56 merged for Issue #49 backend Auth Core. Later User Platform
  issues remain unimplemented; #50 is the next unblocked issue.
- 2026-07-10 — Cross-track gate CLEARED: Reliability Sign-off #63 closed (Epic #58
  complete for the core track, PRs #66–#70; golden-17 suite green; zero demo-profile
  drift). #52 unblocked, depends on #51 only.
- 2026-07-09 (later) — Cross-track gate added: #52 (onboarding) is hard-blocked by the
  Classification & Feed Reliability sign-off (#63, Epic #58, Milestone 3) because
  onboarding feeds Calibration V2 inference and first impressions off classification
  facts (evidence: docs/CLASSIFICATION_RELIABILITY_INVESTIGATION.md). #52 may now land
  before or after #54; both orders are handled in the issue bodies. All review
  checkpoints converted to model-independent contracts (Product Review for #52,
  Security/Authorization + Regression for #54) defined in the issue bodies; Epic #48
  is the single canonical home of the dependency graph.
