import { test } from "node:test";
import assert from "node:assert/strict";
import { citation, recordText, standing } from "../src/lib/ask.js";
import { closureLines } from "../src/lib/recordFacts.js";
import { STUDENT_NOTE } from "../src/site.js";

const meta = { run: "forward_2026-09-20", mode: "bands", grade_context: { majors_graded_A_share: 0.942 } };

const place = {
  facility_id: "SAMPLE-FFPP-00077", name: "Sample Grill 077", address: "800 Sample Row, San Diego, CA 92101", facility_type: "restaurant",
  council_district: 3, band: "2", points: 17, flags: ["bc"],
  last_visit: { date: "2026-05-12", type: "followup" },
  grade: { grade: "A", score: 95, date: "2026-05-12", replaced: { grade: "B", score: 81, date: "2026-05-05" } },
  inspections: [
    { date: "2026-05-05", status: "Complete", type: "routine", score: 81, grade: "B", major: 2, minor: 4, grp: 3, closed: false, closure: null, reopened: null },
    { date: "2026-05-12", status: "Complete", type: "followup", score: 95, grade: "A", major: 0, minor: 0, grp: 1, closed: false, closure: null, reopened: null },
  ],
  violations: [{ date: "2026-05-05", visit: "routine", theme: "hands", severity: "major" }],
};

const rec = (date, extra = {}) => ({ date, status: "Complete", type: "routine", score: null, grade: null, major: 0, minor: 0, grp: 0, closed: false, closure: null, reopened: null, ...extra });
/** A place with the given records, its grade the latest letter among them. */
const withRecords = (inspections, grade = { grade: "A", score: 94, date: "2025-02-27", replaced: null }) => ({
  ...place, band: undefined, points: undefined, flags: [], grade, inspections, violations: [],
  last_visit: { date: inspections.at(-1).date, type: inspections.at(-1).type },
});

