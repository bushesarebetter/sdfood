/**
 * "What the County's record shows": the facts in the 12 months before a
 * place's last visit, from its place file, in the County's own words.
 *
 * Each fact has a title, the County's record as lines (its status text, its
 * inspection type, its notes and its item text verbatim), and, when any part
 * of it is the pipeline's reading rather than the County's text, an "Our
 * reading" line with the rule. A fact is a closure (or an "Approved to Reopen"
 * no closure could be placed before), a theme with a major violation (or a
 * minor one at two or more inspections), a B or C grade, two or more
 * reinspections, or a Site Investigation or Environmental visit. Nothing here
 * instructs anyone or judges the place.
 *
 * The closure lines come from `closureEntries`, which the pasted record text
 * (lib/ask.js) uses too, so the panel and the text never word a closure
 * differently.
 *
 * These facts count back from the place's last visit, so they read its own
 * record. The index's `flags` count back from the list date instead
 * (OUR_READING.flags).
 *
 * The theme facts are counted from the items the export lists (at most
 * MAX_ITEMS a place, majors first). When the County's records in the 12
 * months cite more major and minor violations than the list holds for them,
 * the theme facts say "Showing N of M" (windowItemsNote).
 */
import {
  OUR_READING, THEMES, SEVERITY_LABELS, FIELD_TYPES, closureWords, closureEnd, countyNotes, countyType, isGraded,
  lastInspection, recordGradeText, visitPhrase, withinMonths,
} from "./inspections.js";
import { fmtDate, fmtMonth } from "./dates.js";

export const WINDOW_MONTHS = 12;
const MAX_QUOTES = 3;
const MAX_LISTED = 4;
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const sentenceCase = (s) => `${s.charAt(0).toUpperCase()}${s.slice(1)}`;

const listed = (xs, fmt) => {
  const shown = xs.slice(0, MAX_LISTED).map(fmt).join("; ");
  return xs.length > MAX_LISTED ? `${shown}; and ${xs.length - MAX_LISTED} more` : shown;
};

/** A record by the County's words: "Re-inspection, “Complete”, September 2, 2026". */
const recordWords = (j) =>
  `${countyType(j) ?? sentenceCase(visitPhrase(j))}, “${j.status || "Complete"}”${isGraded(j) ? `, graded ${recordGradeText(j)}` : ""}, ${fmtDate(j.date)}`;

/** The items the export lists for a record's day and visit type, in the County's words. */
function itemsThatDay(p, i) {
  const items = (p?.violations ?? []).filter((v) => v.date === i.date && (v.visit ?? i.type) === (i.type ?? "routine"));
  if (items.length) {
    const words = (v) => `${v.code ? `item ${v.code}, ` : ""}“${v.description || THEMES[v.theme] || "item"}” (${SEVERITY_LABELS[v.severity] ?? v.severity})`;
    return `Items cited that day: ${listed(items, words)}.`;
  }
  return (i.major || 0) + (i.minor || 0) + (i.grp || 0) === 0 ? "No items were cited that day." : null;
}

/** One record that starts a closure episode: its title, the County's lines, and our reading. */
function closureEntry(p, list, idx) {
  const i = list[idx];
  const w = closureWords(i);
  const ct = countyType(i);
  let first = `${i.status || "Ordered Closed"} on ${fmtDate(i.date)}${ct ? ` (County type: ${ct})` : ""}`;
  if (w.kind === "inferred" && i.score == null && !isGraded(i)) first += ", with no score and no grade";
  const county = [`${first}.`];
  const notes = countyNotes(i);
  if (notes.length) county.push(`County ${notes.length === 1 ? "note" : "notes"}: ${notes.join("; ")}.`);
  // A closure we read as "other" states what the County did cite that day, so no one reads it as silent.
  if (i.closure === "other" || !i.closure) {
    const items = itemsThatDay(p, i);
    if (items) county.push(items);
  }
  const end = closureEnd(list, idx);
  if (end.reopen) {
    county.push(end.reopen.date ? `${end.reopen.status} on ${fmtDate(end.reopen.date)}.` : "Approved to Reopen afterwards.");
  } else if (i.reopened === false && !end.laterReopen) {
    if (end.nextGraded) {
      county.push(`No “Approved to Reopen” on the County's published record before the next graded visit, on ${fmtDate(end.nextGraded.date)}.`);
    } else {
      county.push("No “Approved to Reopen” and no graded visit after it on the County's published record.");
      if (end.later.length) county.push(`Later County records: ${listed(end.later, recordWords)}.`);
    }
  }
  const at = i.type === "complaint" && !ct ? " It was at a visit we read as a complaint or other field visit." : "";
  return {
    key: `closure-${i.date}`,
    date: i.date,
    title: w.kind === "order" ? "Ordered closed" : w.title,
    county,
    reading: `Our reading: ${w.reading}${at}`,
    // A health closure, or one with nothing after it on the record, leads the facts.
    order: i.closure === "health" || end.open ? 0 : 5,
  };
}

