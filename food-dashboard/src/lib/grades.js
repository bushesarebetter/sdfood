/**
 * A place's grade, in every view, from one helper.
 *
 * The index carries `grade`: the latest letter the County gave the place at a
 * routine or re-grade visit, from a single County record, with `replaced`
 * when that letter came from a visit we read as a re-grade after a routine
 * B or C. Every view (the panel, the place page, the phone sheet, the record
 * summary, the table, the CSV, the citation) takes its grade text from
 * `gradeView`, so no view can lead with a replaced grade or show a letter
 * another view does not.
 */
import { fmtDate, fmtShort } from "./dates.js";
import { GRADES } from "./inspections.js";

export const GRADE_SWATCH = { A: "#C9C1B0", B: "#D97706", C: "#7F1D1D" };
// Amber as text is darkened for contrast on paper; A is drawn in ink.
export const GRADE_TEXT = { A: null, B: "#9A4A07", C: "#7F1D1D" };

const valid = (g) => g && GRADES.includes(g.grade);
const withScore = (g) => (typeof g.score === "number" ? `${g.grade} (${g.score})` : g.grade);

export function gradeView(grade) {
  if (!valid(grade)) {
    return {
      graded: false,
      letter: null,
      text: "Not graded by the County",
      short: "not graded",
      withDate: "not graded by the County",
      sentence: "No County grade is on record for this place in this export.",
      replaced: null,
      replacedSentence: null,
      swatch: null,
      textColor: null,
      csv: { grade: "", grade_score: "", grade_date: "", replaced_grade: "", replaced_score: "", replaced_date: "" },
    };
  }
  const r = valid(grade.replaced) ? grade.replaced : null;
  const text = withScore(grade);
  return {
    graded: true,
    letter: grade.grade,
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
      grade: grade.grade,
      grade_score: typeof grade.score === "number" ? grade.score : "",
      grade_date: grade.date ?? "",
      replaced_grade: r?.grade ?? "",
      replaced_score: typeof r?.score === "number" ? r.score : "",
      replaced_date: r?.date ?? "",
    },
  };
}
