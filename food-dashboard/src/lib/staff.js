/**
 * The City staff site: the same app, built in the PRIVATE staff repository (vite.config.js defines
 * __STAFF__ there) and shipped with a staff copy of meta.json (publish_city_site.py: audience "staff",
 * contact, operator, sunset, review_status). The staff site shows what the public site never needs:
 * that downloads are public records, whom to write to, and which checks the list has not passed.
 */
/* global __STAFF__ */

export function isStaff(meta) {
  const built = typeof __STAFF__ !== "undefined" && __STAFF__ === true;
  return built || meta?.audience === "staff";
}

/** "Jane Doe (jane@example.org)", or null. */
export function contactLine(meta) {
  const c = meta?.contact;
  if (!c || typeof c !== "object") return null;
  if (c.name && c.email) return `${c.name} (${c.email})`;
  return c.email || c.name || null;
}

/** The public-release checks this list has not passed, as the staff copy of meta states them. */
export function reviewStatus(meta) {
  return Array.isArray(meta?.review_status) ? meta.review_status.filter((s) => typeof s === "string" && s) : [];
}

export const PUBLIC_RECORD_NOTE =
  "Anything you download, print or send from this site may be a City public record under the California Public Records Act.";

export const USE_NOTE =
  "This is a student analysis of the County's published results, not a City or County finding about any business. " +
  "Do not forward names or bands outside the City, and do not contact a business about its band or use a band for any permit, " +
  "license, enforcement, grant, procurement or public-statement decision.";
