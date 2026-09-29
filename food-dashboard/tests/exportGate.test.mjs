import { test } from "node:test";
import assert from "node:assert/strict";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import exportGate, { checkExport } from "../scripts/exportGate.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const sampleData = join(root, "public", "data");

/** Run the plugin's hooks as Vite would, without Vite: returns the error message, or null. */
function build(env, publicDir, outDir) {
  const gate = exportGate(env);
  const extra = gate.config?.() ?? {};
  gate.configResolved({ publicDir, root: dirname(outDir), build: { outDir: extra.build?.outDir ?? outDir } });
  try {
    gate.buildStart.call({ error: (m) => { throw new Error(m); } });
  } catch (e) {
    return e.message;
  }
  gate.closeBundle();
  return null;
}

/** A copy of the sample with meta.sample flipped: a real-looking export that is not approved. */
function unapproved(dir) {
  cpSync(sampleData, dir, { recursive: true });
  const meta = JSON.parse(readFileSync(join(dir, "meta.json"), "utf8"));
  writeFileSync(join(dir, "meta.json"), JSON.stringify({ ...meta, sample: false, run: "forward_2026-09-20", expires: "2026-09-01" }));
  return dir;
}

test("the committed sample passes the gate", () => {
  assert.deepEqual(checkExport(sampleData), []);
});

