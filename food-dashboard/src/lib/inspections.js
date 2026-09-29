/**
 * What a facility's inspection record says, computed once from its place file.
 *
 * A place file (`data/place/<facility_id>.json`) carries each County record
 * since the public record starts (January 2023), oldest first, one entry per
 * record: the County's own `status` text ("Complete", "Ordered Closed",
 * "Approved to Reopen", "Self Closed"), its own inspection type
 * (`county_type`: "Routine", "Re-inspection", "Site Investigation",
 * "Environmental", "Status Verification") and its own notes (`notes`, such as
 * "Impoundment" or "No Valid Permit"), all shown verbatim. Exports from
 * before `county_type` and `notes` carry only the visit type.
 *
 * These things on a record are the pipeline's readings, and the site labels
 * them "Our reading":
 *  - a routine inspection retyped as a re-grade or reopening visit (`followup`);
 *  - a "Site Investigation" or "Environmental" record grouped as a complaint
 *    or other field visit (`complaint`);
 *  - the reason for a closure (`closure`), and a "Self Closed" record with a
 *    major violation read as the operator's own closure;
 *  - a closure that only a later "Approved to Reopen" shows, with no closure
 *    order on the published record (`closure_inferred`), and an "Approved to
 *    Reopen" before which no closure could be placed (`reopen_without_closure`);
 *  - the theme of each item.
 * A record that starts a closure episode also carries `reopened_on`, the date
 * of the County's "Approved to Reopen" record that ended it, or null. A
 * "Status Verification" record the export keeps (it cites items, or is
 * "Ordered Closed") has the type `status_check`: shown, never scored.
 *
 * `violations` holds the items cited in the 36 months before the last visit:
 * major violations, minor violations and good-retail-practice items (`grp`),
 * majors first, at most 60. `theme_counts` and `violations_total`, where the
 * export gives them, count every item in that window before the cut.
 *
 * Grades are the County's letters as recorded. None is ever derived from a
 * score: a visit the County did not grade has no grade here either.
 */
import { fmtDate } from "./dates.js";

/**
 * Themes follow the sections of the County's own inspection report (the
 * fixed-facility form's items 1a to 23, then the good-retail-practice items
 * from 24 on; the mobile form's items are mapped to the same sections).
 */
export const THEMES = {
  knowledge: "Food safety certificate and food handler cards",
  health: "Employee health and hygiene",
  hands: "Hands washed, gloves used",
  handsink: "Hand sinks stocked and accessible",
  temperature: "Food temperatures",
  condition: "Food condition",
  sanitizing: "Food-contact surfaces cleaned and sanitized",
  supplier: "Food source and shellfish tags",
  process: "Special processes (HACCP)",
  advisory: "Consumer advisory",
  hsp: "Foods not allowed for highly susceptible people",
  water: "Hot and cold water",
  sewage: "Sewage and wastewater",
  vermin: "Pests",
  grp_staff: "Supervision and personal cleanliness (good retail practice)",
  grp_food: "Food handling and chemicals (good retail practice)",
  grp_storage: "Food storage, display and labels (good retail practice)",
  grp_equipment: "Equipment, utensils and dishwashing (good retail practice)",
  grp_facility: "Building and premises (good retail practice)",
  grp_signs: "Signs, grade card and permits (good retail practice)",
  grp_other: "Other (good retail practice)",
  other: "Other",
};

export const TYPE_LABELS = {
  restaurant: "Restaurant",
  limited: "Limited-preparation food service",
  market: "Market with a deli or food processing",
  mobile: "Food truck or cart",
  bar: "Bar",
  school: "School kitchen",
  bakery: "Bakery",
  caterer: "Caterer",
  other: "Food facility",
};

export const TYPE_PLURALS = {
  restaurant: "restaurants",
  limited: "limited-preparation food places",
  market: "markets",
  mobile: "food trucks and carts",
  bar: "bars",
  school: "school kitchens",
  bakery: "bakeries",
  caterer: "caterers",
  other: "other food facilities",
};

