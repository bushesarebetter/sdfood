import { test } from "node:test";
import assert from "node:assert/strict";
import { citation, recordText, standing } from "../src/lib/ask.js";

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
  violations: [{ date: "2026-05-05", visit: "routine", theme: "handwashing", severity: "major" }],
};

test("a citation names the authors, the run, the place and, in bands mode, its band; never a position", () => {
  const c = citation({ place, url: "https://example.org/place/SAMPLE-FFPP-00077", meta, mode: "bands" });
  assert.match(c, /^Zhang, C\., and Pendharkar, A\. \(\d{4}\)\. San Diego Food Inspection Record, run forward_2026-09-20: Sample Grill 077, 800 Sample Row, San Diego, CA 92101, band 2 on the published rule\. https:\/\/example\.org\/place\/SAMPLE-FFPP-00077\. Retrieved \d{4}-\d{2}-\d{2}\.$/);
  assert.doesNotMatch(citation({ place, url: "u", meta }), /band/, "record mode names no band");
  assert.doesNotMatch(citation({ place, url: "u", meta, mode: "bands", expired: true }), /band/);
  assert.equal(standing({ ...place, on_hold: true, band: undefined }, { mode: "bands" }), null);
});

test("the record text states the County's record, marks our readings, and says where to check it", () => {
  const t = recordText({ place, url: "https://example.org/place/SAMPLE-FFPP-00077", meta, mode: "bands" });
  assert.match(t, /County permit record SAMPLE-FFPP-00077/);
  assert.match(t, /band 2 on the published rule, 17 points\./);
  assert.match(t, /Latest County grade on record: A \(95\), May 12, 2026\./);
  assert.match(t, /Before it, the routine inspection on May 5, 2026 was graded B \(81\)\. Our reading: the later visit was a re-grade\./);
  assert.match(t, /94% of them did\. The County requires each major violation to be corrected/);
  assert.match(t, /Last visit: 2026-05-12, re-grade or reopening visit \(County status: Complete\), score 95, grade A \(95\)\./);
  assert.match(t, /2 major violations, 4 minor violations and 4 good-retail-practice items across 2 County records/);
  assert.match(t, /Our reading: 1 of those records are re-grade or reopening visits\./);
  assert.match(t, /Hand washing: 1 item, 1 major, latest 2026-05-05/);
  assert.match(t, /sandiegocounty\.gov/);
  assert.match(t, /not affiliated with or endorsed by the County of San Diego/);
  assert.doesNotMatch(t, /unsafe|dangerous|rank/);
  assert.doesNotMatch(recordText({ place, url: "u", meta }), /band|points/, "record mode states no band");
});
