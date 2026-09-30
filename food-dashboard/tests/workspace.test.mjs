import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";

/**
 * The staff site's desktop layout (StaffWorkspace): the notice on every layout, the views each at
 * their own address with the list the default, and no welcome modal on the staff site; the filter
 * rail as an overlay under 1280px, the views' heading and focus, the place panel beside the list,
 * the address bar in step with what is shown, and the skeleton while the list loads. Read from the
 * source, since the layout is JSX; the place panel's focus on close is run against a small stand-in
 * for the page.
 */
const src = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
const read = (name) => readFileSync(join(src, name), "utf8");

test("the staff bar is on every layout, and the staff site's desktop is the workspace", () => {
  assert.match(read("StaffWorkspace.jsx"), /<StaffBanner fixed \/>/);
  for (const name of ["PageFrame.jsx", "Landing.jsx"]) assert.match(read(name), /<StaffBanner \/>/, name);
  assert.match(read("MobileShell.jsx"), /<StaffBanner compact \/>/);
  const app = read("App.jsx");
  assert.match(app, /\{!staff && <WelcomeModal \/>\}/, "on the staff site the notice opens instead of the welcome");
  assert.match(app, /if \(staff\) \{\s*return \(\s*<StaffWorkspace/, "the staff site's desktop layout");
});

test("the staff site's views each have an address, and the list is the default", () => {
  const ws = read("StaffWorkspace.jsx");
  assert.match(ws, /\{ key: "list", label: "List", path: "\/" \}/);
  assert.match(ws, /\{ key: "map", label: "Map", path: "\/map" \}/);
  assert.match(ws, /\{ key: "summary", label: "Summary", path: "\/summary" \}/);
  assert.match(ws, /aria-current=\{on \? "page" : undefined\}/, "the view shown is marked for screen readers");
  assert.match(ws, /href=\{`\$\{t\.path\}\$\{search\}`\}/, "a view's link keeps the open place and the district");
  const app = read("App.jsx");
  assert.match(app, /if \(staff\) return \{ view: "map", place: null, list: true, key, tab: "list" \}/, "the staff site's / is the list");
  assert.match(app, /staff && path === "\/summary"/, "/summary only on the staff site");
});

test("under 1280px the filter rail is an overlay that holds focus until it closes, and focus goes back to Filters", () => {
  const ws = read("StaffWorkspace.jsx");
  assert.match(ws, /useMediaQuery\(WIDE\)/);
  assert.match(ws, /const WIDE = "\(min-width: 1280px\)"/);
  assert.match(ws, /const overlay = railOpen && !wide/, "only while the rail is actually an overlay");
  assert.match(ws, /if \(wide\) setRailOpen\(false\)/, "widening the window closes it");
  assert.match(ws, /railHeading\.current\?\.focus\(/, "on open, its heading takes focus");
  assert.match(ws, /<h2 id="filter-rail-heading" ref=\{headingRef\} tabIndex=\{-1\}/);
  assert.match(ws, /filtersButton\.current\?\.focus\(/, "on close, focus goes back to Filters");
  assert.match(ws, /document\.addEventListener\("keydown", onKey, true\)/, "Escape in the capture phase, before the open place's own");
  assert.match(ws, /e\.stopPropagation\(\);\s*closeRail\(\);/);
  assert.match(ws, /<CloseButton onClose=\{onClose\} label="Close the filters" \/>/, "a visible close button in the overlay");
  assert.match(ws, /onClose=\{overlay \? \(\) => closeRail\(\) : null\}/);
  assert.match(ws, /<div aria-hidden="true" onMouseDown=\{\(e\) => \{ e\.preventDefault\(\); closeRail\(\); \}\}/,
    "the backdrop closes it with the mouse, keeps the focus the close gives Filters, and is not a tab stop");
  assert.doesNotMatch(ws, /<button[^>]*aria-label="Close the filters"/);
  assert.match(ws, /const inert = overlay \? "" : undefined/);
  assert.match(ws, /<div id="workspace" tabIndex=\{-1\} inert=\{inert\}/, "the rest of the page is inert while it is open");
  assert.equal((ws.match(/<div className="contents" inert=\{inert\}>/g) ?? []).length, 2, "the masthead, the notice, the views row and the footer too");
  assert.match(ws, /overlay \? \{ role: "dialog", "aria-modal": "true", "aria-labelledby": "filter-rail-heading" \}/);
});

test("the Filters count and the rail's Clear read as words", () => {
  const ws = read("StaffWorkspace.jsx");
  assert.match(ws, /<span className="sr-only">, \{changed\} changed<\/span>/);
  assert.match(ws, /<span aria-hidden="true" className="tnum ml-1\.5 bg-ink/);
  assert.match(ws, /Clear \{changed === 1 \? "the filter" : `all \$\{changed\} filters`\}/);
});

test("the rail has the address check right under the district, as the staff sidebar did", () => {
  const ws = read("StaffWorkspace.jsx");
  const rail = ws.slice(ws.indexOf("function FilterRail"));
  const picker = rail.indexOf("<DistrictPicker");
  const near = rail.indexOf("Near an address");
  const bar = rail.indexOf("<FilterBar compact");
  assert.ok(picker > 0 && picker < near && near < bar, "district, then an address, then the other filters");
});

test("each view has one heading that stays mounted, a change of view is announced, and a lost focus goes to the heading", () => {
  const ws = read("StaffWorkspace.jsx");
  assert.equal((ws.match(/<h1\b/g) ?? []).length, 1);
  const h1 = ws.indexOf('<h1\n            id="view-heading"');
  assert.match(ws, /id="view-heading"\s+ref=\{viewHeading\}\s+tabIndex=\{-1\}\s+className="sr-only focus:not-sr-only[^"]*focus:outline-ink"/, "seen while it has focus");
  assert.ok(h1 > ws.indexOf('<div id="workspace"') && h1 < ws.indexOf("{loading ? ("), "first in #workspace, outside the views");
  assert.match(ws, /<p className="sr-only" role="status">\{announce\}<\/p>/, "a live region mounted from the first render");
  assert.match(ws, /const lost = !a \|\| a === document\.body \|\| !a\.isConnected \|\| a\.getClientRects\(\)\.length === 0;\s*if \(lost\) \{\s*viewHeading\.current\?\.focus\(/);
  assert.match(ws, /href="#view-heading"/, "the skip link lands on the heading");
});

test("the list stays mounted on the other views, and its printout is off while it is hidden", () => {
  const ws = read("StaffWorkspace.jsx");
  assert.doesNotMatch(ws, /\{tab === "list" && \(?\s*<PlaceTable/);
  assert.match(ws, /<div className=\{tab === "list" \? "print-release h-full min-w-0 flex-1" : "hidden"\} inert=\{tab === "list" && selected && !docks \? "" : undefined\}>\s*<PlaceTable\s+inline\s+active=\{tab === "list"\}/,
    "under 1024px, while the place panel covers it, the list is out of the tab order");
  assert.match(ws, /onShowSummary=\{\(\) => onTab\("summary"\)\}/);
});

test("on the List the place panel stands beside the list from 1024px, which folds its last columns", () => {
  const ws = read("StaffWorkspace.jsx");
  assert.match(ws, /beside=\{tab === "list" && Boolean\(selected\)\}/);
  assert.match(ws, /docked=\{tab === "list"\}/);
  assert.match(ws, /returnFocusTo="view-heading"/);
  assert.match(ws, /<div id="workspace"[^>]*className="print-release relative flex min-w-0 flex-1/, "#workspace is a row");
  const panel = read("PlacePanel.jsx");
  assert.match(panel, /docked \? " lg:static lg:w-\[27rem\] lg:max-w-none lg:shrink-0 lg:shadow-none" : ""/);
  assert.match(read("App.jsx"), /<PlacePanel feature=\{selected\} onClose=\{closePlace\} returnFocusTo="map-area"/, "the public site falls back to the map");
});

test("only the place panel's top stays put: its tags and lines scroll with the record", () => {
  const panel = read("PlacePanel.jsx");
  const header = panel.slice(panel.indexOf("<header"), panel.indexOf("</header>"));
  assert.match(header, /ref=\{headingRef\}/);
  assert.doesNotMatch(header, /<PlaceLines|<Tag\b|<StaleBadge/);
  const body = panel.indexOf('<div className="print-scroll min-h-0 flex-1 overflow-y-auto">');
  assert.ok(body > 0 && panel.indexOf("<PlaceLines") > body && panel.indexOf("<Tag>{typeLabel") > body);
});

test("the cookie line is the workspace's last row, in flow, not over the list's pager", () => {
  const ws = read("StaffWorkspace.jsx");
  assert.match(ws, /<Notice placement="footer" onNavigate=\{onNavigate\} \/>/);
  assert.doesNotMatch(ws, /placement="fixed"/);
});

test("on the public desktop too the cookie line is in flow, and the list's drawer and its toggle sit above it", () => {
  const app = read("App.jsx");
  assert.match(app, /<\/main>\s*\{\/\*[^*]*\*\/\}\s*<Notice placement="footer" onNavigate=\{navigate\} \/>\s*<\/div>/, "the column's last row");
  const table = read("PlaceTable.jsx");
  assert.match(table, /"print-hide absolute bottom-0 left-1\/2 z-30 flex/, "the Full list toggle, at the foot of main");
  assert.match(table, /`print-hide absolute left-0 right-0 z-20 flex-col/, "the drawer, over the foot of main");
  assert.doesNotMatch(table, /print-hide fixed/, "nothing of the list is pinned to the screen, under the cookie line");
});

test("Escape in an open list of suggestions closes only the list: the dialog, the rail and the open place stay", () => {
  assert.match(read("AddressInput.jsx"), /e\.key === "Escape"\) \{\s*e\.preventDefault\(\);\s*setOpen\(false\);/);
  assert.match(read("SearchBox.jsx"), /if \(open && query\.trim\(\)\.length >= 2\) e\.preventDefault\(\);/);
  assert.match(read("Dialog.jsx"), /if \(e\.target\?\.closest\?\.\('\[role="combobox"\]\[aria-expanded="true"\]'\)\) return;\s*e\.stopPropagation\(\);/, "the dialog lets the list close first");
  assert.match(read("StaffWorkspace.jsx"), /if \(e\.target\?\.closest\?\.\('\[role="combobox"\]\[aria-expanded="true"\]'\)\) return;/, "so does the rail");
  assert.match(read("PlacePanel.jsx"), /e\.key === "Escape" && !e\.defaultPrevented && !message && onClose\(\)/, "and the open place");
});

test("the map moves to the open place and the address once it exists", () => {
  const map = read("MapView.jsx");
  assert.match(map, /if \(!mapReady \|\| !map \|\| !pointOverlay\?\.point\) return;[\s\S]*?\}, \[pointOverlay, mapReady\]\);/);
  assert.match(map, /if \(!mapReady \|\| !map \|\| !selected\) return;[\s\S]*?\}, \[selected, selectionOffsetY, mapReady\]\);/);
  assert.ok(map.indexOf("[pointOverlay, mapReady]") < map.indexOf("[selected, selectionOffsetY, mapReady]"), "the place wins over the address");
});

test("the address follows what is shown: back, forward and the masthead never bring back an old place or district", () => {
  const app = read("App.jsx");
  assert.match(app, /writePlaceToUrl\(.*\);\s*\}, \[selected, view, loc\.key\]\);/);
  assert.match(app, /writeDistrictToUrl\(.*\);\s*\}, \[filters\.districts, view, loc\.key\]\);/);
  assert.match(app, /const onPop = \(\) => setLocation\(viewFromLocation\(staff\)\);/, "back and forward change the view only");
  assert.doesNotMatch(app, /onPop[\s\S]{0,200}readDistrictFromUrl/);
});

test("a view's tab adds a history entry only for another view", () => {
  const app = read("App.jsx");
  const goTab = app.slice(app.indexOf("const goTab"), app.indexOf("}, [staff]);", app.indexOf("const goTab")));
  assert.match(goTab, /if \(url\.href === window\.location\.href\) return;/);
  assert.match(goTab, /const sameTab = viewFromLocation\(staff\)\.tab === target\.key;/);
  assert.match(goTab, /window\.history\[sameTab \? "replaceState" : "pushState"\]\(null, "", url\);/);
});

test("the staff Summary's bookmark is the List for a district", () => {
  const ds = read("DistrictSummary.jsx");
  assert.match(ds, /\{staff \? "\/\?district=3" : "\/map\?district=3"\}/);
});

test("while the list loads, the staff desktop is its own layout in grey, under the real masthead and notice", () => {
  const app = read("App.jsx");
  assert.match(app, /if \(loading && !staffDesk\) return <LoadingShell \/>;/);
  assert.match(app, /<StaffWorkspace\s+loading=\{loading\}/);
  const shell = app.slice(app.indexOf("function LoadingShell"));
  assert.match(shell, /if \(staff && !isPhone\)/);
  assert.match(shell, /<RailSkeleton \/>/);
  assert.match(shell, /<ViewSkeleton tab=/);
  assert.match(shell, /hidden w-\[17rem\] shrink-0 border-r border-rule-strong xl:block/, "the rail where it will stand");
  const ws = read("StaffWorkspace.jsx");
  assert.match(ws, /\{loading \? <RailSkeleton \/> : \(/);
  assert.match(ws, /<ViewSkeleton tab=\{tab\} \/>/);
});

/** PlacePanel's refocusAfterClose, taken from the source and run against a stand-in for the page. */
function loadRefocus() {
  const panel = read("PlacePanel.jsx");
  const start = panel.indexOf("export function refocusAfterClose");
  assert.ok(start > 0, "PlacePanel has refocusAfterClose");
  const end = panel.indexOf("\n}\n", start) + 2;
  const code = panel.slice(start, end).replace(/^export /, "");
  return (doc) => runInNewContext(`${code}\nrefocusAfterClose;`, { document: doc, CSS: { escape: (s) => s } });
}

function page() {
  const doc = { body: { name: "body" }, activeElement: null, asked: [], parts: {} };
  doc.activeElement = doc.body;
  doc.querySelector = (sel) => { doc.asked.push(sel); return doc.parts.row ?? null; };
  doc.getElementById = (id) => (id === "view-heading" ? doc.parts.heading ?? null : null);
  doc.el = (name, { takes = true, connected = true } = {}) => ({
    name,
    isConnected: connected,
    focus() { if (takes) doc.activeElement = this; },
  });
  return doc;
}

test("closing a place puts focus on the list's button for it, else on what opened it, else on the view's heading", () => {
  const make = loadRefocus();

  let doc = page();
  doc.parts = { row: doc.el("row"), heading: doc.el("heading") };
  const opener = doc.el("opener");
  make(doc)("DEH-1", opener, "view-heading");
  assert.equal(doc.activeElement.name, "row");
  assert.deepEqual(doc.asked, ['#workspace [data-place-id="DEH-1"]']);

  doc = page();
  doc.parts = { row: doc.el("row", { takes: false }), heading: doc.el("heading") };
  make(doc)("DEH-1", doc.el("opener"), "view-heading");
  assert.equal(doc.activeElement.name, "opener", "the row is in a hidden view: what opened the panel");

  doc = page();
  doc.parts = { heading: doc.el("heading") };
  make(doc)("DEH-1", doc.el("opener", { connected: false }), "view-heading");
  assert.equal(doc.activeElement.name, "heading", "the row is off the page and the opener is gone");

  doc = page();
  doc.parts = { heading: doc.el("heading") };
  make(doc)("DEH-1", doc.el("opener", { takes: false }), "view-heading");
  assert.equal(doc.activeElement.name, "heading", "an opener that cannot take focus");

  doc = page();
  doc.parts = { row: doc.el("row"), heading: doc.el("heading") };
  const masthead = doc.el("masthead");
  doc.activeElement = masthead;
  make(doc)("DEH-1", doc.el("opener"), "view-heading");
  assert.equal(doc.activeElement, masthead, "focus left elsewhere (the masthead, a row) stays");
});

test("the place panel remembers what opened it only when it opens, not when another place opens inside it", () => {
  const panel = read("PlacePanel.jsx");
  assert.match(panel, /if \(feature\) \{\s*if \(!before\) opener\.current = document\.activeElement;/);
  assert.match(panel, /\} else if \(before\) \{\s*refocusAfterClose\(before\.properties\?\.facility_id, opener\.current, returnFocusTo\);/);
});
