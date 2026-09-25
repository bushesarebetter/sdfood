/**
 * What a band is, in the only terms the export can back (`bands` mode only).
 *
 * The published rule (`meta.card.rule`) gives each place points from its own
 * County record, and the places with the most points are cut into bands:
 * band 1 the 2.5% of scored places with the most points, band 2 the next 5%,
 * band 3 the next 10% (`meta.card.bands`, whose `share` is cumulative). A
 * band is a range of points (`min_points` to `max_points`), so places with
 * the same points are always in the same band.
 *
 * Each band carries a hit rate from a backtest: the same rule applied to the
 * record as it stood on an earlier date, checked against the routine
 * inspections that followed. A band's result is stated as its rate beside the
 * rate for scored places below the bands (`meta.card.rest.rate`), and as the
 * ratio of the two. None of it is a statement about any one place.
 */
import { fmtDate } from "./dates.js";

const pct = (x) => `${Math.round(x * 100)}%`;
const sharePct = (x) => `${Math.round(x * 1000) / 10}%`;

/** The bands meta.card defines, in order, each with the slice of scored places it covers. */
export function bandDefs(meta) {
  const bands = meta?.card?.bands;
  if (!Array.isArray(bands)) return [];
  let prev = 0;
  return [...bands]
    .sort((a, b) => Number(a.band) - Number(b.band))
    .map((b) => {
      const to = typeof b.share === "number" ? b.share : null;
      const from = prev;
      if (to != null) prev = to;
      return { ...b, band: String(b.band), from, to, width: to != null ? Math.max(0, to - from) : null };
    });
}

export const bandDef = (meta, band) => (band == null ? null : bandDefs(meta).find((b) => b.band === String(band)) ?? null);

/**
 * "about the 2.5% of scored places with the most points", "about the next 5%
 * by points", or null. "About", because a band's edge moves to keep equal
 * points together, so its share is near the target and rarely on it.
 */
export function bandShare(meta, band) {
  const d = bandDef(meta, band);
  if (!d || d.width == null) return null;
  return d.from === 0 ? `about the ${sharePct(d.width)} of scored places with the most points` : `about the next ${sharePct(d.width)} by points`;
}

/** "12 to 20 points", "20 points", "12 points or more", or null. */
export function bandPoints(meta, band) {
  const d = bandDef(meta, band);
  if (!d) return null;
  const lo = typeof d.min_points === "number" ? d.min_points : null;
  const hi = typeof d.max_points === "number" ? d.max_points : null;
  if (lo == null && hi == null) return null;
  if (lo != null && hi != null) return lo === hi ? `${lo} points` : `${lo} to ${hi} points`;
  return lo != null ? `${lo} points or more` : `up to ${hi} points`;
}

/** The public rule in one sentence, as meta states it. */
export function ruleSentence(meta) {
  return meta?.card?.rule ?? "Places are given points by a published rule over their own County record.";
}

/** The rate for scored places below the bands, or null. */
export function restRate(meta) {
  const r = meta?.card?.rest?.rate;
  return typeof r === "number" ? r : null;
}

/** A band's rate over the rate below the bands, to one decimal, or null. */
export function rateRatio(meta, band) {
  const d = bandDef(meta, band);
  const rest = restRate(meta);
  if (!d || typeof d.rate !== "number" || !(rest > 0)) return null;
  return Math.round((d.rate / rest) * 10) / 10;
}

/** Which list the rates come from: "the list drawn up the same way on September 1, 2025". */
export function backtestList(meta) {
  const asOf = meta?.catch_run?.as_of;
  return asOf ? `the list drawn up the same way on ${fmtDate(asOf)}` : "the list drawn up the same way for the backtest";
}

/**
 * The sentence beside every band: "In the backtest, band 1 places had a major
 * violation at their next routine inspection at 3.4 times the rate of scored
 * places below the bands (55% vs 16%)."
 */
export function bandSummary(meta, band) {
  const d = bandDef(meta, band);
  if (!d || typeof d.rate !== "number") return `Band ${band} has no backtest rate in this export.`;
  const rest = restRate(meta);
  const ratio = rateRatio(meta, band);
  if (rest == null || ratio == null) {
    return `In the backtest, ${pct(d.rate)} of band ${d.band} places had a major violation at their next routine inspection.`;
  }
  return `In the backtest, band ${d.band} places had a major violation at their next routine inspection at ${ratio} times the rate of scored places below the bands (${pct(d.rate)} vs ${pct(rest)}).`;
}

/** "55% had a major at the next routine inspection", for a legend or a table cell. */
export function bandRatePhrase(meta, band) {
  const d = bandDef(meta, band);
  if (!d || typeof d.rate !== "number") return null;
  return `${pct(d.rate)} had a major`;
}

/** "95% interval 46% to 63%", or null. */
export function bandInterval(meta, band) {
  const iv = bandDef(meta, band)?.interval;
  if (!Array.isArray(iv) || iv.length !== 2 || !iv.every((x) => typeof x === "number")) return null;
  return `95% interval ${pct(iv[0])} to ${pct(iv[1])}`;
}

/** How often refits of the rule kept this place in its band. */
export function stabilitySentence(p) {
  const s = p?.band_stability;
  if (p?.band == null || typeof s !== "number") return null;
  return `Stayed in band ${p.band} in ${pct(s)} of refits of the rule on resampled data.`;
}
