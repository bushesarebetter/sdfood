import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { isExpired, expiryNotice, isoDay } from "../src/lib/expiry.js";

const script = join(dirname(fileURLToPath(import.meta.url)), "..", "scripts", "check-expiry.mjs");

test("an export expires only after its expiry day", () => {
  const meta = { expires: "2026-11-03", inspections_through: "2026-09-19" };
  assert.equal(isExpired(meta, "2026-09-24"), false);
  assert.equal(isExpired(meta, "2026-11-03"), false, "the expiry day itself is still current");
  assert.equal(isExpired(meta, "2026-11-04"), true);
  assert.equal(isExpired(meta, "2027-01-01T08:00:00Z"), true);
  assert.equal(isExpired(meta, new Date(2026, 10, 4, 0, 30)), true, "a Date is read in local time");
  assert.equal(isExpired(meta, new Date(2026, 10, 3, 23, 30)), false);
});

test("the sample, an old export and a malformed date never expire", () => {
  assert.equal(isExpired({ expires: null }, "2099-01-01"), false);
  assert.equal(isExpired({}, "2099-01-01"), false);
  assert.equal(isExpired(null, "2099-01-01"), false);
  assert.equal(isExpired({ expires: "soon" }, "2099-01-01"), false);
  assert.equal(isExpired({ expires: "2026-11-03" }, "not a date"), false);
});

test("the notice names the date the record has moved on from and offers search only", () => {
  assert.equal(
    expiryNotice({ inspections_through: "2026-09-19" }),
    "This export is out of date. The County's record has moved on since September 19, 2026, so this site now offers only a search of the record it holds. The County's own search has current results.",
  );
  assert.equal(isoDay(new Date(2026, 0, 5)), "2026-01-05");
});

function runCheck(meta, today) {
  const dir = mkdtempSync(join(tmpdir(), "food-expiry-"));
  try {
    writeFileSync(join(dir, "meta.json"), JSON.stringify(meta));
    const r = spawnSync(process.execPath, [script, dir, "--today", today], { encoding: "utf8" });
    return { ok: r.status === 0, err: r.stderr };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("the prebuild check stops a build of a real export once it has expired", () => {
  assert.ok(runCheck({ sample: false, expires: "2026-10-03" }, "2026-10-03").ok);
  const late = runCheck({ sample: false, expires: "2026-10-03" }, "2026-10-04");
  assert.equal(late.ok, false);
  assert.match(late.err, /expired on 2026-10-03/);
  assert.match(runCheck({ sample: false }, "2026-10-04").err, /without meta\.expires/);
  assert.ok(runCheck({ sample: true, expires: null }, "2099-01-01").ok, "the sample never expires");
});
