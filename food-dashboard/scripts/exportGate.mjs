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
 */
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scripts = dirname(fileURLToPath(import.meta.url));

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

export default function exportGate(env = process.env) {
  const external = env.SDFOOD_SITE_DATA ? resolve(env.SDFOOD_SITE_DATA) : null;
  const review = env.SDFOOD_SITE_REVIEW === "1";
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
      const problems = checkExport(dir, { review });
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
