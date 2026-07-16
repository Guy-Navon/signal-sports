import React, { useState, useEffect, useCallback } from "react";
import { Bell, RefreshCw, AlertTriangle } from "lucide-react";
import { getNotificationsHealth, getNotificationEvents } from "@/api/client";
import SectionCard from "@/components/shared/SectionCard";
import { consoleButton, consoleAlert } from "@/components/ops/consoleStyles";

// M7-8 (#154): Telegram push-pilot observability. Read-only: health counters,
// recent notification decisions/deliveries, and the unknown-outcome review
// list. Deliberately NOT a notification-settings surface, and no secret
// (token / chat id) ever reaches this panel — the API never returns them.

// Pure helpers live in @/api/normalizers (node-tested, mirroring
// SchedulerPanel's convention).
import {
  NOTIFICATION_STATUS_LABELS as STATUS_LABELS,
  manualReviewEvents,
  notificationsStateLabel,
} from "@/api/normalizers";

function formatDateTime(isoStr) {
  if (!isoStr) return "—";
  try {
    return new Date(isoStr).toLocaleString("he-IL", {
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

export default function NotificationsPanel({ isBackendMode }) {
  const [health, setHealth] = useState(null);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!isBackendMode) return;
    try {
      const [h, e] = await Promise.all([
        getNotificationsHealth(),
        getNotificationEvents(10),
      ]);
      setHealth(h);
      setEvents(e);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, [isBackendMode]);

  useEffect(() => {
    load();
  }, [load]);

  if (!isBackendMode) {
    return (
      <SectionCard title="התראות טלגרם" icon={Bell}>
        <p className="text-sm text-text-dim">זמין במצב שרת בלבד.</p>
      </SectionCard>
    );
  }

  const unknownEvents = manualReviewEvents(events);
  const stateLabel = notificationsStateLabel(health);

  return (
    <SectionCard
      title="התראות טלגרם (פיילוט)"
      icon={Bell}
      action={
        <button type="button" onClick={load} className={consoleButton}
                data-testid="notifications-refresh">
          <RefreshCw className="w-3.5 h-3.5" />
          רענון
        </button>
      }
    >
      {error && <div className={consoleAlert}>{error}</div>}

      {health && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm" data-testid="notifications-health">
          <div>
            <span className="text-text-dim">מצב: </span>
            <span className={stateLabel.degraded ? "text-signal-push"
                             : health.enabled ? "text-signal-high" : "text-text-dim"}>
              {stateLabel.label}
            </span>
          </div>
          <div><span className="text-text-dim">נשלחו: </span>{health.sent}</div>
          <div><span className="text-text-dim">ממתינים: </span>{health.pending}</div>
          <div>
            <span className="text-text-dim">לא ידוע: </span>
            <span className={health.unknown > 0 ? "text-signal-hidden font-semibold" : ""}>
              {health.unknown}
            </span>
          </div>
          <div className="col-span-2">
            <span className="text-text-dim">משלוח מאושר אחרון: </span>
            {formatDateTime(health.last_confirmed_delivery_at)}
          </div>
          <div className="col-span-2">
            <span className="text-text-dim">כשלונות רצופים: </span>
            {health.consecutive_delivery_failures}
          </div>
        </div>
      )}

      {unknownEvents.length > 0 && (
        <div className={`${consoleAlert} flex items-start gap-2`} data-testid="unknown-review">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <div className="font-semibold">דורש בדיקה ידנית ({unknownEvents.length})</div>
            <div className="text-xs">
              תוצאת משלוח לא ידועה לא נשלחת שוב אוטומטית — יש לבדוק אם ההודעה הגיעה.
            </div>
          </div>
        </div>
      )}

      {events.length > 0 && (
        <div className="space-y-1.5" data-testid="notification-events">
          <h3 className="text-xs font-semibold text-text-secondary">אירועים אחרונים</h3>
          {events.map((e) => {
            const status = STATUS_LABELS[e.status] || { label: e.status, className: "" };
            return (
              <div key={e.id} className="flex items-center justify-between gap-2 text-xs border-b border-white/5 pb-1">
                <span className="truncate flex-1" title={e.canonical_headline}>
                  {e.canonical_headline}
                </span>
                <span className="text-text-dim shrink-0">{e.source}</span>
                <span className={`shrink-0 ${status.className}`}>{status.label}</span>
                <span className="text-text-dim shrink-0">{formatDateTime(e.created_at)}</span>
              </div>
            );
          })}
        </div>
      )}

      {health && events.length === 0 && (
        <p className="text-sm text-text-dim">אין אירועי התראה עדיין.</p>
      )}
    </SectionCard>
  );
}
