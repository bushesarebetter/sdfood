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
 * (`meta.card.base_rate`), and with the share that had none. Every scored place
 * also gets an estimate read from a monotone (isotonic) fit of rate by points
 * (`meta.card.curve`; for a place whose two years include a routine inspection
 * that ended in a closure, `meta.card.curve_closure`, and the estimate says
 * so), dated to the backtest it comes from. Places outside the
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

/**
 * The places below the bands against the comparison rate, to one decimal: their rate over the rate
 * for all scored restaurants when the export has it, or 1 when they are the comparison. Null
 * without a rate for them.
 */
export function restRatio(meta) {
  const r = restRate(meta);
  if (r == null) return null;
  const base = meta?.card?.base_rate;
  if (typeof base === "number") return base > 0 ? Math.round((r / base) * 10) / 10 : null;
  return 1;
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
const pair = (iv) => Array.isArray(iv) && iv.length === 2 && iv.every((v) => typeof v === "number");
const likely = (iv) => (pair(iv) ? ` (likely ${inHundred(iv[0])} to ${inHundred(iv[1])})` : "");
/** Whether a 95% interval includes zero. */
const spansZero = (iv) => pair(iv) && iv[0] <= 0 && iv[1] >= 0;

/** Beside every band and estimate: what a band is, and what it is not. */
export const GROUP_NOTE = "A band describes what happened to a group of places; it is not a finding that this place has, or will have, a violation.";

/** Added to a band's line when its difference from the same-size persistence group spans zero. */
export const SAME_AS_PERSISTENCE = "Sorting by recent major violations alone picks out a group with the same rate.";

/** Added to an estimate when the export's drift check says the rates should be measured again. */
export const DRIFT_NOTE = "The County's record has changed since these rates were measured.";

/**
 * On the About page when the export's drift check has no complete quarter after the backtest year to
 * compare (`status` "not_yet_measurable"). It speaks of the formal check only, so the latest quarter's
 * note that follows it ("Meanwhile, ...") does not contradict it. driftNotYet adds the dates.
 */
export const DRIFT_NOT_YET =
  "Drift: the formal check compares complete quarters after the backtest year, each counted 30 days after it ends, and none is complete yet.";

const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const isoDay = (d) => d.toISOString().slice(0, 10);

/**
 * DRIFT_NOT_YET with its dates, from the backtest's label window (`meta.catch_run.label_window`,
 * "2025-09-01 to 2026-08-31"): the first quarter that starts after it, and the day it can be counted,
 * 30 days after it ends, as the export's drift check does. "Drift: the formal check compares complete
 * quarters after the backtest year, each counted 30 days after it ends; the first is October to
 * December 2026, counted from January 30, 2027." DRIFT_NOT_YET itself without a label window.
 */
export function driftNotYet(meta) {
  const end = /to (\d{4}-\d{2}-\d{2})\s*$/.exec(String(meta?.catch_run?.label_window ?? ""))?.[1];
  const e = end ? new Date(`${end}T00:00:00Z`) : null;
  if (!e || Number.isNaN(e.getTime())) return DRIFT_NOT_YET;
  let y = e.getUTCFullYear(), q = Math.floor(e.getUTCMonth() / 3) + 1;       // the quarter after the one holding the end
  if (++q > 4) { q = 1; y += 1; }
  const first = 3 * (q - 1);
  const qEnd = new Date(Date.UTC(y, first + 3, 0));
  const countable = new Date(qEnd.getTime() + 30 * 864e5);
  return "Drift: the formal check compares complete quarters after the backtest year, each counted 30 days after it ends; " +
    `the first is ${MONTH_NAMES[first]} to ${MONTH_NAMES[first + 2]} ${y}, counted from ${fmtDate(isoDay(countable))}.`;
}

/** Who an estimate describes when it is read from the curve for places with a closure in their two years. */
export const CLOSURE_GROUP = "whose last two years include a routine inspection that ended in a closure";

/** A place outside the City is described by the rates measured outside it, when the export has them. */
export const isOutside = (p, meta) => p?.council_district == null && Boolean(meta?.card?.outside);

/** The bands the district figures cover (`meta.fairness.bands_used`), or band 1. */
function auditedBands(meta) {
  const b = meta?.fairness?.bands_used;
  return Array.isArray(b) && b.length ? b.map(String).sort((x, y) => Number(x) - Number(y)) : ["1"];
}

/** "1", "1 and 2", "1 to 3". */
function bandList(list) {
  if (list.length === 1) return list[0];
  const run = list.every((b, i) => i === 0 || Number(b) === Number(list[i - 1]) + 1);
  if (run && list.length > 2) return `${list[0]} to ${list.at(-1)}`;
  return `${list.slice(0, -1).join(", ")} and ${list.at(-1)}`;
}

/** "band 1 places", "places in bands 1 and 2", "places in bands 1 to 3". */
function bandGroup(list) {
  return list.length === 1 ? `band ${list[0]} places` : `places in bands ${bandList(list)}`;
}

/** The places the district figures cover, as in bandGroup: "band 1 places" unless the export says otherwise. */
export const auditedGroup = (meta) => bandGroup(auditedBands(meta));

/** The bands the district figures cover, as a name: "Band 1", "Bands 1 to 3". */
export function auditedBandsName(meta) {
  const used = auditedBands(meta);
  return `Band${used.length > 1 ? "s" : ""} ${bandList(used)}`;
}

/**
 * What a district's places in the audited bands did in the backtest: "about 29 in 100 (likely 20 to
 * 39)", from `meta.fairness.by_district[d].precision` and `precision_interval`; null without one.
 */
export function districtPrecision(meta, district) {
  if (district == null) return null;
  const f = meta?.fairness?.by_district?.[String(district)];
  if (typeof f?.precision !== "number") return null;
  return `about ${inHundred(f.precision)} in 100${likely(f.precision_interval)}`;
}

/**
 * "In council district 4, about 29 in 100 band 1 places had one." From `meta.fairness.by_district`,
 * for a City place in a band the district figures cover; null otherwise.
 */
export function districtSentence(meta, band, district) {
  if (district == null || band == null) return null;
  const used = auditedBands(meta);
  if (!used.includes(String(band))) return null;
  const f = meta?.fairness?.by_district?.[String(district)];
  if (typeof f?.precision !== "number") return null;
  return `In council district ${district}, about ${inHundred(f.precision)} in 100 ${bandGroup(used)} had one${likely(f.precision_interval)}.`;
}

/**
 * The sentence beside every band, in natural frequencies with its likely range and the share that
 * had none: "In the backtest, about 37 in 100 band 1 places had a major violation at their next
 * routine inspection (likely 33 to 41), against 21 in 100 of all scored restaurants; about 63 in
 * 100 had none." Then, when the same-size group picked by recent major violations did as well
 * (its `vs_baseline` interval spans zero), SAME_AS_PERSISTENCE; and for a City place with a council
 * district, what the band's places there did. For a place outside the City, the rates measured
 * outside the City, with SAME_AS_PERSISTENCE on the same test of the outside band's own
 * `vs_baseline` (an older export's outside bands have none, and say nothing about it).
 */
export function bandSummary(meta, band, { outside = false, district = null } = {}) {
  const d = bandRow(meta, band, outside);
  if (!d || typeof d.rate !== "number") return `Band ${band} has no backtest rate in this export.`;
  const where = outside ? " outside the City" : "";
  const c = comparison(meta, outside);
  const n = inHundred(d.rate);
  const against = c ? `, against ${inHundred(c.rate)} in 100 of ${c.who}` : "";
  const out = [`In the backtest, about ${n} in 100 band ${d.band} places${where} had a major violation at their next routine inspection${likely(d.interval)}${against}; about ${100 - n} in 100 had none.`];
  if (spansZero(d.vs_baseline)) out.push(SAME_AS_PERSISTENCE);
  const byDistrict = outside ? null : districtSentence(meta, d.band, district);
  if (byDistrict) out.push(byDistrict);
  return out.join(" ");
}

/**
 * Which backtest the rates come from, by its list dates (`meta.card.by_origin`), else the dates in
 * `trained_on`, else the one backtest list: "the backtest of lists drawn up from March 1, 2025 to
 * September 1, 2025".
 */
export function backtestPeriod(meta) {
  const dates = [...new Set((meta?.card?.by_origin ?? [])
    .map((o) => o?.as_of).filter((x) => typeof x === "string" && /^\d{4}-\d{2}-\d{2}/.test(x)))].sort();
  if (dates.length > 1) return `the backtest of lists drawn up from ${fmtDate(dates[0])} to ${fmtDate(dates.at(-1))}`;
  if (dates.length === 1) return `the backtest of the list drawn up on ${fmtDate(dates[0])}`;
  const t = /(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})/.exec(String(meta?.card?.trained_on ?? meta?.catch_run?.trained_on ?? ""));
  if (t) return `the backtest over the record from ${fmtDate(t[1])} to ${fmtDate(t[2])}`;
  const asOf = meta?.catch_run?.as_of;
  return asOf ? `the backtest of the list drawn up on ${fmtDate(asOf)}` : "the backtest";
}

