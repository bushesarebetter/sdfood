/**
 * The City staff site: the same app, built in the PRIVATE staff repository (vite.config.js defines
 * __STAFF__ there) and shipped with a staff copy of meta.json (publish_city_site.py: audience "staff",
 * contact, operator, sunset, review_status). The staff site shows what the public site never needs:
 * that downloads are public records, whom to write to, and which checks the list has not passed.
 */
/* global __STAFF__ */
import { auditedGroup, driftNote } from "./bands.js";
import { SITE } from "../site.js";

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

/** USE_NOTE in a few words, for the staff bar's always-visible line; the notice gives USE_NOTE in full. */
export const USE_POINT = "Do not share names or bands outside the City or use a band for any decision about a business";

/** The guidance sentences, so the banner, the district view and the tests share one wording. */
export const GUIDANCE = {
  demonstration: "The City has not recorded a request for this site or a TRUST Ordinance determination. Until it does, treat the site as a demonstration, not a City tool.",
  unreviewed: "No lawyer or County official has reviewed this list, and no business on it has been told it is listed: do not act on a band or repeat one outside the City.",
  persistence: "The points do no better than a place's recent major violations alone at picking out places with a major next time. Read them as a summary of the County's record, not a forecast for one place.",
  nothingToName: "No band is strong enough to justify singling out a business.",
  drift: "The County's record has changed since the rule was checked, so the rates on this site may be out of date.",
  driftLow: "In the latest quarter the County's inspectors found major violations more often than in the backtest the rates come from, so every rate on this site is probably low.",
  driftHigh: "In the latest quarter the County's inspectors found major violations less often than in the backtest the rates come from, so every rate on this site is probably high.",
  prospective: "The rule has not yet been tested on inspections made after it was frozen.",
  adult: "No independent adult has signed off on this list; its operator is a student author.",
};

/**
 * What the export's drift note (`meta.drift.note`, the latest quarter against the backtest) means for
 * the rates, as an instruction: GUIDANCE.driftLow or driftHigh, by the note's own "may be low" or "may
 * be high", else by `latest_rate` against `major_rate_backtest`. Null without a note. It is not a
 * refit alarm (GUIDANCE.drift is): the formal check cannot run until a quarter after the backtest year
 * is complete.
 */
