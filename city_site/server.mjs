// The City staff site: the built food-dashboard with the real export, behind a sign-in.
// Node built-ins only. publish_city_site.py copies this file into the private deploy repository.
//
// Environment (Render: the service's Environment page; never in any repository):
//   SITE_USERS     one sign-in per person: "ana:<token>,ben:<token>" (each token 16+ characters; make one with
//                  python -c "import secrets; print(secrets.token_urlsafe(24))"). Remove a person's entry the day
//                  they leave: the change restarts the service, which signs everyone out, and that person cannot
//                  sign in again. Every data request is logged with the user name, so Render's log is an access log.
//   SITE_PASSWORD  the operator's own older sign-in, 16+ characters, never given to anyone: City staff each
//                  get a SITE_USERS id. Remove it once the operator's own SITE_USERS id works; while it is set
//                  alongside SITE_USERS the server logs a warning at startup.
//   SITE_USER      the SITE_PASSWORD sign-in's user name (default "city")
//   SITE_OPERATORS the ids that see the named list before the City's request and TRUST answer are on record
//                  (meta.access_approved), comma-separated. Unset: the SITE_PASSWORD sign-in, but only while it
//                  is the only sign-in (no SITE_USERS); once personal sign-ins exist, name the operators here.
//   SITE_CONTACT   who to ask for access, shown on the sign-in page (for example "Jane Doe, jane@example.org")
//   PORT           set by Render
// For the tests only (leave them unset on Render):
//   SESSION_IDLE_MS, SESSION_MAX_MS   the session limits (default 30 minutes idle, 10 hours in all)
//   GEOCODE_UPSTREAM                  a stand-in for both geocoders; GEOCODE_FAIL_MS: how long a miss is kept
//
// Sign-in is a form at /login. It starts a session kept in this process's memory, named by a random id
// in an HttpOnly, Secure, SameSite=Strict cookie; it ends after 30 idle minutes, after 10 hours, or at
// /logout, which also clears the site's cache and storage from the browser. A sign-in clears the site's
// storage too, so the staff notice opens again for the next person on a shared computer.
//
// What it does besides serving files: refuses to start with a weak password; slows password guessing
// (10 failures per address and user name per 15 minutes, then 429; past 300 failures in all, every
// sign-in answer waits 2 seconds, one at a time per address and at most 16 at once, the rest queued);
// shows the named list only to operators until the City has asked for it; closes the site (503) once
// the export is not the staff copy or its
// sunset date has passed; rejects a path that could be read two ways; serves the service worker before
// sign-in so a build that removes it reaches every browser; never lets data be cached on a shared
// computer (no-store); sets security headers on every response and collects CSP reports at /csp-report;
// logs CSV downloads and prints (/audit); /geocode looks up an address (OpenStreetMap, then the US
// Census), cached and held to Nominatim's usage policy.
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, posix, sep } from "node:path";
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { gzipSync } from "node:zlib";

const ROOT = join(import.meta.dirname, "dist");
const MIN_SECRET = 16;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".geojson": "application/geo+json", ".webmanifest": "application/manifest+json",
  ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2", ".txt": "text/plain",
  ".csv": "text/csv; charset=utf-8",
};
const COMPRESS = new Set([".html", ".js", ".css", ".json", ".geojson", ".svg", ".webmanifest", ".txt", ".csv"]);

// Report-only: it blocks nothing, and says what an enforced policy would block. The Google sources are
// those of Google's Maps JavaScript API CSP guide (developers.google.com/maps/documentation/javascript/
// content-security-policy), so enforcing it later would not break the map.
const CSP_REPORT_ONLY = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-eval' blob: https://*.googleapis.com https://*.gstatic.com https://*.google.com " +
    "https://*.ggpht.com https://*.googleusercontent.com",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  "font-src 'self' https://fonts.gstatic.com",
  "img-src 'self' data: blob: https://*.googleapis.com https://*.gstatic.com https://*.google.com https://*.ggpht.com " +
    "https://*.googleusercontent.com",
  "frame-src https://*.google.com",
  "connect-src 'self' https://*.googleapis.com https://*.google.com https://*.gstatic.com data: blob:",
  "worker-src 'self' blob:",
  "frame-ancestors 'none'", "base-uri 'none'", "form-action 'self'", "object-src 'none'",
  "report-uri /csp-report",
].join("; ");
const SECURITY = {
  "Strict-Transport-Security": "max-age=31536000",
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "X-Robots-Tag": "noindex, nofollow",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Content-Security-Policy-Report-Only": CSP_REPORT_ONLY,
};
const NO_STORE = { "Cache-Control": "no-store", "Content-Type": "text/plain; charset=utf-8" };

