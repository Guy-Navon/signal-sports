import React, { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
        <p role="status" className="text-sm text-text-secondary text-center">
          {FORGOT_SENT_MESSAGE}
          <br />
          לא מוצאים? בדקו גם בתיקיית הספאם.
        </p>
      ) : (
        <form onSubmit={onSubmit} noValidate className="space-y-4">
          <p className="text-sm text-text-secondary text-center">
            הזינו את כתובת האימייל של החשבון ונשלח קישור לבחירת סיסמה חדשה.
          </p>
          {error && (
            <p role="alert" className="text-sm text-signal-hidden text-center">{error}</p>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="forgot-email">אימייל</Label>
            <Input id="forgot-email" type="email" dir="ltr" autoComplete="email"
              value={email} onChange={(e) => { setEmail(e.target.value); setError(null); }} />
          </div>
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "שולחים…" : "שליחת קישור"}
          </Button>
        </form>
      )}
      <p className="mt-6 text-sm text-text-secondary text-center">
        <Link to="/login" className="text-foreground underline underline-offset-4">
          חזרה להתחברות
        </Link>
      </p>
    </AuthScene>
  );
}
