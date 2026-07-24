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
    <header className="editorial-rule-heavy grid gap-4 pt-3 sm:grid-cols-[1fr_auto] sm:items-end">
      <div className="min-w-0">
        <div className="mb-2 flex items-center gap-2">
          <span className="index-label">01</span>
          <span className="eyebrow">PERSONAL EDITION / המהדורה האישית</span>
        </div>
        <h1 className="font-display text-[2rem] font-bold leading-[0.98] tracking-[-0.025em] text-foreground sm:text-[2.75rem] lg:text-[3.45rem]">
          {profileName ? (
            <>
              המהדורה של <span className="text-signal-push">{profileName}</span>
            </>
          ) : (
            "המהדורה שלך"
          )}
        </h1>
      </div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-s border-foreground/20 ps-3 text-[11px] text-text-secondary sm:max-w-[15rem] sm:block sm:text-end">
        {dateLine && <p className="font-medium text-foreground">{dateLine}</p>}
        <p>
          <MonoValue className="font-bold text-foreground">{total}</MonoValue> סיפורים נבחרו
        </p>
        {scanned > total && (
          <p>
            מתוך <MonoValue>{scanned}</MonoValue> כתבות שנסרקו
          </p>
        )}
      </div>
    </header>
  );
}
