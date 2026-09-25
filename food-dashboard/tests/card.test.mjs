import { test } from "node:test";
import assert from "node:assert/strict";
import { worksheet, rowText } from "../src/lib/card.js";

const meta = {
  card: {
    items: [
      { item: "avg_deficit", label: "Points below 100, average routine score in the last year", weight: 1, unit: "per point below 100", feature: "avg_deficit" },
      { item: "theme_temperature", label: "Food-temperature citations in the last year", weight: 2, unit: "per citation", feature: "theme_temperature" },
    ],
  },
};
const p = {
  points: 15,
  score_card: [
    { item: "avg_deficit", weight: 1, value: 9, points: 9, met: true },
    { item: "theme_temperature", weight: 2, value: 3, points: 6, met: true },
  ],
};

test("each row is value times weight, and the rows add up to the place's points", () => {
  const w = worksheet(p, meta);
  assert.deepEqual(w.rows.map((r) => [r.item, r.value, r.weight, r.points]), [["avg_deficit", 9, 1, 9], ["theme_temperature", 3, 2, 6]]);
  assert.equal(w.total, 15);
  assert.equal(w.consistent, true);
  assert.equal(rowText(w.rows[1], { advanced: true }), "Food-temperature citations in the last year: 3 × 2 = 6 points");
  assert.equal(rowText(w.rows[1]), "Food-temperature citations in the last year: 3 (6 points)");
  assert.equal(rowText({ label: "x", value: 1, weight: 1, points: 1 }), "x: 1 (1 point)");
});

test("a zero row adds nothing; a total that does not add up is flagged; no worksheet gives null", () => {
  const w = worksheet({ points: 10, score_card: [{ item: "avg_deficit", weight: 1, value: 9, points: 9, met: true }, { item: "theme_temperature", weight: 2, value: 0, points: 0, met: false }] }, meta);
  assert.equal(w.met.length, 1);
  assert.equal(w.unmet.length, 1);
  assert.equal(w.consistent, false);
  assert.equal(worksheet({ score_card: [] }, meta), null);
  assert.equal(worksheet(null, meta), null);
  assert.equal(worksheet({ points: 2, score_card: [{ item: "unknown", weight: 2, value: 1 }] }, null).rows[0].label, "unknown");
});
