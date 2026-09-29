import { test } from "node:test";
import assert from "node:assert/strict";
import {
  bandDefs, bandShare, bandPoints, bandSummary, bandRatePhrase, bandInterval, rateRatio, restRatio, ruleSentence, backtestList, stabilitySentence,
  estimateSentence, persistenceSentence, backtestPeriod, districtSentence, GROUP_NOTE, SAME_AS_PERSISTENCE, DRIFT_NOTE,
  scoreUsedText, scoresRead, utilityRows, frozenLine, driftLine, band1ByRoute, routeSentence, isOutside,
  CLOSURE_GROUP, DRIFT_NOT_YET, driftNote, driftLines, costLimit, costLimitSentence, districtPrecision, auditedBandsName, auditedGroup,
  driftNotYet, curveFor, curveGroups, curveGroupFor, curveGroupRows, curveGroupSpread, pointsSpan,
} from "../src/lib/bands.js";
import { bandsMeta, staffMeta } from "./fixtures/bandsMeta.mjs";


test("bands are ranges of points and slices of the scored places", () => {
  const defs = bandDefs(bandsMeta);
  assert.deepEqual(defs.map((d) => d.band), ["1", "2", "3"]);
  assert.deepEqual(defs.map((d) => Math.round(d.width * 1000) / 1000), [0.025, 0.05, 0.1]);
  assert.equal(bandShare(bandsMeta, "1"), "about the 2.5% of scored places with the most points");
  assert.equal(bandShare(bandsMeta, 3), "about the next 10% by points");
  assert.equal(bandShare(bandsMeta, "9"), null);
  assert.equal(bandPoints(bandsMeta, "1"), "20 points or more", "the top band has no upper limit");
  assert.equal(bandPoints(bandsMeta, "2"), "16 to 19 points");
  assert.equal(bandPoints({ card: { bands: [{ band: "1", min_points: 20, max_points: 20 }] } }, "1"), "20 points");
  assert.equal(bandPoints({}, "1"), null);
  assert.equal(ruleSentence(bandsMeta), bandsMeta.card.rule);
  assert.match(ruleSentence({}), /students' point rule/);
});

test("the band line gives the rate, its likely range, the comparison and the share that had none", () => {
  assert.equal(
    bandSummary(staffMeta, "1").split(". ")[0] + ".",
    "In the backtest, about 37 in 100 band 1 places had a major violation at their next routine inspection (likely 33 to 41), against 21 in 100 of all scored restaurants; about 63 in 100 had none.",
  );
  // below the bands is the comparison only when the export has no rate for all scored restaurants
  assert.equal(
    bandSummary(bandsMeta, "2"),
    "In the backtest, about 33 in 100 band 2 places had a major violation at their next routine inspection (likely 27 to 39), against 16 in 100 of scored places below the bands; about 67 in 100 had none.",
  );
  const noRest = { card: { bands: bandsMeta.card.bands.map((b) => ({ ...b, vs_baseline: null })) } };
  assert.equal(bandSummary(noRest, "2"), "In the backtest, about 33 in 100 band 2 places had a major violation at their next routine inspection (likely 27 to 39); about 67 in 100 had none.");
  assert.equal(bandSummary({}, "1"), "Band 1 has no backtest rate in this export.");
  for (const b of ["1", "2", "3"]) {
    const [n, none] = [...bandSummary(bandsMeta, b).matchAll(/about (\d+) in 100/g)].map((m) => Number(m[1]));
    assert.equal(n + none, 100, "the two shares add up to 100");
  }
  assert.equal(rateRatio(bandsMeta, "1"), 3.4);
  assert.equal(bandRatePhrase(bandsMeta, "3"), "30% had a major");
  assert.equal(bandInterval(bandsMeta, "1"), "95% interval 46% to 63%");
  assert.equal(backtestList(bandsMeta), "the list drawn up the same way on September 1, 2025");
  assert.equal(stabilitySentence({ band: "2", band_stability: 0.67 }), "Stayed in band 2 in 67% of refits of the rule on resampled data.");
  assert.equal(stabilitySentence({ band: "2" }), null);
});

test("when the same-size group picked by recent major violations did as well, the band line says so", () => {
  assert.equal(SAME_AS_PERSISTENCE, "Sorting by recent major violations alone picks out a group with the same rate.");
  assert.ok(bandSummary(staffMeta, "1").endsWith(SAME_AS_PERSISTENCE), "vs_baseline [-3.1, 2.9] spans zero");
  assert.ok(bandSummary(bandsMeta, "1").endsWith(SAME_AS_PERSISTENCE), "vs_baseline [-4, 9] spans zero");
  assert.ok(!bandSummary(bandsMeta, "2").includes(SAME_AS_PERSISTENCE), "no interval, no claim");
  const better = { card: { ...staffMeta.card, bands: [{ ...staffMeta.card.bands[0], vs_baseline: [1, 8] }] } };
  assert.ok(!bandSummary(better, "1").includes(SAME_AS_PERSISTENCE), "an interval above zero is not the same rate");
});

test("for a City place with a council district, the band line adds what the band's places there did", () => {
  assert.equal(districtSentence(staffMeta, "1", 4), "In council district 4, about 29 in 100 band 1 places had one (likely 20 to 39).");
  assert.equal(districtSentence(staffMeta, "1", 2), "In council district 2, about 41 in 100 band 1 places had one.");
  assert.equal(districtSentence(staffMeta, "1", 7), null, "no figures for the district");
  assert.equal(districtSentence(staffMeta, "1", null), null);
  assert.equal(districtSentence({ ...staffMeta, fairness: { ...staffMeta.fairness, bands_used: ["1", "2", "3"] } }, "2", 4),
    "In council district 4, about 29 in 100 places in bands 1 to 3 had one (likely 20 to 39).", "the group the figures cover");
  assert.equal(districtSentence(staffMeta, "2", 4), null, "band 2 is not in the audited bands");
  assert.ok(bandSummary(staffMeta, "1", { district: 4 }).endsWith("In council district 4, about 29 in 100 band 1 places had one (likely 20 to 39)."));
  assert.ok(!bandSummary(staffMeta, "1", { district: 4, outside: true }).includes("council district"), "never outside the City");
  assert.equal(isOutside({ council_district: null }, staffMeta), false, "no outside rates, so City rates");
  assert.equal(isOutside({ council_district: null }, { card: { outside: {} } }), true);
});

test("the below-the-bands ratio is their rate against the comparison rate, never a fixed 1", () => {
  assert.equal(restRatio(staffMeta), 0.9, "0.18 / 0.21");
  assert.equal(restRatio(bandsMeta), 1, "below the bands is itself the comparison");
  assert.equal(restRatio({}), null);
});

test("a place outside the City is described by the rates measured outside the City", () => {
  const meta = { ...bandsMeta, card: { ...bandsMeta.card, base_rate: 0.2,
    outside: { base_rate: 0.17, bands: [{ band: "1", rate: 0.33, interval: [0.29, 0.37] }],
               curve: { rate: [0.05, 0.1, 0.2], low: [0.04, 0.08, 0.17], high: [0.06, 0.12, 0.24] } } } };
  assert.equal(bandSummary(meta, "1", { outside: true }),
    "In the backtest, about 33 in 100 band 1 places outside the City had a major violation at their next routine inspection (likely 29 to 37), against 17 in 100 of all scored restaurants outside the City; about 67 in 100 had none.");
  assert.equal(estimateSentence(meta, 2, { outside: true }),
    "Scored restaurants outside the City with about 2 points: about 20 in 100 had a major violation at their next routine inspection in the backtest of the list drawn up on September 1, 2025 (likely 17 to 24). The likely range reflects sampling only, not changes since then.");
});

test("an estimate names the backtest it comes from, says its range is sampling only, and notes drift", () => {
  assert.equal(backtestPeriod(staffMeta), "the backtest of lists drawn up from March 1, 2025 to September 1, 2025", "by_origin dates, in order");
  assert.equal(backtestPeriod({ card: { trained_on: staffMeta.card.trained_on } }), "the backtest over the record from July 1, 2023 to September 1, 2025");
  assert.equal(backtestPeriod({ card: { trained_on: "sample: invented weights" }, catch_run: { as_of: "2025-09-01" } }), "the backtest of the list drawn up on September 1, 2025");
  assert.equal(backtestPeriod({}), "the backtest");
  assert.equal(
    estimateSentence(staffMeta, 12),
    "Scored restaurants with about 12 points: about 39 in 100 had a major violation at their next routine inspection in the backtest of the list drawn up on September 1, 2025 (likely 35 to 43). " +
      "The likely range reflects sampling only, not changes since then. The County's record has changed since these rates were measured.",
    "read at the largest point on the curve; drift noted",
  );
  const calm = { ...staffMeta, drift: { refit_needed: false, reasons: [] } };
  assert.ok(!estimateSentence(calm, 3).includes(DRIFT_NOTE));
  assert.match(estimateSentence(calm, 1, { estimate: { rate: 0.41, low: 0.3, high: 0.5 } }), /about 41 in 100 .* \(likely 30 to 50\)\. The likely range reflects sampling only/);
  assert.doesNotMatch(estimateSentence(calm, 1, { estimate: { rate: 0.41 } }), /likely/, "no range, no range sentence");
  assert.equal(estimateSentence(staffMeta, null), null);
  assert.equal(estimateSentence({}, 5), null);
});

test("the persistence comparison follows the data; the group note says what a band is not", () => {
  const similar = { card: { bands: [{ band: "1", baseline_rate: 0.37, vs_baseline: [-23, 26] }] } };
  assert.match(persistenceSentence(similar), /similar rate \(about 37 in 100\)\. The points are a transparent summary of that record, not a better predictor\.$/);
  const better = { card: { bands: [{ band: "1", baseline_rate: 0.3, vs_baseline: [4, 30] }] } };
  assert.match(persistenceSentence(better), /whose rate was lower \(about 30 in 100\): band 1 found more/);
  assert.equal(persistenceSentence({}), null);
  assert.equal(GROUP_NOTE, "A band describes what happened to a group of places; it is not a finding that this place has, or will have, a violation.");
});

test("the scores the average reads say what the County recorded for a closure and what the rule counts", () => {
  assert.equal(scoreUsedText({ date: "2025-02-01", score: 95, closure: false, county_score: 95 }), "February 1, 2025: 95");
  assert.equal(scoreUsedText({ date: "2026-01-15", score: 70, closure: true, county_score: null }),
    "January 15, 2026: closed, no County score; this rule counts it as 70");
  assert.equal(scoreUsedText({ date: "2026-03-03", score: 70, closure: true, county_score: 84 }),
    "March 3, 2026: closed (the County's score that day: 84); this rule counts a closure as 70");
  assert.equal(scoreUsedText({ date: "2026-01-15", score: 70, closure: true }), "January 15, 2026: closed; this rule counts a closure as 70", "an older export");
  const r = scoresRead([{ date: "2025-02-01", score: 95, closure: false }, { date: "2025-08-01", score: 94 }, { date: "2026-01-15", score: 70, closure: true, county_score: 88 }]);
  assert.equal(r.mean, 86.3, "a closure counts as 70 whatever the County's score");
  assert.equal(r.lines.length, 3);
  assert.equal(scoresRead([]), null);
  assert.equal(scoresRead([{ date: "2025-01-01" }]), null);
});

test("the cost-ratio table, the frozen rule, drift and band 1 by route read from meta, and are absent without it", () => {
  assert.deepEqual(utilityRows(staffMeta), [{ cost_ratio: 0.25, bar: 0.2, named: [] }, { cost_ratio: 1, bar: 0.5, named: [] }]);
  assert.equal(utilityRows(bandsMeta), null);
  assert.equal(utilityRows({ utility: null }), null);
  assert.equal(frozenLine(staffMeta), "Rule version 2026-09-20-abcd1234, frozen September 20, 2026.");
  assert.equal(frozenLine({ frozen: null }), null);
  assert.equal(driftLine(staffMeta), "The County's record has changed since these rates were measured: routine major rate 27.0% in the last full quarters against 21.0% in the backtest.");
  assert.equal(driftLine({ drift: { refit_needed: true } }), DRIFT_NOTE);
  assert.equal(driftLine({ drift: { refit_needed: false, reasons: ["x"] } }), null);
  assert.equal(driftLine({}), null);
  assert.equal(routeSentence(staffMeta),
    "In the backtest, about 45 in 100 band 1 places that were in it because of a closure counted as 70 had a major violation at their next routine inspection (likely 33 to 58), against about 36 in 100 of those in it on routine scores alone (likely 32 to 40).");
  const list = { card: { band_1_by_route: [{ route: "no_closure", rate: 0.3 }, { route: "closure_70", rate: 0.5 }] } };
  assert.equal(band1ByRoute(list).closure.rate, 0.5);
  assert.equal(band1ByRoute(list).scores.rate, 0.3);
  assert.match(routeSentence({ card: { band_1_by_route: { closure: { rate: 0.5 } } } }), /^In the backtest, about 50 in 100 band 1 places that were in it because of a closure/);
  assert.equal(routeSentence(bandsMeta), null);
});

const NOTE = "In the latest quarter (2026 Q3) 20.5% of routine inspections found a major violation, against 17.5% over the backtest year, so the rates here may be low.";
const calmMeta = { ...staffMeta, drift: { refit_needed: false, reasons: [] } };

test("an estimate read from the closure curve says whose rate it is; one from the scores curve reads as before", () => {
  assert.equal(CLOSURE_GROUP, "whose last two years include a routine inspection that ended in a closure");
  assert.equal(
    estimateSentence(calmMeta, 30, { estimate: { rate: 0.28, low: 0.22, high: 0.34, group: "closure" } }),
    "Scored restaurants with about 30 points whose last two years include a routine inspection that ended in a closure: about 28 in 100 had a major violation at their next routine inspection in the backtest of the list drawn up on September 1, 2025 (likely 22 to 34). " +
      "The likely range reflects sampling only, not changes since then.",
  );
  assert.equal(
    estimateSentence(calmMeta, 30, { estimate: { rate: 0.28, low: 0.22, high: 0.34, group: "scores" } }),
    estimateSentence(calmMeta, 30, { estimate: { rate: 0.28, low: 0.22, high: 0.34 } }),
    "the scores group, and an older export's estimate without a group, read the same",
  );
  assert.match(estimateSentence(calmMeta, 30, { outside: true, estimate: { rate: 0.2, low: 0.1, high: 0.3, group: "closure" } }),
    /^Scored restaurants outside the City with about 30 points whose last two years include a routine inspection that ended in a closure: about 20 in 100/);
  // without a place estimate the site reads `curve`, and says nothing about a group
  assert.doesNotMatch(estimateSentence({ ...calmMeta, card: { ...calmMeta.card, curve_closure: { rate: [0.9], low: [0.8], high: [0.95] } } }, 3), /closure/);
});

test("the export's drift note follows the estimate, after the sampling and refit sentences", () => {
  const noted = { ...staffMeta, drift: { ...staffMeta.drift, note: NOTE } };
  assert.equal(driftNote(noted), NOTE);
  assert.equal(driftNote({ drift: { note: "  " } }), null);
  assert.equal(driftNote({ drift: { note: null } }), null);
  assert.equal(driftNote({}), null);
  const s = estimateSentence(noted, 12);
  assert.ok(s.endsWith(`The likely range reflects sampling only, not changes since then. ${DRIFT_NOTE} ${NOTE}`), s);
  const calmNoted = { ...calmMeta, drift: { refit_needed: false, reasons: [], status: "not_yet_measurable", note: NOTE } };
  assert.ok(estimateSentence(calmNoted, 12).endsWith(`not changes since then. ${NOTE}`), "a note without a refit");
  assert.ok(estimateSentence(calmNoted, 3, { estimate: { rate: 0.3, group: "closure" } }).endsWith(NOTE), "a note even without a range");
});

test("the About page's drift lines: not yet comparable, the refit with its reasons, and the note", () => {
  assert.equal(DRIFT_NOT_YET,
    "Drift: the formal check compares complete quarters after the backtest year, each counted 30 days after it ends, and none is complete yet.");
  const MEANWHILE = `Meanwhile, i${NOTE.slice(1)}`;
  assert.deepEqual(driftLines({ drift: { status: "not_yet_measurable", refit_needed: false, reasons: [], note: NOTE } }), [DRIFT_NOT_YET, MEANWHILE],
    "the formal check cannot run; the latest quarter's note is what can be said meanwhile, not a contradiction");
  assert.doesNotMatch(driftLines({ drift: { status: "not_yet_measurable", note: NOTE } }).join(" "), /cannot be compared/);
  assert.deepEqual(driftLines({ drift: { status: "not_yet_measurable", refit_needed: false, reasons: [], note: null } }), [DRIFT_NOT_YET]);
  assert.deepEqual(
    driftLines({ drift: { status: "refit", refit_needed: true, reasons: ["routine major rate 26.5% in 2026Q1, 2026Q2 against 20.0% over the backtest year"], note: NOTE } }),
    ["The County's record has changed since these rates were measured: routine major rate 26.5% in 2026Q1, 2026Q2 against 20.0% over the backtest year.", NOTE],
  );
  assert.deepEqual(driftLines({ drift: { status: "ok", refit_needed: false, reasons: [], note: null } }), []);
  assert.deepEqual(driftLines(staffMeta), [driftLine(staffMeta)], "an older export without status or note");
  assert.deepEqual(driftLines({}), []);
});

test("band 1 clears C/(B+C) only below the cost ratio low/(1 - low), computed from its interval", () => {
  assert.deepEqual(costLimit(staffMeta), { band: "1", low: 0.33, ratio: 0.49 }, "0.33 / 0.67 = 0.4925");
  assert.equal(costLimitSentence(staffMeta),
    "Band 1's interval starts at 33%, so its low end clears C/(B+C) only when a wrong flag costs less than 0.49 times what a right one is worth (a cost ratio C/B below 0.49).");
  assert.equal(costLimit(bandsMeta).ratio, 0.84, "0.4567 / 0.5433, to two decimals");
  const { low, ratio } = costLimit(bandsMeta);
  for (const r of [ratio - 0.02, ratio + 0.02]) assert.equal(low > r / (1 + r), r < ratio, `the bar at C/B = ${r}`);
  assert.equal(costLimit({}), null);
  assert.equal(costLimit({ card: { bands: [{ band: "1", interval: [null, null] }] } }), null);
  assert.equal(costLimit({ card: { bands: [{ band: "1", interval: [0, 0.1] }] } }), null, "a low end of 0 clears no positive ratio");
  assert.equal(costLimitSentence({}), null);
});

test("a district's backtest figure for the district view, and the bands it covers", () => {
  assert.equal(districtPrecision(staffMeta, 4), "about 29 in 100 (likely 20 to 39)");
  assert.equal(districtPrecision(staffMeta, "2"), "about 41 in 100");
  assert.equal(districtPrecision(staffMeta, 7), null);
  assert.equal(districtPrecision(staffMeta, null), null, "outside the City");
  assert.equal(districtPrecision({}, 4), null);
  assert.equal(auditedBandsName(staffMeta), "Band 1");
  assert.equal(auditedBandsName({}), "Band 1", "band 1 unless the export says otherwise");
  assert.equal(auditedBandsName({ fairness: { bands_used: ["3", "1", "2"] } }), "Bands 1 to 3");
  assert.equal(auditedBandsName({ fairness: { bands_used: ["1", "3"] } }), "Bands 1 and 3");
  assert.equal(auditedGroup(staffMeta), "band 1 places");
  assert.equal(auditedGroup({ fairness: { bands_used: ["1", "2", "3"] } }), "places in bands 1 to 3");
});

test("outside the City, the band line says when recent major violations alone pick out a group with the same rate", () => {
  const outside = (vs) => ({ ...bandsMeta, card: { ...bandsMeta.card, base_rate: 0.2,
    outside: { base_rate: 0.17, bands: [{ band: "1", rate: 0.33, interval: [0.29, 0.37],
      ...(vs === undefined ? {} : { baseline_rate: 0.31, baseline_interval: [0.27, 0.35], vs_baseline: vs }) }] } } });
  assert.ok(bandSummary(outside([-2.5, 3.1]), "1", { outside: true }).endsWith(`had none. ${SAME_AS_PERSISTENCE}`), "the outside interval spans zero");
  assert.ok(!bandSummary(outside([0.5, 6]), "1", { outside: true }).includes(SAME_AS_PERSISTENCE), "above zero: not the same rate");
  assert.ok(!bandSummary(outside(null), "1", { outside: true }).includes(SAME_AS_PERSISTENCE), "no interval, no claim");
  assert.ok(!bandSummary(outside(undefined), "1", { outside: true }).includes(SAME_AS_PERSISTENCE), "an older export's outside band has no baseline");
  // and the comparison under the band is the outside band's own
  assert.match(persistenceSentence(outside([-2.5, 3.1]), "1", { outside: true }),
    /^Sorting the same restaurants outside the City by their recent major violations, .* with a similar rate \(about 31 in 100\)\./);
  assert.equal(persistenceSentence(outside(undefined), "1", { outside: true }), null);
  assert.match(persistenceSentence(staffMeta, "1", { outside: false }), /^Sorting the same restaurants by their recent major violations/);
});

test("the drift check's dates: the first quarter after the backtest year, counted 30 days after it ends", () => {
  assert.equal(driftNotYet({ catch_run: { label_window: "2025-09-01 to 2026-08-31" } }),
    "Drift: the formal check compares complete quarters after the backtest year, each counted 30 days after it ends; " +
      "the first is October to December 2026, counted from January 30, 2027.");
  assert.match(driftNotYet({ catch_run: { label_window: "2025-10-01 to 2026-09-30" } }), /the first is October to December 2026, counted from January 30, 2027\.$/,
    "a year ending on a quarter's last day");
  assert.match(driftNotYet({ catch_run: { label_window: "2025-12-01 to 2026-11-30" } }), /the first is January to March 2027, counted from April 30, 2027\.$/);
  assert.equal(driftNotYet({}), DRIFT_NOT_YET);
  assert.equal(driftNotYet({ catch_run: { label_window: "soon" } }), DRIFT_NOT_YET);
  const lines = driftLines({ catch_run: { label_window: "2025-09-01 to 2026-08-31" }, drift: { status: "not_yet_measurable", note: NOTE } });
  assert.match(lines[0], /January 30, 2027\.$/);
  assert.match(lines[1], /^Meanwhile, in the latest quarter/);
});

// The shape a real export's curves have (export_site.risk_curve): whole-point groups of at least 200
// labelled places, an isotonic step over them, and finer bins; the closure curve is one group.
const rates = (spec, top) => {
  const out = [];
  for (let j = 0; j <= top; j += 1) out.push(spec.find(([lo, hi]) => j >= lo && j <= hi)?.[2] ?? spec[0][2]);
  return out;
};
const plainSpec = [[0, 1, 0.0704, 0.0424, 0.0875], [2, 2, 0.1256], [3, 3, 0.158], [4, 5, 0.2107], [6, 6, 0.3037], [7, 7, 0.3194], [8, 16, 0.4044]];
const curveMeta = {
  mode: "bands",
  catch_run: { as_of: "2025-09-01" },
  card: {
    curve: {
      model: "isotonic (monotone) rate by points at the backtest origin, point values pooled into groups of at least 200 places; 95% interval by address-cluster bootstrap",
      groups: [[0, 0], [1, 1], [2, 2], [3, 3], [4, 4], [5, 5], [6, 6], [7, 7], [8, 16]],
      rate: rates(plainSpec, 16),
      low: rates(plainSpec.map(([lo, hi, r]) => [lo, hi, Math.round((r - 0.04) * 1e4) / 1e4]), 16),
      high: rates(plainSpec.map(([lo, hi, r]) => [lo, hi, Math.round((r + 0.04) * 1e4) / 1e4]), 16),
      bins: [
        { min_points: 0, max_points: 0, labelled: 255, positives: 18, rate: 0.0706 },
        { min_points: 1, max_points: 1, labelled: 370, positives: 26, rate: 0.0703 },
        { min_points: 2, max_points: 2, labelled: 430, positives: 54, rate: 0.1256 },
        { min_points: 3, max_points: 3, labelled: 405, positives: 64, rate: 0.158 },
        { min_points: 4, max_points: 4, labelled: 368, positives: 78, rate: 0.212 },
        { min_points: 5, max_points: 5, labelled: 344, positives: 72, rate: 0.2093 },
        { min_points: 6, max_points: 6, labelled: 270, positives: 82, rate: 0.3037 },
        { min_points: 7, max_points: 16, labelled: 582, positives: 217, rate: 0.3729 },
      ],
      labelled: 3024, positives: 611,
    },
    curve_closure: {
      groups: [[7, 25]],
      rate: Array(26).fill(0.316), low: Array(26).fill(0.263), high: Array(26).fill(0.3723),
      bins: [
        { min_points: 7, max_points: 10, labelled: 22, positives: 3, rate: 0.1364 },
        { min_points: 11, max_points: 18, labelled: 204, positives: 67, rate: 0.3284 },
        { min_points: 19, max_points: 25, labelled: 42, positives: 21, rate: 0.5 },
      ],
      labelled: 268, positives: 91,
    },
  },
};

test("each fitted group is one row, with the rate every place in it is given; counts only where the bins allow", () => {
  const rows = curveGroupRows(curveMeta.card.curve);
  assert.deepEqual(rows.map((r) => [r.lo, r.hi]), curveMeta.card.curve.groups);
  assert.deepEqual(rows[0], { lo: 0, hi: 0, labelled: 255, positives: 18, rate: 0.0704, low: 0.0304, high: 0.1104 },
    "the rate given, pooled with the group above by the monotone step, not the group's own 7.06%");
  assert.equal(rows[1].rate, rows[0].rate, "0 and 1 points read the same rate");
  assert.deepEqual([rows[7].labelled, rows[8].labelled], [null, null], "the 7 to 16 bin runs across the groups' edge");
  assert.deepEqual(curveGroupRows(curveMeta.card.curve_closure), [{ lo: 7, hi: 25, labelled: 268, positives: 91, rate: 0.316, low: 0.263, high: 0.3723 }]);
  const counted = { ...curveMeta.card.curve, group_counts: [{ min_points: 7, max_points: 7, labelled: 230, positives: 70 }] };
  assert.deepEqual([curveGroupRows(counted)[7].labelled, curveGroupRows(counted)[7].positives], [230, 70], "the export's own per-group counts first");
  assert.equal(curveGroupRows({ rate: [0.1] }), null, "an older export's curve has no groups");
  assert.equal(curveGroups({ groups: [[3, 1]] }), null);
});

test("every About row's rate is the rate the estimate gives each place in its points", () => {
  for (const [curve, group] of [[curveMeta.card.curve, "scores"], [curveMeta.card.curve_closure, "closure"]]) {
    for (const row of curveGroupRows(curve)) {
      for (let pts = row.lo; pts <= row.hi; pts += 1) {
        const s = estimateSentence(curveMeta, pts, { estimate: { rate: curve.rate[pts], low: curve.low[pts], high: curve.high[pts], group } });
        assert.match(s, new RegExp(`with ${pointsSpan(row.lo, row.hi)}${group === "closure" ? ` ${CLOSURE_GROUP}` : ""}: about ${Math.round(row.rate * 100)} in 100 `),
          `${group} ${pts} points`);
      }
    }
  }
});

test("the estimate names the group of points it is read from, not the place's exact points", () => {
  const closure = estimateSentence(curveMeta, 23, { estimate: { rate: 0.316, low: 0.263, high: 0.3723, group: "closure" } });
  assert.match(closure, /^Scored restaurants with 7 to 25 points whose last two years include a routine inspection that ended in a closure: about 32 in 100 /);
  assert.doesNotMatch(closure, /about 23 points/);
  assert.match(estimateSentence(curveMeta, 12, { estimate: { rate: 0.4044, low: 0.3644, high: 0.4444 } }), /^Scored restaurants with 8 to 16 points: about 40 in 100 /);
  assert.match(estimateSentence(curveMeta, 7, { estimate: { rate: 0.3194, low: 0.28, high: 0.36, group: "scores" } }), /^Scored restaurants with 7 points: about 32 in 100 /,
    "a group of one value keeps its value");
  assert.match(estimateSentence(curveMeta, 1, { estimate: { rate: 0.0704, group: "scores" } }), /^Scored restaurants with 1 point: /);
  assert.match(estimateSentence(curveMeta, 20, { estimate: { rate: 0.4044, group: "scores" } }),
    /^Scored restaurants with 8 to 16 points \(the group this place's 20 points are read from\): about 40 in 100 /, "past the backtest's largest");
  assert.match(estimateSentence(curveMeta, 12), /^Scored restaurants with 8 to 16 points: about 40 in 100 /, "without a place estimate, read from the curve");
  assert.match(estimateSentence(curveMeta, 9, { estimate: { rate: 0.4, min_points: 8, max_points: 16 } }), /^Scored restaurants with 8 to 16 points: /, "the place's own range first");
  assert.match(estimateSentence(staffMeta, 9), /^Scored restaurants with about 9 points: /, "an older export's curve without groups");
});

test("where a group's finer counts run from low to high, and which curve an estimate reads", () => {
  assert.deepEqual(curveGroupSpread(curveMeta.card.curve), [], "no group of the no-closure curve holds two whole bins that differ");
  const [s] = curveGroupSpread(curveMeta.card.curve_closure);
  assert.deepEqual([s.lo, s.hi, s.min.min_points, s.min.max_points, s.max.min_points, s.max.max_points], [7, 25, 7, 10, 19, 25]);
  assert.equal(pointsSpan(7, 10), "7 to 10 points");
  assert.equal(pointsSpan(1, 1), "1 point");
  assert.deepEqual(curveGroupFor(curveMeta.card.curve, 12), { lo: 8, hi: 16, where: "in" });
  assert.deepEqual(curveGroupFor(curveMeta.card.curve_closure, 3), { lo: 7, hi: 25, where: "below" });
  assert.deepEqual(curveGroupFor({ groups: [[0, 2], [5, 9]] }, 3), { lo: 0, hi: 2, where: "between" }, "the group below, as the fit reads it");
  assert.equal(curveGroupFor({ groups: [[0, 2]] }, null), null);
  assert.equal(curveFor(curveMeta, { group: "closure" }), curveMeta.card.curve_closure);
  assert.equal(curveFor(curveMeta, { group: "scores" }), curveMeta.card.curve);
  assert.equal(curveFor({ card: { curve: 1, outside: { curve: 2 } } }, { outside: true }), 2);
});
