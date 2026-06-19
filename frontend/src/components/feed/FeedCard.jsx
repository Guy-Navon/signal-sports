import React, { useState } from "react";
import { ExternalLink, ThumbsUp, ThumbsDown, Clock, ChevronDown, ChevronUp } from "lucide-react";
import DecisionBadge from "./DecisionBadge";
import { useApp } from "@/context/AppContext";
import { formatDistanceToNow } from "date-fns";
import { he } from "date-fns/locale";

const CARD_STYLES = {
  push: "border-amber-500/40 bg-amber-500/5 hover:border-amber-500/60",
  high_feed: "border-emerald-500/30 bg-emerald-500/5 hover:border-emerald-500/50",
  feed: "border-gray-700 bg-gray-900 hover:border-gray-600",
  low_feed: "border-gray-800 bg-gray-900/60 hover:border-gray-700 opacity-75"
};

function formatTime(dateStr) {
  try {
    return formatDistanceToNow(new Date(dateStr), { addSuffix: true, locale: he });
  } catch {
    return dateStr;
  }
}

export default function FeedCard({ item }) {
  const { addFeedback } = useApp();
  const [feedbackGiven, setFeedbackGiven] = useState(null);
  const [showWhyShown, setShowWhyShown] = useState(false);

  const decision = item.score?.decision || "feed";
  const isCluster = item.type === "cluster";

  // Hebrew-first: prefer translated title; fall back to raw title
  const displayTitle = isCluster
    ? item.clusterTitle
    : (item.translatedTitle || item.title);

  const source = isCluster ? item.sourceDisplayNames?.[0] : item.sourceDisplayName;
  const publishedAt = item.publishedAt || item.firstSeenAt;
  const tags = item.tags || [];
  const url = isCluster ? null : item.url;
  const articleId = item.id;
  const reasoning = item.score?.reasoning || [];

  const additionalSources = isCluster && item.sourceDisplayNames?.length > 1
    ? item.sourceDisplayNames.slice(1)
    : [];

  const handleFeedback = (action) => {
    addFeedback(articleId, action);
    setFeedbackGiven(action);
  };

  const cardBorderClass = CARD_STYLES[decision] || CARD_STYLES.feed;

  // Show only the last 4 reasoning lines for the "why shown" section (most relevant)
  const summaryReasoning = reasoning.slice(-4);

  return (
    <article
      className={`rounded-xl border transition-all duration-200 ${cardBorderClass} ${
        decision === "push" ? "shadow-lg shadow-amber-500/5" : ""
      }`}
    >
      {/* Priority indicator bar */}
      {decision === "push" && (
        <div className="h-0.5 bg-gradient-to-l from-amber-400 to-amber-600 rounded-t-xl" />
      )}
      {decision === "high_feed" && (
        <div className="h-0.5 bg-gradient-to-l from-emerald-400 to-emerald-600 rounded-t-xl" />
      )}

      <div className="p-3">
        {/* Header: badge + source + time */}
        <div className="flex items-center justify-between gap-2 mb-2">
          <DecisionBadge decision={decision} size="xs" />
          <div className="flex items-center gap-1.5 min-w-0 flex-1 justify-end">
            <span className="text-xs text-gray-500 font-medium truncate">{source}</span>
            {isCluster && additionalSources.length > 0 && (
              <span className="text-xs text-gray-600 flex-shrink-0">
                +{additionalSources.length} מקורות
              </span>
            )}
            <span className="text-gray-700 flex-shrink-0">·</span>
            <span className="text-xs text-gray-600 flex items-center gap-0.5 flex-shrink-0">
              <Clock size={10} />
              {formatTime(publishedAt)}
            </span>
          </div>
        </div>

        {/* Main title — always Hebrew (or original when translation unavailable) */}
        <h2 className={`font-semibold leading-snug ${
          decision === "push" ? "text-amber-100 text-sm" :
          decision === "high_feed" ? "text-white text-sm" :
          decision === "feed" ? "text-gray-100 text-sm" :
          "text-gray-400 text-sm"
        }`}>
          {displayTitle}
        </h2>

        {/* Cluster additional sources */}
        {isCluster && item.sources?.length > 1 && (
          <div className="flex items-center gap-1.5 mt-1.5">
            <span className="text-xs text-gray-600">גם ב:</span>
            {additionalSources.slice(0, 3).map(s => (
              <span key={s} className="text-xs text-gray-500 bg-gray-800 rounded px-1.5 py-0.5">{s}</span>
            ))}
          </div>
        )}

        {/* Tags (compact, only for push/high_feed) */}
        {tags.length > 0 && (decision === "push" || decision === "high_feed") && (
          <div className="flex flex-wrap gap-1 mt-1.5">
            {tags.slice(0, 4).map(tag => (
              <span
                key={tag}
                className="text-[10px] text-gray-500 bg-gray-800/80 rounded px-1.5 py-0.5 border border-gray-700/50"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Actions row */}
        <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-800/50 gap-2 flex-wrap">
          {/* Left: link + why shown */}
          <div className="flex items-center gap-3">
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
              >
                <ExternalLink size={11} />
                פתח
              </a>
            )}
            <button
              onClick={() => setShowWhyShown(s => !s)}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300 transition-colors"
            >
              {showWhyShown ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
              למה הוצג?
            </button>
          </div>

          {/* Right: feedback */}
          <div className="flex items-center gap-1">
            {feedbackGiven ? (
              <span className="text-xs text-gray-500 italic">✓ נשמר</span>
            ) : (
              <>
                <button
                  onClick={() => handleFeedback("more_like_this")}
                  className="flex items-center gap-1 px-2 py-1 text-xs text-gray-400 hover:text-emerald-400 hover:bg-emerald-500/10 rounded border border-gray-700/50 hover:border-emerald-500/30 transition-all"
                >
                  <ThumbsUp size={11} />
                  <span>יותר</span>
                </button>
                <button
                  onClick={() => handleFeedback("less_like_this")}
                  className="flex items-center gap-1 px-2 py-1 text-xs text-gray-400 hover:text-red-400 hover:bg-red-500/10 rounded border border-gray-700/50 hover:border-red-500/30 transition-all"
                >
                  <ThumbsDown size={11} />
                  <span>פחות</span>
                </button>
              </>
            )}
          </div>
        </div>

        {/* Why shown? expanded reasoning */}
        {showWhyShown && reasoning.length > 0 && (
          <div className="mt-2 pt-2 border-t border-gray-800/40">
            <div className="space-y-0.5">
              {summaryReasoning.map((line, i) => {
                const isFinal = line.includes("החלטה סופית");
                return (
                  <p
                    key={i}
                    className={`text-xs leading-relaxed ${
                      isFinal ? "text-gray-200 font-medium" : "text-gray-500"
                    }`}
                  >
                    {line}
                  </p>
                );
              })}
            </div>
            {reasoning.length > 4 && (
              <p className="text-[10px] text-gray-600 mt-1">
                +{reasoning.length - 4} שלבים נוספים — ראה פאנל דיבאג לפירוט מלא
              </p>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
