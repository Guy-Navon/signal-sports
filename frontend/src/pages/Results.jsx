import React from "react";
import { BarChart2, Clock } from "lucide-react";

export default function Results() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center space-y-4 max-w-md mx-auto">
      <div className="w-14 h-14 rounded-2xl bg-surface-2 border border-border flex items-center justify-center elevation-1">
        <BarChart2 size={24} className="text-text-dim" />
      </div>
      <h1 className="font-display text-2xl font-bold text-foreground">תוצאות</h1>
      <div className="bg-surface-1 border border-border rounded-2xl p-5 space-y-3 elevation-1">
        <div className="flex items-center gap-2 text-signal-high justify-center">
          <Clock size={16} />
          <span className="text-sm font-medium">בקרוב</span>
        </div>
        <p className="text-sm text-text-secondary leading-relaxed">
          בקרוב: תוצאות מעניינות בלבד, בלי להציף אותך במשחקים שלא מעניינים אותך.
        </p>
        <p className="text-xs text-text-dim leading-relaxed">
          תוצאות יהיו כרטיסייה נפרדת שתאפשר סינון חכם — רק קבוצות וליגות שמעניינות אותך,
          בלי כל שאר הרעש.
        </p>
      </div>
    </div>
  );
}
