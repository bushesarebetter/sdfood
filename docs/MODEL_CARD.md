# Model card: the published scoring rule

This card describes the rule behind the City staff API ([API.md](API.md)) and the gated public
site (`food-dashboard/`): what it is, how it was chosen and tested, and what it is for. Every
figure comes from `data/site/report.md` for the run `forward_2026-09-20`, which was built from the
full SD Food Info pull of 2026-09-23/24, with inspections through 2026-09-19. Rerunning
`export_site.py` regenerates the figures.

## In one paragraph

The rule orders City of San Diego restaurants by points computed from the County's own inspection
record over the past year:

- 19 points per employee-hygiene citation;
- 16 points per food-source citation;
- 12 points per food-temperature citation;
- 5 points per hand-washing citation;
- 2 points per point the average routine score over the last two years fell below 100;
- 1 point per point the last routine score fell below 100.

Restaurants with 41 points or more (the band, about the top 18% of scored restaurants) had a major
violation at their next routine inspection **at about twice the rate of other restaurants**: 37.2%
against 17.8% in the backtest. The rule is fully transparent, and each restaurant's worksheet
shows exactly how its points add up from the County's record. Most inspections that find a major
violation still end with an A, and 94% did; the County requires each major to be corrected during
the inspection.

## Intended use

| | |
|---|---|
| **For** | City of San Diego staff: seeing which restaurants' records point to a likely major violation at the next routine inspection, district by district; monthly worklists; conversations with the County about where attention could go first. |
| **Access** | Internal. The API needs a key ([API.md](API.md)). The public site ships an invented sample, and a real export reaches it only through every gate in [PUBLISHING.md](PUBLISHING.md). |
| **Not for** | Any statement that a restaurant is unsafe; replacing the County's grade card, schedule or risk categories; places outside the City of San Diego; kinds of facility other than restaurants (markets and limited-preparation food service are listed with their records, but not scored). |

## Data

- **Source.** SD Food Info, the County's published inspection results: 16,728 facilities and
  102,762 inspection records, from 2023-01-03 to 2026-09-19. The data was pulled with
  `fetch_sdfood.py`, which identifies itself, rate-limits, and stops for good on a refusal.
- **Data rules** (`export_site.load_places`, tested; shared with the research CSV):
  - "No Access", "Self Closed" and "Status Verification" visits are not inspections (5,403
    records).
  - A routine visit within 30 days after a B, a C or a closure is a re-grade or reopening (1,823).
  - For the model, same-day records of one type are one visit (4,949 merged). For display, every
    County record is shown as published.
  - 0 means "not scored". Grades are the County's, and never derived.
  - Severity tiers come from the status text, and themes from the item text (the mobile-unit report
    numbers its items differently).
  - A closure is an episode with a reason, and `reopened` records whether the County's "Approved to
    Reopen" visit ended it.
- **Listed places.** Restaurants, limited-preparation food service, and markets with a deli or food
  processing, inside the City (SANDAG council districts), visited in the last 18 months, with an
  unexpired permit. 5,386 as of 2026-09-20.
- **Scored places.** Restaurants with two rated routine inspections in the last two years: 3,653.

## The rule

- **Snapshots.** On the first of each month, every active restaurant county-wide is described by its
  record in the year before, and labelled by its first routine inspection in the year after. Each
  feature means the same thing at every snapshot.
- **What it reads.** Counts and score deficits from the place's own record. It reads no ZIP code,
  no neighbourhood, and no kind of place. It also reads nothing from complaint visits: a
  reinspection that follows a complaint visit does not count. A routine visit that ended in a
  closure order counts as a score of 70 in the averages the rule reads; it is never displayed.
- **Candidates, simplest first.**
  - **The average-score rule:** points = how far the average routine score fell below 100.
  - **The count score:** non-negative weights fitted on up to six counts, then rounded to whole
    points, with one point below 100 as the unit.
  - **Yardsticks:** logistic regression, monotone gradient boosting, and a monotone additive model.