test("a citation names the authors, the run, the place and, in bands mode, its band; never a position", () => {
  const c = citation({ place, url: "https://example.org/place/SAMPLE-FFPP-00077", meta, mode: "bands" });
  assert.match(c, /^Zhang, C\., and Pendharkar, A\. \(\d{4}\)\. San Diego Food Inspection Record, run forward_2026-09-20: Sample Grill 077, 800 Sample Row, San Diego, CA 92101, band 2 on the students' point rule\. https:\/\/example\.org\/place\/SAMPLE-FFPP-00077\. Retrieved \d{4}-\d{2}-\d{2}\.$/);
  assert.doesNotMatch(citation({ place, url: "u", meta }), /band/, "record mode names no band");
  assert.doesNotMatch(citation({ place, url: "u", meta, mode: "bands", expired: true }), /band/);
  assert.equal(standing({ ...place, on_hold: true, band: undefined }, { mode: "bands" }), null);
});

test("the record text states the County's record, marks our readings, and says where to check it", () => {
  const t = recordText({ place, url: "https://example.org/place/SAMPLE-FFPP-00077", meta, mode: "bands" });
  assert.match(t, /County permit record SAMPLE-FFPP-00077/);
  assert.match(t, /band 2 on the students' point rule, 17 points\./);
  assert.match(t, /Latest County grade on record: A \(95\), May 12, 2026\./);
  assert.match(t, /Before it, the routine inspection on May 5, 2026 was graded B \(81\)\. Our reading: the later visit was a re-grade\./);
  assert.match(t, /94% of them did\. The County requires each major violation to be corrected/);
  assert.match(t, /Last visit: 2026-05-12, re-grade or reopening visit \(our reading\); County status: Complete, score 95, grade A \(95\)\./);
  assert.match(t, /In the three years before the last visit: 2 major violations, 4 minor violations and 4 good-retail-practice items across 2 County records\./);
  assert.match(t, /Since May 2026: 2 County records; 0 reinspections\./);
  assert.match(t, /Our reading: 1 of those records is a re-grade or reopening visit\./);
  assert.match(t, /Hands washed, gloves used: 1 item, 1 major, latest 2026-05-05/);
  assert.match(t, /sandiegocounty\.gov/);
  assert.ok(t.includes(STUDENT_NOTE), "the site's own disclaimer, as site.js states it");
  assert.doesNotMatch(t, /unsafe|dangerous|rank/);
  assert.doesNotMatch(t, /Closures and reopenings in the three years/, "no closure, no closure line");
  assert.doesNotMatch(recordText({ place, url: "u", meta }), /band|points/, "record mode states no band");
});

test("the record text lists every closure in the three years, in the panel's words, with or without a reopening", () => {
  const p = withRecords([
    rec("2025-02-27", { score: 94, grade: "A", county_type: "Routine" }),
    rec("2025-09-04", { status: "Ordered Closed", major: 1, closed: true, closure: "health", reopened: true, reopened_on: "2025-09-06", county_type: "Routine" }),
    rec("2025-09-05", { status: "Ordered Closed", type: "reinspection", major: 1, county_type: "Re-inspection" }),
    rec("2025-09-06", { status: "Approved to Reopen", type: "reinspection", county_type: "Re-inspection" }),
    rec("2026-02-04", { status: "Ordered Closed", type: "reinspection", major: 1, closed: true, closure: "health", reopened: false, reopened_on: null, county_type: "Re-inspection" }),
    rec("2026-02-11", { type: "reinspection", county_type: "Re-inspection" }),
  ], { grade: "A", score: 94, date: "2025-02-27", replaced: null, open_closure: { date: "2026-02-04", reason: "health", later_ungraded: ["2026-02-11"] } });
  const t = recordText({ place: p, url: "u", meta: {} });
  const lines = t.split("\n");
  // An open closure leads, before the old A.
  assert.match(lines[4], /^The County's record shows a closure on February 4, 2026 \(our reading: health hazard\), and no “Approved to Reopen” and no graded visit after it\./);
  assert.ok(t.indexOf("closure on February 4, 2026") < t.indexOf("A (94)"));
  const start = lines.indexOf("Closures and reopenings in the three years before the last visit:");
  assert.ok(start > 0);
  assert.deepEqual(lines.slice(start + 1, start + 3), closureLines(p).map((l) => `  ${l}`), "the panel's words, oldest first");
  assert.match(lines[start + 1], /^  Ordered closed: Ordered Closed on September 4, 2025 \(County type: Routine\)\. Approved to Reopen on September 6, 2025\. Our reading: a major violation was cited that day\.$/);
  assert.match(lines[start + 2], /Ordered Closed on February 4, 2026 \(County type: Re-inspection\)\. No “Approved to Reopen” and no graded visit after it on the County's published record\. Later County records: Re-inspection, “Complete”, February 11, 2026\./);
  // Both counts: our closures, and the County's rows.
  assert.match(t, /Since February 2025: 6 County records; 4 reinspections; 2 closures in our reading \(3 “Ordered Closed” records; a further order before the place reopened counts as the same closure\): 2 for a health hazard\./);
});

test("an older record that says only reopened: true is never reported as not reopened", () => {
  const p = withRecords([
    rec("2025-06-02", { status: "Ordered Closed", major: 1, closed: true, closure: "health", reopened: true }),
    rec("2025-06-04", { status: "Approved to Reopen", type: "followup", score: 95, grade: "A" }),
  ], { grade: "A", score: 95, date: "2025-06-04", replaced: null });
  const t = recordText({ place: p, url: "u", meta: {} });
  assert.match(t, /Ordered Closed on June 2, 2025\. Approved to Reopen on June 4, 2025\./);
  assert.doesNotMatch(t, /No “Approved to Reopen”/);
});

test("the record text marks a closure only an Approved to Reopen shows, and a reopening with no closure, as our reading", () => {
  const p = withRecords([
    rec("2026-03-03", { major: 1, closed: true, closure: "health", closure_inferred: true, reopened: true, reopened_on: "2026-03-04", county_type: "Routine" }),
    rec("2026-03-04", { status: "Approved to Reopen", type: "followup", score: 98, grade: "A", county_type: "Routine" }),
    rec("2026-06-10", { status: "Approved to Reopen", type: "reinspection", reopen_without_closure: true, county_type: "Re-inspection" }),
  ], { grade: "A", score: 98, date: "2026-03-04", replaced: null });
  const t = recordText({ place: p, url: "u", meta: {} });
  assert.match(t, /Closure, our reading: Complete on March 3, 2026 \(County type: Routine\), with no score and no grade\. Approved to Reopen on March 4, 2026\. Our reading: the County's “Approved to Reopen” on March 4, 2026 implies a closure; no closure order is on the published record\./);
  assert.match(t, /Approved to Reopen, no closure placed: Approved to Reopen on June 10, 2026 \(County type: Re-inspection\)\. Our reading: no closure could be placed before this Approved to Reopen/);
  assert.match(t, /1 closure in our reading \(0 “Ordered Closed” records; 1 shown only by a later “Approved to Reopen”\)/);
  assert.match(t, /1 “Approved to Reopen” record no closure could be placed before \(our reading\)/);
  assert.match(t, /Last visit: 2026-06-10, reinspection; County status: Approved to Reopen\./);
});

test("the record text counts themes from theme_counts, and says when the list it counted was cut", () => {
  const listed = Array.from({ length: 60 }, (_, k) => ({ date: `2026-0${1 + (k % 5)}-01`, visit: "routine", theme: k < 5 ? "temperature" : "grp_facility", severity: k < 5 ? "major" : "grp" }));
  const whole = {
    ...withRecords([rec("2026-05-01", { score: 88, grade: "B", major: 5, grp: 70 })], { grade: "B", score: 88, date: "2026-05-01", replaced: null }),
    violations: listed, violations_total: 80,
    theme_counts: { temperature: { major: 5, minor: 0, grp: 0, complaint: 0, latest: "2026-05-01" }, grp_facility: { major: 0, minor: 0, grp: 75, complaint: 0, latest: "2026-05-01" } },
  };
  const t = recordText({ place: whole, url: "u", meta: {} });
  assert.match(t, /Building and premises \(good retail practice\): 75 items, latest 2026-05-01/);
  assert.doesNotMatch(t, /Showing/);
  const counted = { ...whole, theme_counts: undefined };
  const c = recordText({ place: counted, url: "u", meta: {} });
  assert.match(c, /Building and premises \(good retail practice\): 55 items/);
  assert.match(c, /Showing 60 of 80 items, majors first/);
});
