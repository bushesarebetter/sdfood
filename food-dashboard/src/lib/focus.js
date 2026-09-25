/**
 * Focus inside a dialog. `focusables` lists what Tab can reach inside a
 * root; `trapTarget` says where Tab or Shift+Tab should go instead of
 * leaving it, or null when the browser's own move stays inside.
 */
export const FOCUSABLE = [
  "a[href]", "area[href]", "button:not([disabled])", "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])", "textarea:not([disabled])", "iframe", "[tabindex]:not([tabindex='-1'])", "[contenteditable='true']",
].join(",");

export function focusables(root) {
  if (!root) return [];
  return [...root.querySelectorAll(FOCUSABLE)].filter((el) => !el.closest("[hidden],[inert]") && el.getAttribute("aria-hidden") !== "true");
}

/**
 * items: the focusable elements in order; active: what has focus now;
 * inside: whether `active` is inside the dialog at all.
 */
export function trapTarget(items, active, shiftKey, inside = items.includes(active)) {
  if (!items.length) return null;
  const first = items[0];
  const last = items[items.length - 1];
  if (!inside) return shiftKey ? last : first;
  if (shiftKey && active === first) return last;
  if (!shiftKey && active === last) return first;
  return null;
}