- **Selection.** Publish the simplest candidate within 0.01 AUC of the best model at both
  validation origins (2025-03-01 and 2025-06-01). Neither publishable candidate was within 0.01 at
  both, so the more accurate one, the count score, is published, and the report flags it. The
  confirmation origin (2025-09-01) had been looked at while the pipeline was built, so the
  prospective test is the one that counts (below).
- **Frozen.** The rule published is the rule tested: the weights fitted at the confirmation origin
  (monthly snapshots 2024-02 to 2024-09, county-wide restaurants; scores read over two years, citations over one).

## Results

AUC among eligible restaurants:

| origin | average score | count score | logistic | boosted | additive | persistence |
|---|---|---|---|---|---|---|
| 2025-03-01 | 0.698 | 0.706 | 0.710 | 0.713 | 0.712 | 0.690 |
| 2025-06-01 | 0.692 | 0.690 | 0.707 | 0.707 | 0.709 | 0.687 |
| 2025-09-01 | 0.679 | 0.678 | 0.690 | 0.686 | 0.689 | 0.676 |

The yardsticks sit about 0.004 to 0.019 above the transparent rules, a small price for a rule
anyone can check by hand.

**The band at the confirmation origin (2025-09-01).** 3,481 eligible restaurants; 3,567 City
restaurants had a routine inspection in the following year, and 761 of them found a major.

| | places | had a major at the next routine inspection | 95% interval | kept in refits |
|---|---|---|---|---|
| Band (41 points or more) | 618 | 37.2% | 33.4% to 41.3% | 93% |
| Other scored restaurants | 2,863 | 17.8% | 16.4% to 19.3% | |

- **Why there is one band.** Bands are cut at whole point values, so a tie is never split. Adjacent
  bands whose intervals overlap are merged. At this origin the top 2.5%, 7.5% and 17.5% of the list
  could not be told apart, so they form one band.
- **Refits.** Across 30 refits on resampled training data, 93% of today's band stayed in it.
- **The persistence ordering.** Ranking by each restaurant's recent majors and scores reaches a
  similar rate in a group of the same size (37.8%). The rule is a transparent way to see the
  County's record, not a replacement for it.

**Where the band lands.** The report tabulates, by council district, how many restaurants are in
the band and how many of those had a major at the next inspection. Precision was highest in
Districts 8 (52%) and 3 (50%), and lowest in District 4 (15%, of 21).

## What the label is made of

- 99.3% of graded routine inspections are an A, including 94.2% of those that found a major.
- Scores gather at the A line: 2,930 routine inspections scored exactly 90, and 3 scored 89.
- A major follows a major 29.9% of the time, against 10.9% after a clean routine inspection.
- Different businesses at one address agree more on the same day than on different days. The
  record doesn't say which inspector made a visit, so inspector territories would sharpen any
  rule. The outreach asks the County for them.
- The share of routine inspections with a major rose from 8.9% (2023 Q1) to 15.9% (2026 Q3).
- **Survivorship.** SD Food Info lists facilities that exist today, so the backtest holds places
  that survived to the pull. An official extract that includes inactive permits would remove this.

## Publishing, and monitoring

The staff API is internal. Publishing names on the public site requires every gate in
[PUBLISHING.md](PUBLISHING.md):
- a signed approval bound to the run and file;
- notice to each named place;
- a band clearing the cost ratio and beating the baseline's same-size group;
- district parity;
- a registered frozen run that holds up on the inspections after it.

As of this run the public site stays on its sample.

Each run is archived with a manifest of hashes. `export_site.py --register` names the frozen run
for the prospective test, and `export_site.py --monitor` scores archived runs against the routine
inspections made since.

## Authors

Independent student research by Chenhao Zhang and Ayan Pendharkar (Canyon Crest Academy), not
affiliated with or endorsed by the County of San Diego.
