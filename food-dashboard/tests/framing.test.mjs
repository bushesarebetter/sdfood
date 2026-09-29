import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { siteMode, kindsPhrase, headline, subhead, gradeContextSentence, siteDescription, legendNote, placeLines } from "../src/lib/framing.js";
import { recordFacts } from "../src/lib/recordFacts.js";
import { citation, recordText } from "../src/lib/ask.js";
import { facilitiesToCsv, csvColumns } from "../src/lib/format.js";
import { markFor } from "../src/lib/marks.js";
import { bandsMeta, staffMeta } from "./fixtures/bandsMeta.mjs";

const fixture = join(dirname(fileURLToPath(import.meta.url)), "fixtures", "record");
const recordMeta = JSON.parse(readFileSync(join(fixture, "meta.json"), "utf8"));
const recordIndex = JSON.parse(readFileSync(join(fixture, "facilities.geojson"), "utf8"));
const recordPlaces = readdirSync(join(fixture, "place")).map((n) => JSON.parse(readFileSync(join(fixture, "place", n), "utf8")));

// Anything from a model, in any wording the site uses for one.
const MODEL_WORDS = /\bband|\bpoints?\b|\brule\b|backtest|\bmodel|predict|score card|worksheet|\bcard\b|refit|\brank|percentile/i;

test("the mode is record unless meta says bands", () => {
  assert.equal(siteMode(recordMeta), "record");
  assert.equal(siteMode(bandsMeta), "bands");
  assert.equal(siteMode(null), "record");
  assert.equal(siteMode({ mode: "ranked" }), "record", "an unknown mode shows the record only");
});

test("record mode: the headline, the copy and every place helper say nothing model-related", () => {
  const n = recordIndex.features.length;
  assert.equal(headline(recordMeta, recordIndex.features), `The County's inspection record for ${n} San Diego restaurants and limited-preparation food places`);
  const texts = [headline(recordMeta, recordIndex.features), subhead(recordMeta), siteDescription(recordMeta), legendNote(recordMeta), gradeContextSentence(recordMeta)];
  for (const place of recordPlaces) {
    texts.push(...placeLines(place, recordMeta));
    for (const f of recordFacts(place)) texts.push(f.title, ...f.county, f.reading ?? "");
    texts.push(citation({ place, url: "u", meta: recordMeta }));
    texts.push(recordText({ place, url: "u", meta: recordMeta }));
    assert.equal(markFor(place).label, null, "every dot alike");
  }
  texts.push(csvColumns().join(","));
  texts.push(facilitiesToCsv(recordIndex.features, { meta: recordMeta }).split("\n")[0]);
  for (const t of texts) assert.doesNotMatch(t, MODEL_WORDS, t);
});

test("the kinds are derived from the data, most common first", () => {
  const f = (t) => ({ properties: { facility_type: t } });
  assert.equal(kindsPhrase([f("restaurant"), f("market"), f("restaurant")]), "restaurants and markets");
  assert.equal(kindsPhrase([f("restaurant"), f("market"), f("limited"), f("market")]), "markets, limited-preparation food places and restaurants");
  assert.equal(kindsPhrase([]), "restaurants and markets");
});

