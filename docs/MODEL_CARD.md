# Model card: the students' point rule

This card describes the rule the City staff site shows ([STAFF_SITE.md](STAFF_SITE.md)): what it is,
how it was chosen and checked, and what it is for. Every figure is from `data/site/report.md` and
`meta.json` for the run `forward_2026-09-29-9a49dda0`, built from the full SD Food Info pull of
2026-09-29 (inspections through 2026-09-28), under the frozen rule version `2026-09-29-065efe53`
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
estimate: what places with about its points did in the backtest, read from a separate curve for places
whose two years include a closure (they did less often: about 32 in 100). Ranking by recent major violations,
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
of acting on one that does not (`meta.utility`, shown on the About page). Band 1's low end (33.0%)
clears that bar only if a wrong flag costs less than about half (0.49) of what a right one is worth,
and no one at the City has set that ratio (`cost_ratio` is null). Within Districts 4 and 9 its low ends
are 14% and 18%, so there it may not clear even a quarter. Bands support no decision about a business
(a letter, a visit, outreach or training, a statement, a referral) and no comparison between districts.
A district's pattern, to raise with the County, means its County-record facts (majors, closures, B and
C grades), not how many of its places are in a band.

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
- **Training windows.** The record starts in January 2023, so the earliest training snapshots see less
  than two years of scores: the fitted yardsticks and the count score trained on shortened windows,
  while the average-score rule trains on nothing. The comparison below leans slightly its way.
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
  committed, with a version that names its content, including a hash of the code and the constants
  that decide what a point means (the closure reading, the windows, the episode rule, the themes): an
  export refuses to apply a frozen rule whose feature code has changed. Only `export_site.py --refit`
  chooses again, as a new version with its own prospective test.

## Closures counted as 70

A routine inspection that ended in a health closure order counts as 70 every time (1,320 routine
closures in the pull; the County gave most no score, and 75 a same-day score, which the worksheet shows
beside the 70). That choice carries weight: at the confirmation origin 215 of band 1's 653 labelled
places were there only because of a closure, and they had a major next time 27.4% of the time (21.9 to
33.8), against 41.1% (36.6 to 45.8) for the 438 there on routine scores alone. The site shows both.
[CLOSURE_SENSITIVITY.md](CLOSURE_SENSITIVITY.md) reran the backtest with a closure read as 80, 90 and as
the County's own point formula on the items cited that day: 90 and the formula raise AUC by about
0.008 and move most closure-carried places out of band 1; compared at the same share of the list,
every reading gives about the same rate. Under the rule fixed before running it (change only for more
than 0.01 AUC at every origin), 70 stays. Because the rate differs by route, each place's estimate is
read from its own curve (below).

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
into groups of at least 200 labelled places, with an address-cluster bootstrap range. There are two
curves: one for places whose two scored years include no health closure, and one for places whose
years include one (counted as 70). Closure-carried places had a major next time less often than
places with the same points from routine scores alone, so one pooled curve misread both: it read
closure places about 5 points high and score places about 3 points low at the top. The range is
sampling only: it says nothing about how the County's record has changed since 2025-26, and the site
says so. It levels off where the rates do (a logistic curve, used briefly, overstated the top).

| points | 0–1 | 2 | 3 | 4–5 | 6 | 7 | 8 or more |
|---|---|---|---|---|---|---|---|
| City, no closure (in 100) | 7 | 13 | 16 | 21 | 30 | 32 | 40 |
| City, a closure in the two years | | | | | | 32 | 32 |
| Outside the City, no closure | 4–5 | 9 | 10 | 17–18 | 29 | 32 | 36 |
| Outside the City, a closure | | | | | | | 26 |

## Outside the City

The same rule and cut were checked on restaurants outside the City at the same origins. The ranking
carries over (AUC 0.71) and the band holds (32.2%, 28.4 to 36.2, against 17.2% of scored restaurants
outside the City), so places outside the City are shown in the band, described by the rates measured
outside the City, never the City's.

## Fairness, by council district

For a list of named places the harm is a place in the band that then had no major. For each district
the site shows band 1's precision (with its interval), its false-positive rate against the City's, and
its share of those places over its share of the labelled, scored places, with a 95% address-cluster
bootstrap interval (10,000 draws), a family-wise one (nine districts are compared, so one can look
high by chance), and the family-wise one widened by an assumed design effect of 2 for inspector
clustering, which the record cannot show:

