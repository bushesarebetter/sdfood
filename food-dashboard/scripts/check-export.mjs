#!/usr/bin/env node
/**
 * Check the export the site is about to ship against the contract
 * (docs/FOOD_DATA_CONTRACT.md, version 3.2): the index, every place file,
 * and meta.json.
 *
 * Fails on:
 *  - an index larger than 3 MB (8 MB with --review: an unpublished export
 *    lists every active place county-wide), a mode outside record|bands, or
 *    meta.places that does not count the index;
 *  - a feature property not in the contract (rank, percentile, oof_rank,
 *    score, shap_features, is_known_positive, or anything else unlisted);
 *  - a place without a unique facility_id, a name, an address or a kind, or
 *    an enum outside the contract (kind, district, visit type, grade, flag,
 *    closure, severity, theme; "other" is a theme but never a flag);
 *  - a closure without `reopened_on`, or one that is not null or a date,
 *    that sits on a record that is not a closure or was not reopened, that
 *    comes before the closure, or that names no "Approved to Reopen" record;
 *  - a place file that is missing, that does not match its index entry, or
 *    that has no index entry;
 *  - record mode carrying bands fields; in bands mode, a band meta.card.bands
 *    does not define, worksheet rows whose points do not add up to `points`,
 *    scores_used rows outside { date, score, closure, county_score } (a
 *    closure is read as 70; county_score is null or 0 to 100) or that do not
 *    give the worksheet's deficits, a tie in points straddling a band edge, a
 *    place under review that still shows a band or points, an estimate whose
 *    `group` is not scores|closure or does not match whether scores_used holds
 *    a closure, and, where they are given, meta.frozen, meta.drift (either
 *    threshold shape; status, recent_quarters, latest_* and note),
 *    meta.card.band_1_by_route, meta.card.closure_score, meta.card.interim,
 *    meta.card.curve_closure and meta.card.outside.curve_closure, the outside
 *    bands' baseline_rate, baseline_interval and vs_baseline,
 *    meta.catch_run.eligible, or a district's precision_interval, labelled,
 *    interval_family, interval_family_deff (interval_family_zip, from before
 *    it) or evidence_above_even of the wrong shape (an export from before they
 *    existed passes without them);
 *  - a non-sample export without `expires` or `provenance`, or with a place
 *    named "Sample ...", or (bands mode, named_bands non-empty) a band
 *    outside named_bands;
 *  - a non-sample export that is not approved for publication: no
 *    meta.publication (written only by `export_site.py --publish`), a
 *    publication for another run, a facilities_sha256 that is not the sha256
 *    of the shipped facilities.geojson, no meta.contact, and in bands mode
 *    empty named_bands, a listed place outside them, or a listed place
 *    outside the City (no council district).
 *
 * `--review` checks an unpublished export (data/site): the publication and
 * named-band gates are reported as a warning, "review export: not
 * publishable", and every other check still runs. The site's `prebuild`
 * runs without it.
 *
 *   node scripts/check-export.mjs                          # public/data, what the site ships
 *   node scripts/check-export.mjs ../data/site --review    # an unpublished export
 */
import { createHash } from "node:crypto";
import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const args = process.argv.slice(2);
const review = args.includes("--review");
const dirArg = args.find((a) => !a.startsWith("--"));
const data = dirArg ? resolve(dirArg) : join(root, "public", "data");
const lib = (name) => import(pathToFileURL(join(root, "src", "lib", name)).href);
const { THEMES, TYPE_LABELS, MODES, PUBLIC_TYPES, VISIT_TYPES, SEVERITIES, CLOSURES, GRADES, FLAG_KEYS } = await lib("inspections.js");
const { sampleProblems } = await lib("sampleProof.js");
const FRESH_DAYS = 14;   // export_site.FRESH_DAYS: expires = inspections_through + 14 days

