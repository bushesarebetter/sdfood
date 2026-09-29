/**
 * The City staff site: the same app, built in the PRIVATE staff repository (vite.config.js defines
 * __STAFF__ there) and shipped with a staff copy of meta.json (publish_city_site.py: audience "staff",
 * contact, operator, sunset, review_status). The staff site shows what the public site never needs:
 * that downloads are public records, whom to write to, and which checks the list has not passed.
 */
/* global __STAFF__ */
import { auditedGroup } from "./bands.js";

/** True in the staff build itself (vite.config.js), whatever meta says. */
export const staffBuild = () => typeof __STAFF__ !== "undefined" && __STAFF__ === true;

export function isStaff(meta) {
  return staffBuild() || meta?.audience === "staff";
}

/**
 * The staff site's session ended (30 idle minutes, 10 hours, a restart): a data request answers 401.
 * Send the person to the sign-in page, back to where they were, instead of showing an error. True
 * when it did; never on the public site, which has no sign-in.
 */
export function signInAgain(res, loc = typeof window !== "undefined" ? window.location : null) {
  if (res?.status !== 401 || !staffBuild() || !loc) return false;
  loc.assign(`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`);
  return true;
}

/** "Jane Doe (jane@example.org)", or null. */
export function contactLine(meta) {
  const c = meta?.contact;
  if (!c || typeof c !== "object") return null;
  if (c.name && c.email) return `${c.name} (${c.email})`;
  return c.email || c.name || null;
}

/** The public-release checks this list has not passed, as the staff copy of meta states them. */
export function reviewStatus(meta) {
  return Array.isArray(meta?.review_status) ? meta.review_status.filter((s) => typeof s === "string" && s) : [];
}

/** The staff site's one cookie: the sign-in session (city_site/server.mjs). */
export const COOKIE_NOTE_STAFF =
  "This site sets one cookie of its own, to keep you signed in; it ends when you sign out, after 30 idle minutes, or after 10 hours.";

export const PUBLIC_RECORD_NOTE =
  "What you download, print, copy, screenshot or send from this site, and your messages about it on any account or device, " +
  "are likely City public records under the California Public Records Act and may have to be released on request. " +
  "Nothing on this site makes them confidential.";

export const USE_NOTE =
  "This is a student analysis of the County's published results, not a City or County finding about any business. " +
  "Do not forward names or bands outside the City, and do not contact a business about its band or use a band for any permit, " +
  "license, enforcement, grant, procurement or public-statement decision. That is a use rule, not a promise of confidentiality.";

/** The guidance sentences, so the banner, the district view and the tests share one wording. */
export const GUIDANCE = {
  demonstration: "The City has not recorded a request for this site or a TRUST Ordinance determination. Until it does, treat the site as a demonstration, not a City tool.",
  unreviewed: "No lawyer or County official has reviewed this list, and no business on it has been told it is listed: do not act on a band or repeat one outside the City.",
  persistence: "The points do no better than a place's recent major violations alone at picking out places with a major next time. Read them as a summary of the County's record, not a forecast for one place.",
  nothingToName: "No band is strong enough to justify singling out a business.",
  drift: "The County's record has changed since the rule was checked, so the rates on this site may be out of date.",
  prospective: "The rule has not yet been tested on inspections made after it was frozen.",
  adult: "No independent adult has signed off on this list; its operator is a student author.",
};

const APOS = "['’]";
const LINES = {
  access: new RegExp("^no City request for access is on record", "i"),
  trust: new RegExp("^no TRUST Ordinance determination is on record", "i"),
  council: new RegExp("^the TRUST Ordinance applies and the Council has not approved", "i"),
  lawyer: new RegExp("^no lawyer has reviewed naming these businesses", "i"),
  county: new RegExp("^the County has not commented on this list", "i"),
  owners: new RegExp("^no business on the list has been told it is on it", "i"),
  drift: new RegExp(`^the County${APOS}s record has moved since the rule was frozen`, "i"),
};

/** The districts named in the fairness lines ("district 4: ..."), in order. */
function flaggedDistricts(status) {
  return [...new Set(status.map((s) => /^district (\d+):/i.exec(s)?.[1]).filter(Boolean))].map(Number).sort((a, b) => a - b);
}

/** "District 4", "Districts 4 and 9", "Districts 4, 5 and 9". */
function districtsPhrase(districts) {
  const list = districts.length > 1 ? `${districts.slice(0, -1).join(", ")} and ${districts.at(-1)}` : `${districts[0]}`;
  return `District${districts.length > 1 ? "s" : ""} ${list}`;
}

/** An older export's fairness line, from the gate text alone. */
function districtLine(districts) {
  if (!districts.length) return null;
  return `A band is wrong more often in ${districtsPhrase(districts)} than elsewhere: do not compare districts by how many places are in a band.`;
}

/**
 * The council districts whose `meta.fairness.by_district[d].evidence_above_even` is true, in order:
 * their share of the wrongly named is above even at the low end of both family-wise intervals (the
 * address bootstrap's, and the same widened for an assumed design effect). Null for an export without
 * the field (one from before it existed).
 */
