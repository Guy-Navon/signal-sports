import React from "react";
import GameDetailDialog from "@/components/results/GameDetailDialog";
import "@/components/results/results-board.css";

// Lazy entry for the feed's results strip: the same box score the results page opens.
export default function StripGameDetail(props) {
  return <GameDetailDialog {...props} />;
}
