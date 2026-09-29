# A silent pilot: pre-registered design

A proposal the City of San Diego can bring to the County's Food, Water and Housing Division. In its
first phase nothing about any inspection changes. Every number below comes from
`sim_schedule.py` and `export_worklist.py` on the County's public results (SD Food Info),
2023-01 to 2026-09 (the 2026-09-19 pull, rerun 2026-09-27); see the README.

## The question

If a council district's routine inspections for a month were worked in the list's order,
would major violations be found sooner than in the order actually worked? In the backtest,
ordering each district's month by the one-line rule (lowest mean routine score on record
first) finds them **5.8 days sooner** (95% CI 5.4 to 6.1), and the research model **6.4
days** (6.0 to 6.7): about 2% of the 277–303 days between a facility's routine inspections. It
is detection within a month's schedule, not prevented illness. The pilot checks this going
forward, on the County's own schedule.

## Silent phase: three months

1. **Before each month**, `python export_worklist.py --month <yyyy-mm>` writes one list per
   council district: the facilities estimated due that month (below), in the students' point
   rule's order. Only the kinds of place the site lists appear: restaurants, limited-preparation
   places and markets with food prep, never a private home (home kitchens, cottage food), a
   health-care kitchen, a school or a food truck at its commissary, which follow other rules. It also writes a read-only, timestamped copy with a sha256 manifest
   (`data/worklists/<yyyy-mm>/frozen/<stamp>/`), including `scoring.csv`, which holds every
   active facility's position under each arm. The manifest's hashes are emailed to the County
   before the month starts; `python export_worklist.py --verify <frozen dir>` checks them later.
2. **The County's inspection supervisors, for all nine districts if possible and at least three,** receive their
   district's frozen list (the sizes come from the power section below). **Inspectors change
   nothing**: the list is not used to schedule, assign, reorder or skip any inspection.
3. **After three months**, the County shares the routine inspections done in those districts
   and months (below), and the analysis runs once, as written here.

**A lighter first step (phase 0).** A supervisor who holds a named list may feel bound to act on
what it shows (four closures for vermin, say), and acting on it would change the comparison. So the
County need not receive the lists at all at first: the lists are frozen each month and their hashes
sent to a neutral party (or to the County, unopened), and the result is scored afterwards from the
public record. The County is asked only for its inspector territories and its actual due lists. The
supervisors' part begins only if phase 0 shows a head start worth testing.

**Due this month (an estimate).** The public record has no schedule. A facility is listed when,
on the month's last day, the days since its last routine inspection reach its business type's
median interval between routine inspections (a Kaplan–Meier median that counts still-open
intervals) minus 30 days. In the backtest over 2025-01 to 2026-08, **67%** of each month's City
routine inspections (at facilities already on the record) were on that month's list, and 32% of a
list was inspected that month: a list runs about 2.1 times a month's volume. With the County's schedule this estimate is replaced by the real one.

## Arms: orders compared on the same inspections

- **Usual order:** the dates the inspections were actually done. In 2025-26 it put an inspection
  that found a major ahead of a clean one in the same district-month no more often than chance
  ([COUNTY_METHOD.md](COUNTY_METHOD.md)); the pilot checks that again on the County's own schedule.
- **The list as sent:** places meeting the County's own criteria for a closer look (two or more
  health closures, the same major item at two or more routine inspections, or two or more routine
  scores below 90, in two years) first; then everything on one scale, 100 minus the mean routine
  score: the students' point rule's points where it scores a place, the one-line rule's where it
  does not.
- **The one-line rule alone:** lowest mean routine score on record first.
- **The research model** (`model_food.py`), frozen in `scoring.csv`.
- **Persistence** (prior-year majors, then the last score), for reference.

## Outcomes

- **Primary: is the one-line rule's head start more than 2 days?** The routine inspections
  actually done in a district-month are re-slotted onto the same dates in each arm's order (tied
  positions share their dates), exactly as in `sim_schedule.py`. For each district-month, the
  head start is the mean number of days earlier that inspections finding a major would have been
  reached than in the usual order. **Test, fixed now:** a one-sided t-test at 5% of "the mean
  head start over district-months is 2 days or less". The pilot supports the list only if it
  rejects that, i.e. if the one-sided 95% lower bound is above 2 days. A bootstrap over
  district-months is reported alongside.
