import { test } from "node:test";
import assert from "node:assert/strict";
import { recordFacts, closureEntries, closureLines } from "../src/lib/recordFacts.js";
import { MAX_ITEMS } from "../src/lib/inspections.js";

const visit = (date, type, extra = {}) => ({ date, status: "Complete", type, score: null, grade: null, major: 0, minor: 0, grp: 0, closed: false, closure: null, reopened: null, ...extra });
const routine = (date, score, grade, extra = {}) => visit(date, "routine", { score, grade, ...extra });
const v = (date, theme, severity, extra = {}) => ({ date, visit: "routine", code: "7", theme, severity, description: "Proper hot and cold holding temperatures", ...extra });
const text = (facts) => facts.map((f) => [f.title, ...f.county, f.reading ?? ""].join(" ")).join(" ");
const NO_REOPEN = "No “Approved to Reopen” and no graded visit after it on the County's published record.";

test("a closure quotes the County's status and labels the reason as our reading", () => {
  const p = {
    inspections: [
      routine("2026-02-01", null, null, { status: "Ordered Closed", major: 1, closed: true, closure: "health", reopened: true }),
      visit("2026-02-02", "followup", { status: "Approved to Reopen", score: 94, grade: "A" }),
    ],
    violations: [],
  };
  const [c] = recordFacts(p);
  assert.equal(c.title, "Ordered closed");
  assert.deepEqual(c.county, ["Ordered Closed on February 1, 2026.", "Approved to Reopen on February 2, 2026."]);
  assert.equal(c.reading, "Our reading: a major violation was cited that day.");
  assert.doesNotMatch(text(recordFacts(p)), /ordered it closed for a health hazard/i, "the reason is never put in the County's mouth");
});

test("reopening is stated only when the record says the County approved it; its absence is stated too", () => {
  const notReopened = { inspections: [routine("2026-02-01", null, null, { status: "Ordered Closed", major: 1, closed: true, closure: "health", reopened: false })], violations: [] };
  assert.deepEqual(recordFacts(notReopened)[0].county, ["Ordered Closed on February 1, 2026.", NO_REOPEN]);
  const permit = { inspections: [routine("2026-02-01", 96, "A", { status: "Ordered Closed", closed: true, closure: "permit", reopened: false })], violations: [] };
  assert.equal(recordFacts(permit)[0].reading, "Our reading: no major violation was cited that day and a County note that day mentions a permit, so we read the closure as a permit matter.");
  // An export from before `reopened` was set says nothing either way.
  const unknown = { inspections: [routine("2026-02-01", null, null, { status: "Ordered Closed", major: 1, closed: true, closure: "health", reopened: null })], violations: [] };
  assert.deepEqual(recordFacts(unknown)[0].county, ["Ordered Closed on February 1, 2026."]);
});

test("reopened_on names the County's Approved to Reopen record that ended the closure", () => {
  const p = {
    inspections: [
      routine("2026-02-01", null, null, { status: "Ordered Closed", major: 1, closed: true, closure: "health", reopened: true, reopened_on: "2026-02-05" }),
      visit("2026-02-02", "complaint"),
      visit("2026-02-05", "followup", { status: "Approved to Reopen", score: 94, grade: "A" }),
      routine("2026-05-01", null, null, { status: "Ordered Closed", major: 2, closed: true, closure: "health", reopened: false, reopened_on: null }),
    ],
    violations: [],
  };
  const closures = recordFacts(p).filter((f) => f.title === "Ordered closed");
  assert.deepEqual(closures.map((f) => f.county), [
    ["Ordered Closed on May 1, 2026.", NO_REOPEN],
    ["Ordered Closed on February 1, 2026.", "Approved to Reopen on February 5, 2026."],
  ]);
});

