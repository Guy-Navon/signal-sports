import React from "react";
import { Clock, Trophy } from "lucide-react";
import PageHeader from "@/components/shared/PageHeader";

export default function Results() {
  return (
    <div className="product-page">
      <PageHeader
        title="תוצאות"
        icon={Trophy}
        subtitle="לוח התוצאות האישי יכלול רק קבוצות, שחקנים ותחרויות שנמצאים במעקב."
      />
      <section className="ledger-panel grid min-h-[22rem] place-items-center p-8 text-center">
        <div className="max-w-md">
          <span className="mx-auto inline-flex h-12 w-12 items-center justify-center bg-foreground text-background">
            <Clock size={20} />
          </span>
          <p className="eyebrow mt-5 text-signal-push">COMING NEXT / בקרוב</p>
          <h2 className="mt-2 font-display text-3xl font-bold text-foreground">לוח בלי רעש</h2>
          <p className="mt-3 text-sm leading-relaxed text-text-secondary">
            תוצאות מעניינות בלבד, בלי להציף אותך במשחקים שלא מעניינים אותך. עד שהלוח
            יחובר לנתוני אמת, המסך נשאר שקוף לגבי הסטטוס ולא מציג תוצאות מדומות.
          </p>
        </div>
      </section>
    </div>
  );
}
