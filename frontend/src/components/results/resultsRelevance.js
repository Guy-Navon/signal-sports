// Client-side results relevance (issue #178) — LOCAL data mode only.
//
// In backend mode the server is the sole authority (it filters before the API
// returns). This mirror exists so the offline/local demo mode and the unit
// tests can exercise the exact same rules: a game is relevant when either team
// is followed, a followed player's team plays, or the competition is followed.

// Minimal display→id maps for the local mock corpus (data, not per-user logic).
const LEAGUE_TO_COMP = {
  NBA: "comp:nba",
  EuroLeague: "comp:euroleague",
  EuroCup: "comp:eurocup",
  "Israeli Basketball League": "comp:ibl",
  "Spanish ACB": "comp:acb",
};

const ENTITY_TO_TEAM = {
  "Maccabi Tel Aviv Basketball": "team:maccabi_tlv_bb",
  "Oded Katash": "team:maccabi_tlv_bb",
  "Deni Avdija": "team:portland_blazers", // followed player → his current team
};

// Derive followed { teamIds, competitionIds } from a local userProfiles profile.
export function deriveFollows(profile) {
  const competitionIds = new Set();
  const teamIds = new Set();
  for (const topic of profile?.topics ?? []) {
    const broadLeagueFollow =
      (topic.scope === "league" || topic.scope === "league_group") &&
      topic.mode === "all";
    if (broadLeagueFollow) {
      for (const league of topic.leagues ?? []) {
        const comp = LEAGUE_TO_COMP[league];
        if (comp) competitionIds.add(comp);
      }
    }
  }
  for (const entity of profile?.followedEntities ?? []) {
    const team = ENTITY_TO_TEAM[entity];
    if (team) teamIds.add(team);
  }
  return { teamIds, competitionIds };
}

export function isRelevant(game, follows) {
  const { teamIds, competitionIds } = follows;
  if (game?.home?.id && teamIds.has(game.home.id)) return true;
  if (game?.away?.id && teamIds.has(game.away.id)) return true;
  if (game?.competitionId && competitionIds.has(game.competitionId)) return true;
  return false;
}

export function filterRelevant(games, follows) {
  return games.filter((g) => isRelevant(g, follows));
}

export function hasAnyFollows(follows) {
  return follows.teamIds.size > 0 || follows.competitionIds.size > 0;
}
