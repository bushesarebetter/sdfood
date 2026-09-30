/**
 * A place as text to paste: a citation, and the record in plain lines. Both
 * state the County's record, the grade through lib/grades.js, and, in
 * `bands` mode only, the band. Neither ever gives a position. Closures are
 * worded by lib/recordFacts.js closureEntries, as the place's panel words
 * them.
 */
import { inspectionStats, themeCounts, themeCountsNote, typeLabel, visitPhrase, recordGradeText, withinMonths, SAME_CLOSURE } from "./inspections.js";
import { gradeView } from "./grades.js";
import { closureLines } from "./recordFacts.js";
import { fmtMonth } from "./dates.js";
import { gradeContextSentence } from "./framing.js";
import { shownBand } from "./marks.js";
import { SITE, STUDENT_NOTE } from "../site.js";

const today = () => new Date().toISOString().slice(0, 10);
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const RECORD_MONTHS = 36;

/** "band 2 on the students' point rule", or null outside `bands` mode, for a place in no band, or on an expired export. */
export function standing(p, { mode = "record", expired = false } = {}) {
  if (expired) return null;
  const b = shownBand(p, { mode });
  return b ? `band ${b} on the students' point rule` : null;
}

/** A citation for one place, for a memo, a report or a paper. */
export function citation({ place, url, meta = null, mode = "record", expired = false }) {
  const year = new Date().getFullYear();
  const where = standing(place, { mode, expired });
  const run = meta?.run ? `, run ${meta.run}` : "";
  return `${SITE.citationAuthors} (${year}). ${SITE.siteTitle}${run}: ${place.name}, ${place.address}${where ? `, ${where}` : ""}. ${url}. Retrieved ${today()}.`;
}

/** "; 2 closures (3 “Ordered Closed” records; ...)" for the record-wide counts line, or "". */
function closureCounts(s) {
  const parts = [];
  if (s.closureEpisodes) {
    const notes = [plural(s.orderedClosedRecords, "“Ordered Closed” record")];
    if (s.orderedClosedRecords > (s.orderClosures ?? 0)) notes.push(SAME_CLOSURE);
    if (s.selfClosures) notes.push(`${s.selfClosures} “Self Closed”`);
    if (s.inferredClosures) notes.push(`${s.inferredClosures} shown only by a later “Approved to Reopen”`);
    parts.push(`${plural(s.closureEpisodes, "closure")} in our reading (${notes.join("; ")}): ${s.closures} for a health hazard${s.permitClosures ? `, ${s.permitClosures} for a permit matter` : ""}${s.otherClosures ? `, ${s.otherClosures} with no major violation cited` : ""}`);
  } else if (s.orderedClosedRecords) {
    parts.push(plural(s.orderedClosedRecords, "“Ordered Closed” record"));
  }
  if (s.reopenedWithoutClosure) parts.push(`${plural(s.reopenedWithoutClosure, "“Approved to Reopen” record")} no closure could be placed before (our reading)`);
  return parts.length ? `; ${parts.join("; ")}` : "";
}

/**
 * The record as plain text, to paste into an email or a note. It states what
 * the County recorded, marks our readings, and says where to check it.
 */
export function recordText({ place, url, meta = null, mode = "record", expired = false }) {
  const p = place;
  const s = inspectionStats(p);
  const g = gradeView(p.grade);
  const themes = themeCounts(p).slice(0, 4);
  const where = standing(p, { mode, expired });
  const run = meta?.run ? `, run ${meta.run}` : "";
  const lines = [
    `${p.name}`,
    `${p.address}`,
    `${typeLabel(p.facility_type)}${p.council_district ? `, council district ${p.council_district}` : ""}; County permit record ${p.facility_id}`,
    "",
  ];
  if (where) lines.push(`${SITE.siteTitle}${run}: ${where}${typeof p.points === "number" ? `, ${p.points} points` : ""}.`, "");
  lines.push(g.sentence);
  if (g.replacedSentence) lines.push(g.replacedSentence);
  lines.push(gradeContextSentence(meta));
  if (s) {
    const last = s.last;
    const grade = recordGradeText(last);
    lines.push(`Last visit: ${last.date}, ${visitPhrase(last)}${last.status ? `; County status: ${last.status}` : ""}${last.score != null ? `, score ${last.score}` : ""}${grade ? `, grade ${grade}` : ""}.`);
    lines.push(`In the three years before the last visit: ${s.majors36} major violations, ${s.minors36} minor violations and ${s.grp36} good-retail-practice items across ${plural(s.count36, "County record")}.`);
    lines.push(`Since ${fmtMonth(s.first.date)}: ${plural(s.count, "County record")}; ${plural(s.reinspections, "reinspection")}${closureCounts(s)}.`);
    if (s.followups) lines.push(`Our reading: ${s.followups} of those records ${s.followups === 1 ? "is a re-grade or reopening visit" : "are re-grade or reopening visits"}.`);
    // Every closure in the same three years, oldest first, worded as the place's page words it.
    const closures = closureLines(p, { inWindow: (d) => withinMonths(d, last.date, RECORD_MONTHS) });
    if (closures.length) {
      lines.push("Closures and reopenings in the three years before the last visit:");
      for (const c of closures) lines.push(`  ${c}`);
    }
  }
  if (themes.length) {
    lines.push("Items by theme (our reading of the County's item text):");
    for (const t of themes) lines.push(`  ${t.label}: ${t.count} ${t.count === 1 ? "item" : "items"}${t.major ? `, ${t.major} major` : ""}, latest ${t.last}`);
    const note = themeCountsNote(p);
    if (note) lines.push(`  ${note}`);
  }
  lines.push("");
  lines.push(`The County's own record: ${SITE.regulator.resultsUrl}`);
  lines.push(`This page: ${url}`);
  lines.push(STUDENT_NOTE);
  return lines.join("\n");
}
