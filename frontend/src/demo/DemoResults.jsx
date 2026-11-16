import React, { useCallback } from "react";
import ResultsBoard from "@/components/results/ResultsBoard";

const EMPTY_DETAILS = {};

// Same results UI as the product; all detail reads come from the static snapshot.
export default function DemoResults({ games = [], teamGames = null, followedTeamIds = [], details = EMPTY_DETAILS, nowMs = Date.now() }) {
  const getDetail = useCallback(async (gameId) => {
    if (!Object.hasOwn(details, gameId)) throw new Error("Game detail unavailable");
    return details[gameId];
  }, [details]);
  return <ResultsBoard games={games} teamGames={teamGames} followedTeamIds={followedTeamIds}
    hasPreferences getDetail={getDetail} nowMs={nowMs} readOnly />;
}