// ── the server's own pages (sign-in, closed) ────────────────────────────────────────────────
// Self-contained: one inline style, allowed by its hash in an enforced policy, and nothing else.
const STYLE =
  "body{margin:0;background:#fbf9f5;color:#1d1d1b;font:16px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif}" +
  "main{max-width:24rem;margin:3rem auto;padding:0 1rem}h1{font-size:1.3rem;margin:0}" +
  ".sub{margin:.25rem 0 1.5rem;color:#555}label{display:block;margin:1rem 0 .25rem;font-weight:600}" +
  "input{box-sizing:border-box;width:100%;padding:.55rem;font:inherit;border:1px solid #8a8a86;border-radius:4px;background:#fff}" +
  "button{margin-top:1.5rem;padding:.6rem 1.4rem;font:inherit;font-weight:600;border:0;border-radius:4px;" +
  "background:#1d1d1b;color:#fff;cursor:pointer}.note{margin:0 0 1rem;padding:.6rem .8rem;border-left:4px solid #1d1d1b;" +
  "background:#fff}.bad{border-color:#b3261e}.contact{margin-top:2rem;color:#555}.log{margin-top:1.5rem;font-size:.85rem;color:#555}";
const PAGE_CSP = `default-src 'none'; style-src 'sha256-${createHash("sha256").update(STYLE).digest("base64")}'; ` +
  "form-action 'self'; frame-ancestors 'none'; base-uri 'none'";
const TITLE = "Food Inspection Record: student analysis for City staff";
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

function sendPage(req, res, status, title, body, headers = {}) {
  send(req, res, status, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store",
                           "Content-Security-Policy": PAGE_CSP, ...headers },
    `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">` +
    `<meta name="robots" content="noindex, nofollow"><title>${esc(title)}</title><style>${STYLE}</style><main>${body}</main></html>`);
}

// What the site records, said where a record is first made: the sign-in page (and its 401 and 429 answers)
// and the Withheld page, which is all a sign-in sees before the City's request is on record.
// Every line of it is written by login (a sign-in, and each sign-in refused, for a wrong id or token or for too
// many tries), logout, serveFile, geocodeRoute and audit.
const LOG_NOTICE = "This site keeps a log, under your sign-in id, of each sign-in and sign-out with your network " +
  "address; of each sign-in that is refused, with the address (and the id typed, only when it is one of this " +
  "site's ids); of each place or list opened, downloaded or printed; and of each address lookup (not what you " +
  "typed). The site's operator, and anyone with access to its hosting account, can read that log. During a " +
  "pilot it may be used, by sign-in id, in the pilot's analysis.";
const logNotice = () => `<p class="log">${esc(LOG_NOTICE)}</p>`;
// The site's one disclaimer, word for word (food-dashboard/src/site.js STUDENT_NOTE): it names the City too.
const STUDENT_NOTE = "Independent student project, not affiliated with or endorsed by the City of San Diego or the County of San Diego.";

// The sign-ins are ids and tokens this site issues, never a City account: the page says so, so that no one
// types a City network password into a student-run server.
function loginForm({ next = "/", user = "", notice = "", bad = false } = {}) {
  const contact = process.env.SITE_CONTACT
    ? `<p class="contact">For access, ask ${esc(process.env.SITE_CONTACT)}.</p>`
    : '<p class="contact">No sign-in id yet? Ask the person who sent you this link. Do not try your City account.</p>';
  return "<h1>Food Inspection Record</h1><p class=\"sub\">A student analysis offered to City of San Diego staff, not a " +
    `City site. ${STUDENT_NOTE}</p><p class="sub">Sign in with the ` +
    "sign-in id (such as u07) and access token this site's operator sent you. This is not your City network account: " +
    "never enter your City user name or password here.</p>" +
    (notice ? `<p class="note${bad ? " bad" : ""}" role="${bad ? "alert" : "status"}">${esc(notice)}</p>` : "") +
    `<form method="post" action="/login"><input type="hidden" name="next" value="${esc(next)}">` +
    `<label for="user">Sign-in id</label><input id="user" name="user" autocomplete="username" autocapitalize="none" ` +
    `spellcheck="false" required value="${esc(user)}"${user ? "" : " autofocus"}>` +
    `<label for="password">Access token</label><input id="password" name="password" type="password" ` +
    `autocomplete="current-password" required${user ? " autofocus" : ""}>` +
    "<button type=\"submit\">Sign in</button></form>" + contact + logNotice();
}

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
// Who may see the named list before the City has asked for it: SITE_OPERATORS (ids, comma-separated). The
// SITE_PASSWORD sign-in (user SITE_USER, default "city") is the operator's own older sign-in, never given to
// anyone. With SITE_OPERATORS unset it is an operator only while it is the only sign-in (no SITE_USERS); once
// personal sign-ins exist, the operators are the ids SITE_OPERATORS names.
const OWN = process.env.SITE_PASSWORD ? process.env.SITE_USER || "city" : null;
const PERSONAL = Boolean((process.env.SITE_USERS || "").trim());
const OPERATORS = new Set((process.env.SITE_OPERATORS ?? (OWN && !PERSONAL ? OWN : ""))
  .split(",").map((u) => u.trim()).filter(Boolean));
