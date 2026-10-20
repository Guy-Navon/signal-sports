import React, { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { authVerificationResend } from "@/api/client";
import {
  resendSecondsLeft,
  verificationErrorMessage,
} from "@/pages/emailVerification";

// "Send the link again" for a pending registration. The credentials come from
// the form the person just submitted and live only in memory (never stored).
export default function ResendVerification({ email, password, initialSentAt = null }) {
  const [sentAt, setSentAt] = useState(initialSentAt);
  const [now, setNow] = useState(() => Date.now());
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState(null);
  const secondsLeft = resendSecondsLeft(sentAt, now);

  useEffect(() => {
    if (secondsLeft <= 0) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [secondsLeft]);

  async function onResend() {
    if (sending || secondsLeft > 0) return;
    setSending(true);
    setNotice(null);
    try {
      const result = await authVerificationResend(email, password);
      setSentAt(Date.now());
      setNow(Date.now());
      setNotice(
        result?.status === "verification_send_failed"
          ? "השליחה נכשלה. נסו שוב בעוד דקה."
          : "שלחנו קישור חדש. הקישורים הקודמים כבר לא פעילים.",
      );
    } catch (err) {
      setNotice(verificationErrorMessage(err));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-2 text-center">
      <Button
        type="button"
        variant="outline"
        className="w-full"
        onClick={onResend}
        disabled={sending || secondsLeft > 0}
      >
        {sending
          ? "שולחים…"
          : secondsLeft > 0
            ? `שליחה חוזרת בעוד ${secondsLeft} שניות`
            : "שליחת הקישור שוב"}
      </Button>
      {notice && (
        <p role="status" className="text-sm text-text-secondary">
          {notice}
        </p>
      )}
    </div>
  );
}
