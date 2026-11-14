import React, { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import AffinityLevel from "./AffinityLevel";
import { EVENT_TYPE_HE } from "@/components/feed/storyLabels";
import { calibrationSummary, calibrationScopeLabel } from "./calibrationSummaryModel";

export default function CalibrationSummary({ result, onContinueRating }) {
  const headingRef = useRef(null);
  const { scopes, events, scopeCount, eventCount } = calibrationSummary(result);
  useEffect(() => { headingRef.current?.focus(); }, []);

  return (
    <section className="sg-calibration-summary sg-form-section" aria-labelledby="calibration-summary-title">
      <h2 id="calibration-summary-title" ref={headingRef} tabIndex={-1}>
        <CheckCircle2 size={18} aria-hidden="true" /> מה השתנה בהעדפות שלך
      </h2>
      <p className="sg-form-success" role="status">הכיוונון נשמר — הפיד מחושב לפי ההעדפות המעודכנות.</p>
      <p className="sg-form-note">
        אלה הרמות שנשמרו מהכיוונון. אין כאן השוואה לרמות הקודמות;
        בחירות מפורשות שלך ממשיכות לגבור עליהן.
      </p>
      {scopeCount !== null && eventCount !== null && (
        <p className="sg-form-note">נשמרו העדפות ל־<b>{scopeCount}</b> תחומים ו־<b>{eventCount}</b> התאמות לסוגי חדשות.</p>
      )}
      {scopes.length > 0 && (
        <ul className="sg-form-list" aria-label="רמות עניין שנשמרו מהכיוונון">
          {scopes.map((entry) => (
            <li key={`${entry.scope}:${entry.target_id}`}>
              <bdi dir="auto">{calibrationScopeLabel(entry.target_id)}</bdi>
              <AffinityLevel level={entry.level} />
            </li>
          ))}
        </ul>
      )}
      {events.length > 0 && (
        <ul className="sg-form-list" aria-label="התאמות לסוגי חדשות שנשמרו">
          {events.map((entry) => (
            <li key={`${entry.scope_ref}:${entry.event_type}`}>
              <bdi dir="auto">{EVENT_TYPE_HE[entry.event_type] ?? entry.event_type}</bdi>
              <bdi dir="auto">{entry.scope_ref ? calibrationScopeLabel(entry.scope_ref) : "כל התחומים"}</bdi>
              <span dir="ltr">{entry.delta > 0 ? `+${entry.delta}` : entry.delta}</span>
            </li>
          ))}
        </ul>
      )}
      {scopes.length === 0 && events.length === 0 && (
        <p className="sg-form-note">לא הוחזרו רמות כיוונון להצגה. הדירוגים נשמרו; אפשר לדרג עוד כותרות ולבדוק את ההעדפות שלך.</p>
      )}
      <div className="sg-form-actions">
        <Link to="/" className="sg-form-button sg-form-button--primary">המשך לפיד שלי</Link>
        <Link to="/preferences" className="sg-form-link">מה אני עוקב</Link>
        <Link to="/preferences/learned" className="sg-form-link">מה המערכת למדה</Link>
        <button type="button" onClick={onContinueRating} className="sg-form-link">המשך דירוג</button>
      </div>
    </section>
  );
}