if (!OPERATORS.size) console.warn("no SITE_OPERATORS: until the City's request is on record, nobody sees the named list");
if (OWN && PERSONAL) {
  console.warn(`SITE_PASSWORD is set alongside SITE_USERS: it is the operator's own older sign-in (user ${OWN}), never ` +
    `given to anyone, and ${OPERATORS.has(OWN) ? "SITE_OPERATORS names it an operator" : "it is not an operator"}. ` +
    "Remove SITE_PASSWORD once your own SITE_USERS id works.");
}
const UNKNOWN_OPERATORS = [...OPERATORS].filter((u) => !USERS.has(u));
if (UNKNOWN_OPERATORS.length) console.warn(`SITE_OPERATORS names ${UNKNOWN_OPERATORS.join(", ")}, which no sign-in has`);
if (WEAK.length) {
  console.error(`refusing to start: the sign-in for ${WEAK.join(", ")} is shorter than ${MIN_SECRET} characters. ` +
    'Make one with: python -c "import secrets; print(secrets.token_urlsafe(24))"');
  process.exit(1);
}
if (!USERS.size) console.warn("no sign-in is configured (SITE_USERS or SITE_PASSWORD): nobody can sign in");

/** True when `password` is `user`'s sign-in. The same work whether or not the user exists. */
function credentialsMatch(user, password) {
  const want = USERS.get(user);
  return timingSafeEqual(digest(`${user}:${password}`), want ?? NOBODY) && want !== undefined && password.length >= MIN_SECRET;
}

// Text a client sent, safe for one log line: no control, line-separator or bidi-override characters.
const clean = (s, max = 200) => String(s).replace(/[\p{Cc}\p{Zl}\p{Zp}\p{Bidi_Control}]/gu, "").slice(0, max);

// A POST another site made the browser send. SameSite=Strict already keeps the session cookie off it;
// this also stops another site from signing a browser in to an account of its choosing.
const crossSite = (req) => {
  if (["cross-site", "same-site"].includes(req.headers["sec-fetch-site"])) return true;
  const origin = req.headers.origin;
  if (origin === undefined) return false;
  try {
    return origin === "null" || new URL(origin).host !== req.headers.host;
  } catch {
    return true;
  }
};

// ── sessions ────────────────────────────────────────────────────────────────────────────
// Held in this process's memory only, never on disk: a restart or redeploy (and, on Render's free plan,
// the instance going to sleep) signs everyone out. That is acceptable: signing in again takes a moment.
const SESSIONS = new Map();                       // id -> {user, created, last}, oldest first
const IDLE_MS = Number(process.env.SESSION_IDLE_MS) || 30 * 60e3;
const MAX_MS = Number(process.env.SESSION_MAX_MS) || 10 * 3600e3;
const MAX_SESSIONS = 5000;
const COOKIE = "HttpOnly; Secure; SameSite=Strict; Path=/";
const COOKIE_NAME = "__Host-s";                   // the __Host- prefix: this host only, Secure, Path=/, no Domain

function cookie(req, name) {
  for (const part of (req.headers.cookie || "").split(";")) {
    const i = part.indexOf("=");
    if (i > 0 && part.slice(0, i).trim() === name) return part.slice(i + 1).trim();
  }
  return null;
}

const current = (s, now) => now - s.last <= IDLE_MS && now - s.created <= MAX_MS;

function startSession(user, now) {
  const id = randomBytes(32).toString("base64url");
  SESSIONS.set(id, { user, created: now, last: now });
  while (SESSIONS.size > MAX_SESSIONS) SESSIONS.delete(SESSIONS.keys().next().value);
  return id;
}

/** The request's session, marked as used now; or null. */
function session(req, now) {
  const id = cookie(req, COOKIE_NAME);
  const s = id ? SESSIONS.get(id) : undefined;
  if (!s) return null;
  if (!current(s, now)) {
    SESSIONS.delete(id);
    return null;
  }
  s.last = now;
  return s;
}

/** A path on this site to go to after signing in: never another origin ("//host", "/\host", "https:"). */
function safeNext(next) {
  if (typeof next !== "string" || next.length > 2000 || !next.startsWith("/") || next.startsWith("//")
      || /[\\\p{Cc}\s]/u.test(next)) return "/";
  try {
    const u = new URL(next, "https://this.invalid");
    // Check what the browser will follow, after dot segments resolve: "/.//evil.example" becomes
    // "//evil.example", which is another site.
    if (u.origin !== "https://this.invalid" || /^[/\\]{2}/.test(u.pathname) || u.pathname === "/login" || u.pathname === "/logout") return "/";
    return u.pathname + u.search;
  } catch {
    return "/";
  }
}

// ── slowing password guessing ───────────────────────────────────────────────────────────
// The client's address: Render's edge (Cloudflare) sets CF-Connecting-IP; the service port is not
// reachable from the internet directly. X-Forwarded-For is not used: a client can write anything into it.
const clientOf = (req) => req.headers["cf-connecting-ip"] || req.socket.remoteAddress || "unknown";

