// The City staff site: the built food-dashboard with the real export, behind a sign-in.
// Node built-ins only. publish_city_site.py copies this file into the private deploy repository.
//
// Environment (Render: the service's Environment page; never in any repository):
//   SITE_USERS     one sign-in per person: "ana:<token>,ben:<token>" (each token 16+ characters; make one with
//                  python -c "import secrets; print(secrets.token_urlsafe(24))"). Remove a person's entry the day
//                  they leave. Every data request is logged with the user name, so Render's log is an access log.
//   SITE_PASSWORD  the older shared sign-in (user SITE_USER, default "city"), 16+ characters; while migrating
//   SITE_CONTACT   who to ask for access, shown on the sign-in refusal (for example "Jane Doe, jane@example.org")
//   PORT           set by Render
//
// What it does besides serving files: refuses to start with a weak password; slows password guessing
// (10 failures per client per 15 minutes, then 429); /logout clears the site from the browser; the
// service worker is served before sign-in so a build that removes it reaches every browser; data is
// never cached on a shared computer (no-store); security headers on every response; /geocode looks up
// an address (OpenStreetMap, then the US Census), cached and held to Nominatim's usage policy.
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize, sep } from "node:path";
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { gzipSync } from "node:zlib";

const ROOT = join(import.meta.dirname, "dist");
const MIN_SECRET = 16;
const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".geojson": "application/geo+json", ".webmanifest": "application/manifest+json",
  ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2", ".txt": "text/plain",
  ".csv": "text/csv; charset=utf-8",
};
const COMPRESS = new Set([".html", ".js", ".css", ".json", ".geojson", ".svg", ".webmanifest", ".txt", ".csv"]);
const SECURITY = {
  "Strict-Transport-Security": "max-age=31536000",
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "X-Robots-Tag": "noindex, nofollow",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Content-Security-Policy-Report-Only":
    "default-src 'self'; script-src 'self' https://maps.googleapis.com https://maps.gstatic.com; " +
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; " +
    "img-src 'self' data: blob: https://*.googleapis.com https://*.gstatic.com https://*.google.com https://*.ggpht.com; " +
    "connect-src 'self' https://*.googleapis.com https://*.gstatic.com https://*.google.com data: blob:; " +
    "worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'",
};

// ── sign-in ─────────────────────────────────────────────────────────────────────────────
// Compare fixed-length digests, so neither a password nor its length leaks through timing.
const digest = (s) => createHash("sha256").update(s).digest();
const NOBODY = digest(randomBytes(32));

function parseUsers(env) {
  const users = new Map();
  const weak = [];
  for (const entry of (env.SITE_USERS || "").split(",")) {
    const i = entry.indexOf(":");
    const user = entry.slice(0, i).trim(), token = entry.slice(i + 1).trim();
    if (i <= 0 || !user) continue;
    if (token.length < MIN_SECRET) weak.push(user);
    else users.set(user, digest(`${user}:${token}`));
  }
  if (env.SITE_PASSWORD) {
    const user = env.SITE_USER || "city";
    if (env.SITE_PASSWORD.length < MIN_SECRET) weak.push(user);
    else users.set(user, digest(`${user}:${env.SITE_PASSWORD}`));
  }
  return { users, weak };
}

const { users: USERS, weak: WEAK } = parseUsers(process.env);
if (WEAK.length) {
  console.error(`refusing to start: the sign-in for ${WEAK.join(", ")} is shorter than ${MIN_SECRET} characters. ` +
    'Make one with: python -c "import secrets; print(secrets.token_urlsafe(24))"');
  process.exit(1);
}

/** The signed-in user's name, or null. */
function signedIn(header) {
  if (!header?.startsWith("Basic ")) return null;
  const given = Buffer.from(header.slice(6), "base64").toString("utf8");
  const user = given.slice(0, Math.max(0, given.indexOf(":")));
  return timingSafeEqual(digest(given), USERS.get(user) ?? NOBODY) && USERS.has(user) ? user : null;
}

// Failed sign-ins per client. Render and Cloudflare put the client's address in these headers; the
// service port is not reachable from the internet directly, so they are what Render set.
const FAILS = new Map();
const WINDOW_MS = 15 * 60e3, MAX_FAILS = 10;
const clientOf = (req) =>
  req.headers["cf-connecting-ip"] || (req.headers["x-forwarded-for"] || "").split(",")[0].trim() || req.socket.remoteAddress;

function blocked(who, now) {
  const f = FAILS.get(who);
  return Boolean(f && now - f.since < WINDOW_MS && f.n >= MAX_FAILS);
}

