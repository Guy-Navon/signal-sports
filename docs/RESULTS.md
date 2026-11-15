# Personalized Results — Contract (issue #178)

**Status:** implemented and merged (#178, PR #179, 2026-08-23). The production `.env` runs
`RESULTS_SYNC_ENABLED=true`, so the worker refreshes results every 30 minutes at most.
This is the authoritative contract for the Results feature; where another doc
disagrees, this wins for results behavior.

2026-11-15 — issue #517: per-game detail storage (`game_details`,
`game_player_lines`), an optional provider detail capability and a sync stage,
behind `RESULTS_DETAIL_ENABLED` (default off). See §11; #523 exposes stored detail
through the opt-in API described in §6. The new page is built separately on `ui/next`.

2026-11-15 — issue #522: per-provider health (`results_provider_health`), a
per-provider switch (`RESULTS_PROVIDER_DISABLED`), a read-time fallback to the
default provider (`RESULTS_PROVIDER_STALE_HOURS`) and a backup sync. See §15. No
effect while no route is set (production today).

## 1. What it is

A **preference-filtered history of real game results** — scores, competition,
date/time, and status — for the teams, players, and competitions a user already
follows, **across sports** (basketball and football today). It is deliberately
**not** a generic scoreboard: a user who follows nothing sees nothing, and
unrelated games never appear. The whole pipeline (relevance, resolution,
grouping, rendering) is sport-agnostic — adding a sport is a config + id-mapping
change, not new logic. Draws are a first-class outcome (no false winner emphasis).

Relevance is derived from the **same ProfileV2 affinity model as the feed**
(`docs/PREFERENCE_MODEL_V2.md`, `docs/RELEVANCE_CONTRACT.md`). The separate
chosen-player setting below controls extra result lines only, never game relevance
or feed decisions.

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
key `123` (documented, **not a secret**). It covers every core competition and
returns real data with no account or paid plan. The old key `3` was permanently
disabled and answers 403 with a message naming `123` (found 2026-10-25).

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
  `RESULTS_PROVIDER=fake` (no network). It also implements the optional detail
  capability (§11).

