import React from "react";
import MonoValue from "@/components/shared/MonoValue";

// The edition's masthead line: today's date, the scan summary, and the
// personalized edition title. "המהדורה של גיא" is the product promise —
// this edition was composed for one specific reader.
function hebrewToday() {
  try {
    return new Intl.DateTimeFormat("he-IL", {
      weekday: "long",
      day: "numeric",
      month: "long",
    }).format(new Date());
  } catch {
    return "";
  }
}

export default function EditionHeader({ profileName = "", total = 0, scanned = 0 }) {
  const dateLine = hebrewToday();

  return (
    <header>
      <p className="text-xs text-text-dim tracking-wide flex items-center flex-wrap gap-x-1.5">
        {dateLine && <span>{dateLine}</span>}
        {dateLine && <span aria-hidden>·</span>}
        <span>
          <MonoValue className="text-text-secondary">{total}</MonoValue> סיפורים במהדורה
        </span>
        {scanned > total && (
          <span className="text-text-dim">
            מתוך <MonoValue>{scanned}</MonoValue> שנסרקו
          </span>
        )}
      </p>
      <h1 className="mt-1.5 font-display font-extrabold text-3xl md:text-4xl text-foreground leading-tight">
        {profileName ? `המהדורה של ${profileName}` : "המהדורה שלך"}
      </h1>
    </header>
  );
}
