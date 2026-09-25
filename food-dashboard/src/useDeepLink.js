/**
 * Deep links: `/map?place=<facility_id>` opens that place; `/map?district=3`
 * opens the map filtered to one council district. A place is keyed on the
 * County's permit record id and nothing else. replaceState, so selecting
 * dots does not fill the back button.
 */
const PLACE = "place";
const DISTRICT = "district";

const readRaw = (key) => {
  if (typeof window === "undefined") return null;
  const raw = new URLSearchParams(window.location.search).get(key);
  return raw == null || raw.trim() === "" ? null : raw.trim();
};

const readInt = (key) => {
  const raw = readRaw(key);
  const n = raw == null ? NaN : parseInt(raw, 10);
  return Number.isFinite(n) && n > 0 ? n : null;
};

const writeParam = (key, value) => {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (value) url.searchParams.set(key, String(value));
  else url.searchParams.delete(key);
  window.history.replaceState(null, "", url);
};

/** The facility_id in the address bar, or null. */
export const readPlaceFromUrl = () => readRaw(PLACE);
export const writePlaceToUrl = (key) => writeParam(PLACE, key);
export const readDistrictFromUrl = () => readInt(DISTRICT);
export const writeDistrictToUrl = (d) => writeParam(DISTRICT, d);
