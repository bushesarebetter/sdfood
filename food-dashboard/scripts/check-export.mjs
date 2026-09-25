#!/usr/bin/env node
/**
 * Check the export the site is about to ship against the contract
 * (docs/FOOD_DATA_CONTRACT.md, version 3.1): the index, every place file,
 * and meta.json.
 *
 * Fails on:
 *  - an index larger than 3 MB, a mode outside record|bands, or meta.places
 *    that does not count the index;
 *  - a feature property not in the contract (rank, percentile, oof_rank,
 *    score, shap_features, is_known_positive, or anything else unlisted);
 *  - a place without a unique facility_id, a name, an address or a kind, or
 *    an enum outside the contract (kind, district, visit type, grade, flag,
 *    closure, severity, theme);
 *  - a place file that is missing, that does not match its index entry, or
 *    that has no index entry;
 *  - record mode carrying bands fields; in bands mode, a band meta.card.bands
 *    does not define, worksheet rows whose points do not add up to `points`,
 *    a tie in points straddling a band edge, a place under review that still
 *    shows a band or points;
 *  - a non-sample export without `expires` or `provenance`, or with a place
 *    named "Sample ...", or (bands mode, named_bands non-empty) a band
 *    outside named_bands;
 *  - a non-sample export that is not approved for publication: no
 *    meta.publication (written only by `export_site.py --publish`), a
 *    publication for another run, a facilities_sha256 that is not the sha256
 *    of the shipped facilities.geojson, no meta.contact, and in bands mode
 *    empty named_bands or a listed place outside them.
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

// An index this size is about 300 KB gzipped; the host must serve .geojson compressed.
const MAX_INDEX_BYTES = 3 * 1024 * 1024;
const INDEX_KEYS = new Set(["facility_id", "name", "address", "facility_type", "council_district", "last_visit", "grade", "flags", "band", "points", "on_hold"]);
const DETAIL_KEYS = new Set(["business_type", "inspections", "violations", "score_card", "band_stability"]);
const FORBIDDEN = ["rank", "percentile", "oof_rank", "score", "shap_features", "is_known_positive"];
const BAND_FIELDS = ["band", "points", "on_hold"];
const ISO = /^\d{4}-\d{2}-\d{2}$/;

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
const sample = meta?.sample === true;
const mode = meta?.mode;
const bands = mode === "bands";

if (indexBytes.length > MAX_INDEX_BYTES) fail(`the index is ${(indexBytes.length / 1e6).toFixed(2)} MB, over 3 MB (about 300 KB gzipped at that size; the host must serve .geojson compressed)`);
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
  if (!Number.isInteger(p.council_district) || p.council_district < 1 || p.council_district > 9) note("council_district outside 1 to 9", `${label}: ${p.council_district}`);
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
  }
  const vs = d.violations ?? [];
  if (!Array.isArray(vs) || vs.length > 60) note("violations missing or more than 60", id);
  for (const v of Array.isArray(vs) ? vs : []) {
    if (!SEVERITIES.includes(v.severity)) note(`violation severity outside ${SEVERITIES.join("|")}`, `${id}: ${v.date} ${v.severity}`);
    if (!Object.hasOwn(THEMES, v.theme)) note(`violation theme outside ${Object.keys(THEMES).join("|")}`, `${id}: ${v.date} ${v.theme}`);
    if (!VISIT_TYPES.includes(v.visit)) note(`violation visit outside ${VISIT_TYPES.join("|")}`, `${id}: ${v.date} ${v.visit}`);
  }
  if (!bands) {
    for (const k of ["score_card", "band_stability"]) if (k in d) note(`bands field ${k} in a record-mode place file`, id);
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
  const defs = [...bandDefs.values()].sort((a, b) => Number(a.band) - Number(b.band));
  for (let i = 1; i < defs.length; i++) {
    const hi = defs[i - 1], lo = defs[i];
    if (typeof hi.min_points === "number" && typeof lo.max_points === "number" && lo.max_points >= hi.min_points) {
      fail(`band ${lo.band} reaches ${lo.max_points} points, not below band ${hi.band}'s ${hi.min_points}`);
    }
  }
}

if (!sample) {
  if (!ISO.test(meta?.expires ?? "")) fail("a real export without meta.expires (YYYY-MM-DD)");
  const prov = meta?.provenance;
  if (!prov || typeof prov !== "object" || !prov.code_sha || !prov.pull_sha256) fail("a real export without meta.provenance { code_sha, pull_sha256, python, packages }");
  const gates = [];
  const pub = meta?.publication;
  if (!pub || typeof pub !== "object") gates.push("no meta.publication (only export_site.py --publish writes it)");
  else {
    for (const k of ["run", "approval_sha256", "facilities_sha256", "gates_passed_at"]) if (!pub[k]) gates.push(`meta.publication without ${k}`);
    if (pub.run && pub.run !== meta.run) gates.push(`meta.publication is for run ${pub.run}, not ${meta.run}`);
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
