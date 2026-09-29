import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

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
