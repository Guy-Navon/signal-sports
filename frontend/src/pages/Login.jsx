import React, { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { authPagesRedundant } from "@/context/authView";
import AuthScene from "@/pages/AuthScene";
import {
  authErrorMessage,
  hasErrors,
  validateLoginForm,
} from "@/pages/authValidation";

export default function Login() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState(
    /** @type {{email?: string|null, password?: string|null}} */ ({}),
  );
  const [notice, setNotice] = useState(
    location.state?.expired ? "פג תוקף ההתחברות — היכנסו שוב" : null,
  );
  const [submitting, setSubmitting] = useState(false);

  // Local mode / bypass / already signed in: the login page is redundant.
  if (auth.status !== "loading" && authPagesRedundant(auth)) {
    return <Navigate to="/" replace />;
  }

  async function onSubmit(event) {
    event.preventDefault();
    const validation = validateLoginForm({ email, password });
    setErrors(validation);
    if (hasErrors(validation)) return;
    setSubmitting(true);
    setNotice(null);
    try {
      await auth.login(email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setNotice(authErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthScene kicker="החדר האישי" title="התחברות">
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {notice && (
          <p role="alert" className="text-sm text-signal-hidden text-center">
            {notice}
          </p>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="login-email">אימייל</Label>
          <Input
            id="login-email"
            type="email"
            dir="ltr"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          {errors.email && (
            <p className="text-xs text-signal-hidden">{errors.email}</p>
          )}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="login-password">סיסמה</Label>
          <Input
            id="login-password"
            type="password"
            dir="ltr"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {errors.password && (
            <p className="text-xs text-signal-hidden">{errors.password}</p>
          )}
        </div>
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? "מתחברים…" : "כניסה"}
        </Button>
      </form>

      <p className="mt-6 text-sm text-text-secondary text-center">
        עדיין אין לכם חשבון?{" "}
        <Link to="/signup" className="text-foreground underline underline-offset-4">
          הרשמה
        </Link>
      </p>
    </AuthScene>
  );
}