function failed(who, now) {
  const f = FAILS.get(who);
  FAILS.set(who, f && now - f.since < WINDOW_MS ? { n: f.n + 1, since: f.since } : { n: 1, since: now });
  if (FAILS.size > 10_000) FAILS.clear();
  console.warn(`sign-in failed from ${who}`);
}

// ── address lookup ──────────────────────────────────────────────────────────────────────
// OpenStreetMap's Nominatim, held to San Diego County, then the US Census geocoder. Nominatim's usage
// policy: identify the app, at most one request a second, cache results. Answers {lat, lon, label,
// source}, or null.
const COUNTY_BOX = "-117.61,33.51,-116.08,32.53";
const UA = "sdfood-city-staff-site (https://github.com/bushesarebetter/sdfood)";
const GEO = new Map();
let nextNominatim = 0;

async function nominatim(url) {
  const now = Date.now(), at = Math.max(now, nextNominatim);
  if (at - now > 5000) return null;                  // a queue longer than 5 s: skip to the Census
  nextNominatim = at + 1100;
  await new Promise((r) => setTimeout(r, at - now));
  return fetch(url, { headers: { "User-Agent": UA }, signal: AbortSignal.timeout(5000) });
}

async function geocode(q) {
  try {
    const r = await nominatim(`https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&countrycodes=us&bounded=1&viewbox=${COUNTY_BOX}&q=${encodeURIComponent(q)}`);
    const [hit] = r?.ok ? await r.json() : [];
    if (hit) return { lat: Number(hit.lat), lon: Number(hit.lon), label: hit.display_name, source: "osm" };
  } catch {}
  try {
    const addr = /\b(ca|california)\b|\d{5}/i.test(q) ? q : `${q}, San Diego County, CA`;
    const r = await fetch(`https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?benchmark=Public_AR_Current&format=json&address=${encodeURIComponent(addr)}`,
      { signal: AbortSignal.timeout(5000) });
    const m = r.ok ? (await r.json())?.result?.addressMatches?.[0] : null;
    if (m) return { lat: m.coordinates.y, lon: m.coordinates.x, label: m.matchedAddress, source: "census" };
  } catch {}
  return null;
}

async function cachedGeocode(q) {
  const key = q.toLowerCase().replace(/\s+/g, " ");
  if (GEO.has(key)) return GEO.get(key);
  const hit = await geocode(q);
  if (GEO.size > 5000) GEO.delete(GEO.keys().next().value);
  GEO.set(key, hit);
  return hit;
}

// ── files ───────────────────────────────────────────────────────────────────────────────
const CACHE = new Map();                            // path -> {mtime, body, gz, etag}

async function load(path) {
  let s;
  try {
    s = await stat(path);
  } catch {
    return null;
  }
  if (!s.isFile()) return null;
  const hit = CACHE.get(path);
  if (hit && hit.mtime === s.mtimeMs) return hit;
  const body = await readFile(path);
  const entry = { mtime: s.mtimeMs, body, gz: COMPRESS.has(extname(path)) ? gzipSync(body) : null,
                  etag: `"${createHash("sha256").update(body).digest("base64url").slice(0, 22)}"` };
  CACHE.set(path, entry);
  return entry;
}

async function meta() {
  try {
    return JSON.parse((await load(join(ROOT, "data", "meta.json")))?.body ?? "{}");
  } catch {
    return {};
  }
}

const SERVER_BUILD = createHash("sha256").update(await readFile(new URL(import.meta.url))).digest("hex").slice(0, 12);

// ── requests ────────────────────────────────────────────────────────────────────────────
// One malformed request (an unparsable URL, a bad %-escape) must never take the site down.
process.on("unhandledRejection", (e) => console.error("unhandled rejection:", e));

createServer((req, res) => {
  for (const [k, v] of Object.entries(SECURITY)) res.setHeader(k, v);
  handle(req, res).catch((e) => {
    const bad = e instanceof URIError || e instanceof TypeError;
    if (!bad) console.error(e);
    if (!res.headersSent) res.writeHead(bad ? 400 : 500);
    res.end();
  });
}).listen(Number(process.env.PORT) || 10000, "0.0.0.0");

function send(req, res, status, headers, body) {
  if (body != null && status !== 304) headers = { ...headers, "Content-Length": Buffer.byteLength(body) };
  res.writeHead(status, headers);
  res.end(req.method === "HEAD" || status === 304 ? undefined : body);
}

