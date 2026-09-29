import { test } from "node:test";
import assert from "node:assert/strict";
import {
  isStaff, contactLine, reviewStatus, reviewGuidance, districtGuidance, auditCsv, auditPrint, signInAgain, GUIDANCE, PUBLIC_RECORD_NOTE, USE_NOTE,
  evidenceDistricts, fairnessLine,
} from "../src/lib/staff.js";

const STATUS = [
  "no publishable rule is within 0.01 AUC of the best model at every validation origin",
  "the rule does not beat persistence on AUC among eligible restaurants ([-0.0107, 0.0187])",
  "no band's interval clears the approved cost ratio: nothing to name",
  "district 4: 2.02x its share of wrongly named places (27 named)",
  "district 9: false-positive rate 1.81x the City's",
  "district 9: the share of wrongly named places could be up to 2.35x even",
  "prospective test: no registered run",
];

// The lines the staff copy of meta now carries, by their exact prefixes.
const NEW_STATUS = [
  "no City request for access is on record (docs/STAFF_APPROVAL.json city_requestor)",
  "no TRUST Ordinance determination is on record",
  "no lawyer has reviewed naming these businesses",
  "the County has not commented on this list",
  "no business on the list has been told it is on it",
  "the County's record has moved since the rule was frozen: routine major rate 27.0% against 21.0%",
];

test("the staff copy of meta makes the site a staff site; the public sample is not", () => {
  assert.equal(isStaff({ audience: "staff" }), true);
  assert.equal(isStaff({ sample: true }), false);
  assert.equal(contactLine({ contact: { name: "A", email: "a@example.org" } }), "A (a@example.org)");
  assert.equal(contactLine({ contact: "a@example.org" }), null, "a public export's string contact is not a staff contact object");
});

test("every open check becomes an instruction staff can act on, once", () => {
  const g = reviewGuidance({ review_status: STATUS });
  assert.deepEqual(g, [
    "The points do no better than a place's recent major violations alone at picking out places with a major next time. Read them as a summary of the County's record, not a forecast for one place.",
    "No band is strong enough to justify singling out a business.",
    "A band is wrong more often in Districts 4 and 9 than elsewhere: do not compare districts by how many places are in a band.",
    "The rule has not yet been tested on inspections made after it was frozen.",
  ]);
  assert.ok(!g.join(" ").includes("rank places against each other"), "the list is sorted by points; the old instruction is gone");
  assert.deepEqual(reviewGuidance({}), []);
  assert.equal(reviewStatus({ review_status: ["x", 3, ""] }).length, 1);
});

test("the access, review, owner and drift lines map to their sentences, the demonstration one first", () => {
  const g = reviewGuidance({ review_status: [...STATUS, ...NEW_STATUS] });
  assert.equal(g[0], "The City has not recorded a request for this site or a TRUST Ordinance determination. Until it does, treat the site as a demonstration, not a City tool.");
  assert.equal(g.filter((s) => s === GUIDANCE.demonstration).length, 1, "access and TRUST give one sentence");
  assert.equal(g[1], "No lawyer or County official has reviewed this list, and no business on it has been told it is listed: do not act on a band or repeat one outside the City.");
  assert.equal(g.filter((s) => s === GUIDANCE.unreviewed).length, 1, "lawyer, County and owners give one sentence");
  assert.ok(g.includes("The County's record has changed since the rule was checked, so the rates on this site may be out of date."));
  assert.equal(new Set(g).size, g.length, "no sentence twice");
  // each line alone is enough for its sentence
  assert.deepEqual(reviewGuidance({ review_status: ["no TRUST Ordinance determination is on record"] }), [GUIDANCE.demonstration]);
  assert.deepEqual(reviewGuidance({ review_status: ["the County has not commented on this list"] }), [GUIDANCE.unreviewed]);
  assert.deepEqual(reviewGuidance({ review_status: ["the County’s record has moved since the rule was frozen: x"] }), [GUIDANCE.drift]);
  assert.deepEqual(reviewGuidance({ review_status: ["no independent responsible adult: the operator named is a student author of the list"] }), [GUIDANCE.adult]);
});

test("the notes say downloads are likely public records and the use rule is not confidentiality", () => {
  assert.match(PUBLIC_RECORD_NOTE, /^What you download, print, copy, screenshot or send from this site, and your messages about it on any account or device, are likely City public records under the California Public Records Act and may have to be released on request\. Nothing on this site makes them confidential\.$/);
  assert.ok(USE_NOTE.endsWith("That is a use rule, not a promise of confidentiality."));
  assert.doesNotMatch(PUBLIC_RECORD_NOTE + USE_NOTE, /redistribution/i);
});

