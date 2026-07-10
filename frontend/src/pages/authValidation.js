// Pure form-validation rules for the auth pages (User Platform PR 3, #51).
// Mirrors the backend contract (routes_auth): email shape, password >= 8.
// Extracted so validation states are unit-testable without a DOM renderer.

export function validateEmail(email) {
  const value = (email || "").trim();
  if (!value) return "נדרשת כתובת אימייל";
  if (!value.includes("@") || value.startsWith("@") || value.endsWith("@")) {
    return "כתובת אימייל לא תקינה";
  }
  return null;
}

export function validateLoginPassword(password) {
  if (!password) return "נדרשת סיסמה";
  return null;
}

export function validateSignupPassword(password) {
  if (!password) return "נדרשת סיסמה";
  if (password.length < 8) return "הסיסמה חייבת להכיל לפחות 8 תווים";
  return null;
}

export function validateLoginForm({ email, password }) {
  return {
    email: validateEmail(email),
    password: validateLoginPassword(password),
  };
}

export function validateSignupForm({ email, password }) {
  return {
    email: validateEmail(email),
    password: validateSignupPassword(password),
  };
}

export function hasErrors(errors) {
  return Object.values(errors).some(Boolean);
}

// Map backend auth failures to product-voice Hebrew notices.
export function authErrorMessage(err) {
  const message = err?.message || "";
  if (message.includes("(401)")) return "אימייל או סיסמה שגויים";
  if (message.includes("(409)")) return "כתובת האימייל כבר רשומה במערכת";
  if (message.includes("(429)")) return "יותר מדי ניסיונות התחברות — נסו שוב בעוד רגע";
  if (message.includes("Cannot reach backend")) return "לא ניתן להתחבר לשרת כרגע";
  return "משהו השתבש — נסו שוב";
}
