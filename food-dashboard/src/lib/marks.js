/**
 * The colour and size of a place's mark, on paper and on the map.
 *
 * In `record` mode every place is drawn alike, in one neutral colour: the
 * site orders nothing. In `bands` mode the bands carry the one sequential
 * ramp, darker for more points; lightness carries the order, so the marks
 * survive greyscale and colourblind viewing. A place under review, and a
 * listed place in no band, is drawn in a light neutral with no label.
 */
export const BAND_COLORS = { 1: "#7F1D1D", 2: "#C2410C", 3: "#D97706" };
// The same bands as text on paper: amber is darkened to keep 4.5:1 contrast.
export const BAND_TEXT = { 1: "#7F1D1D", 2: "#C2410C", 3: "#9A4A07" };
const BAND_RADIUS = { 1: 26, 2: 22, 3: 19 };

export const RECORD_DOT = "#55503F";
export const UNBANDED_DOT = "#A39A88";
const RECORD_RADIUS = 20;
const UNBANDED_RADIUS = 15;

const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));

/** Whether a place carries a band the site may show. */
export function shownBand(p, { mode = "record" } = {}) {
  if (mode !== "bands" || !p || p.on_hold || p.band == null) return null;
  return String(p.band);
}

/**
 * { hex, text, rgb, radius, label } for one place. `label` is "Band 1",
 * "Under review", or null.
 */
export function markFor(p, { mode = "record" } = {}) {
  if (mode !== "bands") return { hex: RECORD_DOT, text: null, rgb: rgb(RECORD_DOT), radius: RECORD_RADIUS, label: null };
  const b = shownBand(p, { mode });
  if (b && BAND_COLORS[b]) {
    return { hex: BAND_COLORS[b], text: BAND_TEXT[b], rgb: rgb(BAND_COLORS[b]), radius: BAND_RADIUS[b], label: `Band ${b}` };
  }
  return { hex: UNBANDED_DOT, text: null, rgb: rgb(UNBANDED_DOT), radius: UNBANDED_RADIUS, label: p?.on_hold ? "Under review" : null };
}
