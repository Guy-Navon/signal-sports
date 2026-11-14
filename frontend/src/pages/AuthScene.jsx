import React from "react";
import { Link } from "react-router-dom";
import SignalWordmark from "@/components/signal-ui/SignalWordmark";
import { GroundProvider, useGround } from "@/components/signal-ui/useGround";
import "./account-auth.css";

// Utility routes own their Signal scope; they stay outside both app shells.
// They follow the ground the reader picked in the shell (stored per device,
// read before the first paint), white when nothing is stored (#504).
export default function AuthScene(props) {
  return <GroundProvider><AuthSceneContent {...props} /></GroundProvider>;
}

function AuthSceneContent({ kicker = null, title, children }) {
  const { ground } = useGround();
  return (
    <div dir="rtl" className="signal-ui sg-auth-scene" data-ground={ground}>
      <div className="sg-auth-scene__bar" aria-hidden="true" />
      <header className="sg-auth-scene__masthead">
        <Link to="/" aria-label="סיגנל, לפיד" className="sg-auth-scene__brand">
          <SignalWordmark />
        </Link>
      </header>
      <main className="sg-auth-scene__column">
        <header className="sg-auth-scene__heading">
          {kicker && <p className="sg-auth-scene__kicker">{kicker}</p>}
          <h1>{title}</h1>
        </header>
        {children}
      </main>
    </div>
  );
}
