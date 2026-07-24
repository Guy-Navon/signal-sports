import React from "react";
import SignalMark from "@/components/shell/SignalMark";

// Authentication and welcome share a split editorial cover: the product
// promise on an ink field and the task itself on paper. The composition stacks
// cleanly on small screens and does not depend on decorative photography.
export default function AuthScene({ kicker, title, children }) {
  return (
    <div dir="rtl" className="min-h-screen bg-background lg:grid lg:grid-cols-[minmax(360px,0.8fr)_1.2fr]">
      <aside className="relative overflow-hidden bg-foreground p-6 text-background sm:p-10 lg:flex lg:min-h-screen lg:flex-col lg:justify-between lg:p-12">
        <div
          aria-hidden
          className="absolute inset-0 opacity-30"
          style={{
            background:
              "linear-gradient(90deg, hsl(var(--background) / .08) 1px, transparent 1px) 0 0 / 72px 100%, radial-gradient(circle at 10% 20%, hsl(var(--signal-push) / .45), transparent 15rem)",
          }}
        />

        <div className="relative flex items-center gap-3">
          <SignalMark />
          <span className="font-display text-2xl font-bold">סיגנל</span>
          <span className="font-mono text-[8px] font-bold tracking-[0.2em] text-background/45">
            SPORTS DESK
          </span>
        </div>

        <div className="relative my-14 max-w-xl lg:my-8">
          <span className="inline-block bg-signal-push px-2 py-1 font-mono text-[9px] font-bold tracking-[0.16em] text-white">
            YOUR SIGNAL. ZERO NOISE.
          </span>
          <h2 className="mt-5 text-balance font-display text-[2.8rem] font-bold leading-[0.98] tracking-[-0.03em] sm:text-[4rem] lg:text-[4.75rem]">
            לא כל מה שקרה.
            <br />
            <span className="text-signal-high">רק מה שחשוב לך.</span>
          </h2>
          <p className="mt-6 max-w-md text-sm leading-relaxed text-background/58 sm:text-base">
            חדר חדשות אישי שסורק, מקבץ ומדרג את עולם הספורט לפי תחומי העניין שלך.
          </p>
        </div>

        <div className="relative hidden grid-cols-3 border-t border-background/20 pt-5 text-xs text-background/52 sm:grid">
          <div>
            <p className="font-mono text-[8px] tracking-[0.15em]">01 / SCAN</p>
            <p className="mt-1 text-background/78">סורקים מקורות</p>
          </div>
          <div>
            <p className="font-mono text-[8px] tracking-[0.15em]">02 / CLUSTER</p>
            <p className="mt-1 text-background/78">מאחדים דיווחים</p>
          </div>
          <div>
            <p className="font-mono text-[8px] tracking-[0.15em]">03 / RANK</p>
            <p className="mt-1 text-background/78">מדרגים בשבילך</p>
          </div>
        </div>
      </aside>

      <main className="flex min-h-[58vh] items-center justify-center px-5 py-10 sm:px-10 lg:min-h-screen lg:py-14">
        <div className="w-full max-w-md">
          <div className="editorial-rule-heavy pt-3">
            <p className="eyebrow text-signal-push">{kicker}</p>
            <h1 className="mt-2 font-display text-[2.6rem] font-bold leading-none tracking-[-0.02em] text-foreground sm:text-[3.25rem]">
              {title}
            </h1>
          </div>
          <div className="mt-8">{children}</div>
        </div>
      </main>
    </div>
  );
}
