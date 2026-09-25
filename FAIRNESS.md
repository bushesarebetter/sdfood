# Fairness / disparate-impact analysis

An enforcement-targeting ordering has to answer: **does it send inspectors disproportionately to
lower-income or immigrant neighborhoods, and does it protect every neighborhood equally?** This
is the check. Reproduce with `python fairness_check.py` (needs `data/` from `fetch_sdfood.py`).
Numbers are from the September 2026 rerun: history since 2023-01, no ZIP code, no permit age
(see README, "What changed").

## Method

- Out-of-fold predictions (train ≤ 2024, test 2025+, 32,552 routine inspections the model never saw).
- Each facility joined to its ZIP's **median household income** and **% Hispanic** ([ACS](https://www.census.gov/programs-surveys/acs)
  5-yr via [Census Reporter](https://censusreporter.org): tables [B19013](https://censusreporter.org/tables/B19013/)
  income, [B03002](https://censusreporter.org/tables/B03002/) ethnicity; 99.8% of test inspections
  covered, 97/109 ZIPs matched).
- Grouped by income quartile and %-Hispanic tercile, four orderings of the same inspections,
  each flagging its top 20% (ties split pro rata):
  - the **research model** (no ZIP);
  - the same model **with ZIP**, to see whether ZIP carries a gap;
  - the **one-line rule**: lowest mean routine score on record first;
  - **persistence**: routine inspections with a major in the prior 12 months, then majors, then
    the lowest last routine score.
- For each: the **flag rate** against the **actual** major-violation rate (is targeting driven by
  real risk?), **calibration** (predicted against actual rate within each group), and **equal
  opportunity** (the share of each group's major violations in the top 20%, "recall").
- Every test inspection is at a facility that still exists: SD Food Info lists only those
  (README, "Survivorship"). The figures describe coverage among surviving facilities.

## Results

By ZIP median income (Q1 = lowest):

| group | n | actual major % | model flag % | model predicted % | model recall % | rule flag % | rule recall % | persistence recall % | model with ZIP: recall % |
|---|---|---|---|---|---|---|---|---|---|
| Q1 low | 8,383 | 12.3 | 19.5 | 14.0 | 50.5 | 20.5 | 51.2 | 42.7 | 41.3 |
| Q2 | 7,936 | 13.0 | 21.4 | 14.6 | 49.1 | 21.9 | 49.7 | 42.2 | 51.2 |
| Q3 | 8,263 | 12.3 | 18.9 | 14.0 | 45.0 | 18.5 | 44.9 | 39.5 | 44.4 |
| Q4 high | 7,915 | 12.9 | 20.2 | 14.4 | 47.0 | 19.2 | 47.6 | 41.7 | 57.1 |

By ZIP % Hispanic (low to high tercile): actual rates 14.0%, 12.4%, 11.5%; model flag rate 21.5%,
19.4%, 19.1%; recall 47.4%, 47.3%, 49.2% for the model, 46.9%, 48.3%, 50.3% for the one-line rule,
and 40.7%, 42.5%, 41.4% for persistence. The model with ZIP: 56.3%, 45.7%, 41.8%.

## What it means

1. **Targeting tracks real risk.** Actual major-violation rates are nearly flat across income
   (lowest quartile 0.95× the highest), and so are the flag rates: the model flags low-income
   ZIPs at **0.97×** the rate of high-income ZIPs, the one-line rule at **1.07×**, persistence at
   **0.96×**. Neither lower-income nor higher-Hispanic areas are over-targeted.
2. **Calibrated evenly.** The model's predicted rate sits 1.5 to 1.7 points above the actual rate
   in every income quartile: the same small offset everywhere, and no group is scored below its
   real rate (see `food_fairness.png`).
3. **Even protection.** Under a single top-20% cut, the model finds **45% to 51%** of each income
   quartile's major violations and the one-line rule **45% to 51%**, with the lowest-income
   quartile at the top of both ranges. By %-Hispanic tercile the model covers 47% to 49% and the
   rule 47% to 50%. Both cover every group more fully than persistence (40% to 43%).
4. **Why the model has no ZIP.** With ZIP as a feature the model was just as accurate (README),
   but it flagged low-income ZIPs at 0.62× the rate of high-income ones and covered **41% vs
   57%** of their major violations. Without ZIP the gap closes (50% vs 47%). The research model,
   like the public site's point card, now uses no ZIP code.
5. **Safeguards that stay:** keep routine inspections everywhere, so the ordering reprioritizes
   within the schedule and never zeroes out an area, and monitor coverage by group once it is in
   use (the pilot's monitoring rule is in docs/PILOT.md).

## Equalizing coverage exactly (`threshold_tradeoff.py`)

The recall gap above is at a *single global* top-20% cut. A global threshold can't equalize recall
across groups with different score distributions — only per-group thresholds
([equal-opportunity](https://arxiv.org/abs/1610.02413), Hardt et al. 2016) can. `threshold_tradeoff.py`
quantifies both. Targeting the best group's recall (50%) everywhere:

| income group | global (top-20%) recall | equal-opportunity recall (per-group cut) | flag rate, global → per-group |
|---|---|---|---|
| Q1 low | 50.5% | 50.0% | 19.5% → 19.2% |
| Q2 | 49.1% | 50.0% | 21.4% → 21.9% |
| Q3 | 45.0% | 50.0% | 18.9% → 22.6% |
| Q4 high | 47.0% | 50.0% | 20.2% → 22.0% |

With the recall already this even, per-group cuts would move the total flag budget only from 20%
to 21.4%, but they mean a different decision rule per income group, keyed off a ZIP/income proxy:
disparate *treatment*, which a government enforcement program should avoid. **Recommendation: one
global order, a baseline of routine inspections everywhere, and coverage monitored by group.**
(The script also prints the global precision/recall trade: flagging 20% gives 30% precision, 2.4×
the base rate; flagging 50% reaches 82% of major violations for the model, 78% for the rule and
71% for persistence.)

## Feedback loop

Because inspections generate the labels the model trains on, targeting could compound over time
([runaway feedback loops](https://arxiv.org/abs/1706.09847), Ensign et al. 2018).
`feedback_check.py` tests one round of "only label what we flagged": trained on all 2023-24
labels, the model covers 50% / 49% / 45% / 47% of each income quartile's majors; trained only on
what a 2023 model flagged in 2024, 49% / 50% / 46% / 48%; with a 15% random baseline added, 49% /
50% / 46% / 47%. The one-line rule and persistence are not trained, so this cannot touch them
(51% / 50% / 45% / 48% and 43% / 42% / 40% / 42%). One round cannot show multi-cycle compounding,
so coverage by group is monitored in use.

## Limits

- Area-based (ZIP) income and ethnicity are a standard disparate-impact proxy, not the
  demographics of each facility's owner or customers, and cannot see within-ZIP differences.
- The model no longer reads ZIP, but business type and a facility's record can still correlate
  with neighborhood; that is why this audit reports outcomes by group rather than inputs.
- The data hold only surviving facilities, about 3.7 years of them.
- Any deployment should re-run this audit on the County's internal records, on a schedule.

Full source list (data, methods, fairness papers): [REFERENCES.md](REFERENCES.md).
