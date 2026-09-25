import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { placeKey, placePath, mapPlacePath, parsePlacePath, findPlace } from "../src/lib/links.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

const features = [
  { properties: { facility_id: "DEH2015-FFPP-000001" } },
  { properties: { facility_id: "SAMPLE FFPP/002" } },
  { properties: { facility_id: "43" } },
  { properties: {} },
];

test("every place link is keyed on the County's permit record id", () => {
  assert.equal(placeKey(features[0].properties), "DEH2015-FFPP-000001");
  assert.equal(placePath(features[0].properties), "/place/DEH2015-FFPP-000001");
  assert.equal(placePath(features[1].properties), "/place/SAMPLE%20FFPP%2F002", "an id is encoded");
  assert.equal(mapPlacePath(features[1].properties), "/map?place=SAMPLE%20FFPP%2F002");
  assert.equal(placeKey(features[3].properties), "", "a place without an id has no link");
  assert.equal(placeKey(null), "");
});

test("a place path decodes back to the same place", () => {
  for (const f of features.slice(0, 3)) assert.equal(findPlace(features, parsePlacePath(placePath(f.properties))), f);
  assert.equal(parsePlacePath("/place/DEH2015-FFPP-000001/"), "DEH2015-FFPP-000001");
  assert.equal(parsePlacePath("/place/"), null);
  assert.equal(parsePlacePath("/place/a/b"), null);
  assert.equal(parsePlacePath("/place/%E0%A4%A"), null, "a malformed escape is not a place");
});

test("a numeric key is only ever a facility_id: an old rank link finds nothing", () => {
  assert.equal(findPlace(features, "43").properties.facility_id, "43", "a facility_id that happens to be digits");
  assert.equal(findPlace(features, "1"), null);
  assert.equal(findPlace(features, 2), null);
  assert.equal(findPlace(features, "DEH0000-FFPP-999999"), null);
  assert.equal(findPlace(features, ""), null);
  assert.equal(findPlace(null, "1"), null);
  for (const path of ["src/lib/links.js", "src/useDeepLink.js", "src/App.jsx"]) {
    assert.doesNotMatch(readFileSync(join(root, path), "utf8"), /\.rank\b|rank link|by rank/, `${path} has no rank fallback`);
  }
});
