import React from "react";
import { Code2, ExternalLink, CheckCircle2, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { consoleToggle } from "@/components/ops/consoleStyles";

const TRUST_LABELS = {
  high: { label: "גבוה", color: "text-signal-high" },
  medium: { label: "בינוני", color: "text-signal-push" },
  low: { label: "נמוך", color: "text-signal-hidden" },
};

const SOURCE_TYPE_LABELS = {
  rss: "RSS",
  category_page: "דף קטגוריה",
  scraper: "Scraper",
  api: "API",
};

const LANG_LABELS = { he: "עברית", en: "English" };

// Letter avatar derived from the display name — quiet source identity.
function avatarLetter(name) {
  return (name || "?").trim().charAt(0).toUpperCase();
}

export default function SourceToggleCard({ source, onToggle }) {
  const trust = TRUST_LABELS[source.trustLevel] || TRUST_LABELS.medium;

  return (
    <div
      className={cn(
        "border rounded-2xl p-4 transition-colors",
        source.enabled ? "border-border bg-surface-1" : "border-border/60 bg-surface-1/50 opacity-70"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <div
            className={cn(
              "w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 font-bold text-sm border",
              source.enabled
                ? "bg-signal-high/10 border-signal-high/25 text-signal-high"
                : "bg-surface-3 border-border text-text-dim"
            )}
          >
            {avatarLetter(source.displayName)}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-0.5 flex-wrap">
              <span className={cn("font-medium text-sm", source.enabled ? "text-foreground" : "text-text-secondary")}>
                {source.displayName}
              </span>
              <span
                className={cn(
                  "text-[10px] px-1.5 py-0.5 rounded-full border",
                  source.language === "en"
                    ? "border-signal-feed/30 bg-signal-feed/10 text-signal-feed"
                    : "border-border bg-surface-3 text-text-secondary"
                )}
              >
                {LANG_LABELS[source.language] || source.language}
              </span>
            </div>
            <p className="text-xs text-text-dim mb-2">{source.description}</p>

            <div className="flex items-center gap-3 flex-wrap text-xs text-text-dim">
              <span className="flex items-center gap-1">
                <Code2 size={10} />
                {SOURCE_TYPE_LABELS[source.sourceType] || source.sourceType}
              </span>
              <span className="flex items-center gap-1">
                אמינות: <span className={trust.color}>{trust.label}</span>
              </span>
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-text-dim hover:text-text-secondary transition-colors"
              >
                <ExternalLink size={10} />
                {source.url.replace("https://", "")}
              </a>
            </div>
          </div>
        </div>

        <button
          onClick={() => onToggle(source.id)}
          className={consoleToggle(source.enabled, "flex-shrink-0")}
        >
          {source.enabled ? (
            <><CheckCircle2 size={12} /> פעיל</>
          ) : (
            <><XCircle size={12} /> כבוי</>
          )}
        </button>
      </div>
    </div>
  );
}