| district | in band 1 | precision | share of wrongly named, over its share | 95% | family-wise | allowing for inspectors |
|---|---|---|---|---|---|---|
| 4 | 27 | 27% (14 to 46) | 2.05 | 1.28 to 2.86 | 1.00 to 3.26 | 0.57 to 3.76 |
| 9 | 82 | 26% (18 to 36) | 1.88 | 1.50 to 2.29 | 1.34 to 2.47 | 1.11 to 2.71 |
| 6 | 147 | 34% (27 to 42) | 1.32 | 1.10 to 1.54 | 1.01 to 1.63 | 0.88 to 1.77 |
| 5 | 52 | 31% (20 to 45) | 1.25 | 0.86 to 1.68 | 0.71 to 1.87 | 0.49 to 2.13 |
| 3 | 110 | 47% (38 to 57) | 0.53 | 0.40 to 0.66 | 0.35 to 0.71 | 0.28 to 0.79 |

Only District 9 stays above even on both wider intervals, and the staff notice names only it. Districts
4 and 6 are above even at 95% but not once chance across nine districts and inspector clustering are
allowed for; District 5 cannot be told from even. A place page in a City district says how often band 1
places there had a major. Part of a district's gap may be how its inspectors cite, not its restaurants:
the record does not say which inspector made a visit, and the outreach asks the County for
territories. (Resampling ZIP codes as a stand-in for territories was tried and is degenerate: a district
holds too few ZIP codes.) A coarse screen by restaurant name (`tools/name_screen.py`,
[NAME_SCREEN.md](NAME_SCREEN.md)) suggests clean restaurants whose names suggest East or Southeast
Asian cuisine are put in band 1 about 1.9 times as often as unclassified names (1.5 to 2.5): the rule
is the County's own average score, so it passes any gap in those scores through unchanged
([FAIRNESS.md](../FAIRNESS.md), "Limits").

## What the label is made of

- 99.2% of graded routine inspections are an A, including 94.1% of those that found a major.
- Scores heap at the A line: 2,893 routine inspections scored exactly 90, and none 89.
- A major follows a major 31.5% of the time, against 14.3% after a clean routine inspection.
- Different businesses at one address agree more on the same day (0.097) than on different days
  (0.065): inspector effects are real and unmeasured.
- The share of routine inspections with a major rose from 12.3% (2023 Q1) to 20.5% (2026 Q3, a partial
  quarter), so the backtest rates, measured on 2025-26, will drift.
- **Survivorship.** SD Food Info lists facilities that exist today. Places whose permits had since
  expired had about the same rate as the rest (21%, from only 38 places), so the size of this bias is
  unknown; if a tenth of band 1's places had been places now gone, at that rate, band 1's rate would be
  35.1% rather than 36.6%.

## Monitoring, drift, and when to refit

- **Drift, weekly, with no new labels** (`meta.drift`, on `/healthz` and the staff banner), each
  against max(2 points, 3 standard errors): the routine major rate in complete quarters that start
  after the backtest's label year (which ended August 2026), against the label year's own 17.5%; and
  band 1's share of scored City restaurants against its share then (20.5% against 19.7% today, within
  the threshold). No quarter after the label year is complete yet, so the first signal reads "not yet
  measurable", never a clean result. Meanwhile the latest quarter (2026 Q3, through September 28) found
  a major at 20.4% of routine inspections, clearly above the backtest year's 17.5%, and every estimate
  on the site says the rates may be low. A refit (`export_site.py --refit`) makes a new version.
- **The monitor** (`export_site.py --monitor`, run by every refresh) scores every archived list on the
  routine inspections made since, the City and outside it apart, each against its own backtest: band
  rates, the estimates (observed over expected), band 1 against persistence's same-size group, and a
  count of places missing from the later pull (matched on the County's business id). A list is
  complete once its label year (plus 30 days for the County's reporting) has passed in the pull. Before
  that its rates cover a 90, 180 or 270-day window and are set against the backtest's rates for the
  same window (`card.interim`: band 1 36%, 33% and 37%), since the County returns sooner to places with
  worse records.
- **The prospective test.** `export_site.py --register` registers a list for its rule version, only one
  the frozen rule drew up, and only within 14 days of the list date. The test counts the registration's
  first commit, and only once that commit is pushed (a local date can be set to anything). It passes
  only after 90 days, a complete label year, and at least 300 later routine inspections of band 1 City
  places, when band 1's rate clears the cost bar, stays clearly above all scored City places, and is no
  more than 5 points below its backtest rate; the estimates are calibrated (observed over expected 0.85
  to 1.15); and band 1 catches more than persistence's same-size group. Nothing has passed it yet.

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
