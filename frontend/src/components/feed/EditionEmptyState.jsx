import React from "react";
import { Link } from "react-router-dom";
import { SlidersHorizontal } from "lucide-react";
import SignalMark from "@/components/shell/SignalMark";

// The zero-articles moment. Two species (User Platform PR 4, #52):
// - default: sources are quiet, the profile is calibrated;
// - calibrate: the user skipped calibration (empty ProfileV2) — the feed is
//   INTENTIONALLY empty (explicit product decision: no generic fallback feed)
//   and this state is the persistent "calibrate your feed" CTA.
export default function EditionEmptyState({ variant = "default" }) {
  if (variant === "calibrate") {
    return (
      <div className="flex flex-col items-center justify-center text-center py-24 px-4">
        <SignalMark className="scale-[2.2] mb-6" />
        <p className="text-[11px] font-semibold tracking-wide text-signal-ai">
          הפיד ממתין לכיול
        </p>
        <h2 className="font-display text-xl font-bold text-foreground mt-2">
          עוד אין לנו ממה ללמוד
        </h2>
        <p className="text-sm text-text-secondary leading-relaxed mt-2 max-w-sm">
          הפיד שלך ריק בכוונה — אנחנו לא ממלאים אותו ברעש גנרי. דרגו כמה
          כותרות לדוגמה והמערכת תתחיל להציף רק את מה שחשוב לך. כל משוב בהמשך
          ימשיך לחדד את התמונה.
        </p>
        <Link
          to="/calibration"
          className="mt-6 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 transition-colors"
        >
          <SlidersHorizontal size={15} />
          לכיול הפיד
        </Link>
        <p className="text-xs text-text-dim mt-4">
          הכיול זמין תמיד — גם אחר כך, מעמוד ההעדפות.
        </p>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center justify-center text-center py-24 px-4">
      <SignalMark className="scale-[2.2] mb-6" />
      <p className="text-[11px] font-semibold tracking-wide text-signal-feed">ממתין לאות</p>
      <h2 className="font-display text-xl font-bold text-foreground mt-2">אין סיגנלים חדשים</h2>
      <p className="text-sm text-text-secondary leading-relaxed mt-2 max-w-sm">
        המערכת סורקת את המקורות ברקע — סיפורים שרלוונטיים לפרופיל שלך יופיעו כאן.
      </p>
    </div>
  );
}
