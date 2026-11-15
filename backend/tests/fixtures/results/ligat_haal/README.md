# Bamboo football fixtures

Saved public CDN payloads captured on 2026-11-15 for issue #521. No HTTP is
performed by tests. `game_2627.json` retains round 1 (all 14 clubs), game 310793
and the upcoming game 310803; other files retain the fields used by the adapter.
Player records preserve their source team id for the transfer regression case.

The original `stats_game_310793.json` contains 42 rows: 40 player rows and two
`-1` team-total rows. Both teams total two goals. The actual named home scorers
are Ester Sokler and Sagiv Jehezkel; away scorers are Eitan Tibi and Guy Hadida.
The `-1` rows repeat goals/cards/xG rather than adding unattributed goals. Tests
also remove a named scorer to exercise an unnamed gap without doubling totals.

Endpoints are `https://cdnapi.bamboo-cloud.com/api/football/<endpoint>` with
`format=json&iid=573881b7181f46ae4c8b4567`; stats use `filter={"gameId":310793}`,
player uses `filter={"id":N}`. No Opta endpoint was used. Payloads omit unrelated
fields, including Opta ids; fixture capture is never part of a test run.
