# Personalized Results — Contract (issue #178)

**Status:** implemented (branch `feature/personalized-results-178`, PR for #178).
This is the authoritative contract for the Results feature; where another doc
disagrees, this wins for results behavior.

## 1. What it is

A **preference-filtered history of real game results** — scores, competition,
date/time, and status — for the teams, players, and competitions a user already
follows, **across sports** (basketball and football today). It is deliberately
**not** a generic scoreboard: a user who follows nothing sees nothing, and
unrelated games never appear. The whole pipeline (relevance, resolution,
grouping, rendering) is sport-agnostic — adding a sport is a config + id-mapping
change, not new logic. Draws are a first-class outcome (no false winner emphasis).

Relevance is derived from the **same ProfileV2 affinity model as the feed**
(`docs/PREFERENCE_MODEL_V2.md`, `docs/RELEVANCE_CONTRACT.md`). There is no
results-specific preference system.

## 2. Relevance rules (server-side, authoritative)

A game is relevant to a profile when **any** of:

1. either team is an explicitly **followed team** (`team` scope affinity, level ≥ 1), or
2. either team is the current team of a **followed player/coach** (the player's
   `team_id` in the taxonomy — so the casual Deni fan sees Portland without
   following the franchise), or
3. the game's **competition is followed** (`competition` scope affinity, level ≥ 1).

Level threshold is the "Follow" tier (1); "Star" is 2. **Sport-level follows do
NOT qualify** (sport Follow = level 0) — this is the guard against the page
degrading into a generic scoreboard. Negative/de-prioritized affinities (e.g.
Guy's `comp:acb = -1`) are below threshold and therefore not followed.

Relevance and isolation are enforced **server-side** in
`app/results/service.py`. The identity comes only from the session
(`GET /api/me/results`) or, for the admin view-as route
(`GET /api/results/{user_id}`), from the admin gate — the client never supplies
a profile to filter by. A direct team follow beats a player-derived reason in
`relevance_reason` (transparency, not a decision input).

## 3. Data source & provider abstraction

**Provider:** [TheSportsDB](https://www.thesportsdb.com) free tier, public test
key `3` (documented, **not a secret**). It covers every core competition and
returns real data with no account or paid plan.

The source is isolated behind `app/results/providers/`:

- `base.ResultsProvider` — protocol: `fetch(competition_ids) -> FetchOutcome`
  (normalized games + per-competition error map + fetched counts). **Partial
  failure is first-class**: one competition erroring never loses the others.
- `thesportsdb.TheSportsDBProvider` — HTTP adapter with timeout + bounded retry
  (429/5xx/timeouts), per-competition isolation, and `normalize_event()` (the
  pure, unit-tested raw→`NormalizedGame` mapping). Team names are resolved to
  canonical taxonomy ids by `team_resolver.resolve_team()` (competition-scoped,
  so shared football/basketball aliases pick the right sport).
- `fake.FakeResultsProvider` — deterministic offline games for tests and
  `RESULTS_PROVIDER=fake` (no network).

`providers.get_provider()` selects by `RESULTS_PROVIDER`.

### Tracked competitions → provider league ids (verified live 2026-07)

| Sport | Competition | comp id | TheSportsDB league |
|---|---|---|---|
| Basketball | NBA | `comp:nba` | 4387 |
| Basketball | EuroLeague | `comp:euroleague` | 4546 |
| Basketball | EuroCup | `comp:eurocup` | 4547 |
| Basketball | Israeli Basketball Premier League | `comp:ibl` | 4474 |
| Basketball | Spanish ACB | `comp:acb` | 4408 |
| Football | Israeli Premier League | `comp:ligat_haal` | 4644 |
| Football | English Premier League | `comp:epl` | 4328 |
| Football | Spanish La Liga | `comp:la_liga` | 4335 |
| Football | German Bundesliga | `comp:bundesliga` | 4331 |
| Football | UEFA Champions League | `comp:ucl` | 4480 |

TheSportsDB labels football as sport "Soccer"; the normalizer trusts the
**taxonomy** competition's sport (`football`), so `NormalizedGame.sport` stays
consistent with the rest of the system. Tennis is intentionally out of scope —
it is tournament-shaped (no persistent home/away teams with a running score), so
it does not fit the `game_results` model. `TestScopeCoverage` asserts every
tracked competition has a mapped league id (no silent "no league id" errors).

### History window (bounded — no unbounded crawl)

Per competition we fetch `eventspastleague` (most recent) + `eventsseason` for
the two most recent seasons. The free tier returns a small bounded slice
(≈1 recent + ≤5 per season), so ingestion is naturally bounded. The read path
shows games within `RESULTS_WINDOW_DAYS` (default 400 — a recent-history window,
**not** the 36h feed horizon, because results are a history, not a live feed).

## 4. Persistence & idempotency

`game_results` (project-owned, provider-agnostic; new table, created by
`create_all` on clean and existing DBs alike — no `ALTER` needed). Identity is
`(provider, external_id)`; the primary key is `game_` + sha1(provider|external_id).
`game_result_repository.upsert` therefore **updates** an existing game (score /
status / time drift between cycles) and never inserts a duplicate. `upsert_many`
reports created vs updated.

`results_sync_state` (one row) records `last_attempt_at` / `last_success_at` /
`last_status` / `last_summary` — it both throttles the scheduler stage and
powers ops observability.

## 5. Sync & scheduling

- **The read path never calls the provider** — `GET` reads the DB only.
- Sync runs (a) as a **scheduler stage** in `orchestrate_cycle`, guarded by
  `RESULTS_SYNC_ENABLED` and throttled by `RESULTS_SYNC_MIN_INTERVAL_SECONDS`
  (skips if the last attempt is newer), failure-degrading the cycle like the
  notification/retention stages (never blocks ingestion, its own session); and
  (b) via the manual admin `POST /api/results/sync` (bypasses the throttle).

## 6. API

| Method | Route | Auth | Notes |
|---|---|---|---|
| GET | `/api/me/results` | session (`require_user`) | consumer surface; identity from session |
| GET | `/api/results/{user_id}` | admin (`require_admin`) | ops view-as, parity handler |
| POST | `/api/results/sync` | admin | manual sync (force) |
| GET | `/api/results/sync/state` | admin | last sync outcome |

Response: `{ "has_preferences": bool, "games": [GameResult] }`. `has_preferences`
distinguishes the "no follows" state from "no relevant results". Each
`GameResult` carries `competition_he/en`, `status`, `start_time` (UTC ISO),
`home`/`away` (`id`, `name` = taxonomy Hebrew when resolved else provider name,
`name_provider`, `score`, `is_winner`), `winner`, and `relevance_reason`.

## 7. Frontend

`/results` (product route, RTL). Data flows through `AppContext`
(`resultsGames` / `resultsHasPreferences` / `resultsLoading` / `resultsError`),
using `/api/me/results` for consumer sessions and `/api/results/{user_id}` for
admin view-as — matching the feed's routing exactly. States: loading skeleton,
error (retry), no-preferences (CTA to `/interests`), no-relevant-results, and a
chronological grouped list (`groupByDay`, newest first). The winner of a
completed game is quietly emphasized (bold name + green score); times render in
`Asia/Jerusalem`. Games render 1-up on mobile, 2-up from `sm`.

Local data mode (offline demo / tests) runs the identical
normalize → relevance → group path over `src/data/mockResults.js` with
client-side relevance (`resultsRelevance.js`); in backend mode the server is the
sole relevance authority.

## 8. Configuration

See `backend/.env.example` (`RESULTS_*`, `THESPORTSDB_*`). Activation pattern
matches CLUSTERING/TELEGRAM: `RESULTS_SYNC_ENABLED` defaults false in the example
and is opted into in the live `.env`. `RESULTS_ENABLED=true` keeps the read
surface available (safe with an empty corpus). Rollback = flip
`RESULTS_SYNC_ENABLED=false` (no data touched).

## 9. Tests

- Backend `tests/test_results_178.py` (45): payload normalization, stable
  identity + idempotent upsert, score/status drift, duplicate prevention, team
  resolver, followed-team / followed-league / followed-player-team relevance,
  unrelated-game exclusion, profile isolation (incl. two real login sessions),
  chronological ordering, sync bookkeeping/throttle/error capture, the API
  auth matrix + response contract, and the **cross-sport** path (football
  normalization taking the taxonomy sport, football-follow → football results,
  football draw has no winner, basketball profiles never see football, and
  every tracked competition maps to a provider league id).
- Frontend `src/components/results/*.test.js` (26): normalization, timezone/day
  formatting, grouping, and relevance/isolation (deriveFollows, filter,
  preference-change).

## 10. Known limitations

- The free provider tier returns a small bounded slice — a narrow follower may
  legitimately see 0 recent games (correct "no generic scoreboard" behavior).
- Team names the taxonomy doesn't know (e.g. an apostrophe'd club, a non-tracked
  visitor) fall back to the provider English name; such games are still relevant
  via a followed competition.
- Live in-play score streaming is out of scope (status supports `live` but sync
  is periodic, not a stream).
