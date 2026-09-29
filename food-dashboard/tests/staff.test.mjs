import { test } from "node:test";
import assert from "node:assert/strict";
import { isStaff, contactLine, reviewStatus, reviewGuidance } from "../src/lib/staff.js";

const STATUS = [
  "no publishable rule is within 0.01 AUC of the best model at every validation origin",
  "the rule does not beat persistence on AUC among eligible restaurants ([-0.0107, 0.0187])",
  "no band's interval clears the approved cost ratio: nothing to name",
  "district 4: 2.02x its share of wrongly named places (27 named)",
  "district 9: false-positive rate 1.81x the City's",
  "district 9: the share of wrongly named places could be up to 2.35x even",
  "prospective test: no registered run",
];

test("the staff copy of meta makes the site a staff site; the public sample is not", () => {
  assert.equal(isStaff({ audience: "staff" }), true);
  assert.equal(isStaff({ sample: true }), false);
  assert.equal(contactLine({ contact: { name: "A", email: "a@example.org" } }), "A (a@example.org)");
  assert.equal(contactLine({ contact: "a@example.org" }), null, "a public export's string contact is not a staff contact object");
});

test("every failing check becomes an instruction staff can act on, once", () => {
  const g = reviewGuidance({ review_status: STATUS });
  assert.equal(g.length, 4);
  assert.match(g[0], /do not rank places against each other by points/);
  assert.match(g[1], /No band is strong enough to justify singling out a business/);
  assert.equal(g[2], "A band is wrong more often in Districts 4 and 9 than elsewhere: do not compare districts by how many places are in a band.");
  assert.match(g[3], /not yet been tested on inspections made after it was frozen/);
  assert.deepEqual(reviewGuidance({}), []);
  assert.equal(reviewStatus({ review_status: ["x", 3, ""] }).length, 1);
});
