# San Diego food-inspection risk targeting

Order each month's routine food inspections by each facility's own inspection record, so that
**major violations** (the County's term) are found sooner, with the same inspectors and the same
schedule. This is the classic "help a public agency allocate a scarce resource" setup (cf.
Chicago's food-inspection model).

**By Ayan Pendharkar** (research) **and Chenhao Zhang**, students at Canyon Crest Academy, San Diego. Independent: not affiliated with or endorsed by the
County of San Diego. The data were collected from the County's public SD Food Info search on 2026-09-19, pending an
official extract from the County. That pull ran before `fetch_sdfood.py` was changed to send an
identifying User-Agent (2026-09-22): it sent a browser User-Agent. Later pulls identify themselves.

## The short version

- **A one-line rule does most of the work.** Ranking routine inspections by each facility's mean
  routine score on record, lowest first, puts **48%** of 2025-26 major violations in the first
  20% of inspections, **2.4×** the base rate. Within a council district's month it finds them
  **5.8 days sooner** than the order actually worked (95% CI 5.4–6.1), which is 1.9–2.1% of the
  277–303 days between a facility's routine inspections.
- **The research model adds a little, and the data can tell.** Trained and scored as of the 1st of
  each month, as a monthly list would be, it puts **49%** in the first 20% (1.6 points more than the
  rule, 95% CI +0.4 to +2.7), ranks the whole list better (AUC 0.763 against 0.737; +0.026, +0.022
  to +0.031), and finds major violations **6.4 days sooner**: 0.6 day more than the rule (0.5–0.7),
  about 0.2% of the gap between routine inspections.
- **The baseline is the County's own order, and it does not already rank by risk.** Within a
  district's month, the order the County actually worked puts an inspection that found a major
  ahead of a clean one 50.7% of the time (95% CI 49.1–52.1%), where chance is 50%. The County
  says it "prioritizes inspections based on relative risk"; in its record that shows up in how
  often a kind of place is visited, which this project leaves alone ([docs/COUNTY_METHOD.md](docs/COUNTY_METHOD.md)).
- **Coverage by neighborhood income: no detectable difference.** The model found 46% to 52% of
  each ZIP-income quartile's major violations, the rule 44% to 52%. Lowest minus highest quartile:
  model +3.4 points (95% CI −4.6 to +11.7), rule +4.6 (−4.1 to +13.5). Both intervals cover zero,
  so the data cannot tell the groups apart; that is not proof of evenness (FAIRNESS.md).
- **What "days sooner" is.** Within a month it is the ranking's AUC restated (about
  24 × (AUC − 0.5) days in a district's month), and 6 days is about 2% of the 277–303-day gap
  between routine inspections. It is detection latency within an already-scheduled month, not
  prevented illness, which the public record cannot measure. The case for it is that a major found
  sooner is corrected sooner, at no cost in inspections: summed over the majors, the rule's head
  start is about 13,800 facility-days a year (95% CI 12,900 to 14,700), if each violation was there
  from the 1st (outreach.md, "Will it prevent food poisoning?").
- **For the City and the County:** monthly worklists per council district (`export_worklist.py`)
  and a pre-registered silent pilot the City can propose to the County ([docs/PILOT.md](docs/PILOT.md)).

Every figure in this README, FAIRNESS.md, outreach.md, docs/ and the dashboard was regenerated on
2026-09-27, after the September 2026 fixes (training and scoring as of the 1st of the month, closures
read as 70, two-year persistence, time-based early stopping, Kaplan–Meier due dates, whole-ZIP
fairness intervals, a feedback test that deletes skipped inspections), from the 2026-09-19 pull
(inspections through 2026-09-18). What the docs say about the County's own method was checked
against the County's published sources the same day ([docs/COUNTY_METHOD.md](docs/COUNTY_METHOD.md)).

## What changed (September 2026)

### The data

The inspection table every script reads (`data/sd_inspections.csv`) is built with the same data
rules as the public site's exporter (`export_site.load_places`, tested). From the same pull:

- **5,403 records that were not inspections are gone:** 3,785 "Status Verification" checks,
  1,617 "No Access" / "Self Closed" visits where the inspector could not inspect (1,436 of them
  routine) and 1 incomplete record. They had counted as inspections with no violations, and a
  routine one left a score of `0` in the facility's history.
- **1,823 "routine" visits are now `Follow-up`:** a routine within 30 days after a routine scored
  under 90 (a B/C) or after a closure order is the County's re-grade or reopening visit. The 359
  re-grades came a median 6 days after the B/C and found a major 3% of the time; the 1,464
  reopenings came a median 1 day after the closure order (a major 6% of the time). They are no
  longer routine labels, and their scores are not the facility's routine score.
- **4,948 same-day records of one type were merged** (grocery departments are inspected as separate records).
- **102,755 rows → 92,404 inspections**, 15,870 businesses, 2023-01-03 → 2026-09-18. A routine
  inspection's history features read strictly earlier dates only.

The authors also rebuilt the old rules on the same pull and recovered the figures published
earlier; the script for that check is not in the repository, so its numbers are not repeated here.

### The model, the comparison and the deliverable

| headline (2025+ forward test) | as published earlier in September | now (trained and scored as of the 1st) |
|---|---|---|
| Model features | since-2023 history, ZIP, permit age as of the pull | since-2023 history, **no ZIP, no permit age** |
| Model ROC-AUC | 0.756 | **0.763** |
| Model: top 20% → share of major violations | 48.2% | **49.4%** |
| One-line rule: top 20% → share | 48.3% | **47.8%** |
| Days sooner within a district's month: model / rule | +6.2 / +5.8 | **+6.4 / +5.8** |
| Model's coverage of majors, lowest vs highest income quartile | 42% vs 58% | **52% vs 49%** (gap 95% CI −4.6 to +11.7 points) |
| Model's flag rate, low- vs high-income ZIPs | 0.61× | **0.97×** (0.74–1.24) |

- **Permit age removed (a leak).** `opened_date` is the permit in force when the data were
  collected. A permit reissued after an inspection (a change of owner, say) gave 171 training
  inspections a negative age; they found a major 23.4% of the time against 11.4%. Dropping the
  feature changes AUC by +0.001 (95% CI −0.001 to +0.003) and the top-20% share by +0.1 points
  (−0.7 to +1.0): the published figures were not inflated by it. Setting only the impossible ages
  to missing was tested too (47.8% in the top 20%), but a blank still marks a later reissue, so
  the feature is gone.
- **ZIP removed.** With ZIP the model ranks slightly worse: AUC −0.006 (−0.011 to −0.002),
  top-20% share −2.5 points (−3.9 to −1.1), days sooner −0.2 (−0.3 to −0.0), all "with minus
  without". With ZIP it also covered the major violations of the lowest-%-Hispanic ZIPs better than
  those of the highest (57% against 41%; gap +16.3 points, +2.4 to +29.3), the only coverage gap
  in the audit the data can detect (FAIRNESS.md). The research model now matches the public site's
  card, which never used ZIP.
- **12-month history tested; since-2023 history kept.** See "History window" below.
- **The one-line rule leads,** the research model second, persistence as the reference. The model
  is measurably better than the rule, but by little, and the rule needs no model.
- **The dashboard's "risk × overdue" ranking was backtested and replaced.** It found major
  violations 5.3 days sooner within a district's month, against 5.8 for the rule and 6.4 for the
  model, so worklists now use the rule's order.
- **The research dashboard publishes counts only.** It used to embed one row per active facility
  (type, risk, history bands, months since the last visit). 80% of those rows were unique and
  could be matched to named businesses in SD Food Info, so `dashboard.html` now shows counts by
  type and risk band, gated by `privacy_gate.py`. Old versions stay in git history until
  `tools/purge_history.sh` is run ([docs/PUBLISHING.md](docs/PUBLISHING.md)).
- **Survivorship stated and bounded** (below), **monthly worklists** for the City's council
  districts with a frozen copy for a pilot (`export_worklist.py`), a pinned environment
  (`requirements.txt`), and one shared feature library (`model_food.py`) that every research
  script imports, so a fix lands everywhere.

## What this is

The County says its inspection methodology "prioritizes inspections based on relative risk" (SD
Food Info). It publishes no inspection frequencies and says nothing about the order of a month's
inspections, so what follows is measured from its record and labelled as such
([docs/COUNTY_METHOD.md](docs/COUNTY_METHOD.md) sets every claim beside the County's own sources):

- **How often depends mostly on the kind of place.** A school processing kitchen's next routine
  inspection comes a median 185 days later, a restaurant's 312, a pre-packaged market's
  361 (`model_food.py`); school processing facilities get about 2.3 routine inspections a
  year against a 1.5 median.
- **A facility's own record moves it a little.** The next routine comes a median **277 days** after
  one that found a major against **303** after one that did not; across the 4,746 facilities on the
  record for three years or more, the correlation between a facility's routine major-violation rate
  and its routine inspections per year is −0.07.
- **Within a month, the order shows no risk ordering** (above). Follow-up visits respond to
  findings: a B or C is re-graded within 30 days (County Code §61.107(b)).

This project orders routine inspections **within the County's required schedule** by each facility's
record. It does not change how often any facility is inspected.

## Data

SD County DEH inspection results, from the official **sdfoodinfo.org** app's public JSON search
(`/restaurants/search.htm`): public-record data, pulled on 2026-09-19 with rate limits
but a browser User-Agent. `fetch_sdfood.py` now identifies itself (`SDFOOD_CONTACT`) and records
`data/pull_meta.json`; the current data predates that. For any pilot the County's official
extract should replace it.

- **92,404 inspections**, 15,870 facilities, **2023-01-03 → 2026-09-18** (~3.7 yr).
- **64,081 routine** inspections (18,669 in 2025); plus 21,943 re-inspections, 4,557 complaint
  visits and 1,823 follow-ups (re-grade or reopening visits).
- Per inspection: type, status, score, grade, date, counts of major, minor and good-retail-practice
  items, and closure orders with a reason. `score` is set only for real routine scores.
- **Survivorship:** SD Food Info lists only facilities that exist today (below).

## Model and evaluation

- **Target:** at each *routine* inspection, `major violation found` (12.1% overall).
- **Features, all from strictly earlier dates:** business type, month, and the facility's
  history on the record since 2023-01: prior visits, days since the last one, last and mean
  routine score, prior major-violation rate, mean violations per visit, whether the last visit
  found a major. No ZIP, no permit age.
- **Forward-in-time test:** trained on **Jan 2023 – Dec 2024** (31,533 routine), tested on
  **Jan 2025 – Sep 2026** (32,548 inspections the model never saw; 4,114 found a major).
- **Trained and scored as deployed.** A monthly list is scored on the 1st, and its model is
  trained on routine inspections read the same way, so every headline figure trains and scores on
  each inspection's history as of the 1st of its month (`model_food.month_start_rows` and
  `fit_as_deployed`, the function the worklist uses). Only 0.8% of test inspections had a visit
  between the 1st and the inspection, so the inspection-date figures (below, for comparison) are
  nearly the same.
- **Deployment model** (worklists, dashboard) is the same model fitted on **all** routine
  inspections before the list's month; the accuracy figures come only from the held-out test.
- **Orderings that need no model:** the **one-line rule** (mean routine score on record, lowest
  first); **persistence** (routine inspections with a major in the prior 12 months, then majors,
  then the lowest last routine score over two years; `export_site.persistence`); the last routine
  score; the mean routine score over the prior 12 months; the prior major-violation rate. A routine
  that ended in a health closure order reads as a score of 70, as on the published card. Ties at
  the cut are split pro rata (the expectation under a random order).

| 2025+ test, trained and scored as of the 1st | ROC-AUC | top 20% → share of major violations | precision in top 20% | lift |
|---|---|---|---|---|
| **One-line rule: mean routine score on record** | 0.737 | **47.8%** | 30.2% | 2.39× |
| **Research model** | **0.763** | **49.4%** | 31.2% | 2.47× |
| Last routine score alone | 0.725 | 46.7% | 29.5% | 2.34× |
| Persistence | 0.724 | 46.1% | 29.1% | 2.31× |
| Mean routine score, last 12 months | 0.698 | 43.2% | 27.3% | 2.16× |
| Prior major-violation rate | 0.640 | 42.8% | 27.1% | 2.14× |
| Routine calendar, no ordering | 0.500 | 20% | 12.6% (base rate) | 1× |

Trained and scored at the inspection date instead: model AUC 0.763 and 49.7%, rule 0.736 and
47.8%, persistence 0.723 and 45.9% (model PR-AUC 0.302, base rate 0.126). The model trained at the
inspection date but scored as of the 1st: 0.764 and 49.7%, +0.001 (95% CI −0.001 to +0.003) against
the deployed training, no detectable difference. Paired bootstrap over 15,847 facilities, 95% CIs,
as deployed:

- **The model beats the one-line rule, by a little:** AUC +0.026 (+0.022 to +0.031) and +1.6
  points of major violations in the top 20% (+0.4 to +2.7). At the inspection date: +0.026
  (+0.022 to +0.031) and +1.8 (+0.7 to +3.1).
- **The model beats persistence:** AUC +0.039 (+0.033 to +0.045) and +3.3 points (+2.0 to +4.8).
  The rule's point estimates sit between the two (AUC 0.737 against 0.724); that pair was not
  bootstrapped.
- **Stable across time:** rolling-origin AUC 0.747–0.763 for the model, 0.722–0.738 for the rule
  and 0.716–0.726 for persistence across three cutoffs, trained and scored as of the 1st.
- **Drivers (permutation importance):** business type, mean routine score on record, mean
  violations per visit, prior major-violation rate. Within type the gain holds: flagged
  restaurants find a major 32% of the time against 19% for all restaurants; retail markets with a
  deli 30% against 18%.
- **It reorders visits every facility already gets.** Nothing here skips a facility or lowers how
  often it is inspected.

### Calibration: the ranking holds, the probabilities run high

The ranking is well calibrated in shape (regressing the test outcomes on the model's log-odds gives
a slope of 1.08 against an ideal 1), but the predicted rates run 1 to 2.4 points above the actual
rate in every quarter of 2025 and early 2026 (actual minus predicted, 95% CI over facilities):

| test quarter | inspections | actual major rate | predicted | actual minus predicted |
|---|---|---|---|---|
| 2025 Q1 | 5,404 | 11.3% | 12.4% | −1.1 (−1.9 to −0.3) |
| 2025 Q2 | 4,317 | 12.1% | 14.5% | −2.4 (−3.3 to −1.5) |
| 2025 Q3 | 4,519 | 13.1% | 14.3% | −1.2 (−2.1 to −0.3) |
| 2025 Q4 | 4,429 | 11.5% | 13.7% | −2.2 (−3.1 to −1.3) |
| 2026 Q1 | 5,350 | 11.6% | 13.2% | −1.6 (−2.4 to −0.8) |
| 2026 Q2 | 4,875 | 14.2% | 15.3% | −1.1 (−2.0 to −0.1) |
| 2026 Q3 (to Sep 18) | 3,654 | 15.6% | 15.2% | +0.4 (−0.7 to +1.5) |

**Is history length a clock?** A facility's count of prior visits grows with the calendar, because
the record starts in 2023, so it could carry a time trend into the model. It does, but not the
rising major rate: within any one year the major rate still rises with prior visits, while each
bucket's rate falls from year to year (share of routine inspections with a major, all routine
rows, as of the 1st):

| year | 0 prior visits | 1 | 2 | 3–4 | 5+ |
|---|---|---|---|---|---|
| 2023 | 9.9% | 8.6% | 15.9% | 26.9% | 24.7% |
| 2024 | 8.9% | 10.0% | 12.3% | 15.0% | 28.4% |
| 2025 | 5.1% | 12.2% | 8.0% | 12.0% | 17.4% |
| 2026 | 7.1% | 10.3% | 9.2% | 10.4% | 18.1% |

Early in the record, a long history marks a troubled facility (many re-inspections in a short
time); later it marks mostly time on the record. Trained on 2023-24, the model reads long histories
as riskier than they now are: it over-predicts for facilities with 3–4 prior visits (−1.6 points,
−2.1 to −1.0) and 5+ (−1.6, −2.3 to −0.9), and for facilities new to the record (−3.1, −3.9 to
−2.2), and under-predicts for those with one prior visit (+2.4, +1.2 to +3.7). The ranking already
carries this drift and holds (AUC 0.763 on the same inspections); the probabilities are what read
high, so they are shown as risk bands, never as findings. The deployed model is refitted before each
month's list on everything up to it, so recent years weigh in; whether that closes the offset is for
the monitor to show. `model_food.py` prints the full tables.

### History window: since 2023, or the last 12 months?

The history features grow with the record: the median routine inspection had 0 prior visits on
record in 2023, 2 in 2024, 3 in 2025 and 4 in 2026 (left truncation). A **12-month-window
variant** reads the 365 days before each inspection, as the public site's exporter does, and
trains only on inspections from 2024-01-03, whose year is fully on the record.

| variant (same 2025+ test) | ROC-AUC | top 20% share | days sooner, district month |
|---|---|---|---|
| **Since-2023 history, no ZIP, no permit age (headline)** | **0.763** | **49.7%** | **+6.4** |
| Since-2023, with ZIP | 0.756 | 47.2% | +6.2 |
| Since-2023, ZIP, permit age missing when impossible | 0.756 | 47.8% | |
| As published: since-2023, ZIP, permit age as of the pull | 0.756 | 47.1% | +6.2 |
| 12-month window, no ZIP (trained 2024) | 0.739 | 42.7% | +5.8 |
| 12-month window, with ZIP (trained 2024) | 0.738 | 43.6% | |
| 12-month window, with ZIP, trained 2023-24 | 0.739 | 42.5% | |

(AUC and share trained and scored at the inspection date, where every variant is fitted; days
sooner trained and scored as of the 1st.)

**The headline uses since-2023 history.** A third of test routine inspections (32.6%) have no
routine score in the 365 days before them (a long gap, but also a closure or a first visit), so a
12-month window misses the one score that matters most; it costs 0.024 AUC (0.019 to 0.029) and
7.0 points of the top-20% share (5.6 to 8.6), whatever the training years. The since-2023 forward
test stays honest: every training row saw only what was on the record at the time, and the test
rows simply have longer histories. The same holds for the rule: the mean routine score over the
last 12 months does much worse than the mean on record (43.2% against 47.8%).

## Finding major violations sooner (the operational claim)

Working an already-scheduled batch of routine inspections in a ranked order finds major
violations sooner. Inspectors are assumed to work areas, not one county-wide pool (the County does
not publish how it assigns them), so the realistic batch is **a City of San Diego council district's
month** (outside the City, a ZIP3 area's month). The comparison is the order the County actually
worked, which puts majors first no more often than chance (above; [docs/COUNTY_METHOD.md](docs/COUNTY_METHOD.md)):

| ordering, within a district / ZIP3 month | major violations found sooner than the order actually worked | as a share of the 277–303-day gap between routine inspections | summed over the majors: facility-days a year |
|---|---|---|---|
| **One-line rule** | **+5.8 d** (95% CI 5.4–6.1) | 1.9–2.1% | 13,844 (12,914–14,738) |
| **Research model** | **+6.4 d** (6.0–6.7) | 2.1–2.3% | 15,272 (14,378–16,107) |
| Persistence | +5.5 d (5.1–5.8) | 1.8–2.0% | 13,083 (12,170–14,018) |
| The old dashboard's risk × overdue weighting | +5.3 d (4.9–5.8) | 1.8–1.9% | 12,796 (11,762–13,874) |
| Mean routine score, last 12 months | +4.8 d (4.3–5.2) | 1.6–1.7% | 11,406 (10,370–12,434) |

- The model adds **0.6 day** over the rule (0.5–0.7), about 0.2% of the routine gap, and **0.9
  day** over persistence (0.8–1.1), paired bootstrap over months. Clean facilities wait 0.8–0.9
  day longer: the reorder is zero-sum in inspection-days, so the facility-days a major is found
  sooner are the same facility-days a clean inspection waits.
- Trained and scored as of the 1st (above) or at the inspection date, the model's figure is the
  same +6.4 d.
- County-wide monthly pool: model +6.7 d, rule +6.0 d. A whole quarter treated as one pool: model
  +20.0 d, rule +18.1 d; the effect scales with the reorder window, which is why the honest number
  is the within-month one.
- **Assumptions:** a facility's finding does not depend on the day of the month it is inspected,
  and routing is ignored (a reordered month may cost more driving). Council districts stand in for
  the County's unit of assignment, probably an inspector's territory, which it does not publish and
  the record does not carry. The facility-days figure also assumes each major was there from the
  1st of its month.
- This is a **detection-latency** figure within an already-scheduled batch, not prevented illness
  and not a dollar figure.
- **What the number is.** Within a pool the gain for major violations is, to within a tenth of a
  day, (1 − base rate) × (AUC within the pool − 0.5) × the pool's span of days: every arm above
  fits about 24 × (AUC − 0.5). It restates ranking quality; it is not separate evidence. As a
  share of the 277–303-day gap between routine inspections, 6.4 days is about 2%.
- **It reorders the inspections that were actually done**, as if the month's schedule were known
  on the 1st. The estimated due list covers about 67% of a month's routine inspections and is about
  2.1 times the month's volume, so the list's own benefit is smaller than the simulation's.

## Survivorship

**SD Food Info lists only facilities that exist today, so every cohort here holds survivors.**
Only 12 of the 15,870 businesses in the data were last seen before 2025; a complete record would
hold every place that closed in 2023-24. The pull's permit status shows the few closing places
that remain: 198 of 16,728 businesses have an expired permit, and their 369 test inspections found
a major 21.4% of the time against 12.5%. In 2024, 1,292 permits were opened, 9.7% of the
facilities on the record by then; in a stable population about as many close each year.

**Bound** (`model_food.py`, inspection-date scores): add X% more test inspections from missing
facilities with the expired group's major rate, then re-cut the top 20%.

| missing inspections | ranked like the listed expired facilities: model / rule | worst case, all ranked last: model / rule |
|---|---|---|
| 0% (as measured) | 49.7% / 47.8% | |
| +5% | 49.3% / 47.7% | 47.1% / 45.3% |
| +10% | 48.6% / 47.4% | 45.3% / 43.6% |
| +20% | 47.7% / 46.9% | 41.1% / 40.3% |

Even with a fifth more inspections from vanished facilities, ranked as badly as possible, the top
20% of either ordering still holds about twice its share of major violations. The rule and the
model move together, so the comparison between them holds. The County's full records, inactive
permits included, remove the question.

## Fairness (see FAIRNESS.md)

Scored as of the 1st, with whole ZIPs per income group and 95% intervals that resample whole ZIPs:

- Actual major-violation rates are nearly flat across ZIP income (lowest quartile 0.95× the
  highest, 0.76–1.19), and so are the flag rates: model 0.97× (0.74–1.24), rule 1.08×
  (0.84–1.38), persistence 1.03× (0.83–1.29).
- Share of each income quartile's major violations in the top 20%: model 46% to 52%, rule 44% to
  52%, persistence 42% to 49%. Lowest minus highest quartile: model +3.4 points (−4.6 to +11.7),
  rule +4.6 (−4.1 to +13.5), persistence +5.4 (−2.9 to +14.2).
- **Every one of these intervals covers equality, so the audit finds no detectable difference** by
  income, and none by %-Hispanic tercile for the three orderings. With about 24 ZIPs per quartile
  it cannot rule out gaps of several points either way.
- Under the proposed within-district reordering, major violations surface 5.8 to 6.8 days sooner
  across income quartiles with the model and 5.2 to 6.2 with the rule, with overlapping intervals.
- False-positive rates by quartile: model 15.0% to 16.8%, rule 14.8% to 17.1%. The rule's is 16.7%
  in the lowest-income quartile against 15.3% in the highest; the per-group intervals overlap, and
  the audit does not estimate the difference itself.
- The model's predicted rate runs 1.3 to 1.5 points (10–12% relative) above the actual rate in
  every quartile: the same over-prediction as everywhere in the test ("Calibration" above), not a
  group difference.
- Setting a separate cut per income group to equalize coverage does not pay: set on 2025 and
  applied to 2026, it flags 1.7 more points of all inspections (95% CI +1.3 to +2.1) and leaves
  recall spread across groups at 9.1 points against 10.8 (FAIRNESS.md).
- The model with ZIP, which is not used, shows the audit's one detectable gap (above).

Keep routine inspections everywhere and monitor coverage by group in use.

## Feedback loop (see feedback_check.py)

The labels, and every facility's record, come from the inspections that get done, so targeting
could go blind to places it stops visiting. `feedback_check.py` deletes skipped inspections and
their follow-ups within 45 days from the record over four quarterly rounds of 2024, rebuilds the
model, the rule and persistence from what is left (each round chosen as a list made on the 1st
would be), and scores all three on 2025+. The test inspections are the same in every arm, so each
loss against arm A has a paired 95% interval over facilities:

| AUC on 2025+ | A: every inspection kept | B: only the model's top 40% inspected (change from A, 95% CI) | C: top 40% plus a random 15% of the rest, 3 seeds (change from A) |
|---|---|---|---|
| Model | 0.763 | 0.756 (−0.007, −0.010 to −0.004) | 0.756 (−0.006, −0.009 to −0.004) |
| One-line rule | 0.737 | 0.722 (−0.015, −0.018 to −0.011) | 0.725 (−0.012, −0.015 to −0.009) |
| Persistence | 0.724 | 0.709 (−0.014, −0.018 to −0.011) | 0.713 (−0.011, −0.014 to −0.008) |

Inspecting only the model's picks (arm B removes 9,622 routine inspections, and the mean time since
a facility's last visit in 2025+ rises from 266 to 340 days) costs every ordering a detectable
loss, and the rule and persistence, which read the same thinned record, lose about twice what the
model does: their intervals do not overlap the model's. A random 15% on top (arm C) gives a little
back. Coverage by income quartile moves by at most 3 points. This concerns an inspect-less policy the project does not propose; reordering within the
schedule removes no inspection (arm A).

## Monthly worklists for the City's council districts (`export_worklist.py`)

For a month (by default the one after the data end), one CSV per council district in
`data/worklists/<yyyy-mm>/`, the source the staff API serves:

- **Who is due** is estimated, since the public record has no schedule: a facility is listed when,
  by the month's end, the days since its last routine inspection reach its business type's
  routine interval (a Kaplan–Meier median that counts still-open intervals) minus 30. In a backtest
  over 2025-01 to 2026-08, **67%** of each month's City routine inspections (at facilities already
  on the record) came from that month's list, and 32% of a list was inspected that month: a list
  runs about 2.1 times a month's volume. For October 2026: 2,029 facilities across the nine
  districts.
- **The order:** the published point card's points first (the site's rule, below), then places
  the card does not score by the one-line rule. Each row says why it sits where it does.
