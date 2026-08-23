import React from "react";
import { cn } from "@/lib/utils";
import { RESULT_STATUS, statusLabel, hasScore } from "./resultsModel";
import { formatGameTime } from "./resultsFormat";

// One game as a compact, low-noise card. The winner of a completed game is
// distinguished by a bold name + a green (signal-high) score; nothing else
// shouts. Non-completed games show their status and (for scheduled) tip-off time.
function TeamRow({ team, isWinner, showScore, dimmed }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span
        className={cn(
          "min-w-0 truncate text-[15px]",
          isWinner ? "font-bold text-foreground" : "font-medium",
          dimmed ? "text-text-secondary" : "text-foreground"
        )}
      >
        {team.name}
      </span>
      {showScore && (
        <span
          className={cn(
            "flex-shrink-0 tabular-nums text-[15px]",
            isWinner ? "font-bold text-signal-high" : "font-semibold text-text-secondary"
          )}
        >
          {team.score ?? "—"}
        </span>
      )}
    </div>
  );
}

const STATUS_TONE = {
  [RESULT_STATUS.LIVE]: "text-signal-push",
  [RESULT_STATUS.POSTPONED]: "text-signal-push",
  [RESULT_STATUS.CANCELLED]: "text-signal-hidden",
};

export default function ResultCard({ game }) {
  const completed = hasScore(game) && game.status === RESULT_STATUS.FINAL;
  const scheduled = game.status === RESULT_STATUS.SCHEDULED;
  const time = formatGameTime(game.startTime);
  const showScore = hasScore(game);
  const label = statusLabel(game.status);

  return (
    <article
      className={cn(
        "rounded-xl border border-border/60 bg-surface-1/40 px-4 py-3",
        "transition-colors hover:bg-surface-1/70"
      )}
    >
      <div className="mb-2 flex items-center justify-between gap-2 text-[11px]">
        <span className="min-w-0 truncate font-medium text-text-dim">
          {game.competitionHe}
          {game.stage ? <span className="text-text-dim/60"> · {game.stage}</span> : null}
        </span>
        <span
          className={cn(
            "flex flex-shrink-0 items-center gap-1.5 font-medium",
            STATUS_TONE[game.status] || "text-text-dim"
          )}
        >
          {game.status === RESULT_STATUS.LIVE && (
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-signal-push" />
          )}
          {scheduled && time ? time : label}
        </span>
      </div>

      <div className="space-y-1.5">
        <TeamRow
          team={game.home}
          isWinner={completed && game.winner === "home"}
          showScore={showScore}
          dimmed={completed && game.winner === "away"}
        />
        <TeamRow
          team={game.away}
          isWinner={completed && game.winner === "away"}
          showScore={showScore}
          dimmed={completed && game.winner === "home"}
        />
      </div>
    </article>
  );
}