test("bands mode: the headline is about the rule, never a prediction about a place", () => {
  const features = [
    { properties: { facility_type: "restaurant", band: "1", points: 21 } },
    { properties: { facility_type: "restaurant", band: "3", points: 12 } },
    { properties: { facility_type: "restaurant", on_hold: true } },
    { properties: { facility_type: "market" } },
  ];
  assert.equal(headline(bandsMeta, features), "The 2 San Diego restaurants whose County record scores highest on the students' point rule");
  assert.match(subhead(bandsMeta), /^Places are ordered by how far .* Band 1 is about the 2\.5% of scored places with the most points, band 2 about the next 5% by points, band 3 about the next 10% by points\./);
  assert.match(legendNote(bandsMeta), /^Darker = more points on the students' point rule\. In the backtest, about 55 in 100 band 1 places had a major violation .*; about 45 in 100 had none\./);
});

test("the place lines give the grade, then the band, its points and its backtest rate", () => {
  const base = { grade: { grade: "A", score: 93, date: "2026-06-01", replaced: null } };
  const lines = placeLines({ ...base, band: "1", points: 21 }, bandsMeta);
  assert.deepEqual(lines, [
    "Latest County grade on record: A (93), June 1, 2026.",
    "Band 1 on the students' point rule: 21 points (band 1 is 20 points or more).",
    "In the backtest, about 55 in 100 band 1 places had a major violation at their next routine inspection (likely 46 to 63), against 16 in 100 of scored places below the bands; about 45 in 100 had none. Sorting by recent major violations alone picks out a group with the same rate.",
    "A band describes what happened to a group of places; it is not a finding that this place has, or will have, a violation.",
  ]);
  assert.equal(placeLines({ ...base, points: 9 }, bandsMeta)[1], "In no band: 9 points on the students' point rule (band 3 starts at 12 points).");
  assert.equal(
    placeLines({ ...base }, bandsMeta)[1],
    "Not scored: the students' point rule gives this place no points. It scores restaurants with a scored routine inspection in the year before the list date.",
    "a place without points is never implied to have been scored",
  );
  const held = placeLines({ ...base, on_hold: true, band: "1", points: 21 }, bandsMeta);
  assert.match(held[1], /^Under review: this place's band and points are withheld/);
  assert.doesNotMatch(held.join(" "), /Band 1|21 points/);
  const expired = placeLines({ ...base, band: "1", points: 21 }, { ...bandsMeta, inspections_through: "2026-09-19" }, { expired: true });
  assert.equal(expired.length, 2);
  assert.match(expired[1], /^This export is out of date/);
});

test("the grade-context figure always carries the County's rule", () => {
  assert.equal(
    gradeContextSentence(bandsMeta),
    "Most routine inspections that find a major violation still end with an A: 94% of them did. The County requires each major violation to be corrected immediately, or a suitable alternative put in place until it is; otherwise the affected area or process can be closed.",
  );
  assert.match(gradeContextSentence({}), /corrected immediately, or a suitable alternative put in place/);
  assert.match(siteDescription(bandsMeta), /Independent student project, not affiliated with or endorsed by the County of San Diego\.$/);
});

test("the CSV has band and points columns only in bands mode, and always the list dates", () => {
  assert.ok(!csvColumns().includes("points") && !csvColumns().includes("band"));
  assert.ok(csvColumns({ mode: "bands" }).includes("points"));
  for (const c of ["list_date", "inspections_through", "expires"]) assert.ok(csvColumns().includes(c));
});

test("with an estimate, the place lines lead with it; a City place's band line carries its district", () => {
  const p = { grade: { grade: "A", score: 93, date: "2026-06-01", replaced: null }, band: "1", points: 9, council_district: 4 };
  const lines = placeLines(p, staffMeta, { withGrade: false });
  assert.match(lines[0], /^Scored restaurants with about 9 points: about 39 in 100 .* in the backtest of the list drawn up on September 1, 2025/, "the curve is the confirmation origin's");
  assert.match(lines[0], /The County's record has changed since these rates were measured\.$/, "the export's drift check asks for a refit");
  assert.equal(lines[1], "Band 1 on the students' point rule: 9 points (band 1 is 8 points or more).");
  assert.match(lines[2], /^In the backtest, about 37 in 100 band 1 places .* against 21 in 100 of all scored restaurants; about 63 in 100 had none\. Sorting by recent major violations alone picks out a group with the same rate\. In council district 4, about 29 in 100 band 1 places had one \(likely 20 to 39\)\.$/);
  assert.equal(lines.at(-1), "A band describes what happened to a group of places; it is not a finding that this place has, or will have, a violation.");
  const unbanded = placeLines({ points: 3, council_district: 4 }, staffMeta, { withGrade: false });
  assert.match(unbanded[0], /^Scored restaurants with about 3 points/);
  assert.equal(unbanded[1], "In no band: 3 points on the students' point rule (band 1 starts at 8 points).");
});

test("a place read from the closure curve says so under its name, and the export's drift note follows the estimate", () => {
  const note = "In the latest quarter (2026 Q3, through September 19) 20.5% of routine inspections found a major violation, against 17.5% over the backtest year, so the rates here may be low.";
  const meta = { ...staffMeta, drift: { status: "not_yet_measurable", refit_needed: false, reasons: [], note } };
  const p = { band: "1", points: 30, council_district: 4 };
  const lines = placeLines(p, meta, { withGrade: false, estimate: { rate: 0.28, low: 0.22, high: 0.34, group: "closure" } });
  assert.equal(lines[0],
    "Scored restaurants with about 30 points whose last two years include a routine inspection that ended in a closure: about 28 in 100 had a major violation at their next routine inspection in the backtest of the list drawn up on September 1, 2025 (likely 22 to 34). " +
      `The likely range reflects sampling only, not changes since then. ${note}`);
  assert.equal(lines[1], "Band 1 on the students' point rule: 30 points (band 1 is 8 points or more).");
  const scores = placeLines({ points: 3, council_district: 4 }, meta, { withGrade: false, estimate: { rate: 0.12, low: 0.1, high: 0.14, group: "scores" } });
  assert.match(scores[0], /^Scored restaurants with about 3 points: about 12 in 100 .* may be low\.$/);
});
