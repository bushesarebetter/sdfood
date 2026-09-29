/**
 * The listed places as a spreadsheet, one row per place, from the index.
 *
 * The record columns are the County's (the grade through lib/grades.js, the
 * same text every view shows); `flags` is our reading of the 12 months before
 * the list date (24 for the escalation facts). `band`, `points` and
 * `what_band_means` exist only in `bands` mode; a record export has no
 * position, band or points column. Every row carries the date the list was
 * drawn up and the date it expires: the terms allow reuse only with the list
 * date attached, and never after it expires. The list's printout (listPrint*)
 * shows the same places in the list's own order, as plain text.
 */
import { gradeView } from "./grades.js";
import { FLAG_LABELS, typeLabel, typePlural, visitLabel } from "./inspections.js";
import { markFor, shownBand } from "./marks.js";
import { bandSummary, isOutside } from "./bands.js";
import { auditCsv } from "./staff.js";
import { flagWindow, lastVisitStale, STALE_LABEL } from "./filters.js";
import { fmtShort } from "./dates.js";
import { ALL_PLACES, BAND_FILTERS } from "../constants.js";
import { SITE } from "../site.js";

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

/** The list printout's column heads: the list's own columns. */
export function listPrintColumns({ mode = "record" } = {}) {
  return [...(mode === "bands" ? ["Band", "Points"] : []), "Place", "Kind", "District", "Latest grade", "Last visit",
    "12 months before the list date (our reading)"];
}

/**
 * The list's printout, one row per place in the order given (the list's filters, search and sort,
 * every page, not the 50 on screen): the cells the list shows, as text. The place's cell is its name
 * and, on a second line, its address.
 */
export function listPrintRows(features, { meta = null, mode = "record" } = {}) {
  return (features ?? []).map((f) => {
    const p = f.properties ?? {};
    const g = gradeView(p.grade);
    const v = p.last_visit;
    const last = v ? `${fmtShort(v.date)}, ${visitLabel(v.type)}${lastVisitStale(p, meta) ? ` (${STALE_LABEL})` : ""}` : "";
    return [
      ...(mode === "bands" ? [markFor(p, { mode }).label ?? "", !p.on_hold && typeof p.points === "number" ? String(p.points) : ""] : []),
      [p.name, p.address].filter((x) => typeof x === "string" && x).join("\n"),
      typeLabel(p.facility_type),
      p.council_district ? `D${p.council_district}` : "",
      g.graded || g.closedOpen ? g.short : g.withDate ?? g.text.toLowerCase(),
      last,
      (p.flags ?? []).map((k) => FLAG_LABELS[k] ?? k).join("; "),
    ];
  });
}

const lowerFirst = (s) => (s ? `${s.charAt(0).toLowerCase()}${s.slice(1)}` : s);
const andList = (xs) => (xs.length > 1 ? `${xs.slice(0, -1).join(", ")} and ${xs.at(-1)}` : `${xs[0] ?? ""}`);

/**
 * What a list holds, in words, for the head of its printout: "In the City of San Diego; council
 * district 3; bands 1 to 3; restaurants; a major violation in the 12 months before the list date (our
 * reading); names or streets matching "taco"."
 */
export function listScope(filters = {}, { mode = "record", search = "" } = {}) {
  const district = SITE.districts.label.toLowerCase();
  const d = [...(filters?.districts ?? [])].sort((a, b) => a - b);
  const parts = [filters?.county ? `Across ${SITE.county}` : `In the ${SITE.fullName}`,
    d.length ? `${district}${d.length > 1 ? "s" : ""} ${andList(d)}` : `every ${district}`];
  if (mode === "bands") parts.push(lowerFirst(BAND_FILTERS.find((b) => b.band === (filters?.band ?? ALL_PLACES))?.label ?? "every listed place"));
  if (filters?.types?.length) parts.push(andList(filters.types.map(typePlural)));
  if (filters?.flag) parts.push(`${lowerFirst(FLAG_LABELS[filters.flag] ?? filters.flag)} ${flagWindow(filters.flag)} (our reading)`);
  const q = String(search ?? "").trim();
  if (q) parts.push(`names or streets matching "${q}"`);
  return `${parts.join("; ")}.`;
}

/**
 * What a list's printout is logged under on the staff site (lib/staff.js describePrints): "list " and
 * its CSV file name's stem, which carries its scope and list date; a search is noted, never its text.
 */
export function listPrintName(meta, filters = {}, { search = "" } = {}) {
  return `list ${csvFilename(meta, filters).replace(/\.csv$/, "")}${String(search ?? "").trim() ? ", searched" : ""}`.slice(0, 120);
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
