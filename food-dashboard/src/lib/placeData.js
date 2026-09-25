/**
 * One place's full record, loaded only when the place is opened.
 *
 * The index (`data/facilities.geojson`) holds what the map, the list and the
 * search need; each place's record is its own file,
 * `data/place/<facility_id>.json`. A place view asks for it and says plainly
 * what happened: still loading, no such file (the host's 404, or its app
 * page served in place of a file it does not have), or a network error that
 * a retry may fix.
 */
export const placeFileUrl = (id) => `/data/place/${encodeURIComponent(String(id ?? ""))}.json`;

/** A place file may be a flat object or a GeoJSON Feature; either way, its properties. */
export function detailProps(json) {
  if (json && json.type === "Feature" && json.properties) return json.properties;
  return json && typeof json === "object" ? json : null;
}

/** The index entry's properties with the place file's full record on top. */
export function mergePlace(feature, detail) {
  return { ...(feature?.properties ?? {}), ...(detailProps(detail) ?? {}) };
}

/**
 * { status: "ok", detail } | { status: "missing" } | { status: "error", reason }.
 * `fetchImpl` is injectable for tests.
 */
export async function fetchPlace(id, { fetchImpl = globalThis.fetch } = {}) {
  if (!id) return { status: "missing" };
  let res;
  try {
    res = await fetchImpl(placeFileUrl(id), { headers: { Accept: "application/json" } });
  } catch (err) {
    return { status: "error", reason: String(err?.message ?? err) };
  }
  if (res.status === 404 || res.status === 410) return { status: "missing" };
  if (!res.ok) return { status: "error", reason: `HTTP ${res.status}` };
  const type = res.headers?.get?.("content-type") ?? "";
  // A single-page host answers a missing file with its app page.
  if (/text\/html/i.test(type)) return { status: "missing" };
  let json;
  try {
    json = await res.json();
  } catch (err) {
    return { status: "error", reason: "the file did not read as JSON" };
  }
  const detail = detailProps(json);
  if (!detail) return { status: "error", reason: "the file is empty" };
  if (detail.facility_id != null && String(detail.facility_id) !== String(id)) {
    return { status: "error", reason: "the file is for another place" };
  }
  return { status: "ok", detail };
}

/** What a place view says for each state, in plain words. */
export const PLACE_STATUS_TEXT = {
  loading: "Loading this place's record.",
  missing: "This site has no record file for this place. It may have left the list since the page you came from was made.",
  error: "This place's record did not load. Check the connection and try again.",
};
