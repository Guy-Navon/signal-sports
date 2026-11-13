import React from "react";
import { cn } from "@/lib/utils";
import "./signal-ui.css";

// Logo lockup of the new consumer UI (#462): the slanted accent stroke and the
// word "סיגנל". Renders inside a `.signal-ui` scope; the size follows the font
// size it is given. Not wired into the shell yet; shell/SignalMark stays the
// current Orbit logo until the shell migrates.
export default function SignalWordmark({ className = "" }) {
  return (
    <span className={cn("sg-wordmark", className)}>
      <i className="sg-wordmark__stroke" aria-hidden="true" />
      סיגנל
    </span>
  );
}
