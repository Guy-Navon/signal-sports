// Password reset by email (#200): the /reset-password#t=<token> link and the
// Hebrew outcome messages. Pure, so it is unit-testable without a DOM.

// The same words whatever happened server-side: the backend answers alike for
// an unknown address, a Google-only account and a real one.
export const FORGOT_SENT_MESSAGE =
  "אם יש חשבון עם סיסמה בכתובת הזאת, שלחנו אליה קישור לבחירת סיסמה חדשה. הקישור תקף לשעה.";

// The auth shell can remount the page after the fragment is cleared; keep the
// token in memory for the life of the tab (never in storage).
let rememberedToken = null;

export function captureResetToken(hash) {
  const token = new URLSearchParams((hash || "").replace(/^#/, "")).get("t");
  if (token) rememberedToken = token;
  return rememberedToken;
}

export function forgetResetToken() {
  rememberedToken = null;
}

export function resetErrorMessage(err) {
  const message = err?.message || "";
  if (message.includes("Cannot reach backend")) return "לא ניתן להתחבר לשרת כרגע";
  if (message.includes("(400)") || message.includes("(404)")) {
    return "הקישור כבר לא בתוקף. בקשו קישור חדש.";
  }
  if (message.includes("(422)")) return "הסיסמה חייבת להכיל לפחות 8 תווים";
  if (message.includes("(503)")) return "לא ניתן לשלוח אימיילים כרגע. נסו שוב מאוחר יותר.";
  return "משהו השתבש — נסו שוב";
}
