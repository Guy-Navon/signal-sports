import React, { useId, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { searchCatalog, isFollowed } from "@/components/interests/interestsModel";

const SCOPE_LABELS = { sport: "ענף", competition: "ליגה/טורניר", team: "קבוצה", player: "שחקן" };

// Global search across ALL selectable catalog items — independent of the
// disclosure state. Picking a result adds ONLY that scope (no implicit
// parents; suggestions are the picker's job).
export default function CatalogSearch({ catalog, follows, onPick }) {
  const inputId = useId();
  const [query, setQuery] = useState("");
  const results = useMemo(
    () => searchCatalog(catalog, query),
    [catalog, query],
  );

  return (
    <div className="sg-catalog-search">
      <label htmlFor={inputId}>חיפוש קבוצה, ליגה או שחקן</label>
      <div className="sg-catalog-search__input">
        <Search size={18} aria-hidden="true" />
        <input
          id={inputId}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="בעברית או באנגלית"
        />
      </div>
      {results.length > 0 && (
        <div className="sg-catalog-search__results" aria-label="תוצאות חיפוש">
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
                className="sg-catalog-search__result"
              >
                <bdi dir="auto">{item.display_he}</bdi>
                <small>
                  {followed ? "במעקב" : SCOPE_LABELS[scope]}
                </small>
              </button>
            );
          })}
        </div>
      )}
      {query.trim().length >= 2 && results.length === 0 && <p className="sg-form-note" role="status">לא נמצאו תוצאות. נסו שם אחר בעברית או באנגלית.</p>}
    </div>
  );
}
