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
