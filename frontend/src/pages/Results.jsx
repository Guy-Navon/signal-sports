import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { BarChart2, AlertTriangle, SlidersHorizontal, RefreshCw } from "lucide-react";
import { useApp } from "@/context/AppContext";
import EmptyState from "@/components/shared/EmptyState";
import SectionHeading from "@/components/feed/SectionHeading";
import ResultCard from "@/components/results/ResultCard";
import { groupByDay } from "@/components/results/resultsGrouping";
import { formatDayHeading } from "@/components/results/resultsFormat";

function ResultsSkeleton() {
  return (
    <div className="space-y-6" aria-hidden>
      {[0, 1].map((g) => (
        <div key={g}>
          <div className="mb-3 h-3 w-24 rounded bg-surface-2/60" />
          <div className="grid gap-3 sm:grid-cols-2">
            {[0, 1, 2, 3].map((c) => (
              <div key={c} className="h-24 rounded-xl border border-border/40 bg-surface-1/40" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// Personalized results — a clean history of games from the teams, players, and
// competitions this user follows (server-filtered under enforcement). Grouped
// chronologically; the winner of each completed game is quietly emphasized.
export default function Results() {
  const {
    resultsGames,
    resultsHasPreferences,
    resultsLoading,
    resultsError,
    refreshResults,
    isBackendMode,
  } = useApp();

  const groups = useMemo(() => groupByDay(resultsGames || []), [resultsGames]);
  const total = resultsGames?.length || 0;

  const Header = (
    <header className="mb-6">
      <p className="flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-signal-high">
        <BarChart2 size={12} />
        תוצאות
      </p>
      <h1 className="mt-2 font-display text-2xl font-bold text-foreground">
        התוצאות שרלוונטיות אליך
      </h1>
      <p className="mt-2 max-w-xl text-sm leading-relaxed text-text-secondary">
        רק משחקים של הקבוצות, השחקנים והליגות שאתה עוקב אחריהם — בלי לוח תוצאות כללי
        ובלי רעש.
      </p>
    </header>
  );

  let body;
  if (isBackendMode && resultsLoading && total === 0) {
    body = <ResultsSkeleton />;
  } else if (resultsError) {
    body = (
      <EmptyState
        icon={AlertTriangle}
        title="לא הצלחנו לטעון את התוצאות"
        hint="ייתכן שהשרת אינו זמין כרגע. אפשר לנסות שוב."
        action={
          <button
            onClick={refreshResults}
            className="flex items-center gap-1.5 text-sm text-signal-high transition-colors hover:text-signal-high/80"
          >
            <RefreshCw size={14} />
            נסה שוב
          </button>
        }
      />
    );
  } else if (!resultsHasPreferences) {
    body = (
      <EmptyState
        icon={SlidersHorizontal}
        title="עדיין לא בחרת מה מעניין אותך"
        hint="בחר קבוצות, שחקנים או ליגות כדי לראות כאן את התוצאות שרלוונטיות אליך."
        action={
          <Link
            to="/interests"
            className="text-sm text-signal-high transition-colors hover:text-signal-high/80"
          >
            בחירת תחומי עניין
          </Link>
        }
      />
    );
  } else if (total === 0) {
    body = (
      <EmptyState
        icon={BarChart2}
        title="אין תוצאות רלוונטיות כרגע"
        hint="ברגע שיהיו משחקים חדשים של הקבוצות והליגות שלך, הם יופיעו כאן."
      />
    );
  } else {
    body = (
      <div className="space-y-8">
        {groups.map((group) => (
          <section key={group.dayKey ?? "undated"} aria-label={formatDayHeading(group.dayKey)}>
            <SectionHeading count={group.games.length} className="mb-3">
              {formatDayHeading(group.dayKey)}
            </SectionHeading>
            <div className="grid gap-3 sm:grid-cols-2">
              {group.games.map((game) => (
                <ResultCard key={game.id} game={game} />
              ))}
            </div>
          </section>
        ))}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      {Header}
      {body}
    </div>
  );
}