// What the public site ships (named City places only) stays under 3 MB, about 300 KB gzipped. An
// unpublished review or City-staff export lists every active place county-wide (about 11,000 places
// and 4.6 MB in September 2026, 560 KB gzipped by city_site/server.mjs); it may reach 8 MB, so a
// runaway export still fails. Either way the host must serve .geojson compressed.
const MAX_INDEX_BYTES = 3 * 1024 * 1024;
const MAX_REVIEW_INDEX_BYTES = 8 * 1024 * 1024;
const INDEX_KEYS = new Set(["facility_id", "name", "address", "facility_type", "council_district", "last_visit", "grade", "flags", "band", "points", "on_hold"]);
const DETAIL_KEYS = new Set(["business_type", "inspections", "violations", "score_card", "band_stability", "scores_used", "estimate"]);
const FORBIDDEN = ["rank", "percentile", "oof_rank", "score", "shap_features", "is_known_positive"];
const BAND_FIELDS = ["band", "points", "on_hold"];
const ISO = /^\d{4}-\d{2}-\d{2}$/;
const CLOSURE_SCORE = 70;   // a routine that ended in a health closure order is read as this score
const ESTIMATE_GROUPS = ["scores", "closure"];   // which curve a place's estimate was read from
const DRIFT_STATUS = ["ok", "refit", "not_yet_measurable"];

let failed = false;
const fail = (msg) => { console.error(`FAIL: ${msg}`); failed = true; };
const warn = (msg) => console.warn(`WARNING: ${msg}`);
const problems = new Map();
const note = (kind, example) => {
  const e = problems.get(kind) ?? { n: 0, example };
  e.n += 1;
  problems.set(kind, e);
};

const indexPath = join(data, "facilities.geojson");
const metaPath = join(data, "meta.json");
if (!existsSync(indexPath)) {
  console.error(`FAIL: ${indexPath} is missing`);
  process.exit(1);
}
if (!existsSync(metaPath)) {
  console.error(`FAIL: ${metaPath} is missing`);
  process.exit(1);
}
const indexBytes = readFileSync(indexPath);
let fc, meta;
try {
  fc = JSON.parse(indexBytes.toString("utf8"));
  meta = JSON.parse(readFileSync(metaPath, "utf8"));
} catch (err) {
  console.error(`FAIL: the export does not parse as JSON (${err.message})`);
  process.exit(1);
}
const features = Array.isArray(fc?.features) ? fc.features : [];
// The sample skips the publication gates below, so the claim has to be proven, not just stated.
const pretend = sampleProblems(meta, features);
for (const p of pretend) fail(`meta.sample is true, but this is not the invented sample: ${p}`);
const sample = meta?.sample === true && !pretend.length;
const mode = meta?.mode;
const bands = mode === "bands";

const maxIndex = review ? MAX_REVIEW_INDEX_BYTES : MAX_INDEX_BYTES;
if (indexBytes.length > maxIndex) fail(`the index is ${(indexBytes.length / 1e6).toFixed(2)} MB, over ${maxIndex / 1024 / 1024} MB${review ? " (the limit for an unpublished review or staff export)" : " (what the public site ships; the host must serve .geojson compressed)"}`);
if (!MODES.includes(mode)) fail(`meta.mode is ${JSON.stringify(mode)}, not one of ${MODES.join("|")}`);
if (meta?.places !== features.length) fail(`meta.places is ${meta?.places}, but the index lists ${features.length}`);

const cardItems = new Map((meta?.card?.items ?? []).map((it) => [it.item, it]));
const bandDefs = new Map((meta?.card?.bands ?? []).map((b) => [String(b.band), b]));
const named = (meta?.named_bands ?? []).map(String);
const kinds = sample ? Object.keys(TYPE_LABELS) : PUBLIC_TYPES;

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const isGrade = (g) => g && GRADES.includes(g.grade) && ISO.test(g.date ?? "") && (g.score === null || typeof g.score === "number");

function readPlace(id) {
  for (const name of [`${id}.json`, `${encodeURIComponent(id)}.json`]) {
    const path = join(data, "place", name);
    if (existsSync(path)) {
      try {
        const json = JSON.parse(readFileSync(path, "utf8"));
        return { json: json?.type === "Feature" && json.properties ? json.properties : json, name };
      } catch (err) {
        return { error: err.message, name };
      }
    }
  }
  return null;
}

const ids = new Set();
const fileNames = new Set();
const pointsBands = new Map();
const bandCount = {};
let held = 0;
let scoredOutside = 0;

