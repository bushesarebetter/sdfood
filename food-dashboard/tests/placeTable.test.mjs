import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { BAND_TEXT } from "../src/lib/marks.js";
import { GRADE_TEXT } from "../src/lib/grades.js";
import { bandSummary } from "../src/lib/bands.js";
import { ESCALATION_CAVEAT, FLAG_LABELS, FLAG_SHORT, THEMES } from "../src/lib/inspections.js";
import { PUBLIC_RECORD_NOTE, USE_NOTE } from "../src/lib/staff.js";
import { STUDENT_NOTE } from "../src/site.js";

/**
 * The list (PlaceTable), its printout and the filters (FilterBar), rendered to HTML: the staff list's
 * name buttons, where its facts sit and how they are marked, the band line, the order it states, and
 * the colours its text keeps. The components are JSX, so they are bundled with esbuild (Vite's own)
 * and rendered with react-dom/server; where node_modules is not installed those checks are skipped,
 * and the checks read from the source and the libraries still run.
 */
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (name) => readFileSync(join(root, "src", name), "utf8");

// ---------------------------------------------------------------------------------------------------
// The colours: every band and grade text colour keeps 4.5:1 on paper, a hovered row and an open one.

const lum = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const contrast = (a, b) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

test("every band and grade colour used as text keeps 4.5:1 on paper, on a hovered row and on the open place's row", async () => {
  const { default: config } = await import(pathToFileURL(join(root, "tailwind.config.js")).href);
  const paper = config.theme.extend.colors.paper;
  const grounds = { paper: paper.DEFAULT, "paper.sunk": paper.sunk, "paper.edge": paper.edge };
  const colours = { ...Object.fromEntries(Object.entries(BAND_TEXT).map(([b, c]) => [`band ${b}`, c])),
    ...Object.fromEntries(Object.entries(GRADE_TEXT).filter(([, c]) => c).map(([g, c]) => [`grade ${g}`, c])) };
  for (const [name, c] of Object.entries(colours)) {
    for (const [ground, bg] of Object.entries(grounds)) {
      assert.ok(contrast(c, bg) >= 4.5, `${name} ${c} on ${ground} ${bg}: ${contrast(c, bg).toFixed(2)}:1`);
    }
  }
  assert.ok(contrast(BAND_TEXT[2], BAND_TEXT[3]) > 1 && lum(BAND_TEXT[2]) < lum(BAND_TEXT[3]), "band 2's text is darker than band 3's, in band order");
});

// ---------------------------------------------------------------------------------------------------
// From the source: what a render cannot show (effects, the row model's keys, the chart's margins).

