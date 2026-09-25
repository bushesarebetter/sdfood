import { test } from "node:test";
import assert from "node:assert/strict";
import { fetchPlace, placeFileUrl, mergePlace, detailProps, PLACE_STATUS_TEXT } from "../src/lib/placeData.js";

const response = (status, body, type = "application/json") => ({
  status,
  ok: status >= 200 && status < 300,
  headers: { get: (k) => (k.toLowerCase() === "content-type" ? type : null) },
  json: async () => (typeof body === "string" ? JSON.parse(body) : body),
});

test("a place's file is named by its facility_id", () => {
  assert.equal(placeFileUrl("DEH2015-FFPP-000001"), "/data/place/DEH2015-FFPP-000001.json");
  assert.equal(placeFileUrl("a b/c"), "/data/place/a%20b%2Fc.json");
});

test("loaded, missing and network failures are told apart", async () => {
  const ok = await fetchPlace("X1", { fetchImpl: async (url) => (assert.equal(url, "/data/place/X1.json"), response(200, { facility_id: "X1", inspections: [] })) });
  assert.equal(ok.status, "ok");
  assert.equal(ok.detail.facility_id, "X1");
  assert.equal((await fetchPlace("X1", { fetchImpl: async () => response(404, "") })).status, "missing");
  assert.equal((await fetchPlace("X1", { fetchImpl: async () => response(200, "<!doctype html>", "text/html") })).status, "missing", "an app page served for a missing file");
  const net = await fetchPlace("X1", { fetchImpl: async () => { throw new TypeError("Failed to fetch"); } });
  assert.equal(net.status, "error");
  assert.equal((await fetchPlace("X1", { fetchImpl: async () => response(503, "") })).status, "error");
  assert.equal((await fetchPlace("X1", { fetchImpl: async () => response(200, "{not json") })).status, "error");
  assert.equal((await fetchPlace("X1", { fetchImpl: async () => response(200, { facility_id: "X2" }) })).status, "error", "a file for another place");
  assert.equal((await fetchPlace("", { fetchImpl: async () => response(200, {}) })).status, "missing");
  for (const k of ["loading", "missing", "error"]) assert.ok(PLACE_STATUS_TEXT[k]);
});

test("a place file may be flat or a Feature; the record is merged over the index entry", () => {
  const feature = { properties: { facility_id: "X1", name: "Sample", flags: ["major"] } };
  assert.deepEqual(mergePlace(feature, { facility_id: "X1", inspections: [1] }), { facility_id: "X1", name: "Sample", flags: ["major"], inspections: [1] });
  assert.deepEqual(detailProps({ type: "Feature", properties: { a: 1 } }), { a: 1 });
  assert.equal(detailProps(null), null);
});