for (const f of features) {
  const p = f?.properties ?? {};
  const id = p.facility_id;
  const label = id ?? "(no facility_id)";

  const [lon, lat] = f?.geometry?.coordinates ?? [];
  if (f?.type !== "Feature" || f?.geometry?.type !== "Point" || !Number.isFinite(lon) || !Number.isFinite(lat)) note("a feature that is not a Point with coordinates", label);

  for (const k of Object.keys(p)) {
    if (FORBIDDEN.includes(k)) note(`feature property not in the contract: ${k}`, label);
    else if (!INDEX_KEYS.has(k)) note(`feature property not in the contract: ${k}`, label);
  }
  if (typeof id !== "string" || !id) note("a place without a facility_id", JSON.stringify(p).slice(0, 80));
  else if (ids.has(id)) note("a facility_id listed twice", id);
  else ids.add(id);

  if (!p.name || !p.address) note("a place without a name or an address", label);
  if (!kinds.includes(p.facility_type)) note(`facility_type outside ${kinds.join("|")}`, `${label}: ${p.facility_type}`);
  if (p.council_district != null && (!Number.isInteger(p.council_district) || p.council_district < 1 || p.council_district > 9)) note("council_district outside 1 to 9 (null: outside the City)", `${label}: ${p.council_district}`);
  if (!ISO.test(p.last_visit?.date ?? "") || !VISIT_TYPES.includes(p.last_visit?.type)) note("last_visit without a date and a visit type from the contract", label);
  if (p.grade != null && (!isGrade(p.grade) || (p.grade.replaced != null && !isGrade(p.grade.replaced)))) note("grade outside { grade: A|B|C, score, date, replaced }", label);
  if (!Array.isArray(p.flags) || p.flags.some((k) => !FLAG_KEYS.includes(k))) note(`flags outside ${FLAG_KEYS.join("|")}`, `${label}: ${JSON.stringify(p.flags)}`);
  if (!sample && /^Sample /.test(p.name ?? "")) note("a real export contains a place named 'Sample …'", label);

  if (!bands) {
    for (const k of BAND_FIELDS) if (k in p) note(`bands field ${k} in a record-mode export`, label);
  } else {
    if (p.on_hold != null && typeof p.on_hold !== "boolean") note("on_hold that is not true or false", label);
    if (p.on_hold && (p.band != null || p.points != null)) note("a place under review that still shows a band or points", label);
    if (p.band != null) {
      const b = String(p.band);
      if (typeof p.band !== "string") note("a band that is not a string", `${label}: ${p.band}`);
      bandCount[b] = (bandCount[b] || 0) + 1;
      if (!bandDefs.has(b)) note("band not defined in meta.card.bands", `${label}: band ${b}`);
      if (typeof p.points !== "number") note("a banded place without points", label);
      else {
        const set = pointsBands.get(p.points) ?? new Set();
        set.add(b);
        pointsBands.set(p.points, set);
        // max_points is null for the top band: it has no upper limit.
        const d = bandDefs.get(b);
        if (d && ((typeof d.min_points === "number" && p.points < d.min_points) || (typeof d.max_points === "number" && p.points > d.max_points))) {
          note("points outside the band's min_points to max_points", `${label}: ${p.points} in band ${b}`);
        }
      }
      if (!sample && named.length && !named.includes(b)) note("band not in meta.named_bands", `${label}: band ${b}`);
    } else if (typeof p.points === "number") scoredOutside++;
    if (p.on_hold) held++;
  }

  if (typeof id !== "string" || !id) continue;
  const got = readPlace(id);
  if (!got) {
    note("place file missing (place/<facility_id>.json)", id);
    continue;
  }
  fileNames.add(got.name);
  if (got.error) {
    note("place file does not parse", `${id}: ${got.error}`);
    continue;
  }
  const d = got.json ?? {};
  for (const k of Object.keys(p)) if (!same(p[k], d[k])) note("place file does not match its index entry", `${id}: ${k}`);
  for (const k of INDEX_KEYS) if (!(k in p) && k in d) note("place file does not match its index entry", `${id}: ${k} only in the place file`);
  for (const k of Object.keys(d)) {
    if (FORBIDDEN.includes(k) || (!INDEX_KEYS.has(k) && !DETAIL_KEYS.has(k))) note(`place-file property not in the contract: ${k}`, id);
  }
  if (typeof d.business_type !== "string" || !d.business_type) note("a place file without business_type", id);
  if (!Array.isArray(d.inspections) || !d.inspections.length) note("a place file without inspections", id);
  for (const i of d.inspections ?? []) {
    if (!ISO.test(i.date ?? "")) note("an inspection without a date", id);
    if (typeof i.status !== "string" || !i.status) note("an inspection without the County's status text", `${id}: ${i.date}`);
    if (!VISIT_TYPES.includes(i.type)) note(`inspection type outside ${VISIT_TYPES.join("|")}`, `${id}: ${i.date} ${i.type}`);
    if (i.grade != null && !GRADES.includes(i.grade)) note("grade outside A|B|C|null", `${id}: ${i.date} ${i.grade}`);
    if (i.closure != null && !CLOSURES.includes(i.closure)) note(`closure outside ${CLOSURES.join("|")}|null`, `${id}: ${i.date} ${i.closure}`);
    if (Boolean(i.closed) !== (i.closure != null)) note("closed and closure disagree", `${id}: ${i.date}`);
    if (i.reopened != null && typeof i.reopened !== "boolean") note("reopened outside true|false|null", `${id}: ${i.date}`);
    // reopened_on: the date of the County's "Approved to Reopen" record that ended the closure, or null.
    if (i.closed && !("reopened_on" in i)) note("a closure without reopened_on (a date or null)", `${id}: ${i.date}`);
    const on = i.reopened_on;
    if (on != null) {
      if (typeof on !== "string" || !ISO.test(on)) note("reopened_on outside YYYY-MM-DD|null", `${id}: ${i.date} ${JSON.stringify(on)}`);
      else if (!i.closed) note("reopened_on on a record that is not a closure", `${id}: ${i.date}`);
      else if (i.reopened !== true) note("reopened_on on a closure whose reopened is not true", `${id}: ${i.date}`);
      else if (on < i.date) note("reopened_on before the closure", `${id}: ${i.date} reopened ${on}`);
      else if (!d.inspections.some((j) => j.date === on && /approved to reopen/i.test(j.status ?? ""))) {
        note('reopened_on that is not the date of an "Approved to Reopen" record', `${id}: ${i.date} reopened ${on}`);
      }
    }
  }
  const vs = d.violations ?? [];
  if (!Array.isArray(vs) || vs.length > 60) note("violations missing or more than 60", id);
  for (const v of Array.isArray(vs) ? vs : []) {
    if (!SEVERITIES.includes(v.severity)) note(`violation severity outside ${SEVERITIES.join("|")}`, `${id}: ${v.date} ${v.severity}`);
    if (!Object.hasOwn(THEMES, v.theme)) note(`violation theme outside ${Object.keys(THEMES).join("|")}`, `${id}: ${v.date} ${v.theme}`);
    if (!VISIT_TYPES.includes(v.visit)) note(`violation visit outside ${VISIT_TYPES.join("|")}`, `${id}: ${v.date} ${v.visit}`);
  }
  if (!bands) {
    for (const k of ["score_card", "band_stability", "scores_used", "estimate"]) if (k in d) note(`bands field ${k} in a record-mode place file`, id);
  } else if (typeof p.points === "number") {
    if (!Array.isArray(d.score_card) || !d.score_card.length) note("a place with points and no score_card", id);
    else {
      let sum = 0;
      for (const r of d.score_card) {
        if (!cardItems.has(r.item)) note("a score_card row for an item meta.card.items does not list", `${id}: ${r.item}`);
        if (typeof r.weight !== "number" || typeof r.value !== "number" || typeof r.points !== "number") note("a score_card row without weight, value and points", `${id}: ${r.item}`);
        else if (Math.abs(r.points - r.weight * r.value) > 1e-9) note("a score_card row whose points are not weight × value", `${id}: ${r.item}`);
        if (typeof r.points === "number" && Boolean(r.met) !== r.points > 0) note("a score_card row whose met disagrees with its points", `${id}: ${r.item}`);
        sum += Number(r.points) || 0;
      }
      if (Math.abs(sum - p.points) > 1e-9) note("points of met score_card rows do not add up to points", `${id}: ${sum} against ${p.points}`);
      // The worksheet can be checked by hand: the average deficit is 100 minus the rounded mean of the
      // routine scores listed (a closure order read as 70), and the last deficit is 100 minus the last.
      // county_score is the County's own score that day, or null when it gave none.
      const used = d.scores_used;
      const pct = (x) => typeof x === "number" && x >= 0 && x <= 100;
      if (!Array.isArray(used) || used.some((u) => !pct(u?.score) || !ISO.test(u?.date ?? "") || typeof u?.closure !== "boolean"
          || !("county_score" in (u ?? {})) || (u.county_score !== null && !pct(u.county_score)))) {
        note("a scored place without scores_used [{date, score, closure, county_score}] (scores 0 to 100; county_score may be null)", id);
      } else if (used.some((u) => u.closure && u.score !== CLOSURE_SCORE)) {
        note(`a scores_used closure not read as ${CLOSURE_SCORE}`, `${id}: ${JSON.stringify(used.find((u) => u.closure && u.score !== CLOSURE_SCORE))}`);
      } else if (used.length) {
        const row = (item) => d.score_card.find((r) => r.item === item);
        const avg = row("avg_deficit"), last = row("last_deficit");
        const mean = used.reduce((a, u) => a + u.score, 0) / used.length;
        if (avg && avg.value !== 100 - Math.round(mean)) note("avg_deficit does not match the scores_used it reads", `${id}: ${avg.value} against ${100 - Math.round(mean)}`);
        if (last && last.value !== 100 - used.at(-1).score) note("last_deficit does not match the last of scores_used", `${id}: ${last.value}`);
      }
    }
    const e = d.estimate;
    if (e != null && !(typeof e.rate === "number" && typeof e.low === "number" && typeof e.high === "number"
        && e.low >= 0 && e.high <= 1 && e.low <= e.rate + 1e-9 && e.rate <= e.high + 1e-9)) {
      note("an estimate outside 0 <= low <= rate <= high <= 1", `${id}: ${JSON.stringify(e)}`);
    }
    // group: the curve the estimate was read from, "closure" exactly when the scores the rule reads
    // include a routine inspection that ended in a health closure (optional: older exports lack it).
    if (e != null && typeof e === "object" && "group" in e) {
      if (!ESTIMATE_GROUPS.includes(e.group)) note(`an estimate group outside ${ESTIMATE_GROUPS.join("|")}`, `${id}: ${JSON.stringify(e.group)}`);
      else if (Array.isArray(d.scores_used) && (e.group === "closure") !== d.scores_used.some((u) => u?.closure === true)) {
        note("an estimate group that does not match whether scores_used holds a closure", `${id}: ${e.group}`);
      }
    }
  }
}

