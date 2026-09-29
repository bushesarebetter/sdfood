/**
 * A place's grade, in every view, from one helper.
 *
 * The index carries `grade`: the latest letter the County gave the place at a
 * routine or re-grade visit, from a single County record, with `replaced`
 * when that letter came from a visit we read as a re-grade after a routine
 * B or C, and `open_closure` when the place's last closure has no "Approved
 * to Reopen" and no graded visit after it on the published record. Every view
 * (the panel, the place page, the phone sheet, the record summary, the table,
 * the CSV, the citation) takes its grade text from `gradeView`, so no view can
 * lead with a replaced grade or show a letter another view does not.
 *
 * `graded` says whether a view leads with the letter ("Grade A 94, Jul 2026").
 * It is false when the County has no letter on record, and when a closure is
 * open after the letter (`closedOpen`): the County posts no grade card while
 * it has a place closed for a health hazard (County Code sec. 61.107(a)), so
 * an older A must not read as the place's grade. The views then lead with
 * `text` ("Closed Sep 2026, no reopening on record"), and `sentence` gives the
 * closure first and the latest letter after it (`letter`, `lastGrade`); the
 * CSV keeps the letter in its columns and adds `open_closure_date`. None of it
 * says the place is closed now: a later visit the County did not grade may
 * have been its reopening.
 */
import { fmtDate, fmtShort } from "./dates.js";
import { GRADES, CLOSURES, CLOSURE_LABELS } from "./inspections.js";

export const GRADE_SWATCH = { A: "#C9C1B0", B: "#D97706", C: "#7F1D1D" };
// Amber as text is darkened for contrast on paper; A is drawn in ink.
export const GRADE_TEXT = { A: null, B: "#9A4A07", C: "#7F1D1D" };
/** A closure with no reopening on record: the colour the record chart gives a closure. */
export const OPEN_CLOSURE_COLOR = "#7F1D1D";

const ISO = /^\d{4}-\d{2}-\d{2}$/;
const valid = (g) => g && GRADES.includes(g.grade);
const withScore = (g) => (typeof g.score === "number" ? `${g.grade} (${g.score})` : g.grade);

/** The grade object's `open_closure`, when it is well formed: { date, reason, status, laterUngraded }. */
export function openClosure(grade) {
  const o = grade?.open_closure;
  if (!o || typeof o !== "object" || !ISO.test(o.date ?? "")) return null;
  return {
    date: o.date,
    reason: CLOSURES.includes(o.reason) ? o.reason : null,
    // The County's status text on the record that started it, where the export gives it.
    status: typeof o.status === "string" && o.status.trim() ? o.status.trim() : null,
    laterUngraded: Array.isArray(o.later_ungraded) ? o.later_ungraded.filter((d) => ISO.test(d ?? "")) : [],
  };
}

const EMPTY_CSV = { grade: "", grade_score: "", grade_date: "", replaced_grade: "", replaced_score: "", replaced_date: "", open_closure_date: "" };

/** The lead for a place whose last closure is open, and the last letter before it (or none). */
function openView(oc, grade) {
  const letter = valid(grade) ? grade : null;
  const r = letter && valid(letter.replaced) ? letter.replaced : null;
  // Without the status text, "a closure": a Self Closed record must not read as a County order.
  const what = oc.status ? `“${oc.status}”` : "a closure";
  const tag = oc.status ? oc.status.charAt(0).toUpperCase() + oc.status.slice(1).toLowerCase() : "Closed";
  const reason = oc.reason ? ` (our reading: ${CLOSURE_LABELS[oc.reason]})` : "";
  const later = oc.laterUngraded.length
    ? ` The County's later ${oc.laterUngraded.length === 1 ? "record, on" : "records, on"} ${oc.laterUngraded.map(fmtDate).join(", ")}, ${oc.laterUngraded.length === 1 ? "has" : "have"} no grade.`
    : "";
  const before = letter ? ` The latest County grade on record: ${withScore(letter)}, ${fmtDate(letter.date)}.` : " No County grade is on record for this place.";
  const text = `${tag} ${fmtShort(oc.date)}, no reopening on record`;
  return {
    graded: false,
    closedOpen: true,
    openClosure: oc,
    letter: letter?.grade ?? null,
    lastGrade: letter ? { text: withScore(letter), date: letter.date } : null,
    text,
    short: text,
    withDate: `${tag.toLowerCase()} ${fmtDate(oc.date)}, no reopening on record`,
    sentence: `The County's record shows ${what} on ${fmtDate(oc.date)}${reason}, and no “Approved to Reopen” and no graded visit after it.${later}${before}`,
    // The replaced grade is older than the last letter; the closure and that letter are what the views state.
    replaced: null,
    replacedSentence: null,
    swatch: OPEN_CLOSURE_COLOR,
    textColor: OPEN_CLOSURE_COLOR,
    csv: {
      ...EMPTY_CSV,
      grade: letter?.grade ?? "",
      grade_score: typeof letter?.score === "number" ? letter.score : "",
      grade_date: letter?.date ?? "",
      replaced_grade: r?.grade ?? "",
      replaced_score: typeof r?.score === "number" ? r.score : "",
      replaced_date: r?.date ?? "",
      open_closure_date: oc.date,
    },
  };
}

export function gradeView(grade) {
  const oc = openClosure(grade);
  if (oc) return openView(oc, grade);
  if (!valid(grade)) {
    return {
      graded: false,
      closedOpen: false,
      openClosure: null,
      letter: null,
      lastGrade: null,
      text: "Not graded by the County",
      short: "not graded",
      withDate: "not graded by the County",
      sentence: "No County grade is on record for this place in this export.",
      replaced: null,
      replacedSentence: null,
      swatch: null,
      textColor: null,
      csv: { ...EMPTY_CSV },
    };
  }
  const r = valid(grade.replaced) ? grade.replaced : null;
  const text = withScore(grade);
  return {
    graded: true,
    closedOpen: false,
    openClosure: null,
    letter: grade.grade,
    lastGrade: { text, date: grade.date },
    text,
    short: `${grade.grade}${typeof grade.score === "number" ? ` ${grade.score}` : ""}, ${fmtShort(grade.date)}`,
    withDate: `${text}, ${fmtDate(grade.date)}`,
    sentence: `Latest County grade on record: ${text}, ${fmtDate(grade.date)}.`,
    replaced: r ? { text: withScore(r), date: r.date } : null,
    // Always after the posted grade, never in its place.
    replacedSentence: r
      ? `Before it, the routine inspection on ${fmtDate(r.date)} was graded ${withScore(r)}. Our reading: the later visit was a re-grade.`
      : null,
    swatch: GRADE_SWATCH[grade.grade],
    textColor: GRADE_TEXT[grade.grade],
    csv: {
      ...EMPTY_CSV,
      grade: grade.grade,
      grade_score: typeof grade.score === "number" ? grade.score : "",
      grade_date: grade.date ?? "",
      replaced_grade: r?.grade ?? "",
      replaced_score: typeof r?.score === "number" ? r.score : "",
      replaced_date: r?.date ?? "",
    },
  };
}
