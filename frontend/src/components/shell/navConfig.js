import { Rss, Settings, Sliders, BarChart2, Database, Bug, FlaskConical, Terminal } from "lucide-react";

// Product area — the consumer experience.
export const PRODUCT_NAV_ITEMS = [
  { path: "/", label: "פיד אישי", icon: Rss },
  { path: "/preferences", label: "העדפות", icon: Settings },
  { path: "/calibration", label: "כיוונון", icon: Sliders },
  { path: "/results", label: "תוצאות", icon: BarChart2 },
];

// Ops console — dev/QA tooling, visually separated from the product.
export const OPS_NAV_ITEMS = [
  { path: "/sources", label: "מקורות", icon: Database },
  { path: "/debug", label: "דיבאג", icon: Bug },
  { path: "/llm-qa", label: "QA LLM", icon: FlaskConical, backendOnly: true },
];

export const OPS_PATHS = OPS_NAV_ITEMS.map((item) => item.path);

export function getOpsNavItems(isBackendMode) {
  return OPS_NAV_ITEMS.filter((item) => !item.backendOnly || isBackendMode);
}

export function getAreaForPath(pathname) {
  return OPS_PATHS.includes(pathname) ? "ops" : "product";
}

// Mobile bottom bar: current area's items plus one entry to cross over.
export function getMobileNavItems(area, isBackendMode) {
  if (area === "ops") {
    return [...getOpsNavItems(isBackendMode), { path: "/", label: "לפיד", icon: Rss }];
  }
  return [...PRODUCT_NAV_ITEMS, { path: "/sources", label: "קונסולה", icon: Terminal }];
}
