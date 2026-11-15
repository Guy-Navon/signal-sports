# Personalized Results — Contract (issue #178)

**Status:** implemented and merged (#178, PR #179, 2026-08-23). The production `.env` runs
`RESULTS_SYNC_ENABLED=true`, so the worker refreshes results every 30 minutes at most.
This is the authoritative contract for the Results feature; where another doc
disagrees, this wins for results behavior.

2026-11-15 — issue #517: per-game detail storage (`game_details`,
`game_player_lines`), an optional provider detail capability and a sync stage,
behind `RESULTS_DETAIL_ENABLED` (default off). See §11. No API or UI change yet
(#523, #513).

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

**Read rule (#532).** Reads show, per competition, only rows whose `provider` equals the provider that competition is currently routed to (the route, else `RESULTS_PROVIDER`): `providers.active_provider_for(competition_id)` / `active_provider_map()`, applied in `game_result_repository.list_games(active_providers=...)` by `results.service.personalized_results` (consumer and admin view-as share it). Older rows of the same games from a previous provider are not shown as duplicates; nothing is deleted, and switching a route back shows them again. Detail lookups use only the ids that pass. With no routes every row belongs to the default provider, so output is unchanged. A bad route config on the read path logs a warning and falls back to the default provider instead of failing. The demo exporter does not read results.

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
way by `create_all`.

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
`RESULTS_SYNC_ENABLED=false` (no data touched). `RESULTS_DETAIL_ENABLED` and
`RESULTS_DETAIL_MAX_PER_RUN` control the detail stage (§11).

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
- Backend `tests/test_results_euroleague_519.py`: saved EuroLeague/EuroCup
  payloads, UTC dates, upcoming games, season rollover, complete season coverage,
  sponsored-name resolution, box scores/leaders/DNP, ranks, auth failures,
  bounded retries, pacing, 429 isolation, routing with a fake default and an
  in-memory DB sync proving stored detail is never fetched again. All HTTP uses
  `httpx.MockTransport`; no network or live DB is used.
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
`euroleague` provider (section 3, #519) and `RESULTS_PROVIDER=fake` return detail.
Other real providers are added by #520 and #521. `/api/me/results` does not expose it yet
(#523). `game_results` is unchanged, so the page keeps working with scores only when a
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

Player identity is the **source's** player id and name; mapping to taxonomy players is
#525. A name may be missing when the source has the id but no name record: the line
or leader is kept, not dropped.

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

**Relevance of the cups.** Results relevance (`relevance.py`) matches the competition
exactly; it does not follow the taxonomy `parent`. A profile that follows `comp:ibl` is
therefore **not** shown `comp:winner_cup` or `comp:il_super_cup` games between unfollowed
clubs (only the games of a followed team). Not changed in #518.