/** The export's enums, shared with the contract check. */
export const MODES = ["record", "bands"];
export const PUBLIC_TYPES = ["restaurant", "limited", "market"];
export const VISIT_TYPES = ["routine", "reinspection", "followup", "complaint", "status_check"];
export const SEVERITIES = ["major", "minor", "grp"];
export const CLOSURES = ["health", "permit", "other"];
export const GRADES = ["A", "B", "C"];
/** The escalation facts: our counts, in the 24 months before the list date, of patterns the County's Operator's Guide names. */
export const ESCALATION_FLAGS = ["major_2", "closures2", "repeat_item", "lt90_2"];
export const RECORD_FLAGS = ["major", "closed", "bc", "repeat", ...ESCALATION_FLAGS];
/** A flag is a record flag or the theme of a major violation; "other" is never a flag. */
export const FLAG_KEYS = [...RECORD_FLAGS, ...Object.keys(THEMES).filter((k) => k !== "other")];

const lowerFirst = (s) => `${s.charAt(0).toLowerCase()}${s.slice(1)}`;
const sentenceCase = (s) => `${s.charAt(0).toUpperCase()}${s.slice(1)}`;

/**
 * The escalation facts a place meets, as its page lists them: [{ key, label }], in ESCALATION_FLAGS
 * order. Facts about the County's record, counted from the list date; not predictions.
 */
export function escalationFacts(flags) {
  const have = new Set(Array.isArray(flags) ? flags : []);
  return ESCALATION_FLAGS.filter((k) => have.has(k)).map((k) => ({ key: k, label: FLAG_LABELS[k] }));
}

/**
 * The index's record flags, as filter labels. Every one is our reading of the record. A closure is
 * any closure episode read as a health hazard: the County's "Ordered Closed", a "Self Closed" read as
 * the operator's own closure, or one only a later "Approved to Reopen" shows; so the label says
 * "closed", never "ordered closed".
 */
export const FLAG_LABELS = {
  major: "A major violation",
  closed: "Closed for a health hazard",
  bc: "A B or C grade",
  repeat: "Two or more reinspections",
  major_2: "Major violations at two or more routine inspections in two years",
  closures2: "Closed for a health hazard two or more times in two years",
  repeat_item: "Same major item at two or more routine inspections in two years",
  lt90_2: "Scored below 90 at two or more routine inspections in two years",
  ...Object.fromEntries(Object.entries(THEMES).filter(([k]) => k !== "other").map(([k, v]) => [k, `Major: ${lowerFirst(v)}`])),
};

/**
 * The facts in a few words each, for the list and the staff site's filter rail, where FLAG_LABELS
 * would make every row ten lines tall. Each short tag keeps every qualifier of its FLAG_LABELS
 * wording (the reason, the routine inspections, the window) and stands for it: the list gives the
 * full wording to screen readers and as a tooltip, and the place's own view gives it in full.
 */
export const FLAG_SHORT = {
  major: "Major violation",
  closed: "Closed, health hazard",
  bc: "B or C grade",
  repeat: "2+ reinspections",
  major_2: "Majors at 2+ routines, 2 years",
  closures2: "Closed for a health hazard 2+ times, 2 years",
  repeat_item: "Same major item at 2+ routines, 2 years",
  lt90_2: "Below 90 at 2+ routines, 2 years",
};

/**
 * A place's facts for the list: the record facts and the escalation facts as `{key, short, full}` tags,
 * in RECORD_FLAGS order, and the themes of its major violations in a few words ("food temperatures").
 */