/** An "Approved to Reopen" before which no closure could be placed. */
function reopenOnlyEntry(i) {
  const ct = countyType(i);
  return {
    key: `reopen-${i.date}`,
    date: i.date,
    title: "Approved to Reopen, no closure placed",
    county: [`${i.status || "Approved to Reopen"} on ${fmtDate(i.date)}${ct ? ` (County type: ${ct})` : ""}.`],
    reading: `Our reading: ${OUR_READING.reopenOnly}`,
    order: 5,
  };
}

/**
 * Every closure on a place's record, oldest first, and every "Approved to
 * Reopen" no closure could be placed before, each as { key, date, title,
 * county: [lines], reading, order }. `inWindow(date)` limits the records read.
 * The one wording of a closure: the facts panel and the pasted record text
 * both take it from here.
 */
export function closureEntries(p, { inWindow = () => true } = {}) {
  const list = (p?.inspections ?? []).filter((i) => i?.date);
  const out = [];
  list.forEach((i, idx) => {
    if (!inWindow(i.date)) return;
    if (i.closed) out.push(closureEntry(p, list, idx));
    else if (i.reopen_without_closure === true) out.push(reopenOnlyEntry(i));
  });
  return out;
}

/** The closure entries as plain lines: "Ordered closed: <County lines> Our reading: ...". */
export function closureLines(p, opts = {}) {
  return closureEntries(p, opts).map((e) => `${e.title}: ${e.county.join(" ")} ${e.reading}`);
}

/**
 * Whether the items the export lists for the window hold every major and minor violation the County's
 * records in it count (each record's `major` and `minor`): the list is cut at MAX_ITEMS, majors first,
 * so a place past the cut lists fewer. "Showing N of M ..." when they differ, else null. Read from the
 * records themselves, so it holds whether or not the export gives `theme_counts`, which count the 36
 * months, not these 12.
 */
function windowItemsNote(p, inWindow) {
  const count = (x) => (Number.isInteger(x) && x > 0 ? x : 0);
  const recorded = (p?.inspections ?? []).filter((i) => i?.date && inWindow(i.date)).reduce((a, i) => a + count(i.major) + count(i.minor), 0);
  const listed = (p?.violations ?? []).filter((v) => inWindow(v.date) && (v.severity === "major" || v.severity === "minor")).length;
  if (recorded <= listed) return null;
  return `Showing ${listed} of the ${recorded} major and minor violations the County's records in these 12 months cite, majors first: ` +
    "a theme's count of minor violations, and its latest date, may be low, and a theme with minor violations at two inspections may be left out.";
}

