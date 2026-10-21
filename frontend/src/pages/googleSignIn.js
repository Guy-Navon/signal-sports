// Google sign-in (Slice B1): the fixed notices the callback sends back as
// /login?google=<code>, and the Account page's view of password-less
// accounts. Pure, so it is unit-testable without a DOM renderer.

const MESSAGES = {
  cancelled: "ההתחברות עם Google בוטלה.",
  expired: "תוקף ההתחברות עם Google פג. נסו שוב.",
  unavailable: "Google לא זמין כרגע. נסו שוב בעוד רגע, או התחברו עם סיסמה.",
  failed: "ההתחברות עם Google נכשלה. נסו שוב.",
  invalid: "לא הצלחנו לאמת את החשבון מול Google. נסו שוב.",
  unverified_email: "כתובת האימייל בחשבון Google הזה לא מאומתת אצל Google.",
  unsupported_email:
    "אפשר להירשם עם Google כרגע רק עם Gmail או חשבון ארגוני של Google. אפשר לפתוח חשבון בהרשמה עם אימייל וסיסמה.",
  account_exists:
    "כבר יש חשבון עם האימייל הזה. התחברו עם הסיסמה שלו.",
  signup_closed: "ההרשמה סגורה, והכתובת הזאת לא ברשימת המוזמנים.",
};

export const GOOGLE_NOTICE_CODES = Object.keys(MESSAGES);

export function readGoogleNotice(search) {
  return new URLSearchParams(search || "").get("google") || null;
}

// Login drops ?google= from the address bar, but the auth shell can remount
// the page afterwards (bootstrap loading → ready). Keep the code in memory
// until the person acts, so a remount still shows the notice.
let rememberedNotice = null;

export function captureGoogleNotice(search) {
  const fromUrl = readGoogleNotice(search);
  if (fromUrl) rememberedNotice = fromUrl;
  return rememberedNotice;
}

export function dismissGoogleNotice() {
  rememberedNotice = null;
}

export function googleNoticeMessage(code) {
  return MESSAGES[code] || MESSAGES.failed;
}

// Accounts created through Google have no password: nothing to change, and
// deleting them needs the Google confirmation flow (not built yet).
export function accountHasPassword(user) {
  return user?.has_password !== false;
}