if (existsSync(join(data, "place"))) {
  for (const name of readdirSync(join(data, "place"))) {
    if (name.endsWith(".json") && !fileNames.has(name) && statSync(join(data, "place", name)).isFile()) note("a place file with no index entry", name);
  }
}
for (const [pts, set] of pointsBands) if (set.size > 1) note("a tie in points straddles a band edge", `${pts} points in bands ${[...set].sort().join(" and ")}`);

for (const [kind, { n, example }] of problems) fail(`${n} ${n === 1 ? "case" : "cases"}: ${kind} (e.g. ${example})`);

if (bands) {
  if (!bandDefs.size) fail("a bands-mode export whose meta.card.bands defines no band");
  for (const p of metaShapeProblems(meta)) fail(p);
  const defs = [...bandDefs.values()].sort((a, b) => Number(a.band) - Number(b.band));
  for (let i = 1; i < defs.length; i++) {
    const hi = defs[i - 1], lo = defs[i];
    if (typeof hi.min_points === "number" && typeof lo.max_points === "number" && lo.max_points >= hi.min_points) {
      fail(`band ${lo.band} reaches ${lo.max_points} points, not below band ${hi.band}'s ${hi.min_points}`);
    }
  }
}

/**
 * The shape of the bands-mode meta fields added in September 2026. Each is optional, so an export
 * from before them still passes; one that is present must have the contract's shape.
 */
