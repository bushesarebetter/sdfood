/**
 * The export gate, inside the build: whatever data Vite actually ships is checked.
 *
 * `npm run build` also runs the checks as `prebuild`, but only on public/data,
 * and `npx vite build` (or a config with another publicDir) skips `prebuild`
 * entirely. This plugin runs check-expiry and check-export at `buildStart` on the
 * data the build will really contain, and stops the build if either fails.
 *
 * Where the data comes from:
 *   - default: `<publicDir>/data`, which in git is always the invented sample;
 *   - SDFOOD_SITE_DATA=<dir>: a published real export kept OUTSIDE git (export_site.py
 *     --publish writes data/site-publish/). It is checked, then copied over dist/data
 *     after the bundle is written, so the real export never has to enter public/data;
 *   - SDFOOD_SITE_REVIEW=1: an unpublished export for a local look. It is checked with
 *     --review, and the build goes to dist-review/ with a do-not-deploy marker, never dist/.
 *   - the City staff site: publish_city_site.py writes STAFF_MARKER into the PRIVATE staff
 *     repository's root. There the unpublished export is checked with --review (it is served
 *     behind a password by server.mjs, never publicly) and still built into dist/. The marker is a
 *     file, not an environment variable, so a public build cannot switch this on by a setting;
 *     tests/test_publish_city_site.py checks this public repository never contains it.
 *     The staff build also stops unless its meta.json is the staff copy (audience "staff") with a
 *     sunset date that has not passed: the same conditions under which server.mjs closes the site.
 */
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scripts = dirname(fileURLToPath(import.meta.url));
export const STAFF_MARKER = "STAFF-SITE-PRIVATE-DO-NOT-PUBLISH";

function run(script, args) {
  const r = spawnSync(process.execPath, [join(scripts, script), ...args], { encoding: "utf8" });
  return { ok: r.status === 0, out: `${r.stdout ?? ""}${r.stderr ?? ""}`.trim() };
}

/** Run both checks on `dir`; returns the problems ([] when the export may ship). */
export function checkExport(dir, { review = false } = {}) {
  const problems = [];
  if (!existsSync(join(dir, "meta.json"))) return [`no export in ${dir}`];
  for (const [script, args] of [["check-expiry.mjs", [dir]], ["check-export.mjs", [dir, ...(review ? ["--review"] : [])]]]) {
    const r = run(script, args);
    if (!r.ok) problems.push(`${script}: ${r.out}`);
  }
  return problems;
}

/** Why a staff build of `dir` may not ship ([] when it may): its meta.json must be the staff copy that
 *  publish_city_site.py writes (audience "staff") and carry a sunset date (YYYY-MM-DD, UTC) that has not
 *  passed. `today` is YYYY-MM-DD. */
export function staffProblems(dir, today = new Date().toISOString().slice(0, 10)) {
  let meta;
  try {
    meta = JSON.parse(readFileSync(join(dir, "meta.json"), "utf8"));
  } catch (e) {
    return [`cannot read ${join(dir, "meta.json")}: ${e.message}`];
  }
  const problems = [];
  if (meta?.audience !== "staff") {
    problems.push(`meta.audience is ${JSON.stringify(meta?.audience)}, not "staff": publish the staff site with publish_city_site.py`);
  }
  const sunset = meta?.sunset;
  const isDate = typeof sunset === "string" && /^\d{4}-\d{2}-\d{2}$/.test(sunset)
    && !Number.isNaN(Date.parse(`${sunset}T00:00:00Z`)) && new Date(`${sunset}T00:00:00Z`).toISOString().slice(0, 10) === sunset;
  if (!isDate) problems.push(`meta.sunset is ${JSON.stringify(sunset)}, not a date (YYYY-MM-DD)`);
  else if (sunset < today) problems.push(`the sunset date ${sunset} has passed: take the site down, or record a City owner and a new date`);
  return problems;
}

export default function exportGate(env = process.env, root = join(scripts, "..")) {
  const external = env.SDFOOD_SITE_DATA ? resolve(env.SDFOOD_SITE_DATA) : null;
  const review = env.SDFOOD_SITE_REVIEW === "1";
  const staff = existsSync(join(root, STAFF_MARKER));
  let publicDir, outDir;
  return {
    name: "sdfood-export-gate",
    apply: "build",
    config() {
      return review ? { build: { outDir: "dist-review" } } : {};
    },
    configResolved(config) {
      publicDir = config.publicDir;
      outDir = resolve(config.root, config.build.outDir);
    },
    buildStart() {
      const dir = external ?? (publicDir ? join(publicDir, "data") : null);
      if (!dir) this.error("the build has no public directory, so it has no export to check");
      const problems = checkExport(dir, { review: review || staff });
      if (staff) problems.push(...staffProblems(dir));
      if (problems.length) this.error(`the export at ${dir} may not ship:\n${problems.join("\n")}`);
    },
    closeBundle() {
      if (external) {
        const target = join(outDir, "data");
        rmSync(target, { recursive: true, force: true });
        cpSync(external, target, { recursive: true });
      }
      if (review) {
        writeFileSync(join(outDir, "REVIEW-BUILD-DO-NOT-DEPLOY.txt"),
          "This build holds an unpublished export for review. It did not pass the publication gates. Do not deploy it.\n");
      }
    },
  };
}
