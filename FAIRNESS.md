# Fairness / disparate-impact analysis

An enforcement-targeting ordering has to answer: **does it send inspectors disproportionately to
lower-income or immigrant neighborhoods, and does it protect every neighborhood equally?** This
is the check. Reproduce with `python fairness_check.py` (needs `data/` from `fetch_sdfood.py`).
Numbers are from the rerun of 2026-09-26 on the 2026-09-19 pull: history since 2023-01, no ZIP
code, no permit age (see README, "What changed"), scored as of the 1st of each inspection's month,
as the monthly list is.

## Method

- Out-of-fold predictions (train ≤ 2024, test 2025+, 32,548 routine inspections the model never saw).
- Each facility joined to its ZIP's **median household income** and **% Hispanic** ([ACS](https://www.census.gov/programs-surveys/acs)
  5-yr via [Census Reporter](https://censusreporter.org): tables [B19013](https://censusreporter.org/tables/B19013/)
  income, [B03002](https://censusreporter.org/tables/B03002/) ethnicity; 99.8% of test inspections
  covered, 97/109 ZIPs matched).
- **Whole ZIPs per group:** income quartiles and %-Hispanic terciles are cut so that each ZIP sits
  in one group, with about equal inspection counts per group.
- Four orderings of the same inspections, each flagging its top 20% county-wide (ties split pro rata):
  - the **research model** (no ZIP);
  - the same model **with ZIP**, to see whether ZIP carries a gap;
  - the **one-line rule**: lowest mean routine score on record first;
  - **persistence**: routine inspections with a major in the prior 12 months, then majors, then
    the lowest last routine score over two years.
- For each: the **flag rate** against the **actual** major-violation rate (is targeting driven by
  real risk?), the **false-positive rate** (the share of each group's clean inspections flagged),
  **calibration** (predicted against actual rate within each group), **equal opportunity** (the
  share of each group's major violations in the top 20%, "recall"), and **days sooner** by group
  under the policy actually proposed: reordering each council district's (or ZIP3 area's) month.
- **95% intervals resample whole ZIPs** (a ZIP-clustered bootstrap), so they reflect how few ZIPs
  each group holds. If an interval covers equality (0 for a gap, 1 for a ratio), the data cannot
  tell the groups apart.
- Every test inspection is at a facility that still exists: SD Food Info lists only those
  (README, "Survivorship"). The figures describe coverage among surviving facilities.

## Results

By ZIP median income (Q1 = lowest), research model:

| group | ZIPs | n | actual major % | flag % | predicted % | recall % (95% CI) | false-positive rate % (95% CI) | days sooner (95% CI) |
|---|---|---|---|---|---|---|---|---|
| Q1 low | 25 | 8,380 | 12.3 | 19.5 | 13.3 | 51.2 (44.6–58.1) | 15.0 (11.6–18.6) | +6.8 (5.7–7.8) |
| Q2 | 16 | 7,936 | 13.0 | 21.4 | 14.1 | 51.2 (44.0–59.5) | 16.9 (14.5–19.5) | +6.5 (5.1–8.3) |
| Q3 | 26 | 8,262 | 12.3 | 18.8 | 13.5 | 46.7 (41.3–51.8) | 14.9 (12.2–17.7) | +6.0 (5.2–6.9) |
| Q4 high | 30 | 7,915 | 12.9 | 20.4 | 13.8 | 49.4 (44.7–53.2) | 16.1 (14.1–17.9) | +6.3 (5.4–7.3) |

The other orderings, same groups:

| group | rule flag % | rule recall % (95% CI) | rule false-positive % | rule days sooner | persistence recall % | model with ZIP: recall % |
|---|---|---|---|---|---|---|
| Q1 low | 21.0 | 51.6 (44.7–58.6) | 16.7 (13.5–20.4) | +6.2 (4.9–7.3) | 49.4 | 41.4 |
| Q2 | 21.3 | 49.3 (41.9–57.8) | 17.1 (14.1–21.3) | +6.0 (4.7–7.5) | 49.3 | 48.7 |
| Q3 | 18.3 | 43.6 (37.5–48.7) | 14.8 (12.0–17.5) | +5.2 (4.3–6.3) | 41.6 | 44.2 |
| Q4 high | 19.4 | 47.0 (41.6–51.7) | 15.3 (13.3–17.3) | +5.7 (4.7–6.7) | 44.0 | 55.4 |

Lowest against highest income quartile:

| | recall gap, Q1 minus Q4 (95% CI) | flag rate, Q1 ÷ Q4 (95% CI) |
|---|---|---|
| Research model | +1.8 points (−6.2 to +10.1) | 0.96× (0.74–1.22) |
| One-line rule | +4.6 (−4.1 to +13.5) | 1.08× (0.84–1.38) |
| Persistence | +5.4 (−2.9 to +14.2) | 1.03× (0.83–1.29) |
| Model with ZIP (not used) | −14.0 (−32.2 to +5.0) | 0.61× (0.30–1.06) |
| Actual major-violation rate | | 0.95× (0.76–1.19) |

By ZIP % Hispanic (low to high tercile): actual rates 14.0%, 12.4%, 11.6% (lowest ÷ highest
1.21×, 1.01–1.44); model flag rate 21.6%, 19.3%, 19.1% (1.13×, 0.92–1.36); recall 49.7%, 48.0%,
51.3% for the model (gap −1.6 points, −8.3 to +4.7), 45.9%, 47.1%, 50.9% for the one-line rule
(−5.0, −12.1 to +1.9) and 43.5%, 46.0%, 49.3% for persistence (−5.8, −12.8 to +1.0). The model with
ZIP: 55.9%, 44.9%, 39.8% (+16.1, +1.4 to +30.2). Days sooner under the within-district reordering:
model +6.2, +6.6, +6.5; rule +5.4, +6.1, +5.8, with overlapping intervals.

## What it means

Each income quartile holds 16 to 30 ZIPs, and ZIPs differ from one another for reasons that have
nothing to do with income, so the intervals are wide: most can't rule out gaps of 5 to 10 points
either way. "No detectable difference" below means exactly that, not that coverage is even.

1. **Flag rates and actual rates.** Actual major-violation rates are nearly flat across income
   (lowest quartile 0.95× the highest), and so are the flag rates: the model flags low-income ZIPs
   at **0.96×** the rate of high-income ZIPs, the one-line rule at **1.08×**, persistence at
   **1.03×**. Every interval covers 1: no detectable difference. Per group, the rule flags the
   lowest-income quartile at 1.71× its actual rate against 1.50× for the highest, and its
   false-positive rate there is 16.7% against 15.3%. The per-group intervals overlap, and the
   audit does not estimate that difference itself. By %-Hispanic tercile the *actual* rate does
   differ detectably (1.21× higher in the lowest-%-Hispanic ZIPs), and the model's flag rate
   follows it (1.13×, interval covering 1).
2. **Calibration, in the large only.** The model's predicted rate sits 0.9 to 1.2 points above the
   actual rate in every income quartile, 7–10% relative: the same offset everywhere, and no group
   scored below its real rate. Group means are not calibration within groups; the plot shows only
   the means.
3. **Coverage.** Under a single top-20% cut, the model finds **47% to 51%** of each income
   quartile's major violations, the one-line rule **44% to 52%** and persistence **42% to 49%**. By
   %-Hispanic tercile the model covers 48% to 51%, the rule 46% to 51% and persistence 44% to 49%.
   Every lowest-minus-highest gap for these three covers 0: no detectable difference.
4. **Days sooner by group.** Under the proposed within-district reordering, major violations
   surface 6.0 to 6.8 days sooner across income quartiles with the model and 5.2 to 6.2 with the
   rule, with overlapping intervals: no group is left behind that the data can see.
5. **Why the model has no ZIP.** With ZIP as a feature the model ranks slightly worse (AUC −0.006,
   −0.011 to −0.002; README) and it covers the lowest-%-Hispanic ZIPs' major violations at 56%
   against 40% for the highest: a gap of +16.1 points (+1.4 to +30.2), the only coverage gap in this
   audit the data can detect. By income its gap (−14.0 points, 41% against 55%) is large but its
   interval covers 0. The research model, like the public site's point card, uses no ZIP code.
6. **Safeguards that stay:** keep routine inspections everywhere, so the ordering reprioritizes
   within the schedule and never zeroes out an area, and monitor coverage by group once it is in
   use (the pilot's monitoring rule is in docs/PILOT.md).

## Equalizing coverage exactly (`threshold_tradeoff.py`)

(The per-group cuts below are set on the test set's own labels, so the 20.9% budget is an
**in-sample** figure: what equalizing would have cost had the labels been known.)

The recall figures above are at a *single global* top-20% cut. A global threshold can't equalize
recall across groups with different score distributions — only per-group thresholds
([equal-opportunity](https://arxiv.org/abs/1610.02413), Hardt et al. 2016) can. `threshold_tradeoff.py`
quantifies both. Targeting the best group's recall (51%) everywhere:

| income group | global (top-20%) recall | equal-opportunity recall (per-group cut) | flag rate, global → per-group |
|---|---|---|---|
| Q1 low | 51.2% | 51.0% | 19.5% → 19.3% |
| Q2 | 51.2% | 51.0% | 21.4% → 21.3% |
| Q3 | 46.7% | 51.0% | 18.8% → 21.7% |
| Q4 high | 49.4% | 51.0% | 20.4% → 21.2% |

Per-group cuts would move the total flag budget from 20.0% to 20.9% (in-sample), but they mean a
different decision rule per income group, keyed off a ZIP/income proxy: disparate *treatment*,
which a government enforcement program should avoid, to close gaps the data cannot tell from zero.
**Recommendation: one global order, a baseline of routine inspections everywhere, and coverage
monitored by group.** (The script also prints the global precision/recall trade: flagging 20%
gives the model 31% precision, 2.5× the base rate, and the rule 30%; flagging 50% reaches 83% of
major violations for the model, 78% for the rule and 77% for persistence.)

## Feedback loop

Because inspections generate the labels the model trains on, targeting could compound over time
([runaway feedback loops](https://arxiv.org/abs/1706.09847), Ensign et al. 2018).
The earlier version of `feedback_check.py` tested one round of "only label what we flagged" and
found coverage moving by at most a point. It could not have found more. It dropped only the
labels and kept every facility's full history, and it selected purely on the model's own
features. A skipped inspection also leaves no score, no "days since" and no majors on the record,
which is what the rule and persistence read too.

The script now deletes skipped inspections, and the follow-ups within 45 days they would have
triggered, from the record over four quarterly rounds of 2024. It rebuilds the model, the rule and
persistence from what is left and scores them on 2025+:

| AUC on 2025+ | A: every inspection kept | B: only the model's top 40% inspected | C: top 40% plus a random 15% of the rest (3 seeds) |
|---|---|---|---|
| Model | 0.763 | 0.757 | 0.756 |
| One-line rule | 0.736 | 0.722 | 0.725 |
| Persistence | 0.723 | 0.708 | 0.711 |

Arm B removes 9,440 routine inspections, and the mean time since a facility's last visit in 2025+
rises from 279 to 351 days. The model loses 0.006 AUC; the rule and persistence, which read the
same thinned record, lose 0.014 to 0.015. A random 15% (arm C) barely changes that. Recall by
income quartile moves by at most 3 points in any arm (model, A to B: 52/51/46/50% to
51/50/46/47%). Arms A and B are single deterministic runs, so none of these differences carries an
interval. This concerns an inspect-less policy; reordering within the schedule removes no
inspection. Coverage by group is still monitored in use.

## Limits

- Area-based (ZIP) income and ethnicity are a standard disparate-impact proxy, not the
  demographics of each facility's owner or customers, and cannot see within-ZIP differences.
- The model no longer reads ZIP, but business type and a facility's record can still correlate
  with neighborhood; that is why this audit reports outcomes by group rather than inputs.
- The data hold only surviving facilities, about 3.7 years of them.
- Any deployment should re-run this audit on the County's internal records, on a schedule.

Full source list (data, methods, fairness papers): [REFERENCES.md](REFERENCES.md).
