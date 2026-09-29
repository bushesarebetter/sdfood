# Model card: the students' point rule

This card describes the rule the City staff site shows ([STAFF_SITE.md](STAFF_SITE.md)): what it is,
how it was chosen and checked, and what it is for. Every figure is from `data/site/report.md` and
`meta.json` for the run `forward_2026-09-29-91e1bb95`, built from the full SD Food Info pull of
2026-09-29 (inspections through 2026-09-28), under the frozen rule version `2026-09-29-63c8fc7f`
(`docs/rule.json`). Rerunning `export_site.py` regenerates them; a run id names its content, so two
different lists never share one.

## In one paragraph

A restaurant's points are how far its average routine inspection score over the last two years fell
below 100, rounded half up (a routine inspection that ended in a health closure order counts as 70:
the County gives no score then). That is the whole rule, and every place's page lists the scores it
averages. Restaurants with **8 points or more** (an average of 92 or lower; about the top 20% of scored
restaurants) had a major violation at their next routine inspection **at about 1.7 times the rate of
all scored restaurants**: 36.6% (95% interval 33.0 to 40.4) against 21.2%, and about the same at every
backtest date (36.6%, 36.5%, 39.0%). About 63 in 100 of them had none. Every scored place also gets an
estimate: what places with about its points did in the backtest. Ranking by recent major violations,
which the County's record already shows, does as well (36.5% in a group of the same size): the rule's
value is that anyone can check it, not that it predicts better.

## Intended use

| | |
|---|---|
| **For** | City of San Diego staff: looking up a place a constituent asks about, with the County's full record and where to route a complaint; seeing a council district's pattern; preparing a conversation with the County. |
| **Access** | Signed-in City staff only, one sign-in per person, after a City requestor, a TRUST Ordinance determination and a responsible adult are on file ([STAFF_SITE.md](STAFF_SITE.md)); until the first two are, every page calls the site a demonstration. The public site ships an invented sample. |
| **Not for** | Any statement that a place is unsafe; any permit, licence, enforcement, grant, procurement or public-statement decision; contacting a business about its band, including outreach or training aimed at it; replacing the County's grade card, schedule or risk categories. |

**The decisions it can inform, and at what cost of a wrong flag.** A band is worth acting on only if
its rate clears C/(B+C), where C is the cost of acting on a place that turns out clean and B the value
of acting on one that does not (`meta.utility`, shown on the About page). Band 1 (36.6%, low end 33.0%)
clears the bar only when a wrong flag costs a quarter or less of what a right one is worth, so the only
decisions it fits are ones that single out no business:

| Decision | C/B the office should accept | Does band 1 clear it? |
|---|---|---|
| Raising a district's pattern with the County (the County decides what, if anything, to do) | low (0.25) | yes |
| Anything aimed at one business: a letter, a visit, outreach or training, a statement, a referral | 0.5 or more | no |

## Data

- **Source.** SD Food Info, the County's published inspection results, pulled 2026-09-29: 16,723
  facilities and 92,929 inspections (2023-01-03 to 2026-09-28), by `fetch_sdfood.py`, which identifies
  itself, rate-limits, and stops for good on a refusal. The pull is kept as a dated backup with its
  sha256; an export refuses a pull not recorded as complete.
- **Data rules** (`export_site.load_places`, tested):
  - "No Access", "Self Closed" and "Status Verification" visits are not inspections (5,444 records).
  - A routine visit within 30 days after a B, a C or a closure is a re-grade or reopening (1,841).
  - For the model, same-day records of one type are one visit (4,973 merged). For display, every
    County record is shown as published.
  - 0 means "not scored". Grades are the County's, never derived.
  - A closure is one episode, from the closure order to the County's "Approved to Reopen" (kept, with
    its date), a graded inspection on a later day, or a 30-day gap: a complaint visit or ungraded
    reinspection while a place is closed does not start a second one.
  - Themes are the sections of the County's own inspection report, read from the item text (the
    mobile-unit form numbers items differently).
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
- **Selection:** the sparsest candidate within 0.01 AUC of the best model at both validation origins.
  No transparent rule came that close (the yardsticks sit 0.01 to 0.02 above), so a fallback added
  after that first run chose instead: the sparsest candidate within 0.01 of the best *transparent*
  rule, flagged as such (`selection.within_epsilon` false). The fallback is post hoc, and is disclosed
  as one; the prospective test below is the check that does not depend on it. A denser rule is never
  chosen on a difference inside the tolerance.