export function factTags(flags) {
  const f = Array.isArray(flags) ? flags : [];
  const tag = (k) => ({ key: k, short: FLAG_SHORT[k] ?? FLAG_LABELS[k] ?? k, full: FLAG_LABELS[k] ?? k });
  return {
    record: RECORD_FLAGS.filter((k) => !ESCALATION_FLAGS.includes(k) && f.includes(k)).map(tag),
    escalation: ESCALATION_FLAGS.filter((k) => f.includes(k)).map(tag),
    themes: f.filter((k) => k !== "other" && THEMES[k]).map((k) => lowerFirst(THEMES[k])),
  };
}

/**
 * Where the escalation facts come from, quoted in full: the County's Retail Food Facility
 * Operator's Guide, p. 8. The Guide sets no count or period; the counts are ours.
 */
export const GUIDE_CRITERIA = "recurring major violations, recurring scores of less than 90%, or recurring facility closures";
export const ESCALATION_TITLE = "Patterns the County's Operator's Guide names";
export const ESCALATION_NOTE =
  `The County's Retail Food Facility Operator's Guide (p. 8) says a facility with “a history of ${GUIDE_CRITERIA}” may be issued a notice to appear for an administrative hearing. ` +
  "The County sets no count or period. These are our counts (two or more in the 24 months before the list date; a closure, which the County does not score, counts as a closure, not as a score below 90); " +
  "meeting one is not a County finding and does not mean the County has acted or will.";

export const VISIT_LABELS = {
  routine: "routine inspection",
  reinspection: "reinspection",
  followup: "re-grade or reopening visit",
  complaint: "complaint or other field visit",
  status_check: "status verification",
};

/** The visit types that are our reading of the County's type, not its own words. */
export const READ_VISIT_TYPES = ["followup", "complaint"];

/** The read visit types in the list's few words: each still names what the full label does. */
export const VISIT_SHORT = {
  followup: "re-grade or reopening",
  complaint: "field visit",
};

/** The County's own inspection type for each visit type, as `county_type` carries it. */
export const COUNTY_TYPES = {
  routine: ["Routine"],
  followup: ["Routine"],
  reinspection: ["Re-inspection"],
  complaint: ["Site Investigation", "Environmental"],
  status_check: ["Status Verification"],
};

export const SEVERITY_LABELS = { major: "major violation", minor: "minor violation", grp: "good-retail-practice item" };

/** Our reading of a closure's reason, in a few words. */
export const CLOSURE_LABELS = { health: "health hazard", permit: "permit matter", other: "no major violation cited" };

/**
 * The pipeline's readings, each with its rule in one line. Anything the site
 * says that is not the County's own text carries one of these.
 */
export const OUR_READING = {
  followup: "a routine inspection within 30 days after a B, a C or a closure is read as a re-grade or reopening visit.",
  complaint: "the County's Site Investigation and Environmental records are read as complaint or other field visits.",
  health: "a major violation was cited that day.",
  permit: "no major violation was cited that day and the inspector's notes mention a permit, so we read the closure as a permit matter.",
  other: "no item marked major was cited that day and no note mentions a permit; the County's record gives no reason.",
  selfClosed: "a Self Closed record with a major violation cited that day is read as the operator's own closure.",
  inferred: "an Approved to Reopen with no closure order before it is read as ending a closure that began at this visit.",
  reopenOnly: "no closure could be placed before this Approved to Reopen, and none is read into the record.",
  themes: "each item is put under a theme from the County's item text.",
  flags: "read from the 12 months before the list date, and 24 months for the four escalation facts.",
};

const typeOf = (i) => i?.type ?? "routine";
export const visitLabel = (type) => VISIT_LABELS[type ?? "routine"] ?? String(type);
export const isGraded = (i) => GRADES.includes(i?.grade);

/** The County's own inspection type on a record, verbatim, or null in an export from before it. */
export const countyType = (i) => (typeof i?.county_type === "string" && i.county_type.trim() ? i.county_type.trim() : null);

/** The County's own notes on a record ("Impoundment", "No Valid Permit"), verbatim; [] when none or in an older export. */
export const countyNotes = (i) => (Array.isArray(i?.notes) ? i.notes.filter((n) => typeof n === "string" && n.trim()).map((n) => n.trim()) : []);

