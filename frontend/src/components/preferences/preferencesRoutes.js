export const PREFERENCE_TABS = [
  { id: "following", label: "מה אני עוקב", path: "/preferences" },
  { id: "calibration", label: "כיוונון", path: "/preferences/calibration" },
  { id: "learned", label: "מה המערכת למדה", path: "/preferences/learned" },
  { id: "muted", label: "מושתק", path: "/preferences/muted" },
];

export function preferenceTab(pathname) {
  const path = pathname.replace(/\/$/, "");
  return PREFERENCE_TABS.find((tab) => tab.path === path)?.id ?? null;
}

export function legacyPreferencesTarget(pathname, search = "", hash = "") {
  const target = pathname === "/calibration" ? "/preferences/calibration" : "/preferences";
  return `${target}${search}${hash}`;
}

// Manual activation: arrows move focus; Enter/Space follows the real link.
export function adjacentTab(id, key) {
  const index = PREFERENCE_TABS.findIndex((tab) => tab.id === id);
  if (key === "Home") return PREFERENCE_TABS[0].id;
  if (key === "End") return PREFERENCE_TABS.at(-1).id;
  if (key !== "ArrowLeft" && key !== "ArrowRight") return null;
  const offset = key === "ArrowLeft" ? 1 : -1;
  return PREFERENCE_TABS[(index + offset + PREFERENCE_TABS.length) % PREFERENCE_TABS.length].id;
}