// Failures are counted per address AND user name, so a City office sharing one outbound address is not
// locked out by one person's typos, and a lockout never refuses anyone else's correct sign-in.
const FAILS = new Map();                          // `${ip}|${user}` -> {n, since}, oldest window first
const WINDOW_MS = 15 * 60e3, MAX_FAILS = 10, MAX_FAIL_KEYS = 10_000;
// Against guessing spread over many addresses and names: past 300 failures in all in 15 minutes, every
// sign-in answer (right or wrong, so a quick answer does not give a right password away) waits 2 s.
const GLOBAL_FAILS = 300, SLOW_MS = 2000;
// ...and at most MAX_CHECKING of those slowed answers at once: parallel requests cannot get round the wait.
// Past the budget, slowed checks run one at a time per address (so one client cannot occupy them) and at
// most MAX_CHECKING at once in all; the rest wait their turn, up to MAX_WAITING, instead of being refused.
const MAX_CHECKING = 16, MAX_WAITING = 64;
let checking = 0;
const CHECKING_BY_IP = new Set();
const WAITING = [];

async function slowTurn(ip) {
  if (checking >= MAX_CHECKING) {
    if (WAITING.length >= MAX_WAITING) return false;
    await new Promise((r) => WAITING.push(r));
  }
  checking += 1;
  CHECKING_BY_IP.add(ip);
  try {
    await new Promise((r) => setTimeout(r, SLOW_MS));
  } finally {
    checking -= 1;
    CHECKING_BY_IP.delete(ip);
    WAITING.shift()?.();
  }
  return true;
}
const FAILS_BY_MINUTE = new Map();                // minute -> failures in it

function blocked(key, now) {
  const f = FAILS.get(key);
  return Boolean(f && now - f.since < WINDOW_MS && f.n >= MAX_FAILS);
}

function failed(key, now) {
  const f = FAILS.get(key);
  if (f && now - f.since < WINDOW_MS) f.n += 1;
  else {
    FAILS.delete(key);                            // re-inserted at the end: the map stays oldest first
    FAILS.set(key, { n: 1, since: now });
  }
  if (FAILS.size > MAX_FAIL_KEYS) {                // room is made from keys that are not locked out, oldest first
    for (const k of FAILS.keys()) {
      if (FAILS.size <= MAX_FAIL_KEYS) break;
      if (k !== key && !blocked(k, now)) FAILS.delete(k);
    }
  }
  const minute = Math.floor(now / 60e3);
  FAILS_BY_MINUTE.set(minute, (FAILS_BY_MINUTE.get(minute) || 0) + 1);
}

function recentFailures(now) {
  const minute = Math.floor(now / 60e3);
  let n = 0;
  for (const [m, count] of FAILS_BY_MINUTE) {
    if (m <= minute - WINDOW_MS / 60e3) FAILS_BY_MINUTE.delete(m);
    else n += count;
  }
  return n;
}

/** A fixed-window rate limit: call per event; false once `key` has had more than `limit` in the window. */
function rateLimit(limit, windowMs, maxKeys = 10_000) {
  const seen = new Map();
  return (key, now) => {
    let e = seen.get(key);
    if (!e || now - e.since >= windowMs) {
      seen.delete(key);
      seen.set(key, (e = { n: 0, since: now }));
      while (seen.size > maxKeys) seen.delete(seen.keys().next().value);
    }
    e.n += 1;
    return e.n <= limit;
  };
}

setInterval(() => {                               // forget what has expired
  const now = Date.now();
  for (const [id, s] of SESSIONS) if (!current(s, now)) SESSIONS.delete(id);
  for (const [key, f] of FAILS) if (now - f.since >= WINDOW_MS) FAILS.delete(key);
  recentFailures(now);
}, 60e3).unref();

// ── address lookup ──────────────────────────────────────────────────────────────────────
// OpenStreetMap's Nominatim, held to San Diego County, then the US Census geocoder. Nominatim's usage
// policy: identify the app, at most one request a second, cache results. Answers {lat, lon, label,
// source}, or null. A miss is kept for 10 minutes only (a geocoder may have been down); identical
// lookups in flight share one; at most 2 Census lookups run at once, and a third answers 503.
const COUNTY_BOX = "-117.61,33.51,-116.08,32.53";
const UA = "sdfood-city-staff-site (https://github.com/bushesarebetter/sdfood)";
const OSM = process.env.GEOCODE_UPSTREAM || "https://nominatim.openstreetmap.org";
const CENSUS = process.env.GEOCODE_UPSTREAM || "https://geocoding.geo.census.gov";
const MISS_MS = Number(process.env.GEOCODE_FAIL_MS) || 10 * 60e3;
const CENSUS_AT_ONCE = 2;
const GEO = new Map();                            // key -> {hit, at}, oldest first
const PENDING = new Map();                        // key -> the lookup in flight
let nextNominatim = 0, censusRunning = 0;

class Busy extends Error {}