export function evidenceDistricts(meta) {
  const by = meta?.fairness?.by_district;
  if (!by || typeof by !== "object") return null;
  const rows = Object.entries(by).filter(([d, f]) => /^\d+$/.test(d) && typeof f?.evidence_above_even === "boolean");
  if (!rows.length) return null;
  return rows.filter(([, f]) => f.evidence_above_even).map(([d]) => Number(d)).sort((a, b) => a - b);
}

/**
 * The fairness line for the banner and the district view, saying what was measured: a district's
 * share of the places put in the band that then had no major, over its share of the places with a
 * later inspection (`false_share_ratio`), from `evidence_above_even` when the export has it:
 * "In the backtest, places in District 9 were put in band 1 and then had no major violation about
 * 1.9 times as often as across the City, for their number of places, even allowing for chance; ...".
 * Nothing when no district has that evidence; an older export falls back to its gate text's districts.
 */
export function fairnessLine(meta) {
  const ev = evidenceDistricts(meta);
  if (ev === null) return districtLine(flaggedDistricts(reviewStatus(meta)));
  if (!ev.length) return null;
  const by = meta.fairness.by_district;
  const ratio = (d) => by[String(d)]?.false_share_ratio;
  const times = ev.every((d) => typeof ratio(d) === "number")
    ? ` about ${ev.map((d) => `${ratio(d).toFixed(1)}`).join(ev.length > 2 ? ", " : " and ").replace(/, ([^,]*)$/, " and $1")} times as often as across the City`
    : " more often than across the City";
  return `In the backtest, places in ${districtsPhrase(ev)} were put in ${auditedBandsPhrase(meta)} and then had no major violation${times}` +
    `${ev.length > 1 ? " respectively" : ""}, for their number of places, even allowing for chance; part of this may be how inspectors ` +
    "there cite. Do not compare districts by how many places are in a band.";
}

/** "band 1", or "bands 1 to 3": the bands the district figures cover. */
function auditedBandsPhrase(meta) {
  return auditedGroup(meta).replace(/^places in /, "").replace(/ places$/, "");
}

/**
 * What the checks the list has not passed mean for someone using it, one sentence each: a count of
 * open checks is ignored by the second week; an instruction is not. When the City has recorded no
 * request for the site or no TRUST Ordinance determination, that comes first: the site is a
 * demonstration until it has.
 */
export function reviewGuidance(meta) {
  const status = reviewStatus(meta);
  const out = [];
  const has = (re) => status.some((s) => re.test(s));
  // The staff copy of meta says whether the City's request and TRUST answer are on record; an older
  // export only says so in its status lines.
  const notApproved = meta?.access_approved === false
    || (meta?.access_approved === undefined && (has(LINES.access) || has(LINES.trust) || has(LINES.council)));
  if (notApproved) out.push(GUIDANCE.demonstration);
  if (has(LINES.lawyer) || has(LINES.county) || has(LINES.owners)) out.push(GUIDANCE.unreviewed);
  if (has(/does not beat|within 0\.01 AUC/)) out.push(GUIDANCE.persistence);
  if (has(/cost ratio|nothing to name/)) out.push(GUIDANCE.nothingToName);
  const d = fairnessLine(meta);
  if (d) out.push(d);
  if (has(LINES.drift)) out.push(GUIDANCE.drift);
  if (has(/prospective test/)) out.push(GUIDANCE.prospective);
  if (has(/responsible adult|student author/)) out.push(GUIDANCE.adult);
  return out;
}

/**
 * "What to do" at the top of the district view on the staff site: how to use a district's list,
 * where a question about a place goes, and, when the fairness figures show districts above even
 * (fairnessLine), not to compare districts by their bands.
 */
export function districtGuidance(meta) {
  if (!isStaff(meta)) return [];
  const out = [
    "Open a district's list to see its places; each place's page shows its County record, which is the record of reference.",
    "A resident's report, an illness or a question about a place's record goes to the County: each place's page says where.",
  ];
  const d = fairnessLine(meta);
  if (d) out.push(d);
  return out;
}

/**
 * On the staff site, a CSV download is logged to the site's own server (`/audit`), which adds the
 * signed-in name: `{event: "csv", rows, name}`. Never throws; true when the browser queued it.
 */
export function auditCsv(meta, rows, name, nav = typeof navigator !== "undefined" ? navigator : null) {
  return audit(meta, { event: "csv", rows, name }, nav);
}

/** A print on the staff site, logged like a download: a printout is a City record too. */
export function auditPrint(meta, name, nav = typeof navigator !== "undefined" ? navigator : null) {
  return audit(meta, { event: "print", name }, nav);
}

function audit(meta, payload, nav) {
  if (!isStaff(meta)) return false;
  try {
    const body = new Blob([JSON.stringify(payload)], { type: "application/json" });
    return Boolean(nav?.sendBeacon?.("/audit", body));
  } catch {
    return false;
  }
}
