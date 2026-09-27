# References

Sources backing the claims in this repo, grouped by what they support. Links verified 2026-09.

## Precedent — a government food-inspection risk model has been deployed before

- **City of Chicago — Food Inspection Forecasting.** Deployed model that predicts critical
  violations to prioritize inspectors; open code + published evaluation showing critical violations
  found earlier. This project is the same idea for San Diego.
  - Repo: https://github.com/Chicago/food-inspections-evaluation
  - Project write-up: https://chicago.github.io/food-inspections-evaluation/

## Regulatory context — who sets the schedule, and what San Diego says it does

Checked against the sources on 2026-09-27; [docs/COUNTY_METHOD.md](docs/COUNTY_METHOD.md) sets every
claim this repository makes about the County beside what the County says and what the record shows.

- **CDPH Retail Food Program** — the California Retail Food Code is "primarily enforced by 62 local
  environmental health regulatory agencies":
  https://www.cdph.ca.gov/Programs/CEH/DFDCS/Pages/FDBPrograms/FoodSafetyProgram/RetailFoodProgram.aspx
- **California Retail Food Code (CalCode)** — Health & Safety Code, Division 104, Part 7:
  https://leginfo.legislature.ca.gov/faces/codesTOCSelected.xhtml?tocCode=HSC
  (an excerpt effective 2017: https://cns.ucdavis.edu/sites/g/files/dgvnsk416/files/inline-files/crfc_2.pdf ).
  Its text sets no statewide number of routine inspections a year; the state evaluates each local
  agency's program at least once every three years (§113713(c)).
- **San Diego County DEHQ — SD Food Info (Food Facility Inspection Search)** — "approximately 14,000
  retail food establishments are inspected on a routine basis"; "Unannounced inspections are
  performed by a Registered Environmental Health Specialist"; "Our inspection methodology
  prioritizes inspections based on relative risk": https://www.sandiegocounty.gov/content/sdc/deh/fhd/ffis/intro.html.html
- **SD Food Info disclaimer** — the site shows results "for the past three years at each facility":
  https://www.sandiegocounty.gov/content/sdc/deh/fhd/ffis/disclaimer.html
- **San Diego County DEHQ — Food Program** — "risk-based inspections, which means we focus on items
  that strongly affect food safety" (what an inspection looks at, not how often); the grading
  system (a Major Risk Factor is four points, a Minor two, a Good Retail Practice one; A is 90 to
  100); "more than 32,000 inspections at these food facilities each year":
  https://www.sandiegocounty.gov/content/sdc/deh/fhd/food/food.html
- **Food Program FAQ** — "When major violations are found, they are immediately corrected or a
  suitable alternative is implemented until they are corrected":
  https://www.sandiegocounty.gov/content/sdc/deh/fhd/food/food_faq.html
- **County Code of Regulatory Ordinances §61.107** (Ordinance 10218, 2012) — the letter grades; DEH
  "may order a food facility permit holder receiving a grade of 'B' or 'C' to submit to subsequent
  re-grade inspections within 30 days, until the facility receives an 'A' grade", at a fee; no grade
  card when a facility is closed for an imminent health hazard:
  https://files.amlegal.com/pdffiles/SanDiegoCo/ord10218.pdf
- **Retail Food Facility Operator's Guide** (County DEH, third edition) — "Facilities must earn a grade
  of A within 30 days of receiving a grade of B or C"; a re-grade inspection follows an
  unscheduled-inspection fee; majors not corrected at once, or given a suitable alternative, may close
  "the impacted areas or processes":
  https://www.sandiegocounty.gov/content/dam/sdc/deh/fhd/food/pdf/publications_opguide.pdf
- **Food complaints** (the site's complaint and illness lines, (858) 505-6903 and (858) 505-6814):
  https://www.sandiegocounty.gov/content/sdc/deh/fhd/food/foodcomplaints.html

> No County source found states how often each kind of facility is routinely inspected, or how a
> month's inspections are ordered. An earlier version of this file cited a "risk-based, ~1-3x/yr"
> practice; no San Diego source supports those numbers, so they are gone. What this repository says
> about cadence and order is measured from the public record (`model_food.py`, `sim_schedule.py`) and
> labelled as measured; the County can confirm or correct it.

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
