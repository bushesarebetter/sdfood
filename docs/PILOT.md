# A silent pilot: pre-registered design

A proposal the City of San Diego can bring to the County's Food & Housing Division. In its
first phase nothing about any inspection changes. Every number below comes from
`sim_schedule.py` and `export_worklist.py` on the County's public results (SD Food Info),
2023-01 to 2026-09; see the README.

## The question

If a council district's routine inspections for a month were worked in the list's order,
would major violations be found sooner than in the order actually worked? In the backtest,
ordering each district's month by the one-line rule (lowest mean routine score on record
first) finds them **5.8 days sooner** (95% CI 5.5 to 6.2), and the research model **6.2
days** (5.9 to 6.6). The pilot checks this going forward, on the County's own schedule.

## Silent phase: three months

1. **Before each month**, `python export_worklist.py --month <yyyy-mm>` writes one list per
   council district: the facilities estimated due that month (below), in the published rule's
   order. It also writes a read-only, timestamped copy with a sha256 manifest
   (`data/worklists/<yyyy-mm>/frozen/<stamp>/`), including `scoring.csv`, which holds every
   active facility's position under each arm. The manifest's hashes are emailed to the County
   before the month starts; `python export_worklist.py --verify <frozen dir>` checks them later.
2. **One or two district supervisors** receive their district's frozen list. **Inspectors change
   nothing**: the list is not used to schedule, assign, reorder or skip any inspection.
3. **After three months**, the County shares the routine inspections done in those districts
   and months (below), and the analysis runs once, as written here.

**Due this month (an estimate).** The public record has no schedule. A facility is listed when,
on the month's last day, the days since its last routine inspection reach its business type's
median interval between routine inspections minus 30 days. In the backtest over 2025-01 to
2026-08, **72%** of each month's City routine inspections (at facilities already on the record)
were on that month's list, and 28% of a list was inspected that month: a list runs about 2.6
times a month's volume. With the County's schedule this estimate is replaced by the real one.

## Arms: orders compared on the same inspections

- **Usual order:** the dates the inspections were actually done.
- **The list as sent:** the published point card's points first, then the one-line rule for
  places the card does not score.
- **The one-line rule alone:** lowest mean routine score on record first.
- **The research model** (`model_food.py`), frozen in `scoring.csv`.
- **Persistence** (prior-year majors, then the last score), for reference.

## Outcomes

- **Primary: days to find a major, within the district-month.** The routine inspections actually
  done in a district-month are re-slotted onto the same dates in each arm's order (tied
  positions share their dates), exactly as in `sim_schedule.py`. For each district-month, the
  mean number of days earlier that inspections finding a major would have been reached than in
  the usual order. Summary: the mean over district-months, with a t-interval and a bootstrap
  over district-months.
- **Secondary:** (a) majors per inspection in the first half of each order; (b) recall by income
  quartile: the share of each quartile's majors in the first 20% of each order, by ZIP median
  income quartile and by %-Hispanic tercile (ACS, as `fairness_check.py`).
- **Reported alongside:** how many of the month's routine inspections were on the list, and how
  much of the list was inspected.
- **Rules fixed now:** routine inspections only (follow-ups and re-inspections excluded); a
  facility inspected but not on its district's list takes its frozen position in `scoring.csv`;
  a facility missing from `scoring.csv` (a new permit) is placed as a typical A (97) with no card
  points and at the median model position.

## Power

From the 184 City council district-months of 2025-26 with at least one major (median 10 majors
each). Per district-month, the one-line rule's advantage over the order worked has mean **+5.8
days** and SD **4.4 days**.

| to detect (two-sided 5%, 80% power) | district-months needed (normal approximation) | power by resampling the observed district-months (t-test) |
|---|---|---|
| an advantage of the backtest's size (+5.8 d) | 5 | 0.32 with 3, 0.79 with 6, 0.94 with 9 |
| a 2-day advantage | 38 | 0.14 with 6, 0.31 with 12, 0.67 with 27 |
| a 2-day difference between the model and the rule (SD of the difference 1.8 d) | 7 | |
| the backtest's model-over-rule difference (+0.3 d) | 325 | |

Two districts for three months (6 district-months) can confirm an advantage near the backtest's
size. Confirming a 2-day minimum takes about all nine districts for four months. No practical
silent pilot can separate the research model from the one-line rule, and this one does not try:
the rule is the primary arm. (The list as sent is scored with the rule's spread as a proxy.)

## Later: a randomized active phase (optional)

If the silent phase shows earlier detection, the County could randomize **district-months**, not
facilities (facilities share inspectors and routes), to "work the month in the list's order" or
"usual order", stratified by district. Primary outcome: the mean day of the month on which
majors are found. Under the usual order that averages day 14.5 with an SD of 3.8 days across
district-months, so detecting a 2-day difference takes about **57 district-months per arm**.
Secondary: majors per routine inspection, recall by income quartile, inspections completed per
month, and driving time.

## Assumptions

- A facility's finding does not depend on which day of the month it is inspected.
- Reordering ignores routing: a reordered month may cost more driving. The active phase measures it.
- Council districts stand in for the County's real unit, an inspector's territory. With the
  County's data we would use its actual inspector assignments.
- The public data hold only facilities that exist today (survivorship; see the README).

## What the County would need to share

- For the pilot districts and months: each routine inspection's facility, date and findings, and
  the **inspector or territory id**, which separates a place from its inspector.
- **The actual schedule:** how routine inspections are assigned, the month's planned list, and
  any order it was worked in.
- Ideally the full inspection history **including inactive and closed permits**, which removes
  the survivorship gap. A records request template is at the end of `outreach.md`.

## Stopping and fairness monitoring

- **Silent phase:** nothing changes, so there is nothing to stop. Each month the monitor reports,
  by income quartile and %-Hispanic tercile, the share of majors in the first 20% of the list's
  order and of the usual order. A gap of more than 10 points against any group in two consecutive
  months goes to the County before any active phase.
- **Active phase:** a district-month arm stops if, after three months, majors are found later
  than in the usual order (the CI lies below zero); if the coverage gap above persists for two
  months; if routine inspections completed per month fall by more than 5%; or whenever the County
  asks. No facility is skipped or visited less often: the list reorders visits within the
  County's required schedule.

## Keeping the study clean

- The pilot uses only **de-identified or County-internal lists**. District lists go only to the
  participating supervisors. City staff who use the internal API should not pass district lists
  to inspectors or businesses during the pilot.
- **No public list of names exists during the study.** The public website in `food-dashboard/`
  shows only invented sample data, and no real names are published from the County's data without
  the County's review. A public named list could change what businesses and inspectors do, and
  would contaminate the comparison.
- The frozen copies are read-only and hashed; the analysis uses them, never a later rerun.

## Contacts

- **Project point of contact (an adult, not a student):** `[NAME, ROLE, EMAIL, PHONE: to be filled in before the County is contacted]`
- **County contact:** `[Food & Housing Division contact, once agreed]`
- **Authors:** Chenhao Zhang and Ayan Pendharkar, students at Canyon Crest Academy. Independent
  research, not affiliated with or endorsed by the County of San Diego.
