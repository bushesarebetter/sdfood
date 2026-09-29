/**
 * When an export stops being shown as a list.
 *
 * A real export carries `meta.expires` (`inspections_through` + 14 days).
 * After it, the County's record has moved on far enough that the export no
 * longer describes the places, so the site closes down to a notice and a
 * search of the record it holds: no list, no map list, no bands, no headline
 * claim. The sample carries `expires: null` and never expires. The build
 * refuses a real export that has already expired (scripts/check-expiry.mjs).
 */
import { fmtDate } from "./dates.js";

const ISO_DAY = /^(\d{4}-\d{2}-\d{2})/;

/** A Date as "YYYY-MM-DD" in the viewer's own time zone. */
export function isoDay(d = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * True when meta.expires is set and `today` is after it. `today` is a Date or
 * an ISO date string; the expiry day itself still counts as current.
 */
export function isExpired(meta, today = new Date()) {
  const m = ISO_DAY.exec(meta?.expires ?? "");
  if (!m) return false;
  const t = typeof today === "string" ? ISO_DAY.exec(today)?.[1] : isoDay(today);
  if (!t) return false;
  return t > m[1];
}

/** Whole days from `today` to meta.expires (0 on the expiry day itself), or null without an expiry. */
export function daysLeft(meta, today = new Date()) {
  const m = ISO_DAY.exec(meta?.expires ?? "");
  const t = typeof today === "string" ? ISO_DAY.exec(today)?.[1] : isoDay(today);
  if (!m || !t) return null;
  return Math.round((Date.parse(`${m[1]}T00:00:00Z`) - Date.parse(`${t}T00:00:00Z`)) / 864e5);
}

/** Within SOON_DAYS of expiry, and not yet expired: say when the list goes search-only, and who refreshes it. */
export const SOON_DAYS = 3;
export function soonNotice(meta, today = new Date()) {
  const d = daysLeft(meta, today);
  if (d == null || d < 0 || d > SOON_DAYS) return null;
  const who = meta?.operator?.name ? ` It is refreshed by ${meta.operator.name}.` : "";
  const when = d === 0 ? "today" : d === 1 ? "tomorrow" : `in ${d} days`;
  return `This list goes search-only ${when}, on ${fmtDate(meta.expires)}, unless it is refreshed.${who}`;
}

export function expiryNotice(meta) {
  const since = meta?.inspections_through ? fmtDate(meta.inspections_through) : "this export was made";
  return `This export is out of date. The County's record has moved on since ${since}, so this site now offers only a search of the record it holds. The County's own search has current results.`;
}