async function handle(req, res) {
  if (req.method !== "GET" && req.method !== "HEAD") return send(req, res, 405, { Allow: "GET, HEAD" }, "");
  const url = new URL(req.url, "http://x");

  // Open, carrying no data: the health check, the service worker (so a build that removes it reaches
  // browsers that are not signed in), and sign-out.
  if (url.pathname === "/healthz") {
    const m = await meta();
    const today = new Date().toISOString().slice(0, 10);
    return send(req, res, 200, { "Content-Type": "application/json", "Cache-Control": "no-store" }, JSON.stringify({
      ok: true, run: m.run ?? null, inspections_through: m.inspections_through ?? null, expires: m.expires ?? null,
      stale: Boolean(m.expires && today > m.expires), source: process.env.RENDER_GIT_COMMIT ?? null, server: SERVER_BUILD,
    }));
  }
  if (url.pathname === "/sw.js") {
    const f = await load(join(ROOT, "sw.js"));
    return f ? send(req, res, 200, { "Content-Type": "text/javascript", "Cache-Control": "no-store" }, f.body)
             : send(req, res, 404, { "Cache-Control": "no-store" }, "");
  }
  if (url.pathname === "/logout") {
    // No WWW-Authenticate, so no new prompt; Clear-Site-Data drops cached pages, storage and (in
    // Chromium browsers) the remembered sign-in.
    return send(req, res, 401, { "Clear-Site-Data": '"cache", "cookies", "storage"', "Cache-Control": "no-store",
                                 "Content-Type": "text/html; charset=utf-8" },
      "<!doctype html><meta charset=utf-8><title>Signed out</title><p style='font:16px system-ui;margin:3rem'>" +
      "Signed out. Close every window of this browser before you leave the computer.");
  }

  const who = clientOf(req), now = Date.now();
  if (blocked(who, now)) return send(req, res, 429, { "Retry-After": "900", "Cache-Control": "no-store" }, "Too many sign-in attempts. Try again in 15 minutes.");
  const user = signedIn(req.headers.authorization);
  if (!user) {
    if (req.headers.authorization) failed(who, now);
    const contact = process.env.SITE_CONTACT ? ` For access, ask ${process.env.SITE_CONTACT}.` : "";
    return send(req, res, 401, { "WWW-Authenticate": 'Basic realm="Food Inspection Record: student analysis for City staff", charset="UTF-8"',
                                 "Cache-Control": "no-store", "Content-Type": "text/plain; charset=utf-8" },
      `Sign in with your City staff sign-in.${contact}`);
  }
  FAILS.delete(who);

  if (url.pathname === "/geocode") {
    const q = (url.searchParams.get("q") || "").trim().slice(0, 200);
    const hit = q ? await cachedGeocode(q) : null;
    console.log(`access user=${user} geocode`);
    return send(req, res, hit ? 200 : 404, { "Content-Type": "application/json", "Cache-Control": "no-store" },
      JSON.stringify(hit || { error: "not found" }));
  }

  const rel = normalize(decodeURIComponent(url.pathname)).replace(/^([/\\])+/, "");
  let path = join(ROOT, rel);
  if (!path.startsWith(ROOT + sep) && path !== ROOT) return send(req, res, 400, {}, "");
  let f = await load(path);
  if (!f) {
    // A missing data file is a 404; any other path is a page of the app.
    if (url.pathname.startsWith("/data/") || extname(url.pathname)) return send(req, res, 404, { "Cache-Control": "no-store" }, "Not found");
    path = join(ROOT, "index.html");
    f = await load(path);
    if (!f) return send(req, res, 404, {}, "Not found");
  }
  if (url.pathname.startsWith("/data/")) console.log(`access user=${user} ${url.pathname}`);
  const ext = extname(path);
  const headers = {
    "Content-Type": TYPES[ext] || "application/octet-stream",
    // Hashed assets hold no data. Everything else (the page and every data file) is never stored, so
    // nothing real stays on a shared City computer.
    "Cache-Control": url.pathname.startsWith("/assets/") ? "private, max-age=31536000, immutable" : "no-store",
    ETag: f.etag,
  };
  if (req.headers["if-none-match"] === f.etag) return send(req, res, 304, headers, undefined);
  let body = f.body;
  if (f.gz && /\bgzip\b/.test(req.headers["accept-encoding"] || "")) {
    body = f.gz;
    headers["Content-Encoding"] = "gzip";
    headers.Vary = "Accept-Encoding";
  }
  send(req, res, 200, headers, body);
}
