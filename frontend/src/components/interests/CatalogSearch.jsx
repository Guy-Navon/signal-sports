import React, { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { searchCatalog, isFollowed } from "@/components/interests/interestsModel";

const SCOPE_LABELS = { sport: "ענף", competition: "ליגה/טורניר", team: "קבוצה", player: "שחקן" };

// Global search across ALL selectable catalog items — independent of the
// disclosure state. Picking a result adds ONLY that scope (no implicit
// parents; suggestions are the picker's job).
export default function CatalogSearch({ catalog, follows, onPick }) {
  const [query, setQuery] = useState("");
  const results = useMemo(
    () => searchCatalog(catalog, query),
    [catalog, query],
  );

  return (
    <div className="relative">
      <div className="flex items-center gap-2 bg-surface-1 border border-border rounded-[10px] px-3 py-2">
        <Search size={14} className="text-text-dim flex-shrink-0" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="חיפוש קבוצה, ליגה או שחקן — בעברית או באנגלית"
          className="bg-transparent text-sm text-foreground placeholder:text-text-dim outline-none w-full"
        />
      </div>
      {results.length > 0 && (
        <div className="absolute z-20 mt-1 w-full bg-surface-1 border border-border rounded-[10px] shadow-lg max-h-64 overflow-y-auto">
          {results.map(({ scope, item }) => {
            const followed = isFollowed(follows, scope, item.id);
            return (
              <button
                key={`${scope}:${item.id}`}
                type="button"
                disabled={followed}
                onClick={() => {
                  onPick(scope, item.id);
                  setQuery("");
                }}
                className="w-full flex items-center justify-between px-3 py-2 text-sm text-right hover:bg-surface-2 disabled:opacity-50"
              >
                <span className="text-foreground">{item.display_he}</span>
                <span className="text-xs text-text-dim">
                  {followed ? "במעקב" : SCOPE_LABELS[scope]}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
