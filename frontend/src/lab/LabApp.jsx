import React, { useEffect, useRef, useState } from "react";
import SignalStrength from "@/components/signal-ui/SignalStrength";
import SignalWordmark from "@/components/signal-ui/SignalWordmark";
import { getDecisionConfig } from "@/components/feed/decisionConfig";
import "@/components/signal-ui/signal-ui.css";
import "./lab.css";
import FeedLab from "./FeedLab";
import MotionLab from "./MotionLab";
import NavLab from "./NavLab";
import FilterLab from "./FilterLab";
import { GROUNDS } from "@/components/signal-ui/ground";
import { GroundProvider } from "@/components/signal-ui/useGround";

const TOKENS = [
  "bg", "band", "card", "ink", "dim", "line", "acc", "tint", "top", "top-fg",
  "slab", "slab-fg", "slab-dim", "hot", "hot-fg", "off", "t1", "t2", "t3", "t4",
];

const DECISIONS = ["low_feed", "feed", "high_feed", "push"];

function TokenSwatches() {
  const listRef = useRef(null);
  const [values, setValues] = useState({});

  // Read the resolved values back from the ground, so the specimen shows what
  // the CSS actually produced rather than a copy of it.
  useEffect(() => {
    const style = getComputedStyle(listRef.current);
    setValues(Object.fromEntries(TOKENS.map((t) => [t, style.getPropertyValue(`--sg-${t}`).trim()])));
  }, []);

  return (
    <ul className="lab-swatches" ref={listRef}>
      {TOKENS.map((token) => (
        <li key={token}>
          <span className="lab-swatch" style={{ background: `var(--sg-${token})` }} />
          <code dir="ltr">--sg-{token}</code>
          <code dir="ltr" className="lab-dim">{values[token]}</code>
        </li>
      ))}
    </ul>
  );
}

function Ground({ id, label }) {
  return (
    <section className="signal-ui lab-ground" data-ground={id === "light" ? undefined : id}>
      <header className="lab-ground__head">
        <SignalWordmark className="lab-wordmark" />
        <span className="lab-dim">רקע: {label}{id === "light" && " (ברירת מחדל)"}</span>
      </header>

      <h2 className="lab-h">צבעים</h2>
      <TokenSwatches />

      <h2 className="lab-h">טיפוגרפיה</h2>
      <div className="lab-slab">
        <p className="lab-lead sg-lead-title">דני אבדיה הועבר לקבוצה חדשה</p>
        <p className="lab-note">Karantina 700, כותרת ה-push בלבד</p>
      </div>
      <p className="lab-type" style={{ fontSize: 21, fontWeight: 600 }}>
        מכבי תל אביב בשיחות מתקדמות עם רכז יורוליג (Assistant 600 · 21)
      </p>
      <p className="lab-type" style={{ fontSize: 17, fontWeight: 400 }}>
        טקסט רץ: למה אצלך? כי ביקשת לדעת על כל מו״מ של מכבי. 1234567890 (Assistant 400 · 17)
      </p>
      <p className="lab-type lab-dim" style={{ fontSize: 13.5 }}>
        ספורט 5 · לפני 12 דק׳ · יורוליג (Assistant 400 · 13.5, dim)
      </p>
      <p className="lab-type" style={{ fontSize: 18, fontWeight: 800 }}>עוד בפיד שלך (Assistant 800 · 18)</p>

      <h2 className="lab-h">עוצמת סיגנל</h2>
      <ul className="lab-marks">
        {DECISIONS.map((decision) => (
          <li key={decision}>
            <SignalStrength decision={decision} />
            <span>{getDecisionConfig(decision).label}</span>
            <code dir="ltr" className="lab-dim">{decision}</code>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function LabApp() {
  // lab.html?page=feed opens the feed lab (#464), ?page=motion the motion lab
  // (#467), ?page=nav the navigation lab (#491), ?page=filters the filter-bar
  // lab (#483); the default is the specimen
  // (#462).
  const params = new URLSearchParams(window.location.search);
  const page = params.get("page");
  const initialGround = params.get("ground") || undefined;
  if (page === "feed") return <GroundProvider initialGround={initialGround}><FeedLab /></GroundProvider>;
  if (page === "motion") return <GroundProvider initialGround={initialGround}><MotionLab /></GroundProvider>;
  if (page === "filters") return <GroundProvider initialGround={initialGround}><FilterLab /></GroundProvider>;
  if (page === "nav") return <GroundProvider initialGround={initialGround}><NavLab /></GroundProvider>;
  return (
    <main className="lab-page">
      {GROUNDS.map((ground) => (
        <Ground key={ground.id} {...ground} />
      ))}
    </main>
  );
}
