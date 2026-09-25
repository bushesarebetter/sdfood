/**
 * One place to decide whether a listed place is shown, and in what order.
 * The map, the table, the district counts and the address check all call
 * this, so they never disagree. Every filter reads the index only.
 *
 * filters: { band: "1" | "2" | "3" | "all", districts: number[],
 *            types: string[], flag: string | null }
 *
 * `band` applies in `bands` mode only: band 1 alone, bands 1 and 2, bands 1
 * to 3, or every listed place. A place under review is in no band. `flag` is
 * one of the index's record flags (lib/inspections.js FLAG_KEYS).
 */
import { FLAG_KEYS, FLAG_LABELS, TYPE_LABELS } from "./inspections.js";
import { shownBand } from "./marks.js";
import { ALL_PLACES } from "../constants.js";

export function inBandScope(p, band, { mode = "record" } = {}) {
  if (!p) return false;
  if (mode !== "bands" || band == null || band === ALL_PLACES) return true;
  const b = shownBand(p, { mode });
  return b != null && Number(b) <= Number(band);
}

export function passesFilters(p, filters, { mode = "record" } = {}) {
  if (!p) return false;
  const f = filters ?? {};
  if (!inBandScope(p, f.band, { mode })) return false;
  if (f.districts?.length && !f.districts.includes(p.council_district)) return false;
  if (f.types?.length && !f.types.includes(p.facility_type ?? "other")) return false;
  if (f.flag && !(p.flags ?? []).includes(f.flag)) return false;
  return true;
}

/** Places per band, cumulative, and every listed place: {"1": 29, "2": 86, "3": 200, all: 1143}. */
export function bandCounts(fc, { mode = "bands" } = {}) {
  const per = {};
  const features = fc?.features ?? [];
  for (const f of features) {
    const b = shownBand(f.properties, { mode });
    if (b != null) per[b] = (per[b] || 0) + 1;
  }
  const out = {};
  let run = 0;
  for (const b of Object.keys(per).sort((a, c) => Number(a) - Number(c))) {
    run += per[b];
    out[b] = run;
  }
  out[ALL_PLACES] = features.length;
  return out;
}

/** The record-flag chips worth showing: only flags some place in scope has, in a fixed order. */
export function flagChips(fc, filters = null, { mode = "record" } = {}) {
  if (!fc?.features) return [];
  const counts = {};
  for (const f of fc.features) {
    if (!inBandScope(f.properties, filters?.band, { mode })) continue;
    for (const k of f.properties.flags ?? []) counts[k] = (counts[k] || 0) + 1;
  }
  return FLAG_KEYS.filter((k) => counts[k]).map((key) => ({ key, label: FLAG_LABELS[key], count: counts[key] }));
}

/** The facility types present in scope, most common first. */
export function typesFor(fc, filters = null, { mode = "record" } = {}) {
  if (!fc?.features) return [];
  const counts = {};
  for (const f of fc.features) {
    if (!inBandScope(f.properties, filters?.band, { mode })) continue;
    const t = f.properties.facility_type ?? "other";
    counts[t] = (counts[t] || 0) + 1;
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([key, count]) => ({ key, label: TYPE_LABELS[key] ?? TYPE_LABELS.other, count }));
}

const byName = (a, b) => String(a.properties?.name ?? "").localeCompare(String(b.properties?.name ?? "")) || String(a.properties?.facility_id ?? "").localeCompare(String(b.properties?.facility_id ?? ""));

/**
 * The order of every list. `record` mode: by name. `bands` mode: by band
 * (places in no band, and places under review, after the bands), then points,
 * most first (places without points after those with them), then name. No
 * list ever shows a position.
 */
export function sortPlaces(features, { mode = "record" } = {}) {
  const list = [...(features ?? [])];
  if (mode !== "bands") return list.sort(byName);
  const band = (f) => {
    const b = shownBand(f.properties, { mode });
    return b == null ? 99 : Number(b);
  };
  const pts = (f) => (!f.properties?.on_hold && typeof f.properties?.points === "number" ? f.properties.points : -Infinity);
  return list.sort((a, b) => band(a) - band(b) || (pts(b) === pts(a) ? 0 : pts(b) > pts(a) ? 1 : -1) || byName(a, b));
}

/** A place's points, where the export gives them and the place is not under review; otherwise null. */
export function shownPoints(p, { mode = "record" } = {}) {
  if (mode !== "bands" || !p || p.on_hold || typeof p.points !== "number") return null;
  return p.points;
}
