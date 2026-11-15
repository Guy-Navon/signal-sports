import React from "react";
import { Link } from "react-router-dom";
import { FEED_LOAD_ERROR } from "@/components/feed/feedLoadModel";
import "@/components/signal-ui/signal-ui.css";
import "./signal-feed.css";

// The feed body's other states (feedBodyState), in the new look (#464). Each
// opens its own .signal-ui scope, like SignalFeedView.

/** While the first feed request is in flight (backend mode only). */
export function SignalFeedLoading() {
  return (
    <div className="signal-ui sg-feed">
      <div className="sg-in sg-skeleton" aria-busy="true" aria-label="טוען את הפיד שלך">
        <i />
        <i />
        <i />
        <i />
        <i />
      </div>
    </div>
  );
}

/** The feed request failed and nothing is on screen yet. */
export function SignalFeedError({ onRetry, status = null }) {
  return (
    <div className="signal-ui sg-feed">
      {status && <div className="sg-in sg-status">{status}</div>}
      <div className="sg-in sg-state" role="alert">
        <h2>{FEED_LOAD_ERROR.title}</h2>
        <p>{FEED_LOAD_ERROR.message}</p>
        <button type="button" className="sg-more" onClick={onRetry}>
          {FEED_LOAD_ERROR.retryLabel}
        </button>
      </div>
    </div>
  );
}

/**
 * Zero visible stories. Two cases (User Platform PR 4, #52; Explicit Interests, #82):
 * - default: sources are quiet, the profile is set up;
 * - calibrate: the user skipped both interest selection and calibration, so the
 *   feed is intentionally empty (no generic fallback feed) and this is the
 *   persistent "tell us what you follow" call to action.
 */
export function SignalFeedEmpty({ variant = "default", status = null }) {
  if (variant === "calibrate") {
    return (
      <div className="signal-ui sg-feed">
        {status && <div className="sg-in sg-status">{status}</div>}
        <div className="sg-in sg-state">
          <h2>עוד אין לנו ממה ללמוד</h2>
          <p>
            הפיד שלך ריק בכוונה — אנחנו לא ממלאים אותו ברעש גנרי. ספרו לנו אחרי מה אתם
            עוקבים, כיילו בכמה כותרות — והמערכת תתחיל להציף רק את מה שחשוב לך.
          </p>
          <Link to="/interests" className="sg-more">
            בחרו תחומי עניין
          </Link>
          <p>הבחירה והכיול זמינים תמיד — גם אחר כך, מעמוד ההעדפות.</p>
        </div>
      </div>
    );
  }
  return (
    <div className="signal-ui sg-feed">
      {status && <div className="sg-in sg-status">{status}</div>}
      <div className="sg-in sg-state">
        <h2>אין סיגנלים חדשים</h2>
        <p>המערכת סורקת את המקורות ברקע — סיפורים שרלוונטיים לפרופיל שלך יופיעו כאן.</p>
      </div>
    </div>
  );
}
