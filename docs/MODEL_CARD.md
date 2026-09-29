# Model card: the students' point rule

This card describes the rule the City staff site shows ([STAFF_SITE.md](STAFF_SITE.md)): what it is,
how it was chosen and checked, and what it is for. Every figure is from `data/site/report.md` and
`meta.json` for the run `forward_2026-09-29-dbe49815`, built from the full SD Food Info pull of
2026-09-29 (inspections through 2026-09-28). Rerunning `export_site.py` regenerates them; a run id
names its content, so two different lists never share one.

## In one paragraph

A restaurant's points are how far its average routine inspection score over the last two years fell
below 100 (a routine inspection that ended in a closure order counts as 70). That is the whole rule,
and every place's page lists the scores it averages. Restaurants with **8 points or more** (an average
of 92 or lower; about the top 19% of scored restaurants) had a major violation at their next routine
inspection **at about 1.7 times the rate of all scored restaurants**: 36.9% (95% interval 33.2 to
40.7) against 21.2%, and the same at every backtest date (36.8%, 36.8%, 39.1%). Every scored place
also gets an estimate: places with about its points did this well in the backtest. Ranking by recent
major violations, which the County's record already shows, does about as well (36.9% in a group of
the same size): the rule's value is that anyone can check it, not that it predicts better.

## Intended use

| | |
|---|---|
| **For** | City of San Diego staff: looking up a place a constituent asks about, with the County's full record and where to route a complaint; seeing a council district's pattern; preparing a conversation with the County. |
| **Access** | Signed-in City staff only, one sign-in per person, after a City requestor, a TRUST Ordinance determination and a responsible adult are on file ([STAFF_SITE.md](STAFF_SITE.md)). The public site ships an invented sample. |
| **Not for** | Any statement that a place is unsafe; any permit, licence, enforcement, grant, procurement or public-statement decision; contacting a business about its band; replacing the County's grade card, schedule or risk categories. |

**The decisions it can inform, and at what cost of a wrong flag.** A band is worth acting on only if
its rate clears C/(B+C), where C is the cost of acting on a place that turns out clean and B the value
of acting on one that does not. Band 1 clears the bar only when a wrong flag costs a quarter or less
of what a right one is worth (`meta.utility`):

| Decision | C/B the office should accept | Does band 1 clear it? |
|---|---|---|
| Choosing where to send food-safety outreach or training material | low (0.25): a wasted visit costs little | yes |
| Raising a district's pattern with the County | low: the County decides what to do | yes |
| Anything that singles out one business (a letter, a statement, a referral) | 0.5 or more | no |

## Data

- **Source.** SD Food Info, the County's published inspection results, pulled 2026-09-29: 16,723
  facilities and 92,929 inspections (2023-01-03 to 2026-09-28), by `fetch_sdfood.py`, which identifies
  itself, rate-limits, and stops for good on a refusal. The pull is kept as a dated backup with its
  sha256; an export refuses a pull not recorded as complete.
- **Data rules** (`export_site.load_places`, tested):
  - "No Access", "Self Closed" and "Status Verification" visits are not inspections (5,444 records).
  - A routine visit within 30 days after a B, a C or a closure is a re-grade or reopening (1,830).
  - For the model, same-day records of one type are one visit (4,973 merged). For display, every
    County record is shown as published.
  - 0 means "not scored". Grades are the County's, never derived.
  - Nothing found at a reinspection that followed a complaint visit counts toward a rule.
- **Listed places.** Restaurants, limited-preparation food service, and markets with a deli or food
  processing, visited in the last 18 months, whose entry was not marked expired: 10,965 county-wide,
  of which 5,404 are inside the City (SANDAG council districts). Private homes (home kitchens, cottage
  food) are never listed.
- **Scored places.** Restaurants with two rated routine inspections in the last two years.

## The rule, and how it was chosen

- **Snapshots.** On the first of each month, every active restaurant county-wide is described by its
  record before that date and labelled by its first routine inspection in the year after.
- **Candidates, simplest first:** the average-score rule (one number); a count score (up to six
  whole-number weights on citations and score deficits); and, as yardsticks only, logistic
  regression, monotone gradient boosting and a monotone additive model.
- **Selection (declared before looking):** the sparsest candidate within 0.01 AUC of the best model at
  both validation origins; failing that, the sparsest within 0.01 of the best *publishable* rule. A
  denser rule is never chosen on a difference inside that tolerance.

| origin | average score | count score | logistic | boosted | additive | persistence |
|---|---|---|---|---|---|---|
| 2025-03-01 (validation) | 0.698 | 0.705 | 0.712 | 0.713 | 0.712 | 0.690 |
| 2025-06-01 (validation) | 0.694 | 0.690 | 0.707 | 0.707 | 0.708 | 0.687 |
| 2025-09-01 (confirmation) | 0.680 | 0.678 | 0.691 | 0.687 | 0.690 | 0.676 |

