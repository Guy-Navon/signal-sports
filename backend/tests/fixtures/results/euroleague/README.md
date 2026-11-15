# Official EuroLeague / EuroCup fixtures (#519)

Real payloads captured on 2026-11-15; no fixtures are fetched during tests.

- `v2_games_E2026.json`: copied from the issue brief's saved payload, trimmed to
  three complete rows (two played games and an upcoming game).
- `live_boxscore_E2026_103.json`: copied unchanged from the brief; Maccabi Rapyd
  Tel Aviv 80-73 Hapoel IBI Tel Aviv, 2026-11-12, round 11.
- `v2_games_U2026.json`: two complete rows (played/upcoming), trimmed from
  `https://api-live.euroleague.net/v2/competitions/U/seasons/U2026/games`.
- `live_boxscore_U2026_103.json`: full response from
  `https://live.euroleague.net/api/Boxscore?gamecode=103&seasoncode=U2026`.
- `v3_standings_E2026_round11.json`: full response from
  `https://api-live.euroleague.net/v3/competitions/E/seasons/E2026/rounds/11/basicstandings`.
- `v3_standings_U2026_round7.json`: full response from
  `https://api-live.euroleague.net/v3/competitions/U/seasons/U2026/rounds/7/basicstandings`.

Four GETs captured the extra fixtures, at least seven seconds apart, with
`User-Agent: signal-sports-results/1.0 (fixture capture for issue 519)`.
The trimmed season files' `total` values reflect the saved subset.