/**
 * The backtest list an estimate comes from: the curve is fitted at the confirmation origin only
 * (`meta.catch_run.as_of`, the first `by_origin` entry), not across every origin.
 */
export function estimatePeriod(meta) {
  const asOf = meta?.catch_run?.as_of ?? meta?.card?.by_origin?.[0]?.as_of;
  return typeof asOf === "string" && /^\d{4}-\d{2}-\d{2}/.test(asOf)
    ? `the backtest of the list drawn up on ${fmtDate(asOf)}` : backtestPeriod(meta);
}

/** The export's drift note (`meta.drift.note`), a neutral sentence on the latest quarter, or null. */
export function driftNote(meta) {
  const n = meta?.drift?.note;
  return typeof n === "string" && n.trim() ? n.trim() : null;
}

/**
 * The curve an estimate is read from: for a place in the closure group (`estimate.group` "closure")
 * `curve_closure`, otherwise `curve`; for a place outside the City, the curves measured outside it.
 */
export function curveFor(meta, { group = null, outside = false } = {}) {
  const o = outside ? outsideOf(meta) : meta?.card;
  return (group === "closure" && o?.curve_closure) || o?.curve || null;
}

const isRange = (g) => Array.isArray(g) && g.length === 2 && g.every(Number.isInteger) && g[0] <= g[1];

