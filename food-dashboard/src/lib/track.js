/**
 * Count an action, when a counter is present.
 *
 * The deploy may load GoatCounter (see main.jsx); if it did, this records a
 * named event with no personal data, so "messages copied" and "routes checked"
 * become numbers the project can report. Without a counter it does nothing.
 */
export function track(name) {
  try {
    const gc = window.goatcounter;
    if (gc && typeof gc.count === "function") gc.count({ path: `event/${name}`, title: name, event: true });
  } catch {
    /* never let counting break the page */
  }
}