export function driftNoteGuidance(meta) {
  const note = driftNote(meta);
  if (!note) return null;
  const said = /\bmay be (low|high)\b/i.exec(note)?.[1]?.toLowerCase();
  if (said) return said === "low" ? GUIDANCE.driftLow : GUIDANCE.driftHigh;
  const now = meta?.drift?.latest_rate, then = meta?.drift?.major_rate_backtest;
  if (typeof now !== "number" || typeof then !== "number" || now === then) return null;
  return now > then ? GUIDANCE.driftLow : GUIDANCE.driftHigh;
}

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
export function districtsPhrase(districts) {
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
 * The fairness line for the staff notice and the district view, saying what was measured: a district's
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

const NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"];
const lowAboveEven = (iv) => Array.isArray(iv) && typeof iv[0] === "number" && iv[0] > 1;

/**
 * Which districts are above even under which interval, for the About page's district table, from
 * `meta.fairness.by_district` (never from district numbers typed in): the districts whose
 * `evidence_above_even` is true stay above even on both wider intervals (family-wise, and widened for
 * inspectors), and fairnessLine names only them; of the rest, those whose 95% `interval` for the
 * district alone starts above 1, split by whether the family-wise one does too. Sentences, in that
 * order; null for an export without `evidence_above_even` (one from before it existed). `staff` says
 * that the staff notice and the district view name only the first group.
 */
export function districtStatus(meta, { staff = isStaff(meta) } = {}) {
  const ev = evidenceDistricts(meta);
  if (ev === null) return null;
  const alone = [], family = [];
  for (const [d, f] of Object.entries(meta.fairness.by_district)) {
    if (!/^\d+$/.test(d) || f?.evidence_above_even === true || !lowAboveEven(f?.interval)) continue;
    (lowAboveEven(f?.interval_family) ? family : alone).push(Number(d));
  }
  const n = SITE.districts.count;
  const across = `chance across the ${NUMBER_WORDS[n] ?? n} districts`;
  const is = (list) => (list.length > 1 ? "are" : "is");
  const out = [];
  if (ev.length) {
    const named = staff ? `, so the staff notice and the district view name ${ev.length > 1 ? "only these" : "only it"}` : "";
    out.push(`Only ${districtsPhrase(ev)} ${ev.length > 1 ? "stay" : "stays"} above even on both wider intervals, allowing for ${across} and for inspectors${named}.`);
  } else {
    out.push(`No district stays above even on both wider intervals, allowing for ${across} and for inspectors${staff ? ", so the staff notice and the district view name none" : ""}.`);
  }
  family.sort((a, b) => a - b);
  alone.sort((a, b) => a - b);
  if (family.length) {
    out.push(`${districtsPhrase(family)} ${is(family)} above even on the 95% interval for the district alone and on the family-wise one, ` +
      "but not once inspectors are allowed for too.");
  }
  if (alone.length) {
    out.push(`${districtsPhrase(alone)} ${is(alone)} above even on the 95% interval for the district alone, but not on the family-wise one, ` +
      `which allows for ${across}.`);
  }
  return out;
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
  // Not an open check: the export's own note on the latest quarter, as an instruction.
  const note = driftNoteGuidance(meta);
  if (note) out.push(note);
  if (has(/prospective test/)) out.push(GUIDANCE.prospective);
  if (has(/responsible adult|student author/)) out.push(GUIDANCE.adult);
  return out;
}

/** "This list has not passed 7 of the checks a public release would need.", or null when none is open. */
export function openChecksSentence(meta) {
  const n = reviewStatus(meta).length;
  return n > 0 ? `This list has not passed ${n} of the checks a public release would need.` : null;
}

/** "Questions: Jane Doe", a mailto link to meta.contact's email (the email itself without a name), or null. */
export function mailContact(meta) {
  const c = meta?.contact;
  const email = c && typeof c === "object" && typeof c.email === "string" ? c.email.trim() : "";
  if (!/^[^\s@<>"?&#]+@[^\s@<>"?&#]+$/.test(email)) return null;
  const name = typeof c.name === "string" && c.name.trim() ? c.name.trim() : email;
  return { href: `mailto:${email}`, label: `Questions: ${name}` };
}

/**
 * The staff notice (StaffBanner), on every page and both layouts. `points` are the one line that is
 * always in view, each rule in a few words: for whom, a student analysis, the use rule, that downloads,
 * prints and messages are likely public records, the demonstration point while the City has recorded
 * no request or TRUST answer, and the open checks while there are any. `mail` (whom to write to) sits
 * beside them. The rest is the whole notice one click away: the public-record note, the full use rule
 * (`use`), whom to write to (`contact`), the open checks (`open`, and the checks themselves) and every
 * instruction (`guidance`). It opens by itself at each sign-in until it is acknowledged.
 */
export function staffBar(meta) {
  const guidance = reviewGuidance(meta);
  const contact = contactLine(meta);
  const checks = reviewStatus(meta);
  const n = checks.length;
  return {
    points: [
      "For City of San Diego staff",
      "A student analysis, not a City or County finding",
      USE_POINT,
      "Downloads, prints and messages are likely public records",
      ...(guidance[0] === GUIDANCE.demonstration ? ["A demonstration, not a City tool"] : []),
      ...(n ? [`Not cleared for public release: ${n} ${n === 1 ? "check" : "checks"} open`] : []),
    ],
    mail: mailContact(meta),
    toggle: "The whole notice",
    contact: contact ? `Questions and corrections: ${contact}.` : null,
    use: USE_NOTE,
    open: openChecksSentence(meta),
    checks,
    guidance,
  };
}

/** Beside the district view's counts: majors, closures and grades are what inspectors cite. */
export const DISTRICT_CITING_NOTE =
  "Majors, closures and B or C grades are what the County's inspectors cite, and the record does not say which inspector made a visit, " +
  "so a gap between districts may be how they are cited. Take a district's pattern to the County as a question, not as a ranking of districts.";

/**
 * For the one district selected in the district view, and only for it (a rate on every row would rank
 * districts): each fact as a share of its listed places. `r` is the view's row, `{n, major, closed, bc}`.
 * "District 3, out of its 1,336 listed places: a major violation at 21 in 100, closed for a health
 * hazard at 2 in 100, a B or C grade at 3 in 100." Null without places.
 */
export function districtShareLine(name, r) {
  const n = r?.n;
  if (!Number.isInteger(n) || n <= 0) return null;
  const share = (k) => `${Math.round((100 * (Number(r[k]) || 0)) / n)} in 100`;
  return `${name}, out of its ${n.toLocaleString("en-US")} listed ${n === 1 ? "place" : "places"}: a major violation at ${share("major")}, ` +
    `closed for a health hazard at ${share("closed")}, a B or C grade at ${share("bc")}.`;
}

/**
 * "What to do" at the top of the district view on the staff site: how to use a district's list,
 * where a question about a place goes, that the district counts are what inspectors cite
 * (DISTRICT_CITING_NOTE, on every staff export), and, when the fairness figures show districts above
 * even (fairnessLine), not to compare districts by their bands.
 */
export function districtGuidance(meta) {
  if (!isStaff(meta)) return [];
  const out = [
    "Open a district's list to see its places; each place's page shows its County record, which is the record of reference.",
    "A resident's report, an illness or a question about a place's record goes to the County: each place's page says where.",
    DISTRICT_CITING_NOTE,
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

/**
 * A print on the staff site, logged like a download: a printout is a City record too. `rows`, when
 * given, is how many places the printout lists.
 */
export function auditPrint(meta, name, nav = typeof navigator !== "undefined" ? navigator : null, rows = undefined) {
  return audit(meta, { event: "print", ...(Number.isSafeInteger(rows) && rows >= 0 ? { rows } : {}), name }, nav);
}

// The view that can say what a print holds (the list's printout), asked at the moment of printing.
let describer = null;

/**
 * Registers `fn`, `() => ({name, rows}) | null`, as what a print holds while the view that knows is
 * open; returns the function that unregisters it. With none (or a null answer) a print is logged under
 * the page's address.
 */
export function describePrints(fn) {
  describer = fn;
  return () => { if (describer === fn) describer = null; };
}

/** The name (at most 120 characters, as the server takes) and row count a print is logged under. */
export function printSubject(loc = typeof window !== "undefined" ? window.location : null) {
  let s = null;
  try {
    s = describer?.() ?? null;
  } catch {
    s = null;
  }
  const name = String(s?.name || `${loc?.pathname ?? "/"}${loc?.search ?? ""}`).slice(0, 120);
  return { name, rows: Number.isSafeInteger(s?.rows) ? s.rows : undefined };
}

/**
 * Logs every print on the staff site once, whatever the layout (the phone shell, the map, a page):
 * mounted once at the root of the app (StaffBanner.jsx PrintAudit), never by a banner, so no layout
 * goes unlogged and none logs twice. Returns the function that stops it; nothing on the public site.
 */
export function watchPrints(meta, win = typeof window !== "undefined" ? window : null, nav = typeof navigator !== "undefined" ? navigator : null) {
  if (!isStaff(meta) || typeof win?.addEventListener !== "function") return () => {};
  const onPrint = () => {
    const s = printSubject(win.location);
    auditPrint(meta, s.name, nav, s.rows);
  };
  win.addEventListener("beforeprint", onPrint);
  return () => win.removeEventListener("beforeprint", onPrint);
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
