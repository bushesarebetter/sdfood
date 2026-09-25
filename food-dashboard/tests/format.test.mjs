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
