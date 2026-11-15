// Timezone-aware formatting for results (issue #178).
// The backend stores UTC; the product is Israel-facing, so game times are shown
// in Asia/Jerusalem consistently (not the viewer's browser zone).

export const APP_TIME_ZONE = "Asia/Jerusalem";

// "YYYY-MM-DD" in the app timezone — the chronological grouping key.
export function jerusalemDayKey(startTimeIso) {
  if (!startTimeIso) return null;
  const d = new Date(startTimeIso);
  if (Number.isNaN(d.getTime())) return null;
  // en-CA renders ISO-style YYYY-MM-DD.
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: APP_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

// "HH:mm" in the app timezone, or "" when unknown.
export function formatGameTime(startTimeIso) {
  if (!startTimeIso) return "";
  const d = new Date(startTimeIso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("he-IL", {
    timeZone: APP_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
}

// A human day heading in Hebrew, relative when possible ("היום"/"אתמול").
export function formatDayHeading(dayKey, now = new Date()) {
  if (!dayKey) return "ללא תאריך";
  const todayKey = jerusalemDayKey(now.toISOString());
  const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  const yesterdayKey = jerusalemDayKey(yesterday.toISOString());
  if (dayKey === todayKey) return "היום";
  if (dayKey === yesterdayKey) return "אתמול";
  // dayKey is "YYYY-MM-DD"; render as a Hebrew calendar date.
  const [y, m, d] = dayKey.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d, 12, 0, 0));
  if (Number.isNaN(dt.getTime())) return dayKey;
  return new Intl.DateTimeFormat("he-IL", {
    timeZone: "UTC",
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(dt);
}

const dayDate = (dayKey) => {
  const [y, m, d] = dayKey.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d, 12, 0, 0));
};
const weekdayOf = (dayKey) => new Intl.DateTimeFormat("he-IL", { timeZone: "UTC", weekday: "long" })
  .format(dayDate(dayKey)).replace(/^יום\s+/, "");

// "שבת, 14 בנובמבר": weekday and date without the year, for headings and popups.
export function formatDayLong(dayKey) {
  if (!dayKey) return "";
  const date = new Intl.DateTimeFormat("he-IL", { timeZone: "UTC", day: "numeric", month: "long" }).format(dayDate(dayKey));
  return `${weekdayOf(dayKey)}, ${date}`;
}

// "חמישי 12.11": the compact label of a date chip.
export function formatDayChip(dayKey) {
  if (!dayKey) return "";
  const [, m, d] = dayKey.split("-").map(Number);
  return `${weekdayOf(dayKey)} ${d}.${m}`;
}

// The weekday alone ("חמישי"), the title of an older day section.
export function formatWeekday(dayKey) {
  return dayKey ? weekdayOf(dayKey) : "";
}