test("the list's rows are its places, and a list another view hides is not the one that prints", () => {
  const src = read("PlaceTable.jsx");
  assert.match(src, /getRowId: \(f\) => String\(f\.properties\.facility_id\)/, "a row is keyed by its place");
  assert.match(src, /const open = inline \? active : drawerOpen;/, "inline and not active counts as closed");
  assert.match(src, /listPrints\(\) \? \{ name: listPrintName/, "the print log hears of the list only while it prints");
  for (const prop of ["inline = false", "active = true", "beside = false", "selectedId = null", "onShowSummary = null"]) {
    assert.ok(src.includes(prop), `PlaceTable takes ${prop}`);
  }
  assert.doesNotMatch(src, /opacity-70/);
});

test("the place's chart keeps its score labels inside it, every one, and its first date whole", () => {
  const src = read("InspectionChart.jsx");
  assert.match(src, /margin=\{\{ top: 8, right: 8, left: 0, bottom: 0 \}\}/);
  assert.match(src, /ticks=\{\[FLOOR, 80, 90, 100\]\} interval=\{0\}/, "90, the A line, is not dropped");
  assert.match(src, /width=\{28\}/);
});

test("the filters' counts are solid colours, never faded", () => {
  const src = read("FilterBar.jsx");
  assert.doesNotMatch(src, /opacity-70/);
  assert.match(src, /const countCls = \(on\) => `tnum ml-1\.5 \$\{on \? "text-paper\/80" : "text-ink-3"\}`/);
  assert.equal(src.match(/className=\{countCls\(/g)?.length, 3, "the bands', the kinds' and the facts' counts");
});

// ---------------------------------------------------------------------------------------------------
// Rendered.

let ui = null;
let why = "";
try {
  const { build } = await import("esbuild");
  const dir = mkdtempSync(join(tmpdir(), "sdfood-list-"));
  const out = join(dir, "ui.mjs");
  await build({
    stdin: {
      contents: [
        'export { default as PlaceTable, ListPrintout, listAddress, factsNote, FACTS_IN_LAST_COLUMN, FACTS_EITHER_PLACE, FACTS_UNDER_NAME } from "./src/PlaceTable.jsx";',
        'export { default as FilterBar } from "./src/FilterBar.jsx";',
        'export { default as SampleBanner } from "./src/SampleBanner.jsx";',
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

const bandsMeta = { ...JSON.parse(readFileSync(join(root, "public", "data", "meta.json"), "utf8")), sample: false, audience: "staff" };
const recordMeta = { mode: "record", generated: "2026-09-28", inspections_through: "2026-09-26", expires: "2026-10-12" };
const place = (id, extra = {}) => ({
  type: "Feature",
  geometry: { type: "Point", coordinates: [-117.15, 32.72] },
  properties: {
    facility_id: id, name: `PLACE ${id}`, address: "1250 J ST, SAN DIEGO, CA 92101-6918", facility_type: "restaurant",
    council_district: 3, band: "1", points: 30, flags: ["major", "closed", "bc", "closures2", "temperature", "vermin"],
    last_visit: { date: "2025-06-08", type: "followup" }, grade: { grade: "A", score: 95, date: "2025-06-08" },
    ...extra,
  },
});
const facilities = {
  type: "FeatureCollection",
  features: [
    place("A1"),
    place("B2", { band: "2", points: 1, flags: ["major"], last_visit: { date: "2026-08-01", type: "routine" } }),
    place("C3", { band: null, points: 3, flags: [], address: "401 W MAIN ST, EL CAJON, CA 92020", last_visit: { date: "2026-08-01", type: "complaint" } }),
  ],
};
const filters = { band: "all", districts: [], types: [], flag: null, county: false };

const html = (el, meta = bandsMeta) => ui.renderToStaticMarkup(ui.createElement(ui.MetaProvider, { meta }, ui.createElement(ui.AdvancedProvider, null, el)));
const table = (props = {}, meta = bandsMeta) => html(ui.createElement(ui.PlaceTable, { facilities, filters, onSelect: () => {}, ...props }), meta);
const decode = (s) => s.replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
const text = (s) => decode(s.replace(/<[^>]+>/g, "")).replace(/\s+/g, " ").trim();
// A label as a pattern: "2+" and "(HACCP)" match themselves.
const lit = (s) => String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const nameButtons = (h) => [...h.matchAll(/<button type="button" data-place-id="([^"]*)"([^>]*)>([\s\S]*?)<\/button>/g)]
  .map(([, id, attrs, inner]) => ({ id, attrs, inner }));
const heads = (h) => [...h.matchAll(/<th [^>]*class="([^"]*)"[^>]*>([\s\S]*?)<\/th>/g)].map(([, cls, inner]) => ({ cls, label: text(inner) }));
const note = (h) => text(/<p class="px-5 py-3[^"]*">([\s\S]*?)<\/p>/.exec(h)?.[1] ?? "");
const placeCell = (h, id) => new RegExp(`<td[^>]*>(<button type="button" data-place-id="${id}"[\\s\\S]*?)</td>`).exec(h)?.[1] ?? "";

rendered("each name's button is the place's name, kind and address only; its id is on it, and the open place's button is marked", () => {
  const h = table({ inline: true, selectedId: "A1" });
  const buttons = nameButtons(h);
  assert.deepEqual(buttons.map((b) => b.id), ["A1", "B2", "C3"]);
  assert.equal(text(buttons[0].inner), "PLACE A1Restaurant · 1250 J ST, 92101");
  for (const b of buttons) {
    assert.doesNotMatch(b.inner, /sr-only|Our reading|last visit over a year ago|Majors:/, `${b.id}: nothing but the place in its name`);
  }
  assert.match(buttons[0].attrs, /aria-current="true"/);
  assert.doesNotMatch(buttons[1].attrs + buttons[2].attrs, /aria-current/);
  assert.doesNotMatch(h, /<tr[^>]*aria-current/, "the mark is on the focusable name, once");
  assert.match(h, /first:shadow-\[inset_3px_0_0_#17150F\]/, "the open place's row has an ink bar, not only a faint background");
});

rendered("under a name the facts are marked as our reading, as their column's heading marks them, and the note says where they sit", () => {
  const h = table({ inline: true });
  const cell = placeCell(h, "A1");
  assert.match(cell, /<\/button><span class="inline-block[^"]*mt-1 lg:hidden">last visit over a year ago<\/span>/, "the stale mark follows the name while the last visit is folded");
  assert.match(cell, /<span class="block text-\[12px\] leading-snug text-ink-2 mt-1 xl:hidden"><span class="block"><span class="text-ink-3">Our reading: <\/span>/);
  assert.equal(placeCell(h, "C3").includes("Our reading"), false, "no facts, no label");
  const th = heads(h);
  const facts = th.find((x) => x.label.startsWith("Facts"));
  assert.equal(facts.label, "Facts, 12 months before the list date (our reading)");
  assert.match(facts.cls, /hidden xl:table-cell/);
  assert.doesNotMatch(facts.cls, /whitespace-nowrap/, "its heading wraps in its column");
  assert.match(th.find((x) => x.label === "Last visit").cls, /hidden lg:table-cell/);
  assert.ok(note(h).includes(`${ui.FACTS_EITHER_PLACE} our reading of the County's record in the 12 months before the list date`));
  assert.doesNotMatch(note(h), /The last column/, "on a narrower screen the last column is not the facts");
});

rendered("beside an open place the list folds its last visit and its facts at every width, under each name", () => {
  const h = table({ inline: true, beside: true, selectedId: "A1" });
  const th = heads(h);
  for (const label of ["Last visit", "Facts, 12 months before the list date (our reading)"]) {
    const c = th.find((x) => x.label === label).cls;
    assert.match(c, /\bhidden\b/, label);
    assert.doesNotMatch(c, /table-cell/, `${label}: folded whatever the width`);
  }
  assert.doesNotMatch(h, /<td[^>]*table-cell/, "no folded cell comes back");
  const cell = placeCell(h, "A1");
  assert.match(cell, /class="inline-block[^"]*mt-1">last visit over a year ago/);
  assert.match(cell, /text-ink-2 mt-1"><span class="block"><span class="text-ink-3">Our reading: /);
  assert.doesNotMatch(cell, /lg:hidden|xl:hidden/);
  assert.ok(note(h).includes(`${ui.FACTS_UNDER_NAME} our reading of`));
});

rendered("the facts read as text: a few words each, the full wording to screen readers and as a tooltip, never twice", () => {
  const h = table({ inline: true });
  const cell = /<td[^>]*xl:table-cell">([\s\S]*?)<\/td>/.exec(h)[1];
  assert.doesNotMatch(cell, /\bborder\b/, "no boxes");
  for (const k of ["major", "closed", "bc", "closures2"]) {
    assert.ok(cell.includes(`<span aria-hidden="true" title="${FLAG_LABELS[k]}">${FLAG_SHORT[k]}</span><span class="sr-only">${FLAG_LABELS[k]}.</span>`), k);
  }
  assert.match(cell, /<span class="font-semibold text-ink"><span aria-hidden="true" title="Closed for a health hazard two/, "an escalation fact in ink");
  assert.equal(cell.match(/<span aria-hidden="true"> · <\/span>/g).length, 3, "dots between the four facts, hidden from screen readers");
  assert.match(cell, /class="line-clamp-1">Majors: food temperatures, pests<\/span>/);
  assert.doesNotMatch(cell, /<span title="[^"]*" class="(?!line-clamp)/, "no tooltip on anything a screen reader reads");
});

rendered("in bands mode the list opens with band 1's rate as a group, and a way to every band's", () => {
  const h = table({ inline: true, onShowSummary: () => {} });
  const line = /<p class="shrink-0 border-b[^"]*">([\s\S]*?)<\/p>/.exec(h)?.[1];
  assert.ok(line, "the line is there");
  assert.ok(text(line).startsWith(bandSummary(bandsMeta, "1")), "band 1's rate, as the place pages state it");
  assert.match(text(line), /in 100 band 1 places/);
  assert.match(line, /<button type="button"[^>]*>Every band’s rate: Summary<\/button>/);
  assert.doesNotMatch(table({ inline: true }), /Every band’s rate/, "no link without a Summary view");
  assert.match(table({ inline: true }), /in 100 band 1 places/, "the rate stays without it");
  assert.doesNotMatch(table({ inline: true }, recordMeta), /in 100 band/, "a record export has no bands");
  assert.doesNotMatch(table({}), /shrink-0 border-b border-rule px-5 py-2 text-\[12\.5px\]/, "the public drawer has its own sidebar");
});

rendered("the staff list gives the band and the points in one column, and its addresses drop what every row repeats", () => {
  const h = table({ inline: true });
  const th = heads(h);
  assert.deepEqual(th.map((x) => x.label).slice(0, 2), ["Band, points", "Place"]);
  assert.match(h, /<span class="block font-semibold" style="color:#7F1D1D">Band 1<\/span><span class="block text-\[12px\] leading-snug text-ink">30 points<\/span>/);
  assert.match(h, /style="color:#A63A0A">Band 2<\/span><span[^>]*>1 point<\/span>/, "band 2 in its text colour; one point");
  assert.match(h, /<span class="tnum block"><span class="block text-\[12px\] leading-snug text-ink">3 points<\/span><\/span>/, "no band: the points alone");
  assert.equal(ui.listAddress("1250 J ST, SAN DIEGO, CA 92101-6918"), "1250 J ST, 92101");
  assert.equal(ui.listAddress("762 5TH AVE, SAN DIEGO, CA 92101"), "762 5TH AVE, 92101");
  assert.equal(ui.listAddress("401 W MAIN ST, EL CAJON, CA 92020"), "401 W MAIN ST, EL CAJON, CA 92020", "another town is kept");
  assert.equal(ui.listAddress(null), "");
  const drawer = heads(table({}));
  assert.deepEqual(drawer.map((x) => x.label).slice(0, 3), ["Band", "Points", "Place"], "the public drawer keeps two columns");
});

rendered("the narrow last-visit column shortens a visit we read, still marked, and gives screen readers its full words", () => {
  const h = table({ inline: true });
  assert.ok(h.includes('<span aria-hidden="true" title="re-grade or reopening visit (our reading)">re-grade or reopening (our reading)</span><span class="sr-only">re-grade or reopening visit (our reading)</span>'));
  assert.ok(h.includes('<span aria-hidden="true" title="complaint or other field visit (our reading)">field visit (our reading)</span>'));
  assert.match(h, /<span class="block text-\[12px\] leading-snug">routine inspection<\/span>/, "the County's own type as it is");
});

rendered("the caption states the list's order, which is the printout's too", () => {
  assert.match(table({ inline: true }), /<caption class="sr-only">Listed places, by band, then points, then name\. Select a place’s name to open it\.<\/caption>/);
  assert.match(table({ inline: true }, recordMeta), /<caption class="sr-only">Listed places, by name\./);
  assert.doesNotMatch(table({ inline: true }, recordMeta), /Band, points/, "record mode has no band column");
});

rendered("the public drawer keeps its columns, the full address and a note on its last column", () => {
  const h = table({});
  assert.ok(nameButtons(h).every((b) => /1250 J ST, SAN DIEGO, CA 92101-6918|EL CAJON/.test(b.inner)), "the full address");
  assert.equal(heads(h).at(-1).label, "12 months before the list date (our reading)");
  assert.doesNotMatch(h, /Our reading: /);
  assert.ok(note(h).startsWith("Grades are the County’s latest"));
  assert.ok(note(h).includes(`${ui.FACTS_IN_LAST_COLUMN} our reading of the County's record`));
  assert.ok(note(h).endsWith(ESCALATION_CAVEAT), "an escalation fact is listed, so the note says it is not a County finding");
  assert.match(h, /Jun 2025, re-grade or reopening visit \(our reading\)/);
});

rendered("the note on the facts says an escalation fact is not a County finding only when one is listed", () => {
  assert.ok(ui.factsNote(ui.FACTS_IN_LAST_COLUMN, ["major", "lt90_2"]).endsWith(ESCALATION_CAVEAT));
  assert.equal(ui.factsNote(ui.FACTS_IN_LAST_COLUMN, ["major"]), "The last column is our reading of the County's record in the 12 months before the list date.");
  const quiet = { ...facilities, features: facilities.features.map((f) => ({ ...f, properties: { ...f.properties, flags: ["major"] } })) };
  assert.doesNotMatch(note(table({ inline: true, facilities: quiet })), /not a County finding/);
});

rendered("the printout carries the use rule, the order, each printed band's rate as a group, and what the facts are", () => {
  const print = (props, meta = bandsMeta) => html(ui.createElement(ui.ListPrintout, { features: facilities.features, meta, mode: meta.mode, filters, order: "by name, A to Z", ...props }), meta);
  const h = text(print({}));
  assert.ok(h.includes(USE_NOTE) && h.includes(PUBLIC_RECORD_NOTE), "the staff site's use rule and public-records note");
  assert.match(h, /3 places, by name, A to Z\./);
  assert.ok(h.includes(`${bandSummary(bandsMeta, "1")} ${bandSummary(bandsMeta, "2")}`), "band 1's and band 2's rates, the bands it prints");
  assert.ok(h.includes("The last column is our reading of the County's record"));
  assert.ok(h.includes(ESCALATION_CAVEAT));
  assert.match(h, /Jun 2025, re-grade or reopening visit \(our reading\) \(last visit over a year ago\)/);
  assert.match(text(print({ order: undefined, search: "taco" })), /3 places, closest match first, then by name\./);
  const pub = text(print({}, { ...bandsMeta, audience: undefined }));
  assert.ok(pub.includes(STUDENT_NOTE) && !pub.includes(USE_NOTE), "the public site's printout carries the student note");
  assert.doesNotMatch(text(print({ features: [] })), /in 100 band/, "no rows, no band line");
});

rendered("the filter rail names the facts as the list does, the full wording in each choice's name and tooltip, the escalation facts and the themes apart", () => {
  const rail = (flag = null) => html(ui.createElement(ui.FilterBar, { compact: true, facilities, filters: { ...filters, flag }, onFiltersChange: () => {} }));
  const h = rail();
  assert.match(h, new RegExp(`aria-label="${lit(FLAG_LABELS.closed)}, 1 place" title="${lit(FLAG_LABELS.closed)}"[^>]*>${lit(FLAG_SHORT.closed)}<span`));
  assert.match(h, /<span class="font-semibold text-ink">Over two years<\/span> \(patterns the County(&#x27;|')s Operator(&#x27;|')s Guide names\)/);
  assert.match(h, new RegExp(`title="${lit(FLAG_LABELS.closures2)}" class="[^"]*font-semibold text-ink[^"]*">${lit(FLAG_SHORT.closures2)}<span`), "an escalation choice in ink, as the list marks it");
  assert.match(h, /<details class="group\/themes mt-3">/, "the themes one click away");
  assert.match(h, /aria-label="Major: pests, 1 place" title="Major: pests"[^>]*>Pests<span/);
  const chosen = rail("vermin");
  assert.match(chosen, /<details open="" class="group\/themes mt-3">/, "a chosen theme is never hidden");
  assert.match(text(chosen), /By theme of the major violation: Pests/);
  assert.doesNotMatch(h, /opacity-70/);
  assert.match(h, /class="tnum ml-1\.5 text-ink-3" aria-hidden="true">/);
  const side = html(ui.createElement(ui.FilterBar, { facilities, filters, onFiltersChange: () => {} }));
  assert.match(side, new RegExp(`aria-label="${lit(FLAG_LABELS.closed)}, 1 place" class="[^"]*">${lit(FLAG_LABELS.closed)}<span`), "the public sidebar keeps the full wording, with no tooltip");
  assert.doesNotMatch(side, /group\/themes/);
  assert.ok(THEMES.vermin === "Pests");
});

rendered("the sample banner's lead is band 2's text colour, which keeps 4.5:1 on its ground", () => {
  const h = html(ui.createElement(ui.SampleBanner, {}), { ...bandsMeta, sample: true });
  assert.match(h, new RegExp(`<span class="font-semibold" style="color:${BAND_TEXT[2]}">Sample data\\.</span>`));
  assert.doesNotMatch(h, /text-band-2/);
});