async function nominatim(url) {
  const now = Date.now(), at = Math.max(now, nextNominatim);
  if (at - now > 5000) return null;                  // a queue longer than 5 s: skip to the Census
  nextNominatim = at + 1100;
  await new Promise((r) => setTimeout(r, at - now));
  return fetch(url, { headers: { "User-Agent": UA }, signal: AbortSignal.timeout(5000) });
}

async function geocode(q) {
  try {
    const r = await nominatim(`${OSM}/search?format=jsonv2&limit=1&countrycodes=us&bounded=1&viewbox=${COUNTY_BOX}&q=${encodeURIComponent(q)}`);
    const [hit] = r?.ok ? await r.json() : [];
    if (hit) return { lat: Number(hit.lat), lon: Number(hit.lon), label: hit.display_name, source: "osm" };
  } catch {}
  if (censusRunning >= CENSUS_AT_ONCE) throw new Busy("the Census geocoder is busy");
  censusRunning += 1;
  try {
    const addr = /\b(ca|california)\b|\d{5}/i.test(q) ? q : `${q}, San Diego County, CA`;
    const r = await fetch(`${CENSUS}/geocoder/locations/onelineaddress?benchmark=Public_AR_Current&format=json&address=${encodeURIComponent(addr)}`,
      { signal: AbortSignal.timeout(5000) });
    const m = r.ok ? (await r.json())?.result?.addressMatches?.[0] : null;
    if (m) return { lat: m.coordinates.y, lon: m.coordinates.x, label: m.matchedAddress, source: "census" };
  } catch {} finally {
    censusRunning -= 1;
  }
  return null;
}

function cachedGeocode(q) {
  const key = q.toLowerCase().replace(/\s+/g, " ");
  const kept = GEO.get(key);
  if (kept && (kept.hit || Date.now() - kept.at < MISS_MS)) return Promise.resolve(kept.hit);
  let p = PENDING.get(key);
  if (!p) {
    p = geocode(q).then((hit) => {
      GEO.delete(key);
      GEO.set(key, { hit, at: Date.now() });
      while (GEO.size > 5000) GEO.delete(GEO.keys().next().value);
      return hit;
    }).finally(() => PENDING.delete(key));
    PENDING.set(key, p);
  }
  return p;
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
    return JSON.parse((await load(join(ROOT, "data", "meta.json")))?.body ?? "{}") ?? {};
  } catch {
    return {};
  }
}

// The date in San Diego (YYYY-MM-DD): a sunset or expiry date ends at midnight Pacific, not UTC.
const PACIFIC = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit" });
const today = () => PACIFIC.format(new Date());

/** Why the site is closed, or null. It closes itself once its export is not the staff copy
 *  (publish_city_site.py writes audience "staff") or the sunset date agreed for it has passed. */
function closedReason(m, day) {
  if (m.audience !== "staff") return 'its export is not the staff copy (meta.json audience is not "staff")';
  if (typeof m.sunset !== "string" || !ISO_DATE.test(m.sunset)) return "its export has no sunset date";
  if (day > m.sunset) return `its sunset date, ${m.sunset}, has passed`;
  return null;
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
    if (!res.headersSent) res.writeHead(bad ? 400 : 500, { "Cache-Control": "no-store" });
    res.end();
  });
}).listen(Number(process.env.PORT) || 10000, "0.0.0.0");

function send(req, res, status, headers, body) {
  if (body != null && status !== 304) headers = { ...headers, "Content-Length": Buffer.byteLength(body) };
  res.writeHead(status, headers);
  res.end(req.method === "HEAD" || status === 304 || body == null ? undefined : body);
}

/** True when the method is one of `methods`; otherwise answers 405. */
function allow(req, res, ...methods) {
  if (methods.includes(req.method)) return true;
  send(req, res, 405, { ...NO_STORE, Allow: methods.join(", ") }, "");
  return false;
}

/** The request body, or null when it is longer than `limit` bytes. */
function readBody(req, limit) {
  if (Number(req.headers["content-length"]) > limit) return Promise.resolve(null);
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", (c) => {
      size += c.length;
      if (size > limit) resolve(null);           // the rest is discarded; the reply closes the connection
      else chunks.push(c);
    });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

const TOO_LARGE = { ...NO_STORE, Connection: "close" };

/** The path, %-decoded exactly once, and the query; null when the path could be read two ways
 *  (an encoded / or \, a backslash, NUL or other control character, "." or ".." segments, "//"). */
function target(url) {
  const q = url.indexOf("?");
  const raw = q < 0 ? url : url.slice(0, q);
  if (!raw.startsWith("/") || /%2f|%5c/i.test(raw)) return null;
  let path;
  try {
    path = decodeURIComponent(raw);
  } catch {
    return null;
  }
  if (/[\\\x00-\x1f\x7f]/.test(path) || path !== posix.normalize(path)) return null;
  return { path, query: new URLSearchParams(q < 0 ? "" : url.slice(q + 1)) };
}

