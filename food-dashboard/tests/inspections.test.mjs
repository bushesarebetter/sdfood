import { test } from "node:test";
import assert from "node:assert/strict";
import * as inspections from "../src/lib/inspections.js";

const { inspectionStats, themeCounts, lastInspection, visitLabel, recordGradeText, reopenedText, typeLabel, THEMES, FLAG_KEYS, FLAG_LABELS, FLAG_SHORT, factTags, RECORD_FLAGS, ESCALATION_FLAGS, ESCALATION_NOTE, OUR_READING } = inspections;

const visit = (date, type, extra = {}) => ({ date, status: "Complete", type, score: null, grade: null, major: 0, minor: 0, grp: 0, closed: false, closure: null, reopened: null, ...extra });
const routine = (date, score, grade, extra = {}) => visit(date, "routine", { score, grade, ...extra });

const record = {
  inspections: [
    routine("2022-03-01", 96, "A", { major: 1, minor: 1, grp: 1 }),
    routine("2023-10-12", 94, "A", { grp: 2 }),
    routine("2024-05-20", 95, "A", { major: 1, minor: 2, grp: 1 }),
    visit("2024-05-27", "reinspection", { minor: 1 }),
    routine("2025-01-09", null, null, { status: "Ordered Closed", major: 2, minor: 5, grp: 3, closed: true, closure: "health", reopened: true, reopened_on: "2025-01-10" }),
    visit("2025-01-10", "followup", { status: "Approved to Reopen", score: 91, grade: "A", minor: 1 }),
    visit("2025-03-01", "complaint"),
    routine("2025-05-01", 97, "A", { status: "Ordered Closed", closed: true, closure: "permit", reopened: false, reopened_on: null }),
    routine("2025-09-03", 82, "B", { major: 2, minor: 4, grp: 2 }),
  ],
  violations: [
    { date: "2025-09-03", visit: "routine", code: "7", theme: "temperature", severity: "major" },
    { date: "2025-09-03", visit: "routine", code: "23", theme: "vermin", severity: "major" },
    { date: "2025-01-09", visit: "routine", code: "6", theme: "handsink", severity: "major" },
    { date: "2025-01-09", visit: "routine", code: "14", theme: "sanitizing", severity: "minor" },
    { date: "2024-05-20", visit: "routine", code: "14", theme: "sanitizing", severity: "grp" },
    { date: "2025-03-01", visit: "complaint", code: "15", theme: "supplier", severity: "minor" },
    { date: "2023-10-12", visit: "routine", code: "44", theme: "notatheme", severity: "grp" },
  ],
};

test("themes are the sections of the County's inspection report", () => {
  assert.deepEqual(Object.keys(THEMES), [
    "knowledge", "health", "hands", "handsink", "temperature", "condition", "sanitizing", "supplier", "process", "advisory", "hsp",
    "water", "sewage", "vermin", "grp_staff", "grp_food", "grp_storage", "grp_equipment", "grp_facility", "grp_signs", "grp_other", "other",
  ]);
  assert.equal(THEMES.knowledge, "Food safety certificate and food handler cards");
  assert.equal(THEMES.hands, "Hands washed, gloves used");
  assert.equal(THEMES.handsink, "Hand sinks stocked and accessible");
  assert.equal(THEMES.sanitizing, "Food-contact surfaces cleaned and sanitized");
  assert.equal(THEMES.hsp, "Foods not allowed for highly susceptible people");
  assert.equal(THEMES.grp_signs, "Signs, grade card and permits (good retail practice)");
  for (const old of ["handwashing", "hygiene", "plumbing", "storage", "equipment", "labeling", "source"]) assert.equal(THEMES[old], undefined, old);
});

test("flags: the record facts, the four escalation facts, and every theme but other", () => {
  assert.deepEqual(ESCALATION_FLAGS, ["major_2", "closures2", "repeat_item", "lt90_2"]);
  assert.deepEqual(RECORD_FLAGS, ["major", "closed", "bc", "repeat", "major_2", "closures2", "repeat_item", "lt90_2"]);
  for (const k of [...RECORD_FLAGS, "supplier", "process", "grp_staff", "grp_other"]) assert.ok(FLAG_KEYS.includes(k), k);
  assert.ok(!FLAG_KEYS.includes("other"), "a major's theme is never flagged as other");
  for (const k of FLAG_KEYS) assert.ok(FLAG_LABELS[k], `label for ${k}`);
  assert.equal(FLAG_LABELS.process, "Major: special processes (HACCP)", "only the first letter is lowered");
  assert.equal(FLAG_LABELS.lt90_2, "Scored below 90 at two or more routine inspections in two years");
  assert.match(FLAG_LABELS.closures2, /two or more times in two years/);
  assert.match(FLAG_LABELS.repeat_item, /two or more routine inspections in two years/);
});

