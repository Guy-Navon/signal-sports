import React, { useState } from "react";
import { Button, Input, Label } from "@/pages/AuthControls";
import { Link, Navigate } from "react-router-dom";
import { authForgotPassword } from "@/api/client";
import { useAuth } from "@/context/AuthContext";
import { authPagesRedundant } from "@/context/authView";
import AuthScene from "@/pages/AuthScene";
import { validateEmail } from "@/pages/authValidation";
import { FORGOT_SENT_MESSAGE, resetErrorMessage } from "@/pages/passwordReset";

// "שכחתם את הסיסמה?" (#200). The answer never says whether an account exists.
export default function ForgotPassword() {
  const auth = useAuth();
  const [email, setEmail] = useState("");
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (auth.status !== "loading" && authPagesRedundant(auth)) {
    return <Navigate to="/" replace />;
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (submitting) return;
    const invalid = validateEmail(email);
    if (invalid) {
      setError(invalid);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await authForgotPassword(email.trim());
      setSent(true);
    } catch (err) {
      setError(resetErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthScene kicker="החדר האישי" title="איפוס סיסמה">
      {sent ? (
        <p role="status" className="text-sm sg-auth-muted text-center">
          {FORGOT_SENT_MESSAGE}
          <br />
          לא מוצאים? בדקו גם בתיקיית הספאם.
        </p>
      ) : (
        <form onSubmit={onSubmit} noValidate className="sg-auth-stack">
          <p className="text-sm sg-auth-muted text-center">
            הזינו את כתובת האימייל של החשבון ונשלח קישור לבחירת סיסמה חדשה.
          </p>
          {error && (
            <p role="alert" className="text-sm sg-auth-error text-center">{error}</p>
          )}
          <div className="sg-auth-field">
            <Label htmlFor="forgot-email">אימייל</Label>
            <Input id="forgot-email" type="email" dir="ltr" autoComplete="email"
              value={email} onChange={(e) => { setEmail(e.target.value); setError(null); }} />
          </div>
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "שולחים…" : "שליחת קישור"}
          </Button>
        </form>
      )}
      <p className="mt-6 text-sm sg-auth-muted text-center">
        <Link to="/login" className="sg-auth-ink underline underline-offset-4">
          חזרה להתחברות
        </Link>
      </p>
    </AuthScene>
  );
}
