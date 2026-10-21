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
  // A Google sign-up on a non-Gmail address (#329): the address is proven by
  // an emailed link, then one more Google sign-in.
  check_email:
    "שלחנו קישור אימות לכתובת האימייל של חשבון ה-Google. פתחו אותו והמשיכו עם אותו חשבון Google כדי לסיים את ההרשמה.",
  check_email_recent:
    "כבר שלחנו קישור אימות לפני רגע. חפשו אותו בתיבת האימייל (גם בספאם).",
  check_email_send_failed: "לא הצלחנו לשלוח את קישור האימות. נסו להתחבר עם Google שוב בעוד דקה.",
  too_many: "יותר מדי ניסיונות. נסו שוב מאוחר יותר.",
  mail_unavailable: "לא ניתן לשלוח אימיילים כרגע, ולכן ההרשמה עם הכתובת הזאת לא זמינה.",
  verify_expired: "קישור האימות כבר לא בתוקף. התחברו עם Google שוב כדי לקבל קישור חדש.",
  verify_wrong_account:
    "הקישור שייך לחשבון Google אחר. בחרו את חשבון ה-Google שאיתו נרשמתם.",
  verify_email_changed:
    "כתובת האימייל של חשבון ה-Google השתנתה מאז ההרשמה. התחברו עם Google שוב כדי לקבל קישור לכתובת החדשה.",
  account_exists:
    "כבר יש חשבון עם האימייל הזה. התחברו עם הסיסמה שלו.",
  signup_closed: "ההרשמה סגורה, והכתובת הזאת לא ברשימת המוזמנים.",
};

export const GOOGLE_NOTICE_CODES = Object.keys(MESSAGES);

const INFO_CODES = new Set(["check_email", "check_email_recent"]);

// "check your inbox" is a next step, not a failure.
export function googleNoticeTone(code) {
  return INFO_CODES.has(code) ? "info" : "error";
}

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
