import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { trapTarget } from "../src/lib/focus.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

test("Tab wraps from the last control to the first, Shift+Tab the other way, and focus outside comes back in", () => {
  const [a, b, c] = ["a", "b", "c"];
  const items = [a, b, c];
  assert.equal(trapTarget(items, c, false), a);
  assert.equal(trapTarget(items, a, true), c);
  assert.equal(trapTarget(items, b, false), null, "the browser's own move stays inside");
  assert.equal(trapTarget(items, b, true), null);
  assert.equal(trapTarget(items, "heading", false), a, "from the heading, Tab goes to the first control");
  assert.equal(trapTarget(items, "heading", true), c);
  assert.equal(trapTarget([], a, false), null);
});

test("every modal uses the one Dialog, which focuses its heading, traps Tab, closes on Escape and restores focus", () => {
  const dialog = readFileSync(join(root, "src", "Dialog.jsx"), "utf8");
  assert.match(dialog, /heading\?\.focus\(/);
  assert.match(dialog, /e\.key === "Escape"/);
  assert.match(dialog, /trapTarget\(/);
  assert.match(dialog, /previous\.focus\(/);
  assert.match(dialog, /aria-modal="true"/);
  for (const name of ["AboutModal.jsx", "WelcomeModal.jsx", "MessageBox.jsx", "MobileShell.jsx"]) {
    const src = readFileSync(join(root, "src", name), "utf8");
    assert.match(src, /<Dialog\b/, `${name} uses Dialog`);
    assert.doesNotMatch(src, /role="dialog"/, `${name} has no dialog of its own`);
  }
});
