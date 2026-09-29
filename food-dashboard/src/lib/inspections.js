/**
 * What a facility's inspection record says, computed once from its place file.
 *
 * A place file (`data/place/<facility_id>.json`) carries each County record
 * since the public record starts (January 2023), oldest first, one entry per
 * record: the County's own `status` text ("Complete", "Ordered Closed",
 * "Approved to Reopen"), shown verbatim, and the visit type. Three things on a
 * record are the pipeline's readings, and the site labels them "Our reading":
 * a routine inspection retyped as a re-grade or reopening visit (`followup`),
 * the reason for a closure (`closure`), and the theme of each item. A record
 * that starts a closure episode also carries `reopened_on`, the date of the
 * County's "Approved to Reopen" record that ended it, or null.
 * `violations` holds the items cited in the 36 months before the last visit:
 * major violations, minor violations and good-retail-practice items (`grp`).
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
export const VISIT_TYPES = ["routine", "reinspection", "followup", "complaint"];
export const SEVERITIES = ["major", "minor", "grp"];
export const CLOSURES = ["health", "permit", "other"];
export const GRADES = ["A", "B", "C"];
/** The escalation facts: the 24 months before the list date, the County's own criteria for a closer look. */
export const ESCALATION_FLAGS = ["closures2", "repeat_item", "lt90_2"];
export const RECORD_FLAGS = ["major", "closed", "bc", "repeat", ...ESCALATION_FLAGS];
/** A flag is a record flag or the theme of a major violation; "other" is never a flag. */
export const FLAG_KEYS = [...RECORD_FLAGS, ...Object.keys(THEMES).filter((k) => k !== "other")];

const lowerFirst = (s) => `${s.charAt(0).toLowerCase()}${s.slice(1)}`;

/**
 * The escalation facts a place meets, as its page lists them: [{ key, label }], in ESCALATION_FLAGS
 * order. Facts about the County's record, counted from the list date; not predictions.
 */
export function escalationFacts(flags) {
  const have = new Set(Array.isArray(flags) ? flags : []);
  return ESCALATION_FLAGS.filter((k) => have.has(k)).map((k) => ({ key: k, label: FLAG_LABELS[k] }));
}

/** The index's record flags, as filter labels. Every one is our reading of the record. */
export const FLAG_LABELS = {
  major: "A major violation",
  closed: "Ordered closed, health hazard",
  bc: "A B or C grade",
  repeat: "Two or more reinspections",
  closures2: "Ordered closed, health hazard, two or more times in two years",
  repeat_item: "Same major item at two or more routine inspections in two years",
  lt90_2: "Scored below 90 at two or more routine inspections in two years",
  ...Object.fromEntries(Object.entries(THEMES).filter(([k]) => k !== "other").map(([k, v]) => [k, `Major: ${lowerFirst(v)}`])),
};

/**
 * Where the escalation facts come from, quoted in full: the County's Retail
 * Food Facility Operator's Guide, p. 8, on what brings a closer look.
 */
export const GUIDE_CRITERIA = "recurring major violations, recurring scores of less than 90%, or recurring facility closures";
export const ESCALATION_NOTE =
  `The three escalation facts follow the County's own criteria for a closer look at a place (Retail Food Facility Operator's Guide, p. 8): “${GUIDE_CRITERIA}”. The County may already be acting on these places.`;

export const VISIT_LABELS = {
  routine: "routine inspection",
  reinspection: "reinspection",
  followup: "re-grade or reopening visit",
  complaint: "complaint visit",
};

export const SEVERITY_LABELS = { major: "major violation", minor: "minor violation", grp: "good-retail-practice item" };

/** Our reading of a closure's reason, in a few words. */
export const CLOSURE_LABELS = { health: "health hazard", permit: "permit matter", other: "reason not given" };

/**
 * The pipeline's readings, each with its rule in one line. Anything the site
 * says that is not the County's own text carries one of these.
 */
export const OUR_READING = {
  followup: "a routine inspection within 30 days after a B, a C or a closure is read as a re-grade or reopening visit.",
  health: "a major violation was cited that day.",
  permit: "no major violation was cited that day and the inspector's notes mention a permit, so we read the closure as a permit matter.",
  other: "the record does not say why.",
  themes: "each item is put under a theme from the County's item text.",
  flags: "read from the 12 months before the list date, and 24 months for the three escalation facts.",
};

const typeOf = (i) => i?.type ?? "routine";
export const visitLabel = (type) => VISIT_LABELS[type ?? "routine"] ?? String(type);
export const isGraded = (i) => GRADES.includes(i?.grade);

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
  const closedBy = (reason) => list.filter((i) => i.closed && i.closure === reason).length;
  return {
    count: list.length,
    routineCount: list.filter((i) => typeOf(i) === "routine").length,
    first: list[0],
    last,
    lastScore: typeof last.score === "number" ? last.score : null,
    majors36: sum(recent36, "major"),
    minors36: sum(recent36, "minor"),
    grp36: sum(recent36, "grp"),
    closures: closedBy("health"),
    permitClosures: closedBy("permit"),
    otherClosures: closedBy("other"),
    reinspections: list.filter((i) => i.type === "reinspection").length,
    followups: list.filter((i) => i.type === "followup").length,
    complaints: list.filter((i) => i.type === "complaint").length,
  };
}

/** Items cited, grouped by theme, worst first: majors, then count, then recency. */
export function themeCounts(violations = []) {
  const by = new Map();
  for (const v of violations ?? []) {
    const key = THEMES[v.theme] ? v.theme : "other";
    const t = by.get(key) ?? { theme: key, label: THEMES[key], count: 0, major: 0, minor: 0, grp: 0, complaint: 0, last: null };
    t.count += 1;
    if (v.severity === "major") t.major += 1;
    else if (v.severity === "grp") t.grp += 1;
    else t.minor += 1;
    if (v.visit === "complaint") t.complaint += 1;
    if (!t.last || v.date > t.last) t.last = v.date;
    by.set(key, t);
  }
  return [...by.values()].sort((a, b) => b.major - a.major || b.count - a.count || (b.last ?? "").localeCompare(a.last ?? ""));
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

export const typeLabel = (type) => TYPE_LABELS[type] ?? TYPE_LABELS.other;
export const typePlural = (type) => TYPE_PLURALS[type] ?? TYPE_PLURALS.other;
