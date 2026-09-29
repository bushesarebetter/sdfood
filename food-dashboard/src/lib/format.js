/**
 * The listed places as a spreadsheet, one row per place, from the index.
 *
 * The record columns are the County's (the grade through lib/grades.js, the
 * same text every view shows); `flags` is our reading of the 12 months before
 * the list date (24 for the escalation facts). `band`, `points` and
 * `what_band_means` exist only in `bands` mode; a record export has no
 * position, band or points column. Every row carries the date the list was
 * drawn up and the date it expires: the terms allow reuse only with the list
 * date attached, and never after it expires.
 */
import { gradeView } from "./grades.js";
import { typeLabel } from "./inspections.js";
import { shownBand } from "./marks.js";
import { bandSummary, isOutside } from "./bands.js";
import { auditCsv } from "./staff.js";

// Text a spreadsheet would run as a formula (a leading =, +, -, @, tab or carriage return) gets a
// leading apostrophe; numbers, and text that is just a number, are left alone.
const FORMULA = /^[=+\-@\t\r]/;
const cell = (v) => {
  let s = v == null ? "" : String(v);
  if (typeof v === "string" && FORMULA.test(s) && !Number.isFinite(Number(s))) s = "'" + s;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

const RECORD_COLUMNS = [
  "facility_id", "name", "address", "facility_type", "council_district",
  "last_visit_date", "last_visit_type",
  "grade", "grade_score", "grade_date", "replaced_grade", "replaced_score", "replaced_date",
  "flags", "lon", "lat",
];
const BAND_COLUMNS = ["band", "points", "under_review", "what_band_means"];
const DATE_COLUMNS = ["list_date", "inspections_through", "expires", "list_run"];

export function csvColumns({ mode = "record" } = {}) {
  return mode === "bands"
    ? [...RECORD_COLUMNS.slice(0, 5), ...BAND_COLUMNS, ...RECORD_COLUMNS.slice(5), ...DATE_COLUMNS]
    : [...RECORD_COLUMNS, ...DATE_COLUMNS];
}

/** Beside a band in a spreadsheet, so a row passed on alone still says what the band is. */
export const BAND_SOURCE = "Students' point rule, not a County rating.";

/** Beside points with no band: where the number comes from, so it says something when passed on alone. */
export const POINTS_SOURCE =
  "100 minus the average routine score over the two years before the list date (a health closure counted as 70); in no band. " +
  "Students' point rule, not a County rating.";

/**
 * What a row's band means: the band's line as the place's page states it, then BAND_SOURCE; for
 * points with no band, POINTS_SOURCE; "" with neither (or on hold).
 */
export function bandMeaning(p, meta, { mode = "bands" } = {}) {
  const b = shownBand(p, { mode });
  if (!b) return mode === "bands" && p?.points != null && !p?.on_hold ? POINTS_SOURCE : "";
  return `${bandSummary(meta, b, { outside: isOutside(p, meta), district: p?.council_district ?? null })} ${BAND_SOURCE}`;
}

export function facilitiesToCsv(features, { meta = null, mode = "record" } = {}) {
  const cols = csvColumns({ mode });
  const rows = (features ?? []).map((f) => {
    const p = f.properties ?? {};
    const g = gradeView(p.grade).csv;
    const [lon, lat] = f.geometry?.coordinates ?? ["", ""];
    const values = {
      facility_id: p.facility_id, name: p.name, address: p.address, facility_type: typeLabel(p.facility_type),
      council_district: p.council_district ?? "",
      band: shownBand(p, { mode }) ?? "", points: mode === "bands" && !p.on_hold ? p.points ?? "" : "", under_review: p.on_hold ? "yes" : "",
      what_band_means: mode === "bands" ? bandMeaning(p, meta, { mode }) : "",
      last_visit_date: p.last_visit?.date ?? "", last_visit_type: p.last_visit?.type ?? "",
      ...g,
      flags: (p.flags ?? []).join("; "), lon, lat,
      list_date: meta?.generated ?? "", inspections_through: meta?.inspections_through ?? "", expires: meta?.expires ?? "",
      list_run: meta?.run ?? "",
    };
    return cols.map((c) => cell(values[c])).join(",");
  });
  return [cols.join(","), ...rows].join("\n");
}

/**
 * The download's name says what is in it: food-inspection-record[-county][-district-3][-band-1]-<list date>.csv.
 * A file passed around a City office then carries its own scope and date.
 */
export function csvFilename(meta, filters = {}) {
  const parts = ["food-inspection-record"];
  if (filters?.county) parts.push("county");
  const d = filters?.districts ?? [];
  if (d.length) parts.push(`district-${[...d].sort((a, b) => a - b).join("-")}`);
  if (filters?.band && filters.band !== "all") parts.push(`band-${filters.band === "1" ? "1" : `1-to-${filters.band}`}`);
  if (filters?.flag) parts.push(String(filters.flag).replace(/[^a-z0-9]+/gi, "-").toLowerCase());
  parts.push(meta?.generated ?? "export");
  return `${parts.join("-")}.csv`;
}

/**
 * Save these places as a CSV in the browser, named by csvFilename. On the staff site the download
 * is also logged to the site's own server (lib/staff.js auditCsv). Returns the file name.
 */
export function saveCsv(features, { meta = null, mode = "record", filters = {} } = {}) {
  const list = features ?? [];
  const name = csvFilename(meta, filters);
  const blob = new Blob([facilitiesToCsv(list, { meta, mode })], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
  auditCsv(meta, list.length, name);
  return name;
}


/**
 * The town in a County address ("401 W MAIN ST, EL CAJON, CA 92020" -> "El Cajon"), or null. A place
 * outside the City is labelled by its own town, never as San Diego.
 */
export function cityOf(address) {
  const parts = String(address ?? "").split(",").map((x) => x.trim());
  if (parts.length < 3) return null;
  const town = parts.at(-2);
  if (!/^[A-Za-z .'-]+$/.test(town)) return null;
  return town.toLowerCase().replace(/\b([a-z])/g, (c) => c.toUpperCase());
}
