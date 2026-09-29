import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  isStaff, contactLine, reviewStatus, reviewGuidance, districtGuidance, auditCsv, auditPrint, signInAgain, GUIDANCE, PUBLIC_RECORD_NOTE, USE_NOTE,
  evidenceDistricts, fairnessLine, USE_NOTE_SHORT, compactBanner, openChecksSentence, watchPrints, describePrints, printSubject,
  driftNoteGuidance, DISTRICT_CITING_NOTE, districtStatus, districtShareLine, staffBar,
} from "../src/lib/staff.js";

const src = join(dirname(fileURLToPath(import.meta.url)), "..", "src");

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
  assert.equal(g.length, 4);
  assert.match(g[0], /^Open a district's list/);
  assert.equal(g[2], DISTRICT_CITING_NOTE);
  assert.equal(g[3], "A band is wrong more often in Districts 4 and 9 than elsewhere: do not compare districts by how many places are in a band.",
    "an older export without evidence_above_even: the gate text's districts");
  assert.equal(districtGuidance({ audience: "staff" }).length, 3);
});

test("every staff export's district view says its counts are what inspectors cite, to take to the County, not to rank", () => {
  assert.equal(DISTRICT_CITING_NOTE,
    "Majors, closures and B or C grades are what the County's inspectors cite, and the record does not say which inspector made a visit, " +
      "so a gap between districts may be how they are cited. Take a district's pattern to the County as a question, not as a ranking of districts.");
  const none = { 4: { false_share_ratio: 1.9, interval: [1.2, 2.6], evidence_above_even: false } };
  for (const meta of [{ audience: "staff" }, { audience: "staff", review_status: STATUS }, { audience: "staff", fairness: { by_district: none } }]) {
    assert.ok(districtGuidance(meta).includes(DISTRICT_CITING_NOTE), JSON.stringify(meta).slice(0, 60));
  }
  assert.ok(!districtGuidance({ sample: true }).includes(DISTRICT_CITING_NOTE), "never on the public site");
  assert.doesNotMatch(DISTRICT_CITING_NOTE, /compare a district with itself over time/, "the site has no view over time");
});

test("only the district selected is given as shares of its own places", () => {
  assert.equal(districtShareLine("District 3", { n: 1336, major: 276, closed: 24, bc: 40 }),
    "District 3, out of its 1,336 listed places: a major violation at 21 in 100, ordered closed at 2 in 100, a B or C grade at 3 in 100.");
  assert.equal(districtShareLine("District 4", { n: 1, major: 1, closed: 0, bc: 0 }),
    "District 4, out of its 1 listed place: a major violation at 100 in 100, ordered closed at 0 in 100, a B or C grade at 0 in 100.");
  assert.equal(districtShareLine("District 5", { n: 0, major: 0, closed: 0, bc: 0 }), null, "no places, no share");
  assert.equal(districtShareLine("District 5", null), null);
});

// District 5's share of the wrongly named is above even, but its family-wise interval spans 1.
const byDistrict = (ev) => ({
  4: { named: 30, precision: 0.29, false_share_ratio: 1.9, interval_family: [1.1, 3.0], interval_family_deff: [1.02, 3.4], evidence_above_even: ev[4] },
  5: { named: 22, precision: 0.33, false_share_ratio: 1.5, interval_family: [0.8, 2.6], interval_family_deff: [0.5, 2.9], evidence_above_even: ev[5] },
  9: { named: 25, precision: 0.3, false_share_ratio: 1.8, interval_family: [1.2, 2.7], interval_family_deff: [1.01, 3.1], evidence_above_even: ev[9] },
  None: { named: 3, evidence_above_even: true },
});
const EVIDENCE_4_9 = "In the backtest, places in Districts 4 and 9 were put in band 1 and then had no major violation about 1.9 and 1.8 times as often as across the City respectively, for their number of places, even allowing for chance; " +
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
  assert.equal(districtGuidance(meta)[3], EVIDENCE_4_9, "the district view says the same, after the citing note");
  // one district; the bands the district figures cover
  const one = { fairness: { bands_used: ["1", "2", "3"], by_district: byDistrict({ 4: true, 5: false, 9: false }) } };
  assert.equal(fairnessLine(one),
    "In the backtest, places in District 4 were put in bands 1 to 3 and then had no major violation about 1.9 times as often as across the City, for their number of places, even allowing for chance; " +
      "part of this may be how inspectors there cite. Do not compare districts by how many places are in a band.");
});