- **Why a 2-day bar and not zero.** A test against zero passes for any order better than chance,
  and the backtest already shows that (it is the ranking's AUC restated; README). What a pilot can
  still learn is whether the head start survives going forward, with a list made on the 1st that
  holds only about two thirds of the month's inspections, by enough to act on. Two days is the
  smallest head start this design treats as worth acting on: about 0.7% of the 277–303 days
  between a facility's routine inspections.
- **Secondary:** (a) the head start summed over the majors found (the facility-days by which
  major violations were found, and so corrected, sooner); (b) majors per inspection in the first
  half of each order; (c) recall by income
  quartile: the share of each quartile's majors in the first 20% of each order, by ZIP median
  income quartile and by %-Hispanic tercile (ACS, as `fairness_check.py`).
- **Reported alongside:** how many of the month's routine inspections were on the list, and how
  much of the list was inspected. If the County can share time on site, majors found per
  inspection-hour too; the public record has no hours.
- **Rules fixed now:** routine inspections only (follow-ups and re-inspections excluded); a
  facility inspected but not on its district's list takes its frozen position in `scoring.csv`;
  a facility missing from `scoring.csv` (a new permit) is placed as a typical A (97) with no card
  points and at the median model position.

## Power

From the 184 City council district-months of 2025-26 with at least one major (median 10 majors
each). Per district-month, the one-line rule's advantage over the order worked has mean **+5.7
days** and SD **4.2 days**.

**The primary test** (head start above 2 days, one-sided 5%, 80% power), by how large the head
start really is going forward:

| if the true head start is | district-months needed (normal approximation) | power by resampling the observed district-months (t-test) |
|---|---|---|
| as in the backtest, +5.7 d | 9 | 0.63 with 6, 0.81 with 9, 0.91 with 12, 1.00 with 27 |
| +4 d (it shrinks by about a third) | 28 | 0.26 with 6, 0.49 with 12, 0.80 with 27 |
| +3 d | 111 | 0.11 with 6, 0.33 with 27, 0.40 with 36 |

**The design: all nine districts for three months (27 district-months).** That clears the bar if
the backtest's head start holds (power 1.00) and still has 0.80 power if it shrinks to 4 days.
Three districts for three months (9) is the minimum, enough only if nothing shrinks. The silent
phase costs no more than sending the lists, so there is no saving in asking for fewer districts.
A head start near 3 days can't be told from the 2-day bar at any practical size; the pilot would
report it as not shown.

For comparison, other questions (two-sided 5%, 80% power):

| to detect | district-months needed (normal approximation) | power by resampling (t-test) |
|---|---|---|
| any head start of the backtest's size (+5.7 d) against zero | 5 | 0.31 with 3, 0.80 with 6, 0.95 with 9 |
| a 2-day head start against zero | 36 | 0.15 with 6, 0.32 with 12, 0.70 with 27 |
| a 2-day difference between the model and the rule (SD of the difference 1.7 d) | 6 | |
| the backtest's model-over-rule difference (+0.5 d) | 86 | |

Separating the research model from the one-line rule would take about 86 district-months (all
nine districts for about ten months), and this pilot does not try: the rule is the primary arm.
(The list as sent is scored with the rule's spread as a proxy.)

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
- Council districts stand in for the County's unit of assignment, which it does not publish
  (probably an inspector's territory). With the County's data we would use its actual inspector
  assignments.
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

- The pilot uses only **County-internal lists**; anything public is counts only (`dashboard.html`). District lists go only to the
  participating inspection supervisors.
- **The City staff site.** While the pilot runs, no band, point or list from the staff site (or the
  staff API) may reach an inspector, a supervisor or a business: the pilot would then measure the
  list's influence, not its accuracy. The staff site says so in a banner during the pilot, and its
  access log records each place opened; the analysis reports the primary result both with and
  without the inspections at places staff looked at in the month before.
- **We will not publish a named list.** The public website in `food-dashboard/` shows only
  invented sample data, and no real names are published from the County's data without the
  County's review. Lists held by the City or the County are their records and may be released under
  the Public Records Act; the pilot does not depend on keeping them confidential.
- The frozen copies are read-only and hashed; the analysis uses them, never a later rerun.

## Contacts

- **Project point of contact (an adult, not a student):** `[NAME, ROLE, EMAIL, PHONE: to be filled in before the County is contacted]`
- **County contact:** `[Food, Water and Housing Division contact, once agreed]`
- **Authors:** Chenhao Zhang and Ayan Pendharkar, students at Canyon Crest Academy. Independent
  research, not affiliated with or endorsed by the County of San Diego.
