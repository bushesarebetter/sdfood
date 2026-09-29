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

/**
 * What the checks the list has not passed mean for someone using it, one sentence each: a count of
 * open checks is ignored by the second week; an instruction is not.
 */
export function reviewGuidance(meta) {
  const status = reviewStatus(meta);
  const out = [];
  const has = (re) => status.some((s) => re.test(s));
  if (has(/does not beat|within 0\.01 AUC/)) {
    out.push("The points summarise the County's record; they do not predict better than a place's recent major violations. Read a record with them, but do not rank places against each other by points.");
  }
  if (has(/cost ratio|nothing to name/)) {
    out.push("No band is strong enough to justify singling out a business.");
  }
  const districts = [...new Set(status.map((s) => /^district (\d+):/.exec(s)?.[1]).filter(Boolean))].map(Number).sort((a, b) => a - b);
  if (districts.length) {
    const list = districts.length > 1 ? `${districts.slice(0, -1).join(", ")} and ${districts.at(-1)}` : `${districts[0]}`;
    out.push(`A band is wrong more often in District${districts.length > 1 ? "s" : ""} ${list} than elsewhere: do not compare districts by how many places are in a band.`);
  }
  if (has(/prospective test/)) {
    out.push("The rule has not yet been tested on inspections made after it was frozen.");
  }
  if (has(/responsible adult|student author/)) {
    out.push("No independent adult has signed off on this list; its operator is a student author.");
  }
  return out;
}
