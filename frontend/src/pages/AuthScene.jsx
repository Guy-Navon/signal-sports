import React from "react";
import { Link } from "react-router-dom";
import SignalWordmark from "@/components/signal-ui/SignalWordmark";
import "./account-auth.css";

// Utility routes own their Signal scope; they stay outside both app shells.
export default function AuthScene({ kicker = null, title, children }) {
  return (
    <div dir="rtl" className="signal-ui sg-auth-scene">
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
