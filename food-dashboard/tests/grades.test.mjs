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
  assert.deepEqual(g.csv, { grade: "A", grade_score: 90, grade_date: "2026-07-29", replaced_grade: "B", replaced_score: 81, replaced_date: "2026-05-20" });
  assert.equal(gradeView({ grade: "B", score: 84, date: "2026-02-01", replaced: null }).textColor, "#9A4A07", "amber as text is darkened");
});

test("no grade, or a malformed one, reads as not graded", () => {
  for (const g of [null, undefined, {}, { grade: "D", score: 60, date: "2026-01-01" }]) {
    const v = gradeView(g);
    assert.equal(v.graded, false);
    assert.equal(v.text, "Not graded by the County");
    assert.equal(v.replacedSentence, null);
  }
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
