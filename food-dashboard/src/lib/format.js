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

const cell = (v) => {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

const RECORD_COLUMNS = [
  "facility_id", "name", "address", "facility_type", "council_district",
  "last_visit_date", "last_visit_type",
  "grade", "grade_score", "grade_date", "replaced_grade", "replaced_score", "replaced_date",
  "flags", "lon", "lat",
];
const BAND_COLUMNS = ["band", "points", "under_review"];
const DATE_COLUMNS = ["list_date", "inspections_through", "expires"];

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
    };
    return cols.map((c) => cell(values[c])).join(",");
  });
  return [cols.join(","), ...rows].join("\n");
}