| origin (AUC, eligible restaurants) | average score | count score | logistic | boosted | additive | persistence |
|---|---|---|---|---|---|---|
| 2025-03-01 (validation) | 0.697 | 0.704 | 0.711 | 0.713 | 0.713 | 0.690 |
| 2025-06-01 (validation) | 0.695 | 0.694 | 0.706 | 0.707 | 0.708 | 0.687 |
| 2025-09-01 (confirmation) | 0.680 | 0.677 | 0.690 | 0.686 | 0.689 | 0.676 |

The average-score rule is within 0.01 of the count score at both validation origins and is the
sparser, so it is the rule. It does not beat persistence (the difference at the confirmation origin is
-0.011 to 0.018). The three origins are three and six months apart and share most of their labels:
they are three looks at overlapping data, not three independent tests.

- **Frozen.** The rule, its cut, its estimates and this backtest are frozen in `docs/rule.json`,
  committed, with a version that names its content. Every export applies it unchanged; only
  `export_site.py --refit` chooses again, as a new version with its own prospective test.

## Closures counted as 70

A routine inspection that ended in a health closure order counts as 70 every time (1,320 routine
closures in the pull; the County gave most no score, and 75 a same-day score, which the worksheet shows
beside the 70). That choice carries weight: at the confirmation origin 215 of band 1's 653 labelled
places were there only because of a closure, and they had a major next time 27.4% of the time (21.9 to
33.8), against 41.1% (36.6 to 45.8) for the 438 there on routine scores alone. The site shows both.
[CLOSURE_SENSITIVITY.md](CLOSURE_SENSITIVITY.md) reran the backtest with a closure read as 80, 90 and as
the County's own point formula on the items cited that day: 90 and the formula raise AUC by about
0.008 and move most closure-carried places out of band 1. Under the rule fixed before running it
(change only for more than 0.01 AUC at every origin), 70 stays.

## Bands

- **Cut at fixed shares** of the scored list (2.5%, 7.5%, 17.5%), chosen before any outcome was seen,
  at whole points so a tie is never split: 17, 12 and 8 points.
- **Kept only where real.** A split between two bands survives only if the higher band's rate is above
  the lower one's at every backtest origin and the pooled difference is at least 2.326 standard errors
  (one-sided 1%), with one origin's worth of places because the origins overlap.
  `tools/band_null_sim.py` checks this on invented lists with no gradient and origins that share most of
  their labels, as the real ones do: the earlier threshold, 1.645, kept a spurious band 2 to 7% of the
  time (0.25% only if the origins had been independent, the figure this card used to give); 2.326
  keeps one 0.2 to 1.2% of the time. Band 1's real split is far past either.
- **Result: one band, 8 points or more.** 17 and 12 did not separate from 8 at every origin.

| | 2025-09-01 | 2025-03-01 | 2025-06-01 |
|---|---|---|---|
| Band 1 (8 points or more) | 36.6% (33.0 to 40.4; 653 labelled) | 36.5% | 39.0% |
| Scored restaurants below it | 17.4% | 15.9% | 17.1% |
| All scored restaurants | 21.2% | | |

Today: 745 City restaurants in band 1 (1,430 county-wide).

## Estimates: what a place's points say

Every scored place gets the rate at which places with about its points had a major at their next
routine inspection, from a monotone (isotonic) fit at the confirmation origin over point values pooled
into groups of at least 200 labelled places, with an address-cluster bootstrap range. The range is
sampling only: it says nothing about how the County's record has changed since 2025-26, and the site
says so. It levels off where the rates do (a logistic curve, used briefly, overstated the top of the
list).

| points | 0–1 | 2 | 3 | 4–5 | 6 | 7–8 | 9 or more |
|---|---|---|---|---|---|---|---|
| City (in 100) | 7 | 13 | 16 | 21 | 30 | 33 | 38 |
| Outside the City | 4–5 | 9 | 10 | 17–18 | 29 | 32 | 32 |

