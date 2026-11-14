import React, { useState } from "react";
import { Button, Input, Label } from "@/pages/AuthControls";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { authPagesRedundant } from "@/context/authView";
import AuthScene from "@/pages/AuthScene";
import GoogleSignInButton from "@/pages/GoogleSignInButton";
import { googleNoticeMessage } from "@/pages/googleSignIn";
import ResendVerification from "@/pages/ResendVerification";
import {
  hasErrors,
  signupErrorMessage,
  validateSignupForm,
} from "@/pages/authValidation";

export default function Signup() {
  const auth = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [errors, setErrors] = useState(
    /** @type {{email?: string|null, password?: string|null}} */ ({}),
  );
  const [notice, setNotice] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  // After a successful signup: {email, delivered, sentAt}. The password stays
  // in this component's memory only, for "send again".
  const [pending, setPending] = useState(null);

  if (auth.status !== "loading" && authPagesRedundant(auth)) {
    return <Navigate to="/" replace />;
  }

  // Signup closed by the server (AUTH_SIGNUP_ENABLED=false, #265): say so
  // instead of showing a form that can only fail with 403.
  if (auth.status !== "loading" && !auth.signupEnabled && !auth.signupByInvitation) {
    return (
      <AuthScene kicker="מצטרפים לסיגנל" title="ההרשמה סגורה">
        <p className="text-sm sg-auth-muted text-center">
          פתיחת חשבונות חדשים אינה זמינה כרגע.
        </p>
        <p className="mt-6 text-sm sg-auth-muted text-center">
          כבר יש לכם חשבון?{" "}
          <Link to="/login" className="sg-auth-ink underline underline-offset-4">
            התחברות
          </Link>
        </p>
      </AuthScene>
    );
  }

  async function onSubmit(event) {
    event.preventDefault();
    const validation = validateSignupForm({ email, password });
    setErrors(validation);
    if (hasErrors(validation)) return;
    setSubmitting(true);
    setNotice(null);
    try {
      const result = await auth.signup({
        email: email.trim(),
        password,
        displayName: displayName.trim() || null,
      });
      setPending({
        email: result.email,
        delivered: result.status === "verification_sent",
        sentAt: Date.now(),
      });
    } catch (err) {
      setNotice(signupErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (pending) {
    return (
      <AuthScene kicker="מצטרפים לסיגנל" title="בדקו את תיבת האימייל">
        <div className="space-y-5">
          {pending.delivered ? (
            <p className="text-sm sg-auth-muted text-center">
              שלחנו קישור אימות אל{" "}
              <bdi dir="ltr" className="sg-auth-ink">{pending.email}</bdi>.
              <br />
              פתחו אותו בכל מכשיר והזינו את הסיסמה כדי להפעיל את החשבון.
              הקישור תקף ל-24 שעות.
            </p>
          ) : (
            <p role="alert" className="text-sm sg-auth-error text-center">
              לא הצלחנו לשלוח את האימייל אל{" "}
              <bdi dir="ltr">{pending.email}</bdi>. נסו לשלוח שוב בעוד דקה.
            </p>
          )}
          <ResendVerification
            email={pending.email}
            password={password}
            initialSentAt={pending.sentAt}
          />
          <p className="text-sm sg-auth-muted text-center">
            לא מוצאים? בדקו גם בתיקיית הספאם.
            <br />
            הכתובת שגויה?{" "}
            <button
              type="button"
              className="sg-auth-text-link"
              onClick={() => {
                setPending(null);
                setPassword("");
              }}
            >
              הרשמה מחדש עם כתובת אחרת
            </button>
          </p>
        </div>
      </AuthScene>
    );
  }

  return (
    <AuthScene kicker="מצטרפים לסיגנל" title="פתיחת חשבון">
      {auth.signupByInvitation && (
        <p className="mb-4 text-sm sg-auth-muted text-center">
          ההרשמה פתוחה כרגע למוזמנים בלבד.
        </p>
      )}
      <form onSubmit={onSubmit} noValidate aria-busy={submitting} className="sg-auth-stack">
        {notice && (
          <p role="alert" className="text-sm sg-auth-error text-center">
            {notice}
          </p>
        )}
        <div className="sg-auth-field">
          <Label htmlFor="signup-name">איך לקרוא לכם? (לא חובה)</Label>
          <Input
            id="signup-name"
            type="text"
            autoComplete="name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </div>
        <div className="sg-auth-field">
          <Label htmlFor="signup-email">אימייל</Label>
          <Input
            id="signup-email"
            type="email"
            dir="ltr"
            autoComplete="email"
            aria-invalid={Boolean(errors.email)}
            aria-describedby={errors.email ? "signup-email-error" : undefined}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          {errors.email && (
            <p id="signup-email-error" role="alert" className="sg-auth-error">{errors.email}</p>
          )}
        </div>
        <div className="sg-auth-field">
          <Label htmlFor="signup-password">סיסמה (לפחות 8 תווים)</Label>
          <Input
            id="signup-password"
            type="password"
            dir="ltr"
            autoComplete="new-password"
            aria-invalid={Boolean(errors.password)}
            aria-describedby={errors.password ? "signup-password-error" : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {errors.password && (
            <p id="signup-password-error" role="alert" className="sg-auth-error">{errors.password}</p>
          )}
        </div>
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? "שולחים קישור אימות…" : "הרשמה"}
        </Button>
      </form>

      {auth.googleEnabled && (
        <div className="mt-5 space-y-4">
          <div className="flex items-center gap-3 text-xs sg-auth-muted" aria-hidden>
            <span className="h-px flex-1 sg-auth-rule" />
            או
            <span className="h-px flex-1 sg-auth-rule" />
          </div>
          <GoogleSignInButton onError={() => setNotice(googleNoticeMessage("unavailable"))} />
        </div>
      )}

      <p className="mt-6 text-sm sg-auth-muted text-center">
        כבר יש לכם חשבון?{" "}
        <Link to="/login" className="sg-auth-ink underline underline-offset-4">
          התחברות
        </Link>
      </p>
    </AuthScene>
  );
}
