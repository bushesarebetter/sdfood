import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { gradeView } from "../src/lib/grades.js";
import { copyFor } from "../src/lib/copy.js";
import { FIELD_TYPES, KEPT_NOTE, MAX_ITEMS, SAME_CLOSURE } from "../src/lib/inspections.js";
import { CLOSURE_GROUP, curveGroupFor, estimateSentence, isOutside } from "../src/lib/bands.js";

/**
 * The place views (the page, the phone sheet, the items by theme, the record's sentences and its
 * list of records) and the About page rendered to HTML: a place whose last closure has no reopening
 * on record leads with it in every view, the items by theme are counted before the export's
 * MAX_ITEMS cut and say so when they cannot be, a County field visit is named by the County's own
 * types, the phone sheet says where a question about the place goes on the staff site, the record's
 * count of "Ordered Closed" records is the list's and the rule for a further order is stated when
 * it joins a closure, the list of records says which it leaves out, and every place's estimate, in
 * the City or outside it, names a group and rate a row of the About page shows. Bundled with esbuild
 * and rendered with react-dom/server, as in placeTable.test.mjs; where node_modules is not installed
 * the rendered checks are skipped and the checks read from the source still run.
 */
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (name) => readFileSync(join(root, "src", name), "utf8");

const fixture = JSON.parse(readFileSync(join(root, "tests", "fixtures", "record", "place", "SAMPLE-FFPP-00005.json"), "utf8"));

// ---------------------------------------------------------------------------------------------------
// From the source.

test("every list view writes a grade it does not lead with in the grade's own words, never lowercased", () => {
  for (const name of ["PlacePanel.jsx", "NearPanel.jsx", "MapView.jsx", "SearchBox.jsx", "MobileShell.jsx", "PlaceTable.jsx"]) {
    assert.doesNotMatch(read(name), /\.text\.toLowerCase\(\)/, `${name}: "Not graded by the County" keeps its capital, and a closure its month`);
  }
  assert.equal(gradeView(null).withDate, "not graded by the County");
  assert.equal(gradeView(fixture.grade).withDate, "closed May 20, 2026, no reopening on record");
});

