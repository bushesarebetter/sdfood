# San Diego food-inspection risk targeting

Order each month's routine food inspections by each facility's own inspection record, so that
**major violations** (the County's term) are found sooner, with the same inspectors and the same
schedule. This is the classic "help a public agency allocate a scarce resource" setup (cf.
Chicago's food-inspection model).

**By Ayan Pendharkar** (research) **and Chenhao Zhang**, students at Canyon Crest Academy, San Diego. Independent: not affiliated with or endorsed by the
County of San Diego. The data were collected from the County's public SD Food Info search with an
identifying User-Agent (`fetch_sdfood.py`), pending an official extract from the County.

## The short version

- **A one-line rule does most of the work.** Ranking routine inspections by each facility's mean
  routine score on record, lowest first, puts **48%** of 2025-26 major violations in the first
  20% of inspections, **2.4×** the base rate. Within a council district's month it finds them
  **5.8 days sooner** than the order actually worked.
- **The research model adds a little.** It reaches the same 48%, with AUC 0.76 against the
  rule's 0.74, and finds major violations **6.2 days sooner** (0.4 day more than the rule).
- **Even coverage.** Both find 45% to 51% of the major violations in every ZIP-income quartile.
- **For the City and the County:** monthly worklists per council district (`export_worklist.py`)
  and a pre-registered silent pilot the City can propose to the County ([docs/PILOT.md](docs/PILOT.md)).

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
- **4,949 same-day records of one type were merged** (grocery departments are inspected as separate records).
- **102,755 rows → 92,410 inspections**, 15,870 businesses, 2023-01-03 → 2026-09-19. A routine
  inspection's history features read strictly earlier dates only.

Rebuilt from the same pull, the old rules reproduce the old figures exactly (AUC 0.745, 47% in the
top 20%, +6.3 d in a county-wide month); the clean data give 0.756, 48% and +6.5 d.

### The model, the comparison and the deliverable

| headline (2025+ forward test) | as published earlier in September | now |
|---|---|---|
| Model features | since-2023 history, ZIP, permit age as of the pull | since-2023 history, **no ZIP, no permit age** |
| Model ROC-AUC | 0.756 | **0.758** |
| Model: top 20% → share of major violations | 48.2% | **47.9%** |
| One-line rule: top 20% → share | 48.3% | **48.3%** |
| Days sooner within a district's month: model / rule | +6.2 / +5.8 | **+6.2 / +5.8** |
| Model's coverage of majors, lowest vs highest income quartile | 42% vs 58% | **50% vs 47%** |
| Model's flag rate, low- vs high-income ZIPs | 0.61× | **0.97×** |

- **Permit age removed (a leak).** `opened_date` is the permit in force when the data were
  collected. A permit reissued after an inspection (a change of owner, say) gave 171 training
  inspections a negative age; they found a major 23.4% of the time against 11.4%. Dropping the
  feature changes AUC by +0.000 (95% CI −0.002 to +0.002) and the top-20% share by +0.3 points
  (−0.5 to +1.2): the published figures were not inflated by it. Setting only the impossible ages
  to missing was tested too (47.5% in the top 20%), but a blank still marks a later reissue, so
  the feature is gone.
- **ZIP removed.** With and without ZIP the model is equally accurate (AUC −0.002, −0.006 to
  +0.003; top-20% share +0.6 points, −0.7 to +2.1; days sooner −0.1, −0.2 to +0.1, all "with
  minus without"). Without ZIP its coverage is even across income groups; with ZIP it was not
  (FAIRNESS.md). The research model now matches the public site's card, which never used ZIP.
- **12-month history tested; since-2023 history kept.** See "History window" below.
- **The one-line rule leads,** the research model second, persistence as the reference.
- **The dashboard's "risk × overdue" ranking was backtested and replaced.** It found major
  violations 5.3 days sooner within a district's month, against 5.8 for the rule and 6.2 for the
  model, so `dashboard.html` now lists facilities in the rule's order.
- **Survivorship stated and bounded** (below), **monthly worklists** for the City's council
  districts with a frozen copy for a pilot (`export_worklist.py`), a pinned environment
  (`requirements.txt`), and one shared feature library (`model_food.py`) that every research
  script imports, so a fix lands everywhere.

## What this is

San Diego County sets routine inspection **frequency by facility category** (school processing
facilities about 2.3 times a year against a 1.5 median), and **follow-up visits respond to
findings**. The routine cadence itself moves a little with a facility's own record: the next
routine comes a median **277 days** after one that found a major against **303** after one that
did not, and across the 4,747 facilities on the record for three years or more, the correlation
between a facility's routine major-violation rate and its routine inspections per year is −0.07
(`model_food.py` prints all three). This project orders routine inspections **within the County's
required schedule** by that record. It does not change how often any facility is inspected.

## Data

SD County DEH inspection results, from the official **sdfoodinfo.org** app's public JSON search
(`/restaurants/search.htm`): public-record data, collected with an honest User-Agent and rate
limits (see `fetch_sdfood.py`). For any pilot the County's official extract should replace it.

- **92,410 inspections**, 15,870 facilities, **2023-01-03 → 2026-09-19** (~3.7 yr).
- **64,085 routine** inspections (18,669 in 2025); plus 21,944 re-inspections, 4,558 complaint
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
  **Jan 2025 – Sep 2026** (32,552 inspections the model never saw; 4,115 found a major).
- **Deployment model** (worklists, dashboard) is fitted on **all** routine inspections before the
  list's month; the accuracy figures come only from the held-out test.
- **Orderings that need no model:** the **one-line rule** (mean routine score on record, lowest
  first); **persistence** (routine inspections with a major in the prior 12 months, then majors,
  then the lowest last routine score; `export_site.persistence`); the last routine score; the mean
  routine score over the prior 12 months; the prior major-violation rate. Ties at the cut are
  split pro rata (the expectation under a random order).

| 2025+ test | ROC-AUC | top 20% → share of major violations | precision in top 20% | lift |
|---|---|---|---|---|
| **One-line rule: mean routine score on record** | 0.740 | **48.3%** | 30.5% | 2.42× |
| **Research model** | **0.758** | 47.9% | 30.3% | 2.39× |
| Last routine score alone | 0.725 | 46.9% | 29.6% | 2.34× |
| Prior major-violation rate | 0.640 | 42.8% | 27.1% | 2.14× |
| Persistence (last 12 months) | 0.684 | 41.5% | 26.2% | 2.08× |
| Mean routine score, last 12 months | 0.682 | 40.7% | 25.7% | 2.04× |
| Routine calendar, no ordering | 0.500 | 20% | 12.6% (base rate) | 1× |

Model PR-AUC 0.294 (base rate 0.126). Paired bootstrap over facilities, 95% CIs:

- **Model and one-line rule are tied at the top-20% cut** (model minus rule −0.4 points, −1.7 to
  +0.8); the model ranks the whole list a little better (AUC +0.018, +0.013 to +0.023).
- **Both clearly beat persistence:** the model by AUC +0.074 (+0.067 to +0.081) and +6.4 points of
  major violations in the top 20% (+4.8 to +8.0).
- **Stable across time:** rolling-origin AUC 0.725–0.759 for the model and 0.722–0.741 for the rule
  across three cutoffs (persistence 0.673–0.697).
- **Drivers (permutation importance):** mean routine score on record, business type, mean
  violations per visit, prior major-violation rate. Within type the gain holds: flagged
  restaurants find a major 31% of the time against 19% for all restaurants; retail markets with a
  deli 28% against 18%.
- **It reorders visits every facility already gets.** Nothing here skips a facility or lowers how
  often it is inspected.

### History window: since 2023, or the last 12 months?

The history features grow with the record: the median routine inspection had 0 prior visits on
record in 2023, 2 in 2024, 3 in 2025 and 4 in 2026 (left truncation). A **12-month-window
variant** reads the 365 days before each inspection, as the public site's exporter does, and
trains only on inspections from 2024-01-03, whose year is fully on the record.

| variant (same 2025+ test) | ROC-AUC | top 20% share | days sooner, district month |
|---|---|---|---|
| **Since-2023 history, no ZIP, no permit age (headline)** | **0.758** | **47.9%** | **+6.2** |
| Since-2023, with ZIP | 0.756 | 48.5% | +6.2 |
| Since-2023, ZIP, permit age missing when impossible | 0.755 | 47.5% | |
| As published: since-2023, ZIP, permit age as of the pull | 0.756 | 48.2% | +6.2 |
| 12-month window, no ZIP (trained 2024) | 0.736 | 42.7% | +5.7 |
| 12-month window, with ZIP (trained 2024) | 0.735 | 43.1% | |
| 12-month window, with ZIP, trained 2023-24 | 0.738 | 43.3% | |

**The headline uses since-2023 history.** A third of routine inspections (32.6% in the test)
come more than a year after the facility's previous routine, so a 12-month window misses the one
score that matters most; it costs 0.022 AUC (0.017 to 0.028) and 5.2 points of the top-20% share
(3.6 to 6.8), whatever the training years. The since-2023 forward test stays honest: every
training row saw only what was on the record at the time, and the test rows simply have longer
histories. The same holds for the rule: the mean routine score over the last 12 months does much
worse than the mean on record (40.7% against 48.3%).

## Finding major violations sooner (the operational claim)

Working an already-scheduled batch of routine inspections in a ranked order finds major
violations sooner. Inspectors work areas, not one county-wide pool, so the realistic batch is **a
City of San Diego council district's month** (outside the City, a ZIP3 area's month):

| ordering, within a district / ZIP3 month | major violations found sooner than the order actually worked |
|---|---|
| **One-line rule** | **+5.8 d** (95% CI 5.5–6.2) |
| **Research model** | **+6.2 d** (5.9–6.6) |
| The old dashboard's risk × overdue weighting | +5.3 d (4.8–5.8) |
| Persistence | +4.4 d (4.0–4.8) |
| Mean routine score, last 12 months | +4.3 d (3.9–4.8) |

- The model adds **0.4 day** over the rule (0.3–0.5) and **1.8 days** over persistence (1.6–2.1),
  paired bootstrap over months. Clean facilities wait 0.8–0.9 day longer: the reorder is zero-sum
  in inspection-days.
- County-wide monthly pool: model +6.5 d, rule +6.1 d. A whole quarter treated as one pool: model
  +19.6 d, rule +18.3 d; the effect scales with the reorder window, which is why the honest number
  is the within-month one.
- **Assumptions:** a facility's finding does not depend on the day of the month it is inspected,
  and routing is ignored (a reordered month may cost more driving). Council districts stand in for
  the County's real unit, an inspector's territory, which the public record does not carry.
- This is a **detection-latency** figure within an already-scheduled batch, not prevented illness
  and not a dollar figure.

## Survivorship

**SD Food Info lists only facilities that exist today, so every cohort here holds survivors.**
Only 12 of the 15,870 businesses in the data were last seen before 2025; a complete record would
hold every place that closed in 2023-24. The pull's permit status shows the few closing places
that remain: 196 of 16,728 businesses have an expired permit, and their 367 test inspections found
a major 21.5% of the time against 12.5%. In 2024, 1,292 permits were opened, 9.7% of the
facilities on the record by then; in a stable population about as many close each year.

**Bound** (`model_food.py`): add X% more test inspections from missing facilities with the
expired group's major rate, then re-cut the top 20%.

| missing inspections | ranked like the listed expired facilities: model / rule | worst case, all ranked last: model / rule |
|---|---|---|
| 0% (as measured) | 47.9% / 48.3% | |
| +5% | 47.1% / 48.1% | 45.5% / 45.8% |
| +10% | 46.7% / 47.6% | 43.8% / 44.1% |
| +20% | 45.6% / 46.7% | 40.2% / 40.8% |

Even with a fifth more inspections from vanished facilities, ranked as badly as possible, the top
20% of either ordering still holds about twice its share of major violations. The rule and the
model move together, so the comparison between them holds. The County's full records, inactive
permits included, remove the question.

## Fairness (see FAIRNESS.md)

Targeting tracks real risk: actual major-violation rates are nearly flat across ZIP income
(0.95×, lowest to highest quartile), and so are the flag rates (model 0.97×, rule 1.07×,
persistence 0.96×). Coverage is even: in every income quartile the model finds 45% to 51% of the
major violations in its top 20%, and the rule 45% to 51%, with the lowest-income quartile at the
top of both ranges. The model's predicted rate sits 1.5 to 1.7 points above the actual rate in
every quartile. Keep routine inspections everywhere and monitor coverage by group in use.

## Feedback loop (see feedback_check.py)

The labels come from the inspections that get done, so targeting could go blind to places it
stops visiting. In a one-round censoring test, training only on what a 2023 model flagged in 2024
moves each income quartile's coverage by at most 1 point (49% / 50% / 46% / 48% against 50% / 49%
/ 45% / 47%), with or without a 15% random baseline. One round cannot show multi-cycle
compounding, so coverage by group is monitored in use.

## Monthly worklists for the City's council districts (`export_worklist.py`)

For a month (by default the one after the data end), one CSV per council district in
`data/worklists/<yyyy-mm>/`, the source the staff API serves:

- **Who is due** is estimated, since the public record has no schedule: a facility is listed when,
  by the month's end, the days since its last routine inspection reach its business type's median
  routine interval minus 30. In a backtest over 2025-01 to 2026-08, **72%** of each month's City
  routine inspections (at facilities already on the record) came from that month's list; a list
  runs about 2.6 times a month's volume. For October 2026: 2,279 facilities across the nine
  districts.
- **The order:** the published point card's points first (the site's rule, below), then places
  the card does not score by the one-line rule. Each row says why it sits where it does.
- **A frozen copy** (read-only, timestamped, with sha256 hashes and every active facility's
  position under each ordering) lets a silent pilot be scored later against exactly what was sent:
  [docs/PILOT.md](docs/PILOT.md). In the backtest, two districts for three months are enough to
  confirm a head start of the size above (power 0.79).

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
python -m pip install -r requirements.txt   # Python 3.14.4, pinned
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
| Shows | every listed City restaurant and market with the County's record, the published rule's points and band, district summaries, monthly worklists | the same records and bands on a map | a de-identified worklist |
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
routine inspection **at about twice the rate of other restaurants** (37.2% against 17.8%). What it
is and how it was chosen: [docs/MODEL_CARD.md](docs/MODEL_CARD.md).

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
