const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function apiFetch(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, options);
  } catch (err) {
    throw new Error(`Cannot reach backend at ${API_BASE_URL}${path}: ${err.message}`);
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