/** A curve's fitted groups (`groups`, [lo, hi] point ranges), low to high; null for a curve without them. */
export function curveGroups(curve) {
  const g = curve?.groups;
  return Array.isArray(g) && g.length && g.every(isRange) ? [...g].sort((a, b) => a[0] - b[0]) : null;
}

/**
 * The fitted group a place's points are read from, as the export reads them: `{lo, hi, where}`, where
 * is "in" (its points are in the group), "above" (more points than any place in the backtest: read at
 * the top group), "below" (read at the lowest group) or "between" (a value no backtest place had, read
 * at the group below). Null without groups or points.
 */
export function curveGroupFor(curve, points) {
  const groups = curveGroups(curve);
  if (!groups || typeof points !== "number" || !Number.isFinite(points)) return null;
  const p = Math.round(points);
  const hit = groups.find(([lo, hi]) => lo <= p && p <= hi);
  if (hit) return { lo: hit[0], hi: hit[1], where: "in" };
  if (p < groups[0][0]) return { lo: groups[0][0], hi: groups[0][1], where: "below" };
  const under = groups.filter(([, hi]) => hi < p).at(-1);
  return { lo: under[0], hi: under[1], where: p > groups.at(-1)[1] ? "above" : "between" };
}

/** "7 points", "1 point", "7 to 25 points". */
const pointsRange = (lo, hi) => (lo === hi ? `${lo} ${lo === 1 ? "point" : "points"}` : `${lo} to ${hi} points`);

/**
 * Who an estimate describes, by points: the fitted group the place is read from (the place file's
 * `estimate.min_points`/`max_points` when it has them, else the curve's `groups`), since every place
 * in a group is given the group's rate; "about N points" for an older export's curve without groups.
 */
