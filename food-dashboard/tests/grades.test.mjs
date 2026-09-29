import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { gradeView } from "../src/lib/grades.js";
import { facilitiesToCsv } from "../src/lib/format.js";
import { recordText } from "../src/lib/ask.js";
import { placeLines } from "../src/lib/framing.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

const regraded = { grade: "A", score: 90, date: "2026-07-29", replaced: { grade: "B", score: 81, date: "2026-05-20" } };

test("the posted grade leads; a replaced grade only ever follows it", () => {
  const g = gradeView(regraded);
  assert.equal(g.text, "A (90)");
  assert.equal(g.sentence, "Latest County grade on record: A (90), July 29, 2026.");
  assert.equal(g.short, "A 90, Jul 2026");
  assert.equal(g.replacedSentence, "Before it, the routine inspection on May 20, 2026 was graded B (81). Our reading: the later visit was a re-grade.");
  assert.equal(g.textColor, null, "A is drawn in ink");
  assert.deepEqual(g.csv, { grade: "A", grade_score: 90, grade_date: "2026-07-29", replaced_grade: "B", replaced_score: 81, replaced_date: "2026-05-20", open_closure_date: "" });
  assert.equal(gradeView({ grade: "B", score: 84, date: "2026-02-01", replaced: null }).textColor, "#9A4A07", "amber as text is darkened");
  assert.equal(gradeView({ ...regraded, open_closure: null }).graded, true, "no open closure: the letter leads");
});

test("no grade, or a malformed one, reads as not graded", () => {
  for (const g of [null, undefined, {}, { grade: "D", score: 60, date: "2026-01-01" }]) {
    const v = gradeView(g);
    assert.equal(v.graded, false);
    assert.equal(v.closedOpen, false);
    assert.equal(v.text, "Not graded by the County");
    assert.equal(v.replacedSentence, null);
  }
});

// A place ordered closed after its last A, with no "Approved to Reopen" and no graded visit since.
const open = { grade: "A", score: 94, date: "2025-07-28", replaced: null, open_closure: { date: "2026-09-01", reason: "health", later_ungraded: ["2026-09-08"] } };

test("a closure with no reopening on record leads every grade view; the older letter follows it", () => {
  const g = gradeView(open);
  assert.equal(g.graded, false, "no view leads with the A");
  assert.equal(g.closedOpen, true);
  assert.equal(g.letter, "A", "the letter is still on record");
  assert.deepEqual(g.lastGrade, { text: "A (94)", date: "2025-07-28" });
  assert.equal(g.text, "Closed Sep 2026, no reopening on record");
  assert.equal(
    g.sentence,
    "The County's record shows a closure on September 1, 2026 (our reading: health hazard), and no “Approved to Reopen” and no graded visit after it. " +
      "The County's later record, on September 8, 2026, has no grade. The latest County grade on record: A (94), July 28, 2025.",
  );
  assert.doesNotMatch(g.sentence + g.text, /is closed|still closed|closed now|currently/i, "the record, not the place's state today");
  assert.equal(g.textColor, "#7F1D1D", "never the A's colour");
  assert.equal(g.swatch, "#7F1D1D");
  assert.equal(g.replacedSentence, null);
  assert.deepEqual(g.csv, { grade: "A", grade_score: 94, grade_date: "2025-07-28", replaced_grade: "", replaced_score: "", replaced_date: "", open_closure_date: "2026-09-01" });
  // A view written as `g.graded ? "Grade " + g.short : g.text` leads with the closure.
  assert.equal(g.graded ? `Grade ${g.short}` : g.text, "Closed Sep 2026, no reopening on record");
});

