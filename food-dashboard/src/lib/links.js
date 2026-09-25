/**
 * Links to one place.
 *
 * A place is keyed on the County's permit record id (`facility_id`), which
 * stays with the place from one export to the next and names its file,
 * `data/place/<facility_id>.json`. `/place/<id>` is the place as a page and
 * `/map?place=<id>` opens it on the map. Nothing else is a key: a link that
 * names no listed facility_id is a page that is not found.
 */
export function placeKey(p) {
  return p?.facility_id != null && p.facility_id !== "" ? String(p.facility_id) : "";
}

export const placePath = (p) => `/place/${encodeURIComponent(placeKey(p))}`;
export const mapPlacePath = (p) => `/map?place=${encodeURIComponent(placeKey(p))}`;

/** The key in a `/place/<key>` path, decoded, or null. */
export function parsePlacePath(pathname) {
  const m = /^\/place\/([^/]+)\/?$/.exec(pathname ?? "");
  if (!m) return null;
  try {
    const key = decodeURIComponent(m[1]).trim();
    return key || null;
  } catch {
    return null;
  }
}

/** The index feature whose facility_id is `key`, or null. */
export function findPlace(features, key) {
  if (!features || key == null) return null;
  const k = String(key).trim();
  if (!k) return null;
  return features.find((f) => f.properties?.facility_id != null && String(f.properties.facility_id) === k) ?? null;
}