function pointsPhrase(meta, points, e, outside) {
  const own = Number.isInteger(e?.min_points) && Number.isInteger(e?.max_points) && e.min_points <= e.max_points;
  const g = own ? { lo: e.min_points, hi: e.max_points, where: points >= e.min_points && points <= e.max_points ? "in" : "out" }
    : curveGroupFor(curveFor(meta, { group: e?.group ?? null, outside }), points);
  if (!g) return `with about ${points} points`;
  const range = pointsRange(g.lo, g.hi);
  return g.where === "in" ? `with ${range}` : `with ${range} (the group this place's ${points} ${points === 1 ? "point is" : "points are"} read from)`;
}

/**
 * What a place's points say as a rate, from its place file's `estimate` or read from the export's
 * curve, dated to the backtest list it comes from, and naming the group of points it is read from
 * (every place in a fitted group gets the group's rate): "Scored restaurants with 8 to 16 points:
 * about 40 in 100 had a major violation at their next routine inspection in the backtest of the list
 * drawn up on September 1, 2025 (likely 36 to 45). The likely range reflects sampling only, not
 * changes since then." An estimate the export read from the curve for places with a closure in their
 * two years (`estimate.group` "closure", `meta.card.curve_closure`) says so (CLOSURE_GROUP). Then
 * DRIFT_NOTE when the export's drift check asks for a refit, and the export's drift note when it has
 * one. Without a place estimate the site reads `curve`. Null without points or a curve.
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
  const who = e.group === "closure" ? ` ${CLOSURE_GROUP}` : "";
  const range = likely([e.low, e.high]);
  const out = [`Scored restaurants${where} ${pointsPhrase(meta, points, e, outside)}${who}: about ${inHundred(e.rate)} in 100 had a major violation at their next routine inspection in ${estimatePeriod(meta)}${range}.`];
  if (range) out.push("The likely range reflects sampling only, not changes since then.");
  if (meta?.drift?.refit_needed === true) out.push(DRIFT_NOTE);
  const note = driftNote(meta);
  if (note) out.push(note);
  return out.join(" ");
}

/**
 * The comparison that keeps the rule honest: ranking by recent major violations, which the County's
 * record already shows, does about as well. For a place outside the City, the outside band's own
 * comparison. Null when the export has no same-size comparison.
 */
