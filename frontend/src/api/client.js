// Default is same-origin: relative paths served through the Vite dev proxy
// (see vite.config.js). Set VITE_API_BASE_URL only to hit a backend directly
// (cross-origin), e.g. http://127.0.0.1:8000 without the proxy.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

// Session-expiry signal (User Platform PR 3, issue #51): any authenticated
// API call that comes back 401 means the cookie session is gone — AuthContext
// listens for this event, clears the user, and redirects to /login. Auth
// routes themselves are excluded (a failed login is not an expired session).
export const AUTH_EXPIRED_EVENT = "signal:auth-expired";

function emitAuthExpired(path) {
  if (typeof window === "undefined" || path.startsWith("/api/auth/")) return;
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, { detail: { path } }));
}

async function apiFetch(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, options);
  } catch (err) {
    throw new Error(`Cannot reach backend at ${API_BASE_URL}${path}: ${err.message}`);
  }
  if (res.status === 401) {
    emitAuthExpired(path);
  }
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      detail = await res.text().catch(() => "");
    }
    throw new Error(`API ${options.method || "GET"} ${path} failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export function getHealth() {
  return apiFetch("/health");
}

export function getProfiles() {
  return apiFetch("/api/profiles");
}

export function getProfile(userId) {
  return apiFetch(`/api/profiles/${userId}`);
}

export function getArticles() {
  return apiFetch("/api/articles");
}

export function getFeed(userId) {
  return apiFetch(`/api/feed/${userId}`);
}

export function getDebugFeed(userId) {
  return apiFetch(`/api/debug/feed/${userId}`);
}

export function submitFeedback(payload) {
  return apiFetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getCalibrationHeadlines() {
  return apiFetch("/api/calibration/headlines");
}

export function getIngestSources() {
  return apiFetch("/api/ingest/sources");
}

export function runIngestion(sourceId) {
  const path = sourceId
    ? `/api/ingest/run?source_id=${encodeURIComponent(sourceId)}`
    : "/api/ingest/run";
  return apiFetch(path, { method: "POST" });
}

export function getIngestRuns(limit = 5) {
  return apiFetch(`/api/ingest/runs?limit=${limit}`);
}

export function getIngestQuality() {
  return apiFetch("/api/ingest/quality");
}

/** Calibration V2 (issue #33) — backend-owned dataset + inference. */
export function getCalibrationItems() {
  return apiFetch("/api/calibration/items");
}

export function previewCalibration(ratings) {
  return apiFetch("/api/calibration/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ratings }),
  });
}

export function applyCalibration(userId, ratings) {
  return apiFetch("/api/calibration/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, ratings }),
  });
}

export function getCalibrationResponses(userId) {
  return apiFetch(`/api/calibration/responses/${encodeURIComponent(userId)}`);
}

/** Feedback learning (issue #34). */
export function getLearningState(userId) {
  return apiFetch(`/api/learning/${encodeURIComponent(userId)}`);
}

export function resetLearning(userId, feature = {}) {
  return apiFetch(`/api/learning/${encodeURIComponent(userId)}/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(feature),
  });
}

export function neverShow(userId, articleId) {
  return apiFetch(`/api/profiles/${encodeURIComponent(userId)}/never_show`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ article_id: articleId }),
  });
}

/** Shadow-mode comparison (issue #32): legacy vs Preference V2 decisions. */
export function getShadowReport(userId) {
  return apiFetch(`/api/debug/shadow/${encodeURIComponent(userId)}`);
}

export function getClassifyStatus() {
  return apiFetch("/api/classify/status");
}

export function classifyBackfill({ sourceId, limit, dryRun = false, force = false } = {}) {
  const params = new URLSearchParams();
  if (sourceId) params.set("source_id", sourceId);
  if (limit != null) params.set("limit", String(limit));
  if (dryRun) params.set("dry_run", "true");
  if (force) params.set("force", "true");
  const qs = params.toString();
  return apiFetch(`/api/classify/backfill${qs ? `?${qs}` : ""}`, { method: "POST" });
}

export function resetRssData() {
  return apiFetch("/api/dev/reset-rss-data", { method: "POST" });
}

export function runLlmGatingBenchmark() {
  return apiFetch("/api/dev/benchmark/llm-gating", { method: "POST" });
}

export function getSchedulerStatus() {
  return apiFetch("/api/ingest/scheduler/status");
}

export function runSchedulerNow() {
  return apiFetch("/api/ingest/scheduler/run-now", { method: "POST" });
}

export function getSourceHealth() {
  return apiFetch("/api/ingest/source-health");
}

// Enable/disable a source at runtime (persisted override; wins over config default).
export function setSourceEnabled(sourceId, enabled) {
  return apiFetch(`/api/ingest/sources/${encodeURIComponent(sourceId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}

// True when the error came from the shared ingestion lock (HTTP 409).
// apiFetch embeds the status code and the JSON detail in the error message.
export function isIngestionBusyError(err) {
  const msg = err?.message || "";
  return msg.includes("(409)") || msg.includes("ingestion_already_running");
}

/** Auth shell (User Platform PR 3, issue #51). Cookies ride same-origin
 * fetch automatically — no header or token work. */
export function getAuthSession() {
  return apiFetch("/api/auth/session");
}

export function authLogin(email, password) {
  return apiFetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export function authSignup({ email, password, displayName }) {
  return apiFetch("/api/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, display_name: displayName || null }),
  });
}

export function authLogout() {
  return apiFetch("/api/auth/logout", { method: "POST" });
}

/** Consumer /api/me/* surface (User Platform PR 5, #53) — session-derived
 * identity; the product uses these under enforcement instead of {user_id}. */
export function getMeProfile() {
  return apiFetch("/api/me/profile");
}

export function getMeFeed() {
  return apiFetch("/api/me/feed");
}

export function submitMeFeedback(articleId, action) {
  return apiFetch("/api/me/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ article_id: articleId, action }),
  });
}

export function meNeverShow(articleId) {
  return apiFetch("/api/me/never_show", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ article_id: articleId }),
  });
}

export function applyMeCalibration(ratings) {
  return apiFetch("/api/me/calibration/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ratings }),
  });
}

export function getMeCalibrationResponses() {
  return apiFetch("/api/me/calibration/responses");
}

export function getMeLearningState() {
  return apiFetch("/api/me/learning");
}

export function resetMeLearning(feature = {}) {
  return apiFetch("/api/me/learning/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(feature),
  });
}

export function saveMeCalibrationResponses(ratings) {
  return apiFetch("/api/me/calibration/responses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ratings }),
  });
}

export function completeMeOnboarding() {
  return apiFetch("/api/me/onboarding/complete", { method: "POST" });
}

/** Account lifecycle (User Platform PR 7, #55). */
export function changeMePassword(currentPassword, newPassword) {
  return apiFetch("/api/me/password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export function deleteMeAccount(currentPassword) {
  return apiFetch("/api/me/account", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password: currentPassword }),
  });
}
