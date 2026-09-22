# Fairness / disparate-impact analysis

An enforcement-targeting model has to answer: **does it disproportionately send inspectors
to lower-income or immigrant neighborhoods?** This is the check. Reproduce with
`python fairness_check.py` (needs `data/` from `fetch_sdfood.py`).

## Method

- Out-of-fold predictions (train ≤ 2024, test 2025+, 36,543 inspections the model never saw).
- Joined each facility to its ZIP's **median household income** and **% Hispanic** ([ACS](https://www.census.gov/programs-surveys/acs)
  5-yr via [Census Reporter](https://censusreporter.org): tables [B19013](https://censusreporter.org/tables/B19013/)
  income, [B03002](https://censusreporter.org/tables/B03002/) ethnicity; 100% of test inspections
  covered, 97/109 ZIPs matched).
- Grouped by income quartile and %-Hispanic tercile, and compared:
  - **actual** critical-violation rate vs the model's **flag rate** (top-20% risk) — is targeting
    driven by real risk or by income?
  - **calibration** — does predicted risk match the actual rate *within* each group?
  - **equal opportunity** — is recall of true critical violations similar across groups?

## Results

By ZIP median income (Q1 = lowest):

| group | n | actual critical % | model flag % | mean predicted risk % | recall of criticals % |
|---|---|---|---|---|---|
| Q1 low | 9,434 | 11.3 | 15.8 | 11.7 | 37.9 |
| Q2 | 8,929 | 12.4 | 21.5 | 13.6 | 50.7 |
| Q3 | 9,208 | 11.3 | 18.3 | 11.7 | 45.5 |
| Q4 high | 8,917 | 11.8 | 24.6 | 14.6 | 54.5 |

By ZIP % Hispanic (T3 = highest): flag rate falls from 26.2% (low) to 15.5% (high), tracking
actual rates (12.7% → 10.7%).

## What it means

1. **No over-targeting of low-income / higher-Hispanic areas — the opposite.** Low-income ZIPs
   are flagged at **0.64×** the rate of high-income ZIPs, while actual violation rates are nearly
   flat across income (**0.96×**). Higher-Hispanic areas are flagged the *least*. The model flags
   in proportion to real risk, and real risk does not skew toward poor/immigrant areas here.
2. **Broadly calibrated, slightly hot at the top.** Predicted risk ≈ actual violation rate in the
   low and middle income groups; in the highest-income quartile the model runs a bit hot (mean
   predicted 14.6% vs actual 11.8%). No group is *under*-scored relative to its real rate, so the
   targeting isn't inflated against any group (see `food_fairness.png`).
3. **The real, honest caveat — equal *protection*, not over-policing.** Under a single global
   "top-20%" rule, recall of true critical violations is lower in lower-income / higher-Hispanic
   areas (**38% vs 54%**), because they score lower on average and the model simply has **less
   discriminative signal there** (shorter/compressed histories). This is an **under-coverage**
   risk: a pure risk-ranking could let real violations in lower-scored areas be caught later.
   **Mitigations:** (a) keep a baseline of routine/rotating inspections everywhere so the model
   reprioritizes but never zeroes out an area; (b) monitor recall by group after deployment;
   (c) if the gap matters operationally, use **per-group thresholds** rather than one global cut.
   Note that (a) alone prevents blind spots but does **not** by itself close the recall gap on the
   targeted portion — it's a floor, not a fix.

## Closing the recall gap — what it costs (`threshold_tradeoff.py`)

The recall gap above is at a *single global* top-20% cut. A global threshold can't equalize recall
across groups with different score distributions — only per-group thresholds
([equal-opportunity](https://arxiv.org/abs/1610.02413), Hardt et al. 2016) can. `threshold_tradeoff.py`
quantifies both:

| income group | global (top-20%) recall | equal-opportunity recall (per-group cut) |
|---|---|---|
| Q1 low | 37.9% | 55.0% |
| Q2 | 50.7% | 55.0% |
| Q3 | 45.5% | 55.0% |
| Q4 high | 54.5% | 55.0% |

Equalizing works, but the price is: (a) total flag budget rises ~20% → ~25% (more inspector
capacity), and (b) it means a **different decision rule per income group, keyed off a ZIP/income
proxy** — disparate *treatment*, which a government enforcement program often cannot defend even
when the outcome is "fairer." **Recommendation: keep a random baseline everywhere + monitor recall
by group, rather than per-group thresholds.** (The script also prints the plain global
precision/recall/lift trade-off — AUC 0.745 caps it: even flagging 50% of facilities only reaches
~80% recall.)

## Feedback loop

Because inspections generate the very labels the model trains on, targeting can compound over time
([runaway feedback loops](https://arxiv.org/abs/1706.09847), Ensign et al. 2018).
`feedback_check.py` tests this: one round of "only label what we flagged" moves low-income recall
by ~1 point and a 15% random baseline holds it steady — reassuring, but single-round, so live
recall-by-group monitoring is still required.

## Limits

- Area-based (ZIP) income/ethnicity is a standard disparate-impact proxy, not the demographics of
  each facility's owner or clientele (ecological — it can't see within-ZIP disparities).
- ZIP is also a model *feature*, which is the channel through which neighborhood bias could enter;
  that's exactly why this audit exists and must be re-run on the county's internal data.
- ~3 years of data; rates could shift with more history.
- Deployment should re-run this monitoring on the county's internal records on an ongoing basis.

Full source list (data, methods, fairness papers): [REFERENCES.md](REFERENCES.md).