test("no district above even at the family-wise low end: no fairness line, whatever the gate text says", () => {
  const meta = { audience: "staff", review_status: STATUS, fairness: { by_district: byDistrict({ 4: false, 5: false, 9: false }) } };
  assert.deepEqual(evidenceDistricts(meta), []);
  assert.equal(fairnessLine(meta), null);
  assert.ok(!reviewGuidance(meta).some((s) => /District|district/.test(s)));
  assert.equal(districtGuidance(meta).length, 3, "the two uses and the citing note");
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

test("the demonstration line follows access_approved, including TRUST applying without the Council", () => {
  assert.equal(reviewGuidance({ audience: "staff", access_approved: false, review_status: [] })[0], GUIDANCE.demonstration);
  assert.ok(!reviewGuidance({ audience: "staff", access_approved: true, review_status: [] }).includes(GUIDANCE.demonstration));
  assert.equal(reviewGuidance({ review_status: ["the TRUST Ordinance applies and the Council has not approved this use (council_approval)"] })[0],
    GUIDANCE.demonstration, "an older export: from the status line");
});


const CONTACT = { name: "A. Student", email: "student@example.org" };
const staffWith = (extra = {}) => ({ audience: "staff", contact: CONTACT, access_approved: false, review_status: [...STATUS, ...NEW_STATUS], ...extra });

test("the phone banner keeps the use rule, the public-record note and the contact in view, and every instruction one tap away", () => {
  const meta = staffWith();
  const b = compactBanner(meta);
  assert.deepEqual(b.lead, [GUIDANCE.demonstration, USE_NOTE_SHORT, PUBLIC_RECORD_NOTE], "the demonstration line while it applies");
  assert.equal(b.contact, "Questions and corrections: A. Student (student@example.org).");
  assert.equal(b.use, USE_NOTE, "the full use rule");
  assert.equal(b.open, `This list has not passed ${STATUS.length + NEW_STATUS.length} of the checks a public release would need.`);
  assert.deepEqual(b.guidance, reviewGuidance(meta), "every instruction the full banner lists, in the same words");
  assert.equal(b.summary, `The full use rule and all ${b.guidance.length} instructions`);
  // once the City has recorded its request and TRUST answer, the use rule still leads
  const approved = compactBanner(staffWith({ access_approved: true }));
  assert.deepEqual(approved.lead, [USE_NOTE_SHORT, PUBLIC_RECORD_NOTE]);
  assert.ok(!approved.guidance.includes(GUIDANCE.demonstration));
  const bare = compactBanner({ audience: "staff" });
  assert.equal(bare.contact, null);
  assert.equal(bare.open, null);
  assert.equal(bare.summary, "The full use rule");
  assert.equal(openChecksSentence({ review_status: ["x"] }), "This list has not passed 1 of the checks a public release would need.");
});

test("the short use rule says what the full one forbids", () => {
  for (const words of [/not a City or County finding/, /do not forward names or bands outside the City/, /contact a business about its band/, /any decision about a business/]) {
    assert.match(USE_NOTE_SHORT, words);
  }
});

/** A window stand-in: an EventTarget with a location. */
function fakeWindow(pathname = "/map", search = "?place=DEH2024-FFPP-000001") {
  const w = new EventTarget();
  w.location = { pathname, search };
  return w;
}
const beacons = () => {
  const sent = [];
  return { sent, nav: { sendBeacon: (url, body) => { sent.push([url, body]); return true; } } };
};

test("every print on the staff site is logged exactly once, from any layout, and never on the public site", async () => {
  const win = fakeWindow();
  const { sent, nav } = beacons();
  const stop = watchPrints({ audience: "staff" }, win, nav);
  win.dispatchEvent(new Event("beforeprint"));
  assert.equal(sent.length, 1);
  assert.equal(sent[0][0], "/audit");
  assert.deepEqual(JSON.parse(await sent[0][1].text()), { event: "print", name: "/map?place=DEH2024-FFPP-000001" });
  stop();
  win.dispatchEvent(new Event("beforeprint"));
  assert.equal(sent.length, 1, "stopped");
  const pub = fakeWindow();
  watchPrints({ sample: true }, pub, nav);
  pub.dispatchEvent(new Event("beforeprint"));
  assert.equal(sent.length, 1, "the public site logs nothing");
  assert.doesNotThrow(() => watchPrints({ audience: "staff" }, null, nav)());
});

test("the list's printout is logged under its scope and row count while it is what prints", async () => {
  const win = fakeWindow("/", "?list=1");
  const { sent, nav } = beacons();
  const stop = watchPrints({ audience: "staff" }, win, nav);
  const unregister = describePrints(() => ({ name: "list food-inspection-record-district-3-2026-09-29", rows: 1336 }));
  win.dispatchEvent(new Event("beforeprint"));
  assert.deepEqual(JSON.parse(await sent[0][1].text()), { event: "print", rows: 1336, name: "list food-inspection-record-district-3-2026-09-29" });
  unregister();
  win.dispatchEvent(new Event("beforeprint"));
  assert.deepEqual(JSON.parse(await sent[1][1].text()), { event: "print", name: "/?list=1" }, "back to the page's address");
  const quiet = describePrints(() => null);
  assert.deepEqual(printSubject(win.location), { name: "/?list=1", rows: undefined }, "a describer with nothing to say");
  quiet();
  const u = describePrints(() => { throw new Error("gone"); });
  assert.equal(printSubject(win.location).name, "/?list=1", "a describer that throws never stops the log");
  u();
  assert.equal(printSubject({ pathname: `/${"x".repeat(200)}`, search: "" }).name.length, 120, "the server takes 120 characters");
  stop();
});

test("the print log is mounted once at the root of the app, never by a banner", () => {
  const read = (name) => readFileSync(join(src, name), "utf8");
  const banner = read("StaffBanner.jsx");
  assert.doesNotMatch(banner, /addEventListener\(\s*["']beforeprint/, "no banner listens for prints");
  const app = read("App.jsx");
  assert.equal(app.match(/<PrintAudit \/>/g)?.length, 1, "one print log");
  const root = app.slice(app.indexOf("export default function App()"), app.indexOf("function Dashboard()"));
  assert.match(root, /<PrintAudit \/>[\s\S]*status === "loading"/, "above every view and layout, the phone shell included");
  for (const name of ["MobileShell.jsx", "PageFrame.jsx", "Landing.jsx"]) assert.doesNotMatch(read(name), /PrintAudit|beforeprint/, name);
  assert.match(read("MobileShell.jsx"), /<StaffBanner compact \/>/);
});

const LOW = "In the latest quarter (2026 Q3, through September 28) 20.4% of routine inspections found a major violation, against 17.5% over the backtest year, so the rates here may be low.";

test("the export's drift note becomes an instruction: the rates are probably low (or high)", () => {
  assert.equal(driftNoteGuidance({ drift: { note: LOW } }), GUIDANCE.driftLow);
  assert.match(GUIDANCE.driftLow, /every rate on this site is probably low\.$/);
  assert.equal(driftNoteGuidance({ drift: { note: LOW.replace("may be low", "may be high") } }), GUIDANCE.driftHigh);
  assert.equal(driftNoteGuidance({ drift: { note: "Something else.", latest_rate: 0.2, major_rate_backtest: 0.17 } }), GUIDANCE.driftLow, "from the rates");
  assert.equal(driftNoteGuidance({ drift: { note: "Something else.", latest_rate: 0.15, major_rate_backtest: 0.17 } }), GUIDANCE.driftHigh);
  assert.equal(driftNoteGuidance({ drift: { note: "Something else." } }), null);
  assert.equal(driftNoteGuidance({ drift: { note: null, latest_rate: 0.2, major_rate_backtest: 0.17 } }), null, "no note, no instruction");
  const meta = { audience: "staff", review_status: STATUS, drift: { status: "not_yet_measurable", refit_needed: false, note: LOW } };
  const g = reviewGuidance(meta);
  assert.ok(g.includes(GUIDANCE.driftLow));
  assert.ok(!g.includes(GUIDANCE.drift), "not a refit alarm");
  assert.equal(g.indexOf(GUIDANCE.driftLow), g.indexOf(GUIDANCE.prospective) - 1, "where the drift line goes");
  assert.equal(openChecksSentence(meta), `This list has not passed ${STATUS.length} of the checks a public release would need.`, "not counted as an open check");
  assert.ok(compactBanner(meta).guidance.includes(GUIDANCE.driftLow), "on the phone banner too");
  assert.ok(reviewGuidance({ ...meta, review_status: [...STATUS, NEW_STATUS.at(-1)] }).includes(GUIDANCE.drift), "a refit line still gives its own");
});

// The shape of a real export's district figures: one district above even on both wider intervals, one
// above even for itself and family-wise, one for itself only.
const STATUS_DISTRICTS = {
  4: { false_share_ratio: 2.05, interval: [1.28, 2.86], interval_family: [1.0, 3.26], interval_family_deff: [0.57, 3.76], evidence_above_even: false },
  6: { false_share_ratio: 1.32, interval: [1.1, 1.54], interval_family: [1.01, 1.63], interval_family_deff: [0.88, 1.77], evidence_above_even: false },
  7: { false_share_ratio: 0.48, interval: [0.25, 0.74], interval_family: [0.16, 0.87], interval_family_deff: [0.03, 1.04], evidence_above_even: false },
  9: { false_share_ratio: 1.88, interval: [1.5, 2.29], interval_family: [1.34, 2.47], interval_family_deff: [1.11, 2.71], evidence_above_even: true },
  None: { interval: [2, 3], evidence_above_even: false },
};

test("About says which districts are above even under which interval, from the export's fields", () => {
  const meta = { audience: "staff", fairness: { by_district: STATUS_DISTRICTS } };
  assert.deepEqual(districtStatus(meta), [
    "Only District 9 stays above even on both wider intervals, allowing for chance across the nine districts and for inspectors, so the banner and the district view name only it.",
    "District 6 is above even on the 95% interval for the district alone and on the family-wise one, but not once inspectors are allowed for too.",
    "District 4 is above even on the 95% interval for the district alone, but not on the family-wise one, which allows for chance across the nine districts.",
  ]);
  assert.match(fairnessLine(meta), /places in District 9 were put in band 1/, "the banner's line names the same district");
  assert.equal(districtStatus({ fairness: { by_district: STATUS_DISTRICTS } }, { staff: false })[0],
    "Only District 9 stays above even on both wider intervals, allowing for chance across the nine districts and for inspectors.", "no banner on the public site");
  const none = { 4: STATUS_DISTRICTS[4], 5: { ...STATUS_DISTRICTS[4] } };
  assert.deepEqual(districtStatus({ audience: "staff", fairness: { by_district: none } }), [
    "No district stays above even on both wider intervals, allowing for chance across the nine districts and for inspectors, so the banner and the district view name none.",
    "Districts 4 and 5 are above even on the 95% interval for the district alone, but not on the family-wise one, which allows for chance across the nine districts.",
  ]);
  assert.equal(districtStatus({ fairness: { by_district: { 4: { interval: [1.2, 2] } } } }), null, "an older export keeps its gate lines alone");
  assert.equal(districtStatus({}), null);
});

test("the one-line staff bar keeps each rule in view in a few words, and opens the whole notice", () => {
  const meta = staffWith();
  const b = staffBar(meta);
  assert.deepEqual(b.points, [
    "For City of San Diego staff",
    "Downloads are likely public records",
    "A student analysis, not a City or County finding",
    "A demonstration, not a City tool",
    `${STATUS.length + NEW_STATUS.length} open checks`,
  ]);
  assert.equal(b.toggle, `The notice and ${b.guidance.length} instructions`);
  // the panel holds what the full banner held, in the same words
  assert.deepEqual(b.guidance, reviewGuidance(meta));
  assert.equal(b.use, USE_NOTE);
  assert.equal(b.open, openChecksSentence(meta));
  assert.equal(b.contact, "Questions and corrections: A. Student (student@example.org).");
  const approved = staffBar(staffWith({ access_approved: true, review_status: ["x"] }));
  assert.ok(!approved.points.includes("A demonstration, not a City tool"), "not once the City's request and TRUST answer are on record");
  assert.equal(approved.points.at(-1), "1 open check");
  const bare = staffBar({ audience: "staff" });
  assert.deepEqual(bare.points.slice(0, 3), ["For City of San Diego staff", "Downloads are likely public records", "A student analysis, not a City or County finding"]);
  assert.ok(!bare.points.some((p) => /open check/.test(p)), "no count without open checks");
});

test("the staff bar opens by itself once a session, prints the whole notice, and signs out by POST", () => {
  const banner = readFileSync(join(src, "StaffBanner.jsx"), "utf8");
  assert.match(banner, /sessionStorage/, "once a browser session");
  assert.match(banner, /print-only[\s\S]*PUBLIC_RECORD_NOTE[\s\S]*USE_NOTE/, "on paper, the whole notice");
  assert.match(banner, /method="post" action="\/logout"/, "sign-out is a POST");
});
