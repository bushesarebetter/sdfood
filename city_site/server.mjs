// The City staff site: the built food-dashboard with the real export, behind a password.
// Node built-ins only. Env: SITE_PASSWORD (required), SITE_USER (default "city"), PORT.
// publish_city_site.py copies this file into the private deploy repository.
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize, sep } from "node:path";
import { timingSafeEqual } from "node:crypto";
import { gzipSync } from "node:zlib";

const ROOT = join(import.meta.dirname, "dist");
const USER = process.env.SITE_USER || "city";
const PASSWORD = process.env.SITE_PASSWORD || "";
const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".geojson": "application/geo+json", ".webmanifest": "application/manifest+json",
  ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2", ".txt": "text/plain",
};
// Address lookup without a Google key: OpenStreetMap's Nominatim, held to San Diego County, then
// the US Census geocoder. Answers {lat, lon, label}, or 404 when neither finds the address.
const COUNTY_BOX = "-117.61,33.51,-116.08,32.53";
const UA = "sdfood-city-staff-site (https://github.com/bushesarebetter/sdfood)";
async function geocode(q) {
  try {
    const u = `https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&countrycodes=us&bounded=1&viewbox=${COUNTY_BOX}&q=${encodeURIComponent(q)}`;
    const [hit] = await (await fetch(u, { headers: { "User-Agent": UA } })).json();
    if (hit) return { lat: Number(hit.lat), lon: Number(hit.lon), label: hit.display_name };
  } catch {}
  try {
    const addr = /\b(ca|california)\b|\d{5}/i.test(q) ? q : `${q}, San Diego County, CA`;
    const u = `https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?benchmark=Public_AR_Current&format=json&address=${encodeURIComponent(addr)}`;
    const m = (await (await fetch(u)).json())?.result?.addressMatches?.[0];
    if (m) return { lat: m.coordinates.y, lon: m.coordinates.x, label: m.matchedAddress };
  } catch {}
  return null;
}

const COMPRESS = new Set([".html", ".js", ".css", ".json", ".geojson", ".svg", ".webmanifest", ".txt"]);

function authorized(header) {
  if (!PASSWORD || !header?.startsWith("Basic ")) return false;
  const given = Buffer.from(Buffer.from(header.slice(6), "base64").toString("utf8"));
  const want = Buffer.from(`${USER}:${PASSWORD}`);
  return given.length === want.length && timingSafeEqual(given, want);
}

async function file(path) {
  try {
    const s = await stat(path);
    return s.isFile() ? path : null;
  } catch {
    return null;
  }
}

createServer(async (req, res) => {
  const url = new URL(req.url, "http://x");
  if (url.pathname === "/healthz") return res.end("ok");
  if (!authorized(req.headers.authorization)) {
    res.writeHead(401, { "WWW-Authenticate": 'Basic realm="San Diego Food Inspection Record", charset="UTF-8"' });
    return res.end(PASSWORD ? "Sign in with the City staff password." : "SITE_PASSWORD is not set.");
  }
  if (url.pathname === "/geocode") {
    const q = (url.searchParams.get("q") || "").trim().slice(0, 200);
    const hit = q ? await geocode(q) : null;
    res.writeHead(hit ? 200 : 404, { "Content-Type": "application/json", "Cache-Control": "private, max-age=86400" });
    return res.end(JSON.stringify(hit || { error: "not found" }));
  }
  const rel = normalize(decodeURIComponent(url.pathname)).replace(/^([/\\])+/, "");
  let path = join(ROOT, rel);
  if (!path.startsWith(ROOT + sep) && path !== ROOT) return res.writeHead(400).end();
  path = await file(path);
  if (!path) {
    // A missing data file is a 404; any other path is a page of the app.
    if (url.pathname.startsWith("/data/") || extname(url.pathname)) return res.writeHead(404).end("Not found");
    path = join(ROOT, "index.html");
  }
  const ext = extname(path);
  let body = await readFile(path);
  const headers = {
    "Content-Type": TYPES[ext] || "application/octet-stream",
    "Cache-Control": url.pathname.startsWith("/assets/") ? "private, max-age=31536000, immutable" : "private, no-cache",
    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Robots-Tag": "noindex, nofollow",
  };
  if (COMPRESS.has(ext) && /\bgzip\b/.test(req.headers["accept-encoding"] || "")) {
    body = gzipSync(body);
    headers["Content-Encoding"] = "gzip";
    headers.Vary = "Accept-Encoding";
  }
  res.writeHead(200, headers).end(body);
}).listen(Number(process.env.PORT) || 10000, "0.0.0.0");
