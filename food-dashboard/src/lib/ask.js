/**
 * A place as text to paste: a citation, and the record in plain lines. Both
 * state the County's record, the grade through lib/grades.js, and, in
 * `bands` mode only, the band. Neither ever gives a position.
 */
import { inspectionStats, themeCounts, typeLabel, visitLabel, recordGradeText } from "./inspections.js";
import { gradeView } from "./grades.js";
import { gradeContextSentence } from "./framing.js";
import { shownBand } from "./marks.js";
import { SITE, STUDENT_NOTE } from "../site.js";

const today = () => new Date().toISOString().slice(0, 10);

/** "band 2 on the published rule", or null outside `bands` mode, for a place in no band, or on an expired export. */
export function standing(p, { mode = "record", expired = false } = {}) {
  if (expired) return null;
  const b = shownBand(p, { mode });
  return b ? `band ${b} on the published rule` : null;
}

/** A citation for one place, for a memo, a report or a paper. */
export function citation({ place, url, meta = null, mode = "record", expired = false }) {
  const year = new Date().getFullYear();
  const where = standing(place, { mode, expired });
  const run = meta?.run ? `, run ${meta.run}` : "";
  return `${SITE.citationAuthors} (${year}). ${SITE.siteTitle}${run}: ${place.name}, ${place.address}${where ? `, ${where}` : ""}. ${url}. Retrieved ${today()}.`;
}

/**
 * The record as plain text, to paste into an email or a note. It states what
 * the County recorded, marks our readings, and says where to check it.
 */
export function recordText({ place, url, meta = null, mode = "record", expired = false }) {
  const p = place;
  const s = inspectionStats(p);
  const g = gradeView(p.grade);
  const themes = themeCounts(p.violations).slice(0, 4);
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
    lines.push(`Last visit: ${last.date}, ${visitLabel(last.type)}${last.status ? ` (County status: ${last.status})` : ""}${last.score != null ? `, score ${last.score}` : ""}${grade ? `, grade ${grade}` : ""}.`);
    lines.push(`In the three years before the last visit: ${s.majors36} major violations, ${s.minors36} minor violations and ${s.grp36} good-retail-practice items across ${s.count} County records; ${s.reinspections} reinspections.`);
    if (s.followups) lines.push(`Our reading: ${s.followups} of those records are re-grade or reopening visits.`);
  }
  if (themes.length) {
    lines.push("Items by theme (our reading of the County's item text):");
    for (const t of themes) lines.push(`  ${t.label}: ${t.count} ${t.count === 1 ? "item" : "items"}${t.major ? `, ${t.major} major` : ""}, latest ${t.last}`);
  }
  lines.push("");
  lines.push(`The County's own record: ${SITE.regulator.resultsUrl}`);
  lines.push(`This page: ${url}`);
  lines.push(STUDENT_NOTE);
  return lines.join("\n");
}
