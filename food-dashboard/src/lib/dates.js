const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** "2026-09-17" -> "September 17, 2026", without a Date object's timezone shift. */
export function fmtDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
  if (!m) return iso || "";
  return `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}`;
}

/** "2026-09-17" -> "September 2026". */
export function fmtMonth(iso) {
  const m = /^(\d{4})-(\d{2})/.exec(iso || "");
  if (!m) return iso || "";
  return `${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
}

/** "2026-09-17" -> "Sep 2026", for a chart axis and a table cell. */
export function fmtShort(iso) {
  const m = /^(\d{4})-(\d{2})/.exec(iso || "");
  if (!m) return iso || "";
  return `${MONTHS[Number(m[2]) - 1].slice(0, 3)} ${m[1]}`;
}