function themeFacts(p, inWindow) {
  const by = new Map();
  for (const v of p?.violations ?? []) {
    if (!THEMES[v.theme] || !inWindow(v.date)) continue;
    if (v.severity !== "major" && v.severity !== "minor") continue;
    const t = by.get(v.theme) ?? { majors: 0, minors: 0, minorDates: new Set(), complaint: 0, last: null, texts: new Map() };
    if (v.severity === "major") t.majors += 1;
    else {
      t.minors += 1;
      t.minorDates.add(v.date);
    }
    if (v.visit === "complaint") t.complaint += 1;
    if (!t.last || v.date > t.last) t.last = v.date;
    if (v.description) t.texts.set(v.description, (t.texts.get(v.description) ?? 0) + (v.severity === "major" ? 100 : 1));
    by.set(v.theme, t);
  }
  // Counted from the items the export lists: when they are fewer than the records count, the reading says so.
  const cut = windowItemsNote(p, inWindow);
  const out = [];
  for (const [theme, t] of by) {
    if (!(t.majors > 0 || t.minorDates.size >= 2)) continue;
    const parts = [t.majors ? plural(t.majors, "major violation") : null, t.minors ? plural(t.minors, "minor violation") : null].filter(Boolean);
    const quotes = [...t.texts.entries()].sort((a, b) => b[1] - a[1]).slice(0, MAX_QUOTES).map(([d]) => `“${d}”`);
    const county = [
      `${parts.join(" and ")} cited in the 12 months before its last visit, most recently in ${fmtMonth(t.last)}${t.complaint ? ` (${t.complaint} found at a ${FIELD_TYPES} visit)` : ""}.`,
    ];
    if (quotes.length) county.push(`As the County wrote ${quotes.length === 1 ? "it" : "them"}: ${quotes.join("; ")}.`);
    const reading = `Our reading: ${OUR_READING.themes}${cut ? ` ${cut}` : ""}`;
    out.push({ key: `theme-${theme}`, title: THEMES[theme], county, reading, order: t.majors ? 1 : 4, weight: t.majors });
  }
  // No theme to carry the line: it stands alone, so a cut list never reads as a quiet year.
  if (cut && !out.length) out.push({ key: "theme-cut", title: "Items cited", county: [cut], reading: null, order: 4, weight: 0 });
  return out.sort((a, b) => a.order - b.order || b.weight - a.weight);
}

function gradeFact(p, inWindow) {
  const g = p?.grade;
  // The letter itself, whether or not a later closure leads the grade views.
  if (!g || !["A", "B", "C"].includes(g.grade)) return null;
  if ((g.grade === "B" || g.grade === "C") && inWindow(g.date)) {
    return { key: "grade", title: `A ${g.grade} grade`, county: [`Graded ${recordGradeText(g)} on ${fmtDate(g.date)}.`], reading: null, order: 2 };
  }
  const r = g.replaced;
  if (r && (r.grade === "B" || r.grade === "C") && inWindow(r.date)) {
    return {
      key: "grade",
      title: `A ${r.grade} grade, then ${g.grade}`,
      county: [`Graded ${recordGradeText(r)} on ${fmtDate(r.date)}, then ${recordGradeText(g)} on ${fmtDate(g.date)}.`],
      reading: "Our reading: the later visit was a re-grade.",
      order: 2,
    };
  }
  return null;
}

/** The Site Investigation and Environmental records, by the County's own type where the export gives it. */
function fieldVisitFact(list, inWindow) {
  const visits = list.filter((i) => i.type === "complaint" && inWindow(i.date));
  if (!visits.length) return null;
  const byType = new Map();
  for (const i of visits) {
    const ct = countyType(i);
    if (ct) byType.set(ct, (byType.get(ct) ?? 0) + 1);
  }
  const typed = [...byType.values()].reduce((a, n) => a + n, 0);
  const parts = [...byType.entries()].map(([ct, n]) => plural(n, `${ct} record`));
  if (typed < visits.length) parts.push(plural(visits.length - typed, "record", "records") + " with no County type in this export");
  return {
    key: "complaint",
    title: typed ? `${FIELD_TYPES} visits` : "Complaint or other field visits",
    county: [`${parts.join(" and ")} in the 12 months before its last visit.`],
    reading: `Our reading: ${OUR_READING.complaint}`,
    order: 3,
  };
}

/** Every fact the last 12 months of the record support, closures first. */
export function recordFacts(p) {
  const last = lastInspection(p);
  if (!last?.date) return [];
  const inWindow = (d) => withinMonths(d, last.date, WINDOW_MONTHS);
  const list = (p.inspections ?? []).filter((i) => i?.date);
  const facts = [...closureEntries(p, { inWindow }).reverse().map(({ date, ...f }) => f), ...themeFacts(p, inWindow)];
  const grade = gradeFact(p, inWindow);
  if (grade) facts.push(grade);
  const reinspections = list.filter((i) => i.type === "reinspection" && inWindow(i.date)).length;
  if (reinspections >= 2) {
    facts.push({ key: "repeat", title: "Repeat reinspections", county: [`${plural(reinspections, "reinspection")} in the 12 months before its last visit.`], reading: null, order: 3 });
  }
  const field = fieldVisitFact(list, inWindow);
  if (field) facts.push(field);
  return facts.sort((a, b) => a.order - b.order).map(({ order, weight, ...f }) => f);
}
