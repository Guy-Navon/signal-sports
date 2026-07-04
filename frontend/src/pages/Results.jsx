import React from "react";
import { Clock } from "lucide-react";
import SignalMark from "@/components/shell/SignalMark";

export default function Results() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center max-w-md mx-auto">
      <SignalMark className="scale-150 mb-5" />
      <p className="text-[11px] font-semibold tracking-wide text-signal-high flex items-center gap-1.5">
        <Clock size={12} />
        בקרוב
      </p>
      <h1 className="font-display text-2xl font-bold text-foreground mt-2">תוצאות</h1>
      <p className="text-sm text-text-secondary leading-relaxed mt-4">
        תוצאות מעניינות בלבד, בלי להציף אותך במשחקים שלא מעניינים אותך — כרטיסייה נפרדת שתסנן חכם,
        רק קבוצות וליגות שמעניינות אותך, בלי כל שאר הרעש.
      </p>
    </div>
  );
}