- **A frozen copy** (read-only, timestamped, with sha256 hashes and every active facility's
  position under each ordering) lets a silent pilot be scored later against exactly what was sent:
  [docs/PILOT.md](docs/PILOT.md). The pilot's primary test is whether the rule's head start is
  above 2 days, not above zero; all nine districts for three months give it 0.80 power even if the
  head start shrinks from the backtest's +5.7 d to +4 d.

## Two sets of numbers

This repository reports two models, and they answer different questions:

- **The research model and one-line rule** (this section): each *routine inspection* in 2025-26,
  county-wide, every facility type; "was a major found at this inspection?", scored against the
  order the inspections were actually done.
- **The published point card** (the section below, and docs/MODEL_CARD.md): monthly snapshots of
  *City restaurants*, each described by its scores over the two years before and its citations over
  the year before, and "will its next routine inspection within a year find a major?"; published as bands.

Both rest on the same finding: a facility's own routine record is a strong guide to where major
violations will be found.

## Scope

- About 3.7 years of public history, all of it at facilities that still exist.
- The label is what inspectors *found*, a measurement of risk rather than risk itself, and the
  public record carries no inspector id, so a place and its inspector can't be separated yet.
  Inspector or territory ids from the County are the fix.
- The County's internal records would let the pilot use real schedules and inspector territories.

