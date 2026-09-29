import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * The staff site's desktop layout (StaffWorkspace): the notice on every layout, the views each at
 * their own address with the list the default, and no welcome modal on the staff site. Read from the
 * source, since the layout is JSX.
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
  const app = read("App.jsx");
  assert.match(app, /if \(staff\) return \{ view: "map", place: null, list: true, key, tab: "list" \}/, "the staff site's / is the list");
  assert.match(app, /staff && path === "\/summary"/, "/summary only on the staff site");
});
