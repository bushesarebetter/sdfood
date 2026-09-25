/**
 * Shared constants, in their own module so that components never import from
 * App.jsx and App.jsx never depends on a component for a number.
 */

// A `bands` export opens on all three bands and offers band 1, bands 1 and 2,
// bands 1 to 3, or every listed place. The labels say what each choice holds.
export const DEFAULT_BAND = "3";
export const ALL_PLACES = "all";
export const BAND_FILTERS = [
  { band: "1", label: "Band 1" },
  { band: "2", label: "Bands 1 and 2" },
  { band: "3", label: "Bands 1 to 3" },
  { band: ALL_PLACES, label: "Every listed place" },
];

export const REPO_URL = "https://github.com/bushesarebetter/sdfood";
