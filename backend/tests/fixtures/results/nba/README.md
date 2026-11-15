ESPN NBA responses saved on 2026-11-15, supplied with issue #520's brief.

- `espn_scoreboard_YYYYMMDD.json`: NBA `scoreboard?dates=YYYYMMDD`, a US date.
  Retains every event's identity, UTC date, status, competitors, quarter scores
  and leaders; removes unrelated statistics, links and presentation metadata.
- `espn_summary_<id>_<teams>.json`: NBA `summary?event=<id>`. Retains only
  `boxscore`, `gameInfo` and `header`, with links/images/branding removed.

Base URL: `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/`.
Tests only read these files and use `httpx.MockTransport`; no network requests.

The Portland/Sacramento payload has Deni Avdija at 34 points, 11-13 FG,
9-9 FT, 6 rebounds, 4 assists and +11. Sacramento's top scorer is De'Andre
Hunter (24), while Domantas Sabonis has 21 points and 12 rebounds. Both the
scoreboard and summary agree; the brief incorrectly calls Sabonis the top scorer.
