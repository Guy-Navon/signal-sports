import React, { useEffect, useState } from "react";
import { AccountDialogContent } from "@/pages/AccountDialog";
import { Button, Input, Label } from "@/pages/AuthControls";
import { useLocation, useNavigate } from "react-router-dom";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { deleteMeAccountWithGrant, startMeGoogleDeletion } from "@/api/client";
import {
  captureAccountGoogleState,
  deletionNoticeMessage,
  forgetAccountGoogleState,
  matchesAccountEmail,
} from "@/pages/googleDeletion";
import { isLinkCode } from "@/pages/googleLinking";

// Deleting an account that was opened with Google and has no password (#331).
// Step 1: type the account's email, then confirm with the same Google account.
// Step 2: back here with /account?delete=confirm, delete for good. The Google
// step only earns a short-lived, single-use permission for THIS session; the
// deletion itself is this page's explicit button.
/** @param {{ email: string, onDeleted: () => void }} props */
export default function GoogleAccountDeletion({ email, onDeleted }) {
  const location = useLocation();
  const navigate = useNavigate();
  const initial = captureAccountGoogleState(location.search);
  const [confirming, setConfirming] = useState(initial.confirm);
  // Connect-Google codes (#330) share ?google= and belong to the sign-in section.
  const ownCode = initial.code && !isLinkCode(initial.code) ? initial.code : null;
  const [notice, setNotice] = useState(ownCode ? deletionNoticeMessage(ownCode) : null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);

  const hasParams = /[?&](delete|google)=/.test(location.search);
  useEffect(() => {
    if (hasParams) navigate(location.pathname, { replace: true });
  }, [hasParams, location.pathname, navigate]);

  async function startGoogle() {
    if (busy) return;
    if (!matchesAccountEmail(typed, email)) {
      setNotice("הקלידו את כתובת האימייל של החשבון בדיוק כפי שהיא מופיעה למעלה.");
      return;
    }
    setBusy(true);
    setNotice(null);
    forgetAccountGoogleState();
    try {
      const { url } = await startMeGoogleDeletion(typed.trim());
      window.location.assign(url);
    } catch {
      setBusy(false);
      setNotice(deletionNoticeMessage("failed"));
    }
  }

  async function deleteForGood() {
    if (busy) return;
    setBusy(true);
    setNotice(null);
    try {
      await deleteMeAccountWithGrant();
      forgetAccountGoogleState();
      onDeleted();
    } catch (err) {
      setBusy(false);
      const message = err?.message || "";
      if (message.includes("(409)")) {
        setNotice("לא ניתן למחוק את חשבון האדמין האחרון במערכת.");
      } else if (message.includes("(403)")) {
        forgetAccountGoogleState();
        setConfirming(false);
        setNotice("תוקף האישור מול Google פג (5 דקות). התחילו שוב.");
      } else {
        setNotice("משהו השתבש — החשבון לא נמחק.");
      }
    }
  }

  if (confirming) {
    return (
      <div role="alert" className="sg-auth-stack sg-account__form sg-account__confirmation">
        <p className="text-sm">
          Google אישר את החשבון. למחוק עכשיו את החשבון לצמיתות? אין דרך לשחזר
          את הפרופיל, הכיול או המשובים.
        </p>
        {notice && <p className="text-xs sg-auth-error">{notice}</p>}
        <div className="flex flex-wrap gap-2">
          <Button variant="destructive" onClick={deleteForGood} disabled={busy}>
            {busy ? "מוחקים…" : "מחיקה לצמיתות"}
          </Button>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => { forgetAccountGoogleState(); setConfirming(false); }}
          >
            ביטול
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {notice && <p role="alert" className="text-xs sg-auth-error max-w-sm">{notice}</p>}
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="destructive">מחיקת החשבון…</Button>
        </AlertDialogTrigger>
        <AccountDialogContent>
          <AlertDialogHeader className="sg-account-dialog__header">
            <AlertDialogTitle>מחיקת החשבון לצמיתות</AlertDialogTitle>
            <AlertDialogDescription>
              הפעולה בלתי הפיכה. לאישור, הקלידו את כתובת האימייל של החשבון ואשרו
              עם אותו חשבון Google. אחרי האישור תחזרו לכאן ללחיצה אחרונה.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="sg-auth-field">
            <Label htmlFor="acct-delete-email">אימייל החשבון</Label>
            <Input id="acct-delete-email" type="email" dir="ltr" autoComplete="off"
              value={typed} onChange={(e) => { setTyped(e.target.value); setNotice(null); }} />
            {notice && <p role="alert" className="text-xs sg-auth-error">{notice}</p>}
          </div>
          <AlertDialogFooter className="sg-account-dialog__footer">
            <AlertDialogCancel className="sg-account-dialog__cancel">ביטול</AlertDialogCancel>
            <Button variant="destructive" onClick={startGoogle} disabled={busy}>
              {busy ? "מעבירים ל-Google…" : "אישור עם Google"}
            </Button>
          </AlertDialogFooter>
        </AccountDialogContent>
      </AlertDialog>
    </div>
  );
}