/**
 * A record's visit in words, with our reading marked: "routine inspection",
 * "re-grade or reopening visit (our reading; County type: Routine)",
 * "complaint or other field visit (our reading)" in an export without the County's type.
 */
export function visitPhrase(i) {
  const type = typeOf(i);
  const ct = countyType(i);
  if (!READ_VISIT_TYPES.includes(type)) return visitLabel(type);
  return `${visitLabel(type)} (our reading${ct ? `; County type: ${ct}` : ""})`;
}

/**
 * A visit in the list's narrow column, our reading still marked: "re-grade or reopening (our
 * reading)", "field visit (our reading)"; the County's own types as visitLabel gives them. The list
 * gives visitPhrase beside it, to screen readers and as a tooltip.
 */
export function visitShort(i) {
  const type = typeOf(i);
  if (!READ_VISIT_TYPES.includes(type)) return visitLabel(type);
  return `${VISIT_SHORT[type] ?? visitLabel(type)} (our reading)`;
}

const REOPEN = /approved to reopen/i;
export const isReopenRecord = (i) => REOPEN.test(i?.status ?? "");
export const isSelfClosed = (i) => /self closed/i.test(i?.status ?? "");
/** A closure only a later "Approved to Reopen" shows: no closure order is on the published record. */
export const isInferredClosure = (i) => Boolean(i?.closed) && i?.closure_inferred === true;

/**
 * The words for a record that starts a closure episode, one set for every
 * view (the table, the facts panel and the pasted text):
 *  - `kind`: "order" (the County's "Ordered Closed"), "self" (the County's
 *    "Self Closed", read as the operator's own closure) or "inferred" (only a
 *    later "Approved to Reopen" shows it);
 *  - `title`: the County's status text, or "Closure, our reading" when no
 *    closure is on the published record;
 *  - `reason`: our reading of the reason, in a few words;
 *  - `short`: what a table cell says after "our reading: ";
 *  - `reading`: the rule behind it, to follow "Our reading: ".
 */
export function closureWords(i) {
  const reason = CLOSURE_LABELS[i?.closure] ?? CLOSURE_LABELS.other;
  const because = OUR_READING[i?.closure] ?? OUR_READING.other;
  if (isInferredClosure(i)) {
    const on = /^\d{4}-\d{2}-\d{2}$/.test(i.reopened_on ?? "") ? ` on ${fmtDate(i.reopened_on)}` : "";
    return {
      kind: "inferred",
      title: "Closure, our reading",
      reason,
      short: `a closure (${reason}), from the “Approved to Reopen”${on}`,
      reading: `the County's “Approved to Reopen”${on} implies a closure; no closure order is on the published record. ${sentenceCase(because)}`,
    };
  }
  if (isSelfClosed(i)) {
    return { kind: "self", title: i.status, reason, short: `the operator's own closure (${reason})`, reading: OUR_READING.selfClosed };
  }
  return { kind: "order", title: i?.status || "Ordered Closed", reason, short: reason, reading: because };
}

const MS_DAY = 24 * 3600 * 1000;
const MS_MONTH = 30.44 * MS_DAY;
const monthsBetween = (a, b) => (new Date(b) - new Date(a)) / MS_MONTH;
const sum = (xs, key) => xs.reduce((a, i) => a + (i[key] || 0), 0);

/** Whether `date` falls in the `months` before `end`, `end` included. */
export function withinMonths(date, end, months) {
  if (!date || !end) return false;
  const m = monthsBetween(date, end);
  return m >= 0 && m <= months;
}

export function lastInspection(p) {
  const list = p?.inspections ?? [];
  return list.length ? list[list.length - 1] : null;
}

