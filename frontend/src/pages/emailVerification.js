// Email verification for password signups (Slice A): link parsing and the
// Hebrew notices for each backend outcome. Pure, so it is unit-testable
// without a DOM renderer (docs/FRONTEND_DESIGN_SYSTEM.md §10).

// Mirrors the backend's RESEND_COOLDOWN (the server enforces it; this only
// keeps the button honest).
export const RESEND_COOLDOWN_SECONDS = 60;

// The link is /verify-email#t=<token>: a fragment never reaches the server or
// a Referer header.
export function readVerificationToken(hash) {
  const params = new URLSearchParams((hash || "").replace(/^#/, ""));
  return params.get("t") || null;
}

// The page drops the fragment from the address bar right away, but the auth
// shell can remount it (bootstrap loading → ready). Keep the token in memory
// for the life of the tab — never in storage — so a remount still has it.
let rememberedToken = null;

export function captureVerificationToken(hash) {
  const fromHash = readVerificationToken(hash);
  if (fromHash) rememberedToken = fromHash;
  return rememberedToken;
}

export function forgetVerificationToken() {
  rememberedToken = null;
}

export function isUnverifiedLogin(err) {
  const message = err?.message || "";
  return message.includes("(403)") && message.includes("Email not verified");
}

export function verificationErrorMessage(err) {
  const message = err?.message || "";
  if (message.includes("Cannot reach backend")) return "לא ניתן להתחבר לשרת כרגע";
  if (message.includes("(400)") || message.includes("(404)")) {
    return "הקישור כבר לא בתוקף. היכנסו עם האימייל והסיסמה כדי לקבל קישור חדש.";
  }
  if (message.includes("(401)")) return "אימייל או סיסמה שגויים";
  if (message.includes("(403)")) return "הסיסמה שגויה";
  if (message.includes("(409)")) return "כבר קיים חשבון עם האימייל הזה. אפשר פשוט להתחבר.";
  if (message.includes("(429)")) return "יותר מדי ניסיונות — נסו שוב בעוד רגע";
  if (message.includes("(503)")) return "לא ניתן לשלוח אימיילים כרגע. נסו שוב מאוחר יותר.";
  return "משהו השתבש — נסו שוב";
}

export function resendSecondsLeft(lastSentAtMs, nowMs) {
  if (!lastSentAtMs) return 0;
  const left = RESEND_COOLDOWN_SECONDS - (nowMs - lastSentAtMs) / 1000;
  return Math.max(0, Math.ceil(left));
}
