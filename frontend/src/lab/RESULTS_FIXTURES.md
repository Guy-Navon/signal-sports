# Results lab fixture provenance

`resultsFixtures.json` is an offline projection of the existing saved provider
payloads through their real normalizers, detail storage, exact player mapping and
the results API read model. No source requests or production database were used.
It is imported only by the private design lab, never the public demo.

- Winner: `backend/tests/fixtures/results/winner/segev_440_{boxscore,gameinfo}.json`
  and `ws_games_2027_sample.json`: Maccabi–Hapoel **87–105**, 1 November 2026.
- EuroLeague: `backend/tests/fixtures/results/euroleague/live_boxscore_E2026_103.json`,
  saved season and standings: Maccabi–Hapoel **80–73**, 12 November 2026.
- ESPN: `backend/tests/fixtures/results/nba/espn_summary_401909303_POR_SAC.json`
  and its scoreboard: Sacramento home **107–120** Portland, 14 November in Israel.
  Deni's actual **34 PTS / 6 REB / 4 AST** line and the source's shooting strings
  are preserved. The stored payload, rather than an invented score, is authoritative.
- Bamboo: `backend/tests/fixtures/results/ligat_haal/`: Maccabi Tel Aviv–Maccabi
  Petah Tikva **2–2**, 6 November, with Sokler/Jehezkel and Tibi/Hadida. Team-total
  rows are not added to individual scorers.
- The upcoming Winner game is the saved season's Segev id 452 on 15 November.
  The lab clock is fixed to `2026-11-15T12:00:00Z`; original dates/times are retained.

Rows and popup alternatives: `npm run lab`, then
`http://127.0.0.1:5182/lab.html?page=results`. Query parameters `layout=one-line`
and `popup=side` link directly to the alternatives. `state` selects loading,
error, preferences, empty or unavailable examples.
