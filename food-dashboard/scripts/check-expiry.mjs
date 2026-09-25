#!/usr/bin/env node
/**
 * Refuse to build a site whose data has expired.
 *
 * Run by `npm run build` (the `prebuild` script) before the contract check.
 * A real export (meta.sample is not true) must carry meta.expires, and the
 * build stops once that day has passed: an expired export would still ship
 * with every new deploy otherwise. The invented sample never expires.
 *
 *   node scripts/check-expiry.mjs                          # public/data
 *   node scripts/check-expiry.mjs <dir> --today 2026-11-04 # for tests
 */
import { readFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const args = process.argv.slice(2);
const at = args.indexOf("--today");
const today = at >= 0 ? args[at + 1] : new Date();
const dirArg = args.find((a, i) => !a.startsWith("--") && args[i - 1] !== "--today");
const data = dirArg ? resolve(dirArg) : join(root, "public", "data");
const { isExpired } = await import(pathToFileURL(join(root, "src", "lib", "expiry.js")).href);

const path = join(data, "meta.json");
if (!existsSync(path)) {
  console.error(`FAIL: ${path} is missing`);
  process.exit(1);
}
const meta = JSON.parse(readFileSync(path, "utf8"));
if (meta.sample === true) {
  console.log("expiry check passed (sample data never expires)");
  process.exit(0);
}
if (!/^\d{4}-\d{2}-\d{2}$/.test(meta.expires ?? "")) {
  console.error("FAIL: a real export without meta.expires (YYYY-MM-DD)");
  process.exit(1);
}
if (isExpired(meta, today)) {
  console.error(`FAIL: this export expired on ${meta.expires}. Refresh it (fetch_sdfood.py, then export_site.py --publish) or restore the sample (scripts/make_sample_export.py) before building.`);
  process.exit(1);
}
console.log(`expiry check passed (expires ${meta.expires})`);