async function handle(req, res) {
  const t = target(req.url);
  if (!t) return send(req, res, 400, NO_STORE, "Bad request");
  const { path, query } = t;
  const now = Date.now();

  // Open, carrying no data: the health check, the service worker (so a build that removes it reaches
  // browsers that are not signed in), signing in and out, and CSP reports.
  if (path === "/healthz") return allow(req, res, "GET", "HEAD") && healthz(req, res);
  if (path === "/sw.js") return allow(req, res, "GET", "HEAD") && serviceWorker(req, res);
  if (path === "/login") {
    if (!allow(req, res, "GET", "HEAD", "POST")) return;
    return req.method === "POST" ? login(req, res) : loginPage(req, res, query, now);
  }
  if (path === "/logout") return allow(req, res, "GET", "POST") && logout(req, res);
  if (path === "/csp-report") return allow(req, res, "POST") && cspReport(req, res, now);

  const m = await meta();
  const why = closedReason(m, today());
  if (why) return sendPage(req, res, 503, "Closed", `<h1>Food Inspection Record</h1><p>This site is closed: ${esc(why)}.</p>`);

  const s = session(req, now);
  if (!s) {
    if ((req.method === "GET" || req.method === "HEAD") && /\btext\/html\b/i.test(req.headers.accept || "")) {
      return send(req, res, 303, { "Cache-Control": "no-store", Location: `/login?next=${encodeURIComponent(req.url)}` }, "");
    }
    return send(req, res, 401, NO_STORE, "Sign in first: /login");
  }

  // Until a City request and a TRUST Ordinance determination are on record (meta.access_approved), the
  // named list is shown only to the site's operators (SITE_OPERATORS), who build and check it; a site
  // sign-in issued early sees why, not the list (docs/STAFF_SITE.md, "Who may use it"). Only the value the
  // publisher writes, true, opens it: "yes" or any other truthy value does not.
  const withheld = m.access_approved !== true && !OPERATORS.has(s.user);
  if (withheld && path === "/data/meta.json") {           // the app can say why, but no per-place field leaves
    console.log(`withheld user=${s.user} ${path}`);
    const { corrections, ...rest } = m;                    // eslint-disable-line no-unused-vars
    return send(req, res, 200, { "Content-Type": "application/json", "Cache-Control": "no-store" },
      JSON.stringify({ ...rest, corrections: [] }));
  }
  if (withheld && !path.startsWith("/assets/")) {
    console.log(`withheld user=${s.user} ${path}`);
    return sendPage(req, res, 503, "Withheld", "<h1>Food Inspection Record</h1><p>The named list is withheld until the City " +
      "has recorded a request for this site and a TRUST Ordinance determination.</p>" +
      '<form method="post" action="/logout"><button type="submit">Sign out</button></form>' + logNotice());
  }
  if (path === "/audit") return allow(req, res, "POST") && audit(req, res, s.user);
  if (!allow(req, res, "GET", "HEAD")) return;
  if (path === "/geocode") return geocodeRoute(req, res, query, s.user);
  return serveFile(req, res, path, s.user);
}

/** The monitor's summary as the publisher shipped it (meta.monitor), or null for an older export. An alert
 *  is any alert sentence, or a monitor that did not run for this list (status "failed"). */
function monitorOf(m) {
  const mon = m.monitor && typeof m.monitor === "object" && !Array.isArray(m.monitor) ? m.monitor : null;
  const alert = Boolean(mon && (mon.status === "failed" || (Array.isArray(mon.alerts) && mon.alerts.length > 0)));
  return { status: typeof mon?.status === "string" ? mon.status : null, alert };
}

// Open and carrying no data: which export, rule and server are live, and yes/no signals for the daily check
// (city_site/watch.yml). The drift note and the monitor's alerts are said as booleans only; their text stays
// behind the sign-in.
async function healthz(req, res) {
  const m = await meta();
  const day = today();
  const mon = monitorOf(m);
  return send(req, res, 200, { "Content-Type": "application/json", "Cache-Control": "no-store" }, JSON.stringify({
    ok: true, run: m.run ?? null, inspections_through: m.inspections_through ?? null, expires: m.expires ?? null,
    stale: Boolean(m.expires && day > m.expires), source: process.env.RENDER_GIT_COMMIT ?? null, server: SERVER_BUILD,
    sunset: m.sunset ?? null, closed: closedReason(m, day), refit_needed: !!m.drift?.refit_needed,
    drift_note: typeof m.drift?.note === "string" && m.drift.note.trim() !== "",
    monitor: mon.status, monitor_alert: mon.alert,
    rule_version: m.frozen?.version ?? null, access_approved: m.access_approved === true,
    named_list: m.access_approved === true ? "signed-in staff" : "operators only",
  }));
}

async function serviceWorker(req, res) {
  const f = await load(join(ROOT, "sw.js"));
  return f ? send(req, res, 200, { "Content-Type": "text/javascript", "Cache-Control": "no-store" }, f.body)
           : send(req, res, 404, { "Cache-Control": "no-store" }, "");
}

