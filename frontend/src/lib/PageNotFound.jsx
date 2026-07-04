import { useLocation, useNavigate } from "react-router-dom";
import { ArrowUpLeft } from "lucide-react";
import SignalMark from "@/components/shell/SignalMark";

// "אין אות" — no signal. The one page in the app that isn't wrapped in the
// product shell, so it carries its own small atmosphere rather than
// borrowing one — same visual language (mesh glow, court-line whisper,
// SignalMark), scaled down to a single quiet moment.
export default function PageNotFound() {
  const location = useLocation();
  const navigate = useNavigate();
  const pageName = location.pathname.substring(1);

  return (
    <div
      dir="rtl"
      className="relative min-h-screen flex items-center justify-center p-6 overflow-hidden bg-background"
    >
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 50% 45% at 50% 35%, hsl(var(--signal-hidden) / 0.06), transparent 65%)",
        }}
      />
      <svg
        aria-hidden
        viewBox="0 0 600 600"
        fill="none"
        className="absolute inset-0 m-auto h-[130%] w-auto text-foreground opacity-[0.03]"
      >
        <circle cx="300" cy="300" r="260" stroke="currentColor" strokeWidth="1.5" />
        <circle cx="300" cy="300" r="160" stroke="currentColor" strokeWidth="1" />
      </svg>

      <div className="relative max-w-md w-full text-center">
        <div className="flex justify-center mb-5 opacity-40 grayscale">
          <SignalMark className="scale-125" />
        </div>

        <p className="text-[11px] font-semibold tracking-wide text-signal-hidden/90">אין אות</p>

        <h1 className="font-display text-3xl font-bold text-foreground mt-2">
          הדף הזה לא משדר
        </h1>

        <p className="text-sm text-text-secondary leading-relaxed mt-3">
          {pageName ? (
            <>
              הכתובת <span className="font-medium text-foreground" dir="ltr">/{pageName}</span> לא
              קיימת במערכת.
            </>
          ) : (
            "הכתובת הזו לא קיימת במערכת."
          )}{" "}
          ייתכן שהיא הוסרה, או שהקישור פשוט שגוי.
        </p>

        <button
          onClick={() => navigate("/")}
          className="inline-flex items-center gap-2 mt-6 px-4 py-2 text-sm font-medium rounded-full border border-signal-high/40 text-signal-high hover:bg-signal-high/10 hover:border-signal-high/60 transition-colors"
        >
          חזרה למהדורה
          <ArrowUpLeft size={14} />
        </button>
      </div>
    </div>
  );
}