test("the page and the panel lead with an open closure where they would show the grade", () => {
  assert.match(read("PlaceCard.jsx"), /\(g\.graded \|\| g\.closedOpen\) && \(/);
  assert.match(read("PlacePanel.jsx"), /g\.graded \? `Grade \$\{g\.short\}` : g\.text/);
  for (const name of ["PlaceCard.jsx", "PlacePanel.jsx"]) assert.match(read(name), /<ThemeList place=\{place\}/, `${name} gives ThemeList the place`);
});

test("the no-facts line and the chart's note name the County's field-visit types, and the phone sheet says the same", () => {
  assert.equal(copyFor(false).detailNoFacts,
    `No closure, major violation, B or C grade, repeat reinspection, ${FIELD_TYPES} visit in the 12 months before the last visit.`);
  assert.equal(FIELD_TYPES, "Site Investigation or Environmental");
  assert.match(copyFor(true).detailHistoryNote, /complaint or other field visits \(our reading\) and status verifications drawn lighter/);
  assert.match(read("MobileSheet.jsx"), /empty=\{copyFor\(false\)\.detailNoFacts\}/);
  for (const name of ["MobileSheet.jsx", "PlaceParts.jsx"]) assert.doesNotMatch(read(name), /complaint visit/, name);
});

// ---------------------------------------------------------------------------------------------------
// Rendered.

let ui = null;
let why = "";
try {
  const { build } = await import("esbuild");
  const dir = mkdtempSync(join(tmpdir(), "sdfood-place-"));
  const out = join(dir, "ui.mjs");
  await build({
    stdin: {
      contents: [
        'export { ThemeList } from "./src/PlaceParts.jsx";',
        'export { default as MobileSheet } from "./src/MobileSheet.jsx";',
        'export { default as PlaceCard } from "./src/PlaceCard.jsx";',
        'export { default as RecordSummary } from "./src/RecordSummary.jsx";',
        'export { default as VisitList } from "./src/VisitList.jsx";',
        'export { default as AboutModal } from "./src/AboutModal.jsx";',
        'export { MetaProvider } from "./src/useMeta.jsx";',
        'export { AdvancedProvider } from "./src/useAdvanced.jsx";',
        'export { renderToStaticMarkup } from "react-dom/server";',
        'export { createElement } from "react";',
      ].join("\n"),
      resolveDir: root,
      loader: "js",
    },
    bundle: true,
    platform: "node",
    format: "esm",
    jsx: "automatic",
    outfile: out,
    logLevel: "error",
    define: { "process.env.NODE_ENV": '"production"' },
    banner: { js: 'import { createRequire as __req } from "node:module"; const require = __req(import.meta.url);' },
  });
  ui = await import(pathToFileURL(out).href);
  process.on("exit", () => rmSync(dir, { recursive: true, force: true }));
} catch (err) {
  why = `the components could not be bundled here (${err?.code ?? err?.message ?? err}); run npm ci first`;
}
const rendered = (name, fn) => test(name, { skip: ui ? false : why }, fn);

const recordMeta = { mode: "record", generated: "2026-09-28", inspections_through: "2026-09-26", expires: "2099-10-12" };
const staffMeta = { ...recordMeta, audience: "staff", contact: { name: "A Student", email: "student@example.org" } };
const html = (el, meta = recordMeta) => ui.renderToStaticMarkup(ui.createElement(ui.MetaProvider, { meta }, ui.createElement(ui.AdvancedProvider, null, el)));
const decode = (s) => s.replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const text = (s) => decode(s.replace(/<[^>]+>/g, " ")).replace(/\s+/g, " ").trim();
const feature = (props) => ({ type: "Feature", geometry: { type: "Point", coordinates: [-117.15, 32.72] }, properties: props });

rendered("the items by theme are the export's whole counts, with the County's field-visit types, and no cut line", () => {
  const out = text(html(ui.createElement(ui.ThemeList, { place: fixture })));
  // theme_counts: vermin 2 major, water 2 minor, condition 1 minor with 1 at a field visit.
  assert.match(out, /Pests 2 items, 2 major/);
  assert.match(out, /Hot and cold water 2 items/);
  assert.match(out, new RegExp(`1 found at a ${FIELD_TYPES} visit`));
  assert.doesNotMatch(out, /complaint visit|Showing/);
});

rendered("a list the export cut, with no whole counts, says so under the themes", () => {
  const item = (i) => ({ date: `2026-0${1 + (i % 8)}-1${i % 10}`, item: "21", theme: "water", severity: "minor", visit: "routine", text: "Hot & cold water available" });
  const total = MAX_ITEMS + 20;
  const cut = { violations: Array.from({ length: MAX_ITEMS }, (_, i) => item(i)), violations_total: total };
  const out = text(html(ui.createElement(ui.ThemeList, { place: cut })));
  assert.match(out, new RegExp(`Showing ${MAX_ITEMS} of ${total} items, majors first`));
  const whole = text(html(ui.createElement(ui.ThemeList, { place: { ...cut, theme_counts: { water: { major: 0, minor: total, grp: 0, complaint: 0, latest: "2026-08-19" } } } })));
  assert.match(whole, new RegExp(`${total} items`));
  assert.doesNotMatch(whole, /Showing/, "whole counts need no line");
});

rendered("the place page's tag leads with a closure no reopening follows, in the closure's colour", () => {
  const p = { ...fixture, band: null, points: null };
  const out = html(ui.createElement(ui.PlaceCard, { placeKey: p.facility_id, facilities: { type: "FeatureCollection", features: [feature(p)] }, onNavigate: () => {} }));
  const g = gradeView(p.grade);
  const tag = /<p class="inline-block border[^"]*" style="([^"]*)">([^<]*)<\/p>/.exec(out);
  assert.ok(tag, "the tag is there");
  assert.equal(decode(tag[2]), "Closed May 2026, no reopening on record");
  assert.match(tag[1], new RegExp(`color:${g.textColor}`, "i"));
  assert.doesNotMatch(text(out), /Grade A 92/, "the older A is not the lead");
});

rendered("the phone sheet says where a question about a place goes on the staff site, and nowhere else", () => {
  const props = { feature: feature({ ...fixture, band: null, points: null }), onClose: () => {}, onNavigate: () => {} };
  const staff = text(html(ui.createElement(ui.MobileSheet, props), staffMeta));
  assert.match(staff, /What to do with a question about this place/);
  assert.match(staff, /This site is wrong: A Student \(student@example\.org\)/);
  assert.match(staff, /Closed May 2026, no reopening on record/, "the sheet's tag leads with the closure too");
  const pub = text(html(ui.createElement(ui.MobileSheet, props)));
  assert.doesNotMatch(pub, /What to do with a question about this place/);
});

// ---------------------------------------------------------------------------------------------------
// The record's sentences beside its list of records.

const rec = (date, extra = {}) => ({ date, status: "Complete", type: "routine", county_type: "Routine", score: null, grade: null, major: 0, minor: 0, grp: 0,
  notes: [], closed: false, closure: null, reopened: null, ...extra });
const order = (date, extra = {}) => rec(date, { status: "Ordered Closed", major: 1, ...extra });
/** The "Ordered Closed" rows of the rendered list of records. */
const orderRows = (html) => [...html.matchAll(/<tr[^>]*>(.*?)<\/tr>/g)]
  .map((m) => [...m[1].matchAll(/<td[^>]*>(.*?)<\/td>/g)].map((c) => text(c[1])))
  .filter((cells) => cells.length && cells[2].startsWith("Ordered Closed")).length;
const summary = (inspections) => text(html(ui.createElement(ui.RecordSummary, { place: { inspections, violations: [] }, meta: recordMeta })));

rendered("the record's count of Ordered Closed records is the list's, and a further order that joined a closure gives its rule", () => {
  // 2 closures from 3 orders: the second order came 6 days after the first, before the reopening.
  const joined = [
    rec("2025-06-02", { score: 94, grade: "A" }),
    order("2025-09-04", { closed: true, closure: "health", reopened: true, reopened_on: "2025-09-12" }),
    order("2025-09-10", { type: "reinspection", county_type: "Re-inspection" }),
    rec("2025-09-12", { status: "Approved to Reopen", type: "reinspection", county_type: "Re-inspection" }),
    order("2026-02-04", { major: 2, closed: true, closure: "health", reopened: false, reopened_on: null }),
  ];
  const s = summary(joined);
  assert.match(s, /; 3 “Ordered Closed” records and 2 closures in our reading \(a further order within 30 days of the last, with no reopening or graded visit between, is part of the same closure\)/);
  assert.ok(s.includes(SAME_CLOSURE));
  assert.equal(orderRows(html(ui.createElement(ui.VisitList, { inspections: joined, open: true }))), 3, "the list shows the 3 the sentence counts");
  // Two orders more than 30 days apart are two closures: both numbers, and no rule to give.
  const apart = [
    order("2025-02-01", { closed: true, closure: "health", reopened: false, reopened_on: null }),
    order("2025-04-01", { closed: true, closure: "health", reopened: false, reopened_on: null }),
  ];
  const a = summary(apart);
  assert.match(a, /; 2 “Ordered Closed” records and 2 closures in our reading\./);
  assert.doesNotMatch(a, /further order/);
  assert.equal(orderRows(html(ui.createElement(ui.VisitList, { inspections: apart, open: true }))), 2);
  // A "Self Closed" closure beside an order that joined another: as many orders as closures, and the rule still given.
  const self = [
    rec("2025-03-03", { status: "Self Closed", major: 1, closed: true, closure: "health", reopened: true, reopened_on: "2025-03-05" }),
    rec("2025-03-05", { status: "Approved to Reopen", type: "followup", score: 95, grade: "A" }),
    order("2025-08-01", { closed: true, closure: "health", reopened: true, reopened_on: "2025-08-20" }),
    order("2025-08-10", { type: "reinspection", county_type: "Re-inspection" }),
    rec("2025-08-20", { status: "Approved to Reopen", type: "reinspection", county_type: "Re-inspection" }),
  ];
  const t = summary(self);
  assert.match(t, /; 2 “Ordered Closed” records and 2 closures in our reading \(a further order within 30 days/);
  assert.match(t, /; 1 of the closures “Self Closed”/);
  assert.equal(orderRows(html(ui.createElement(ui.VisitList, { inspections: self, open: true }))), 2);
});

rendered("the list of records is headed by the records we keep and says which it leaves out", () => {
  const out = html(ui.createElement(ui.VisitList, { inspections: [rec("2026-01-02", { score: 96, grade: "A" })] }));
  assert.match(text(out), /^The County records we keep \(1\)/);
  assert.ok(text(out).includes(KEPT_NOTE));
  assert.match(KEPT_NOTE, /“No Access” and “Incomplete” records/);
  assert.doesNotMatch(out, /Every County record/i);
  for (const advanced of [false, true]) assert.doesNotMatch(`${copyFor(advanced).detailVisits} ${copyFor(advanced).detailHistoryNote}`, /\bevery\b/i);
});

// ---------------------------------------------------------------------------------------------------
// The About page: every place's estimate is a row it shows, in the City and outside it.

const flat = (groups, top) => {
  const at = (j) => groups.find(([lo, hi]) => j >= lo && j <= hi) ?? groups.filter(([, hi]) => hi < j).at(-1) ?? groups[0];
  return { rate: Array.from({ length: top + 1 }, (_, j) => at(j)[2]), low: Array.from({ length: top + 1 }, (_, j) => at(j)[2] - 0.03),
    high: Array.from({ length: top + 1 }, (_, j) => at(j)[2] + 0.04) };
};
const fittedCurve = (groups, top, counts) => ({
  model: "isotonic (monotone) rate by points at the backtest origin, point values pooled into groups of at least 200 places",
  groups: groups.map(([lo, hi]) => [lo, hi]), ...flat(groups, top),
  group_counts: groups.map(([lo, hi], k) => ({ min_points: lo, max_points: hi, labelled: counts[k], positives: Math.round(counts[k] * groups[k][2]) })),
  labelled: counts.reduce((x, y) => x + y, 0), positives: 1,
});
const aboutMeta = {
  mode: "bands", generated: "2026-09-28", inspections_through: "2026-09-26", expires: "2099-10-12", catch_run: { as_of: "2025-09-01" },
  card: {
    rule: "A rule.", bands: [],
    curve: fittedCurve([[0, 1, 0.07], [2, 3, 0.14], [4, 6, 0.21], [7, 16, 0.4]], 16, [625, 835, 982, 582]),
    curve_closure: fittedCurve([[7, 25, 0.32]], 25, [288]),
    outside: {
      bands_shown: false, base_rate: 0.17,
      curve: fittedCurve([[0, 2, 0.05], [3, 4, 0.12], [5, 16, 0.29]], 16, [900, 700, 1513]),
      curve_closure: fittedCurve([[8, 30, 0.26]], 30, [202]),
    },
  },
};

/** The rows of the About page's tables in a section, by the curve label above them: { label: [[points, ..., rate]] }. */
function aboutRows(page, heading) {
  const section = page.split("<section").find((sec) => sec.includes(`>${heading}</h3>`)) ?? "";
  const out = {};
  let label = "";
  for (const m of section.matchAll(/<tr[^>]*>(.*?)<\/tr>/g)) {
    const cells = [...m[1].matchAll(/<td[^>]*>(.*?)<\/td>/g)].map((c) => text(c[1]));
    if (!cells.length) continue;
    if (cells[0].startsWith("Places")) label = cells[0];
    else (out[label] ??= []).push(cells);
  }
  return out;
}

rendered("every place's estimate, in the City and outside it, names a group and rate that a row of the About page shows", () => {
  const page = html(ui.createElement(ui.AboutModal, { onClose: () => {} }), aboutMeta);
  const all = text(page);
  assert.match(all, /Each group of places in the City, and the rate every place in it is given \(places outside the City are read from the groups measured outside it, under Outside the City\):/);
  assert.match(all, /Each group outside the City, and the rate every place in it is given:/);
  assert.match(all, /one for places whose two years include a routine inspection that started a closure for a health hazard \(a County closure order, the operator's own closure with a major cited, or a closure read from a later reopening\), which the rule counts as 70/);
  const tables = { city: aboutRows(page, "What the points say, place by place"), outside: aboutRows(page, "Outside the City") };
  assert.deepEqual(Object.keys(tables.city), ["Places in the City whose two scored years include no health closure", "Places in the City whose two years include a health closure counted as 70"]);
  assert.deepEqual(Object.keys(tables.outside), ["Places outside the City whose two scored years include no health closure", "Places outside the City whose two years include a health closure counted as 70"]);
  let checked = 0;
  for (const council_district of [3, null]) {
    const area = council_district == null ? aboutMeta.card.outside : aboutMeta.card;
    for (const group of ["scores", "closure"]) {
      const curve = group === "closure" ? area.curve_closure : area.curve;
      for (let points = 0; points <= 30; points += 1) {
        const p = { points, council_district };
        const j = Math.min(points, curve.rate.length - 1);
        const g = curveGroupFor(curve, points);
        const s = estimateSentence(aboutMeta, points, { estimate: { rate: curve.rate[j], low: curve.low[j], high: curve.high[j], group, min_points: g.lo, max_points: g.hi }, outside: isOutside(p, aboutMeta) });
        const m = /with (\d+(?: to \d+)?) points?(?: \([^)]*\))?( whose last two years)?[^:]*: about (\d+) in 100/.exec(s);
        assert.ok(m, s);
        assert.equal(Boolean(m[2]), group === "closure" && s.includes(CLOSURE_GROUP));
        const outside = council_district == null;
        const label = `Places ${outside ? "outside" : "in"} the City ${group === "closure" ? "whose two years include a health closure counted as 70" : "whose two scored years include no health closure"}`;
        const rows = tables[outside ? "outside" : "city"][label] ?? [];
        assert.ok(rows.some((r) => r[0] === m[1] && r[3].startsWith(`${m[3]}% `)), `${outside ? "outside" : "City"} ${group} ${points} points: "${s}" is a row under "${label}"`);
        checked += 1;
      }
    }
  }
  assert.equal(checked, 124);
});

rendered("the About page states a pooling floor its own table bears out, for the shipped sample too", () => {
  assert.match(text(html(ui.createElement(ui.AboutModal, { onClose: () => {} }), aboutMeta)), /pooled into groups of at least 200 labelled places/);
  const sample = JSON.parse(readFileSync(join(root, "public", "data", "meta.json"), "utf8"));
  const counts = [sample.card?.curve, sample.card?.curve_closure].flatMap((c) => (c?.group_counts ?? []).map((g) => g.labelled));
  const page = text(html(ui.createElement(ui.AboutModal, { onClose: () => {} }), { ...sample, expires: "2099-10-12" }));
  assert.doesNotMatch(page, /at least 200 labelled places/, "the sample's curves state no floor");
  if (counts.length) assert.match(page, new RegExp(`pooled into groups of at least ${Math.min(...counts)} labelled places`));
});