function loginPage(req, res, query, now) {
  const next = safeNext(query.get("next") ?? "/");
  if (query.get("out") !== "1" && session(req, now)) return send(req, res, 303, { "Cache-Control": "no-store", Location: next }, "");
  const notice = query.get("out") === "1" ? "You are signed out. Close every window of this browser before you leave the computer." : "";
  return sendPage(req, res, 200, TITLE, loginForm({ next, notice }));
}

async function login(req, res) {
  if (crossSite(req)) return send(req, res, 403, NO_STORE, "Sign in from this site's own sign-in page.");
  if (!/^application\/x-www-form-urlencoded\b/i.test(req.headers["content-type"] || "")) {
    return send(req, res, 415, NO_STORE, "Expected a form (application/x-www-form-urlencoded).");
  }
  const body = await readBody(req, 4096);
  if (body === null) return send(req, res, 413, TOO_LARGE, "Too large.");
  const form = new URLSearchParams(body.toString("utf8"));
  const user = (form.get("user") || "").trim().slice(0, 100), password = form.get("password") || "";
  const next = safeNext(form.get("next") ?? "/");
  const ip = clientOf(req), key = `${ip}|${user}`;
  const now = Date.now();
  // Every refused sign-in is logged, as LOG_NOTICE says. The name typed is logged only when it is one of this
  // site's ids: a City account name or an email typed here by mistake never reaches the log.
  const typed = USERS.has(user) ? JSON.stringify(clean(user, 100)) : "<not an id>";
  if (blocked(key, now)) {
    console.warn(`sign-in refused user=${typed} from ${clean(ip, 64)}: too many wrong sign-ins`);
    return sendPage(req, res, 429, TITLE, loginForm({ next, user, bad: true,
      notice: "Too many wrong sign-ins for this id from here. Try again in 15 minutes." }), { "Retry-After": "900" });
  }
  const over = recentFailures(now) > GLOBAL_FAILS;
  const busy = () => {
    console.warn(`sign-in refused user=${typed} from ${clean(ip, 64)}: too many at once`);
    return sendPage(req, res, 429, TITLE, loginForm({ next, user, bad: true,
      notice: "Too many sign-ins at once from here. Try again in a few seconds." }), { "Retry-After": "5" });
  };
  if (over && CHECKING_BY_IP.has(ip)) return busy();       // one slowed check at a time per address
  const ok = credentialsMatch(user, password);
  if (over && !(await slowTurn(ip))) return busy();
  if (!ok) {
    failed(key, now);
    console.warn(`sign-in failed user=${typed} from ${clean(ip, 64)}`);
    return sendPage(req, res, 401, TITLE, loginForm({ next, user, bad: true,
      notice: "The sign-in id or access token is not right. Try again." }));
  }
  FAILS.delete(key);
  const old = cookie(req, COOKIE_NAME);
  if (old) SESSIONS.delete(old);                  // a new id at every sign-in: none can be planted beforehand
  const id = startSession(user, Date.now());
  console.log(`sign-in user=${user} from ${clean(ip, 64)}`);
  // Each sign-in starts the site afresh in this browser: the last person's settings and the staff notice's
  // "I have read this" mark (sessionStorage) go, so the notice opens again for whoever signs in, even in a
  // tab whose session timed out. "storage" only: the new session cookie is set by this same response.
  return send(req, res, 303, {
    "Cache-Control": "no-store",
    "Clear-Site-Data": '"storage"',
    "Set-Cookie": `${COOKIE_NAME}=${id}; ${COOKIE}`,
    Location: next,
  }, "");
}

function logoutPage(req, res) {
  return sendPage(req, res, 200, TITLE, '<h1>Food Inspection Record</h1><form method="post" action="/logout">' +
    '<p class="sub">Sign out of the staff site on this browser?</p><button type="submit">Sign out</button></form>');
}

function logout(req, res) {
  if (req.method !== "POST") return logoutPage(req, res);
  if (crossSite(req)) return send(req, res, 403, NO_STORE, "Sign out from this site's own page.");
  const id = cookie(req, COOKIE_NAME);
  const s = id ? SESSIONS.get(id) : undefined;
  if (id) SESSIONS.delete(id);
  if (s) console.log(`sign-out user=${s.user} from ${clean(clientOf(req), 64)}`);
  // Cookies are cleared by name (below), not by Clear-Site-Data, which Firefox does not apply to them all.
  return send(req, res, 303, {
    "Cache-Control": "no-store",
    "Set-Cookie": [`${COOKIE_NAME}=; Max-Age=0; ${COOKIE}`, "s=; Max-Age=0; Path=/; HttpOnly; Secure; SameSite=Strict"],
    "Clear-Site-Data": '"cache", "storage"',
    Location: "/login?out=1",
  }, "");
}

// CSP violation reports: open (a browser sends them without the cookie), small, and limited.
const REPORTS_PER_CLIENT = rateLimit(20, 60e3), REPORTS_IN_ALL = rateLimit(300, 60e3);