test("a closure a later graded visit followed, with no Approved to Reopen, says so; an open one lists the records after it", () => {
  const p = {
    inspections: [
      routine("2026-01-10", 95, "A", { status: "Ordered Closed", closed: true, closure: "permit", reopened: false, reopened_on: null, county_type: "Routine", notes: ["No Valid Permit"] }),
      routine("2026-03-01", 94, "A", { county_type: "Routine" }),
      routine("2026-08-21", null, null, { status: "Ordered Closed", major: 1, closed: true, closure: "health", reopened: false, reopened_on: null, county_type: "Routine" }),
      visit("2026-08-28", "reinspection", { county_type: "Re-inspection" }),
      visit("2026-09-02", "status_check", { county_type: "Status Verification", grp: 1 }),
    ],
    violations: [],
  };
  const [open, permit] = recordFacts(p).filter((f) => f.key.startsWith("closure-"));
  assert.deepEqual(open.county, [
    "Ordered Closed on August 21, 2026 (County type: Routine).",
    NO_REOPEN,
    "Later County records: Re-inspection, “Complete”, August 28, 2026; Status Verification, “Complete”, September 2, 2026.",
  ]);
  assert.doesNotMatch(text([open]), /is closed|still closed|closed now/i, "the record, not the place's state today");
  assert.deepEqual(permit.county, [
    "Ordered Closed on January 10, 2026 (County type: Routine).",
    "County note: No Valid Permit.",
    "No “Approved to Reopen” on the County's published record before the next graded visit, on March 1, 2026.",
  ]);
});

test("a closure read as other names what the County cited that day, never that the record is silent", () => {
  const p = {
    inspections: [
      routine("2026-03-01", 94, "A"),
      routine("2026-04-03", null, null, { status: "Ordered Closed", minor: 1, closed: true, closure: "other", reopened: true, reopened_on: "2026-04-05", county_type: "Routine" }),
      visit("2026-04-05", "followup", { status: "Approved to Reopen", score: 95, grade: "A" }),
    ],
    violations: [v("2026-04-03", "water", "minor", { code: "21", description: "Hot & cold water available" })],
  };
  const [c] = recordFacts(p);
  assert.deepEqual(c.county, [
    "Ordered Closed on April 3, 2026 (County type: Routine).",
    "Items cited that day: item 21, “Hot & cold water available” (minor violation).",
    "Approved to Reopen on April 5, 2026.",
  ]);
  assert.equal(c.reading, "Our reading: no item marked major was cited that day and no County note that day mentions a permit; the County's record gives no reason.");
  assert.doesNotMatch(text([c]), /does not say why|reason not given/);
  const bare = { inspections: [routine("2026-04-03", null, null, { status: "Ordered Closed", closed: true, closure: "other", reopened: false })], violations: [] };
  assert.equal(recordFacts(bare)[0].county[1], "No items were cited that day.");
});

test("a Self Closed closure, a closure only an Approved to Reopen shows, and a reopening with no closure are each marked as our reading", () => {
  const p = {
    inspections: [
      routine("2025-11-17", null, null, { status: "Self Closed", major: 1, closed: true, closure: "health", reopened: false, reopened_on: null, county_type: "Routine" }),
      visit("2025-11-24", "followup", { score: 100, grade: "A", county_type: "Routine" }),
      routine("2026-03-03", null, null, { major: 1, closed: true, closure: "health", closure_inferred: true, reopened: true, reopened_on: "2026-03-04", county_type: "Routine" }),
      visit("2026-03-04", "followup", { status: "Approved to Reopen", score: 98, grade: "A", county_type: "Routine" }),
      visit("2026-06-10", "reinspection", { status: "Approved to Reopen", reopen_without_closure: true, county_type: "Re-inspection" }),
    ],
    violations: [],
  };
  const facts = recordFacts(p);
  const self = facts.find((f) => f.key === "closure-2025-11-17");
  assert.equal(self.title, "Self Closed");
  assert.equal(self.county[0], "Self Closed on November 17, 2025 (County type: Routine).");
  assert.equal(self.reading, "Our reading: a Self Closed record with a major violation cited that day is read as the operator's own closure.");
  const inferred = facts.find((f) => f.key === "closure-2026-03-03");
  assert.equal(inferred.title, "Closure, our reading");
  assert.deepEqual(inferred.county, ["Complete on March 3, 2026 (County type: Routine), with no score and no grade.", "Approved to Reopen on March 4, 2026."]);
  assert.equal(
    inferred.reading,
    "Our reading: the County's “Approved to Reopen” on March 4, 2026 implies a closure; no closure order is on the published record. A major violation was cited that day.",
  );
  assert.doesNotMatch(inferred.title + inferred.county.join(" "), /Ordered Closed/, "no County order is claimed");
  const reopen = facts.find((f) => f.key === "reopen-2026-06-10");
  assert.equal(reopen.title, "Approved to Reopen, no closure placed");
  assert.deepEqual(reopen.county, ["Approved to Reopen on June 10, 2026 (County type: Re-inspection)."]);
  assert.equal(reopen.reading, "Our reading: no closure could be placed before this Approved to Reopen, and none is read into the record.");
});

