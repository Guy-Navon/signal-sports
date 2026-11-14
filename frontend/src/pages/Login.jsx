import React, { useEffect, useState } from "react";
import { Button, Input, Label } from "@/pages/AuthControls";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { authPagesRedundant } from "@/context/authView";
import AuthScene from "@/pages/AuthScene";
import GoogleSignInButton from "@/pages/GoogleSignInButton";
import ResendVerification from "@/pages/ResendVerification";
import { isUnverifiedLogin } from "@/pages/emailVerification";
import {
  captureGoogleNotice,
  dismissGoogleNotice,
  googleNoticeMessage,
  googleNoticeTone,
  readGoogleNotice,
} from "@/pages/googleSignIn";
import {
  authErrorMessage,
  hasErrors,
  validateLoginForm,
} from "@/pages/authValidation";

const PASSWORD_RESET_NOTICE = "הסיסמה עודכנה. היכנסו עם הסיסמה החדשה.";

export default function Login() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState(
    /** @type {{email?: string|null, password?: string|null}} */ ({}),
  );
  // The Google callback sends failures back as /login?google=<code>.
  const googleCode = captureGoogleNotice(location.search);
  const [notice, setNotice] = useState(
    googleCode
      ? googleNoticeMessage(googleCode)
      : location.state?.passwordReset ? PASSWORD_RESET_NOTICE
      : location.state?.expired ? "פג תוקף ההתחברות — היכנסו שוב" : null,
  );

  // "Check your inbox" (#329) is the next step, not a failure.
  const noticeIsInfo =
    (Boolean(notice) && googleNoticeTone(googleCode) === "info" &&
      notice === googleNoticeMessage(googleCode)) ||
    (Boolean(location.state?.passwordReset) && notice === PASSWORD_RESET_NOTICE);

  // Drop ?google= from the address bar so a reload or a shared URL doesn't
  // repeat the notice; the code itself stays remembered until the next action.
  const codeInUrl = readGoogleNotice(location.search);
  useEffect(() => {
    if (codeInUrl) navigate(location.pathname, { replace: true, state: location.state });
  }, [codeInUrl, location.pathname, location.state, navigate]);
  const [submitting, setSubmitting] = useState(false);
  // The credentials matched a signup whose email is not verified yet.
  const [unverified, setUnverified] = useState(null);

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
    dismissGoogleNotice();
    setUnverified(null);
    try {
      await auth.login(email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      if (isUnverifiedLogin(err)) {
        setUnverified({ email: email.trim(), password });
      } else {
        setNotice(authErrorMessage(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthScene kicker="החדר האישי" title="התחברות">
      <form onSubmit={onSubmit} noValidate aria-busy={submitting} className="sg-auth-stack">
        {notice && (
          <p
            role={noticeIsInfo ? "status" : "alert"}
            className={`text-sm text-center ${noticeIsInfo ? "sg-auth-success" : "sg-auth-error"}`}
          >
            {notice}
          </p>
        )}
        {unverified && (
          <div role="alert" className="space-y-3 sg-auth-callout">
            <p className="text-sm text-center">
              עוד לא אימתתם את כתובת האימייל. פתחו את הקישור ששלחנו אל{" "}
              <bdi dir="ltr">{unverified.email}</bdi> כדי להפעיל את החשבון.
            </p>
            <ResendVerification email={unverified.email} password={unverified.password} />
          </div>
        )}
        <div className="sg-auth-field">
          <Label htmlFor="login-email">אימייל</Label>
          <Input
            id="login-email"
            type="email"
            dir="ltr"
            autoComplete="email"
            aria-invalid={Boolean(errors.email)}
            aria-describedby={errors.email ? "login-email-error" : undefined}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          {errors.email && (
            <p id="login-email-error" role="alert" className="sg-auth-error">{errors.email}</p>
          )}
        </div>
        <div className="sg-auth-field">
          <Label htmlFor="login-password">סיסמה</Label>
          <Input
            id="login-password"
            type="password"
            dir="ltr"
            autoComplete="current-password"
            aria-invalid={Boolean(errors.password)}
            aria-describedby={errors.password ? "login-password-error" : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {errors.password && (
            <p id="login-password-error" role="alert" className="sg-auth-error">{errors.password}</p>
          )}
          <Link to="/forgot-password" className="text-xs sg-auth-muted underline underline-offset-4">
            שכחתם את הסיסמה?
          </Link>
        </div>
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? "מתחברים…" : "כניסה"}
        </Button>
      </form>

      {auth.googleEnabled && (
        <div className="mt-5 space-y-4">
          <div className="flex items-center gap-3 text-xs sg-auth-muted" aria-hidden>
            <span className="h-px flex-1 sg-auth-rule" />
            או
            <span className="h-px flex-1 sg-auth-rule" />
          </div>
          <GoogleSignInButton
            onStart={dismissGoogleNotice}
            onError={() => setNotice(googleNoticeMessage("unavailable"))}
          />
        </div>
      )}

      {(auth.signupEnabled || auth.signupByInvitation) && (
        <p className="mt-6 text-sm sg-auth-muted text-center">
          עדיין אין לכם חשבון?{" "}
          <Link to="/signup" className="sg-auth-ink underline underline-offset-4">
            הרשמה
          </Link>
        </p>
      )}
    </AuthScene>
  );
}
