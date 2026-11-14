import React, { useEffect, useRef, useState } from "react";
import { Button, Input, Label } from "@/pages/AuthControls";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { authResetPassword, authResetPeek } from "@/api/client";
import { useAuth } from "@/context/AuthContext";
import AuthScene from "@/pages/AuthScene";
import { validateSignupPassword } from "@/pages/authValidation";
import { captureResetToken, forgetResetToken, resetErrorMessage } from "@/pages/passwordReset";

// The emailed reset link lands here: /reset-password#t=<token> (#200).
// Opening it changes nothing; the new password is set only on submit, after
// which every session ends and the person signs in on /login.
export default function ResetPassword() {
  const auth = useAuth();
  const navigate = useNavigate();
  const tokenRef = useRef(
    typeof window === "undefined" ? null : captureResetToken(window.location.hash),
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
    authResetPeek(token)
      .then((result) => {
        if (cancelled) return;
        setMaskedEmail(result.email);
        setState("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        forgetResetToken();
        setNotice(resetErrorMessage(err));
        setState("invalid");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (auth.status !== "loading" && auth.mode !== "enforced") {
    return <Navigate to="/" replace />;
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (submitting) return;
    const invalid = validateSignupPassword(password);
    if (invalid) {
      setNotice(invalid);
      return;
    }
    setSubmitting(true);
    setNotice(null);
    try {
      await authResetPassword(tokenRef.current, password);
      forgetResetToken();
      await auth.refreshSession();
      navigate("/login", { replace: true, state: { passwordReset: true } });
    } catch (err) {
      setNotice(resetErrorMessage(err));
      if (!/\((422)\)/.test(err?.message || "")) {
        forgetResetToken();
        setState("invalid");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (state === "checking") {
    return (
      <AuthScene kicker="איפוס סיסמה" title="בודקים את הקישור…">
        <p role="status" className="text-sm sg-auth-muted text-center">רגע אחד.</p>
      </AuthScene>
    );
  }

  if (state === "invalid") {
    return (
      <AuthScene kicker="איפוס סיסמה" title="הקישור לא בתוקף">
        <p role="alert" className="text-sm sg-auth-muted text-center">
          {notice || "הקישור חסר, פג תוקפו או שכבר השתמשו בו."}
        </p>
        <p className="mt-6 text-sm sg-auth-muted text-center">
          <Link to="/forgot-password" className="sg-auth-ink underline underline-offset-4">
            בקשת קישור חדש
          </Link>
        </p>
      </AuthScene>
    );
  }

  return (
    <AuthScene kicker="איפוס סיסמה" title="בחירת סיסמה חדשה">
      <form onSubmit={onSubmit} noValidate className="sg-auth-stack">
        <p className="text-sm sg-auth-muted text-center">
          סיסמה חדשה לחשבון{" "}
          <bdi dir="ltr" className="sg-auth-ink">{maskedEmail}</bdi>. אחרי השמירה
          כל ההתחברויות הקיימות ינותקו.
        </p>
        {notice && (
          <p role="alert" className="text-sm sg-auth-error text-center">{notice}</p>
        )}
        <div className="sg-auth-field">
          <Label htmlFor="reset-password">סיסמה חדשה (לפחות 8 תווים)</Label>
          <Input id="reset-password" type="password" dir="ltr" autoComplete="new-password"
            value={password} onChange={(e) => { setPassword(e.target.value); setNotice(null); }} />
        </div>
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? "שומרים…" : "שמירת הסיסמה"}
        </Button>
      </form>
    </AuthScene>
  );
}
