/**
 * How the site describes itself, in one place, for both modes.
 *
 * The site is a working tool for City of San Diego staff. `record` (the
 * default, and what a missing or unknown `meta.mode` falls back to) is the
 * County's inspection record for every listed place, listed by name, with
 * nothing from a model: no points, no bands, no rule, no backtest. `bands`
 * adds the students' point rule, which puts some places in bands; every band
 * is described by the rule, its points and its backtest rate (lib/bands.js),
 * and every scored place by an estimate read from the backtest.
 *
 * These helpers are pure so tests can check that record mode says nothing
 * model-related and that no sentence runs past what the export backs.
 */
import { SITE, STUDENT_NOTE } from "../site.js";
import { expiryNotice } from "./expiry.js";
import { MAX_ITEMS, typePlural } from "./inspections.js";
import { gradeView } from "./grades.js";
import { shownBand } from "./marks.js";
import { GROUP_NOTE, bandDefs, bandPoints, bandShare, bandSummary, estimateSentence, isOutside, ruleSentence } from "./bands.js";

export function siteMode(meta) {
  return meta?.mode === "bands" ? "bands" : "record";
}

export const isBands = (meta) => siteMode(meta) === "bands";

const count = (n) => Number(n || 0).toLocaleString("en-US");

function joinWords(words) {
  if (words.length <= 1) return words.join("");
  return `${words.slice(0, -1).join(", ")} and ${words.at(-1)}`;
}

/** "restaurants, markets and limited-preparation food places": the kinds present, most common first. */
export function kindsPhrase(features) {
  const counts = new Map();
  for (const f of features ?? []) {
    const t = f?.properties?.facility_type ?? "other";
    counts.set(t, (counts.get(t) ?? 0) + 1);
  }
  if (!counts.size) return "restaurants and markets";
  return joinWords([...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([t]) => typePlural(t)));
}

const banded = (features) => (features ?? []).filter((f) => shownBand(f.properties, { mode: "bands" }));

/**
 * The headline. Record: "The County's inspection record for 1,143 San Diego
 * restaurants and markets". Bands: "The 200 San Diego restaurants and markets
 * whose County record scores highest on the students' point rule".
 */
export function headline(meta, features) {
  if (siteMode(meta) === "bands") {
    const b = banded(features);
    if (!b.length) return `The ${SITE.name} food places whose County record scores highest on the students' point rule`;
    return `The ${count(b.length)} ${SITE.name} ${kindsPhrase(b)} whose County record scores highest on the students' point rule`;
  }
  const n = features?.length ?? 0;
  return n
    ? `The County's inspection record for ${count(n)} ${SITE.name} ${kindsPhrase(features)}`
    : `The County's inspection record for ${SITE.name} restaurants and markets`;
}

/** The paragraph under the headline. */
export function subhead(meta) {
  if (siteMode(meta) === "bands") {
    const shares = bandDefs(meta).map((d) => [d.band, bandShare(meta, d.band)]).filter(([, s]) => s);
    const cut = shares.length ? ` ${shares.map(([b, s], i) => (i ? `band ${b} ${s}` : `Band ${b} is ${s}`)).join(", ")}.` : "";
    return `${ruleSentence(meta)}${cut} Every other fact shown is the County's published record.`;
  }
  return "The inspection records the County has published for each place since January 2023, with each score, grade, cited item " +
    "and County note, listed by name. Left out: visits marked No Access or Incomplete, and Self Closed or Status Verification " +
    `records that cite no item and were not ordered closed. Each place lists up to ${MAX_ITEMS} items from the three years ` +
    "before its last visit, majors first.";
}

/** The share of routine inspections with a major that still end with an A, with the County's rule beside it. */
export function gradeContextSentence(meta) {
  const s = meta?.grade_context?.majors_graded_A_share;
  const share = typeof s === "number" && s > 0 && s <= 1
    ? `Most routine inspections that find a major violation still end with an A: ${Math.round(s * 100)}% of them did.`
    : "Most routine inspections that find a major violation still end with an A.";
  return `${share} ${SITE.regulator.majorRule}`;
}

/** The description for a page's meta tags. */
export function siteDescription(meta) {
  if (siteMode(meta) === "bands") {
    return `${SITE.name} restaurants and markets whose County inspection record scores highest on the students' point rule, with each place's record. ${STUDENT_NOTE}`;
  }
  return `The County's inspection record for ${SITE.fullName} restaurants and markets: each inspection record, score, grade and finding, as the County published it. ${STUDENT_NOTE}`;
}

/** The map key's note, which says which way darker goes in words. */
export function legendNote(meta) {
  if (siteMode(meta) === "bands") return `Darker = more points on the students' point rule. ${bandSummary(meta, "1")}`;
  return "Every listed place is drawn alike. Select one to see its County record.";
}

/**
 * The lines under a place's name in every place view: its grade (unless the
 * view states it in its record summary), then, in `bands` mode, the estimate
 * for places with about its points first, then its band, its points and what
 * the band's backtest showed.
 */
export function placeLines(p, meta, { expired = false, withGrade = true, estimate = null } = {}) {
  const g = gradeView(p?.grade);
  const lines = withGrade ? [g.sentence] : [];
  if (withGrade && g.replacedSentence) lines.push(g.replacedSentence);
  if (expired) {
    lines.push(expiryNotice(meta));
    return lines;
  }
  if (siteMode(meta) !== "bands") return lines;
  if (p?.on_hold) {
    lines.push("Under review: this place's band and points are withheld while they are checked. Its County record is shown below.");
    return lines;
  }
  // Outside the City, rates are the ones measured outside the City (meta.card.outside).
  const outside = isOutside(p, meta);
  const b = shownBand(p, { mode: "bands" });
  // With separate curves by route (card.curve_closure), only the place's own estimate can say which
  // one it reads: while its record loads there is no estimate line, rather than a guess.
  const est = !estimate && meta?.card?.curve_closure ? null : estimateSentence(meta, p?.points, { estimate, outside });
  if (!b) {
    if (typeof p?.points === "number") {
      const lowest = bandDefs(meta).at(-1);
      const edge = typeof lowest?.min_points === "number" ? ` (band ${lowest.band} starts at ${lowest.min_points} points)` : "";
      if (est) lines.push(est);
      lines.push(`In no band: ${p.points} points on the students' point rule${edge}.`);
    } else {
      const who = typeof meta?.card?.eligibility === "string" ? ` It scores ${meta.card.eligibility.replace(/\.$/, "")}.` : "";
      lines.push(`Not scored: the students' point rule gives this place no points.${who}`);
    }
    return lines;
  }
  const range = bandPoints(meta, b);
  const pts = typeof p.points === "number" ? `: ${p.points} points` : "";
  if (est) lines.push(est);
  lines.push(`Band ${b} on the students' point rule${pts}${range ? ` (band ${b} is ${range})` : ""}.`);
  lines.push(bandSummary(meta, b, { outside, district: p?.council_district ?? null }));
  lines.push(GROUP_NOTE);
  return lines;
}
