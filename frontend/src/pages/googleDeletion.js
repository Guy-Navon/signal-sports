// Self-deletion of a Google-only account (#331). The Google callback returns
// to /account?delete=confirm (a single-use deletion grant now exists for this
// session, ~5 minutes) or /account?google=<code>. Pure, so it is unit-testable
// without a DOM renderer.

const MESSAGES = {
  cancelled: "האישור מול Google בוטל. החשבון לא נמחק.",
  expired: "תוקף האישור מול Google פג. התחילו שוב.",
  unavailable: "Google לא זמין כרגע. נסו שוב בעוד רגע.",
  failed: "האישור מול Google נכשל. החשבון לא נמחק.",
  invalid: "לא הצלחנו לאמת את האישור מול Google. נסו שוב.",
  delete_failed: "האישור לא הושלם בהתחברות הזאת. התחילו שוב מהדף הזה.",
  delete_wrong_account:
    "האישור נעשה עם חשבון Google אחר. בחרו את חשבון ה-Google שמחובר לחשבון הזה.",
};

export const ACCOUNT_GOOGLE_CODES = Object.keys(MESSAGES);

// The auth shell can remount the page after the URL is cleaned; keep the
// state in memory (never in storage) until the person acts.
let remembered = { confirm: false, code: null };

export function captureAccountGoogleState(search) {
  const params = new URLSearchParams(search || "");
  if (params.get("delete") === "confirm") {
    remembered = { confirm: true, code: null };
  } else if (params.get("google")) {
    remembered = { confirm: false, code: params.get("google") };
  }
  return remembered;
}

export function forgetAccountGoogleState() {
  remembered = { confirm: false, code: null };
}

export function deletionNoticeMessage(code) {
  return MESSAGES[code] || MESSAGES.failed;
}

export function matchesAccountEmail(typed, accountEmail) {
  const value = (typed || "").trim().toLowerCase();
  return Boolean(value) && value === (accountEmail || "").toLowerCase();
}
