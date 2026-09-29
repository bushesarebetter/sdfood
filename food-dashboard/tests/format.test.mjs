import { test } from "node:test";
import assert from "node:assert/strict";
import { facilitiesToCsv, csvColumns } from "../src/lib/format.js";

const meta = { generated: "2026-09-20", inspections_through: "2026-09-19", expires: "2026-10-03" };

const feature = {
  properties: {
    facility_id: "SAMPLE-FFPP-00004", name: "Sample Taqueria, North", address: "1234 Sample Row, San Diego, CA 92104", facility_type: "restaurant",
    council_district: 3, last_visit: { date: "2026-02-08", type: "reinspection" },
    grade: { grade: "B", score: 84, date: "2026-02-01", replaced: null }, flags: ["major", "bc", "temperature"], band: "1", points: 21,
  },
  geometry: { coordinates: [-117.13, 32.75] },
};

const parse = (csv) => {
  const [header, row] = csv.split("\n");
  const cols = header.split(",");
  const vals = row.match(/("([^"]|"")*"|[^,]*)(,|$)/g).map((s) => s.replace(/,$/, "").replace(/^"|"$/g, "").replace(/""/g, '"'));
  return (name) => vals[cols.indexOf(name)];
};

test("record mode: the County's record, our flags and the list dates, with no position, band or points", () => {
  const csv = facilitiesToCsv([feature], { meta });
  const header = csv.split("\n")[0].split(",");
  for (const col of ["rank", "percentile", "band", "points", "band_stability", "met_items"]) assert.ok(!header.includes(col), col);
  const get = parse(csv);
  assert.equal(get("name"), "Sample Taqueria, North", "a comma in the name is quoted");
  assert.equal(get("facility_type"), "Restaurant");
  assert.equal(get("grade"), "B");
  assert.equal(get("grade_score"), "84");
  assert.equal(get("last_visit_type"), "reinspection");
  assert.equal(get("flags"), "major; bc; temperature");
  assert.equal(get("list_date"), "2026-09-20");
  assert.equal(get("expires"), "2026-10-03");
  assert.equal(get("lat"), "32.75");
});

test("bands mode adds band, points and review state, and a held place shows neither", () => {
  const get = parse(facilitiesToCsv([feature], { meta, mode: "bands" }));
  assert.equal(get("band"), "1");
  assert.equal(get("points"), "21");
  const held = { ...feature, properties: { ...feature.properties, band: undefined, points: undefined, on_hold: true } };
  const h = parse(facilitiesToCsv([held], { meta, mode: "bands" }));
  assert.equal(h("band"), "");
  assert.equal(h("points"), "");
  assert.equal(h("under_review"), "yes");
  assert.deepEqual(csvColumns({ mode: "bands" }).slice(5, 8), ["band", "points", "under_review"]);
});

test("a place with no grade still produces a row of the same width", () => {
  const bare = { properties: { facility_id: "x", name: "Sample", address: "x", flags: [] }, geometry: { coordinates: [0, 0] } };
  const [header, row] = facilitiesToCsv([bare]).split("\n");
  assert.equal(header.split(",").length, row.split(",").length);
});

test("a name that a spreadsheet would run as a formula is neutralised; numbers are not", () => {
  const evil = { ...feature, properties: { ...feature.properties, name: '=HYPERLINK("http://evil.example","x")', address: "@SUM(A1)" } };
  const get = parse(facilitiesToCsv([evil], { meta }));
  assert.equal(get("name"), `'=HYPERLINK("http://evil.example","x")`);
  assert.equal(get("address"), "'@SUM(A1)");
  assert.equal(get("lon"), "-117.13", "a negative longitude stays a number");
});

