import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { MAX_ITEMS } from "../src/lib/inspections.js";

const script = join(dirname(fileURLToPath(import.meta.url)), "..", "scripts", "check-export.mjs");

const record = (date, extra = {}) => ({ date, status: "Complete", type: "routine", score: 95, grade: "A", major: 0, minor: 1, grp: 1, closed: false, closure: null, reopened: null, ...extra });

/** One listed place: its index entry and its place file. */
function place(n, { band, points, index = {}, detail = {} } = {}) {
  const props = {
    facility_id: `DEH2020-FFPP-${String(n).padStart(6, "0")}`, name: `Test Place ${n}`, address: "1 Main St, San Diego, CA 92101",
    facility_type: "restaurant", council_district: 3, last_visit: { date: "2026-05-01", type: "routine" },
    grade: { grade: "A", score: 95, date: "2026-05-01", replaced: null }, flags: [],
    ...(band != null ? { band } : {}), ...(points != null ? { points } : {}), ...index,
  };
  const card = points != null ? { score_card: [{ item: "avg_deficit", weight: 1, value: points - 2, points: points - 2, met: points - 2 > 0 }, { item: "theme_temperature", weight: 2, value: 1, points: 2, met: true }], band_stability: 0.9,
    scores_used: [{ date: "2026-01-02", score: 100 - (points - 2), closure: false, county_score: 100 - (points - 2) }] } : {};
  return {
    feature: { type: "Feature", geometry: { type: "Point", coordinates: [-117.16, 32.72] }, properties: props },
    file: { ...props, business_type: "Restaurant Food Facility", inspections: [record("2026-05-01")], violations: [{ date: "2026-05-01", visit: "routine", code: "7", theme: "temperature", severity: "minor", description: "x" }], ...card, ...detail },
  };
}

const card = {
  items: [{ item: "avg_deficit", label: "Points below 100", weight: 1, unit: "per point", feature: "avg_deficit" }, { item: "theme_temperature", label: "Temperature citations", weight: 2, unit: "per citation", feature: "theme_temperature" }],
  rule: "A rule.",
  bands: [{ band: "1", min_points: 20, max_points: null, share: 0.025 }, { band: "2", min_points: 10, max_points: 19, share: 0.075 }],
  rest: { rate: 0.16 },
};

const reviewMeta = (places) => ({
  mode: "bands", sample: false, run: "forward_test", generated: "2026-09-20", places, expires: "2026-10-03", inspections_through: "2026-09-19",
  provenance: { code_sha: "abc", pull_sha256: "def", python: "3.14", packages: {} }, contact: null, operator: null, corrections: [], publication: null,
  named_bands: [], card, catch_run: {},
});

