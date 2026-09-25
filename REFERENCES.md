# References

Sources backing the claims in this repo, grouped by what they support. Links verified 2026-09.

## Precedent — a government food-inspection risk model has been deployed before

- **City of Chicago — Food Inspection Forecasting.** Deployed model that predicts critical
  violations to prioritize inspectors; open code + published evaluation showing critical violations
  found earlier. This project is the same idea for San Diego.
  - Repo: https://github.com/Chicago/food-inspections-evaluation
  - Project write-up: https://chicago.github.io/food-inspections-evaluation/

## Regulatory context — inspection frequency is risk-based and set by the county, not fixed by the state

Supports the reframed premise: San Diego already tiers by facility category, and frequency is a
local-agency decision — so risk-prioritizing *within* the required schedule is the right framing.

- **CDPH Retail Food Program** — states the California Retail Food Code is "enforced by 62 local
  environmental health regulatory agencies" (frequency/enforcement is local discretion):
  https://www.cdph.ca.gov/Programs/CEH/DFDCS/Pages/FDBPrograms/FoodSafetyProgram/RetailFoodProgram.aspx
- **California Retail Food Code (CalCode)** — Health & Safety Code, Division 104, Part 7 (full text):
  https://leginfo.legislature.ca.gov/faces/codesTOCSelected.xhtml?tocCode=HSC
  (a county-hosted PDF excerpt, if leginfo is slow: https://cns.ucdavis.edu/sites/g/files/dgvnsk416/files/inline-files/crfc_2.pdf )
- **San Diego County DEH — Food Program** (the enforcing agency; risk-based methodology):
  https://www.sandiegocounty.gov/content/sdc/deh/fhd/food/food.html
- **San Diego County — Food Facility Inspection Search (FFIS)** (the public inspection records,
  same data the app exposes): https://www.sandiegocounty.gov/content/sdc/deh/fhd/ffis.html

> Note: CalCode does not fix a statewide number of inspections per year; the "risk-based, ~1–3×/yr"
> practice is set per local enforcement agency. The "corr ≈ 0.06 between a facility's own history and
> its cadence" claim is computed from the public inspection data in this repo, not from a policy
> document — present it as such and let the county confirm.

## Fairness data — ZIP income and ethnicity

- **U.S. Census Bureau — American Community Survey (ACS) 5-year:**
  https://www.census.gov/programs-surveys/acs
- **Census Reporter** (keyless ACS access used by `fairness_check.py`): https://censusreporter.org
  - **B19013** — Median Household Income: https://censusreporter.org/tables/B19013/
  - **B03002** — Hispanic or Latino Origin by Race (for % Hispanic): https://censusreporter.org/tables/B03002/

## Methods — modeling and validation

- **scikit-learn `HistGradientBoostingClassifier`** (the model):
  https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html
- **scikit-learn — model evaluation** (ROC-AUC, average precision / PR-AUC, calibration):
  https://scikit-learn.org/stable/modules/model_evaluation.html
- **Time-series / rolling-origin cross-validation** (why we split forward in time, not randomly) —
  Hyndman & Athanasopoulos, *Forecasting: Principles and Practice*:
  https://otexts.com/fpp3/tscv.html

## Fairness & equity — methods and risks

- **Equal opportunity / per-group thresholds** — Hardt, Price & Srebro (2016), *Equality of
  Opportunity in Supervised Learning*: https://arxiv.org/abs/1610.02413
  (backs `threshold_tradeoff.py` and the recall-parity discussion in `FAIRNESS.md`)
- **Feedback loops in enforcement allocation** — Ensign et al. (2018), *Runaway Feedback Loops in
  Predictive Policing*: https://arxiv.org/abs/1706.09847
  (backs the feedback-loop caveat and `feedback_check.py`)
- **Disparate impact** (concept behind the flag-rate vs actual-rate ratio, e.g. the "four-fifths"
  heuristic): https://en.wikipedia.org/wiki/Disparate_impact
