// The shape export_site.py writes for contract v3.1, trimmed: shares are cumulative.
export const bandsMeta = {
  mode: "bands",
  catch_run: { as_of: "2025-09-01", baseline_name: "average score" },
  card: {
    rule: "Places are ordered by how far their average routine score in the last year fell below 100.",
    items: [{ item: "avg_deficit", label: "Points below 100, average routine score in the last year", weight: 1, unit: "per point below 100", feature: "avg_deficit" }],
    baseline_name: "persistence",
    eligibility: "restaurants with a scored routine inspection in the year before the list date",
    bands: [
      { band: "1", min_points: 20, max_points: null, share: 0.025, places_now: 128, labelled: 119, positives: 65, rate: 0.5462, interval: [0.4567, 0.6328], baseline_rate: 0.52, vs_baseline: [-4, 9], kept_in_refits: 0.92 },
      { band: "2", min_points: 16, max_points: 19, share: 0.075, places_now: 257, labelled: 226, positives: 74, rate: 0.3274, interval: [0.2696, 0.3911], baseline_rate: null, vs_baseline: null },
      { band: "3", min_points: 12, max_points: 15, share: 0.175, places_now: 514, labelled: 448, positives: 135, rate: 0.3013, interval: [0.2607, 0.3454] },
    ],
    rest: { band: "rest", labelled: 3794, positives: 609, rate: 0.1605, interval: [0.1492, 0.1725] },
  },
  grade_context: { majors_graded_A_share: 0.942, graded_A_share: 0.9928 },
};

// The staff copy's shape with the figures the band's backtest gave: band 1 (8+ points) at about
// 37 in 100 against 21 in 100 for all scored restaurants, the same rate as the same-size group picked
// by recent major violations, and the fields a frozen rule's export adds.
export const staffMeta = {
  mode: "bands",
  audience: "staff",
  inspections_through: "2026-09-19",
  catch_run: { as_of: "2025-09-01" },
  card: {
    rule: "Places get 100 minus their rounded average routine score over two years, a health closure counted as 70.",
    trained_on: "2023-07-01 to 2025-09-01 (27 monthly snapshots, 41,000 labelled rows, county-wide restaurants)",
    base_rate: 0.21,
    bands: [
      { band: "1", min_points: 8, max_points: null, share: 0.1, places_now: 180, labelled: 560, positives: 207, rate: 0.37, interval: [0.33, 0.41], baseline_rate: 0.37, vs_baseline: [-3.1, 2.9] },
    ],
    rest: { band: "rest", labelled: 5000, positives: 900, rate: 0.18, interval: [0.17, 0.19] },
    by_origin: [
      { as_of: "2025-09-01", 1: { rate: 0.36 } },
      { as_of: "2025-03-01", 1: { rate: 0.38 } },
      { as_of: "2025-06-01", 1: { rate: 0.37 } },
    ],
    curve: { rate: [0.1, 0.15, 0.2, 0.25, 0.3, 0.32, 0.34, 0.36, 0.39], low: [0.08, 0.13, 0.18, 0.22, 0.27, 0.29, 0.31, 0.33, 0.35], high: [0.12, 0.17, 0.22, 0.28, 0.33, 0.35, 0.37, 0.39, 0.43] },
    band_1_by_route: {
      closure: { labelled: 60, positives: 27, rate: 0.45, interval: [0.33, 0.58] },
      scores: { labelled: 500, positives: 180, rate: 0.36, interval: [0.32, 0.4] },
    },
  },
  fairness: {
    bands_used: ["1"],
    by_district: {
      4: { named: 30, precision: 0.29, precision_interval: [0.2, 0.39], false_share_ratio: 1.9, interval: [1.2, 2.6] },
      2: { named: 25, precision: 0.41 },
    },
  },
  cost_ratio: null,
  utility: [
    { cost_ratio: 0.25, bar: 0.2, named: [] },
    { cost_ratio: 1, bar: 0.5, named: [] },
  ],
  frozen: { version: "2026-09-20-abcd1234", frozen_on: "2026-09-20", from_run: "forward_2026-09-20-abcd1234" },
  drift: { refit_needed: true, reasons: ["routine major rate 27.0% in the last full quarters against 21.0% in the backtest"] },
};
