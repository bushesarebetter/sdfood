/**
 * What a band is, in the only terms the export can back (`bands` mode only).
 *
 * The students' point rule (`meta.card.rule`) gives each place points from
 * its own County record. The places with the most points are cut into bands
 * at fixed shares of the list, and a split is kept only where it held at
 * every backtest date (`meta.card.band_rule`), so there may be one band or
 * several (`meta.card.bands`, whose `share` is cumulative). A band is a range
 * of points (`min_points` to `max_points`): equal points share a band.
 *
 * Each band carries a hit rate from a backtest: the same rule applied to the
 * record as it stood on an earlier date, checked against the routine
 * inspections that followed. It is stated in natural frequencies with its
 * likely range, beside the rate for all scored restaurants
 * (`meta.card.base_rate`). Every scored place also gets an estimate read from
 * a monotone (isotonic) fit of rate by points (`meta.card.curve`). Places outside the
 * City are described by rates measured outside the City (`meta.card.outside`).
 * None of it is a statement about any one place (GROUP_NOTE).
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

/** The rule in one sentence, as meta states it. */
export function ruleSentence(meta) {
  return meta?.card?.rule ?? "Places are given points by the students' point rule over their own County record.";
}

/** Rates measured outside the City, for a place outside it (null when the export has none). */
const outsideOf = (meta) => meta?.card?.outside ?? null;

/** A band's backtest row: the City's, or for a place outside the City the one measured there. */
function bandRow(meta, band, outside) {
  if (outside) return (outsideOf(meta)?.bands ?? []).find((r) => String(r.band) === String(band)) ?? null;
  return bandDef(meta, band);
}

/** The rate a band is compared with: all scored restaurants (base_rate), or the rest below the bands. */
function comparison(meta, outside) {
  const o = outside ? outsideOf(meta) : meta?.card;
  if (typeof o?.base_rate === "number") return { rate: o.base_rate, who: outside ? "all scored restaurants outside the City" : "all scored restaurants" };
  const r = outside ? o?.rest?.rate : restRate(meta);
  return typeof r === "number" ? { rate: r, who: outside ? "scored places outside the City below the bands" : "scored places below the bands" } : null;
}

/** The rate for scored places below the bands, or null. */
export function restRate(meta) {
  const r = meta?.card?.rest?.rate;
  return typeof r === "number" ? r : null;
}

/** A band's rate over the comparison rate (all scored restaurants when the export has it), to one decimal, or null. */
export function rateRatio(meta, band, { outside = false } = {}) {
  const d = bandRow(meta, band, outside);
  const c = comparison(meta, outside);
  if (!d || typeof d.rate !== "number" || !(c?.rate > 0)) return null;
  return Math.round((d.rate / c.rate) * 10) / 10;
}

/** Which list the rates come from: "the list drawn up the same way on September 1, 2025". */
export function backtestList(meta) {
  const asOf = meta?.catch_run?.as_of;
  return asOf ? `the list drawn up the same way on ${fmtDate(asOf)}` : "the list drawn up the same way for the backtest";
}

const inHundred = (x) => Math.round(x * 100);
const likely = (iv) => (Array.isArray(iv) && iv.length === 2 && iv.every((v) => typeof v === "number")
  ? ` (likely ${inHundred(iv[0])} to ${inHundred(iv[1])})` : "");

/** Beside every band and estimate: what a band is, and what it is not. */
export const GROUP_NOTE = "A band is a statistic about a group of places, not a finding about any one of them.";

/**
 * The sentence beside every band, in natural frequencies with its likely range: "In the backtest,
 * band 1 places had a major violation at their next routine inspection at about 1.7 times the rate
 * of all scored restaurants: about 37 in 100 (likely 33 to 41), against 21 in 100." For a place
 * outside the City, the rates measured outside the City.
 */
export function bandSummary(meta, band, { outside = false } = {}) {
  const d = bandRow(meta, band, outside);
  if (!d || typeof d.rate !== "number") return `Band ${band} has no backtest rate in this export.`;
  const where = outside ? " outside the City" : "";
  const c = comparison(meta, outside);
  const ratio = rateRatio(meta, band, { outside });
  if (!c || ratio == null) {
    return `In the backtest, about ${inHundred(d.rate)} in 100 band ${d.band} places${where} had a major violation at their next routine inspection${likely(d.interval)}.`;
  }
  return `In the backtest, band ${d.band} places${where} had a major violation at their next routine inspection at about ${ratio} times the rate of ${c.who}: about ${inHundred(d.rate)} in 100${likely(d.interval)}, against ${inHundred(c.rate)} in 100.`;
}

/**
 * What a place's points say as a rate, from its place file's `estimate` or read from the export's
 * curve: "Scored restaurants with about 12 points: about 39 in 100 had a major violation at their
 * next routine inspection in the backtest (likely 35 to 41)." Null without points or a curve.
 */
export function estimateSentence(meta, points, { estimate = null, outside = false } = {}) {
  if (typeof points !== "number") return null;
  let e = estimate;
  if (!e) {
    const curve = outside ? outsideOf(meta)?.curve : meta?.card?.curve;
    if (!Array.isArray(curve?.rate) || !curve.rate.length) return null;
    const j = Math.min(Math.max(Math.round(points), 0), curve.rate.length - 1);
    e = { rate: curve.rate[j], low: curve.low?.[j], high: curve.high?.[j] };
  }
  if (typeof e?.rate !== "number") return null;
  const where = outside ? " outside the City" : "";
  return `Scored restaurants${where} with about ${points} points: about ${inHundred(e.rate)} in 100 had a major violation at their next routine inspection in the backtest${likely([e.low, e.high])}.`;
}

/**
 * The comparison that keeps the rule honest: ranking by recent major violations, which the County's
 * record already shows, does about as well. Null when the export has no same-size comparison.
 */
export function persistenceSentence(meta, band = "1") {
  const d = bandDef(meta, band);
  if (typeof d?.baseline_rate !== "number") return null;
  const vs = d.vs_baseline;                      // 95% interval for (band's majors) - (the same-size group's)
  const group = `Sorting the same restaurants by their recent major violations, which the County's record already shows, picks out a group of the same size`;
  if (Array.isArray(vs) && typeof vs[0] === "number" && vs[0] > 0) {
    return `${group} whose rate was lower (about ${inHundred(d.baseline_rate)} in 100): band ${d.band} found more of the places that went on to have a major.`;
  }
  return `${group} with a similar rate (about ${inHundred(d.baseline_rate)} in 100). The points are a transparent summary of that record, not a better predictor.`;
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
