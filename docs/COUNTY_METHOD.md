# What San Diego County does: the baseline, checked

Every comparison in this repository is made against **the order the County's routine inspections were
actually done in**, read from the County's published record. It is not made against a description of
County policy. Still, the docs describe how the County works, and a wrong description would misstate the
case, so this page sets each claim beside what the County itself publishes and what the record shows.
Checked 2026-09-27; the County's pages are linked in [REFERENCES.md](../REFERENCES.md).

## The short version

- **What the County publishes is confirmed**, with one wording fix: grades and points, unannounced
  inspections, re-grade inspections within 30 days of a B or C, the three-year window of SD Food Info,
  and what happens when a major violation is found.
- **What the County does not publish, we had stated as fact.** No County page says how often each kind of
  facility is routinely inspected or how a month's inspections are ordered. The County says only that its
  "inspection methodology prioritizes inspections based on relative risk". The docs now say what the record
  shows instead, and label it as measured.
- **The record answers the question that matters for the case.** Within a council district's month, the
  order the County actually worked puts an inspection that found a major violation ahead of a clean one
  50.7% of the time (95% CI 49.1–52.1%): no different from chance. The one-line rule does so
  74.4% of the time. Schools are visited about twice as often as restaurants because federal law
  requires two inspections a school year for schools in the national school lunch program
  (42 U.S.C. §1758(h)); apart from them, the kinds of place differ little (low-risk facilities every
  315 days, restaurants every 312). Whatever risk tiers the County uses, the public record does not
  show them, and this project leaves how often places are visited alone: it changes only the order
  within a month. So the head start is measured against an order that
  does not already rank by risk, and it is not counting risk work the County already does.

## Claim by claim

| what this repository says | what the County publishes | verdict |
|---|---|---|
| Routine inspections are unannounced | "Unannounced inspections are performed by a Registered Environmental Health Specialist" (SD Food Info) | confirmed |
| "Major violation" is the County's term | "There are three levels of violations for a restaurant inspection - Major Violations, Minor Violations and Good Retail Practices" (FAQ) | confirmed |
| A major is corrected at once | "When major violations are found, they are immediately corrected or a suitable alternative is implemented until they are corrected" (FAQ); if neither, "closure of the impacted areas or processes" (Operator's Guide) | confirmed in substance; the site said "corrected during the inspection, or the affected area is closed", now the County's wording |
| The score and the grade | 100 minus 4 points per Major Risk Factor, 2 per Minor, 1 per Good Retail Practice; A is 90 to 100, B 80 to 89, C 79 or less (Food Program page; County Code §61.107(a)) | confirmed |
| A routine visit within 30 days after a B or C is a re-grade, not a routine inspection (a data rule) | DEH "may order a food facility permit holder receiving a grade of 'B' or 'C' to submit to subsequent re-grade inspections within 30 days" (County Code §61.107(b)); "Facilities must earn a grade of A within 30 days" (Operator's Guide); the operator pays for the re-grade | confirmed: the rule reads the County's own 30-day window |
| No grade is posted when a place is closed | no grade card when DEH closes a facility for an imminent health hazard (§61.107(a)) | confirmed; the research reads a health closure at a routine as a score of 70, a modelling choice, stated where used |
| SD Food Info holds about three years | "grade scores and a summary of violations ... for the past three years at each facility" (disclaimer) | confirmed: the record starts 2023-01-03, the left truncation the docs describe |
| "The County sets routine inspection frequency by facility category" | "Our inspection methodology prioritizes inspections based on relative risk" (SD Food Info); "risk-based inspections" on the Food Program page means what an inspection looks at ("handwashing, food temperatures ... are more important than a missing light bulb"), not how often | **not published; now stated as measured** (below) |
| "1 to 3 inspections a year by risk category" (REFERENCES.md) | no San Diego source; CalCode sets no statewide frequency and leaves enforcement to 62 local agencies | **removed** |
| Inspectors work areas; an inspector's territory is the County's real unit | not published | **an assumption**, now labelled; council districts stand in for it, and outreach asks the County |
| The County inspects the City of San Diego's restaurants (the City's worklists are built from its record) | "There are 18 cities with more than 13,800 permanent retail food facilities in San Diego County, including over 8,100 restaurants" (Food Program page) | consistent: the dashboard counts 8,274 active restaurant facilities county-wide |
| About 18,700 routine inspections in 2025 | "more than 32,000 inspections at these food facilities each year" (all kinds, Food Program page) | consistent: the public record holds 27,130 inspections of all kinds for 2025 (after the data rules) |

The public record holds fewer inspections than the County's figure. Part of the gap is survivorship: SD
Food Info lists only facilities that exist today, so the older a year, the more of its inspections are
missing (21,628 inspections on the record for 2023, 22,838 for 2024, 27,130 for 2025). Part may be
kinds of inspection the search does not show; the County can say.

## What the record shows the County does (measured)

**How often: by kind of facility.** Median days from one routine inspection to the next (routines through
2025-06 whose next routine is on the record; `model_food.py`):

| kind of facility | routine inspections observed | median days to the next routine |
|---|---|---|
| School processing food facility | 2,666 | 185 |
| School food auxiliary facility | 1,016 | 186 |
| Restaurant food facility | 22,016 | 312 |
| Low risk food facility | 2,754 | 315 |
| Retail market with deli | 3,263 | 322 |
| Mobile food facility prep unit | 1,422 | 345 |
| Pre-packaged retail market | 2,975 | 361 |
| Miscellaneous food facility | 1,009 | 365 |

**How often: a facility's own record moves it a little.** The next routine comes a median 277 days
after one that found a major, against 303 after one that did not; by the facility's mean routine
score on record, best to worst quintile: 322, 326, 317, 297 and 289 days. Across facilities on the record three years or
more, the correlation between a facility's routine major-violation rate and its routine inspections per
year is −0.07.

**The order within a month: no risk ordering** (`sim_schedule.py`, 2025-26 routine inspections):

| ordering | an inspection that found a major comes before a clean one in the same window | 95% CI |
|---|---|---|
| the order the County actually worked, within a council district's (or ZIP3 area's) month | 50.7% | 49.1–52.1% |
| the order actually worked, within a county-wide month | 49.9% | 48.6–51.1% |
| the one-line rule (lowest mean routine score on record first), same windows | 74.4% | 73.3–75.6% |

