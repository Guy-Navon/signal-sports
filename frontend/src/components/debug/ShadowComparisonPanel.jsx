import React, { useEffect, useState } from "react";
import { RefreshCw, AlertCircle } from "lucide-react";
import { getShadowReport } from "@/api/client";
import { cn } from "@/lib/utils";
import MonoValue from "@/components/shared/MonoValue";
import StatCard from "@/components/shared/StatCard";

const DECISION_TONE = {
  push: "text-signal-push",
  high_feed: "text-signal-high",
  feed: "text-signal-feed",
  low_feed: "text-text-secondary",
  hidden: "text-text-dim",
};

function DecisionBadge({ decision }) {
  return (
    <span className={cn("font-mono text-xs font-medium", DECISION_TONE[decision] || "text-text-dim")}>
      {decision}
    </span>
  );
}

function DisagreementCard({ comparison }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-surface-2 border border-border rounded-[10px] px-3 py-2">
      <button onClick={() => setOpen(!open)} className="w-full text-start">
        <div className="text-xs text-text-secondary truncate mb-1">{comparison.title}</div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs">
          <span className="text-text-dim">{comparison.event_type}</span>
          <span className="text-text-dim">
            ישן: <DecisionBadge decision={comparison.legacy_decision} />
          </span>
          <span className="text-text-dim">
            v2: <DecisionBadge decision={comparison.v2_decision} />
          </span>
          <span className={comparison.direction === "promoted" ? "text-signal-high" : "text-signal-push/80"}>
            {comparison.direction === "promoted" ? "קידום ↑" : "הורדה ↓"}
          </span>
        </div>
      </button>
      {open && (
        <div className="mt-2 pt-2 border-t border-border/60 grid sm:grid-cols-2 gap-3 text-xs">
          <div>
            <div className="text-text-dim font-medium mb-1">מנוע ישן</div>
            {comparison.legacy_reasoning.map((line, i) => (
              <div key={i} className="text-text-secondary">{line}</div>
            ))}
          </div>
          <div>
            <div className="text-text-dim font-medium mb-1">מנוע v2 (affinities)</div>
            {comparison.v2_reasoning.map((line, i) => (
              <div key={i} className="text-text-secondary">{line}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Shadow-mode tab (issue #32): legacy vs Preference V2 decisions per article.
 * Backend mode only — the v2 engine has no JS port by design. */
export default function ShadowComparisonPanel({ userId, isBackendMode }) {
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isBackendMode || !userId) return;
    setLoading(true);
    setError(null);
    getShadowReport(userId)
      .then(setReport)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [userId, isBackendMode]);

  if (!isBackendMode) {
    return (
      <p className="text-xs text-text-secondary">
        השוואת מנועים (shadow) זמינה רק במצב שרת — מנוע ההעדפות v2 רץ בבקאנד בלבד.
      </p>
    );
  }
  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-text-dim">
        <RefreshCw size={12} className="animate-spin" /> טוען השוואת מנועים...
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex items-start gap-2 text-xs text-signal-push">
        <AlertCircle size={12} className="mt-0.5 flex-shrink-0" /> {error}
      </div>
    );
  }
  if (!report) return null;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        <StatCard label="כתבות" value={report.total} className="px-2 py-2 text-center" />
        <StatCard label="הסכמה" value={report.agreement_rate != null ? `${Math.round(report.agreement_rate * 1000) / 10}%` : "—"} tone="high" className="px-2 py-2 text-center" />
        <StatCard label="אי-הסכמות" value={report.disagreements} tone={report.disagreements > 0 ? "low" : "high"} className="px-2 py-2 text-center" />
        <StatCard label="קידומים" value={report.promoted} className="px-2 py-2 text-center" />
        <StatCard label="הורדות" value={report.demoted} className="px-2 py-2 text-center" />
      </div>
      <div className="text-xs text-text-dim">
        push: מנוע ישן <MonoValue className="text-text-secondary">{report.legacy_push_count}</MonoValue>{" "}
        · v2 <MonoValue className="text-text-secondary">{report.v2_push_count}</MonoValue>
      </div>
      {report.comparisons.length === 0 ? (
        <p className="text-xs text-signal-high">שני המנועים מסכימים על כל הכתבות.</p>
      ) : (
        <div className="space-y-1.5">
          {report.comparisons.map((c) => (
            <DisagreementCard key={c.article_id} comparison={c} />
          ))}
        </div>
      )}
    </div>
  );
}
