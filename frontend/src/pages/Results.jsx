import React, { useCallback } from "react";
import { useApp } from "@/context/AppContext";
import { getMeResultsGameDetail, getResultsGameDetail } from "@/api/client";
import ResultsBoard from "@/components/results/ResultsBoard";

export default function Results() {
  const { resultsGames, resultsHasPreferences, resultsLoading, resultsError, refreshResults,
    isBackendMode, consumerSession, qaSurfaceAllowed, activeProfileId, activeProfile } = useApp();
  const detail = useCallback((gameId) => {
    if (!isBackendMode) return Promise.reject(new Error("detail unavailable offline"));
    return consumerSession && !qaSurfaceAllowed ? getMeResultsGameDetail(gameId) : getResultsGameDetail(activeProfileId, gameId);
  }, [isBackendMode, consumerSession, qaSurfaceAllowed, activeProfileId]);
  // A QA identity change unmounts its popup, so another profile cannot retain it.
  return <ResultsBoard key={activeProfileId} profile={activeProfile} games={resultsGames || []} hasPreferences={resultsHasPreferences}
    loading={resultsLoading} error={resultsError} onRetry={refreshResults} getDetail={detail} />;
}