test("the CSV's file name says what is in it", async () => {
  const { csvFilename } = await import("../src/lib/format.js");
  const meta = { generated: "2026-09-29" };
  assert.equal(csvFilename(meta, {}), "food-inspection-record-2026-09-29.csv");
  assert.equal(csvFilename(meta, { band: "all", districts: [3] }), "food-inspection-record-district-3-2026-09-29.csv");
  assert.equal(csvFilename(meta, { county: true, band: "2", districts: [9, 3], flag: "major" }),
    "food-inspection-record-county-district-3-9-band-1-to-2-major-2026-09-29.csv");
  assert.equal(csvFilename(meta, { band: "1" }), "food-inspection-record-band-1-2026-09-29.csv");
  assert.equal(csvFilename(null, {}), "food-inspection-record-export.csv");
});


test("every CSV row names the list it came from", async () => {
  const { facilitiesToCsv, csvColumns } = await import("../src/lib/format.js");
  assert.ok(csvColumns().includes("list_run") && csvColumns({ mode: "bands" }).includes("list_run"));
  const csv = facilitiesToCsv([{ properties: { facility_id: "X", name: "N" }, geometry: { coordinates: [0, 0] } }],
    { meta: { run: "forward_2026-09-20-abcd1234", generated: "2026-09-29" } });
  const [head, row] = csv.split("\n");
  assert.equal(row.split(",")[head.split(",").indexOf("list_run")], "forward_2026-09-20-abcd1234");
});


test("a place outside the City is labelled by its own town", async () => {
  const { cityOf } = await import("../src/lib/format.js");
  assert.equal(cityOf("401 W MAIN ST, EL CAJON, CA 92020"), "El Cajon");
  assert.equal(cityOf("1 Oak St, SAN DIEGO, CA 92101"), "San Diego");
  assert.equal(cityOf("no commas here"), null);
  assert.equal(cityOf(null), null);
});


test("bands mode: every banded row says what its band means, and that the rule is the students', not the County's", async () => {
  const { bandMeaning, BAND_SOURCE } = await import("../src/lib/format.js");
  const { staffMeta } = await import("./fixtures/bandsMeta.mjs");
  const m = { ...meta, ...staffMeta };
  const banded = { ...feature, properties: { ...feature.properties, band: "1", points: 9, council_district: 4 } };
  const get = parse(facilitiesToCsv([banded], { meta: m, mode: "bands" }));
  assert.equal(BAND_SOURCE, "Students' point rule, not a County rating.");
  assert.ok(get("what_band_means").startsWith(
    "In the backtest, about 37 in 100 band 1 places had a major violation at their next routine inspection (likely 33 to 41), against 21 in 100 of all scored restaurants; about 63 in 100 had none."));
  assert.ok(get("what_band_means").includes("In council district 4, about 29 in 100 band 1 places had one"), "the band line the place's page shows");
  assert.ok(get("what_band_means").endsWith(" Students' point rule, not a County rating."));
  const none = { ...feature, properties: { ...feature.properties, band: undefined, points: 3 } };
  const { POINTS_SOURCE } = await import("../src/lib/format.js");
  assert.equal(parse(facilitiesToCsv([none], { meta: m, mode: "bands" }))("what_band_means"), POINTS_SOURCE,
    "points with no band still say where the number comes from");
  const unscored = { ...feature, properties: { ...feature.properties, band: undefined, points: undefined } };
  assert.equal(parse(facilitiesToCsv([unscored], { meta: m, mode: "bands" }))("what_band_means"), "", "no points, no text");
  const held = { ...feature, properties: { ...feature.properties, band: "1", on_hold: true } };
  assert.equal(parse(facilitiesToCsv([held], { meta: m, mode: "bands" }))("what_band_means"), "", "a held place shows no band");
  assert.equal(bandMeaning({ band: "1" }, m, { mode: "record" }), "");
  assert.ok(!csvColumns().includes("what_band_means"), "a record export has no band column");
  assert.deepEqual(csvColumns({ mode: "bands" }).slice(5, 9), ["band", "points", "under_review", "what_band_means"]);
});
