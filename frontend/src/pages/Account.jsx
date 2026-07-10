import React, { useState } from "react";
import { Navigate } from "react-router-dom";
import { KeyRound, LogOut, Trash2, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { changeMePassword, deleteMeAccount } from "@/api/client";
import { useAuth } from "@/context/AuthContext";
import DeskIntro from "@/components/shared/DeskIntro";
import { validateSignupPassword } from "@/pages/authValidation";

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

  if (auth.status !== "loading" && (!auth.authEnforced || !auth.user)) {
    return <Navigate to="/" replace />;
  }
  if (!auth.user) return null;

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
          : "משהו השתבש — נסו שוב",
      });
    } finally {
      setPwBusy(false);
    }
  }

  async function confirmDelete() {
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
      } else {
        setDeleteNotice("משהו השתבש — החשבון לא נמחק");
      }
    }
  }

  return (
    <div className="max-w-2xl space-y-8">
      <DeskIntro kicker="החשבון שלך">ניהול ההתחברות והחשבון — ההעדפות עצמן גרות בעמוד ההעדפות.</DeskIntro>

      <section className="space-y-2">
        <h2 className="flex items-center gap-2 text-sm font-medium text-text-secondary">
          <UserRound size={14} /> זהות
        </h2>
        <p dir="ltr" className="text-sm text-foreground font-mono">{auth.user.email}</p>
      </section>

      <section className="space-y-3 border-t border-border pt-6">
        <h2 className="flex items-center gap-2 text-sm font-medium text-text-secondary">
          <KeyRound size={14} /> החלפת סיסמה
        </h2>
        <form onSubmit={submitPasswordChange} noValidate className="space-y-3 max-w-sm">
          <div className="space-y-1.5">
            <Label htmlFor="acct-current">סיסמה נוכחית</Label>
            <Input id="acct-current" type="password" dir="ltr" autoComplete="current-password"
              value={currentPw} onChange={(e) => setCurrentPw(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="acct-new">סיסמה חדשה (לפחות 8 תווים)</Label>
            <Input id="acct-new" type="password" dir="ltr" autoComplete="new-password"
              value={newPw} onChange={(e) => setNewPw(e.target.value)} />
          </div>
          {pwNotice && (
            <p role="alert" className={
              pwNotice.tone === "ok" ? "text-xs text-signal-high" : "text-xs text-signal-hidden"
            }>
              {pwNotice.text}
            </p>
          )}
          <Button type="submit" disabled={pwBusy}>
            {pwBusy ? "מעדכנים…" : "עדכון סיסמה"}
          </Button>
          <p className="text-xs text-text-dim">
            עדכון הסיסמה מנתק את כל ההתחברויות האחרות; ההתחברות הנוכחית נשארת.
          </p>
        </form>
      </section>

      <section className="space-y-3 border-t border-border pt-6">
        <h2 className="flex items-center gap-2 text-sm font-medium text-text-secondary">
          <LogOut size={14} /> התנתקות
        </h2>
        <Button variant="outline" onClick={() => auth.logout()}>התנתקות מהחשבון</Button>
      </section>

      <section className="space-y-3 border-t border-border pt-6">
        <h2 className="flex items-center gap-2 text-sm font-medium text-signal-hidden">
          <Trash2 size={14} /> מחיקת חשבון
        </h2>
        <p className="text-xs text-text-secondary max-w-sm">
          מחיקה מסירה לצמיתות את החשבון, הפרופיל, הכיול, המשובים והלמידה.
          הכתבות עצמן הן מידע כללי ואינן נמחקות.
        </p>
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="destructive">מחיקת החשבון…</Button>
          </AlertDialogTrigger>
          <AlertDialogContent dir="rtl">
            <AlertDialogHeader>
              <AlertDialogTitle>מחיקת החשבון לצמיתות</AlertDialogTitle>
              <AlertDialogDescription>
                הפעולה בלתי הפיכה — אין דרך לשחזר את הפרופיל, הכיול או המשובים.
                לאישור, הזינו את הסיסמה הנוכחית.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <div className="space-y-1.5">
              <Label htmlFor="acct-delete-pw">סיסמה נוכחית</Label>
              <Input id="acct-delete-pw" type="password" dir="ltr"
                autoComplete="current-password"
                value={deletePw} onChange={(e) => setDeletePw(e.target.value)} />
              {deleteNotice && (
                <p role="alert" className="text-xs text-signal-hidden">{deleteNotice}</p>
              )}
            </div>
            <AlertDialogFooter>
              <AlertDialogCancel>ביטול</AlertDialogCancel>
              <AlertDialogAction
                onClick={(e) => { e.preventDefault(); confirmDelete(); }}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                מחיקה לצמיתות
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </section>
    </div>
  );
}
