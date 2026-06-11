import React from "react";
import { BarChart2, Clock } from "lucide-react";

export default function Results() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center space-y-4 pb-20 md:pb-6">
      <div className="w-14 h-14 rounded-xl bg-gray-800 border border-gray-700 flex items-center justify-center mb-2">
        <BarChart2 size={24} className="text-gray-600" />
      </div>
      <h1 className="text-xl font-bold text-white">תוצאות</h1>
      <div className="max-w-sm bg-gray-900/50 border border-gray-800 rounded-xl p-5 space-y-3">
        <div className="flex items-center gap-2 text-amber-400/80 justify-center">
          <Clock size={16} />
          <span className="text-sm font-medium">בקרוב</span>
        </div>
        <p className="text-sm text-gray-400 leading-relaxed">
          בקרוב: תוצאות מעניינות בלבד, בלי להציף אותך במשחקים שלא מעניינים אותך.
        </p>
        <p className="text-xs text-gray-600 leading-relaxed">
          תוצאות יהיו כרטיסייה נפרדת שתאפשר סינון חכם — רק קבוצות וליגות שמעניינות אותך,
          בלי כל שאר הרעש.
        </p>
      </div>
    </div>
  );
}