/**
 * The record in numbers. The `36` windows count back from the last visit on
 * record, not from today, so a stale export does not empty every place's
 * counts. Grades are not here: every view takes a place's grade from the
 * index's `grade` through lib/grades.js.
 */
export function inspectionStats(p) {
  const list = (p?.inspections ?? []).filter((i) => i?.date);
  const last = lastInspection({ inspections: list });
  if (!last) return null;
  const recent36 = list.filter((i) => monthsBetween(i.date, last.date) <= 36);
  const closed = list.filter((i) => i.closed);
  const closedBy = (reason) => closed.filter((i) => i.closure === reason).length;
  return {
    count: list.length,
    count36: recent36.length,
    routineCount: list.filter((i) => typeOf(i) === "routine").length,
    first: list[0],
    last,
    lastScore: typeof last.score === "number" ? last.score : null,
    majors36: sum(recent36, "major"),
    minors36: sum(recent36, "minor"),
    grp36: sum(recent36, "grp"),
    // Closure episodes (our reading), by reason, over the whole record: `closures` is the health ones.
    closures: closedBy("health"),
    permitClosures: closedBy("permit"),
    otherClosures: closedBy("other"),
    closureEpisodes: closed.length,
    inferredClosures: closed.filter(isInferredClosure).length,
    selfClosures: closed.filter(isSelfClosed).length,
    // The County's own rows: every record whose status is "Ordered Closed", whether or not it starts an episode.
    orderedClosedRecords: list.filter((i) => i.status === "Ordered Closed").length,
    reopenedWithoutClosure: list.filter((i) => i.reopen_without_closure === true).length,
    reinspections: list.filter((i) => i.type === "reinspection").length,
    followups: list.filter((i) => i.type === "followup").length,
    complaints: list.filter((i) => i.type === "complaint").length,
    statusChecks: list.filter((i) => i.type === "status_check").length,
  };
}

/** The export lists at most this many items per place (export_site.MAX_VIOLATIONS), majors first. */
export const MAX_ITEMS = 60;

const count = (x) => (Number.isInteger(x) && x >= 0 ? x : 0);
const byWorst = (a, b) => b.major - a.major || b.count - a.count || (b.last ?? "").localeCompare(a.last ?? "");

/**
 * Items cited in the three years before the last visit, grouped by theme,
 * worst first: majors, then count, then recency. Given a place, it reads the
 * export's `theme_counts` (every item in the window, counted before the
 * 60-item cut) when there are any; given a list of items, or a place from an
 * export without them, it counts the items listed.
 */
export function themeCounts(input = []) {
  const place = input && !Array.isArray(input) && typeof input === "object" ? input : null;
  const tc = place?.theme_counts;
  const by = new Map();
  const row = (key) => by.get(key) ?? { theme: key, label: THEMES[key], count: 0, major: 0, minor: 0, grp: 0, complaint: 0, last: null };
  if (tc && typeof tc === "object" && !Array.isArray(tc) && Object.keys(tc).length) {
    for (const [theme, c] of Object.entries(tc)) {
      const key = THEMES[theme] ? theme : "other";
      const t = row(key);
      t.major += count(c?.major);
      t.minor += count(c?.minor);
      t.grp += count(c?.grp);
      t.count = t.major + t.minor + t.grp;
      t.complaint += count(c?.complaint);
      const latest = c?.latest ?? c?.last ?? null;
      if (latest && (!t.last || latest > t.last)) t.last = latest;
      by.set(key, t);
    }
    return [...by.values()].filter((t) => t.count > 0).sort(byWorst);
  }
  for (const v of (place ? place.violations : input) ?? []) {
    const key = THEMES[v.theme] ? v.theme : "other";
    const t = row(key);
    t.count += 1;
    if (v.severity === "major") t.major += 1;
    else if (v.severity === "grp") t.grp += 1;
    else t.minor += 1;
    if (v.visit === "complaint") t.complaint += 1;
    if (!t.last || v.date > t.last) t.last = v.date;
    by.set(key, t);
  }
  return [...by.values()].sort(byWorst);
}