test("a build whose publicDir holds an unapproved export stops at buildStart", () => {
  const tmp = mkdtempSync(join(tmpdir(), "gate-"));
  try {
    const pub = join(tmp, "pub");
    unapproved(join(pub, "data"));
    const err = build({}, pub, join(tmp, "dist"));
    assert.match(err ?? "", /may not ship/);
    assert.ok(!existsSync(join(tmp, "dist")), "nothing is written");
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test("SDFOOD_SITE_DATA is checked, and on success replaces dist/data", () => {
  const tmp = mkdtempSync(join(tmpdir(), "gate-"));
  try {
    const bad = unapproved(join(tmp, "bad"));
    assert.match(build({ SDFOOD_SITE_DATA: bad }, join(root, "public"), join(tmp, "dist")) ?? "", /may not ship/);
    // a "published" export stand-in: the sample itself (it passes), copied into dist/data after the bundle
    const out = join(tmp, "dist");
    mkdirSync(join(out, "data"), { recursive: true });
    writeFileSync(join(out, "data", "stale.json"), "{}");
    assert.equal(build({ SDFOOD_SITE_DATA: sampleData }, join(root, "public"), out), null);
    assert.ok(existsSync(join(out, "data", "meta.json")) && !existsSync(join(out, "data", "stale.json")));
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test("a review build goes to dist-review with a do-not-deploy marker", () => {
  const gate = exportGate({ SDFOOD_SITE_REVIEW: "1" });
  assert.deepEqual(gate.config(), { build: { outDir: "dist-review" } });
  const tmp = mkdtempSync(join(tmpdir(), "gate-"));
  try {
    const out = join(tmp, "dist-review");
    mkdirSync(out);
    gate.configResolved({ publicDir: join(root, "public"), root: tmp, build: { outDir: "dist-review" } });
    gate.buildStart.call({ error: (m) => { throw new Error(m); } });
    gate.closeBundle();
    assert.ok(existsSync(join(out, "REVIEW-BUILD-DO-NOT-DEPLOY.txt")));
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

const today = new Date().toISOString().slice(0, 10);
const inDays = (n) => new Date(Date.now() + n * 864e5).toISOString().slice(0, 10);

/** In `tmp`: public/data holding a real-looking, unpublished export (the staff copy of meta.json unless
 *  `metaExtra` says otherwise). Returns the public directory. */
function staffExport(tmp, metaExtra = {}) {
  const pub = join(tmp, "public");
  cpSync(sampleData, join(pub, "data"), { recursive: true });
  const meta = JSON.parse(readFileSync(join(pub, "data", "meta.json"), "utf8"));
  const places = JSON.parse(readFileSync(join(pub, "data", "facilities.geojson"), "utf8"));
  for (const f of places.features) {
    f.properties.name = f.properties.name.replace(/^Sample /, "Real ");
    const pf = join(pub, "data", "place", `${f.properties.facility_id}.json`);
    const d = JSON.parse(readFileSync(pf, "utf8"));
    writeFileSync(pf, JSON.stringify({ ...d, name: f.properties.name }));
  }
  writeFileSync(join(pub, "data", "facilities.geojson"), JSON.stringify(places));
  writeFileSync(join(pub, "data", "meta.json"), JSON.stringify({ ...meta, sample: false, run: "forward_x",
    inspections_through: today, expires: inDays(7), provenance: { code_sha: "abc", pull_sha256: "def" },
    audience: "staff", sunset: inDays(200), ...metaExtra }));
  return pub;
}

/** The staff build's buildStart for `tmp` (the marker is written): the error message, or null. */
async function staffBuild(tmp, pub) {
  const { STAFF_MARKER } = await import("../scripts/exportGate.mjs");
  writeFileSync(join(tmp, STAFF_MARKER), "private\n");
  const staff = exportGate({}, tmp);
  staff.configResolved({ publicDir: pub, root: tmp, build: { outDir: "dist" } });
  try {
    staff.buildStart.call({ error: (m) => { throw new Error(m); } });
    return null;
  } catch (e) {
    return e.message;
  }
}

test("the City staff site (marker file in its private repo) builds an unpublished export into dist/", async () => {
  const { STAFF_MARKER } = await import("../scripts/exportGate.mjs");
  const tmp = mkdtempSync(join(tmpdir(), "gate-staff-"));
  try {
    const pub = staffExport(tmp);
    const withoutMarker = exportGate({}, tmp);
    withoutMarker.configResolved({ publicDir: pub, root: tmp, build: { outDir: "dist" } });
    assert.throws(() => withoutMarker.buildStart.call({ error: (m) => { throw new Error(m); } }), /not approved for publication/);
    writeFileSync(join(tmp, STAFF_MARKER), "private\n");
    const staff = exportGate({}, tmp);
    assert.deepEqual(staff.config(), {}, "the staff build still goes to dist/");
    staff.configResolved({ publicDir: pub, root: tmp, build: { outDir: "dist" } });
    staff.buildStart.call({ error: (m) => { throw new Error(m); } });   // review-mode checks pass
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test("the staff build stops unless meta.json is the staff copy with a sunset that has not passed", async () => {
  const tmp = mkdtempSync(join(tmpdir(), "gate-staff-"));
  try {
    const pub = staffExport(tmp);
    const metaPath = join(pub, "data", "meta.json");
    const staffMeta = JSON.parse(readFileSync(metaPath, "utf8"));
    for (const [extra, why] of [
      [{ audience: undefined }, /meta\.audience is undefined, not "staff"/],
      [{ sunset: inDays(-1) }, /the sunset date .* has passed/],
    ]) {
      writeFileSync(metaPath, JSON.stringify({ ...staffMeta, ...extra }));
      assert.match(await staffBuild(tmp, pub) ?? "", why, JSON.stringify(extra));
    }
    writeFileSync(metaPath, JSON.stringify({ ...staffMeta, sunset: today }));
    assert.equal(await staffBuild(tmp, pub), null, "the sunset day itself still builds");
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test("staffProblems: the staff copy, and a real sunset date on or after the day it is given", async () => {
  const { staffProblems } = await import("../scripts/exportGate.mjs");
  const tmp = mkdtempSync(join(tmpdir(), "gate-staff-"));
  try {
    const data = join(tmp, "data");
    mkdirSync(data);
    const check = (meta, day) => {
      writeFileSync(join(data, "meta.json"), JSON.stringify(meta));
      return staffProblems(data, day).join("\n");
    };
    assert.equal(check({ audience: "staff", sunset: "2027-06-30" }, "2027-06-30"), "");
    assert.match(check({ audience: "staff", sunset: "2027-06-30" }, "2027-07-01"), /2027-06-30 has passed/);
    assert.match(check({ audience: "public", sunset: "2027-06-30" }, "2027-01-01"), /meta\.audience is "public", not "staff"/);
    assert.match(check({ sunset: "2027-06-30" }, "2027-01-01"), /meta\.audience is undefined/);
    for (const sunset of [undefined, null, "", "soon", "2027-02-30", "2027-6-30", 20270630]) {
      assert.match(check({ audience: "staff", sunset }, "2027-01-01"), /meta\.sunset is .*, not a date/, String(sunset));
    }
    assert.match(staffProblems(join(tmp, "missing")).join(), /cannot read/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});