function metaShapeProblems(m) {
  const out = [];
  const isObj = (x) => x != null && typeof x === "object" && !Array.isArray(x);
  const share = (x) => typeof x === "number" && x >= 0 && x <= 1;
  const shareOrNull = (x) => x === null || share(x);
  const count = (x) => Number.isInteger(x) && x >= 0;
  const interval = (iv) => Array.isArray(iv) && iv.length === 2
    && ((iv[0] === null && iv[1] === null) || (share(iv[0]) && share(iv[1]) && iv[0] <= iv[1]));
  // A ratio's interval (1 is even) and a difference's (it may be negative): null or [lo, hi], lo <= hi.
  const pairOf = (ok) => (iv) => iv === null || (Array.isArray(iv) && iv.length === 2 && iv.every(ok) && iv[0] <= iv[1]);
  const ratioInterval = pairOf((x) => typeof x === "number" && Number.isFinite(x) && x >= 0);
  const diffInterval = pairOf((x) => typeof x === "number" && Number.isFinite(x));
  const quarter = (q) => typeof q === "string" && /^\d{4}Q[1-4]$/.test(q);
  const curveShape = (c) => isObj(c) && Array.isArray(c.rate) && c.rate.length > 0 && Array.isArray(c.low) && Array.isArray(c.high)
    && c.low.length === c.rate.length && c.high.length === c.rate.length
    && c.rate.every((r, j) => share(r) && share(c.low[j]) && share(c.high[j]) && c.low[j] <= r + 1e-9 && r <= c.high[j] + 1e-9);

  if ("frozen" in m && m.frozen !== null) {
    const f = m.frozen;
    if (!isObj(f) || !/^\d{4}-\d{2}-\d{2}-[0-9a-f]{8}$/.test(f.version ?? "") || !ISO.test(f.frozen_on ?? "")
        || typeof f.from_run !== "string" || !f.from_run) {
      out.push(`meta.frozen is not null or { version: "YYYY-MM-DD-<8 hex>", frozen_on: YYYY-MM-DD, from_run } (${JSON.stringify(f)})`);
    }
  }
  if ("drift" in m && m.drift !== null) {
    const d = m.drift;
    const nums = ["major_rate_backtest", "major_rate_recent", "band_1_share_backtest", "band_1_share_now"];
    // Fixed thresholds until October 2026 ({ major_rate, band_share }); since then scaled to the counts.
    const t = isObj(d) ? d.thresholds : null;
    const thresholds = isObj(t) && ((typeof t.major_rate === "number" && typeof t.band_share === "number")
      || (typeof t.min === "number" && typeof t.standard_errors === "number"));
    if (!isObj(d) || nums.some((k) => !(k in d) || !shareOrNull(d[k])) || typeof d.refit_needed !== "boolean"
        || !Array.isArray(d.reasons) || d.reasons.some((r) => typeof r !== "string") || !thresholds) {
      out.push(`meta.drift is not { ${nums.join(", ")} (0 to 1 or null), refit_needed, reasons: string[], thresholds: { min, standard_errors } or { major_rate, band_share } }`);
    } else {
      // The quarter-by-quarter fields; an export from before them has none.
      if ("status" in d && (!DRIFT_STATUS.includes(d.status) || (d.status === "refit") !== d.refit_needed)) {
        out.push(`meta.drift.status is not ${DRIFT_STATUS.join("|")}, "refit" exactly when refit_needed (${JSON.stringify(d.status)})`);
      }
      if ("recent_quarters" in d && (!Array.isArray(d.recent_quarters) || !d.recent_quarters.every(quarter))) {
        out.push('meta.drift.recent_quarters is not a list of quarters ("YYYYQn")');
      }
      if ("latest_quarter" in d && d.latest_quarter !== null && !quarter(d.latest_quarter)) out.push('meta.drift.latest_quarter is not null or "YYYYQn"');
      if ("latest_rate" in d && !shareOrNull(d.latest_rate)) out.push("meta.drift.latest_rate is not null or 0 to 1");
      if ("latest_n" in d && d.latest_n !== null && !count(d.latest_n)) out.push("meta.drift.latest_n is not null or a count");
      if ("note" in d && d.note !== null && (typeof d.note !== "string" || !d.note.trim())) out.push("meta.drift.note is not null or a sentence");
    }
  }
  const card = m.card ?? {};
  if ("closure_score" in card && card.closure_score !== CLOSURE_SCORE) out.push(`meta.card.closure_score is ${JSON.stringify(card.closure_score)}, not ${CLOSURE_SCORE}`);
  if ("band_1_by_route" in card && card.band_1_by_route !== null) {
    const r = card.band_1_by_route;
    const route = (x) => isObj(x) && count(x.labelled) && count(x.positives) && x.positives <= x.labelled
      && shareOrNull(x.rate) && interval(x.interval);
    if (!isObj(r) || !route(r.closure) || !route(r.scores)) {
      out.push("meta.card.band_1_by_route is not null or { closure, scores }, each { labelled, positives, rate, interval: [lo, hi] }");
    }
  }
  // The estimate curve for places whose two scored years include a health closure, beside `curve`.
  for (const [where, c] of [["meta.card", card], ["meta.card.outside", card.outside]]) {
    if (isObj(c) && "curve_closure" in c && c.curve_closure !== null && !curveShape(c.curve_closure)) {
      out.push(`${where}.curve_closure is not null or a curve { rate, low, high } (lists of one length, 0 to 1, low <= rate <= high)`);
    }
  }
  // Rates with the label cut off after N days, for the monitor: { "90": { "1": {...}, "all": {...} }, ... }.
  if ("interim" in card && card.interim !== null) {
    const group = (g) => isObj(g) && count(g.labelled) && count(g.positives) && g.positives <= g.labelled && shareOrNull(g.rate);
    if (!isObj(card.interim) || !Object.entries(card.interim).every(([days, gs]) => /^\d+$/.test(days) && isObj(gs) && Object.values(gs).every(group))) {
      out.push("meta.card.interim is not null or { days: { group: { labelled, positives, rate } } }");
    }
  }
  for (const b of Array.isArray(card.outside?.bands) ? card.outside.bands : []) {
    if (!isObj(b)) continue;
    const bad = [];
    if ("baseline_rate" in b && !shareOrNull(b.baseline_rate)) bad.push("baseline_rate (0 to 1 or null)");
    if ("baseline_interval" in b && b.baseline_interval !== null && !interval(b.baseline_interval)) bad.push("baseline_interval (null or [lo, hi] within 0 to 1)");
    if ("vs_baseline" in b && !diffInterval(b.vs_baseline)) bad.push("vs_baseline (null or [lo, hi])");
    if (bad.length) out.push(`meta.card.outside.bands band ${b.band}: ${bad.join(", ")} of the wrong shape`);
  }
  if (isObj(m.catch_run) && "eligible" in m.catch_run && !count(m.catch_run.eligible)) out.push("meta.catch_run.eligible is not a count");
  for (const [dist, f] of Object.entries(m.fairness?.by_district ?? {})) {
    if (!isObj(f)) continue;
    const at = `meta.fairness.by_district[${dist}]`;
    if ("precision_interval" in f && f.precision_interval !== null && !interval(f.precision_interval)) {
      out.push(`${at}.precision_interval is not null or [lo, hi] within 0 to 1`);
    }
    if ("labelled" in f && !count(f.labelled)) out.push(`${at}.labelled is not a count`);
    // interval_family_zip came from a ZIP-code bootstrap that was dropped (too few ZIP codes per
    // district); an export may still carry it. interval_family_deff is the family-wise interval
    // widened by an assumed design effect, so its low end may fall below 0.
    for (const k of ["interval_family", "interval_family_zip"]) {
      if (k in f && !ratioInterval(f[k])) out.push(`${at}.${k} is not null or [lo, hi], 0 <= lo <= hi`);
    }
    if ("interval_family_deff" in f && !diffInterval(f.interval_family_deff)) out.push(`${at}.interval_family_deff is not null or [lo, hi], lo <= hi`);
    if ("evidence_above_even" in f) {
      // True only when every family-wise interval the export gives, and at least interval_family, starts above 1 (even).
      const lows = ["interval_family", "interval_family_deff"].map((k) => f[k]).filter(Array.isArray).map((iv) => iv[0]);
      if (typeof f.evidence_above_even !== "boolean") out.push(`${at}.evidence_above_even is not true or false`);
      else if (f.evidence_above_even && !(Array.isArray(f.interval_family) && lows.every((x) => typeof x === "number" && x > 1))) {
        out.push(`${at}.evidence_above_even is true, but interval_family, or interval_family_deff, does not start above 1`);
      }
    }
  }
  return out;
}

