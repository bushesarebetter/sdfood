import { test } from "node:test";
import assert from "node:assert/strict";
import { passesFilters, flagChips, typesFor, inBandScope, bandCounts, sortPlaces, shownPoints } from "../src/lib/filters.js";

const site = (id, name, district, facility_type, flags = [], extra = {}) => ({ properties: { facility_id: id, name, council_district: district, facility_type, flags, ...extra } });

const record = {
  features: [
    site("a", "Zeta Grill", 3, "restaurant", ["major", "vermin"]),
    site("b", "Alpha Market", 3, "market"),
    site("c", "Mid Cafe", 7, "restaurant", ["closed", "major"]),
    site("d", "Beta Bar", 1, "limited", ["repeat"]),
  ],
};
const ids = (fc, filters, opts) => fc.features.filter((f) => passesFilters(f.properties, filters, opts)).map((f) => f.properties.facility_id);

test("record mode: kind, district and record flags narrow the list; there is no band", () => {
  const base = { band: "1", districts: [], types: [], flag: null };
  assert.deepEqual(ids(record, base), ["a", "b", "c", "d"], "a band choice does nothing in record mode");
  assert.deepEqual(ids(record, { ...base, districts: [3] }), ["a", "b"]);
  assert.deepEqual(ids(record, { ...base, types: ["market", "limited"] }), ["b", "d"]);
  assert.deepEqual(ids(record, { ...base, flag: "major" }), ["a", "c"]);
  assert.deepEqual(flagChips(record).map((c) => c.key), ["major", "closed", "repeat", "vermin"]);
  assert.equal(flagChips(record)[0].count, 2);
  assert.deepEqual(typesFor(record).map((t) => [t.key, t.count]), [["restaurant", 2], ["market", 1], ["limited", 1]]);
  assert.deepEqual(sortPlaces(record.features).map((f) => f.properties.name), ["Alpha Market", "Beta Bar", "Mid Cafe", "Zeta Grill"], "by name");
  assert.equal(shownPoints({ points: 5 }), null, "no points outside bands mode");
  assert.equal(passesFilters(null, base), false);
});

const banded = {
  features: [
    site("1", "Omega Grill", 3, "restaurant", [], { band: "1", points: 21 }),
    site("2", "Beta Grill", 3, "restaurant", [], { band: "2", points: 17 }),
    site("3", "Alpha Grill", 7, "restaurant", [], { band: "2", points: 18 }),
    site("4", "Held Grill", 1, "restaurant", [], { on_hold: true }),
    site("5", "Scored Grill", 1, "restaurant", ["major"], { points: 4 }),
    site("6", "Aardvark Market", 1, "market"),
  ],
};

test("bands mode: band 1, bands 1 and 2, bands 1 to 3, or every listed place; a place under review is in no band", () => {
  const opts = { mode: "bands" };
  const base = { band: "3", districts: [], types: [], flag: null };
  assert.deepEqual(ids(banded, base, opts), ["1", "2", "3"]);
  assert.deepEqual(ids(banded, { ...base, band: "1" }, opts), ["1"]);
  assert.deepEqual(ids(banded, { ...base, band: "all" }, opts), ["1", "2", "3", "4", "5", "6"]);
  assert.equal(inBandScope(banded.features[3].properties, "3", opts), false);
  assert.deepEqual(bandCounts(banded), { 1: 1, 2: 3, all: 6 });
  assert.deepEqual(flagChips(banded, { band: "all" }, opts).map((c) => c.key), ["major"]);
  assert.deepEqual(flagChips(banded, { band: "3" }, opts), []);
});

test("bands mode sorts by band, then points, then name; points show only where present", () => {
  assert.deepEqual(sortPlaces(banded.features, { mode: "bands" }).map((f) => f.properties.facility_id), ["1", "3", "2", "5", "6", "4"]);
  assert.equal(shownPoints({ points: 4 }, { mode: "bands" }), 4);
  assert.equal(shownPoints({ on_hold: true, points: 4 }, { mode: "bands" }), null);
  assert.equal(shownPoints({}, { mode: "bands" }), null);
});
