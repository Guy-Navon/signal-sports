import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Compass } from "lucide-react";
import { Button } from "@/components/ui/button";
import { completeMeOnboarding } from "@/api/client";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/context/AuthContext";
import AuthScene from "@/pages/AuthScene";

// The welcome screen (User Platform PR 4, #52) — the first thing a brand-new
// account sees. Product voice: explain signal-over-noise, invite into
// Calibration V2, keep skipping possible at every step. Rendered outside the
// AppShell (full-canvas product moment, AuthScene stage).
export default function Onboarding() {
  const navigate = useNavigate();
  const auth = useAuth();
  const { activeProfile } = useApp();
  const [skipping, setSkipping] = useState(false);
  const [error, setError] = useState(null);

  const name =
    activeProfile?.displayName ||
    (auth.user?.email ? auth.user.email.split("@")[0] : "");

  async function skip() {
    setSkipping(true);
    setError(null);
    try {
      await completeMeOnboarding();
      await auth.refreshSession();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err?.message || "משהו השתבש");
      setSkipping(false);
    }
  }

  return (
    <AuthScene
      kicker="ברוכים הבאים לסיגנל"
      title={name ? `נעים להכיר, ${name}` : "נעים להכיר"}
    >
      <div className="space-y-4 text-center">
        <p className="text-sm text-text-secondary leading-relaxed">
          סיגנל הוא לא עוד אתר ספורט: המערכת סורקת את כל המקורות, מבינה מה כל
          כתבה אומרת — ומציגה לך רק את מה ששווה את תשומת הלב שלך.
        </p>
        <p className="text-sm text-text-secondary leading-relaxed">
          מתחילים בלספר לנו אחרי מה אתם עוקבים — ענפים, ליגות, קבוצות ושחקנים.
          אחר כך כמה כותרות קצרות יכיילו את הניואנסים. שתי דקות — והפיד שלך
          יתחיל לדבר בשפה שלך. אפשר לעצור באמצע ולחזור מכל מכשיר.
        </p>

        {error && (
          <p role="alert" className="text-sm text-signal-hidden">{error}</p>
        )}

        <div className="pt-2 space-y-3">
          <Button
            className="w-full gap-2"
            onClick={() => navigate("/interests")}
          >
            <Compass size={15} />
            בחרו מה מעניין אתכם
          </Button>
          <button
            type="button"
            onClick={skip}
            disabled={skipping}
            className="w-full text-sm text-text-secondary hover:text-foreground transition-colors disabled:opacity-50"
          >
            {skipping ? "רק רגע…" : "דלגו בינתיים — אכייל אחר כך"}
          </button>
        </div>

        <p className="text-xs text-text-dim leading-relaxed pt-2">
          בלי לבחור תחומי עניין הפיד יישאר ריק בכוונה — אנחנו לא מציגים רעש
          גנרי. הבחירה והכיול יחכו לך בלחיצה אחת, ותמיד אפשר לחדד מחדש.
        </p>
      </div>
    </AuthScene>
  );
}