async function cspReport(req, res, now) {
  if (!REPORTS_PER_CLIENT(clientOf(req), now) || !REPORTS_IN_ALL("all", now)) {
    return send(req, res, 429, { ...NO_STORE, "Retry-After": "60" }, "");
  }
  const body = await readBody(req, 8192);
  if (body === null) return send(req, res, 413, TOO_LARGE, "Too large.");
  let r;
  try {
    r = JSON.parse(body.toString("utf8"));
  } catch {
    return send(req, res, 400, NO_STORE, "Expected a CSP report.");
  }
  // report-uri sends {"csp-report": {...}}; the Reporting API sends [{type: "csp-violation", body: {...}}].
  const v = r?.["csp-report"] ?? (Array.isArray(r) ? r[0]?.body : null);
  if (!v || typeof v !== "object") return send(req, res, 400, NO_STORE, "Expected a CSP report.");
  const word = (x) => clean(x ?? "unknown", 300).replace(/\s+/g, "") || "unknown";
  console.log(`csp-report directive=${word(v["violated-directive"] ?? v["effective-directive"] ?? v.effectiveDirective)} ` +
              `blocked=${word(v["blocked-uri"] ?? v.blockedURL)}`);
  return send(req, res, 204, { "Cache-Control": "no-store" }, null);
}

// What staff take away from the site, one line each in the access log. The site sends it with
// navigator.sendBeacon when someone downloads a CSV or prints.
const AUDIT_EVENTS = new Set(["csv", "print"]);
const AUDIT_FIELDS = new Set(["event", "rows", "name"]);

function auditProblem(a) {
  if (!a || typeof a !== "object" || Array.isArray(a)) return "expected {event, rows?, name?}";
  if (Object.keys(a).some((k) => !AUDIT_FIELDS.has(k))) return "unknown field: expected {event, rows?, name?}";
  if (!AUDIT_EVENTS.has(a.event)) return "event must be \"csv\" or \"print\"";
  if (a.rows !== undefined && !(Number.isSafeInteger(a.rows) && a.rows >= 0)) return "rows must be a whole number";
  if (a.name !== undefined && typeof a.name !== "string") return "name must be text";
  if (a.name !== undefined && [...clean(a.name, Infinity)].length > 120) return "name is longer than 120 characters";
  return null;
}

async function audit(req, res, user) {
  if (crossSite(req)) return send(req, res, 403, NO_STORE, "Refused.");
  const body = await readBody(req, 2048);
  if (body === null) return send(req, res, 413, TOO_LARGE, "Too large.");
  let a;
  try {
    a = JSON.parse(body.toString("utf8"));
  } catch {
    return send(req, res, 400, NO_STORE, "Expected JSON.");
  }
  const problem = auditProblem(a);
  if (problem) return send(req, res, 400, NO_STORE, problem);
  console.log(`audit user=${user} event=${a.event} rows=${a.rows ?? "-"} name=${a.name === undefined ? "-" : JSON.stringify(clean(a.name, Infinity))}`);
  return send(req, res, 204, { "Cache-Control": "no-store" }, null);
}

async function geocodeRoute(req, res, query, user) {
  const q = (query.get("q") || "").trim().slice(0, 200);
  console.log(`access user=${user} geocode`);
  let hit = null;
  if (q) {
    try {
      hit = await cachedGeocode(q);
    } catch (e) {
      if (!(e instanceof Busy)) throw e;
      return send(req, res, 503, { "Content-Type": "application/json", "Cache-Control": "no-store", "Retry-After": "5" },
        JSON.stringify({ error: "busy: try again in a few seconds" }));
    }
  }
  return send(req, res, hit ? 200 : 404, { "Content-Type": "application/json", "Cache-Control": "no-store" },
    JSON.stringify(hit || { error: "not found" }));
}

// Every decision here (data or asset, logged or not, cached or not) is made on the decoded path.
async function serveFile(req, res, path, user) {
  const isData = path.toLowerCase().startsWith("/data/");
  let file = join(ROOT, path);
  if (!file.startsWith(ROOT + sep) && file !== ROOT) return send(req, res, 400, NO_STORE, "Bad request");
  let f = await load(file), page = false;
  if (!f) {
    // A missing data file is a 404; any other path is a page of the app.
    if (isData || extname(path)) return send(req, res, 404, NO_STORE, "Not found");
    file = join(ROOT, "index.html");
    f = await load(file);
    page = true;
    if (!f) return send(req, res, 404, NO_STORE, "Not found");
  }
  if (isData) console.log(`access user=${user} ${path}`);
  const headers = {
    "Content-Type": TYPES[extname(file)] || "application/octet-stream",
    // Hashed assets hold no data. Everything else (the page and every data file) is never stored, so
    // nothing real stays on a shared City computer.
    "Cache-Control": path.startsWith("/assets/") && !page ? "private, max-age=31536000, immutable" : "no-store",
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