Inspections that found a major were done on day 15.3 of the month on average, clean ones on day
15.3. 50% is what a random order gives.

**The order within a month does follow something: due dates, a little.** Within a district's month,
being inspected earlier goes with a longer time since the facility's last visit (as of the 1st): a
rank correlation of +0.089 (95% CI +0.064 to +0.113). With the facility's record it is −0.002
(−0.024 to +0.021). So the County's month leans slightly toward the most overdue places and not at all toward
the riskiest. Ordering by the record would override that lean, inside the same month: every place due
that month is still inspected that month. The simulation's blend of the two (the old dashboard's
risk × overdue weighting) finds majors later than the record alone (README).

## What this means for the case

- **The baseline is sound.** The head start (+5.8 days for the rule, +6.4 for the model,
  within a district's month) is measured against the order the County actually worked, and that order does
  not already put risky places first. If the County ranked by risk inside a month, it would show here; it
  does not.
- **Nothing here second-guesses the County's frequencies.** Any risk tiers the County uses would work
  through how often a place is visited (the records request asks for them). The proposal keeps every visit and every frequency, and only orders the
  visits already due in a month.
- **The same kind of result has been found before.** Chicago's food-inspection pilot, the precedent this
  project follows, reports critical violations found about 7 days sooner
  ([its evaluation](https://chicago.github.io/food-inspections-evaluation/)); its window and baseline
  differ from these, so the two numbers are comparable in size only.
- **What only the County can settle:** how routine inspections are assigned (inspector territories, as the
  district simulation assumes), who sets the order within a month, which inspections the public search
  leaves out, and records for facilities that have closed. The three questions at the top of
  [outreach.md](../outreach.md) and its records request ask for exactly these.