## Outside the City

The same rule and cut were checked on restaurants outside the City at the same origins. The ranking
carries over (AUC 0.71) and the band holds (32.2%, 28.4 to 36.2, against 17.2% of scored restaurants
outside the City), so places outside the City are shown in the band, described by the rates measured
outside the City, never the City's.

## Fairness, by council district

For a list of named places the harm is a place in the band that then had no major. For each district
the site shows band 1's precision (with its interval), its false-positive rate against the City's, and
its share of those places over its share of the labelled places, with a 95% interval and a wider
family-wise one (nine districts are compared, so one can look high by chance):

| district | in band 1 | precision | share of wrongly named, over its share | 95% | family-wise |
|---|---|---|---|---|---|
| 4 | 27 | 27% (14 to 46) | 1.99 | 1.25 to 2.76 | 1.01 to 3.24 |
| 9 | 82 | 26% (18 to 36) | 1.84 | 1.43 to 2.24 | 1.32 to 2.43 |
| 6 | 147 | 34% (27 to 42) | 1.35 | 1.13 to 1.57 | 1.05 to 1.67 |
| 3 | 110 | 47% (38 to 57) | 0.52 | 0.40 to 0.64 | 0.35 to 0.70 |

Districts 4, 9 and 6 stay above even on the family-wise interval. A place page in those districts says
how often band 1 places there had a major. Part of a district's gap may be how its inspectors cite, not
its restaurants: the record does not say which inspector made a visit, and the outreach asks the County
for territories. A coarse screen by restaurant name suggests a cuisine-linked gap that comes from the
County's own scores ([FAIRNESS.md](../FAIRNESS.md), "Limits").

## What the label is made of

- 99.2% of graded routine inspections are an A, including 94.1% of those that found a major.
- Scores heap at the A line: 2,893 routine inspections scored exactly 90, and none 89.
- A major follows a major 31.5% of the time, against 14.3% after a clean routine inspection.
- Different businesses at one address agree more on the same day (0.097) than on different days
  (0.065): inspector effects are real and unmeasured.
- The share of routine inspections with a major rose from 12.3% (2023 Q1) to 20.5% (2026 Q3, a partial
  quarter), so the backtest rates, measured on 2025-26, will drift.
- **Survivorship.** SD Food Info lists facilities that exist today. If a tenth of band 1's places had
  been places now gone, with the rate seen at places whose permits have expired (21%), band 1's rate
  would be 35.1% rather than 36.6%.

## Monitoring, drift, and when to refit

- **Drift, weekly, with no new labels** (`meta.drift`, on `/healthz` and the staff banner): the routine
  major rate of the last two full quarters against the backtest's quarters (17.7% against 17.5% today),
  and band 1's share of scored City restaurants against its share then (20.5% against 19.7%). Either
  moving more than 5 points means refit (`export_site.py --refit`), review and commit a new version.
- **The monitor** (`export_site.py --monitor`, run by every refresh) scores every archived list on the
  routine inspections made since, for the City and outside it apart, with the rate for all scored
  places beside band 1's and a count of places missing from the later pull. Until a list's label year
  is over its rates are marked interim: the County returns sooner to places with worse records, so an
  early rate is not comparable to the backtest's full-year one.
- **The prospective test.** `export_site.py --register` registers a run for its rule version; the
  test passes only after the registration has been committed 90 days, the label year is over, and
  band 1 has at least 300 later routine inspections in the City whose rate clears the cost bar and
  stays clearly above the rate for all scored City places. Nothing has passed it yet.

## Releases

The staff site ships with its own gates (a responsible adult, a corrections contact, a sunset date at
most a year away, a complete export from committed code applying the committed frozen rule) and tells
staff, on every page, what has not been done: no City request or TRUST determination, no lawyer, no
County comment, no owner told, the public-release gates the list fails, and any drift. Publishing names
on the public site requires every gate in [PUBLISHING.md](PUBLISHING.md), including an adult of record
who is 18 or older and not an author; today the public site shows only its invented sample.

## Authors

Independent student research by Chenhao Zhang and Ayan Pendharkar (Canyon Crest Academy), not
affiliated with or endorsed by the County of San Diego.
