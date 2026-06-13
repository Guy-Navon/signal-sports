import React, { useState, useEffect, useCallback } from "react";
import { RefreshCw, Play, CheckCircle2, AlertCircle, ChevronDown, ChevronUp, Languages } from "lucide-react";
import { getIngestSources, runIngestion, getIngestRuns, getIngestQuality, backfillTranslations, getTranslationStatus } from "@/api/client";

const RESULT_LABELS = [
  { key: "fetched",           label: "נמצאו" },
  { key: "inserted",          label: "נוספו" },
  { key: "skipped_duplicate", label: "דולגו ככפולים" },
  { key: "skipped_filtered",  label: "סוננו" },
  { key: "failed",            label: "נכשלו" },
];

function formatRunTime(isoStr) {
  if (!isoStr) return "—";
  try {
    return new Date(isoStr).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
}

function SourceResultCard({ result }) {
  const hasNew = result.inserted > 0;
  return (
    <div className={`rounded-lg border p-3 ${
      hasNew
        ? "border-emerald-800/40 bg-emerald-900/10"
        : "border-gray-800 bg-gray-900/30"
    }`}>
      <div className="text-xs font-medium text-gray-300 mb-2">{result.source_id}</div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {RESULT_LABELS.map(({ key, label }) => (
          <span key={key} className="flex gap-1">
            <span className="text-gray-600">{label}:</span>
            <span className={
              key === "inserted" && result[key] > 0
                ? "text-emerald-400 font-medium"
                : key === "failed" && result[key] > 0
                  ? "text-red-400 font-medium"
                  : "text-gray-300"
            }>
              {result[key] ?? 0}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

function QualityPanel({ quality }) {
  return (
    <div className="mt-3 space-y-3 text-xs">
      <div className="flex gap-4 flex-wrap">
        <span className="text-gray-500">
          סה״כ כתבות RSS:{" "}
          <span className="text-gray-300">{quality.total_rss_articles}</span>
        </span>
        <span className="text-gray-500">
          ביטחון נמוך:{" "}
          <span className={quality.low_confidence_count > 0 ? "text-amber-400" : "text-gray-300"}>
            {quality.low_confidence_count}
          </span>
        </span>
        <span className="text-gray-500">
          לבדיקה:{" "}
          <span className="text-gray-300">{quality.questionable_articles?.length ?? 0}</span>
        </span>
      </div>

      <div>
        <div className="text-gray-600 mb-1">ספורט</div>
        <div className="flex gap-2 flex-wrap">
          {Object.entries(quality.sport_breakdown).map(([sport, count]) => (
            <span
              key={sport}
              className="px-2 py-0.5 rounded border border-gray-800 bg-gray-900/30 text-gray-400"
            >
              {sport}: {count}
            </span>
          ))}
        </div>
      </div>

      {Object.keys(quality.event_type_breakdown).length > 0 && (
        <div>
          <div className="text-gray-600 mb-1">סוגי אירועים</div>
          <div className="flex gap-2 flex-wrap">
            {Object.entries(quality.event_type_breakdown)
              .sort(([, a], [, b]) => b - a)
              .slice(0, 8)
              .map(([ev, count]) => (
                <span
                  key={ev}
                  className="px-2 py-0.5 rounded border border-gray-800 bg-gray-900/30 text-gray-400"
                >
                  {ev}: {count}
                </span>
              ))}
          </div>
        </div>
      )}

      {quality.questionable_articles?.length > 0 && (
        <div>
          <div className="text-gray-600 mb-1">
            כתבות לבדיקה — {quality.questionable_articles.length} כתבות
          </div>
          <div className="space-y-1">
            {quality.questionable_articles.slice(0, 5).map(a => (
              <div
                key={a.id}
                className="bg-gray-900/30 border border-gray-800 rounded-lg px-3 py-2"
              >
                <div className="text-gray-400 mb-0.5 truncate">{a.title}</div>
                <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-gray-600">
                  <span>{a.source}</span>
                  <span>·</span>
                  <span>{a.sport}</span>
                  {a.league && (
                    <>
                      <span>·</span>
                      <span>{a.league}</span>
                    </>
                  )}
                  <span>·</span>
                  <span className="text-amber-600/80">{a.reasons.join(", ")}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const BACKFILL_RESULT_LABELS = [
  { key: "checked",                    label: "נבדקו" },
  { key: "candidates",                 label: "מועמדים לתרגום" },
  { key: "translated",                 label: "תורגמו" },
  { key: "retranslated_fake",          label: "הוחלפו תרגומי בדיקה" },
  { key: "forced_retranslated",        label: "תורגמו מחדש בכפייה" },
  { key: "language_corrected",         label: "שפה תוקנה" },
  { key: "skipped_hebrew",             label: "דולגו — עברית" },
  { key: "skipped_already_translated", label: "דולגו — כבר תורגמו" },
  { key: "skipped_provider_not_ready", label: "דולגו — ספק לא מוכן" },
  { key: "failed",                     label: "נכשלו" },
];

const PROVIDER_STATUS_LABELS = {
  disabled: "תרגום לא פעיל",
  noop:     "תרגום לא פעיל",
  fake:     "תרגום בדיקה פעיל — לא תרגום אמיתי",
  claude:   "תרגום פעיל: Claude",
};

function ProviderStatusBadge({ status }) {
  if (!status) return null;
  const { provider, can_translate, reason } = status;
  const label = PROVIDER_STATUS_LABELS[provider] ?? `ספק: ${provider}`;
  const color = can_translate
    ? provider === "fake"
      ? "text-amber-400 border-amber-800/40"
      : "text-emerald-400 border-emerald-800/40"
    : "text-gray-500 border-gray-800";
  return (
    <div className={`flex items-center gap-1.5 text-xs border rounded px-2 py-0.5 ${color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${can_translate ? (provider === "fake" ? "bg-amber-400" : "bg-emerald-400") : "bg-gray-600"}`} />
      <span>{label}</span>
    </div>
  );
}

function TranslationSection({ selectedSource, onFeedRefresh }) {
  const [isRunning, setIsRunning] = useState(false);
  const [dryRun, setDryRun] = useState(false);
  const [includeFake, setIncludeFake] = useState(false);
  const [forceRetranslate, setForceRetranslate] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [providerStatus, setProviderStatus] = useState(null);

  useEffect(() => {
    getTranslationStatus()
      .then(status => {
        setProviderStatus(status);
        // When switching to a real provider, default includeFake to true
        // so existing stub translations get replaced automatically.
        if (status?.provider === "claude" && status?.can_translate) {
          setIncludeFake(true);
        }
      })
      .catch(() => {});
  }, []);

  const handleBackfill = async () => {
    setIsRunning(true);
    setError(null);
    setResult(null);
    try {
      const sourceId = selectedSource === "all" ? undefined : selectedSource;
      const res = await backfillTranslations({ sourceId, dryRun, includeFake, force: forceRetranslate });
      setResult(res);
      if (!dryRun && res.translated > 0 && onFeedRefresh) {
        onFeedRefresh();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsRunning(false);
    }
  };

  const provider = providerStatus?.provider;
  const providerReady = providerStatus?.can_translate ?? true; // optimistic until loaded
  const isFakeProvider = provider === "fake";
  const isRealProvider = providerReady && !isFakeProvider;

  const successMessage = () => {
    if (dryRun) return `בדיקה בלבד — ${result.candidates} מועמדים לתרגום`;
    if (result.translated === 0) return "לא נמצאו כותרות לתרגום";
    if (isFakeProvider) return `נוצרו ${result.translated} תרגומי בדיקה`;
    if (result.retranslated_fake > 0 && result.translated > result.retranslated_fake) {
      return `תורגמו ${result.translated} כותרות (כולל ${result.retranslated_fake} תרגומי בדיקה שהוחלפו)`;
    }
    if (result.retranslated_fake > 0) return `הוחלפו ${result.retranslated_fake} תרגומי בדיקה`;
    return `תורגמו ${result.translated} כותרות`;
  };

  return (
    <div className="border-t border-gray-800/60 pt-3 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold text-gray-400 flex items-center gap-2">
          <Languages size={13} className="text-blue-400" />
          תרגום כותרות
        </h3>
        <ProviderStatusBadge status={providerStatus} />
      </div>

      {/* Warning when provider is not configured */}
      {providerStatus && !providerReady && (
        <div className="flex items-start gap-2 text-xs text-amber-500/80 bg-amber-900/10 border border-amber-800/30 rounded-lg px-3 py-2">
          <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
          <span>
            {providerStatus.reason === "TRANSLATION_PROVIDER is disabled"
              ? "תרגום לא פעיל — הגדר TRANSLATION_PROVIDER=claude ו-TRANSLATION_API_KEY בקובץ backend/.env"
              : providerStatus.reason === "TRANSLATION_API_KEY is missing"
                ? "חסר מפתח API — הגדר TRANSLATION_API_KEY בקובץ backend/.env"
                : providerStatus.reason ?? "ספק תרגום לא מוכן"}
          </span>
        </div>
      )}

      {/* Warning when fake provider is active */}
      {isFakeProvider && (
        <div className="flex items-start gap-2 text-xs text-amber-400/80 bg-amber-900/10 border border-amber-800/30 rounded-lg px-3 py-2">
          <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
          <span>מצב בדיקה — הכותרות לא יתורגמו באמת. הגדר TRANSLATION_PROVIDER=claude לתרגום אמיתי.</span>
        </div>
      )}

      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={handleBackfill}
          disabled={isRunning}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-700 hover:bg-indigo-600 disabled:bg-indigo-900/40 disabled:cursor-not-allowed text-white disabled:text-indigo-400 text-xs font-medium transition-all"
        >
          {isRunning ? (
            <>
              <RefreshCw size={12} className="animate-spin" />
              מתרגם...
            </>
          ) : (
            <>
              <Languages size={12} />
              תרגם כותרות חסרות
            </>
          )}
        </button>

        <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={dryRun}
            onChange={e => setDryRun(e.target.checked)}
            className="w-3 h-3 accent-indigo-500"
          />
          בדיקה בלבד
        </label>
      </div>

      {/* includeFake option — only useful with a real provider */}
      {isRealProvider && (
        <div className="space-y-1.5">
          <label className="flex items-start gap-1.5 text-xs text-gray-500 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={includeFake}
              onChange={e => setIncludeFake(e.target.checked)}
              className="w-3 h-3 accent-indigo-500 mt-0.5 flex-shrink-0"
            />
            <span>
              תרגם מחדש תרגומי בדיקה
              <span className="text-gray-600 mr-1">— יחליף כותרות שמתחילות ב״תרגום בדיקה:״</span>
            </span>
          </label>

          <label className="flex items-start gap-1.5 text-xs text-gray-500 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={forceRetranslate}
              onChange={e => setForceRetranslate(e.target.checked)}
              className="w-3 h-3 accent-indigo-500 mt-0.5 flex-shrink-0"
            />
            <span>
              כפה תרגום מחדש
              <span className="text-gray-600 mr-1">— יתרגם מחדש את כל הכתבות, גם אם כבר תורגמו</span>
            </span>
          </label>
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 text-xs text-red-400 bg-red-900/10 border border-red-800/30 rounded-lg px-3 py-2">
          <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <div className="space-y-2">
          {/* Skipped / provider not ready */}
          {result.status === "skipped" && (
            <div className="flex items-start gap-2 text-xs text-amber-500/80 bg-amber-900/10 border border-amber-800/30 rounded-lg px-3 py-2">
              <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
              <span>
                תרגום לא פעיל — {result.candidates} כותרות ממתינות לתרגום.
                {result.reason && ` (${result.reason})`}
              </span>
            </div>
          )}

          {/* Success summary */}
          {result.status !== "skipped" && (
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <CheckCircle2 size={12} className="text-indigo-400 flex-shrink-0" />
              {successMessage()}
            </div>
          )}

          <div className="rounded-lg border border-gray-800 bg-gray-900/30 p-3">
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
              {BACKFILL_RESULT_LABELS.map(({ key, label }) => (
                (result[key] ?? 0) > 0 || key === "checked" ? (
                  <span key={key} className="flex gap-1">
                    <span className="text-gray-600">{label}:</span>
                    <span className={
                      key === "translated" && result[key] > 0
                        ? "text-indigo-400 font-medium"
                        : key === "retranslated_fake" && result[key] > 0
                          ? "text-indigo-300 font-medium"
                          : key === "forced_retranslated" && result[key] > 0
                            ? "text-indigo-300 font-medium"
                            : key === "language_corrected" && result[key] > 0
                              ? "text-blue-400 font-medium"
                              : key === "failed" && result[key] > 0
                                ? "text-red-400 font-medium"
                                : "text-gray-300"
                    }>
                      {result[key] ?? 0}
                    </span>
                  </span>
                ) : null
              ))}
            </div>

            {result.errors?.length > 0 && (
              <div className="mt-2 space-y-1">
                {result.errors.slice(0, 3).map((e, i) => (
                  <div key={i} className="text-xs text-red-400/70 truncate">
                    {e.article_id}: {e.error}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function IngestionPanel({ isBackendMode, onFeedRefresh }) {
  const [ingestSources, setIngestSources] = useState([]);
  const [selectedSource, setSelectedSource] = useState("all");
  const [isRunning, setIsRunning] = useState(false);
  const [lastResult, setLastResult] = useState(null);
  const [recentRuns, setRecentRuns] = useState([]);
  const [quality, setQuality] = useState(null);
  const [isLoadingQuality, setIsLoadingQuality] = useState(false);
  const [showQuality, setShowQuality] = useState(false);
  const [error, setError] = useState(null);

  const loadMeta = useCallback(async () => {
    if (!isBackendMode) return;
    try {
      const [sources, runs] = await Promise.all([
        getIngestSources(),
        getIngestRuns(5),
      ]);
      setIngestSources(sources);
      setRecentRuns(runs);
    } catch (err) {
      setError(err.message);
    }
  }, [isBackendMode]);

  useEffect(() => {
    loadMeta();
  }, [loadMeta]);

  const handleRun = async () => {
    setIsRunning(true);
    setError(null);
    try {
      const sourceId = selectedSource === "all" ? undefined : selectedSource;
      const result = await runIngestion(sourceId);
      setLastResult(result);
      const runs = await getIngestRuns(5);
      setRecentRuns(runs);
      if (onFeedRefresh) onFeedRefresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsRunning(false);
    }
  };

  const handleToggleQuality = async () => {
    if (showQuality) {
      setShowQuality(false);
      return;
    }
    setIsLoadingQuality(true);
    try {
      const q = await getIngestQuality();
      setQuality(q);
      setShowQuality(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoadingQuality(false);
    }
  };

  if (!isBackendMode) {
    return (
      <div className="border border-gray-800 rounded-xl p-4 bg-gray-900/20">
        <h2 className="text-sm font-semibold text-gray-500 mb-1">ייבוא כתבות RSS</h2>
        <p className="text-xs text-gray-600">ייבוא RSS זמין רק במצב שרת</p>
        <p className="text-xs text-gray-700 mt-1">
          מצב מקומי פעיל — כדי לראות RSS אמיתי הפעל VITE_DATA_MODE=backend
        </p>
      </div>
    );
  }

  const totalInserted = lastResult?.sources?.reduce((sum, s) => sum + (s.inserted ?? 0), 0) ?? 0;

  return (
    <div className="border border-gray-700 rounded-xl bg-gray-900/40 p-4 space-y-4">
      <h2 className="text-sm font-semibold text-white flex items-center gap-2">
        <RefreshCw size={14} className="text-blue-400" />
        ייבוא כתבות RSS
      </h2>

      {error && (
        <div className="flex items-start gap-2 text-xs text-red-400 bg-red-900/10 border border-red-800/30 rounded-lg px-3 py-2">
          <AlertCircle size={12} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Source selector */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setSelectedSource("all")}
          className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${
            selectedSource === "all"
              ? "border-blue-500/50 bg-blue-500/10 text-blue-300"
              : "border-gray-700 text-gray-500 hover:border-gray-600 hover:text-gray-400"
          }`}
        >
          כל המקורות
        </button>
        {ingestSources.map(src => (
          <button
            key={src.source_id}
            onClick={() => setSelectedSource(src.source_id)}
            className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${
              selectedSource === src.source_id
                ? "border-blue-500/50 bg-blue-500/10 text-blue-300"
                : "border-gray-700 text-gray-500 hover:border-gray-600 hover:text-gray-400"
            }`}
          >
            {src.display_name}
          </button>
        ))}
      </div>

      {/* Run button */}
      <button
        onClick={handleRun}
        disabled={isRunning}
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-blue-900/40 disabled:cursor-not-allowed text-white disabled:text-blue-400 text-sm font-medium transition-all"
      >
        {isRunning ? (
          <>
            <RefreshCw size={14} className="animate-spin" />
            מייבא...
          </>
        ) : (
          <>
            <Play size={14} />
            הרץ ייבוא עכשיו
          </>
        )}
      </button>

      {/* Result summary */}
      {lastResult && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <CheckCircle2 size={12} className="text-emerald-400 flex-shrink-0" />
            {totalInserted > 0
              ? `הייבוא הסתיים — נוספו ${totalInserted} כתבות חדשות`
              : "הייבוא הסתיים — לא נוספו כתבות חדשות"}
          </div>
          {lastResult.sources?.map(src => (
            <SourceResultCard key={src.source_id} result={src} />
          ))}
        </div>
      )}

      {/* Recent runs */}
      {recentRuns.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs text-gray-600 font-medium">ריצות אחרונות</div>
          {recentRuns.map(run => (
            <div
              key={run.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs bg-gray-900/30 border border-gray-800 rounded-lg px-3 py-2"
            >
              <span className={run.status === "ok" ? "text-emerald-500" : "text-red-400"}>●</span>
              <span className="text-gray-400 font-medium">{run.source_id}</span>
              <span className="text-gray-700">{formatRunTime(run.started_at)}</span>
              <span className="text-gray-600">
                נמצאו: {run.fetched_count} | נוספו: {run.inserted_count} | כפולים: {run.skipped_duplicate_count}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Quality panel toggle */}
      <div className="border-t border-gray-800/60 pt-3">
        <button
          onClick={handleToggleQuality}
          disabled={isLoadingQuality}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          {isLoadingQuality
            ? <RefreshCw size={11} className="animate-spin" />
            : showQuality
              ? <ChevronUp size={11} />
              : <ChevronDown size={11} />
          }
          איכות הסיווג
        </button>

        {showQuality && quality && <QualityPanel quality={quality} />}
      </div>

      {/* Translation backfill section */}
      <TranslationSection
        selectedSource={selectedSource}
        onFeedRefresh={onFeedRefresh}
      />
    </div>
  );
}
