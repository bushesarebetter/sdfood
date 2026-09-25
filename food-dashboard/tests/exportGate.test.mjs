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
