import React, { useEffect, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
      <form onSubmit={onSubmit} noValidate className="space-y-4">
        {notice && (
          <p
            role={noticeIsInfo ? "status" : "alert"}
            className={`text-sm text-center ${noticeIsInfo ? "text-signal-high" : "text-signal-hidden"}`}
          >
            {notice}
          </p>
        )}
        {unverified && (
          <div role="alert" className="space-y-3 rounded-md border border-border p-3">
            <p className="text-sm text-center">
              עוד לא אימתתם את כתובת האימייל. פתחו את הקישור ששלחנו אל{" "}
              <bdi dir="ltr">{unverified.email}</bdi> כדי להפעיל את החשבון.
            </p>
            <ResendVerification email={unverified.email} password={unverified.password} />
          </div>
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
          <Link to="/forgot-password" className="text-xs text-text-secondary underline underline-offset-4">
            שכחתם את הסיסמה?
          </Link>
        </div>
        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? "מתחברים…" : "כניסה"}
        </Button>
      </form>

      {auth.googleEnabled && (
        <div className="mt-5 space-y-4">
          <div className="flex items-center gap-3 text-xs text-text-dim" aria-hidden>
            <span className="h-px flex-1 bg-border" />
            או
            <span className="h-px flex-1 bg-border" />
          </div>
          <GoogleSignInButton
            onStart={dismissGoogleNotice}
            onError={() => setNotice(googleNoticeMessage("unavailable"))}
          />
        </div>
      )}

      {(auth.signupEnabled || auth.signupByInvitation) && (
        <p className="mt-6 text-sm text-text-secondary text-center">
          עדיין אין לכם חשבון?{" "}
          <Link to="/signup" className="text-foreground underline underline-offset-4">
            הרשמה
          </Link>
        </p>
      )}
    </AuthScene>
  );
}