test("flags are read back from the list date, and the escalation facts quote the County's Guide in full", () => {
  assert.equal(OUR_READING.flags, "read from the 12 months before the list date, and 24 months for the four escalation facts.");
  assert.doesNotMatch(OUR_READING.flags, /last visit/);
  assert.match(ESCALATION_NOTE, /Retail Food Facility Operator's Guide \(p\. 8\)/);
  assert.ok(ESCALATION_NOTE.includes("“a history of recurring major violations, recurring scores of less than 90%, or recurring facility closures”"));
  assert.match(ESCALATION_NOTE, /The County sets no count or period\. These are our counts/);
  assert.match(ESCALATION_NOTE, /is not a County finding and does not mean the County has acted or will\.$/);
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
  assert.deepEqual(t.map((x) => x.theme), ["temperature", "vermin", "handsink", "sanitizing", "supplier", "other"]);
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
  assert.equal(visitLabel("complaint"), "complaint or other field visit");
  assert.equal(visitLabel("status_check"), "status verification");
  assert.equal(visitLabel(undefined), "routine inspection");
  assert.equal(typeLabel("limited"), "Limited-preparation food service");
  assert.equal(typeLabel("something"), "Food facility");
  assert.equal(OUR_READING.health, "a major violation was cited that day.");
  assert.equal(OUR_READING.permit, "no major violation was cited that day and the inspector's notes mention a permit, so we read the closure as a permit matter.");
  for (const k of ["followup", "complaint", "health", "permit", "other", "selfClosed", "inferred", "reopenOnly", "themes", "flags"]) {
    assert.ok(OUR_READING[k].length < 130, k);
  }
});

test("a closure read as other says what was not cited, never that the record is silent", () => {
  assert.equal(inspections.CLOSURE_LABELS.other, "no major violation cited");
  assert.equal(OUR_READING.other, "no item marked major was cited that day and no note mentions a permit; the County's record gives no reason.");
  const all = Object.values(OUR_READING).join(" ") + Object.values(inspections.CLOSURE_LABELS).join(" ");
  assert.doesNotMatch(all, /does not say why|reason not given/);
});

test("the County's own type and notes are shown verbatim, and a type we group is marked as our reading", () => {
  const { visitPhrase, countyType, countyNotes, VISIT_TYPES, COUNTY_TYPES, READ_VISIT_TYPES } = inspections;
  assert.ok(VISIT_TYPES.includes("status_check"), "a kept Status Verification record is shown");
  assert.deepEqual(READ_VISIT_TYPES, ["followup", "complaint"]);
  assert.deepEqual(COUNTY_TYPES.complaint, ["Site Investigation", "Environmental"]);
  assert.equal(visitPhrase(visit("2026-01-01", "complaint", { county_type: "Environmental" })), "complaint or other field visit (our reading; County type: Environmental)");
  assert.equal(visitPhrase(visit("2026-01-01", "complaint")), "complaint or other field visit (our reading)", "an export from before county_type");
  assert.equal(visitPhrase(visit("2026-01-01", "followup", { county_type: "Routine" })), "re-grade or reopening visit (our reading; County type: Routine)");
  assert.equal(visitPhrase(routine("2026-01-01", 95, "A", { county_type: "Routine" })), "routine inspection");
  assert.equal(visitPhrase(visit("2026-01-01", "status_check", { county_type: "Status Verification" })), "status verification");
  assert.equal(countyType(visit("2026-01-01", "complaint", { county_type: " Site Investigation " })), "Site Investigation");
  assert.equal(countyType(visit("2026-01-01", "complaint")), null);
  assert.deepEqual(countyNotes(visit("2026-01-01", "routine", { notes: ["No Valid Permit", "", 7, "Impoundment"] })), ["No Valid Permit", "Impoundment"]);
  assert.deepEqual(countyNotes(visit("2026-01-01", "routine")), [], "an export from before notes");
});

test("one set of closure words: a County order, a Self Closed record, and a closure only an Approved to Reopen shows", () => {
  const { closureWords } = inspections;
  const order = closureWords(routine("2026-02-01", null, null, { status: "Ordered Closed", closed: true, closure: "health" }));
  assert.deepEqual([order.kind, order.title, order.short, order.reading], ["order", "Ordered Closed", "health hazard", "a major violation was cited that day."]);
  const self = closureWords(routine("2026-02-01", null, null, { status: "Self Closed", major: 1, closed: true, closure: "health" }));
  assert.equal(self.kind, "self");
  assert.equal(self.title, "Self Closed");
  assert.equal(self.short, "the operator's own closure (health hazard)");
  const inferred = closureWords(routine("2026-03-03", null, null, { major: 1, closed: true, closure: "health", closure_inferred: true, reopened: true, reopened_on: "2026-03-04" }));
  assert.equal(inferred.kind, "inferred");
  assert.equal(inferred.title, "Closure, our reading");
  assert.equal(
    inferred.reading,
    "the County's “Approved to Reopen” on March 4, 2026 implies a closure; no closure order is on the published record. A major violation was cited that day.",
  );
  assert.doesNotMatch(inferred.title, /Ordered/, "never a closure order the County did not publish");
  assert.equal(closureWords(routine("2026-02-01", null, null, { status: "Ordered Closed", closed: true, closure: "mystery" })).short, "no major violation cited");
});

test("a place's own closures and the County's Ordered Closed rows are counted apart", () => {
  // Two episodes, three "Ordered Closed" rows: the next day's order kept the place closed.
  const p = {
    inspections: [
      routine("2025-09-04", null, null, { status: "Ordered Closed", major: 1, closed: true, closure: "health", reopened: true, reopened_on: "2025-09-06" }),
      visit("2025-09-05", "reinspection", { status: "Ordered Closed", major: 1 }),
      visit("2025-09-06", "reinspection", { status: "Approved to Reopen" }),
      visit("2025-09-23", "reinspection", { status: "Ordered Closed", major: 1, closed: true, closure: "health", reopened: true, reopened_on: "2025-09-24" }),
      visit("2025-09-24", "reinspection", { status: "Approved to Reopen" }),
      routine("2025-11-03", null, null, { major: 1, closed: true, closure: "health", closure_inferred: true, reopened: true, reopened_on: "2025-11-04" }),
      visit("2025-11-04", "followup", { status: "Approved to Reopen", score: 96, grade: "A" }),
      routine("2025-12-01", null, null, { status: "Self Closed", major: 1, closed: true, closure: "health", reopened: false, reopened_on: null }),
      visit("2026-01-15", "reinspection", { status: "Approved to Reopen", reopen_without_closure: true }),
      visit("2026-02-01", "status_check", { grp: 1 }),
    ],
  };
  const s = inspectionStats(p);
  assert.equal(s.orderedClosedRecords, 3, "the County's rows, as the table below shows them");
  assert.equal(s.closureEpisodes, 4);
  assert.equal(s.closures, 4);
  assert.equal(s.inferredClosures, 1);
  assert.equal(s.selfClosures, 1);
  assert.equal(s.reopenedWithoutClosure, 1);
  assert.equal(s.statusChecks, 1);
  assert.equal(s.count36, s.count);
  assert.equal(inspectionStats(record).count36, 8, "the record's first visit is more than 36 months before its last");
});

test("theme counts read the export's theme_counts when it gives them, and say when the list was cut", () => {
  const { themeCountsNote, itemsShown, MAX_ITEMS } = inspections;
  assert.equal(MAX_ITEMS, 60);
  // 80 items cited, 60 listed: the listed ones hold every major and the newest others.
  const listed = [
    ...Array.from({ length: 10 }, () => ({ date: "2026-03-01", visit: "routine", theme: "temperature", severity: "major" })),
    ...Array.from({ length: 50 }, () => ({ date: "2026-03-01", visit: "routine", theme: "grp_equipment", severity: "grp" })),
  ];
  const place = {
    violations: listed,
    violations_total: 80,
    theme_counts: {
      temperature: { major: 10, minor: 4, grp: 0, complaint: 1, latest: "2026-03-01" },
      grp_equipment: { major: 0, minor: 0, grp: 64, complaint: 0, latest: "2026-03-01" },
      notatheme: { major: 0, minor: 0, grp: 2, complaint: 0, latest: "2024-01-01" },
    },
  };
  const t = themeCounts(place);
  assert.deepEqual(t.map((x) => [x.theme, x.count, x.major, x.minor, x.grp, x.complaint, x.last]), [
    ["temperature", 14, 10, 4, 0, 1, "2026-03-01"],
    ["grp_equipment", 64, 0, 0, 64, 0, "2026-03-01"],
    ["other", 2, 0, 0, 2, 0, "2024-01-01"],
  ]);
  assert.equal(t.reduce((a, x) => a + x.count, 0), place.violations_total, "every item in the window, before the cut");
  assert.equal(themeCountsNote(place), null, "counts from theme_counts are whole");
  assert.deepEqual(itemsShown(place), { shown: 60, total: 80, cut: true });
  // An export with violations_total but no theme_counts: counted from the list, and it says so.
  const counted = { violations: listed, violations_total: 80 };
  assert.equal(themeCounts(counted).find((x) => x.theme === "grp_equipment").count, 50);
  assert.equal(themeCountsNote(counted), "Showing 60 of 80 items, majors first: counts of minor and good-retail-practice items, and their latest dates, may be low.");
  // An older export at the cut does not say how many more there were.
  assert.match(themeCountsNote({ violations: listed }), /^Showing the first 60 items, majors first; the export lists no more/);
  assert.equal(themeCountsNote({ violations: listed.slice(0, 20) }), null, "a list below the cut is whole");
  assert.equal(themeCountsNote({ violations: listed.slice(0, 20), violations_total: 20 }), null);
  assert.deepEqual(themeCounts({ violations: record.violations }), themeCounts(record.violations), "a place without theme_counts counts its list");
});

test("what follows a closure: its Approved to Reopen, the next graded visit, or nothing", () => {
  const { closureEnd } = inspections;
  const list = [
    routine("2026-01-05", null, null, { status: "Ordered Closed", major: 1, closed: true, closure: "health", reopened: true, reopened_on: "2026-01-07" }),
    visit("2026-01-07", "reinspection", { status: "Approved to Reopen" }),
    routine("2026-03-02", 96, "A", { status: "Ordered Closed", closed: true, closure: "permit", reopened: false, reopened_on: null }),
    routine("2026-06-01", 93, "A"),
    routine("2026-08-21", null, null, { status: "Ordered Closed", major: 2, closed: true, closure: "health", reopened: false, reopened_on: null }),
    visit("2026-08-28", "reinspection"),
  ];
  assert.equal(closureEnd(list, 0).reopen.date, "2026-01-07");
  assert.equal(closureEnd(list, 0).open, false);
  const permit = closureEnd(list, 2);
  assert.equal(permit.reopen, null);
  assert.equal(permit.nextGraded.date, "2026-06-01", "a graded visit on a later day");
  assert.equal(permit.open, false);
  const last = closureEnd(list, 4);
  assert.equal(last.open, true, "no Approved to Reopen and no graded visit after it");
  assert.deepEqual(last.later.map((i) => i.date), ["2026-08-28"]);
  const legacy = [
    routine("2025-01-09", null, null, { status: "Ordered Closed", closed: true, closure: "health", reopened: true }),
    visit("2025-01-12", "followup", { status: "Approved to Reopen", score: 94, grade: "A" }),
  ];
  assert.equal(closureEnd(legacy, 0).reopen.date, "2025-01-12", "an export from before reopened_on");
  assert.equal(closureEnd(legacy, 5).open, false);
});

test("a closure the County reopened shows the reopening date; nothing else does", () => {
  const [, , , , closed, reopen, , permit] = record.inspections;
  assert.equal(reopenedText(closed), "Reopened January 10, 2025");
  assert.equal(reopenedText(permit), null, "not reopened");
  assert.equal(reopenedText(reopen), null, "the reopening record itself");
  assert.equal(reopenedText({ ...closed, reopened_on: undefined }), null, "an export from before reopened_on");
  assert.equal(reopenedText({ ...reopen, reopened_on: "2025-01-10" }), null, "only a closure carries it");
});

test("a place's page lists the County's escalation criteria it meets, in order, and nothing else", () => {
  assert.deepEqual(inspections.escalationFacts(["major", "lt90_2", "closures2", "vermin"]).map((f) => f.key), ["closures2", "lt90_2"]);
  assert.match(inspections.escalationFacts(["repeat_item"])[0].label, /^Same major item at two or more routine inspections/);
  assert.deepEqual(inspections.escalationFacts(undefined), []);
});

test("the list's short fact tags: every record fact has one, each keeps its full wording, the themes in a line", () => {
  for (const k of RECORD_FLAGS) assert.ok(FLAG_SHORT[k], `short tag for ${k}`);
  for (const k of ESCALATION_FLAGS) assert.match(FLAG_SHORT[k], /2 years$/, `${k} says its window`);
  const t = factTags(["lt90_2", "pests", "major", "closures2", "bc", "temperature", "other"]);
  assert.deepEqual(t.record.map((x) => x.key), ["major", "bc"], "in RECORD_FLAGS order");
  assert.deepEqual(t.escalation.map((x) => x.key), ["closures2", "lt90_2"]);
  assert.deepEqual(t.record[0], { key: "major", short: "Major violation", full: FLAG_LABELS.major });
  assert.ok(t.themes.length >= 1 && !t.themes.includes("other"), "the majors' themes, never other");
  for (const theme of t.themes) assert.equal(theme, theme.charAt(0).toLowerCase() + theme.slice(1));
  assert.deepEqual(factTags(null), { record: [], escalation: [], themes: [] });
});

