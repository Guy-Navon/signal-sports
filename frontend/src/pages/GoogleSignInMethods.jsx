import React, { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { startMeGoogleLink, unlinkMeGoogle } from "@/api/client";
import {
  captureAccountGoogleState,
  forgetAccountGoogleState,
} from "@/pages/googleDeletion";
import { isLinkCode, linkNoticeMessage } from "@/pages/googleLinking";

// "שיטות התחברות" on the Account page (#330): which sign-in methods this
// account has, and connecting / disconnecting Google. Connecting re-enters
// the password, then goes to Google; the callback returns here with
// ?google=linked or ?google=link_<reason>. Disconnecting needs the password
// and is not offered to an account without one (it would be locked out).
/**
 * @param {{
 *   hasPassword: boolean,
 *   googleEmail: string | null,
 *   googleEnabled: boolean,
 *   onChanged: () => Promise<unknown>,
 * }} props
 */
export default function GoogleSignInMethods({ hasPassword, googleEmail, googleEnabled, onChanged }) {
  const location = useLocation();
  const navigate = useNavigate();
  const captured = captureAccountGoogleState(location.search).code;
  const [notice, setNotice] = useState(isLinkCode(captured) ? linkNoticeMessage(captured) : null);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [dialogNotice, setDialogNotice] = useState(null);

  const hasParams = /[?&](delete|google)=/.test(location.search);
  useEffect(() => {
    if (hasParams) navigate(location.pathname, { replace: true });
  }, [hasParams, location.pathname, navigate]);

  function passwordError(err) {
    const message = err?.message || "";
    if (message.includes("(403)")) return "הסיסמה שגויה";
    if (message.includes("(429)")) return "יותר מדי ניסיונות — נסו שוב בעוד כמה דקות";
    if (message.includes("(409)")) return "הפעולה לא זמינה לחשבון הזה כרגע.";
    return "משהו השתבש — נסו שוב";
  }

  async function connect() {
    if (busy) return;
    setBusy(true);
    setDialogNotice(null);
    forgetAccountGoogleState();
    try {
      const { url } = await startMeGoogleLink(password);
      window.location.assign(url);
    } catch (err) {
      setBusy(false);
      setDialogNotice(passwordError(err));
    }
  }

  async function disconnect() {
    if (busy) return;
    setBusy(true);
    setDialogNotice(null);
    forgetAccountGoogleState();
    try {
      await unlinkMeGoogle(password);
      setPassword("");
      setNotice("Google נותק מהחשבון.");
      await onChanged();
    } catch (err) {
      setDialogNotice(passwordError(err));
    } finally {
      setBusy(false);
    }
  }

  const passwordField = (
    <div className="space-y-1.5">
      <Label htmlFor="acct-google-pw">סיסמה נוכחית</Label>
      <Input id="acct-google-pw" type="password" dir="ltr" autoComplete="current-password"
        value={password}
        onChange={(e) => { setPassword(e.target.value); setDialogNotice(null); }} />
      {dialogNotice && <p role="alert" className="text-xs text-signal-hidden">{dialogNotice}</p>}
    </div>
  );

  return (
    <div className="space-y-3 max-w-sm">
      {notice && <p role="status" className="text-xs text-signal-high">{notice}</p>}
      <dl className="space-y-1 text-sm">
        <div className="flex gap-2">
          <dt className="text-text-secondary">סיסמה:</dt>
          <dd>{hasPassword ? "מוגדרת" : "אין (נכנסים עם Google)"}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-text-secondary">Google:</dt>
          <dd>
            {googleEmail ? <bdi dir="ltr">{googleEmail}</bdi> : "לא מחובר"}
          </dd>
        </div>
      </dl>

      {googleEmail && hasPassword && (
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="outline">ניתוק Google…</Button>
          </AlertDialogTrigger>
          <AlertDialogContent dir="rtl">
            <AlertDialogHeader>
              <AlertDialogTitle>ניתוק Google מהחשבון</AlertDialogTitle>
              <AlertDialogDescription>
                אחרי הניתוק ההתחברות תהיה עם האימייל והסיסמה בלבד. לאישור, הזינו את הסיסמה הנוכחית.
              </AlertDialogDescription>
            </AlertDialogHeader>
            {passwordField}
            <AlertDialogFooter>
              <AlertDialogCancel>ביטול</AlertDialogCancel>
              <Button onClick={disconnect} disabled={busy}>
                {busy ? "מנתקים…" : "ניתוק"}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
      {googleEmail && !hasPassword && (
        <p className="text-xs text-text-secondary">
          לחשבון בלי סיסמה Google הוא הדרך היחידה להתחבר, ולכן אי אפשר לנתק אותו.
        </p>
      )}

      {!googleEmail && hasPassword && googleEnabled && (
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="outline">חיבור Google…</Button>
          </AlertDialogTrigger>
          <AlertDialogContent dir="rtl">
            <AlertDialogHeader>
              <AlertDialogTitle>חיבור חשבון Google</AlertDialogTitle>
              <AlertDialogDescription>
                אחרי החיבור אפשר יהיה להיכנס גם עם Google. לאישור, הזינו את הסיסמה הנוכחית ואז
                בחרו את חשבון ה-Google.
              </AlertDialogDescription>
            </AlertDialogHeader>
            {passwordField}
            <AlertDialogFooter>
              <AlertDialogCancel>ביטול</AlertDialogCancel>
              <Button onClick={connect} disabled={busy}>
                {busy ? "מעבירים ל-Google…" : "המשך ל-Google"}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </div>
  );
}
