import React from "react";
import MonoValue from "@/components/shared/MonoValue";

// The edition's masthead line: today's date, the story count, and the
// personalized edition title. Kept deliberately smaller than the lead
// headline — the lead story is the biggest thing on the page.
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
    <header className="flex items-end justify-between gap-4 flex-wrap">
      <div>
        <p className="text-[11px] tracking-[0.08em] text-text-dim flex items-center flex-wrap gap-x-1.5">
          {dateLine && <span>{dateLine}</span>}
          {dateLine && <span aria-hidden>·</span>}
          <span>
            <MonoValue className="text-text-secondary">{total}</MonoValue> סיפורים במהדורה
          </span>
          {scanned > total && (
            <span className="xl:hidden">
              מתוך <MonoValue>{scanned}</MonoValue> שנסרקו
            </span>
          )}
        </p>
        <h1 className="mt-1 font-display font-bold text-[1.3rem] md:text-[1.8rem] text-foreground leading-tight">
          {profileName ? `המהדורה של ${profileName}` : "המהדורה שלך"}
        </h1>
      </div>
    </header>
  );
}
