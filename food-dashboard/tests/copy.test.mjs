import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Words the site does not use, anywhere in src/, index.html or the static
 * 404 page, comments included. Results are stated as rates, never around
 * what a list did not find; a band is a range of points on a published rule,
 * never a risk word or a prediction about a place; and the per-place diner
 * advice is gone. URLs are left out of the check (the host's name is not
 * copy).
 */
const root = join(dirname(fileURLToPath(import.meta.url)), "..");

const BANNED = [
  [/\bfail(?:s|ed|ing|ure|ures)?\b/i, "fail"],
  [/\brisk\b/i, "risk"],
  [/most likely/i, "most likely"],
  [/if you eat here/i, "if you eat here"],
  [/\bmiss(?:es|ed)\b/i, "misses"],
  [/\bcaught\b/i, "caught"],
  [/\bclean\b/i, "clean"],
  [/did not\b.*\bhave a major|\d+% did not/i, "N% did not"],
  [/did as well or better/i, "a simpler rule did as well or better"],
  [/at random/i, "picking at random"],
  [/found it in order/i, "found it in order"],
  [/reason to leave/i, "reason to leave"],
  [/inspected more often/i, "inspected more often"],
  [/strongest sign/i, "strongest sign"],
  [/public[- ]domain/i, "public domain"],
  [/point card/i, "point card"],
  [/—/, "em dash"],
];

function files(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) out.push(...files(path));
    else if (/\.(jsx?|css|html)$/.test(name)) out.push(path);
  }
  return out;
}

test("src/, index.html and the 404 page carry none of the reviewed-out words", () => {
  const targets = [...files(join(root, "src")), join(root, "index.html"), join(root, "public", "404.html")];
  assert.ok(targets.length > 30, "the walk found the source");
  const hits = [];
  for (const path of targets) {
    const lines = readFileSync(path, "utf8").split("\n");
    lines.forEach((line, i) => {
      const text = line.replace(/https?:\/\/\S+/g, "");
      for (const [re, word] of BANNED) if (re.test(text)) hits.push(`${relative(root, path)}:${i + 1} "${word}"`);
    });
  }
  assert.deepEqual(hits, []);
});

test("the site is the San Diego Food Inspection Record everywhere it names itself", () => {
  const html = readFileSync(join(root, "index.html"), "utf8");
  assert.match(html, /<title>San Diego Food Inspection Record<\/title>/);
  assert.match(html, /not affiliated with or endorsed by the County of San Diego/);
  assert.match(html, /<noscript>[\s\S]*sandiegocounty\.gov[\s\S]*<\/noscript>/);
  const vite = readFileSync(join(root, "vite.config.js"), "utf8");
  assert.match(vite, /name: "San Diego Food Inspection Record"/);
  assert.match(vite, /not affiliated with or endorsed by the County of San Diego/);
  assert.match(vite, /handler: "NetworkFirst"/);
  assert.doesNotMatch(vite + html, /Food Safety Risk|fonts\.googleapis/);
  assert.match(readFileSync(join(root, "public", "robots.txt"), "utf8"), /^Disallow: \/data\/$/m);
  assert.equal(JSON.parse(readFileSync(join(root, "package.json"), "utf8")).scripts.prebuild, "node scripts/check-expiry.mjs && node scripts/check-export.mjs");
});
