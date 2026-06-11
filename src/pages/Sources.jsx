import React from "react";
import { useApp } from "@/context/AppContext";
import { Database, Globe, Radio, Code2, ExternalLink, CheckCircle2, XCircle } from "lucide-react";

const TRUST_LABELS = {
  high: { label: "גבוה", color: "text-emerald-400" },
  medium: { label: "בינוני", color: "text-amber-400" },
  low: { label: "נמוך", color: "text-red-400" }
};

const SOURCE_TYPE_LABELS = {
  rss: "RSS",
  category_page: "דף קטגוריה",
  scraper: "Scraper",
  api: "API"
};

const LANG_LABELS = {
  he: "עברית",
  en: "English"
};

export default function Sources() {
  const { sources, toggleSource } = useApp();

  const enabledCount = sources.filter(s => s.enabled).length;

  return (
    <div className="space-y-4 pb-20 md:pb-6 max-w-2xl">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Database size={18} className="text-gray-400" />
          מקורות
        </h1>
        <p className="text-xs text-gray-500 mt-0.5">
          {enabledCount}/{sources.length} מקורות פעילים
        </p>
      </div>

      {/* Info banner */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-3">
        <p className="text-xs text-gray-500 leading-relaxed">
          בגרסה הראשונה, כל המקורות משתמשים בנתוני דמו.
          בגרסאות הבאות, כל מקור יהיה מחובר ל-RSS, Scraper, או API בהתאם.
        </p>
      </div>

      {/* Sources list */}
      <div className="space-y-2">
        {sources.map(source => {
          const trust = TRUST_LABELS[source.trustLevel] || TRUST_LABELS.medium;
          return (
            <div
              key={source.id}
              className={`border rounded-xl p-4 transition-all ${
                source.enabled
                  ? "border-gray-700 bg-gray-900"
                  : "border-gray-800 bg-gray-900/40 opacity-60"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`font-medium text-sm ${source.enabled ? "text-white" : "text-gray-400"}`}>
                      {source.displayName}
                    </span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                      source.language === "en"
                        ? "border-blue-800/60 bg-blue-900/20 text-blue-400"
                        : "border-gray-700/60 bg-gray-800/40 text-gray-400"
                    }`}>
                      {LANG_LABELS[source.language] || source.language}
                    </span>
                  </div>
                  <p className="text-xs text-gray-600 mb-2">{source.description}</p>

                  <div className="flex items-center gap-3 flex-wrap text-xs text-gray-600">
                    <span className="flex items-center gap-1">
                      <Code2 size={10} />
                      {SOURCE_TYPE_LABELS[source.sourceType] || source.sourceType}
                    </span>
                    <span className="flex items-center gap-1">
                      <span>אמינות:</span>
                      <span className={trust.color}>{trust.label}</span>
                    </span>
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-gray-600 hover:text-gray-400 transition-colors"
                    >
                      <ExternalLink size={10} />
                      {source.url.replace("https://", "")}
                    </a>
                  </div>
                </div>

                {/* Toggle */}
                <button
                  onClick={() => toggleSource(source.id)}
                  className={`flex-shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                    source.enabled
                      ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20"
                      : "bg-gray-800 border-gray-700 text-gray-500 hover:border-gray-600"
                  }`}
                >
                  {source.enabled ? (
                    <>
                      <CheckCircle2 size={12} />
                      פעיל
                    </>
                  ) : (
                    <>
                      <XCircle size={12} />
                      כבוי
                    </>
                  )}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}