## Reproduce

`model_food.py` holds the shared loader, features, variants and model; every research script
imports it. `model_food.py`, `sim_schedule.py`, `fairness_check.py`, `threshold_tradeoff.py`,
`feedback_check.py` and `export_worklist.py` write their numbers to `data/research_results.json`;
`export_dashboard.py` reads them, so the dashboard has no hand-typed figures.

```bash
python -m pip install -r requirements.txt   # pinned; these figures: Python 3.13.14
python fetch_sdfood.py     # pull the public search -> data/ (gitignored). Set SDFOOD_CONTACT first.
python fetch_sdfood.py --csv-only   # rebuild the CSV from a saved pull, no network
python model_food.py       # forward test, variants, baselines, survivorship bound -> food_gains.png
python sim_schedule.py     # rolling backtest, days-sooner simulation, pilot power -> food_days_earlier.png
python fairness_check.py   # flag rates, calibration, coverage by group -> food_fairness.png (fetches ACS once)
python threshold_tradeoff.py # global precision/recall trade + per-group equal-opportunity
python feedback_check.py   # feedback-loop stress test (needs acs_cache.json)
python export_site.py      # the published card's points (data/site), read by the worklists
python export_worklist.py  # monthly district worklists + frozen copy -> data/worklists/<month>/
python export_dashboard.py # de-identified worklist in the rule's order -> dashboard.html
python -m pytest tests     # includes tests/test_worklist.py
```

