import { test } from "node:test";
import assert from "node:assert/strict";
import {
  bandDefs, bandShare, bandPoints, bandSummary, bandRatePhrase, bandInterval, rateRatio, ruleSentence, backtestList, stabilitySentence,
  estimateSentence, persistenceSentence, GROUP_NOTE,
} from "../src/lib/bands.js";
import { bandsMeta } from "./fixtures/bandsMeta.mjs";


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

test("a band's result is in natural frequencies, with its likely range, beside a stated comparison", () => {
  assert.equal(rateRatio(bandsMeta, "1"), 3.4);
  assert.equal(
    bandSummary(bandsMeta, "1"),
    "In the backtest, band 1 places had a major violation at their next routine inspection at about 3.4 times the rate of scored places below the bands: about 55 in 100 (likely 46 to 63), against 16 in 100.",
  );
  // with the rate for all scored restaurants, that is the comparison (never only the places left below the bands)
  const withBase = { ...bandsMeta, card: { ...bandsMeta.card, base_rate: 0.2 } };
  assert.equal(rateRatio(withBase, "1"), 2.7);
  assert.match(bandSummary(withBase, "1"), /about 2\.7 times the rate of all scored restaurants: about 55 in 100 \(likely 46 to 63\), against 20 in 100\.$/);
  const noRest = { card: { bands: bandsMeta.card.bands } };
  assert.equal(bandSummary(noRest, "2"), "In the backtest, about 33 in 100 band 2 places had a major violation at their next routine inspection (likely 27 to 39).");
  assert.equal(bandSummary({}, "1"), "Band 1 has no backtest rate in this export.");
  assert.equal(bandRatePhrase(bandsMeta, "3"), "30% had a major");
  assert.equal(bandInterval(bandsMeta, "1"), "95% interval 46% to 63%");
  assert.equal(backtestList(bandsMeta), "the list drawn up the same way on September 1, 2025");
  assert.equal(stabilitySentence({ band: "2", band_stability: 0.67 }), "Stayed in band 2 in 67% of refits of the rule on resampled data.");
  assert.equal(stabilitySentence({ band: "2" }), null);
});


test("a place outside the City is described by the rates measured outside the City", () => {
  const meta = { ...bandsMeta, card: { ...bandsMeta.card, base_rate: 0.2,
    outside: { base_rate: 0.17, bands: [{ band: "1", rate: 0.33, interval: [0.29, 0.37] }],
               curve: { rate: [0.05, 0.1, 0.2], low: [0.04, 0.08, 0.17], high: [0.06, 0.12, 0.24] } } } };
  assert.match(bandSummary(meta, "1", { outside: true }), /band 1 places outside the City .* all scored restaurants outside the City: about 33 in 100 \(likely 29 to 37\), against 17 in 100\.$/);
  assert.equal(estimateSentence(meta, 2, { outside: true }),
    "Scored restaurants outside the City with about 2 points: about 20 in 100 had a major violation at their next routine inspection in the backtest (likely 17 to 24).");
});

test("every scored place gets an estimate from its place file or the curve; the persistence comparison follows the data", () => {
  const meta = { ...bandsMeta, card: { ...bandsMeta.card, curve: { rate: [0.05, 0.3], low: [0.04, 0.25], high: [0.06, 0.35] } } };
  assert.match(estimateSentence(meta, 40), /about 40 points: about 30 in 100 .* \(likely 25 to 35\)\.$/, "read at the largest point on the curve");
  assert.match(estimateSentence(meta, 1, { estimate: { rate: 0.41, low: 0.3, high: 0.5 } }), /about 41 in 100 .* \(likely 30 to 50\)/);
  assert.equal(estimateSentence(meta, null), null);
  assert.equal(estimateSentence({}, 5), null);
  const similar = { card: { bands: [{ band: "1", baseline_rate: 0.37, vs_baseline: [-23, 26] }] } };
  assert.match(persistenceSentence(similar), /similar rate \(about 37 in 100\)\. The points are a transparent summary of that record, not a better predictor\.$/);
  const better = { card: { bands: [{ band: "1", baseline_rate: 0.3, vs_baseline: [4, 30] }] } };
  assert.match(persistenceSentence(better), /whose rate was lower \(about 30 in 100\): band 1 found more/);
  assert.equal(persistenceSentence({}), null);
  assert.match(GROUP_NOTE, /not a finding about any one of them/);
});
