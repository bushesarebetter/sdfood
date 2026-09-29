/**
 * The listed places as a spreadsheet, one row per place, from the index.
 *
 * The record columns are the County's (the grade through lib/grades.js, the
 * same text every view shows); `flags` is our reading of the 12 months before
 * the last visit. `band` and `points` exist only in `bands` mode; a record
 * export has no position, band or points column. Every row carries the date
 * the list was drawn up and the date it expires: the terms allow reuse only
 * with the list date attached, and never after it expires.
 */
import { gradeView } from "./grades.js";
import { typeLabel } from "./inspections.js";
import { shownBand } from "./marks.js";

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
const BAND_COLUMNS = ["band", "points", "under_review"];
const DATE_COLUMNS = ["list_date", "inspections_through", "expires", "list_run"];

export function csvColumns({ mode = "record" } = {}) {
  return mode === "bands"
    ? [...RECORD_COLUMNS.slice(0, 5), ...BAND_COLUMNS, ...RECORD_COLUMNS.slice(5), ...DATE_COLUMNS]
    : [...RECORD_COLUMNS, ...DATE_COLUMNS];
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