No transparent rule was within 0.01 of the yardsticks at both validation origins (they sit 0.01 to
0.02 above), so the flagged fallback applies: the average-score rule is within 0.01 of the count
score at both, and it is the sparser, so it is the rule. (An earlier version shipped the six-item count
score on a 0.003 difference; three reviews showed its top weights did not replicate across refits.)

## Bands

- **Cut at fixed shares** of the scored list (2.5%, 7.5%, 17.5%), chosen before any outcome was seen,
  at whole points so a tie is never split: 17, 12 and 8 points.
- **Kept only where real.** A split between two bands survives only if the higher band's rate is above
  the lower one's at every backtest origin and the pooled difference is at least 1.645 standard errors
  (with one origin's worth of places, because the origins overlap). On invented data with no gradient
  this rule keeps a spurious band 0.25% of the time; the rule it replaced, which kept any split whose
  rates happened to be in order at one origin, returned extra bands two times in three.
- **Result: one band, 8 points or more.** 17 and 12 did not separate from 8 at every origin.

| | 2025-09-01 | 2025-03-01 | 2025-06-01 |
|---|---|---|---|
| Band 1 (8 points or more) | 36.9% (33.2 to 40.7; 640 labelled) | 36.8% | 39.1% |
| Scored restaurants below it | 17.4% | 15.9% | 17.2% |
| All scored restaurants | 21.2% | | |

Today: 731 City restaurants in band 1 (1,407 county-wide).

## Estimates: what a place's points say

Every scored place gets the rate at which places with about its points had a major at their next
routine inspection, from a monotone (isotonic) fit at the confirmation origin over point values pooled
into groups of at least 100 places, with an address-cluster bootstrap range. It levels off where the
rates do: a smooth logistic curve, used briefly, kept rising and overstated the top of the list
(46–51% where the backtest shows 35–40%).

| points | 0 | 2 | 4 | 6 | 8 | 10–15 | 16+ |
|---|---|---|---|---|---|---|---|
| City (in 100) | 7 | 12 | 21 | 30 | 34 | 37 | 39 |
| Outside the City | 4 | 9 | 17 | | 30 | 35 | 35 |

## Outside the City

The same rule and cut were checked on restaurants outside the City at the same origins. The ranking
carries over (AUC 0.71) and the band holds (32.6%, 28.8 to 36.7, against 17.2% of scored restaurants
outside the City), so places outside the City are shown in the band, described by the rates measured
outside the City, never the City's.

## Fairness, by council district

For a list of named places the harm is a place in the band that then had no major. Across the band at
the confirmation origin, Districts 4 and 9 carried about twice their share of those places (2.02 times,
interval 1.26 to 2.79, of 27 in the band; and 1.92 times, 1.50 to 2.35, of 81), and District 6 1.32
times. District 3 carried half its share. The site shows this table to staff. Part of a district's gap
may be how its inspectors cite, not its restaurants: the record does not say which inspector made a
visit, and the outreach asks the County for territories. A coarse screen by restaurant name suggests a
cuisine-linked gap that comes from the County's own scores ([FAIRNESS.md](../FAIRNESS.md), "Limits").

## What the label is made of

- 99.2% of graded routine inspections are an A, including 94.1% of those that found a major.
- Scores heap at the A line: 2,894 routine inspections scored exactly 90, and none 89.
- A major follows a major 31.5% of the time, against 14.3% after a clean routine inspection.
- Different businesses at one address agree more on the same day (0.097) than on different days
  (0.065): inspector effects are real and unmeasured.
- The share of routine inspections with a major rose from 12.3% (2023 Q1) to 20.5% (2026 Q3), so the
  backtest rates, measured on 2025-26, will drift.
- **Survivorship.** SD Food Info lists facilities that exist today. If a tenth of band 1's places had
  been places now gone, with the rate seen at places whose permits have expired (21%), band 1's rate
  would be 35.3% rather than 36.9%.

## Monitoring, and when to refit

- Every run is archived once, under its content-hashed run id, with a manifest of hashes.
  `export_site.py --register` freezes a run for the prospective test; `--monitor` scores archived runs
  against the routine inspections made since.
- **Refit** (rerun the selection, not the weights by hand) when band 1's rate on inspections made after
  a registered run falls outside its backtest interval, when the base rate moves by more than 5
  points, or when a new County data feed replaces the scrape.

## Releases

The staff site ships with its own gates (a responsible adult, a corrections contact, a sunset date, a
complete and committed export) and shows staff every public-release gate the list does not pass.
Publishing names on the public site requires every gate in [PUBLISHING.md](PUBLISHING.md); today the
public site shows only its invented sample.

## Authors

Independent student research by Chenhao Zhang and Ayan Pendharkar (Canyon Crest Academy), not
affiliated with or endorsed by the County of San Diego.
