import React from "react";
import { Link } from "react-router-dom";
import { Compass } from "lucide-react";
import SignalMark from "@/components/shell/SignalMark";

// The zero-articles moment. Two species (User Platform PR 4, #52; updated
// by Explicit Interests, #82):
// - default: sources are quiet, the profile is set up;
// - calibrate: the user skipped BOTH interest selection and calibration
//   (empty ProfileV2) — the feed is INTENTIONALLY empty (no generic
//   fallback feed) and this is the persistent "tell us what you follow"
//   CTA. A user with explicit follows but no calibration gets a real feed
//   and never sees this state.
export default function EditionEmptyState({ variant = "default" }) {
  if (variant === "calibrate") {
    return (
      <div className="flex flex-col items-center justify-center text-center py-24 px-4">
        <SignalMark className="scale-[2.2] mb-6" />
        <p className="text-[11px] font-semibold tracking-wide text-signal-ai">
          הפיד ממתין לך
        </p>
        <h2 className="font-display text-xl font-bold text-foreground mt-2">
          עוד אין לנו ממה ללמוד
        </h2>
        <p className="text-sm text-text-secondary leading-relaxed mt-2 max-w-sm">
          הפיד שלך ריק בכוונה — אנחנו לא ממלאים אותו ברעש גנרי. ספרו לנו אחרי
          מה אתם עוקבים, כיילו בכמה כותרות — והמערכת תתחיל להציף רק את מה
          שחשוב לך.
        </p>
        <Link
          to="/interests"
          className="mt-6 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 transition-colors"
        >
          <Compass size={15} />
          בחרו תחומי עניין
        </Link>
        <p className="text-xs text-text-dim mt-4">
          הבחירה והכיול זמינים תמיד — גם אחר כך, מעמוד ההעדפות.
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
