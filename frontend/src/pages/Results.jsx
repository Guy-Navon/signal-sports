import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { BarChart2, AlertTriangle, SlidersHorizontal, RefreshCw } from "lucide-react";
import { useApp } from "@/context/AppContext";
import ResultsState from "@/components/results/ResultsState";
import DayHeading from "@/components/results/DayHeading";
import ResultCard from "@/components/results/ResultCard";
import { groupByDay, dayGridClass } from "@/components/results/resultsGrouping";
import { formatDayHeading } from "@/components/results/resultsFormat";
import "@/components/results/results-page.css";

function ResultsSkeleton() {
  return (
    <>
      <p className="sr-only" role="status">טוען תוצאות…</p>
      <div className="sg-results-page__groups" aria-hidden="true">
        {[0, 1].map((g) => (
          <div key={g}>
            <div className="sg-results-page__placeholder sg-results-page__placeholder--heading" />
            <div className="sg-results-page__games grid sm:grid-cols-2">
              {[0, 1, 2, 3].map((c) => (
                <div key={c} className="sg-results-page__game">
                  <div className="sg-results-page__placeholder sg-results-page__placeholder--meta" />
                  <div className="sg-results-page__placeholder" />
                  <div className="sg-results-page__placeholder" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </>
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
    <header className="sg-results-page__heading">
      <p className="sg-results-page__eyebrow">
        <BarChart2 size={14} aria-hidden="true" />
        תוצאות
      </p>
      <h1>
        התוצאות שרלוונטיות אליך
      </h1>
      <p className="sg-results-page__intro">
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
      <ResultsState
        icon={AlertTriangle}
        role="alert"
        title="לא הצלחנו לטעון את התוצאות"
        hint="ייתכן שהשרת אינו זמין כרגע. אפשר לנסות שוב."
        action={
          <button
            onClick={refreshResults}
            className="sg-results-page__action"
          >
            <RefreshCw size={14} aria-hidden="true" />
            נסה שוב
          </button>
        }
      />
    );
  } else if (!resultsHasPreferences) {
    body = (
      <ResultsState
        icon={SlidersHorizontal}
        title="עדיין לא בחרת מה מעניין אותך"
        hint="בחר קבוצות, שחקנים או ליגות כדי לראות כאן את התוצאות שרלוונטיות אליך."
        action={
          <Link
            to="/interests"
            className="sg-results-page__action"
          >
            בחירת תחומי עניין
          </Link>
        }
      />
    );
  } else if (total === 0) {
    body = (
      <ResultsState
        icon={BarChart2}
        title="אין תוצאות רלוונטיות כרגע"
        hint="ברגע שיהיו משחקים חדשים של הקבוצות והליגות שלך, הם יופיעו כאן."
      />
    );
  } else {
    body = (
      <div className="sg-results-page__groups">
        {groups.map((group) => (
          <section key={group.dayKey ?? "undated"} aria-label={formatDayHeading(group.dayKey)}>
            <DayHeading count={group.games.length}>
              {formatDayHeading(group.dayKey)}
            </DayHeading>
            <div className={`sg-results-page__games ${dayGridClass(group.games.length)}`}>
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
    <div className="sg-gutter">
      <div className="sg-container sg-results-page">
        {Header}
        {body}
      </div>
    </div>
  );
}
