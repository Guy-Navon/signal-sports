import React from "react";
import SignalWordmark from "@/components/signal-ui/SignalWordmark";
import { CONSUMER_NAV_ICONS, RESULTS_ICON_CANDIDATES } from "@/components/shell/navIcons";
import { consumerIconKey, consumerNavItems } from "@/components/shell/productShellModel";
import { GROUNDS } from "@/components/signal-ui/ground";
import { useGround } from "@/components/signal-ui/useGround";
import "@/components/shell/shell.css";

// Navigation lab (#491), lab.html?page=nav: the three results-icon candidates
// in the phone's compact bar and at large size, the whole consumer icon set,
// and the logo lockup on navy and on every ground. Dev-only; outside the main
// and demo bundles.

const DEFAULT_RESULTS = CONSUMER_NAV_ICONS.results;

function CompactBar({ resultsIcon }) {
  return (
    <div className="lab-navbar sg-on-top">
      <span className="lab-navbar__brand"><SignalWordmark /></span>
      <div className="lab-navbar__tabs">
        {consumerNavItems().map((item, index) => {
          const key = consumerIconKey(item.path);
          const Icon = key === "results" ? resultsIcon : CONSUMER_NAV_ICONS[key] ?? item.icon;
          return (
            <span key={item.path} className="lab-navbar__tab" data-current={index === 0 ? "" : undefined}>
              <Icon size={20} strokeWidth={2} aria-hidden="true" />
              {item.label}
            </span>
          );
        })}
      </div>
      <span className="lab-navbar__avatar" aria-hidden="true">G</span>
    </div>
  );
}

export default function NavLab() {
  const { ground } = useGround();
  return (
    <main className="signal-ui lab-page lab-nav" data-ground={ground}>
      <header className="lab-nav__intro">
        <h1>ניווט: אייקון התוצאות</h1>
        <p className="lab-dim">
          שלוש הצעות לאייקון לוח תוצאות, על רשת 24 פיקסלים ובקו של Lucide (עובי 2, קצוות מעוגלים),
          כמו שלושת האייקונים שלידן. ברירת המחדל מסומנת. אפשר לפתוח את הדף עם ?ground=dark או ?ground=soft.
        </p>
      </header>

      <section className="lab-nav__grid" aria-label="הצעות לאייקון התוצאות">
        {RESULTS_ICON_CANDIDATES.map(({ id, label, Icon }) => (
          <figure key={id} className="lab-nav__card" data-candidate={id}>
            <figcaption>
              <b>{label}</b> <code dir="ltr">{id}</code>
              {Icon === DEFAULT_RESULTS && <span className="lab-nav__default">ברירת מחדל</span>}
            </figcaption>
            <CompactBar resultsIcon={Icon} />
            <div className="lab-nav__sizes">
              {[20, 24, 48].map((size) => (
                <span key={size} className="lab-nav__size">
                  <Icon size={size} aria-hidden="true" />
                  <code dir="ltr">{size}px</code>
                </span>
              ))}
              <span className="lab-nav__size lab-nav__size--navy sg-on-top">
                <Icon size={48} aria-hidden="true" />
              </span>
            </div>
          </figure>
        ))}
      </section>

      <section className="lab-nav__set" aria-label="סט האייקונים">
        <h2 className="lab-h">הסט כולו</h2>
        <ul>
          {consumerNavItems().map((item) => {
            const Icon = CONSUMER_NAV_ICONS[consumerIconKey(item.path)] ?? item.icon;
            return (
              <li key={item.path}>
                <Icon size={32} aria-hidden="true" />
                <span>{item.label}</span>
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-label="הלוגו">
        <h2 className="lab-h">הלוגו</h2>
        <div className="lab-nav__logos">
          <span className="lab-nav__logo lab-nav__logo--navy sg-on-top"><SignalWordmark /></span>
          {GROUNDS.map(({ id, label }) => (
            <span key={id} className="signal-ui lab-nav__logo" data-ground={id}>
              <SignalWordmark />
              <small className="lab-dim">{label}</small>
            </span>
          ))}
        </div>
      </section>
    </main>
  );
}
