import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";

// The consumer shell's connection-error strip (accessibility pass, milestone
// 15). The shared ErrorState strip stays as it is for Ops; on the consumer
// grounds its red-on-pink text measured 2.3–3.9:1 and its retry button was
// 22px tall. Here the text is --sg-ink / --sg-dim, the alert colour is only a
// non-text edge and icon, the retry button is a 44px target on a phone, and
// the strip is announced (role="alert").
export default function ConnectionStrip({ title, message = null, retryLabel = "נסו שוב", onRetry = null }) {
  return (
    <div role="alert" className="sg-conn">
      <div className="sg-gutter">
        <div className="sg-container sg-conn__inner">
          <AlertCircle size={16} aria-hidden="true" className="sg-conn__icon" />
          <p className="sg-conn__text">
            <b>{title}</b>
            {message && <> <span className="sg-conn__msg">{message}</span></>}
          </p>
          {onRetry && (
            <button type="button" className="sg-conn__retry" onClick={onRetry}>
              <RefreshCw size={14} aria-hidden="true" />
              {retryLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
