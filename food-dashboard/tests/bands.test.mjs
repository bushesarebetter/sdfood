import { test } from "node:test";
import assert from "node:assert/strict";
import {
  bandDefs, bandShare, bandPoints, bandSummary, bandRatePhrase, bandInterval, rateRatio, ruleSentence, backtestList, stabilitySentence,
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
  assert.match(ruleSentence({}), /published rule/);
});

test("a band's result is its rate beside the rate below the bands, and their ratio", () => {
  assert.equal(rateRatio(bandsMeta, "1"), 3.4);
  assert.equal(
    bandSummary(bandsMeta, "1"),
    "In the backtest, band 1 places had a major violation at their next routine inspection at 3.4 times the rate of scored places below the bands (55% vs 16%).",
  );
  const noRest = { card: { bands: bandsMeta.card.bands } };
  assert.equal(bandSummary(noRest, "2"), "In the backtest, 33% of band 2 places had a major violation at their next routine inspection.");
  assert.equal(bandSummary({}, "1"), "Band 1 has no backtest rate in this export.");
  assert.equal(bandRatePhrase(bandsMeta, "3"), "30% had a major");
  assert.equal(bandInterval(bandsMeta, "1"), "95% interval 46% to 63%");
  assert.equal(backtestList(bandsMeta), "the list drawn up the same way on September 1, 2025");
  assert.equal(stabilitySentence({ band: "2", band_stability: 0.67 }), "Stayed in band 2 in 67% of refits of the rule on resampled data.");
  assert.equal(stabilitySentence({ band: "2" }), null);
});
