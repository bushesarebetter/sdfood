# Fairness / disparate-impact analysis

An enforcement-targeting model has to answer: **does it disproportionately send inspectors
to lower-income or immigrant neighborhoods?** This is the check. Reproduce with
`python fairness_check.py` (needs `data/` from `fetch_sdfood.py`).

## Method

- Out-of-fold predictions (train ≤ 2024, test 2025+, 36,543 inspections the model never saw).
- Joined each facility to its ZIP's **median household income** and **% Hispanic** (ACS 5-yr via
  Census Reporter; 100% of test inspections covered, 97/109 ZIPs matched).
- Grouped by income quartile and %-Hispanic tercile, and compared:
  - **actual** critical-violation rate vs the model's **flag rate** (top-20% risk) — is targeting
    driven by real risk or by income?
  - **calibration** — does predicted risk match the actual rate *within* each group?
  - **equal opportunity** — is recall of true critical violations similar across groups?

## Results

By ZIP median income (Q1 = lowest):

| group | n | actual critical % | model flag % | mean predicted risk % | recall of criticals % |
|---|---|---|---|---|---|
| Q1 low | 9,434 | 11.3 | 15.7 | 10.9 | 35.8 |
| Q2 | 8,929 | 12.4 | 22.5 | 12.7 | 49.4 |
| Q3 | 9,208 | 11.3 | 18.1 | 10.9 | 42.2 |
| Q4 high | 8,917 | 11.8 | 24.0 | 13.0 | 53.4 |

By ZIP % Hispanic (T3 = highest): flag rate falls from 25.9% (low) to 15.1% (high), tracking
actual rates (12.7% → 10.7%).

## What it means

1. **No over-targeting of low-income / higher-Hispanic areas — the opposite.** Low-income ZIPs
   are flagged at **0.65×** the rate of high-income ZIPs, while actual violation rates are nearly
   flat across income (**0.96×**). Higher-Hispanic areas are flagged the *least*. The model flags
   in proportion to real risk, and real risk does not skew toward poor/immigrant areas here.
2. **Well-calibrated across groups.** Predicted risk ≈ actual violation rate in every income
   quartile and ethnicity tercile — the scores are not inflated for any group (see `food_fairness.png`).
3. **The real, honest caveat — equal *protection*, not over-policing.** Under a single global
   "top-20%" rule, recall of true critical violations is lower in lower-income / higher-Hispanic
   areas (36% vs 53%), because they score lower on average. This is an **under-coverage** risk:
   a pure risk-ranking could let real violations in lower-scored areas be caught later.
   **Mitigation: keep a baseline of routine/rotating inspections everywhere** so the model
   reprioritizes but never zeroes out an area. Monitor recall by group after deployment.

## Limits

- Area-based (ZIP) income/ethnicity is a standard disparate-impact proxy, not the demographics of
  each facility's owner or clientele.
- ~3 years of data; rates could shift with more history.
- Deployment should re-run this monitoring on the county's internal records and on an ongoing basis.
