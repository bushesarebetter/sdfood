import { test } from "node:test";
import assert from "node:assert/strict";
import * as inspections from "../src/lib/inspections.js";

const { inspectionStats, themeCounts, lastInspection, visitLabel, recordGradeText, typeLabel, THEMES, FLAG_KEYS, FLAG_LABELS, OUR_READING } = inspections;

const visit = (date, type, extra = {}) => ({ date, status: "Complete", type, score: null, grade: null, major: 0, minor: 0, grp: 0, closed: false, closure: null, reopened: null, ...extra });
const routine = (date, score, grade, extra = {}) => visit(date, "routine", { score, grade, ...extra });

const record = {
  inspections: [
    routine("2022-03-01", 96, "A", { major: 1, minor: 1, grp: 1 }),
    routine("2023-10-12", 94, "A", { grp: 2 }),
    routine("2024-05-20", 95, "A", { major: 1, minor: 2, grp: 1 }),
    visit("2024-05-27", "reinspection", { minor: 1 }),
    routine("2025-01-09", null, null, { status: "Ordered Closed", major: 2, minor: 5, grp: 3, closed: true, closure: "health", reopened: true }),
    visit("2025-01-10", "followup", { status: "Approved to Reopen", score: 91, grade: "A", minor: 1 }),
    visit("2025-03-01", "complaint"),
    routine("2025-05-01", 97, "A", { status: "Ordered Closed", closed: true, closure: "permit", reopened: false }),
    routine("2025-09-03", 82, "B", { major: 2, minor: 4, grp: 2 }),
  ],
  violations: [
    { date: "2025-09-03", visit: "routine", code: "7", theme: "temperature", severity: "major" },
    { date: "2025-09-03", visit: "routine", code: "23", theme: "vermin", severity: "major" },
    { date: "2025-01-09", visit: "routine", code: "6", theme: "handwashing", severity: "major" },
    { date: "2025-01-09", visit: "routine", code: "14", theme: "sanitizing", severity: "minor" },
    { date: "2024-05-20", visit: "routine", code: "14", theme: "sanitizing", severity: "grp" },
    { date: "2025-03-01", visit: "complaint", code: "15", theme: "supplier", severity: "minor" },
    { date: "2023-10-12", visit: "routine", code: "44", theme: "notatheme", severity: "grp" },
  ],
};

test("contract v3 themes: supplier, condition and process replace source", () => {
  assert.equal(THEMES.supplier, "Food source and shellfish tags");
  assert.equal(THEMES.condition, "Food condition");
  assert.equal(THEMES.process, "Special processes (HACCP)");
  assert.equal(THEMES.source, undefined);
  for (const k of ["major", "closed", "bc", "repeat", "supplier", "process"]) assert.ok(FLAG_KEYS.includes(k), k);
  for (const k of FLAG_KEYS) assert.ok(FLAG_LABELS[k], `label for ${k}`);
});

test("no grade is ever derived from a score, and a record's grade is its own letter", () => {
  assert.equal(inspections.gradeFor, undefined);
  assert.equal(inspections.postedGrade, undefined, "grades come from the index through lib/grades.js");
  assert.equal(recordGradeText(routine("2026-01-01", 84, null)), "");
  assert.equal(recordGradeText(routine("2026-01-01", 96, "A")), "A (96)");
});

test("stats count the 36 months before the last visit and split the three kinds of item", () => {
  const s = inspectionStats(record);
  assert.equal(s.count, 9);
  assert.equal(s.routineCount, 6);
  assert.equal(s.first.date, "2022-03-01");
  assert.equal(s.last.date, "2025-09-03");
  assert.equal(s.lastScore, 82);
  assert.equal(s.majors36, 1 + 2 + 2);
  assert.equal(s.minors36, 2 + 1 + 5 + 1 + 4);
  assert.equal(s.grp36, 2 + 1 + 3 + 2);
  assert.equal(s.closures, 1, "only closures read as a health hazard");
  assert.equal(s.permitClosures, 1);
  assert.equal(s.reinspections, 1);
  assert.equal(s.followups, 1);
  assert.equal(s.complaints, 1);
  assert.equal(inspectionStats({ inspections: [] }), null);
  assert.equal(inspectionStats(null), null);
  assert.equal(lastInspection({ inspections: [routine("2026-01-01", 90, "A")] }).date, "2026-01-01");
});

test("themes sort majors first, count complaint-visit findings, and fold unknown themes into other", () => {
  const t = themeCounts(record.violations);
  assert.deepEqual(t.map((x) => x.theme), ["temperature", "vermin", "handwashing", "sanitizing", "supplier", "other"]);
  const sanitizing = t.find((x) => x.theme === "sanitizing");
  assert.equal(sanitizing.count, 2);
  assert.equal(sanitizing.minor, 1);
  assert.equal(sanitizing.grp, 1);
  assert.equal(t.find((x) => x.theme === "supplier").complaint, 1);
  assert.equal(t.at(-1).label, "Other");
  assert.deepEqual(themeCounts(undefined), []);
});

test("visits and kinds of place have plain names, and every reading has a one-line rule", () => {
  assert.equal(visitLabel("followup"), "re-grade or reopening visit");
  assert.equal(visitLabel("complaint"), "complaint visit");
  assert.equal(visitLabel(undefined), "routine inspection");
  assert.equal(typeLabel("limited"), "Limited-preparation food service");
  assert.equal(typeLabel("something"), "Food facility");
  assert.equal(OUR_READING.health, "a major violation was cited that day.");
  for (const k of ["followup", "health", "permit", "other", "themes", "flags"]) assert.ok(OUR_READING[k].length < 120, k);
});