test("an open closure names the County's status where the export gives it, and a malformed one is ignored", () => {
  assert.equal(gradeView({ ...open, open_closure: { ...open.open_closure, status: "Ordered Closed" } }).text, "Ordered closed Sep 2026, no reopening on record");
  assert.match(gradeView({ ...open, open_closure: { ...open.open_closure, status: "Ordered Closed" } }).sentence, /^The County's record shows “Ordered Closed” on September 1, 2026/);
  assert.equal(gradeView({ ...open, open_closure: { ...open.open_closure, status: "Self Closed" } }).text, "Self closed Sep 2026, no reopening on record");
  const noLater = gradeView({ ...open, open_closure: { date: "2026-09-01", reason: "permit" } });
  assert.match(noLater.sentence, /\(our reading: permit matter\), and no “Approved to Reopen” and no graded visit after it\. The latest County grade/);
  for (const bad of [{ date: "Sept 1" }, "2026-09-01", {}]) assert.equal(gradeView({ ...open, open_closure: bad }).graded, true, JSON.stringify(bad));
});

test("the record text, the place lines and the CSV lead with an open closure too", () => {
  const place = {
    facility_id: "SAMPLE-FFPP-00002", name: "Sample Grill 0002", address: "2 Sample Row, San Diego, CA 92101", facility_type: "restaurant",
    council_district: 3, last_visit: { date: "2026-09-08", type: "reinspection" }, grade: open, flags: ["closed"],
    inspections: [
      { date: "2025-07-28", status: "Complete", type: "routine", score: 94, grade: "A", major: 0, minor: 1, grp: 0, closed: false, closure: null, reopened: null },
      { date: "2026-09-01", status: "Ordered Closed", type: "routine", score: null, grade: null, major: 1, minor: 0, grp: 0, closed: true, closure: "health", reopened: false, reopened_on: null },
      { date: "2026-09-08", status: "Complete", type: "reinspection", score: null, grade: null, major: 0, minor: 0, grp: 0, closed: false, closure: null, reopened: null },
    ],
    violations: [],
  };
  const text = recordText({ place, url: "u", meta: {} });
  assert.ok(text.indexOf("closure on September 1, 2026") < text.indexOf("A (94)"), "the closure comes first");
  assert.doesNotMatch(text, /Latest County grade on record: A/);
  assert.match(placeLines(place, {})[0], /^The County's record shows a closure on September 1, 2026/);
  const csv = facilitiesToCsv([{ properties: place, geometry: { coordinates: [-117, 32.7] } }]);
  assert.match(csv, /,A,94,2025-07-28,,,,/, "the letter is still in its columns");
});

test("the CSV, the record text and the place lines all state the same grade", () => {
  const place = {
    facility_id: "SAMPLE-FFPP-00001", name: "Sample Grill 0001", address: "1 Sample Row, San Diego, CA 92101", facility_type: "restaurant",
    council_district: 3, last_visit: { date: "2026-08-13", type: "reinspection" }, grade: regraded, flags: [],
    inspections: [{ date: "2026-08-13", status: "Complete", type: "reinspection", score: null, grade: null, major: 0, minor: 1, grp: 0, closed: false, closure: null, reopened: null }],
    violations: [],
  };
  const csv = facilitiesToCsv([{ properties: place, geometry: { coordinates: [-117, 32.7] } }]);
  assert.match(csv, /,A,90,2026-07-29,B,81,2026-05-20,/);
  const text = recordText({ place, url: "u", meta: {} });
  assert.ok(text.indexOf("Latest County grade on record: A (90)") < text.indexOf("graded B (81)"), "the record text leads with the posted grade");
  assert.equal(placeLines(place, {})[0], "Latest County grade on record: A (90), July 29, 2026.");
});

// Every view that shows a grade takes its text from gradeView, and none reads
// the letter off the grade object or off a record for the place's grade.
const VIEWS = ["src/PlacePanel.jsx", "src/PlaceCard.jsx", "src/MobileSheet.jsx", "src/RecordSummary.jsx", "src/PlaceTable.jsx", "src/SearchBox.jsx", "src/lib/format.js", "src/lib/ask.js", "src/lib/framing.js"];

test("every view's grade text comes from one helper", () => {
  for (const path of VIEWS) {
    const src = readFileSync(join(root, path), "utf8");
    assert.match(src, /gradeView\(/, `${path} uses gradeView`);
    assert.doesNotMatch(src, /\.grade\?*\.grade\b|postedGrade|lastGraded|latestGraded/, `${path} reads no grade letter directly`);
  }
});
