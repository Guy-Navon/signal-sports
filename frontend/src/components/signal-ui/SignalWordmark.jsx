import React from "react";
import { cn } from "@/lib/utils";
import "./signal-ui.css";

// Logo lockup of the consumer UI (#491): the app icon's three rounded bars
// and the word "סיגנל". Renders inside a `.signal-ui` scope; the size follows
// the font size it is given, the word takes the current text colour, and the
// bars take the --sg-logo-* tokens of the ground (navy-header colours inside
// `.sg-on-top`). The bars are decoration: the word is the accessible text.
export default function SignalWordmark({ className = "" }) {
  return (
    <span className={cn("sg-wordmark", className)}>
      <span className="sg-wordmark__bars" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      סיגנל
    </span>
  );
}