test("the district view's guidance is for staff, and names the districts the checks flag", () => {
  assert.deepEqual(districtGuidance({ review_status: STATUS }), [], "not on the public site");
  const g = districtGuidance({ audience: "staff", review_status: STATUS });
  assert.equal(g.length, 3);
  assert.match(g[0], /^Open a district's list/);
  assert.equal(g[2], "A band is wrong more often in Districts 4 and 9 than elsewhere: do not compare districts by how many places are in a band.",
    "an older export without evidence_above_even: the gate text's districts");
  assert.equal(districtGuidance({ audience: "staff" }).length, 2);
});

// District 5's share of the wrongly named is above even, but its family-wise interval spans 1.
const byDistrict = (ev) => ({
  4: { named: 30, precision: 0.29, false_share_ratio: 1.9, interval_family: [1.1, 3.0], interval_family_deff: [1.02, 3.4], evidence_above_even: ev[4] },
  5: { named: 22, precision: 0.33, false_share_ratio: 1.5, interval_family: [0.8, 2.6], interval_family_deff: [0.5, 2.9], evidence_above_even: ev[5] },
  9: { named: 25, precision: 0.3, false_share_ratio: 1.8, interval_family: [1.2, 2.7], interval_family_deff: [1.01, 3.1], evidence_above_even: ev[9] },
  None: { named: 3, evidence_above_even: true },
});
const EVIDENCE_4_9 = "In the backtest, band 1 places in Districts 4 and 9 went on to have no major violation more often than elsewhere, even allowing for chance; " +
  "part of this may be how inspectors there cite. Do not compare districts by how many places are in a band.";

test("the fairness line names only the districts whose family-wise interval starts above even", () => {
  const meta = { audience: "staff", review_status: [...STATUS, "district 5: 1.5x its share of wrongly named places (22 named)"],
                 fairness: { by_district: byDistrict({ 4: true, 5: false, 9: true }) } };
  assert.deepEqual(evidenceDistricts(meta), [4, 9], "not District 5, whose interval spans even; never the places outside the City");
  assert.equal(fairnessLine(meta), EVIDENCE_4_9);
  const g = reviewGuidance(meta);
  assert.ok(g.includes(EVIDENCE_4_9));
  assert.ok(!g.some((s) => /wrong more often|District 5\b/.test(s)), "the gate text no longer names districts");
  assert.equal(g.indexOf(EVIDENCE_4_9), g.indexOf(GUIDANCE.nothingToName) + 1, "where the district line was");
  assert.equal(districtGuidance(meta)[2], EVIDENCE_4_9, "the district view says the same");
  // one district; the bands the district figures cover
  const one = { fairness: { bands_used: ["1", "2", "3"], by_district: byDistrict({ 4: true, 5: false, 9: false }) } };
  assert.equal(fairnessLine(one),
    "In the backtest, places in bands 1 to 3 in District 4 went on to have no major violation more often than elsewhere, even allowing for chance; " +
      "part of this may be how inspectors there cite. Do not compare districts by how many places are in a band.");
});

test("no district above even at the family-wise low end: no fairness line, whatever the gate text says", () => {
  const meta = { audience: "staff", review_status: STATUS, fairness: { by_district: byDistrict({ 4: false, 5: false, 9: false }) } };
  assert.deepEqual(evidenceDistricts(meta), []);
  assert.equal(fairnessLine(meta), null);
  assert.ok(!reviewGuidance(meta).some((s) => /District|district/.test(s)));
  assert.equal(districtGuidance(meta).length, 2);
});

test("an export without evidence_above_even falls back to the districts its gate text names", () => {
  const old = { review_status: STATUS, fairness: { by_district: { 4: { named: 30, precision: 0.29 }, 9: { named: 25 } } } };
  assert.equal(evidenceDistricts(old), null);
  assert.equal(evidenceDistricts({}), null);
  assert.equal(fairnessLine(old), "A band is wrong more often in Districts 4 and 9 than elsewhere: do not compare districts by how many places are in a band.");
  assert.equal(fairnessLine({ review_status: ["district 3: false-positive rate 1.6x the City's"] }),
    "A band is wrong more often in District 3 than elsewhere: do not compare districts by how many places are in a band.");
  assert.equal(fairnessLine({}), null);
  assert.equal(evidenceDistricts({ fairness: { by_district: { 4: { evidence_above_even: "yes" } } } }), null, "only true or false counts");
});

test("a staff CSV download is logged to the site's own server; a public one is not; neither can throw", async () => {
  const sent = [];
  const nav = { sendBeacon: (url, body) => { sent.push([url, body]); return true; } };
  assert.equal(auditCsv({ audience: "staff" }, 12, "food-inspection-record-district-3-2026-09-29.csv", nav), true);
  assert.equal(sent.length, 1);
  assert.equal(sent[0][0], "/audit");
  assert.equal(sent[0][1].type, "application/json");
  assert.deepEqual(JSON.parse(await sent[0][1].text()), { event: "csv", rows: 12, name: "food-inspection-record-district-3-2026-09-29.csv" });
  assert.equal(auditCsv({ sample: true }, 1, "x.csv", nav), false);
  assert.equal(sent.length, 1, "nothing sent from the public site");
  assert.equal(auditCsv({ audience: "staff" }, 1, "x.csv", { sendBeacon: () => { throw new Error("blocked"); } }), false);
  assert.equal(auditCsv({ audience: "staff" }, 1, "x.csv", null), false);
});

test("a staff print is logged like a download", async () => {
  const sent = [];
  const nav = { sendBeacon: (url, body) => { sent.push([url, body]); return true; } };
  assert.equal(auditPrint({ audience: "staff" }, "/place/DEH2024-FFPP-000001", nav), true);
  assert.deepEqual(JSON.parse(await sent[0][1].text()), { event: "print", name: "/place/DEH2024-FFPP-000001" });
  assert.equal(auditPrint({ sample: true }, "/", nav), false);
  assert.equal(sent.length, 1);
});

test("an ended staff session goes back to the sign-in page, never on the public site", () => {
  const went = [];
  const loc = { pathname: "/place/DEH-1", search: "?list", assign: (u) => went.push(u) };
  assert.equal(signInAgain({ status: 401 }, loc), false, "the public build has no sign-in");
  globalThis.__STAFF__ = true;
  try {
    assert.equal(signInAgain({ status: 200 }, loc), false);
    assert.equal(signInAgain({ status: 401 }, loc), true);
    assert.deepEqual(went, ["/login?next=%2Fplace%2FDEH-1%3Flist"]);
  } finally {
    delete globalThis.__STAFF__;
  }
});