test("the panel and the pasted text take a closure's words from one place", () => {
  const p = {
    inspections: [
      routine("2024-01-10", null, null, { status: "Ordered Closed", major: 1, closed: true, closure: "health", reopened: true, reopened_on: "2024-01-12" }),
      visit("2024-01-12", "followup", { status: "Approved to Reopen", score: 94, grade: "A" }),
      routine("2026-02-04", null, null, { status: "Ordered Closed", major: 1, closed: true, closure: "health", reopened: false, reopened_on: null, notes: ["Impoundment"] }),
    ],
    violations: [],
  };
  const entries = closureEntries(p);
  assert.deepEqual(entries.map((e) => e.date), ["2024-01-10", "2026-02-04"], "oldest first");
  const [fact] = recordFacts(p);
  assert.deepEqual([fact.title, fact.county, fact.reading], [entries[1].title, entries[1].county, entries[1].reading]);
  assert.equal(closureLines(p)[1], `Ordered closed: Ordered Closed on February 4, 2026. County note: Impoundment. ${NO_REOPEN} Our reading: a major violation was cited that day.`);
  assert.deepEqual(closureEntries(p, { inWindow: (d) => d >= "2025-01-01" }).map((e) => e.date), ["2026-02-04"]);
  assert.deepEqual(closureEntries({ inspections: [routine("2026-01-01", 96, "A")] }), [], "no closure, no line");
});

test("a theme quotes the County's item text, counts Site Investigation and Environmental findings, and needs a major or minors at two inspections", () => {
  const p = {
    inspections: [routine("2025-11-11", 94, "A"), visit("2026-01-15", "complaint", { major: 1 }), routine("2026-03-02", 86, "B", { major: 1, minor: 1 })],
    violations: [
      v("2026-03-02", "temperature", "major"),
      v("2026-01-15", "temperature", "major", { visit: "complaint", description: "Proper cooling methods" }),
      v("2026-03-02", "sanitizing", "minor", { description: "Wiping cloths properly used and stored" }),
    ],
  };
  const facts = recordFacts(p);
  const temp = facts.find((f) => f.key === "theme-temperature");
  assert.equal(temp.title, "Food temperatures");
  assert.equal(temp.county[0], "2 major violations cited in the 12 months before its last visit, most recently in March 2026 (1 found at a Site Investigation or Environmental visit).");
  assert.match(temp.county[1], /^As the County wrote them: “Proper/);
  assert.equal(temp.reading, "Our reading: each item is put under a theme from the County's item text.");
  assert.ok(!facts.some((f) => f.key === "theme-sanitizing"), "one minor at one inspection is not a fact here");
  const field = facts.find((f) => f.key === "complaint");
  assert.equal(field.title, "Complaint or other field visits", "an export from before county_type");
  assert.equal(field.county[0], "1 record with no County type in this export in the 12 months before its last visit.");
  assert.equal(field.reading, "Our reading: the County's Site Investigation and Environmental records are read as complaint or other field visits.");
});

test("field visits are counted by the County's own type, and the grouping is our reading", () => {
  const p = {
    inspections: [
      visit("2026-01-15", "complaint", { county_type: "Site Investigation" }),
      visit("2026-02-15", "complaint", { county_type: "Site Investigation" }),
      visit("2026-03-01", "complaint", { county_type: "Environmental" }),
      routine("2026-03-02", 96, "A", { county_type: "Routine" }),
    ],
    violations: [],
  };
  const f = recordFacts(p).find((x) => x.key === "complaint");
  assert.equal(f.title, "Site Investigation or Environmental visits");
  assert.deepEqual(f.county, ["2 Site Investigation records and 1 Environmental record in the 12 months before its last visit."]);
  assert.doesNotMatch(f.county.join(" "), /complaint/i, "the County's lines use the County's words");
  assert.match(f.reading, /^Our reading: .*complaint or other field visits\.$/);
});

