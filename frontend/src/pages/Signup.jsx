import React, { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { authPagesRedundant } from "@/context/authView";
import AuthScene from "@/pages/AuthScene";
import {
  authErrorMessage,
  hasErrors,
  validateSignupForm,
} from "@/pages/authValidation";

export default function Signup() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [errors, setErrors] = useState(
    /** @type {{email?: string|null, password?: string|null}} */ ({}),
  );
  const [notice, setNotice] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  if (auth.status !== "loading" && authPagesRedundant(auth)) {
    return <Navigate to="/" replace />;
  }

  async function onSubmit(event) {
    event.preventDefault();
    const validation = validateSignupForm({ email, password });
    setErrors(validation);
    if (hasErrors(validation)) return;
    setSubmitting(true);
    setNotice(null);
    try {
      await auth.signup({
        email: email.trim(),
        password,
        displayName: displayName.trim() || null,
      });
      navigate("/", { replace: true });
    } catch (err) {
      setNotice(authErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthScene kicker="מצטרפים לסיגנל" title="פתיחת חשבון">
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {notice && (
          <p role="alert" className="text-sm text-signal-hidden text-center">
            {notice}
          </p>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="signup-name">איך לקרוא לכם? (לא חובה)</Label>
          <Input
            id="signup-name"
            type="text"
            autoComplete="name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="signup-email">אימייל</Label>
          <Input
            id="signup-email"
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
          <Label htmlFor="signup-password">סיסמה (לפחות 8 תווים)</Label>
          <Input
            id="signup-password"
            type="password"
            dir="ltr"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {errors.password && (
            <p className="text-xs text-signal-hidden">{errors.password}</p>
          )}
        </div>
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? "פותחים חשבון…" : "הרשמה"}
        </Button>
      </form>

      <p className="mt-6 text-sm text-text-secondary text-center">
        כבר יש לכם חשבון?{" "}
        <Link to="/login" className="text-foreground underline underline-offset-4">
          התחברות
        </Link>
      </p>
    </AuthScene>
  );
}