## For the City: the staff API, and the public site

| | `api/` (FastAPI) | `food-dashboard/` (site) | `dashboard.html` |
|---|---|---|---|
| For | City of San Diego staff | the public, once approved | the research summary |
| Shows | every listed City restaurant and market with the County's record, the published rule's points and band, district summaries, monthly worklists | the same records and bands on a map | the research results, and this month's list as counts only (no facility rows) |
| Access | an API key ([docs/API.md](docs/API.md)) | invented sample until every gate passes ([docs/PUBLISHING.md](docs/PUBLISHING.md)) | open |

**The published rule** is a transparent point score built from each restaurant's own County
record:
- 19 points per employee-hygiene citation;
- 16 per food-source citation;
- 12 per food-temperature citation;
- 5 per hand-washing citation;
- 2 per point the average routine score over two years fell below 100;
- 1 per point the last routine score fell below 100.

Every restaurant's worksheet shows how its points add up. In the backtest, restaurants in the band
(41 points or more, about the top 18% of scored restaurants) had a major violation at their next
routine inspection **at about twice the rate of other restaurants** (37.2% against 17.8%). A
persistence group of the same size reaches a similar rate (37.8%), so the band's value is that its
points are transparent, not that it is more accurate. What it is and how it was chosen:
[docs/MODEL_CARD.md](docs/MODEL_CARD.md).

```bash
python export_site.py                          # -> data/site/ (every City place; points and bands; report.md; archive/)
python export_worklist.py                      # -> data/worklists/<month>/district-<n>.csv
SDFOOD_API_KEYS=choose-a-key uvicorn api.main:app --port 8000     # http://localhost:8000/docs
python export_site.py --mode record            # the record-only export, without any score
python export_site.py --publish                # the public site: only if every gate passes
cd food-dashboard && npm install && npm test && npm run dev
python -m pytest tests                         # exporter, API, worklists, and end-to-end builds through the site's contract check
```

- [docs/API.md](docs/API.md): the staff API.
- [docs/MODEL_CARD.md](docs/MODEL_CARD.md): the rule.
- [docs/FOOD_DATA_CONTRACT.md](docs/FOOD_DATA_CONTRACT.md): what the export holds.
- [docs/PUBLISHING.md](docs/PUBLISHING.md): the gates.
- [docs/HOSTING.md](docs/HOSTING.md): the staff API and the site on Render (`deploy_api.py` ships the API).
- [docs/PILOT.md](docs/PILOT.md): a silent pilot the City can propose to the County.