/** Write an export and run the check on it. `publish` fills in meta.publication with the real sha256. */
function check(places, meta, { args = [], publish = false, extraFiles = {}, drop = [], rawIndex = null } = {}) {
  const dir = mkdtempSync(join(tmpdir(), "food-check-"));
  try {
    mkdirSync(join(dir, "place"));
    const index = rawIndex ?? JSON.stringify({ type: "FeatureCollection", features: places.map((p) => p.feature) });
    writeFileSync(join(dir, "facilities.geojson"), index);
    for (const p of places) if (!drop.includes(p.feature.properties.facility_id)) writeFileSync(join(dir, "place", `${p.feature.properties.facility_id}.json`), JSON.stringify(p.file));
    for (const [name, body] of Object.entries(extraFiles)) writeFileSync(join(dir, "place", name), JSON.stringify(body));
    const m = { ...meta };
    if (publish) {
      m.publication = { run: m.run, approval_sha256: "a".repeat(64), facilities_sha256: createHash("sha256").update(index).digest("hex"), gates_passed_at: "2026-09-20T12:00:00Z", ...(publish === true ? {} : publish) };
      m.contact = m.contact ?? "owners@example.org";
      m.named_bands = m.named_bands?.length ? m.named_bands : ["1", "2"];
    }
    writeFileSync(join(dir, "meta.json"), JSON.stringify(m));
    const r = spawnSync(process.execPath, [script, dir, ...args], { encoding: "utf8" });
    return { ok: r.status === 0, err: r.stderr, out: r.stdout };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const banded = () => [place(1, { band: "1", points: 21 }), place(2, { band: "2", points: 12 })];

test("a published bands export passes; the same export for review passes with --review and a warning", () => {
  const places = banded();
  const r = check(places, reviewMeta(2), { publish: true });
  assert.ok(r.ok, r.err);
  const rev = check([...places, place(3, { points: 4 })], reviewMeta(3), { args: ["--review"] });
  assert.ok(rev.ok, rev.err);
  assert.match(rev.err, /review export: not publishable/);
});

test("a published bands export names City places only; a review export may list the county", () => {
  const county = place(3, { band: "2", points: 12, index: { council_district: null } });
  const places = [...banded(), county];
  const pub = check(places, reviewMeta(3), { publish: true });
  assert.equal(pub.ok, false);
  assert.match(pub.err, /not approved for publication: 1 listed place is outside the City \(no council district\)/);
  const rev = check(places, reviewMeta(3), { args: ["--review"] });
  assert.ok(rev.ok, rev.err);
  assert.match(rev.err, /outside the City/);
});

test("without --review, an unapproved real export is refused", () => {
  const r = check(banded(), reviewMeta(2));
  assert.equal(r.ok, false);
  assert.match(r.err, /not approved for publication: no meta\.publication/);
  assert.match(r.err, /no meta\.contact/);
  assert.match(r.err, /empty meta\.named_bands/);
});

test("a publication for another run, or for other bytes, is refused", () => {
  assert.match(check(banded(), reviewMeta(2), { publish: { run: "forward_other" } }).err, /publication is for run forward_other/);
  assert.match(check(banded(), reviewMeta(2), { publish: { facilities_sha256: "0".repeat(64) } }).err, /facilities_sha256 is not the sha256 of the shipped facilities\.geojson/);
  assert.match(check(banded(), reviewMeta(2), { publish: { gates_passed_at: null } }).err, /publication without gates_passed_at/);
});

test("a published bands export lists only places in named bands", () => {
  const r = check([...banded(), place(3, { points: 4 })], reviewMeta(3), { publish: true });
  assert.equal(r.ok, false);
  assert.match(r.err, /1 listed place is in no named band/);
  const outside = check(banded(), { ...reviewMeta(2), named_bands: ["1"] }, { publish: true });
  assert.match(outside.err, /band not in meta\.named_bands/);
});

test("contract properties: no position, no score, nothing unlisted", () => {
  for (const k of ["rank", "percentile", "oof_rank", "score", "shap_features", "is_known_positive"]) {
    const bad = place(2, { band: "2", points: 12, index: { [k]: 1 } });
    assert.match(check([place(1, { band: "1", points: 21 }), bad], reviewMeta(2), { args: ["--review"] }).err, new RegExp(`feature property not in the contract: ${k}`), k);
  }
});

test("place files: missing, mismatched, or orphaned", () => {
  const places = banded();
  assert.match(check(places, reviewMeta(2), { args: ["--review"], drop: [places[1].feature.properties.facility_id] }).err, /place file missing/);
  const off = banded();
  off[1].file.name = "Another Name";
  assert.match(check(off, reviewMeta(2), { args: ["--review"] }).err, /place file does not match its index entry/);
  assert.match(check(banded(), reviewMeta(2), { args: ["--review"], extraFiles: { "DEH2020-FFPP-999999.json": { facility_id: "DEH2020-FFPP-999999" } } }).err, /a place file with no index entry/);
});

test("worksheets must add up, bands must be defined, and a tie must not straddle a band edge", () => {
  const badSum = banded();
  badSum[0].file.score_card[0].points = 3;
  assert.match(check(badSum, reviewMeta(2), { args: ["--review"] }).err, /points are not weight × value|do not add up to points/);
  assert.match(check([place(1, { band: "1", points: 21 }), place(2, { band: "4", points: 12 })], reviewMeta(2), { args: ["--review"] }).err, /band not defined in meta\.card\.bands/);
  const tie = check([place(1, { band: "1", points: 21 }), place(2, { band: "2", points: 21 })], reviewMeta(2), { args: ["--review"] });
  assert.match(tie.err, /a tie in points straddles a band edge/);
  assert.match(check([place(1, { band: "2", points: 25 }), place(2, { band: "2", points: 12 })], reviewMeta(2), { args: ["--review"] }).err, /points outside the band's min_points to max_points/);
  assert.ok(check([place(1, { band: "1", points: 99 }), place(2, { band: "2", points: 12 })], reviewMeta(2), { args: ["--review"] }).ok, "the top band has no upper limit");
  const held = place(3, { band: "2", points: 12, index: { on_hold: true } });
  assert.match(check([...banded(), held], reviewMeta(3), { args: ["--review"] }).err, /a place under review that still shows a band or points/);
});

test("enums outside the contract fail", () => {
  const cases = [
    [{ index: { facility_type: "casino" } }, /facility_type outside/],
    [{ index: { council_district: 12 } }, /council_district outside 1 to 9/],
    [{ index: { flags: ["dirty"] } }, /flags outside/],
    [{ index: { last_visit: { date: "2026-05-01", type: "verification" } } }, /last_visit without a date and a visit type/],
    [{ detail: { inspections: [record("2026-05-01", { type: "verification" })] } }, /inspection type outside/],
    [{ detail: { inspections: [record("2026-05-01", { status: "" })] } }, /without the County's status text/],
    [{ detail: { inspections: [record("2026-05-01", { closed: true, closure: "fire" })] } }, /closure outside/],
    [{ detail: { violations: [{ date: "2026-05-01", visit: "routine", code: "7", theme: "source", severity: "minor" }] } }, /violation theme outside/],
    [{ detail: { violations: [{ date: "2026-05-01", visit: "routine", code: "6", theme: "handwashing", severity: "minor" }] } }, /violation theme outside/],
    [{ index: { flags: ["major", "other"] } }, /flags outside/],
    [{ index: { flags: ["handwashing"] } }, /flags outside/],
    [{ detail: { violations: [{ date: "2026-05-01", visit: "routine", code: "7", theme: "supplier", severity: "critical" }] } }, /violation severity outside/],
  ];
  for (const [extra, re] of cases) {
    const r = check([place(1, { band: "1", points: 21, ...extra })], reviewMeta(1), { args: ["--review"] });
    assert.equal(r.ok, false, String(re));
    assert.match(r.err, re);
  }
});

test("real exports must expire, carry provenance, and never hold a Sample place; the index stays under 3 MB (8 MB for review)", () => {
  assert.match(check(banded(), { ...reviewMeta(2), expires: null }, { args: ["--review"] }).err, /without meta\.expires/);
  assert.match(check(banded(), { ...reviewMeta(2), provenance: null }, { args: ["--review"] }).err, /without meta\.provenance/);
  const sample = [place(1, { band: "1", points: 21, index: { name: "Sample Grill 1" } })];
  sample[0].file.name = "Sample Grill 1";
  assert.match(check(sample, reviewMeta(1), { args: ["--review"] }).err, /a place named 'Sample …'/);
  const big = JSON.stringify({ type: "FeatureCollection", features: banded().map((p) => p.feature), pad: "x".repeat(3.2 * 1024 * 1024) });
  assert.match(check(banded(), reviewMeta(2), { rawIndex: big }).err, /over 3 MB \(what the public site ships/);
  // an unpublished county-wide export for review or the City staff site is larger, and still bounded
  const rev = check(banded(), reviewMeta(2), { args: ["--review"], rawIndex: big });
  assert.ok(rev.ok, rev.err);
  const huge = JSON.stringify({ type: "FeatureCollection", features: banded().map((p) => p.feature), pad: "x".repeat(8.2 * 1024 * 1024) });
  assert.match(check(banded(), reviewMeta(2), { args: ["--review"], rawIndex: huge }).err, /over 8 MB \(the limit for an unpublished review or staff export\)/);
  assert.match(check(banded(), { ...reviewMeta(2), places: 5 }, { args: ["--review"] }).err, /meta\.places is 5/);
});

test("record mode carries no bands field; the sample fixture and a published record export pass", () => {
  const recMeta = { ...reviewMeta(1), mode: "record", named_bands: undefined, card: undefined };
  const r = check([place(1)], recMeta, { publish: { run: "forward_test" } });
  assert.ok(r.ok, r.err);
  assert.match(check([place(1, { band: "1", points: 21 })], recMeta, { args: ["--review"] }).err, /bands field band in a record-mode export/);
  assert.match(check([place(1)], { ...recMeta, mode: "ranked" }, { args: ["--review"] }).err, /meta\.mode is "ranked"/);
  const fixture = spawnSync(process.execPath, [script, join(dirname(fileURLToPath(import.meta.url)), "fixtures", "record")], { encoding: "utf8" });
  assert.equal(fixture.status, 0, fixture.stderr);
});

test("a real export cannot pass as the sample by setting meta.sample", () => {
  const real = [place(1, { band: "1", points: 21 }), place(2, { band: "2", points: 12 })];
  const r = check(real, { ...reviewMeta(2), sample: true, run: "sample", provenance: { code_sha: "sample" }, source: { url: null } });
  assert.ok(!r.ok);
  assert.match(r.err, /meta\.sample is true, but this is not the invented sample: place "DEH2020-FFPP-000001" does not have a sample id/);
  assert.match(r.err, /not approved for publication/, "and it is then held to the real gates");
});

test("a hand-written publication stamp must be well formed and inside the export's window", () => {
  const places = [place(1, { band: "1", points: 21 })];
  const forged = check(places, { ...reviewMeta(1), expires: "2099-01-01" }, { publish: { approval_sha256: "x", gates_passed_at: "x" } });
  assert.ok(!forged.ok);
  assert.match(forged.err, /more than 14 days after inspections_through/);
  assert.match(forged.err, /approval_sha256 is not a sha256/);
  assert.match(forged.err, /gates_passed_at is not a date/);
  const late = check(places, reviewMeta(1), { publish: { gates_passed_at: "2027-01-01" } });
  assert.match(late.err, /outside this export's window/);
  assert.ok(check(places, reviewMeta(1), { publish: true }).ok, "a well-formed stamp inside the window passes");
});

test("the new flags and the report-section themes pass", () => {
  const p = place(1, { band: "1", points: 21, index: { flags: ["major", "closures2", "repeat_item", "lt90_2", "hands", "grp_staff", "grp_other"] } });
  p.file.violations = [
    { date: "2026-05-01", visit: "routine", code: "1b", theme: "knowledge", severity: "minor", description: "x" },
    { date: "2026-05-01", visit: "routine", code: "39", theme: "grp_equipment", severity: "grp", description: "x" },
    { date: "2026-05-01", visit: "routine", code: "99", theme: "other", severity: "grp", description: "x" },
  ];
  const r = check([p], reviewMeta(1), { args: ["--review"] });
  assert.ok(r.ok, r.err);
});

/** A place whose record holds a closure on 2026-03-02 and, when `back`, the County's reopening on 2026-03-05. */
function closedPlace(closure, { back = true } = {}) {
  const closed = record("2026-03-02", { status: "Ordered Closed", score: null, grade: null, major: 1, closed: true, closure: "health", reopened: true, reopened_on: "2026-03-05", ...closure });
  if (closed.reopened_on === undefined) delete closed.reopened_on;
  const inspections = [closed, ...(back ? [record("2026-03-05", { status: "Approved to Reopen", type: "followup" })] : []), record("2026-05-01")];
  return place(1, { band: "1", points: 21, detail: { inspections } });
}

test("a closure carries reopened_on: the date of the County's Approved to Reopen record, or null", () => {
  const ok = check([closedPlace({})], reviewMeta(1), { args: ["--review"] });
  assert.ok(ok.ok, ok.err);
  const notReopened = check([closedPlace({ reopened: false, reopened_on: null }, { back: false })], reviewMeta(1), { args: ["--review"] });
  assert.ok(notReopened.ok, notReopened.err);
  const nullOnOthers = place(1, { band: "1", points: 21, detail: { inspections: [record("2026-05-01", { reopened_on: null })] } });
  assert.ok(check([nullOnOthers], reviewMeta(1), { args: ["--review"] }).ok, "a null reopened_on on any record is allowed");
  const cases = [
    [closedPlace({ reopened_on: undefined }), /a closure without reopened_on/],
    [closedPlace({ reopened_on: "June 8, 2025" }), /reopened_on outside YYYY-MM-DD\|null/],
    [closedPlace({ reopened: false }), /reopened_on on a closure whose reopened is not true/],
    [closedPlace({ reopened_on: "2026-02-20" }), /reopened_on before the closure/],
    [closedPlace({}, { back: false }), /reopened_on that is not the date of an "Approved to Reopen" record/],
    [place(1, { band: "1", points: 21, detail: { inspections: [record("2026-05-01", { reopened_on: "2026-05-03" })] } }), /reopened_on on a record that is not a closure/],
  ];
  for (const [p, re] of cases) {
    const r = check([p], reviewMeta(1), { args: ["--review"] });
    assert.equal(r.ok, false, String(re));
    assert.match(r.err, re);
  }
});

test("scores_used rows are { date, score, closure, county_score }, and a closure is read as 70", () => {
  // avg_deficit 19 = 100 - round(mean(92, 70)); a closure the County scored 78 is read as 70.
  const withClosure = (row) => place(1, { band: "1", points: 21, detail: { scores_used: [{ date: "2025-11-02", score: 92, closure: false, county_score: 92 }, row] } });
  const ok = check([withClosure({ date: "2026-03-02", score: 70, closure: true, county_score: 78 })], reviewMeta(1), { args: ["--review"] });
  assert.ok(ok.ok, ok.err);
  const unscored = check([withClosure({ date: "2026-03-02", score: 70, closure: true, county_score: null })], reviewMeta(1), { args: ["--review"] });
  assert.ok(unscored.ok, unscored.err);
  const cases = [
    [withClosure({ date: "2026-03-02", score: 78, closure: true, county_score: 78 }), /a scores_used closure not read as 70/],
    [withClosure({ date: "2026-03-02", score: 70, closure: true }), /without scores_used \[\{date, score, closure, county_score\}\]/],
    [withClosure({ date: "2026-03-02", score: 70, closure: true, county_score: 120 }), /without scores_used/],
    [withClosure({ date: "2026-03-02", score: 70, closure: "yes", county_score: null }), /without scores_used/],
    [withClosure({ date: "2026-03-02", score: 60, closure: false, county_score: 60 }), /avg_deficit does not match the scores_used it reads/],
  ];
  for (const [p, re] of cases) {
    const r = check([p], reviewMeta(1), { args: ["--review"] });
    assert.equal(r.ok, false, String(re));
    assert.match(r.err, re);
  }
});

const newMeta = {
  frozen: { version: "2026-09-29-1a2b3c4d", frozen_on: "2026-09-29", from_run: "forward_2026-09-29-0a1b2c3d" },
  drift: {
    major_rate_backtest: 0.21, major_rate_recent: 0.24, band_1_share_backtest: 0.025, band_1_share_now: null,
    refit_needed: false, reasons: [], thresholds: { major_rate: 0.05, band_share: 0.05 },
  },
  card: {
    ...card, closure_score: 70,
    band_1_by_route: {
      closure: { labelled: 40, positives: 18, rate: 0.45, interval: [0.31, 0.6] },
      scores: { labelled: 0, positives: 0, rate: null, interval: [null, null] },
    },
  },
  fairness: { by_district: { 3: { named: 4, precision: 0.5, precision_interval: [0.15, 0.85] }, 4: { named: 0, precision: null, precision_interval: null } } },
};

test("the frozen rule, drift, band 1 by route and district precision intervals pass when well formed, and are optional", () => {
  const r = check(banded(), { ...reviewMeta(2), ...newMeta }, { args: ["--review"] });
  assert.ok(r.ok, r.err);
  const nulls = check(banded(), { ...reviewMeta(2), frozen: null, drift: null, card: { ...card, band_1_by_route: null } }, { args: ["--review"] });
  assert.ok(nulls.ok, nulls.err);
  assert.ok(check(banded(), reviewMeta(2), { args: ["--review"] }).ok, "an export from before these fields passes");
});

test("malformed meta.frozen, meta.drift, band_1_by_route, closure_score or precision_interval fail", () => {
  const route = newMeta.card.band_1_by_route;
  const cases = [
    [{ frozen: { ...newMeta.frozen, version: "v1" } }, /meta\.frozen is not null or/],
    [{ frozen: { ...newMeta.frozen, frozen_on: "Sept 29" } }, /meta\.frozen is not null or/],
    [{ frozen: { version: newMeta.frozen.version, frozen_on: "2026-09-29" } }, /meta\.frozen is not null or/],
    [{ drift: { ...newMeta.drift, refit_needed: "no" } }, /meta\.drift is not/],
    [{ drift: { ...newMeta.drift, major_rate_recent: "24%" } }, /meta\.drift is not/],
    [{ drift: { ...newMeta.drift, reasons: "none" } }, /meta\.drift is not/],
    [{ drift: { ...newMeta.drift, thresholds: { major_rate: 0.05 } } }, /meta\.drift is not/],
    [{ card: { ...newMeta.card, closure_score: 75 } }, /meta\.card\.closure_score is 75, not 70/],
    [{ card: { ...newMeta.card, band_1_by_route: { closure: route.closure } } }, /meta\.card\.band_1_by_route is not null or/],
    [{ card: { ...newMeta.card, band_1_by_route: { ...route, scores: { ...route.scores, positives: 3 } } } }, /band_1_by_route is not/],
    [{ card: { ...newMeta.card, band_1_by_route: { ...route, closure: { ...route.closure, interval: [0.6, 0.31] } } } }, /band_1_by_route is not/],
    [{ fairness: { by_district: { 3: { precision_interval: [0.2, 1.4] } } } }, /by_district\[3\]\.precision_interval is not null or \[lo, hi\]/],
    [{ fairness: { by_district: { 3: { precision_interval: 0.5 } } } }, /by_district\[3\]\.precision_interval/],
  ];
  for (const [patch, re] of cases) {
    const r = check(banded(), { ...reviewMeta(2), ...newMeta, ...patch }, { args: ["--review"] });
    assert.equal(r.ok, false, String(re));
    assert.match(r.err, re);
  }
});

// The shapes export_site.py writes since the two estimate curves and the quarter-by-quarter drift check.
const curve = { rate: [0.1, 0.2, 0.3], low: [0.05, 0.15, 0.2], high: [0.15, 0.25, 0.4], bins: [], labelled: 300, positives: 60 };
const latestMeta = {
  ...newMeta,
  drift: {
    status: "not_yet_measurable", major_rate_backtest: 0.175, major_rate_recent: null, recent_quarters: [],
    band_1_share_backtest: 0.025, band_1_share_now: 0.026, latest_quarter: "2026Q3", latest_rate: 0.205, latest_n: 1800,
    refit_needed: false, reasons: [], thresholds: { min: 0.02, standard_errors: 3.0 },
    note: "In the latest quarter (2026 Q3, through September 19) 20.5% of routine inspections found a major violation, against 17.5% over the backtest's label year before that quarter (September 2025 to June 2026), so the rates here may be low.",
  },
  card: {
    ...newMeta.card, curve, curve_closure: curve,
    interim: { 90: { 1: { labelled: 20, positives: 8, rate: 0.4 }, all: { labelled: 900, positives: 180, rate: 0.2 } },
               180: { 1: { labelled: 0, positives: 0, rate: null }, all: { labelled: 1500, positives: 290, rate: 0.1933 } } },
    outside: { bands_shown: true, curve, curve_closure: null,
               bands: [{ band: "1", rate: 0.3, interval: [0.25, 0.35], baseline_rate: 0.29, baseline_interval: [0.24, 0.34], vs_baseline: [-4.5, 6] }] },
  },
  catch_run: { as_of: "2025-09-01", candidates: 3739, eligible: 3100 },
  fairness: { by_district: {
    // a family-wise interval widened for an assumed design effect can start below 0
    3: { named: 4, labelled: 300, precision: 0.5, precision_interval: [0.15, 0.85], interval_family: [0.1, 2.1], interval_family_deff: [-0.3, 2.6], evidence_above_even: false },
    4: { named: 12, labelled: 200, precision: 0.2, precision_interval: [0.05, 0.5], interval_family: [1.3, 2.8], interval_family_deff: [1.05, 3.1], evidence_above_even: true },
    5: { named: 0, precision: null, precision_interval: null, interval_family: null, interval_family_deff: null, evidence_above_even: false },
    // an export from while the ZIP-code bootstrap was tried
    6: { named: 5, labelled: 90, interval_family: [0.4, 1.9], interval_family_zip: [0, 3.7], evidence_above_even: false },
  } },
};
const withEstimate = (group, closure = false) => {
  const places = banded();
  const p = places[0].file;
  p.estimate = { rate: 0.3, low: 0.2, high: 0.4, ...(group === undefined ? {} : { group }) };
  // place 1 has 21 points, 19 of them from avg_deficit: a 92 and a closure read as 70 average 81
  if (closure) p.scores_used = [{ date: "2025-11-02", score: 92, closure: false, county_score: 92 }, { date: "2026-01-02", score: 70, closure: true, county_score: null }];
  return places;
};

test("the two estimate curves, interim rates, outside baselines, drift by quarter and the district evidence pass when well formed", () => {
  const r = check(withEstimate("scores"), { ...reviewMeta(2), ...latestMeta }, { args: ["--review"] });
  assert.ok(r.ok, r.err);
  const refit = { ...latestMeta.drift, status: "refit", refit_needed: true, reasons: ["routine major rate 26.5% in 2026Q1, 2026Q2 against 20.0% over the backtest's label year (September 2025 to August 2026)"],
                  recent_quarters: ["2026Q1", "2026Q2"], major_rate_recent: 0.265, note: null };
  assert.ok(check(banded(), { ...reviewMeta(2), ...latestMeta, drift: refit }, { args: ["--review"] }).ok, "a refit");
  assert.ok(check(withEstimate(undefined), { ...reviewMeta(2), ...latestMeta }, { args: ["--review"] }).ok, "an estimate without a group (older export)");
  assert.ok(check(banded(), { ...reviewMeta(2), ...latestMeta, card: { ...latestMeta.card, curve_closure: null, interim: null } }, { args: ["--review"] }).ok, "null curve_closure and interim");
  assert.ok(check(banded(), { ...reviewMeta(2), ...newMeta }, { args: ["--review"] }).ok, "the older drift thresholds { major_rate, band_share } still pass");
});

test("an estimate's group must be scores or closure, and closure exactly when scores_used holds a closure", () => {
  const meta = { ...reviewMeta(2), ...latestMeta };
  assert.ok(check(withEstimate("closure", true), meta, { args: ["--review"] }).ok, "a closure read as 70, and the closure curve");
  const cases = [
    [withEstimate("other"), /an estimate group outside scores\|closure/],
    [withEstimate("closure"), /an estimate group that does not match whether scores_used holds a closure/],
    [withEstimate("scores", true), /an estimate group that does not match whether scores_used holds a closure/],
  ];
  for (const [places, re] of cases) {
    const r = check(places, meta, { args: ["--review"] });
    assert.equal(r.ok, false, String(re));
    assert.match(r.err, re);
  }
});

test("malformed drift fields, curve_closure, interim, outside baselines, eligible or district evidence fail", () => {
  const d = latestMeta.drift;
  const c = latestMeta.card;
  const dist = latestMeta.fairness.by_district;
  const cases = [
    [{ drift: { ...d, thresholds: { min: 0.02 } } }, /meta\.drift is not/],
    [{ drift: { ...d, status: "fine" } }, /meta\.drift\.status is not ok\|refit\|not_yet_measurable/],
    [{ drift: { ...d, status: "refit" } }, /meta\.drift\.status is not/, "refit without refit_needed"],
    [{ drift: { ...d, status: "ok", refit_needed: true, reasons: ["x"] } }, /meta\.drift\.status is not/],
    [{ drift: { ...d, recent_quarters: ["Q3 2026"] } }, /meta\.drift\.recent_quarters/],
    [{ drift: { ...d, latest_quarter: "2026-07" } }, /meta\.drift\.latest_quarter/],
    [{ drift: { ...d, latest_rate: 20.5 } }, /meta\.drift\.latest_rate/],
    [{ drift: { ...d, latest_n: -3 } }, /meta\.drift\.latest_n/],
    [{ drift: { ...d, note: "" } }, /meta\.drift\.note/],
    [{ card: { ...c, curve_closure: { ...curve, low: [0.15, 0.15, 0.2] } } }, /meta\.card\.curve_closure is not null or a curve/, "low above rate"],
    [{ card: { ...c, curve_closure: { ...curve, high: [0.2] } } }, /meta\.card\.curve_closure is not/, "lists of different lengths"],
    [{ card: { ...c, curve_closure: { rate: [] } } }, /meta\.card\.curve_closure is not/],
    [{ card: { ...c, outside: { ...c.outside, curve_closure: { rate: [1.2], low: [1], high: [1.3] } } } }, /meta\.card\.outside\.curve_closure is not/],
    [{ card: { ...c, interim: { 90: { 1: { labelled: 2, positives: 3, rate: 1 } } } } }, /meta\.card\.interim is not/],
    [{ card: { ...c, interim: { ninety: {} } } }, /meta\.card\.interim is not/],
    [{ card: { ...c, interim: [0.2] } }, /meta\.card\.interim is not/],
    [{ card: { ...c, outside: { ...c.outside, bands: [{ ...c.outside.bands[0], vs_baseline: [6, -4.5] }] } } }, /meta\.card\.outside\.bands band 1: vs_baseline/],
    [{ card: { ...c, outside: { ...c.outside, bands: [{ ...c.outside.bands[0], baseline_rate: 29 }] } } }, /outside\.bands band 1: baseline_rate/],
    [{ card: { ...c, outside: { ...c.outside, bands: [{ ...c.outside.bands[0], baseline_interval: [0.4, 0.2] }] } } }, /outside\.bands band 1: baseline_interval/],
    [{ catch_run: { eligible: "3,100" } }, /meta\.catch_run\.eligible is not a count/],
    [{ fairness: { by_district: { ...dist, 3: { ...dist[3], interval_family_deff: [2.6, -0.3] } } } }, /by_district\[3\]\.interval_family_deff is not null or \[lo, hi\]/],
    [{ fairness: { by_district: { ...dist, 3: { ...dist[3], interval_family_deff: "wide" } } } }, /by_district\[3\]\.interval_family_deff is not/],
    [{ fairness: { by_district: { ...dist, 6: { ...dist[6], interval_family_zip: [3.7, 0] } } } }, /by_district\[6\]\.interval_family_zip is not null or \[lo, hi\]/],
    [{ fairness: { by_district: { ...dist, 4: { ...dist[4], interval_family_deff: [0.9, 3.1] } } } }, /by_district\[4\]\.evidence_above_even is true, but/, "the widened interval starts below 1"],
    [{ fairness: { by_district: { ...dist, 3: { ...dist[3], interval_family: [-0.1, 2] } } } }, /by_district\[3\]\.interval_family is not/],
    [{ fairness: { by_district: { ...dist, 3: { ...dist[3], evidence_above_even: "no" } } } }, /by_district\[3\]\.evidence_above_even is not true or false/],
    [{ fairness: { by_district: { ...dist, 3: { ...dist[3], evidence_above_even: true } } } }, /by_district\[3\]\.evidence_above_even is true, but/, "its intervals start below 1"],
    [{ fairness: { by_district: { ...dist, 5: { ...dist[5], evidence_above_even: true } } } }, /by_district\[5\]\.evidence_above_even is true, but interval_family/],
    [{ fairness: { by_district: { ...dist, 3: { ...dist[3], labelled: 2.5 } } } }, /by_district\[3\]\.labelled is not a count/],
  ];
  for (const [patch, re, why] of cases) {
    const r = check(banded(), { ...reviewMeta(2), ...latestMeta, ...patch }, { args: ["--review"] });
    assert.equal(r.ok, false, why ?? String(re));
    assert.match(r.err, re, why);
  }
});

/**
 * A place with every field the export gained in round 5: the County's type and notes, a Self Closed
 * closure, a kept Status Verification, a closure only an Approved to Reopen shows, a reopening no
 * closure could be placed before, an open last closure, and the counts by theme before the cut.
 */
function roundFivePlace() {
  const r5 = (date, extra) => record(date, { score: null, grade: null, minor: 0, grp: 0, notes: [], ...extra });
  const inspections = [
    r5("2025-11-17", { status: "Self Closed", major: 1, closed: true, closure: "health", reopened: false, reopened_on: null, county_type: "Routine" }),
    r5("2025-11-24", { type: "followup", score: 100, grade: "A", county_type: "Routine" }),
    r5("2026-01-06", { status: "Ordered Closed", type: "status_check", closed: true, closure: "permit", reopened: true, reopened_on: "2026-01-08", county_type: "Status Verification", notes: ["No Valid Permit"] }),
    r5("2026-01-08", { status: "Approved to Reopen", type: "reinspection", county_type: "Re-inspection" }),
    r5("2026-03-03", { major: 1, closed: true, closure: "health", closure_inferred: true, reopened: true, reopened_on: "2026-03-04", county_type: "Routine" }),
    r5("2026-03-04", { status: "Approved to Reopen", type: "followup", score: 95, grade: "A", county_type: "Routine" }),
    r5("2026-04-02", { status: "Approved to Reopen", type: "reinspection", reopen_without_closure: true, county_type: "Re-inspection" }),
    r5("2026-04-20", { type: "status_check", grp: 1, county_type: "Status Verification" }),
    r5("2026-05-01", { score: 95, grade: "A", minor: 1, county_type: "Routine" }),
    r5("2026-06-10", { type: "complaint", county_type: "Environmental", notes: ["Impoundment"] }),
    r5("2026-08-21", { status: "Ordered Closed", major: 1, closed: true, closure: "health", reopened: false, reopened_on: null, county_type: "Routine" }),
    r5("2026-08-28", { type: "reinspection", county_type: "Re-inspection" }),
  ];
  const item = (date, visit, code, theme, severity) => ({ date, visit, code, theme, severity, description: "x" });
  const violations = [
    item("2026-08-21", "routine", "23", "vermin", "major"),
    item("2026-03-03", "routine", "23", "vermin", "major"),
    item("2025-11-17", "routine", "21", "water", "major"),
    item("2026-05-01", "routine", "7", "temperature", "minor"),
    item("2026-04-20", "status_check", "49", "grp_signs", "grp"),
  ];
  const grade = { grade: "A", score: 95, date: "2026-05-01", replaced: null, open_closure: { date: "2026-08-21", reason: "health", later_ungraded: ["2026-08-28"] } };
  return place(1, {
    band: "1", points: 21,
    index: { last_visit: { date: "2026-08-28", type: "reinspection", county_type: "Re-inspection" }, grade },
    detail: {
      inspections, violations, violations_total: 5,
      theme_counts: {
        vermin: { major: 2, minor: 0, grp: 0, complaint: 0, latest: "2026-08-21" },
        water: { major: 1, minor: 0, grp: 0, complaint: 0, latest: "2025-11-17" },
        temperature: { major: 0, minor: 1, grp: 0, complaint: 0, latest: "2026-05-01" },
        grp_signs: { major: 0, minor: 0, grp: 1, complaint: 0, latest: "2026-04-20" },
      },
    },
  });
}

test("the round-5 record fields pass when well formed, and an export without them still passes", () => {
  const r = check([roundFivePlace()], reviewMeta(1), { args: ["--review"] });
  assert.ok(r.ok, r.err);
  assert.ok(check(banded(), reviewMeta(2), { args: ["--review"] }).ok, "an export from before them");
  const nullOpen = roundFivePlace();
  nullOpen.feature.properties.grade = { ...nullOpen.feature.properties.grade, open_closure: null };
  nullOpen.file.grade = nullOpen.feature.properties.grade;
  assert.ok(check([nullOpen], reviewMeta(1), { args: ["--review"] }).ok, "open_closure may be null");
  const withStatus = roundFivePlace();
  withStatus.feature.properties.grade = { ...withStatus.feature.properties.grade,
    open_closure: { ...withStatus.feature.properties.grade.open_closure, status: "Ordered Closed" } };
  withStatus.file.grade = withStatus.feature.properties.grade;
  const r2 = check([withStatus], reviewMeta(1), { args: ["--review"] });
  assert.ok(r2.ok, `open_closure may name the County's status text on the record that started it: ${r2.err}`);
});

test("malformed round-5 record fields fail", () => {
  const edit = (fn) => {
    const p = roundFivePlace();
    fn(p.file, p.feature.properties);
    return p;
  };
  const at = (k, patch) => edit((f) => Object.assign(f.inspections[k], patch));
  const openAs = (patch) => edit((f, idx) => {
    idx.grade = { ...idx.grade, open_closure: { ...idx.grade.open_closure, ...patch } };
    f.grade = idx.grade;
  });
  const lastVisit = (patch) => edit((f, idx) => {
    idx.last_visit = { ...idx.last_visit, ...patch };
    f.last_visit = idx.last_visit;
  });
  const cases = [
    [at(8, { notes: "No Valid Permit" }), /notes that are not a list of the County's note texts/],
    [at(8, { notes: [""] }), /notes that are not a list/],
    [at(8, { county_type: "" }), /county_type that is not the County's inspection type text/],
    [at(9, { county_type: "Routine" }), /county_type that is not one of the County's types for its visit type/],
    [at(7, { county_type: "Re-inspection" }), /county_type that is not one of the County's types/],
    [at(4, { closure_inferred: "yes" }), /closure_inferred outside true\|false/],
    [at(4, { status: "Ordered Closed" }), /closure_inferred on an "Ordered Closed" record/],
    [at(8, { closure_inferred: true }), /closure_inferred on a record that does not start a closure/],
    [at(4, { reopened: false, reopened_on: null }), /closure_inferred without the "Approved to Reopen" that shows it/],
    [at(6, { reopen_without_closure: 1 }), /reopen_without_closure outside true\|false/],
    [at(8, { reopen_without_closure: true }), /reopen_without_closure on a record that is not an "Approved to Reopen"/],
    [at(4, { closure_inferred: false }), /a closure on a record that is not "Ordered Closed" or "Self Closed" and not marked closure_inferred/],
    [at(0, { major: 0, minor: 1 }), /a "Self Closed" closure with no major violation/],
    [at(7, { grp: 0 }), /a "Self Closed" or status-verification record kept with no items and no closure order/],
    [at(7, { score: 90 }), /a status verification with a score/],
    [openAs({ date: "Aug 21" }), /grade\.open_closure outside null\|\{ date, reason/],
    [openAs({ reason: "fire" }), /grade\.open_closure outside/],
    [openAs({ later_ungraded: ["2026-08-01"] }), /grade\.open_closure outside/, "a later record before the closure"],
    [openAs({ later_ungraded: ["2026-08-21"] }), /grade\.open_closure outside/, "a record the same day is not a later record"],
    [openAs({ date: "2026-03-03" }), /grade\.open_closure that is not the date of the place's last closure/],
    [openAs({ reason: "permit" }), /grade\.open_closure whose reason is not its closure's/],
    [openAs({ status: "Self Closed" }), /grade\.open_closure whose status is not the County's status text on the record that started it/],
    [openAs({ status: "" }), /grade\.open_closure outside/],
    [
      edit((f) => {
        Object.assign(f.inspections[10], { reopened: true, reopened_on: "2026-08-28" });
        f.inspections[11].status = "Approved to Reopen";
      }),
      /grade\.open_closure on a closure an "Approved to Reopen" ended/,
    ],
    [edit((f) => Object.assign(f.inspections[11], { type: "routine", county_type: "Routine", score: 96, grade: "A" })), /grade\.open_closure with a graded visit after it/],
    [
      edit((f, idx) => {
        idx.grade = { ...idx.grade, date: "2026-09-01" };
        f.grade = idx.grade;
      }),
      /grade\.open_closure before the grade it follows/,
    ],
    [edit((f) => { f.violations_total = 4; }), /violations_total that is not a count at least the number of items listed/],
    [edit((f) => { f.violations_total = 9; }), new RegExp(`violations_total above the items listed, although the list was not cut at ${MAX_ITEMS}`)],
    [lastVisit({ county_type: "" }), /last_visit county_type that is not the County's inspection type text/],
    [lastVisit({ county_type: "Routine" }), /last_visit county_type that is not one of the County's types for its visit type/],
    [
      edit((f, idx) => {
        idx.last_visit = { date: "2026-08-28", type: "complaint", county_type: "Environmental" };
        f.last_visit = idx.last_visit;
        Object.assign(f.inspections[11], { type: "complaint", county_type: "Site Investigation" });
      }),
      /last_visit county_type that is not the County's type on the place file's last record/,
    ],
    [edit((f) => { f.theme_counts.vermin.major = 1; f.theme_counts.water.major = 2; }), /theme_counts below the items listed \(vermin\)/],
    [edit((f) => { f.theme_counts.vermin.latest = "2026-03-03"; }), /theme_counts below the items listed \(vermin\)/],
    [edit((f) => { f.theme_counts.grp_signs.grp = 2; }), /theme_counts that do not add up to violations_total \(6 against 5\)/],
    [edit((f) => { f.theme_counts.dirt = { major: 0, minor: 0, grp: 0, complaint: 0, latest: "2026-01-01" }; }), /theme_counts outside \{ theme: \{ major, minor, grp, complaint, latest \} \}/],
    [edit((f) => { f.theme_counts.vermin.complaint = 3; }), /theme_counts outside/],
    [edit((f) => { f.theme_counts = [1]; }), /theme_counts outside/],
  ];
  for (const [p, re, why] of cases) {
    const r = check([p], reviewMeta(1), { args: ["--review"] });
    assert.equal(r.ok, false, why ?? String(re));
    assert.match(r.err, re, why);
  }
});

test("past the item cut (export_site.MAX_VIOLATIONS, 150), the counts hold more than the list", () => {
  assert.equal(MAX_ITEMS, 150);
  const p = roundFivePlace();
  const extra = Array.from({ length: MAX_ITEMS - 5 }, (_, k) => ({ date: "2026-05-01", visit: "routine", code: "44", theme: "grp_facility", severity: "grp", description: `x${k}` }));
  p.file.violations = [...p.file.violations, ...extra];
  p.file.theme_counts.grp_facility = { major: 0, minor: 0, grp: MAX_ITEMS + 10, complaint: 0, latest: "2026-05-01" };
  p.file.violations_total = MAX_ITEMS + 15;
  const r = check([p], reviewMeta(1), { args: ["--review"] });
  assert.ok(r.ok, r.err);
  p.file.violations.push(extra[0]);
  assert.match(check([p], reviewMeta(1), { args: ["--review"] }).err, new RegExp(`violations missing or more than ${MAX_ITEMS}`));
});

test("a monitor summary, where the export has one, is { status, runs, alerts, next_window_date }", () => {
  const withMonitor = (body) => {
    const dir = mkdtempSync(join(tmpdir(), "food-check-"));
    try {
      mkdirSync(join(dir, "place"));
      const places = banded();
      writeFileSync(join(dir, "facilities.geojson"), JSON.stringify({ type: "FeatureCollection", features: places.map((p) => p.feature) }));
      for (const p of places) writeFileSync(join(dir, "place", `${p.feature.properties.facility_id}.json`), JSON.stringify(p.file));
      writeFileSync(join(dir, "meta.json"), JSON.stringify(reviewMeta(2)));
      writeFileSync(join(dir, "monitor_summary.json"), typeof body === "string" ? body : JSON.stringify(body));
      const r = spawnSync(process.execPath, [script, dir, "--review"], { encoding: "utf8" });
      return { ok: r.status === 0, err: r.stderr };
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  };
  const good = { status: "interim", runs: 2, alerts: ["Band 1's City rate after 90 days is below what its curve expects."], next_window_date: "2026-12-28" };
  assert.ok(withMonitor(good).ok);
  assert.ok(withMonitor({ status: "too early", runs: 0, alerts: [], next_window_date: null }).ok);
  for (const bad of [{ ...good, status: "fine" }, { ...good, runs: -1 }, { ...good, alerts: "none" }, { ...good, alerts: [""] }, { ...good, next_window_date: "soon" }]) {
    assert.match(withMonitor(bad).err, /monitor_summary\.json is not \{ status: too early\|interim\|complete\|failed/, JSON.stringify(bad));
  }
  assert.match(withMonitor("{").err, /monitor_summary\.json does not parse/);
  const stamped = { ...good, rule_version: "2026-09-01-5f50107e", inspections_through: "2026-09-27",
    by_district: { run: "forward_2026-06-01-bbbbbbbb", window_days: 90,
      districts: { 3: { labelled: 40, positives: 9, rate: 0.225, banded: { bands: ["1"], labelled: 12, positives: 4, rate: 0.3333, interval: [0.14, 0.61], expected: null } } } } };
  assert.ok(withMonitor(stamped).ok, "the stamps and the district figures");
  assert.ok(withMonitor({ ...stamped, rule_version: null, by_district: null }).ok, "before any rule is frozen, and before a list is scored");
  for (const bad of [{ ...stamped, rule_version: 5 }, { ...stamped, inspections_through: "last week" }, { ...stamped, by_district: [] },
    { ...stamped, by_district: { ...stamped.by_district, districts: { 3: { labelled: 4, positives: 9 } } } }]) {
    assert.match(withMonitor(bad).err, /monitor_summary\.json's rule_version, inspections_through or by_district/, JSON.stringify(bad));
  }
});

test("an estimate may name the fitted group it is read from, and a curve the counts each group pools", () => {
  const counted = { ...curve, groups: [[0, 1], [2, 2]], group_counts: [{ min_points: 0, max_points: 1, labelled: 200, positives: 30 }, { min_points: 2, max_points: 2, labelled: 100, positives: 30 }] };
  const meta = { ...reviewMeta(2), ...latestMeta, card: { ...latestMeta.card, curve: counted, curve_closure: counted } };
  const ranged = (patch) => {
    const places = withEstimate("scores");
    Object.assign(places[0].file.estimate, patch);
    return places;
  };
  const r = check(ranged({ min_points: 2, max_points: 2 }), meta, { args: ["--review"] });
  assert.ok(r.ok, r.err);
  const cases = [
    [ranged({ min_points: 2 }), meta, /an estimate whose fitted group is not \{ min_points <= max_points \}, whole points/],
    [ranged({ min_points: 3, max_points: 2 }), meta, /an estimate whose fitted group is not/],
    [ranged({ min_points: 1.5, max_points: 2 }), meta, /an estimate whose fitted group is not/],
    [withEstimate("scores"), { ...meta, card: { ...meta.card, curve: { ...counted, group_counts: counted.group_counts.slice(1) } } },
      /meta\.card\.curve\.group_counts is not one \{ min_points, max_points, labelled, positives \} per fitted group/],
    [withEstimate("scores"), { ...meta, card: { ...meta.card, curve_closure: { ...counted, group_counts: [counted.group_counts[0], { ...counted.group_counts[1], positives: 101 }] } } },
      /meta\.card\.curve_closure\.group_counts is not/],
    [withEstimate("scores"), { ...meta, card: { ...meta.card, outside: { ...meta.card.outside, curve: { ...counted, group_counts: [...counted.group_counts].reverse() } } } },
      /meta\.card\.outside\.curve\.group_counts is not/],
  ];
  for (const [places, m, re] of cases) {
    const got = check(places, m, { args: ["--review"] });
    assert.equal(got.ok, false, String(re));
    assert.match(got.err, re);
  }
});