export function persistenceSentence(meta, band = "1", { outside = false } = {}) {
  const d = bandRow(meta, band, outside);
  if (typeof d?.baseline_rate !== "number") return null;
  const vs = d.vs_baseline;                      // 95% interval for (band's majors) - (the same-size group's)
  const group = `Sorting the same restaurants${outside ? " outside the City" : ""} by their recent major violations, which the County's record already shows, picks out a group of the same size`;
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

/** The score the rule counts for a routine inspection that ended in a closure order. */
export const CLOSURE_SCORE = 70;

/**
 * One score the average reads (`scores_used`, `{date, score, closure, county_score}`), as text:
 * "February 1, 2025: 95", or for a closure, what the County recorded and what the rule counts.
 * An older export's entry without `county_score` says only that the rule counts the closure as 70.
 */
export function scoreUsedText(u) {
  const date = fmtDate(u?.date);
  if (!u?.closure) return `${date}: ${u?.score}`;
  if (u.county_score === null) return `${date}: closed, no County score; this rule counts it as ${CLOSURE_SCORE}`;
  if (typeof u.county_score === "number") return `${date}: closed (the County's score that day: ${u.county_score}); this rule counts a closure as ${CLOSURE_SCORE}`;
  return `${date}: closed; this rule counts a closure as ${CLOSURE_SCORE}`;
}

/** The scores the average reads, as lines, and their mean to one decimal (a closure counted as 70); or null. */
export function scoresRead(used) {
  if (!Array.isArray(used) || !used.length) return null;
  const values = used.map((u) => (u?.closure ? CLOSURE_SCORE : u?.score));
  if (!values.every((v) => typeof v === "number" && Number.isFinite(v))) return null;
  const mean = values.reduce((a, v) => a + v, 0) / values.length;
  return { lines: used.map(scoreUsedText), mean: Math.round(mean * 10) / 10 };
}

/**
 * The cost-ratio table (`meta.utility`): for each cost ratio C/B, the bar C/(B+C) a band's interval
 * must clear at its low end to be named, and the bands that clear it. Null when the export has none.
 */
export function utilityRows(meta) {
  const u = meta?.utility;
  if (!Array.isArray(u)) return null;
  const rows = u
    .filter((r) => typeof r?.cost_ratio === "number" && typeof r?.bar === "number")
    .map((r) => ({ cost_ratio: r.cost_ratio, bar: r.bar, named: Array.isArray(r.named) ? r.named.map(String) : [] }));
  return rows.length ? rows : null;
}

/**
 * The largest cost ratio C/B at which the first band's low end clears the bar C/(B+C): with C/B = r
 * the bar is r/(1+r), so the low end clears it exactly when r < low/(1-low). `{band, low, ratio}`,
 * the ratio to two decimals; null without a low end between 0 and 1.
 */
export function costLimit(meta) {
  const d = bandDefs(meta)[0];
  const low = d?.interval?.[0];
  if (typeof low !== "number" || !(low > 0 && low < 1)) return null;
  return { band: d.band, low, ratio: Math.round((low / (1 - low)) * 100) / 100 };
}

/**
 * "Band 1's interval starts at 33%, so its low end clears C/(B+C) only when a wrong flag costs less
 * than 0.49 times what a right one is worth (a cost ratio C/B below 0.49)." Or null.
 */
export function costLimitSentence(meta) {
  const c = costLimit(meta);
  if (!c) return null;
  return `Band ${c.band}'s interval starts at ${pct(c.low)}, so its low end clears C/(B+C) only when a wrong flag costs less than ${c.ratio} times what a right one is worth (a cost ratio C/B below ${c.ratio}).`;
}

/** "Rule version 2026-09-20-abcd, frozen September 20, 2026.", or null. */
export function frozenLine(meta) {
  const f = meta?.frozen;
  if (!f || typeof f !== "object" || !f.version) return null;
  return `Rule version ${f.version}${f.frozen_on ? `, frozen ${fmtDate(f.frozen_on)}` : ""}.`;
}

/** When the export's drift check asks for a refit: DRIFT_NOTE with its reasons; otherwise null. */
export function driftLine(meta) {
  const d = meta?.drift;
  if (!d || d.refit_needed !== true) return null;
  const reasons = (Array.isArray(d.reasons) ? d.reasons : []).filter((r) => typeof r === "string" && r.trim());
  return reasons.length ? `${DRIFT_NOTE.replace(/\.$/, "")}: ${reasons.join("; ")}.` : DRIFT_NOTE;
}

/**
 * What the About page says about drift, in order: driftNotYet when the drift check has no complete
 * quarter after the backtest year (`status` "not_yet_measurable"), driftLine when it asks for a refit,
 * and the export's drift note when it has one, after the first as what can be said meanwhile ("Meanwhile,
 * in the latest quarter ..."), so the two never read as a contradiction. Empty when there is nothing to say.
 */
export function driftLines(meta) {
  const out = [];
  const notYet = meta?.drift?.status === "not_yet_measurable";
  if (notYet) out.push(driftNotYet(meta));
  const refit = driftLine(meta);
  if (refit) out.push(refit);
  const note = driftNote(meta);
  if (note) out.push(notYet ? `Meanwhile, ${note.charAt(0).toLowerCase()}${note.slice(1)}` : note);
  return out;
}

/**
 * One row per fitted group of an estimate curve, as places are told it (What the points say, on the
 * About page): `{lo, hi, labelled, positives, rate, low, high}`. The rate and its range are the
 * curve's at the group's lowest points, which every place in the group reads. The counts come from
 * the export's `group_counts` when it has them, else from the finer `bins` when every bin that touches
 * the group lies wholly inside it; otherwise they are null. Null for a curve without `groups`.
 */
export function curveGroupRows(curve) {
  const groups = curveGroups(curve);
  if (!groups) return null;
  const at = (arr, j) => (Array.isArray(arr) && arr.length ? arr[Math.min(j, arr.length - 1)] : null);
  const num = (x) => (typeof x === "number" ? x : null);
  const bins = (Array.isArray(curve.bins) ? curve.bins : []).filter((b) => Number.isInteger(b?.min_points) && Number.isInteger(b?.max_points));
  const counted = Array.isArray(curve.group_counts) ? curve.group_counts : [];
  return groups.map(([lo, hi]) => {
    const own = counted.find((c) => c?.min_points === lo && c?.max_points === hi);
    let labelled = num(own?.labelled), positives = num(own?.positives);
    if (labelled == null || positives == null) {
      const touching = bins.filter((b) => b.min_points <= hi && b.max_points >= lo);
      const inside = touching.length > 0 && touching.every((b) => b.min_points >= lo && b.max_points <= hi && typeof b.labelled === "number" && typeof b.positives === "number");
      labelled = inside ? touching.reduce((s, b) => s + b.labelled, 0) : null;
      positives = inside ? touching.reduce((s, b) => s + b.positives, 0) : null;
    }
    return { lo, hi, labelled, positives, rate: num(at(curve.rate, lo)), low: num(at(curve.low, lo)), high: num(at(curve.high, lo)) };
  });
}

/**
 * Where the finer counts inside one fitted group differ, the lowest and highest of them:
 * `[{lo, hi, min: bin, max: bin}]` for each group holding two or more whole `bins` whose rates differ.
 * Empty without groups or bins.
 */
export function curveGroupSpread(curve) {
  const groups = curveGroups(curve) ?? [];
  const bins = (Array.isArray(curve?.bins) ? curve.bins : []).filter((b) => Number.isInteger(b?.min_points) && Number.isInteger(b?.max_points) && typeof b?.rate === "number");
  const out = [];
  for (const [lo, hi] of groups) {
    const inside = bins.filter((b) => b.min_points >= lo && b.max_points <= hi);
    if (inside.length < 2) continue;
    const min = inside.reduce((a, b) => (b.rate < a.rate ? b : a));
    const max = inside.reduce((a, b) => (b.rate > a.rate ? b : a));
    if (inHundred(min.rate) !== inHundred(max.rate)) out.push({ lo, hi, min, max });
  }
  return out;
}

/** "7 to 10 points", "11 points": a bin's or a group's points, for a sentence. */
export const pointsSpan = pointsRange;

/**
 * Band 1's backtest rate by how its places got there (`meta.card.band_1_by_route`): through a
 * closure counted as 70, or on routine scores alone. Takes an object keyed by route or a list of
 * `{route, rate, interval}`; null when neither route has a rate.
 */
export function band1ByRoute(meta) {
  const r = meta?.card?.band_1_by_route;
  if (!r || typeof r !== "object") return null;
  const entries = Array.isArray(r) ? r.map((x) => [String(x?.route ?? x?.key ?? x?.name ?? ""), x]) : Object.entries(r);
  const withRate = entries.filter(([, v]) => typeof v?.rate === "number");
  const scoresKey = (k) => /score|routine|alone|without|no_?closure|other/i.test(k);
  const closure = withRate.find(([k]) => /closure|closed|70/i.test(k) && !scoresKey(k))?.[1] ?? null;
  const scores = withRate.find(([k]) => scoresKey(k))?.[1] ?? null;
  return closure || scores ? { closure, scores } : null;
}

/** Band 1's rate by route, in one sentence, or null. */
export function routeSentence(meta) {
  const r = band1ByRoute(meta);
  if (!r) return null;
  const { closure: c, scores: s } = r;
  const next = "had a major violation at their next routine inspection";
  if (c && s) {
    return `In the backtest, about ${inHundred(c.rate)} in 100 band 1 places that were in it because of a closure counted as ${CLOSURE_SCORE} ${next}${likely(c.interval)}, against about ${inHundred(s.rate)} in 100 of those in it on routine scores alone${likely(s.interval)}.`;
  }
  if (c) return `In the backtest, about ${inHundred(c.rate)} in 100 band 1 places that were in it because of a closure counted as ${CLOSURE_SCORE} ${next}${likely(c.interval)}.`;
  return `In the backtest, about ${inHundred(s.rate)} in 100 band 1 places that were in it on routine scores alone ${next}${likely(s.interval)}.`;
}
