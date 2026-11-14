import React, { useState } from "react";
import { AccountDialogContent } from "@/pages/AccountDialog";
import { Button, Input, Label } from "@/pages/AuthControls";
import { Navigate } from "react-router-dom";
import { KeyRound, LogIn, LogOut, Trash2, UserRound } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { changeMePassword, deleteMeAccount } from "@/api/client";
import { useAuth } from "@/context/AuthContext";
import { validateSignupPassword } from "@/pages/authValidation";
import { accountHasPassword } from "@/pages/googleSignIn";
import GoogleAccountDeletion from "@/pages/GoogleAccountDeletion";
import GoogleSignInMethods from "@/pages/GoogleSignInMethods";

// The account page (User Platform PR 7, #55) — product-side, reached from the
// masthead account menu. Email display, password change (revokes other
// sessions), logout, and irreversible account deletion behind a confirm
// dialog. Product (editorial) styling; exists only under a consumer session.
export default function Account() {
  const auth = useAuth();
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [pwNotice, setPwNotice] = useState(null);
  const [pwBusy, setPwBusy] = useState(false);
  const [deletePw, setDeletePw] = useState("");
  const [deleteNotice, setDeleteNotice] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  if (auth.status !== "loading" && (!auth.authEnforced || !auth.user)) {
    return <Navigate to="/" replace />;
  }
  if (!auth.user) return null;
  // Accounts created through Google have no password to change or confirm.
  const hasPassword = accountHasPassword(auth.user);

  async function submitPasswordChange(event) {
    event.preventDefault();
    const invalid = validateSignupPassword(newPw);
    if (invalid) {
      setPwNotice({ tone: "error", text: invalid });
      return;
    }
    setPwBusy(true);
    setPwNotice(null);
    try {
      const result = await changeMePassword(currentPw, newPw);
      setCurrentPw("");
      setNewPw("");
      setPwNotice({
        tone: "ok",
        text:
          result.revoked_other_sessions > 0
            ? `הסיסמה עודכנה. ${result.revoked_other_sessions} התחברויות אחרות נותקו.`
            : "הסיסמה עודכנה.",
      });
    } catch (err) {
      setPwNotice({
        tone: "error",
        text: err?.message?.includes("(403)")
          ? "הסיסמה הנוכחית שגויה"
          : err?.message?.includes("(429)")
            ? "יותר מדי ניסיונות — נסו שוב בעוד כמה דקות"
            : "משהו השתבש — נסו שוב",
      });
    } finally {
      setPwBusy(false);
    }
  }

  async function confirmDelete() {
    if (deleteBusy) return;
    setDeleteBusy(true);
    setDeleteNotice(null);
    try {
      await deleteMeAccount(deletePw);
      // The session is gone server-side; refresh routes us to /login.
      await auth.refreshSession();
      window.location.assign("/login");
    } catch (err) {
      if (err?.message?.includes("(409)")) {
        setDeleteNotice("לא ניתן למחוק את חשבון האדמין האחרון במערכת");
      } else if (err?.message?.includes("(403)")) {
        setDeleteNotice("הסיסמה שגויה — החשבון לא נמחק");
      } else if (err?.message?.includes("(429)")) {
        setDeleteNotice("יותר מדי ניסיונות — החשבון לא נמחק. נסו שוב בעוד כמה דקות");
      } else {
        setDeleteNotice("משהו השתבש — החשבון לא נמחק");
      }
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <div className="sg-account sg-gutter">
      <div className="sg-container sg-account__content">
        <header className="sg-account__intro">
          <h1>החשבון שלך</h1>
          <p className="sg-auth-muted">ניהול ההתחברות והחשבון — ההעדפות עצמן גרות בעמוד ההעדפות.</p>
        </header>

        <section className="sg-account__section">
          <h2>
            <UserRound size={14} /> זהות
          </h2>
          <p className="sg-account__identity"><bdi dir="auto">{auth.user.email}</bdi></p>
        </section>

        <section className="sg-account__section">
          <h2>
            <LogIn size={14} /> שיטות התחברות
          </h2>
          <GoogleSignInMethods
            hasPassword={hasPassword}
            googleEmail={auth.user.google_email ?? null}
            googleEnabled={Boolean(auth.googleEnabled)}
            onChanged={auth.refreshSession}
          />
        </section>

        {hasPassword && (
        <section className="sg-account__section">
          <h2>
            <KeyRound size={14} /> החלפת סיסמה
          </h2>
          <form onSubmit={submitPasswordChange} noValidate className="sg-auth-stack sg-account__form">
            <div className="sg-auth-field">
              <Label htmlFor="acct-current">סיסמה נוכחית</Label>
              <Input id="acct-current" type="password" dir="ltr" autoComplete="current-password"
                value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} />
            </div>
            <div className="sg-auth-field">
              <Label htmlFor="acct-new">סיסמה חדשה (לפחות 8 תווים)</Label>
              <Input id="acct-new" type="password" dir="ltr" autoComplete="new-password"
                value={newPw} onChange={(e) => setNewPw(e.target.value)} />
            </div>
            {pwNotice && (
              <p role="alert" className={
                pwNotice.tone === "ok" ? "text-xs sg-auth-success" : "text-xs sg-auth-error"
              }>
                {pwNotice.text}
              </p>
            )}
            <Button type="submit" disabled={pwBusy}>
              {pwBusy ? "מעדכנים…" : "עדכון סיסמה"}
            </Button>
            <p className="text-xs sg-auth-muted">
              עדכון הסיסמה מנתק את כל ההתחברויות האחרות; ההתחברות הנוכחית נשארת.
            </p>
          </form>
        </section>
        )}

        <section className="sg-account__section">
          <h2>
            <LogOut size={14} /> התנתקות
          </h2>
          <Button variant="outline" onClick={() => auth.logout()}>התנתקות מהחשבון</Button>
        </section>

        <section className="sg-account__section sg-account__section--danger">
          <h2>
            <Trash2 size={14} /> מחיקת חשבון
          </h2>
          <p className="text-xs sg-auth-muted max-w-sm">
            מחיקה מסירה לצמיתות את החשבון, הפרופיל, הכיול, המשובים והלמידה.
            הכתבות עצמן הן מידע כללי ואינן נמחקות.
          </p>
          {!hasPassword ? (
            <GoogleAccountDeletion
              email={auth.user.email}
              onDeleted={async () => {
                await auth.refreshSession();
                window.location.assign("/login");
              }}
            />
          ) : (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive">מחיקת החשבון…</Button>
            </AlertDialogTrigger>
            <AccountDialogContent>
              <AlertDialogHeader className="sg-account-dialog__header">
                <AlertDialogTitle>מחיקת החשבון לצמיתות</AlertDialogTitle>
                <AlertDialogDescription>
                  הפעולה בלתי הפיכה — אין דרך לשחזר את הפרופיל, הכיול או המשובים.
                  לאישור, הזינו את הסיסמה הנוכחית.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <div className="sg-auth-field">
                <Label htmlFor="acct-delete-pw">סיסמה נוכחית</Label>
                <Input id="acct-delete-pw" type="password" dir="ltr"
                  autoComplete="current-password"
                  value={deletePw} onChange={(e) => setDeletePw(e.target.value)} />
                {deleteNotice && (
                  <p role="alert" className="text-xs sg-auth-error">{deleteNotice}</p>
                )}
              </div>
              <AlertDialogFooter className="sg-account-dialog__footer">
                <AlertDialogCancel className="sg-account-dialog__cancel">ביטול</AlertDialogCancel>
                <AlertDialogAction
                  onClick={(e) => { e.preventDefault(); confirmDelete(); }}
                  disabled={deleteBusy}
                  aria-busy={deleteBusy}
                  data-auth-variant="destructive"
                  className="sg-auth-button"
                >
                  {deleteBusy ? "מוחקים…" : "מחיקה לצמיתות"}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AccountDialogContent>
          </AlertDialog>
          )}
        </section>
      </div>
    </div>
  );
}