/**
 * How many of a place's items the export lists: { shown, total, cut }. `total`
 * is `violations_total` where the export gives it; an older export at the
 * 60-item cut does not say how many more there were (total null, cut true).
 */
export function itemsShown(p) {
  const shown = Array.isArray(p?.violations) ? p.violations.length : 0;
  const total = Number.isInteger(p?.violations_total) && p.violations_total >= shown ? p.violations_total : null;
  return { shown, total, cut: total != null ? total > shown : shown >= MAX_ITEMS };
}

/**
 * The line a view shows under counts read from the listed items when the
 * export cut them at 60, or null: counts from `theme_counts` are whole, and
 * so is a list that was not cut.
 */
export function themeCountsNote(p) {
  const { shown, total, cut } = itemsShown(p);
  if (!cut) return null;
  const tc = p?.theme_counts;
  if (tc && typeof tc === "object" && Object.keys(tc).length) return null;
  return total != null
    ? `Showing ${shown} of ${total} items, majors first: counts of minor and good-retail-practice items, and their latest dates, may be low.`
    : `Showing the first ${shown} items, majors first; the export lists no more, so counts of minor and good-retail-practice items may be low.`;
}

export function fmtScore(score) {
  return score == null ? "" : String(Math.round(score));
}

/** "A (96)", "B", or "" for a record the County did not grade. One County record's letter. */
export function recordGradeText(i) {
  if (!isGraded(i)) return "";
  return typeof i.score === "number" ? `${i.grade} (${i.score})` : i.grade;
}

/**
 * "Reopened June 8, 2025" for a record that starts a closure episode the
 * County's "Approved to Reopen" record ended, else null.
 */
export function reopenedText(i) {
  if (!i?.closed || !/^\d{4}-\d{2}-\d{2}$/.test(i.reopened_on ?? "")) return null;
  return `Reopened ${fmtDate(i.reopened_on)}`;
}

/**
 * What the County's record shows after the record at `idx`, which starts a
 * closure episode:
 *  - `reopen`: the "Approved to Reopen" record that ended it (from
 *    `reopened_on`; in an export from before it, the next such record when
 *    `reopened` is true), or null;
 *  - `nextGraded`: the next graded routine or re-grade on a later day, or null;
 *  - `laterReopen`: an "Approved to Reopen" after it and before `nextGraded`
 *    that the export did not tie to it, or null;
 *  - `later`: every record after it;
 *  - `open`: none of these: no "Approved to Reopen" and no graded visit
 *    follow it on the published record. That says nothing about whether the
 *    place is closed now: a later ungraded visit may have been the reopening.
 */
export function closureEnd(list, idx) {
  const i = list?.[idx];
  if (!i) return { reopen: null, nextGraded: null, laterReopen: null, later: [], open: false };
  const later = list.slice(idx + 1);
  let reopen = null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(i.reopened_on ?? "")) {
    reopen = later.find((j) => j.date === i.reopened_on && isReopenRecord(j)) ?? { status: "Approved to Reopen", date: i.reopened_on };
  } else if (i.reopened === true) {
    reopen = later.find(isReopenRecord) ?? { status: "Approved to Reopen", date: null };
  }
  const nextGraded = later.find((j) => (j.type === "routine" || j.type === "followup") && isGraded(j) && j.date > i.date) ?? null;
  const laterReopen = reopen ? null : later.find((j) => isReopenRecord(j) && (!nextGraded || j.date <= nextGraded.date)) ?? null;
  return { reopen, nextGraded, laterReopen, later, open: i.reopened === false && !laterReopen && !nextGraded };
}

export const typeLabel = (type) => TYPE_LABELS[type] ?? TYPE_LABELS.other;
export const typePlural = (type) => TYPE_PLURALS[type] ?? TYPE_PLURALS.other;
