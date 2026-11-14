import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Compass, ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import { completeMeOnboarding } from "@/api/client";
import { useApp } from "@/context/AppContext";
import { useAuth } from "@/context/AuthContext";
import SignalWordmark from "@/components/signal-ui/SignalWordmark";
import "@/components/signal-ui/signal-ui.css";
import "@/components/preferences/personalization.css";
import "./onboarding.css";

// The welcome screen (User Platform PR 4, #52) — the first thing a brand-new
// account sees. Product voice: explain signal-over-noise, invite into
// Calibration V2, keep skipping possible at every step. Rendered outside the
// AppShell (a standalone Signal UI welcome surface).
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
    <main className="signal-ui sg-welcome">
      <header className="sg-welcome__masthead"><Link to="/" aria-label="סיגנל, לפיד"><SignalWordmark /></Link></header>
      <div className="sg-welcome__body">
        <p className="sg-personalization__eyebrow">ברוכים הבאים לסיגנל</p>
        <h1>{name ? <>נעים להכיר, <bdi dir="auto">{name}</bdi></> : "נעים להכיר"}</h1>
        <p className="sg-welcome__intro">
          סיגנל הוא לא עוד אתר ספורט: המערכת סורקת את כל המקורות, מבינה מה כל
          כתבה אומרת — ומציגה לך רק את מה ששווה את תשומת הלב שלך.
        </p>
        <p className="sg-form-note">
          מתחילים בלספר לנו אחרי מה אתם עוקבים — ענפים, ליגות, קבוצות ושחקנים.
          אחר כך כמה כותרות קצרות יכיילו את הניואנסים. שתי דקות — והפיד שלך
          יתחיל לדבר בשפה שלך. אפשר לעצור באמצע ולחזור מכל מכשיר.
        </p>

        <ol className="sg-welcome__steps" aria-label="איך מתחילים">
          <li><span aria-hidden="true">01</span><div><h2>בוחרים מה מעניין</h2><p>ענפים, ליגות, קבוצות ושחקנים.</p></div></li>
          <li><span aria-hidden="true">02</span><div><h2>מכוונים את העוצמה</h2><p>כמה כותרות קצרות, לפי ההעדפות שלך.</p></div></li>
          <li><span aria-hidden="true">03</span><div><h2>קוראים את הפיד שלך</h2><p>אפשר לחדד את הבחירות בכל שלב.</p></div></li>
        </ol>

        {error && (
          <p role="alert" className="sg-form-error">{error}</p>
        )}

        <div className="sg-welcome__actions">
          <button
            type="button"
            className="sg-form-button sg-form-button--primary"
            onClick={() => navigate("/preferences")}
          >
            <Compass size={15} />
            בחרו מה מעניין אתכם
            <ArrowLeft size={16} aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={skip}
            disabled={skipping}
            className="sg-form-link"
          >
            {skipping ? "רק רגע…" : "דלגו בינתיים — אכייל אחר כך"}
          </button>
        </div>

        <p className="sg-form-note">
          בלי לבחור תחומי עניין הפיד יישאר ריק בכוונה — אנחנו לא מציגים רעש
          גנרי. הבחירה והכיול יחכו לך בלחיצה אחת, ותמיד אפשר לחדד מחדש.
        </p>
      </div>
    </main>
  );
}
