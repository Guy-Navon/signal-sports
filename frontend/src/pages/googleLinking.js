// Connect / disconnect Google from the Account page (#330). The callback
// reports back as /account?google=linked or /account?google=link_<reason>;
// deletion (#331) uses the same parameter with its own codes, so each
// section claims only its own. Pure, so it is unit-testable.

const MESSAGES = {
  linked: "Google חובר לחשבון. מעכשיו אפשר להיכנס גם עם Google.",
  link_cancelled: "החיבור ל-Google בוטל.",
  link_expired: "תוקף החיבור ל-Google פג. נסו שוב.",
  link_unavailable: "Google לא זמין כרגע. נסו שוב בעוד רגע.",
  link_invalid: "לא הצלחנו לאמת את החשבון מול Google. נסו שוב.",
  link_failed: "החיבור ל-Google לא הושלם. התחילו שוב מהדף הזה.",
  link_taken: "חשבון ה-Google הזה כבר מחובר לחשבון אחר ב-Signal.",
  link_already: "לחשבון הזה כבר מחובר חשבון Google.",
};

export const LINK_CODES = Object.keys(MESSAGES);

export function isLinkCode(code) {
  return typeof code === "string" && (code === "linked" || code.startsWith("link_"));
}

export function linkNoticeMessage(code) {
  return MESSAGES[code] || MESSAGES.link_failed;
}
