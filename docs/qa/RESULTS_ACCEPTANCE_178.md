# Results feature — acceptance evidence (issue #178)

Live acceptance run against a **real uvicorn** on a fresh temp DB with the
**real TheSportsDB provider** (network), 2026-07-19.

## Setup

```
DATABASE_URL=sqlite:///<scratch>/acc.db
RESULTS_PROVIDER=thesportsdb   RESULTS_SYNC_ENABLED=false
ALLOW_INSECURE_AUTH_BYPASS=true (admin-surface steps only)
uvicorn app.main:app --host 127.0.0.1 --port 8099
GET /health -> {"status":"ok","service":"signal-sports-backend"}
```

## 1. Real sync against TheSportsDB

```
POST /api/results/sync
-> status ok  fetched 55  created 55  updated 0
   per-competition: nba 11, euroleague 11, eurocup 11, ibl 11, acb 11
   errors: {}
```

## 2. Idempotency (repeated sync creates no duplicates)

```
POST /api/results/sync (again)
-> created 0  updated 55        # same 55 rows updated in place, zero new rows
```

## 3. Personalization + "not a generic scoreboard" (admin view-as, real data)

```
GET /api/results/guy
-> has_preferences True, total 24
   by competition: {Israeli Basketball League 6, NBA 6, EuroLeague 6, EuroCup 6}
   ACB present? False        # Guy de-prioritizes comp:acb (-1) -> excluded
   e.g. NBA  סן אנטוניו ספרס 90-94 ניו יורק ניקס [final]   (real NBA Finals 2026)
        EuroLeague אולימפיאקוס 92-85 ריאל מדריד [final]

GET /api/results/casual_deni_fan
-> has_preferences True, total 0    # the free-tier NBA slice had no Portland
                                    # game; a narrow follower correctly sees
                                    # nothing rather than a flood — the anti-
                                    # scoreboard guard working on real data.
```

## 4. Server-side isolation via the real consumer path (two real login sessions)

Two freshly signed-up `role=user` accounts, each declaring one interest through
`PUT /api/me/interests`, then `GET /api/me/results`:

```
User A follows EuroLeague -> has_preferences True, 6 games, comps {comp:euroleague}
   אולימפיאקוס 92-85 ריאל מדריד (win=home)
   פנאתינייקוס 87-79 באיירן מינכן (win=home)
User B follows IBL        -> has_preferences True, 6 games, comps {comp:ibl}
   הפועל תל אביב 79-83 מכבי תל אביב (win=away)
   הפועל תל אביב 97-82 עירוני קריית אתא (win=home)

disjoint game sets?  True
A sees only EuroLeague?  True   |   B sees only IBL?  True
```

Real taxonomy Hebrew names resolved from provider English (`Real Madrid
Baloncesto` → `ריאל מדריד`, `Maccabi Tel Aviv BC` → `מכבי תל אביב`); an
unmapped club (`Hapoel Be'er Sheva BC`) falls back to the provider name — a game
still relevant via the followed competition. A preference change (different
follows) produces disjoint visible results — proving relevance is server-side.

## 5. Provider-failure resilience

Sync pointed at an unreachable host (`nonexistent-host.invalid`,
`RESULTS_HTTP_MAX_RETRIES=0`):

```
results fetch failed for comp:nba/euroleague/eurocup/ibl/acb: getaddrinfo failed
sync status: error   errors: [all 5 competitions]   (no exception raised)
games in DB before: 55  after failed sync: 55        (read path unaffected)
GET /api/results/guy -> total games 24               (page still serves)
```

## 6. Automated tests

```
backend  pytest tests/test_results_178.py             -> 39 passed
backend  full suite (pre-existing 2400 + results)      -> 2400+39 passed, 1 skipped
         (authz inventory updated for the 4 new routes)
frontend vitest src/components/results                 -> 26 passed
frontend full suite                                    -> 449 passed (423 baseline + 26)
frontend npm run build                                 -> built OK
frontend npm run lint (new files)                      -> clean
```

## Acceptance checklist (issue #178)

- [x] Real personalized results render (live API returns real games)
- [x] Home/away, score, competition, date/time (UTC stored, Asia/Jerusalem shown), status
- [x] Winner distinguished (computed `winner` + `is_winner`)
- [x] Chronological grouping (frontend `groupByDay`, newest first)
- [x] Loading / error / no-preferences / no-relevant-results states
- [x] Server-side relevance + isolation (two real sessions, disjoint results)
- [x] Idempotent sync (created 0 on repeat)
- [x] Unrelated games excluded (ACB absent for Guy)
- [x] Provider failure handled (captured, read path unaffected)
- [x] Migrations from clean + existing DB (`create_all` new tables)
- [x] Tests / lint / build pass

## Note on browser/mobile evidence

The frontend test stack is Vitest in a **node** environment (no DOM renderer),
so mobile/RTL is covered by the responsive Tailwind layout (`grid sm:grid-cols-2`,
`max-w-3xl`, logical RTL utilities) plus the pure logic tests, and the
production build passing — consistent with the repo's existing test conventions.