`euroleague.EuroLeagueProvider` (issue #519) supports official EuroLeague and
EuroCup results and detail. It is opt-in; see the activation example below.
`espn_nba.ESPNNBAProvider` (issue #520) supports NBA scores, upcoming games and
detail via ESPN; opt-in activation and source limits are in section 13.
`bamboo.BambooFootballProvider` (issue #521) supports Israeli Premier League
football results and detail (section 14), also opt-in.

`providers.get_provider()` selects by `RESULTS_PROVIDER` from `providers.REGISTRY`
(name -> constructor; a new provider is one line there).

**Routing (#529).** `RESULTS_PROVIDER_ROUTES="comp:ibl=winner,comp:euroleague=euroleague"`
sends each listed competition to its provider; every other competition goes to
`RESULTS_PROVIDER`. Empty (the default) means no routing: `get_provider()` returns the
plain provider and the requests are exactly the single-provider ones. With routes it
returns `routing.RoutingProvider`, which splits `fetch(competition_ids)` per provider and
merges the `FetchOutcome`s (games, errors, fetched counts, `not_checked`), and sends
`fetch_details(games)` to the provider named in `game.provider`, only if it
`supports_details`. The config is validated at API startup (and on every sync): a
malformed entry, an unknown provider, an unknown competition (not in the taxonomy) or a
competition listed twice raises `ValueError`; nothing is dropped silently. One provider
raising does not lose the others (its competitions get the exception class name in
`errors`).

**Read rule (#532).** Reads show, per competition, only rows whose `provider` equals the provider that competition is currently routed to (the route, else `RESULTS_PROVIDER`): `providers.active_provider_for(competition_id)` / `active_provider_map()`, applied in `game_result_repository.list_games(active_providers=...)` by `results.service.personalized_results` (consumer and admin view-as share it). Older rows of the same games from a previous provider are not shown as duplicates; nothing is deleted, and switching a route back shows them again. Detail lookups use only the ids that pass. With no routes every row belongs to the default provider, so output is unchanged. A bad route config on the read path logs a warning and falls back to the default provider instead of failing. The demo exporter does not read results. Since #522 the route is also dropped when its provider is disabled or not fresh for that competition (§15); one provider per competition still holds.

**Rate limits are per provider.** A 429 puts only that provider's competitions in
`not_checked`; the others sync. The block is stored in the sync summary as
`rate_limited_until_by_provider` (`{name: ISO time}`); `rate_limited_until` stays as the
latest of them for ops readers. The next sync skips only providers still blocked (their
competitions are `not_checked` without a request) and is skipped entirely (`rate_limited`)
only when every provider it would call is blocked. The detail stage likewise skips only
the limited or blocked providers. A summary written before #529 (only
`rate_limited_until`) blocks every provider until it passes.

### Official EuroLeague / EuroCup (issue #519, opt-in)

Keep `RESULTS_PROVIDER=thesportsdb` for other competitions and set:

```dotenv
RESULTS_PROVIDER_ROUTES=comp:euroleague=euroleague,comp:eurocup=euroleague
RESULTS_DETAIL_ENABLED=true
```

If Winner routes (section 12) are already enabled, combine both providers' entries
in the same comma-separated `RESULTS_PROVIDER_ROUTES` value.

Defaults stay unchanged: routes are empty and detail is off. Neither deployment
nor reading results sends new requests. The existing scheduler/manual sync runs
this provider only after it is selected. Roll back by clearing these routes and
setting `RESULTS_DETAIL_ENABLED=false`.

The Competition Engine's public reads currently need no API key. `fetch` makes
one `api-live.euroleague.net/v2/competitions/{E|U}/seasons/{code}/games`
request per requested competition per sync, including played and upcoming games.
Season codes roll over on July 1 (`season.startDate`): November 2026 and January
2027 both select `E2026` / `U2026`. The normalized season label is `2026-2027`;
external ids include the season and competition (`E2026_103` / `U2026_103`), so
identical game codes cannot collide. `RESULTS_SEASONS`, `RESULTS_RECENT_DAYS`
and the TheSportsDB-specific `RESULTS_MAX_GAMES_PER_COMPETITION` cap do not limit
this complete current-season response. `utcDate` supplies UTC start times;
`played=false` means scheduled, with scores unset rather than the source's 0-0.
Teams use the existing resolver; the league's sponsored Israeli club names (Maccabi Rapyd, Hapoel IBI, Hapoel Midtown) map through a provider-local table, never taxonomy aliases, so sponsor names do not change article classification.

Detail uses `live.euroleague.net/api/Boxscore?gamecode=N&seasoncode=E2026`
(or `U2026`), one request per finished candidate. This endpoint matches the saved
real fixtures and provides player ids, decimal-converted minutes (`DNP` -> null),
English names, native player/team stats, quarter scores, attendance and referees
in one response. `leaders_from_lines(..., "points")` retains tied top scorers.
The venue comes from the season response when available in this provider instance;
it may be absent for an older stored game. The existing detail stage caps each
run and permanently skips games with stored detail (section 11).

Ranks use the v3 `competitions/{E|U}/seasons/{code}/rounds/{round}/basicstandings`
endpoint, cached by season + round for the provider instance (including failures).
Each lookup uses the same bounded retry policy; it is not repeated for every game.
The source's `position` is stored as `team_stats.home.rank` / `.away.rank`, with
`standings_round` on each side, ready for #523. EuroCup positions are group ranks.
Native totals remain on each side, with `coach`, `quarters` and the unmodified
`referees` string (commas also occur inside referee names). Missing standings
leave rank absent without losing the box score. A standings 429 keeps the already
fetched box score without rank, stops further requests and propagates Retry-After.

Requests share `RESULTS_HTTP_TIMEOUT_SECONDS`, `RESULTS_HTTP_MAX_RETRIES` and
`RESULTS_HTTP_MIN_INTERVAL_SECONDS`, including scores, box scores, standings and
retries. The User-Agent is `signal-sports-results/1.0`. 401/403 report
`source unavailable (HTTP N)` for that competition/game without retrying or
raising to the caller. A 429 is never retried: remaining competitions/games
are `not_checked`, with Retry-After (60 seconds if missing/invalid), using the
existing provider-specific sync block. No LLM, player Hebrew mapping or API/UI
changes are included.

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
the two most recent seasons + `eventsday` (`d=<UTC date>&l=<league id>`) for
the last `RESULTS_RECENT_DAYS` UTC days, today first. **The default is 0 (off)**, so
deploying the code adds no traffic. Set 1 (today) or 2 (today and yesterday) in `.env` to
enable it. The free tier returns a small bounded slice, so
ingestion is naturally bounded. Measured with key `123` on 2026-10-25:
`eventspastleague` returns **1** event, and `eventsseason` returns **15**, the
**earliest** games of the season (IBL 2026-27: 10–23 October). The provider's
documentation lists a free limit of **3** for `eventsday` (league filter by id
or name) and **1 home event only** for the per-team `eventslast` / `eventsnext`,
which is why per-team requests are not used. The per-day fetch is what keeps
the last two days' games arriving once a season is past its first 15 games. The
3-per-day figure comes from the docs; it was not measured live (no test requests
are sent to the provider). An event whose `idLeague` names another league is
dropped, so a day reply that ignored the filter cannot file foreign games under
a tracked competition. With one season and two days, a sync over the 10 default
competitions makes 40 requests, about 4.7 minutes at the 7 s spacing (20 and
about 2.3 minutes before). The worker waits its interval after a cycle ends, so
the cycle that runs the sync delays the next ingestion by that long. The free
limit is 30 requests a minute; one sync makes 1 + one per season + one per
recent day requests per competition (`RESULTS_SEASONS` narrows the seasons,
`RESULTS_RECENT_DAYS=0` turns the per-day fetch off, and values above 7 are
capped at 7), and the provider spaces
them by `RESULTS_HTTP_MIN_INTERVAL_SECONDS` (default 7 s, a conservative choice, not a
verified limit: the docs say 30 a minute, yet 2.5 s spacing was blocked at about the 11th
request on 2026-10-25). A 429 is not retried. The sync stops, the competitions it did not
reach are recorded as `not_checked` (not as errors), status `rate_limited` or `partial`,
and `rate_limited_until` (from Retry-After, default 60 s) is stored in
`results_sync_state`, so no caller, worker or admin endpoint, sends a request before it
passes. A 429 never blocks ingestion. The read path
shows games within `RESULTS_WINDOW_DAYS` (default 400 — a recent-history window,
**not** the 36h feed horizon, because results are a history, not a live feed).

## 4. Persistence & idempotency

`game_results` (project-owned, provider-agnostic; new table, created by
`create_all` on clean and existing DBs alike — no `ALTER` needed). Identity is
`(provider, external_id)`; the primary key is `game_` + sha1(provider|external_id).
`game_result_repository.upsert` therefore **updates** an existing game (score /
status / time drift between cycles) and never inserts a duplicate. `upsert_many`
reports created vs updated. One guard (#448): a stored `final` game is never downgraded to
`unknown`, and its score is kept when that payload has none; real corrections (e.g.
`postponed`, a changed score) still apply.

`results_sync_state` (one row) records `last_attempt_at` / `last_success_at` /
`last_status` / `last_summary` — it both throttles the scheduler stage and
powers ops observability. `last_attempt_at` is written **before** the provider is
called. An unexpected provider exception becomes status `error` with
`errors = {"provider": "<class name>"}` (the traceback goes to the log).

`results_sync_lease` (one row, new table via `create_all`) makes sync single-flight
across processes, with the scheduler lease's conditional-UPDATE pattern on a separate
row. A sync that finds it held returns `{"skipped": "in_progress"}` without calling the
provider. It has no heartbeat: a crashed holder blocks syncs until the lease is an hour
old, then the next sync takes over.

`game_details` and `game_player_lines` hold per-game detail (§11), created the same
way by `create_all`. `results_provider_health` holds per-provider health (§15), also
created by `create_all`.

## 5. Sync & scheduling

- **The read path never calls the provider** — `GET` reads the DB only.
- Sync runs (a) as a **scheduler stage** in `orchestrate_cycle`, guarded by
  `RESULTS_SYNC_ENABLED` and throttled by `RESULTS_SYNC_MIN_INTERVAL_SECONDS`
  (skips if the last attempt is newer), failure-degrading the cycle like the
  notification/retention stages (never blocks ingestion, its own session); and
  (b) via the manual admin `POST /api/results/sync` (bypasses the throttle, not the
  lease or a provider block; blocks are per provider, §3).

## 6. API

| Method | Route | Auth | Notes |
|---|---|---|---|
| GET | `/api/me/results` | session (`require_user`) | consumer surface; identity from session |
| GET | `/api/me/results/players` | session | own chosen players, Hebrew names |
| GET | `/api/me/results/players/catalog` | session | all taxonomy players for the results picker (names and aliases) |
| PUT | `/api/me/results/players` | session + normal CSRF checks | replace own choices; no feed mutation |
| GET | `/api/me/results/games/{game_id}/detail` | session | relevant final game's serving-provider box score, else 404 |
| GET | `/api/results/{user_id}/games/{game_id}/detail` | admin | identical view-as handler |
| GET | `/api/results/{user_id}` | admin (`require_admin`) | ops view-as, parity handler |
| POST | `/api/results/sync` | admin | manual sync (force) |
| GET | `/api/results/sync/state` | admin | last sync outcome, plus `health` (§15) |

Response: `{ "has_preferences": bool, "games": [GameResult] }`. `has_preferences`
distinguishes the "no follows" state from "no relevant results". Each
`GameResult` carries `competition_he/en`, `status`, `start_time` (UTC ISO),
`home`/`away` (`id`, `name` = taxonomy Hebrew when resolved else provider name,
`name_provider`, `score`, `is_winner`), `winner`, and `relevance_reason`.

2026-11-15 — #523: every old field retains its meaning. Additive fields are:

- `local_date`: Asia/Jerusalem calendar date (`YYYY-MM-DD`, null without a usable start).
  Together with existing `sport` and `competition_id`, this supports date → sport → league.
- `home.rank` / `away.rank`: positive integer from `detail.team_stats.<side>.rank`, else null.
- `leaders`: `[{side, name, entity_id, stat, value}]`. Basketball includes points leaders
  (and all tied scorers), never rebounds/assists leaders; football includes every scorer.
  Names follow §11's mapping/source fallback rule. No quarter scores in the list.
- `chosen_player_lines`: only the session/view-as user's explicit choices that played.
  Each has `side`, `entity_id`, `name`, `minutes` and `stats`: basketball points/rebounds/assists;
  football goals/assists/yellow_cards/red_cards. Native EuroLeague rebounds/assists are
  normalized here. DNP/zero-minute zero-stat lines are omitted; missing stats are not invented.
- `venue`, `attendance` (null when unknown), and `detail_available` (bool).

**Opt-in boundary:** `RESULTS_DETAIL_ENABLED=false` retains the legacy game set, order,
status behavior and all old field values, including with no routes; new detail fields
are empty/null/false. The flag also gates the detail endpoint (404 while off). With
it on, list reads show finals in the existing history window plus scheduled relevant
games from now through `RESULTS_UPCOMING_DAYS` days ahead, inclusive (default 7).
Live, postponed, cancelled and unknown games are **omitted**; no in-play state is
invented. The upcoming window reads stored rows only, without new provider calls or
changing provider fetch windows. Results-only competition expansion makes a follow
of `comp:ibl` also cover `comp:winner_cup` and `comp:il_super_cup` while opted in.
Neither this expansion nor chosen players change feed relevance or classification.

The popup response is `{game_id, players, team_stats, venue, attendance}`. Each player
has side, source_player_id, entity_id, display `name`, minutes and complete native
`stats` (box scores may include players not selected for an inline line). It uses
`service.visible_details` and the same relevance, history window and #522 serving
decision as the list; invisible, wrong-provider, missing-detail and missing games
all answer 404. Consumer identity comes only from the session. Admin view-as reads
the target user's choices, never the admin's. Reads never fetch providers.

2026-11-15 — #524: choices live in `results_chosen_players`, composite primary key
`(user_id, entity_id)` plus UTC `created_at`, created by `create_all`. Account
deletion cascades to these choices. GET and PUT return
`{"players": [{"entity_id": "player:deni_avdija", "name": "דני אבדיה"}]}`.
PUT accepts `{"entity_ids": ["player:deni_avdija"]}` (full replacement, at most
200 ids; duplicates collapse). Empty clears choices. Every id must identify a
taxonomy player; otherwise 422 before any write. Extra fields, including identity,
are forbidden. Unchanged choices retain their timestamps on retries. Session
identity is authoritative for every role. This API neither reads nor changes
ProfileV2, affinities, feed decisions or results relevance. No admin privileges
are required. The public demo has no API client or write surface; its bundle
guard continues to enforce that boundary. UI placement remains Guy's decision.
The read-only `/players/catalog` returns `players` with `entity_id`, Hebrew `name`,
`name_en` and `aliases`, including roster players whose feed mentions imply their
team. It is derived directly from taxonomy players. The shared feed catalog and
classification policy remain unchanged; result choices are not feed follows.

## 7. Frontend

**Public demo boundary (#526, 2026-11-15; results export fixed 2026-11-16).**
The demo exporter writes `feed.json`, `meta.json` and `results.json`.
`results.json` contains the demo profile's final games, projected onto an
explicit allowlist: the game identity, competition, sport, season, stage,
status, times, winner and relevance reason, plus each side's id, names, score
and winner flag. Leaders, chosen lines, venue, attendance, ranks and every
box-score field are dropped, whatever the results API serves. All three files
are then checked recursively against the results detail/stat keys (including
leaders, chosen lines, players, team stats, rank, venue and attendance). A
violation fails the export and preserves the previous snapshot. The stats bundle
guard (`npm run check:demo-bundle`) is the UI part of #526.

Before the fix, the results export bypassed that check. On 2026-11-16, from
01:10 to about 01:20, the public `results.json` carried leaders, venue,
attendance and ranks for 39 games. This followed `RESULTS_DETAIL_ENABLED` going
on in production the evening before. The file was stripped and redeployed, and
the hourly publish task was paused until this fix.

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

The #523 additive API supports the forthcoming `ui/next` page: the client groups by
`local_date`, then `sport`, then `competition_id`, and loads the popup separately.
The existing main UI continues to read its original fields. Scores remain usable
when a serving source has no detail; `detail_available=false` and leaders/lines empty.

## 8. Configuration

See `backend/.env.example` (`RESULTS_*`, `THESPORTSDB_*`). Activation pattern
matches CLUSTERING/TELEGRAM: `RESULTS_SYNC_ENABLED` defaults false in the example
and is opted into in the live `.env`. `RESULTS_ENABLED=true` keeps the read
surface available (safe with an empty corpus). Rollback = flip
`RESULTS_SYNC_ENABLED=false` (no data touched). `RESULTS_DETAIL_ENABLED` and
`RESULTS_DETAIL_MAX_PER_RUN` control the detail stage (§11). `RESULTS_PROVIDER_DISABLED`,
`RESULTS_PROVIDER_STALE_HOURS` and `RESULTS_PROVIDER_BACKUP_SYNC` control health,
fallback and backup sync (§15).

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
- Backend `tests/test_results_pacing.py`: request spacing, the 429 stop and the
  stored Retry-After block. `tests/test_results_coverage.py`: the per-day
  requests (UTC dates, request count per competition, `RESULTS_RECENT_DAYS=0`)
  and the `idLeague` guard. Both use `httpx.MockTransport`, never the network.
- Backend `tests/test_results_detail_517.py`: detail upsert idempotency and the
  read function, leaders from box-score lines, flag off = no detail calls, final
  games only, never re-fetched, the per-run cap, providers without detail, per-game
  and whole-call failures that leave the scores sync untouched, provider-identity
  scoping, and both rate-limit paths.
- Backend `tests/test_results_espn_nba_520.py`: saved ESPN scoreboards and summaries,
  US-date/DST boundaries, statuses, October season rollover, player stat strings,
  leaders, quarters, DNP, retries, pacing, 429 stops, malformed games, routing and
  isolated DB syncs proving stored boxes are never requested again. All HTTP uses
  `httpx.MockTransport`, with real transports blocked.
- Backend `tests/test_results_euroleague_519.py`: saved EuroLeague/EuroCup
  payloads, UTC dates, upcoming games, season rollover, complete season coverage,
  sponsored-name resolution, box scores/leaders/DNP, ranks, auth failures,
  bounded retries, pacing, 429 isolation, routing with a fake default and an
  in-memory DB sync proving stored detail is never fetched again. All HTTP uses
  `httpx.MockTransport`; no network or live DB is used.
- Backend `tests/test_results_health_522.py`: health on success, error, shape failure,
  a raising provider and a 429, per provider and per competition; failure count reset;
  a health-write failure that leaves the sync intact; the switch (not constructed, not
  called, synced and read through the default, bad names rejected); the read fallback
  with an injected clock (fresh, stale, back to fresh, never synced, no fresher default,
  threshold 0); one provider per competition; detail and consumer/admin view-as
  agreeing; backup sync (order, separate reporting, blocked default, rows hidden while
  healthy, TheSportsDB pacing and 429 stop over the backup); no-routes identity; the
  admin view and its auth.
- Frontend `src/components/results/*.test.js` (26): normalization, timezone/day
  formatting, grouping, and relevance/isolation (deriveFollows, filter,
  preference-change).

## 10. Known limitations

- The free provider tier returns a small bounded slice — a narrow follower may
  legitimately see 0 recent games (correct "no generic scoreboard" behavior).
  Because the season slice is the season's **first** 15 games, once a season
  is past them new games come only from `eventspastleague` (the single most
  recent game) and `eventsday` (up to 3 games per league per UTC day, so on a
  day with more games, such as an NBA night or a full football matchday, the rest
  are missed). Earlier games already stored are kept (upsert, never delete).
- A game stored while `live` or `scheduled` is refreshed only when a later
  sync returns it again. Games outside today/yesterday's 3-per-day slices can stay
  stale (on 2026-10-25 the DB held 36 past 2026-27 games still `live`,
  `scheduled` or `unknown`). The free `lookupevent.php?id=` could refresh them one
  request per game; not implemented.
- Team names the taxonomy doesn't know (e.g. an apostrophe'd club, a non-tracked
  visitor) fall back to the provider English name; such games are still relevant
  via a followed competition.
- Live in-play score streaming is out of scope (status supports `live` but sync
  is periodic, not a stream).

## 11. Per-game detail (issue #517)

**Status:** implemented behind `RESULTS_DETAIL_ENABLED` (default **false** in code and
`.env.example`). The Ligat Winner provider (section 12, #518), the official
`euroleague` provider (section 3, #519), `espn_nba` (section 13, #520), the
`bamboo` football provider (section 14, #521) and `RESULTS_PROVIDER=fake` return detail.
`/api/me/results` exposes it only with the flag on (§6, #523).
`game_results` is unchanged, so the page keeps working with scores only when a
detail source fails or has nothing.

### Storage

Two tables, both new and created by `create_all` (no `ALTER`):

- `game_details`, one row per game. Primary key `game_id` = the `game_results` id
  (`game_` + sha1(provider|external_id)); `provider` and `external_id` are unique
  together. Columns: `leaders` (JSON list of `{side, stat, value, source_player_id,
  name, name_he}`; at least the top scorer of each team, `stat` = `points` for
  basketball and `goals` for football, ties give one entry per tied player),
  `team_stats` (JSON `{"home": {...}, "away": {...}}`), `venue`, `attendance`,
  `fetched_at` (ISO UTC).
- `game_player_lines`, optional box-score rows: `game_id`, `side` (`home`/`away`),
  `source_player_id`, `name`, `name_he` (when the source has Hebrew), `minutes`
  (decimal minutes), `stats` (JSON with the source's own fields, so each sport and
  source can carry what it has: points, rebounds, goals, cards, ...).

2026-11-15 — #525: `results_player_mappings` maps `(provider, source_player_id)`
to a taxonomy **player** id, created by `create_all`. Detail upserts populate it in
the same transaction. `results/player_mapping.py` matches English/Hebrew display
names and aliases by unique exact normalized equality (Unicode normalization,
case, whitespace/punctuation and `LAST, FIRST` order). Ambiguous or unknown names
stay unmapped; no fuzzy matching or transliteration. Verified manual fixes belong
only in the provider-local `OVERRIDES` dict (currently empty).

Stored source names remain unchanged. `get_details` adds `entity_id` and
`display_name` to leaders and player lines: taxonomy Hebrew when mapped, otherwise
source Hebrew if present, otherwise the source name. Older cached details resolve
on read without writes or provider requests. A missing name remains missing; the
line/leader is kept. The optional pure resolver's team constraint is not applied
automatically, because current taxonomy rosters can differ from historical games.
No classification alias, feed decision, route or activation default changes.

`game_detail_repository.upsert` writes one game's detail and **replaces** its player
lines as a set, so the same detail written twice leaves one row set (updated, not
duplicated); the caller commits. `get_details(session, game_ids)` is the read function
(`{game_id: StoredGameDetail}`, ids without detail absent) for #523.

### Provider contract

`fetch(competition_ids) -> FetchOutcome` is unchanged. A provider may additionally
define `fetch_details(games: list[NormalizedGame]) -> DetailOutcome`
(`providers/base.DetailProvider`; detected with `supports_details`). Providers without
detail (TheSportsDB) just don't define it. `DetailOutcome` mirrors `FetchOutcome`:

- `details`: `NormalizedGameDetail` per game (leaders, players, team_stats, venue,
  attendance; identity = the game's `(provider, external_id)`);
- `errors`: game id → short error string (stored and served, so no URLs or keys);
- `not_checked`: game ids not requested because of a 429, plus
  `retry_after_seconds`;
- a requested game in none of these has no detail yet (for example, the box score is
  not published) and stays a candidate.

`models.leaders_from_lines(lines, stat)` derives per-team leaders from box-score lines
for sources that give a box score but no leaders (a side whose best value is not
positive, such as a football team that did not score, has no leader).

### Sync

With the flag on, `sync_results` runs `detail_sync.sync_details` after the scores are
upserted and committed, under the same lease:

1. Candidates are the provider's **own** games (`game_results.provider` = the
   provider's name) with status `final` and no `game_details` row, newest first, at
   most `RESULTS_DETAIL_MAX_PER_RUN` (default 10; 0 = no detail requests). The read
   transaction is closed before any request is sent.
2. **A stored detail is never fetched again**: a `game_details` row removes the game
   from the candidates for good. A game that errored or came back empty is asked
   again on a later run (still within the cap).
3. Details for games that were not requested (or duplicates) are ignored and
   counted.
4. Detail failures **never fail or roll back the scores sync** and never change its
   status: a raised exception, a per-game error or a database error ends up in the
   summary under `detail`: `{status, requested, stored, ignored, errors, not_checked,
   pending}`, where `status` is `ok`, `partial`, `error`, `rate_limited`,
   `unsupported` (provider has no detail capability) or `skipped_rate_limited` (the
   scores fetch was rate-limited, so no detail request is sent), and `pending` is
   how many candidates remain.
5. A detail `retry_after_seconds` sets `rate_limited_until` exactly like a scores 429,
   so the next sync of any caller waits.

With the flag off the stage does not run, the summary has no `detail` key, and the
sync sends exactly the requests it sent before.

The lease (stale after an hour) also covers the detail requests: each provider paces
them, and the per-run cap keeps one sync well inside that hour.

## 12. Ligat Winner provider (issue #518)

**Status:** implemented, **not switched on by default**: the tracked list and the routes
are unchanged (TheSportsDB has no league id for the cups), so nothing changes until the
owner sets the config below. Provider name `winner` (`providers/winner.py`).

**Sources** (the league's own public endpoints, no key, verified live 2026-11-15):

- Scores: `https://basket.co.il/ws/ws.asmx/Games?...&cYear=<ending year>...` returns the
  whole season of every competition in one response. One request per sync; the
  competitions asked for are filtered by `BOARD_ID` (5 `comp:ibl`, 10 `comp:winner_cup`,
  34 `comp:il_super_cup`). Future games are stored as `scheduled`. The season is the
  first of `RESULTS_SEASONS` (default: the current one); `cYear` is its ending year.
- Detail: Segev Stats `getBoxScore` and `getGameInfo` (names, Hebrew and English), two
  requests per game, plus one season-list request per run for the Segev id, venue
  (`PlaceOfGameHeb`) and attendance (`total_viewers`).

**Normalization.** `external_id` is the league's `game_id` (always present). Segev's
`ExternalID` is `0` until a game is set up there, so it cannot be the identity; it is
looked up at detail time. `team1` is home. Times are Israel local converted to UTC (a game
with no time yet is placed at local midnight). The list says `0`/`0` before a game, which
is read as no score (basketball has no 0-0). A half-readable score is no score. Names are
HTML-unescaped. `stage` is the round (`gameNumber`). Status is final when scored and in
the past, scheduled when in the future without a score.

**Teams.** The league lists clubs under sponsor names (`Maccabi Rapyd Tel Aviv`, `Hapoel IBI
Tel Aviv`) that the taxonomy aliases do not match, so the provider carries a local
name-to-team table (`CLUB_IDS`) for the clubs the generic resolver misses, and falls back
to the resolver (Hebrew, then English, always against `comp:ibl`: the cups' clubs are the
league's). A club the taxonomy lacks (Maccabi Rishon LeZion) keeps the provider name, so
that game is relevant only through a followed competition. The classifier's aliases were
deliberately not touched.

**Detail.** Player lines (Hebrew and English name, minutes, points, rebounds, assists,
steals, turnovers, blocks, shooting splits, fouls, plus/minus, rate, starter; players who
did not play are dropped), leaders by points via `leaders_from_lines`, team stats (points in
the paint, bench points, biggest lead, quarter scores, ...), venue, attendance. Segev gives
numbers as strings; they are cast defensively. A box score that is not final, or a game
Segev does not have yet, is not an error: it stays a candidate. A failed game-info request
is an error (so the names are retried rather than storing lines without them).

**Reliability.** Timeout, bounded retries for transient errors, requests spaced by
`RESULTS_WINNER_MIN_INTERVAL_SECONDS` (default 2; the league publishes no limit). A 429 is
not retried: scores mark the competitions `not_checked`, detail marks the unrequested games
`not_checked`, both with `retry_after_seconds` (60 when the header is absent). A malformed
payload or HTTP error is a short per-game or per-competition error with no URL. Per
competition at most `RESULTS_MAX_GAMES_PER_COMPETITION` games are kept: the nearest
upcoming ones (a quarter of the cap) and the newest results.

**How to switch on** (all in the live `.env`; the code default stays off):

```
RESULTS_PROVIDER_ROUTES=comp:ibl=winner,comp:winner_cup=winner,comp:il_super_cup=winner
RESULTS_COMPETITIONS=comp:nba,comp:euroleague,comp:eurocup,comp:ibl,comp:acb,comp:ligat_haal,comp:epl,comp:la_liga,comp:bundesliga,comp:ucl,comp:winner_cup,comp:il_super_cup
RESULTS_DETAIL_ENABLED=true
```

Games already stored for `comp:ibl` by TheSportsDB stay as rows of that provider (a
different identity), so the page can show both until the old rows age out of the read
window; check for duplicate Ligat Winner games after switching.

**Relevance of the cups.** With detail enabled, #523's read service expands an IBL
competition follow to Winner Cup and Supercup (§6), including games between clubs
not followed individually. The feed taxonomy/classifier and affinities are unchanged.
With the flag off the legacy exact competition rule remains.

## 13. NBA via ESPN (issue #520, opt-in)

**Status:** implemented as `espn_nba.ESPNNBAProvider`, registered as `espn_nba`,
serving only `comp:nba`. Existing defaults remain TheSportsDB, empty routes and
detail off. No UI, API output, Hebrew player mapping or taxonomy aliases change.

**Activation** (owner opt-in; production activation requires the duplicate-free
read rule from #532, section 3, now implemented):

```dotenv
RESULTS_PROVIDER_ROUTES=comp:nba=espn_nba
RESULTS_DETAIL_ENABLED=true
```

Combine these entries with any existing routes. The existing scheduler/manual
sync populates data; reading results sends no requests. Clear the NBA route to
roll back to the default provider's stored rows; no rows are deleted.

**Source and dates.** ESPN's public, unofficial and undocumented endpoints need
no key. Scoreboards use
`https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=YYYYMMDD`.
There is one request per date from `RESULTS_ESPN_DAYS_BACK` (default 1, at most
14) days before today through `RESULTS_ESPN_DAYS_AHEAD` (default 3, at most 7)
days after today, inclusive. Today is the **America/New_York** calendar date,
with DST, rather than the worker's or Israel's date. Tip-off always comes from
`events[].date`, converted to UTC: the 13 November US Portland/Sacramento game
starts `2026-11-14T03:00:00+00:00`, on 14 November in Israel. Season labels
roll over in October (`2026-2027`); identity is ESPN's event id, scoped to the
provider. TheSportsDB's season settings and game cap do not truncate this short
date window.

`post` plus `completed=true` means `final`, `pre` means `scheduled`, and `in`
means `live`; explicit postponed/cancelled statuses are retained. Scores are set
only for final games with both scores readable. Home/away comes from `homeAway`,
never array order. The existing competition-scoped resolver knows the NBA team
display names; an unresolved name remains the source name with a null team id.

**Detail.** One
`https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=<id>`
request per final candidate. Source player ids and English names are kept;
`MIN` becomes decimal minutes, and `stats` retains label-keyed strings (including
`FG="11-13"`, `FT="9-9"`, `+/-="+11"`) plus integer `points`, `rebounds`,
`assists` and a `starter` boolean. Players with `didNotPlay=true` are skipped;
an otherwise present `DNP` minute string becomes null. Points/rebounds/assists
leaders are derived with `leaders_from_lines`, preserving ties, with scoreboard
leaders available as fallback. Native team stats are keyed by their ESPN names;
each side's `quarters` includes overtime periods. Scoreboard quarters are carried
into detail during the same provider run; for older stored games they come from
the summary header. Venue and attendance come from `gameInfo`.

The existing stage (section 11) caps detail requests and **never re-fetches stored
detail**, including across provider instances and process restarts. Daily
scoreboards are still refreshed to discover schedule/status changes. An empty
or unfinished box stays pending. A mismatched or malformed box, including
incomplete team lines, is a per-game error and remains retryable on the next
sync; scores are preserved. Malformed optional scoreboard detail leaves scores
available. No NBA CDN or stats.nba.com endpoints are used.

**Reliability.** HTTPX accepts gzip/deflate, with shared timeout
`RESULTS_HTTP_TIMEOUT_SECONDS` and bounded transient retries
(`RESULTS_HTTP_MAX_RETRIES`). All ESPN calls, including retries, share
`RESULTS_ESPN_MIN_INTERVAL_SECONDS` (default 2 seconds; courtesy spacing, no
published limit), and send `User-Agent: signal-sports-results/1.0`. Permanent
HTTP failures and malformed JSON are not retried in the same call. A 429 is
never retried: it stops scoreboards (`comp:nba` is `not_checked`) or marks the
remaining detail games `not_checked`, with Retry-After (seconds or HTTP date;
60 seconds if absent/invalid). Existing provider-specific sync blocks apply.
Error strings are short and URL-free. A source change can therefore leave
scores usable while detail fails; no LLM or paid source is involved.

## 14. Israeli Premier League via Bamboo (issue #521)

2026-11-15 — implemented as `BambooFootballProvider`, registered as `bamboo`.
Only `comp:ligat_haal` is supported; other competitions get an error entry.
Routes remain empty and detail remains off by default. To opt in, keep the
default provider for other competitions and set:

```dotenv
RESULTS_PROVIDER_ROUTES=comp:ligat_haal=bamboo
RESULTS_DETAIL_ENABLED=true
```

Combine this route with any existing entries in the same comma-separated value.
Production activation requires #532's provider filtering to be deployed: reads
then show only the currently routed provider's games, preserving old TheSportsDB
rows without showing duplicates. This change does not enable any live flags.
Rollback removes the Bamboo route; disabling detail stops all detail requests.

**Source and scores.** The public football.co.il Bamboo CDN, no key:
`https://cdnapi.bamboo-cloud.com/api/football/{game|team|stats|player|standings}`,
always with `format=json&iid=573881b7181f46ae4c8b4567`. One `game` request per
sync; one `team` request per provider instance, shared with detail. The source
returns its current season, not an archive selected by `RESULTS_SEASONS`.
`external_id` is the source game id; `26/27` becomes `2026-2027`, `stage` is the
round. `date.sec` supplies the UTC timestamp even when `stringDate` is a range
and `hour` is absent; that timestamp does not establish a confirmed kickoff for
an upcoming fixture. Status 3 is final (including 0–0), 2 live, 4 postponed/to
be decided, null with a future date scheduled; other cases are unknown. Only
final/live games retain scores. Bad rows do not lose other games. The existing
`RESULTS_MAX_GAMES_PER_COMPETITION` cap applies: up to a quarter goes to the
nearest upcoming games and the rest to the newest results, as for Winner.

**Teams.** Display names prefer `hebrewName`; ids use `resolve_team` scoped to
`comp:ligat_haal`, Hebrew then English. In the saved 14-club season, nine clubs
resolve. Five have no taxonomy entity: Kiryat Shmona, Bnei Sakhnin, Hapoel Ramat
Gan, Hapoel Petah Tikva and Ironi Tiberias. They retain Hebrew names and null
canonical ids, so they remain relevant through a competition follow. No new
taxonomy entities or aliases were added; article classification is unchanged.

**Detail.** One `stats?filter={"gameId":N}` request per finished candidate,
plus one `player?filter={"id":N}` lookup per new player id, cached for the
provider instance (including missing/failed names). Player lines retain Hebrew
first/last names, Latin name, minutes, `goals`, `assists`, `yellow_cards`,
`red_cards`, `own_goals` and `xg`. Side comes from the stats key's team id,
never a player's current profile team. A missing or failed player lookup keeps
the line without a name and does not prevent storage.

The saved real payload corrects an assumption in the implementation brief:
**`playerId=-1` rows repeat each team's totals**, including goals, cards and xG.
They are stored once in `team_stats.home` / `.away`, not added as player goals.
Any positive gap between those totals and named player counts becomes an unnamed
line (and an unnamed scorer for a goal gap). No player lookup is made for -1.
For saved game 310793, the four scorers are Sokler and Jehezkel for Maccabi Tel
Aviv, Tibi and Hadida for Petah Tikva, matching the 2–2 result. This handling and
the five unresolved clubs were confirmed by Guy during implementation.
Leaders include **every** player with a positive goal count, even when another
player scored more, plus unnamed goal gaps. No goal minutes are invented, and
no licensed Opta widgets or endpoints are used.

Team red-card counts use the totals once (or the sum of player rows if no total
exists). A single optional `standings` lookup per provider instance stores
`position` as each side's `rank`; this is the source's current table, not a
historical round rank. Venue matches the game's `stadiumId` against expanded
team stadiums, preferring Hebrew. A fresh detail-only provider loads one season
response and teams for metadata if needed. Empty stats or a game no longer final
remain pending. Malformed stats are per-game errors; later games still proceed.

**Reliability and request volume.** All endpoints and retries share the same
httpx client within a call, timeout (`RESULTS_HTTP_TIMEOUT_SECONDS`), honest
`signal-sports-results/1.0` User-Agent and pacing
(`RESULTS_BAMBOO_MIN_INTERVAL_SECONDS`, default 2). Transient HTTP failures and
timeouts retry at most `RESULTS_HTTP_MAX_RETRIES`; permanent HTTP errors do not
retry and report short, URL-free messages. A 429 is never retried: it stops all
further requests, propagates `not_checked` and Retry-After (60 seconds if absent
or invalid), and uses the existing provider-specific sync block. If optional
standings is rate-limited, already completed player detail is kept without rank.
Other standings failures are cached without losing detail. The existing detail
stage caps work with `RESULTS_DETAIL_MAX_PER_RUN` and never re-fetches a stored
finished detail; the season list continues to refresh scores and schedules.

**Tests.** `tests/test_results_bamboo_521.py` uses trimmed saved payloads under
`tests/fixtures/results/ligat_haal`, `httpx.MockTransport` and a real-transport
block. It covers normalization, all 14 club names, scorer/totals/gap semantics,
team-from-key transfers, missing names, cards, ranks, venue, retries, pacing,
429 isolation, malformed games, routing, client ownership, and isolated DB
syncs with detail on/off. A second sync requests only scores/teams, never stored
detail or player names. No API output (#523), UI, health UI (#522), player mapping
(#525), LLM or feed-policy changes are included.

## 15. Provider health, switch and fallback (issue #522)

2026-11-15. Nothing changes while `RESULTS_PROVIDER_ROUTES` is empty: the sync calls
the plain default provider exactly as before, the summary has the same keys, and
reads ignore health. Health rows are still written for the default provider.

### Health (`results_provider_health`)

Every sync records the scores fetch per provider and per competition it asked that
provider for, plus one provider-level row (`competition_id = "*"`). Columns:
`last_attempt_at`, `last_success_at`, `last_status`, `last_error` (short, URL-free:
the provider's own error string or the exception class name), `last_error_at`,
`consecutive_failures`, `shape_failures` (cumulative). Per competition:

- the provider raised: `error` with the class name;
- in `not_checked` (a 429 stopped it): `rate_limited`. That is not a source failure,
  so the failure count and `last_success_at` are unchanged;
- in `errors`: `error`. When the error names a parse/shape exception
  (`MalformedResponse`, `ValueError`, `TypeError`, `KeyError`, `AttributeError`,
  `IndexError`, `JSONDecodeError`, `ValidationError`) it also counts as a shape
  failure. This reads the providers' own error strings, so it classifies what they
  report; it is not a separate parser check;
- otherwise `ok` (the provider answered for it, even with zero games), which resets
  the failure count.

The provider row is `ok`, `partial` (some competitions failed), `error` (none
succeeded; the failure count goes up) or `rate_limited`. A blocked provider is not
called and not recorded. The current block is not duplicated here: it is
`rate_limited_until_by_provider` in the sync summary (§3). Health is written after
the scores are committed, in its own commit. If it fails it is rolled back and
logged, and the summary gets `health_error` (class name). It never fails, rolls back
or re-statuses the scores sync. The detail stage (§11) is not part of health yet.

### Switch: `RESULTS_PROVIDER_DISABLED`

Comma-separated provider names (case-insensitive). A disabled provider is not
constructed or called; its routed competitions are synced by `RESULTS_PROVIDER` and
read from its rows. With every route disabled, `get_provider()` returns the plain
default provider. An unknown name, or the default provider itself, raises
`ValueError` at API startup; a sync with a bad value records `status=error`, and
reads fall back to the default provider with a warning (the same handling as a bad
route).

### Read-time fallback: one provider per competition

`providers.active_provider_map(session, now=...)` (and `active_provider_for`) decides,
per routed competition, the one provider whose rows are served (`health.decide`, pure):

1. provider disabled: the default (`disabled`);
2. `RESULTS_PROVIDER_STALE_HOURS` is 0: the route (the #532 rule alone);
3. the routed provider succeeded for **this competition** within the threshold
   (default 6 hours, measured at `now`): the route (`routed`);
4. it never succeeded for it: the default (`never_succeeded`);
5. it is stale: the default (`stale`) when the default provider succeeded for this
   competition more recently, else the route (`stale_no_fallback`). A competition
   the default cannot serve (for example a cup TheSportsDB has no league id for) so
   keeps its last rows instead of showing an empty list.

Only the last success counts: errors after a fresh success do not switch early, and a
success for another competition does not count. `game_result_repository.list_games`
then filters each competition to exactly that provider, so two providers' rows are
never mixed. `personalized_results` (consumer `/api/me/results` and admin view-as)
and `service.visible_details` (the detail lookup for #523) use the same call. If the
health table cannot be read, reads use the default provider and log.

### Backup sync: `RESULTS_PROVIDER_BACKUP_SYNC` (default true)

With routes set, the routing provider also asks the default provider for every routed
competition, in the same `fetch` call and **after** its own competitions. Its pacing
and its 429 stop therefore cover the backup requests, and a 429 costs the backup
first. Backup games are stored under the default provider's identity and stay hidden
while the route is healthy (rule 3). The routed (serving) view in the summary
(`errors`, `fetched_counts`, `not_checked`) is unchanged; the backup is reported
apart under `backup: {provider, competitions, fetched_counts, errors, not_checked}`.
A backup 429 still blocks the default provider (§3). The scores status counts every
stored game, so a sync where every routed provider failed but the backup returned
games is `partial`, not `error`.

**Request volume (TheSportsDB).** One sync makes 1 + S + D requests per competition
it has a league id for (S = seasons in `RESULTS_SEASONS`, D = `RESULTS_RECENT_DAYS`,
§3), 7 s apart. With the production config documented in §3 (one season, two days,
so 4 per competition) and the 10 tracked competitions:

| Setup | TheSportsDB requests per sync | Per day (at most 48 syncs, 30-minute throttle) |
|---|---|---|
| No routes (production today) | 40 (about 4.6 minutes) | at most 1,920 |
| 5 routes (NBA, EuroLeague, EuroCup, IBL, Ligat ha'Al), backup off | 20 | at most 960 |
| The same 5 routes, backup on | 40 | at most 1,920 |

The backup adds 4 requests per routed competition per sync (20 per sync, at most 960
a day for those five routes) compared with routing without it, and nothing compared
with today. With the code defaults (two seasons, no days) it is 3 per competition: 30
per sync with the backup, 15 without it for those five routes. The rate stays at most
8.6 a minute, under the documented 30 a minute; the repository's notes record no
daily limit. Competitions TheSportsDB has no league id for (`comp:winner_cup`,
`comp:il_super_cup`) cost no request: they record a backup error and fall under
rule 5. `RESULTS_PROVIDER_BACKUP_SYNC=false` turns the backup off.

### Ops view

`GET /api/results/sync/state` (admin only, read-only) adds `health`:

```json
{
  "default_provider": "thesportsdb", "stale_hours": 6, "backup_sync": true,
  "config_error": null,
  "providers": [{"provider": "euroleague", "is_default": false, "enabled": true,
                 "rate_limited_until": null, "last_attempt_at": "...",
                 "last_success_at": "...", "last_status": "error",
                 "last_error": "HTTP 503", "last_error_at": "...",
                 "consecutive_failures": 3, "shape_failures": 0}],
  "competitions": [{"competition_id": "comp:euroleague", "routed_to": "euroleague",
                    "serving": "thesportsdb", "reason": "stale",
                    "freshness": {"euroleague": {"last_success_at": "...", "age_hours": 7.5,
                                                 "last_status": "error", "consecutive_failures": 3},
                                  "thesportsdb": {"last_success_at": "...", "age_hours": 0.4,
                                                  "last_status": "ok", "consecutive_failures": 0}}}]
}
```

`reason` is `default` (not routed), `routed`, `disabled`, `never_succeeded`, `stale` or
`stale_no_fallback`. No frontend page reads this endpoint today; the ops UI that shows
it follows on `ui/next`.
