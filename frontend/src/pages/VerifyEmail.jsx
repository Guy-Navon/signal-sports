import React, { useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authVerificationPeek } from "@/api/client";
import { useAuth } from "@/context/AuthContext";
import AuthScene from "@/pages/AuthScene";
import {
  readVerificationToken,
  verificationErrorMessage,
} from "@/pages/emailVerification";

// The emailed link lands here: /verify-email#t=<token>. Opening the page
// changes nothing (mail scanners open links too); the account is activated
// only by submitting the password, on whatever device the link was opened.
export default function VerifyEmail() {
  const auth = useAuth();
  const navigate = useNavigate();
  // Read once, then drop the token from the address bar and history.
  const tokenRef = useRef(
    typeof window === "undefined" ? null : readVerificationToken(window.location.hash),
  );
  const [state, setState] = useState(tokenRef.current ? "checking" : "invalid");
  const [maskedEmail, setMaskedEmail] = useState("");
  const [password, setPassword] = useState("");
  const [notice, setNotice] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hash) {
      window.history.replaceState(null, "", window.location.pathname);
    }
    const token = tokenRef.current;
    if (!token) return undefined;
    let cancelled = false;
    authVerificationPeek(token)
      .then((result) => {
        if (cancelled) return;
        setMaskedEmail(result.email);
        setState("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setNotice(verificationErrorMessage(err));
        setState("invalid");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Only local/bypass modes make this page meaningless. A visitor signed in
  // as someone else still gets to activate the account the link is for.
  if (auth.status !== "loading" && auth.mode !== "enforced") {
    return <Navigate to="/" replace />;
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (submitting) return;
    if (!password) {
      setNotice("נדרשת סיסמה");
      return;
    }
    setSubmitting(true);
    setNotice(null);
    try {
      await auth.confirmVerification(tokenRef.current, password);
      navigate("/", { replace: true });
    } catch (err) {
      const message = verificationErrorMessage(err);
      setNotice(message);
      if (!/\((403|429)\)/.test(err?.message || "")) setState("invalid");
    } finally {
      setSubmitting(false);
    }
  }

  if (state === "checking") {
    return (
      <AuthScene kicker="אימות אימייל" title="בודקים את הקישור…">
        <p role="status" className="text-sm text-text-secondary text-center">
          רגע אחד.
        </p>
      </AuthScene>
    );
  }

  if (state === "invalid") {
    return (
      <AuthScene kicker="אימות אימייל" title="הקישור לא בתוקף">
        <p role="alert" className="text-sm text-text-secondary text-center">
          {notice || "הקישור חסר או שכבר השתמשו בו."}
        </p>
        <p className="mt-6 text-sm text-text-secondary text-center">
          <Link to="/login" className="text-foreground underline underline-offset-4">
            התחברות
          </Link>{" "}
          — אם החשבון עוד לא אומת, תוכלו לבקש שם קישור חדש.
        </p>
      </AuthScene>
    );
  }

  return (
    <AuthScene kicker="אימות אימייל" title="הפעלת החשבון">
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <p className="text-sm text-text-secondary text-center">
          כדי להפעיל את החשבון של{" "}
          <bdi dir="ltr" className="text-foreground">{maskedEmail}</bdi>, הזינו את
          הסיסמה שבחרתם בהרשמה.
        </p>
        {notice && (
          <p role="alert" className="text-sm text-signal-hidden text-center">
            {notice}
          </p>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="verify-password">סיסמה</Label>
          <Input
            id="verify-password"
            type="password"
            dir="ltr"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? "מפעילים…" : "הפעלת החשבון"}
        </Button>
        <p className="text-xs text-text-secondary text-center">
          לא נרשמתם? אפשר לסגור את הדף. בלי הסיסמה החשבון לא יופעל.
        </p>
      </form>
    </AuthScene>
  );
}