test("a theme's reading says when the 12 months go past the export's cut: the records cite more than it lists", () => {
  // 190 minor violations at two routine inspections in the window; the export lists the newest MAX_ITEMS.
  const minors = (date, n) => Array.from({ length: n }, () => v(date, "vermin", "minor", { code: "23", description: "Premises free of rodents/insects" }));
  const p = {
    inspections: [routine("2026-01-02", 80, "B", { minor: 100 }), routine("2026-08-02", 81, "B", { minor: 90 })],
    violations: [...minors("2026-01-02", MAX_ITEMS - 90), ...minors("2026-08-02", 90)],
    violations_total: 190,
  };
  const note = `Showing ${MAX_ITEMS} of the 190 major and minor violations the County's records in these 12 months cite, majors first`;
  const vermin = recordFacts(p).find((f) => f.key === "theme-vermin");
  assert.equal(vermin.county[0], `${MAX_ITEMS} minor violations cited in the 12 months before its last visit, most recently in August 2026.`);
  assert.ok(vermin.reading.includes(note), vermin.reading);
  // Whole counts for the 36 months (theme_counts) do not make the 12 months' facts whole: the line stays.
  const counted = { ...p, theme_counts: { vermin: { major: 0, minor: 190, grp: 0, complaint: 0, latest: "2026-08-02" } } };
  assert.ok(recordFacts(counted).find((f) => f.key === "theme-vermin").reading.includes(note), "theme_counts or not");
  // A list that holds every item the records cite needs no line.
  const whole = { ...p, inspections: [routine("2026-01-02", 80, "B", { minor: MAX_ITEMS - 90 }), routine("2026-08-02", 81, "B", { minor: 90 })], violations_total: MAX_ITEMS };
  assert.doesNotMatch(recordFacts(whole).find((f) => f.key === "theme-vermin").reading, /Showing/);
  // With no theme to carry it, the line stands alone.
  const bare = { inspections: [routine("2026-08-02", 81, "B", { major: 1, minor: 3 })], violations: [] };
  const alone = recordFacts(bare).find((f) => f.key === "theme-cut");
  assert.match(alone.county[0], /^Showing 0 of the 4 major and minor violations the County's records in these 12 months cite, majors first: /);
});

test("a B or C, or a re-grade after one, is stated from the index grade", () => {
  const b = { grade: { grade: "B", score: 84, date: "2026-03-02", replaced: null }, inspections: [routine("2026-03-02", 84, "B", { major: 1 })], violations: [] };
  assert.deepEqual(recordFacts(b).find((f) => f.key === "grade").county, ["Graded B (84) on March 2, 2026."]);
  const re = {
    grade: { grade: "A", score: 95, date: "2026-03-20", replaced: { grade: "B", score: 84, date: "2026-03-02" } },
    inspections: [routine("2026-03-02", 84, "B", { major: 1 }), visit("2026-03-20", "followup", { score: 95, grade: "A" })],
    violations: [],
  };
  const g = recordFacts(re).find((f) => f.key === "grade");
  assert.deepEqual(g.county, ["Graded B (84) on March 2, 2026, then A (95) on March 20, 2026."]);
  assert.equal(g.reading, "Our reading: the later visit was a re-grade.");
  // A later closure with no reopening on record leads the grade views, but the B is still a fact of the record.
  const open = { ...b, grade: { ...b.grade, open_closure: { date: "2026-04-01", reason: "health", later_ungraded: [] } } };
  assert.deepEqual(recordFacts(open).find((f) => f.key === "grade").county, ["Graded B (84) on March 2, 2026."]);
});

test("findings older than 12 months make no fact; nothing instructs or judges", () => {
  const old = {
    inspections: [routine("2024-03-01", null, null, { status: "Ordered Closed", major: 2, closed: true, closure: "health", reopened: true }), routine("2025-09-01", 96, "A")],
    violations: [v("2024-03-01", "vermin", "major")],
  };
  assert.deepEqual(recordFacts(old), []);
  const busy = {
    inspections: [
      routine("2025-10-01", null, null, { status: "Ordered Closed", major: 3, closed: true, closure: "health", reopened: true }),
      visit("2025-10-02", "followup", { status: "Approved to Reopen", score: 91, grade: "A" }),
      visit("2025-10-09", "reinspection"), visit("2025-11-09", "reinspection"), visit("2025-12-01", "complaint"),
      routine("2026-01-04", null, null, { status: "Ordered Closed", closed: true, closure: "other", reopened: false }),
      routine("2026-03-01", 78, "C", { major: 2 }),
    ],
    grade: { grade: "C", score: 78, date: "2026-03-01", replaced: null },
    violations: ["vermin", "temperature", "hands", "handsink", "health", "sanitizing", "supplier", "condition", "process", "water", "sewage", "grp_food"].map((t) => v("2026-03-01", t, "major")),
  };
  const all = text(recordFacts(busy));
  assert.doesNotMatch(all, /look for|tell the County|report it|avoid|should|unsafe|dangerous|if you eat/i);
  assert.equal(recordFacts(null).length, 0);
});
