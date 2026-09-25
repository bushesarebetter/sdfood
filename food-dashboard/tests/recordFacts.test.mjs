import { test } from "node:test";
import assert from "node:assert/strict";
import { recordFacts } from "../src/lib/recordFacts.js";

const visit = (date, type, extra = {}) => ({ date, status: "Complete", type, score: null, grade: null, major: 0, minor: 0, grp: 0, closed: false, closure: null, reopened: null, ...extra });
const routine = (date, score, grade, extra = {}) => visit(date, "routine", { score, grade, ...extra });
const v = (date, theme, severity, extra = {}) => ({ date, visit: "routine", code: "7", theme, severity, description: "Proper hot and cold holding temperatures", ...extra });
const text = (facts) => facts.map((f) => [f.title, ...f.county, f.reading ?? ""].join(" ")).join(" ");

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

test("reopening is stated only when the record says the County approved it", () => {
  const notReopened = { inspections: [routine("2026-02-01", null, null, { status: "Ordered Closed", major: 1, closed: true, closure: "health", reopened: false })], violations: [] };
  assert.deepEqual(recordFacts(notReopened)[0].county, ["Ordered Closed on February 1, 2026."]);
  const permit = { inspections: [routine("2026-02-01", 96, "A", { status: "Ordered Closed", closed: true, closure: "permit", reopened: false })], violations: [] };
  assert.equal(recordFacts(permit)[0].reading, "Our reading: no major violation was cited that day, so the closure is read as a permit matter.");
});

test("a theme quotes the County's item text, notes complaint visits, and needs a major or minors at two inspections", () => {
  const p = {
    inspections: [routine("2025-11-11", 94, "A"), visit("2026-01-15", "complaint"), routine("2026-03-02", 86, "B", { major: 2 })],
    violations: [
      v("2026-03-02", "temperature", "major"),
      v("2026-01-15", "temperature", "major", { visit: "complaint", description: "Proper cooling methods" }),
      v("2026-03-02", "sanitizing", "minor", { description: "Wiping cloths properly used and stored" }),
    ],
  };
  const facts = recordFacts(p);
  const temp = facts.find((f) => f.key === "theme-temperature");
  assert.equal(temp.title, "Food temperatures");
  assert.equal(temp.county[0], "2 major violations cited in the 12 months before its last visit, most recently in March 2026 (1 found at a complaint visit).");
  assert.match(temp.county[1], /^As the County wrote them: “Proper/);
  assert.equal(temp.reading, "Our reading: each item is put under a theme from the County's item text.");
  assert.ok(!facts.some((f) => f.key === "theme-sanitizing"), "one minor at one inspection is not a fact here");
  assert.equal(facts.find((f) => f.key === "complaint").county[0], "1 complaint visit in the 12 months before its last visit.");
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
      routine("2026-03-01", 78, "C", { major: 2 }),
    ],
    grade: { grade: "C", score: 78, date: "2026-03-01", replaced: null },
    violations: ["vermin", "temperature", "handwashing", "hygiene", "sanitizing", "supplier", "condition", "process", "storage", "plumbing"].map((t) => v("2026-03-01", t, "major")),
  };
  const all = text(recordFacts(busy));
  assert.doesNotMatch(all, /look for|tell the County|report it|avoid|should|unsafe|dangerous|if you eat/i);
  assert.equal(recordFacts(null).length, 0);
});
