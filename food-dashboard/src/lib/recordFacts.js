/**
 * "What the County's record shows": the facts in the 12 months before a
 * place's last visit, from its place file, in the County's own words.
 *
 * Each fact has a title, the County's record as lines (its status text and
 * item text verbatim), and, when any part of it is the pipeline's reading
 * rather than the County's text, an "Our reading" line with the rule. A fact
 * is a closure, a theme with a major violation (or a minor one at two or more
 * inspections), a B or C grade, two or more reinspections, or a complaint
 * visit. Nothing here instructs anyone or judges the place.
 */
import { OUR_READING, THEMES, lastInspection, recordGradeText, withinMonths } from "./inspections.js";
import { gradeView } from "./grades.js";
import { fmtDate, fmtMonth } from "./dates.js";

export const WINDOW_MONTHS = 12;
const MAX_QUOTES = 3;
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function closureFacts(list, inWindow) {
  const out = [];
  list.forEach((i, idx) => {
    if (!i.closed || !inWindow(i.date)) return;
    const county = [`${i.status || "Ordered Closed"} on ${fmtDate(i.date)}${i.type === "complaint" ? ", at a complaint visit" : ""}.`];
    if (i.reopened === true) {
      const back = list.slice(idx + 1).find((j) => /approved to reopen/i.test(j.status ?? ""));
      county.push(back ? `${back.status} on ${fmtDate(back.date)}.` : "Approved to Reopen afterwards.");
    }
    out.push({
      key: `closure-${i.date}`,
      title: "Ordered closed",
      county,
      reading: `Our reading: ${OUR_READING[i.closure] ?? OUR_READING.other}`,
      order: i.closure === "health" ? 0 : 5,
    });
  });
  return out.reverse();
}

function themeFacts(violations, inWindow) {
  const by = new Map();
  for (const v of violations ?? []) {
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
  const out = [];
  for (const [theme, t] of by) {
    if (!(t.majors > 0 || t.minorDates.size >= 2)) continue;
    const parts = [t.majors ? plural(t.majors, "major violation") : null, t.minors ? plural(t.minors, "minor violation") : null].filter(Boolean);
    const quotes = [...t.texts.entries()].sort((a, b) => b[1] - a[1]).slice(0, MAX_QUOTES).map(([d]) => `“${d}”`);
    const county = [
      `${parts.join(" and ")} cited in the 12 months before its last visit, most recently in ${fmtMonth(t.last)}${t.complaint ? ` (${t.complaint} found at a complaint visit)` : ""}.`,
    ];
    if (quotes.length) county.push(`As the County wrote ${quotes.length === 1 ? "it" : "them"}: ${quotes.join("; ")}.`);
    out.push({ key: `theme-${theme}`, title: THEMES[theme], county, reading: `Our reading: ${OUR_READING.themes}`, order: t.majors ? 1 : 4, weight: t.majors });
  }
  return out.sort((a, b) => a.order - b.order || b.weight - a.weight);
}

function gradeFact(p, inWindow) {
  const g = p?.grade;
  const view = gradeView(g);
  if (!view.graded) return null;
  if ((g.grade === "B" || g.grade === "C") && inWindow(g.date)) {
    return { key: "grade", title: `A ${g.grade} grade`, county: [`Graded ${view.text} on ${fmtDate(g.date)}.`], reading: null, order: 2 };
  }
  const r = g.replaced;
  if (r && (r.grade === "B" || r.grade === "C") && inWindow(r.date)) {
    return {
      key: "grade",
      title: `A ${r.grade} grade, then ${g.grade}`,
      county: [`Graded ${recordGradeText(r)} on ${fmtDate(r.date)}, then ${view.text} on ${fmtDate(g.date)}.`],
      reading: "Our reading: the later visit was a re-grade.",
      order: 2,
    };
  }
  return null;
}

/** Every fact the last 12 months of the record support, closures first. */
export function recordFacts(p) {
  const last = lastInspection(p);
  if (!last?.date) return [];
  const inWindow = (d) => withinMonths(d, last.date, WINDOW_MONTHS);
  const list = (p.inspections ?? []).filter((i) => i?.date);
  const facts = [...closureFacts(list, inWindow), ...themeFacts(p.violations, inWindow)];
  const grade = gradeFact(p, inWindow);
  if (grade) facts.push(grade);
  const reinspections = list.filter((i) => i.type === "reinspection" && inWindow(i.date)).length;
  if (reinspections >= 2) {
    facts.push({ key: "repeat", title: "Repeat reinspections", county: [`${plural(reinspections, "reinspection")} in the 12 months before its last visit.`], reading: null, order: 3 });
  }
  const complaints = list.filter((i) => i.type === "complaint" && inWindow(i.date)).length;
  if (complaints) {
    facts.push({ key: "complaint", title: "Complaint visits", county: [`${plural(complaints, "complaint visit")} in the 12 months before its last visit.`], reading: null, order: 3 });
  }
  return facts.sort((a, b) => a.order - b.order).map(({ order, weight, ...f }) => f);
}