const addDays = (iso, n) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

if (!sample) {
  if (!ISO.test(meta?.expires ?? "")) fail("a real export without meta.expires (YYYY-MM-DD)");
  else if (ISO.test(meta?.inspections_through ?? "") && meta.expires > addDays(meta.inspections_through, FRESH_DAYS)) {
    fail(`meta.expires ${meta.expires} is more than ${FRESH_DAYS} days after inspections_through ${meta.inspections_through}`);
  }
  const prov = meta?.provenance;
  if (!prov || typeof prov !== "object" || !prov.code_sha || !prov.pull_sha256) fail("a real export without meta.provenance { code_sha, pull_sha256, python, packages }");
  const gates = [];
  const pub = meta?.publication;
  if (!pub || typeof pub !== "object") gates.push("no meta.publication (only export_site.py --publish writes it)");
  else {
    for (const k of ["run", "approval_sha256", "facilities_sha256", "gates_passed_at"]) if (!pub[k]) gates.push(`meta.publication without ${k}`);
    if (pub.run && pub.run !== meta.run) gates.push(`meta.publication is for run ${pub.run}, not ${meta.run}`);
    if (pub.approval_sha256 && !/^[0-9a-f]{64}$/.test(pub.approval_sha256)) gates.push("meta.publication.approval_sha256 is not a sha256");
    const passed = String(pub.gates_passed_at ?? "").slice(0, 10);
    if (pub.gates_passed_at && (!ISO.test(passed) || Number.isNaN(Date.parse(passed)))) gates.push("meta.publication.gates_passed_at is not a date");
    else if (pub.gates_passed_at && ISO.test(meta?.inspections_through ?? "") && ISO.test(meta?.expires ?? "")
             && (passed < meta.inspections_through || passed > meta.expires)) {
      gates.push(`meta.publication.gates_passed_at ${passed} is outside this export's window (${meta.inspections_through} to ${meta.expires})`);
    }
    const sha = createHash("sha256").update(indexBytes).digest("hex");
    if (pub.facilities_sha256 && pub.facilities_sha256 !== sha) gates.push("meta.publication.facilities_sha256 is not the sha256 of the shipped facilities.geojson");
  }
  if (typeof meta?.contact !== "string" || !meta.contact.trim()) gates.push("no meta.contact for owners");
  if (bands) {
    if (!named.length) gates.push("bands mode with empty meta.named_bands");
    else {
      const outside = features.filter((f) => !named.includes(String(f.properties?.band ?? ""))).length;
      if (outside) gates.push(`${outside} listed ${outside === 1 ? "place is" : "places are"} in no named band`);
    }
    // The rule's backtest and its district-parity gate cover City restaurants; a public list names no one else.
    const county = features.filter((f) => f.properties?.council_district == null).length;
    if (county) gates.push(`${county} listed ${county === 1 ? "place is" : "places are"} outside the City (no council district)`);
  }
  if (gates.length) {
    if (review) warn(`review export: not publishable (${gates.join("; ")})`);
    else for (const g of gates) fail(`not approved for publication: ${g}`);
  }
}

const shownBands = Object.keys(bandCount).length ? Object.entries(bandCount).sort().map(([b, n]) => `${b}:${n}`).join("  ") : "(none)";
console.log(`export: ${features.length} places; ${sample ? "SAMPLE DATA; " : ""}${mode ?? "?"} mode; run ${meta?.run ?? "?"}; inspections through ${meta?.inspections_through ?? "?"}; expires ${meta?.expires ?? "never"}; index ${(indexBytes.length / 1e6).toFixed(2)} MB`);
if (bands) console.log(`bands: ${shownBands}; scored outside the bands ${scoredOutside}; under review ${held}; named: ${named.join(", ") || "(none)"}`);
if (failed) process.exit(1);
console.log(`export check passed${review && !sample ? " (review)" : ""}`);
