# Fairness / disparate-impact analysis

An enforcement-targeting ordering has to answer: **does it send inspectors disproportionately to
lower-income or immigrant neighborhoods, and does it protect every neighborhood equally?** This
is the check. Reproduce with `python fairness_check.py` (needs `data/` from `fetch_sdfood.py`).
Numbers are from the rerun of 2026-09-27 on the 2026-09-19 pull: history since 2023-01, no ZIP
code, no permit age (see README, "What changed"), and every model trained and scored as of the 1st
of each inspection's month, as the monthly list is. The two last points under "Limits" (the staff
rule by council district, and the screen by restaurant name) are the staff site's, from the
2026-09-29 pull ([docs/MODEL_CARD.md](docs/MODEL_CARD.md)).

## Method

- Out-of-fold predictions (train ≤ 2024, test 2025+, 32,548 routine inspections the model never saw).
- Each facility joined to its ZIP's **median household income** and **% Hispanic** ([ACS](https://www.census.gov/programs-surveys/acs)
  5-yr via [Census Reporter](https://censusreporter.org): tables [B19013](https://censusreporter.org/tables/B19013/)
  income, [B03002](https://censusreporter.org/tables/B03002/) ethnicity; 99.8% of test inspections
  covered, 97/109 ZIPs matched).
- **Whole ZIPs per group:** income quartiles and %-Hispanic terciles are cut so that each ZIP sits
  in one group, with about equal inspection counts per group.
- Four orderings of the same inspections, each flagging its top 20% county-wide (ties split pro rata):
  - the **research model** (no ZIP);
  - the same model **with ZIP**, to see whether ZIP carries a gap;
  - the **one-line rule**: lowest mean routine score on record first;
  - **persistence**: routine inspections with a major in the prior 12 months, then majors, then
    the lowest last routine score over two years.
- For each: the **flag rate** against the **actual** major-violation rate (is targeting driven by
  real risk?), the **false-positive rate** (the share of each group's clean inspections flagged),
  **calibration** (predicted against actual rate within each group), **equal opportunity** (the
  share of each group's major violations in the top 20%, "recall"), and **days sooner** by group
  under the policy actually proposed: reordering each council district's (or ZIP3 area's) month.
- **95% intervals resample whole ZIPs** (a ZIP-clustered bootstrap), so they reflect how few ZIPs
  each group holds. If an interval covers equality (0 for a gap, 1 for a ratio), the data cannot
  tell the groups apart.
- Every test inspection is at a facility that still exists: SD Food Info lists only those
  (README, "Survivorship"). The figures describe coverage among surviving facilities.

## Results

By ZIP median income (Q1 = lowest), research model:

| group | ZIPs | n | actual major % | flag % | predicted % | recall % (95% CI) | false-positive rate % (95% CI) | days sooner (95% CI) |
|---|---|---|---|---|---|---|---|---|
| Q1 low | 25 | 8,380 | 12.3 | 19.6 | 13.6 | 52.1 (45.3–59.4) | 15.0 (11.5–18.6) | +6.8 (5.7–7.8) |
| Q2 | 16 | 7,936 | 13.0 | 21.2 | 14.4 | 50.2 (43.7–58.0) | 16.8 (14.4–19.0) | +6.5 (5.1–8.3) |
| Q3 | 26 | 8,262 | 12.3 | 19.0 | 13.8 | 46.5 (39.7–52.3) | 15.1 (12.5–17.9) | +5.8 (5.0–6.7) |
| Q4 high | 30 | 7,915 | 12.9 | 20.3 | 14.2 | 48.7 (44.5–52.5) | 16.1 (14.0–18.2) | +6.3 (5.4–7.3) |

The other orderings, same groups:

| group | rule flag % | rule recall % (95% CI) | rule false-positive % (95% CI) | rule days sooner (95% CI) | persistence recall % | model with ZIP: recall % |
|---|---|---|---|---|---|---|
| Q1 low | 21.0 | 51.6 (44.7–58.5) | 16.7 (13.5–20.4) | +6.2 (4.9–7.3) | 49.4 | 42.1 |
| Q2 | 21.3 | 49.3 (41.9–57.8) | 17.1 (14.1–21.3) | +6.0 (4.7–7.5) | 49.3 | 49.5 |
| Q3 | 18.3 | 43.6 (37.5–48.7) | 14.8 (12.0–17.5) | +5.2 (4.3–6.2) | 41.6 | 44.7 |
| Q4 high | 19.4 | 47.0 (41.6–51.7) | 15.3 (13.3–17.3) | +5.7 (4.7–6.7) | 44.0 | 55.9 |

Lowest against highest income quartile:

| | recall gap, Q1 minus Q4 (95% CI) | flag rate, Q1 ÷ Q4 (95% CI) |
|---|---|---|
| Research model | +3.4 points (−4.6 to +11.7) | 0.97× (0.74–1.24) |
| One-line rule | +4.6 (−4.1 to +13.5) | 1.08× (0.84–1.38) |
| Persistence | +5.4 (−2.9 to +14.2) | 1.03× (0.83–1.29) |
| Model with ZIP (not used) | −13.8 (−30.2 to +4.8) | 0.60× (0.31–1.01) |
| Actual major-violation rate | | 0.95× (0.76–1.19) |

By ZIP % Hispanic (low to high tercile): actual rates 14.0%, 12.4%, 11.6% (lowest ÷ highest
1.21×, 1.01–1.44); model flag rate 21.8%, 19.1%, 19.0% (1.15×, 0.94–1.38); recall 49.6%, 47.6%,
50.9% for the model (gap −1.3 points, −8.2 to +5.0), 45.9%, 47.1%, 50.9% for the one-line rule
(−5.0, −12.1 to +1.9) and 43.5%, 46.0%, 49.3% for persistence (−5.8, −12.8 to +1.0). The model with
ZIP: 57.0%, 44.8%, 40.7% (+16.3, +2.4 to +29.3), flagging the lowest-%-Hispanic tercile 1.96× as often
as the highest (1.28–3.26). Days sooner under the within-district reordering: model +6.1, +6.5, +6.5;
rule +5.4, +6.1, +5.8, with overlapping intervals.

## What it means

Each income quartile holds 16 to 30 ZIPs, and ZIPs differ from one another for reasons that have
nothing to do with income, so the intervals are wide: most can't rule out gaps of 5 to 10 points
either way. "No detectable difference" below means exactly that, not that coverage is even.

1. **Flag rates and actual rates.** Actual major-violation rates are nearly flat across income
   (lowest quartile 0.95× the highest), and so are the flag rates: the model flags low-income ZIPs
   at **0.97×** the rate of high-income ZIPs, the one-line rule at **1.08×**, persistence at
   **1.03×**. Every interval covers 1: no detectable difference. Per group, the rule flags the
   lowest-income quartile at 1.71× its actual rate against 1.50× for the highest, and its
   false-positive rate there is 16.7% against 15.3%. The per-group intervals overlap, and the
   audit does not estimate that difference itself. By %-Hispanic tercile the *actual* rate does
   differ detectably (1.21× higher in the lowest-%-Hispanic ZIPs), and the model's flag rate
   follows it (1.15×, interval covering 1).
2. **Calibration, in the large only.** The model's predicted rate sits 1.3 to 1.5 points above the
   actual rate in every income quartile, 10–12% relative: the same offset everywhere, and no group
   scored below its real rate. The offset is not a fairness finding: the model over-predicts
   across the whole test period, because what a long record means drifted after training (README,
   "Calibration"). Group means are not calibration within groups; the plot shows only the means.
3. **Coverage.** Under a single top-20% cut, the model finds **46% to 52%** of each income
   quartile's major violations, the one-line rule **44% to 52%** and persistence **42% to 49%**. By
   %-Hispanic tercile the model covers 48% to 51%, the rule 46% to 51% and persistence 44% to 49%.
   Every lowest-minus-highest gap for these three covers 0: no detectable difference.
4. **Days sooner by group.** Under the proposed within-district reordering, major violations
   surface 5.8 to 6.8 days sooner across income quartiles with the model and 5.2 to 6.2 with the
   rule, with overlapping intervals: no group is left behind that the data can see.
5. **Why the model has no ZIP.** With ZIP as a feature the model ranks slightly worse (AUC −0.006,
   −0.011 to −0.002; README) and it covers the lowest-%-Hispanic ZIPs' major violations at 57%
   against 41% for the highest: a gap of +16.3 points (+2.4 to +29.3), and it flags those ZIPs 1.96×
   as often (1.28–3.26), the only differences in this audit the data can detect. By income its gap
   (−13.8 points, 42% against 56%) is large but its interval covers 0. The research model, like the
   public site's point card, uses no ZIP code.
6. **Safeguards that stay:** keep routine inspections everywhere, so the ordering reprioritizes
   within the schedule and never zeroes out an area, and monitor coverage by group once it is in
   use (the pilot's monitoring rule is in docs/PILOT.md; the report it needs is not built yet).

## Equalizing coverage exactly (`threshold_tradeoff.py`)

The recall figures above are at a *single global* top-20% cut. A global threshold can't equalize
recall across groups with different score distributions — only per-group thresholds
([equal-opportunity](https://arxiv.org/abs/1610.02413), Hardt et al. 2016) can. `threshold_tradeoff.py`
tests both, twice.

**In sample** (cuts set on the test set's own labels, so this is what equalizing would have cost had
the labels been known). Targeting the best group's recall (52%) everywhere:

| income group | global (top-20%) recall | equal-opportunity recall (per-group cut) | flag rate, global → per-group |
|---|---|---|---|
| Q1 low | 52.1% | 52.0% | 19.6% → 19.5% |
| Q2 | 50.2% | 52.0% | 21.2% → 22.2% |
| Q3 | 46.5% | 52.0% | 19.0% → 22.3% |
| Q4 high | 48.7% | 52.0% | 20.3% → 21.9% |

The total flag budget would move from 20.0% to 21.5%.

**Out of sample** (every cut set on the 2025 inspections and applied, unchanged, to 2026's 13,855):

| income group | global cut: flag %, recall % | per-group cuts: flag %, recall % |
|---|---|---|
| Q1 low | 22.4, 60.0 | 23.2, 61.7 |
| Q2 | 24.3, 54.5 | 24.4, 54.5 |
| Q3 | 21.5, 49.2 | 23.6, 52.6 |
| Q4 high | 23.9, 55.9 | 27.6, 61.4 |
| total | 23.0 | 24.7 |

Set in advance, the per-group cuts cost **1.7 more points of all inspections flagged (95% CI +1.3 to
+2.1, whole ZIPs resampled)** and barely even out coverage: recall still spans 9.1 points across the
groups, against 10.8 under the global cut. They are also a different decision rule per income group,
keyed off a ZIP/income proxy: disparate *treatment*, which a government enforcement program should
avoid, to close gaps the data cannot tell from zero. **Recommendation: one global order, a baseline of
routine inspections everywhere, and coverage monitored by group.** (The script also prints the global
precision/recall trade: flagging 20% gives the model 31% precision, 2.5× the base rate, and the rule
30%; flagging 50% reaches 83% of major violations for the model, 78% for the rule and 77% for
persistence.)

## Feedback loop

Because inspections generate the labels the model trains on, targeting could compound over time
([runaway feedback loops](https://arxiv.org/abs/1706.09847), Ensign et al. 2018).
The earlier version of `feedback_check.py` tested one round of "only label what we flagged" and
found coverage moving by at most a point. It could not have found more. It dropped only the
labels and kept every facility's full history, and it selected purely on the model's own
features. A skipped inspection also leaves no score, no "days since" and no majors on the record,
which is what the rule and persistence read too.

The script now deletes skipped inspections, and the follow-ups within 45 days they would have
triggered, from the record over four quarterly rounds of 2024, choosing each round as a list made on
the 1st would. It rebuilds the model, the rule and persistence from what is left and scores them on
2025+. The test inspections are the same in every arm, so each arm's loss against arm A has a
paired 95% interval over facilities:

| AUC on 2025+ | A: every inspection kept | B: only the model's top 40% inspected (change from A, 95% CI) | C: top 40% plus a random 15% of the rest, 3 seeds (change from A) |
|---|---|---|---|
| Model | 0.763 | 0.756 (−0.007, −0.010 to −0.004) | 0.756 (−0.006, −0.009 to −0.004) |
| One-line rule | 0.737 | 0.722 (−0.015, −0.018 to −0.011) | 0.725 (−0.012, −0.015 to −0.009) |
| Persistence | 0.724 | 0.709 (−0.014, −0.018 to −0.011) | 0.713 (−0.011, −0.014 to −0.008) |

Inspecting only the model's picks (arm B removes 9,622 routine inspections, and the mean time since
a facility's last visit in 2025+ rises from 266 to 340 days) costs every ordering a detectable
loss, and the rule and persistence, which read the same thinned record, lose about twice what the
model does: their intervals do not overlap the model's. A random 15% on top (arm C) gives a little
back. Coverage by income quartile moves by at most 3 points. This concerns an inspect-less policy;
reordering within the schedule removes no inspection. Coverage by group should still be monitored in
use (docs/PILOT.md; not built yet).

## Limits

- Area-based (ZIP) income and ethnicity are a standard disparate-impact proxy, not the
  demographics of each facility's owner or customers, and cannot see within-ZIP differences.
- The model no longer reads ZIP, but business type and a facility's record can still correlate
  with neighborhood; that is why this audit reports outcomes by group rather than inputs.
- The data hold only surviving facilities, about 3.7 years of them.
- Any deployment should re-run this audit on the County's internal records, on a schedule.
- **The rule the staff site shows is audited by council district on every band it shows**
  (`export_site.district_fairness`, the About page's district table), not only on a named top band.
  For each district: the band's precision with a Wilson interval, its false-positive rate against the
  City's, and its share of the places in a band that then had no major over its share of the
  *labelled, scored* places (only such a place can be wrongly named; earlier versions divided by all
  candidates, then by all labelled places), with an address-cluster bootstrap interval at 95%, a
  family-wise one over the nine districts compared (Bonferroni), and the family-wise one widened by an
  assumed design effect of 2 for inspector clustering. Only District 9 stays above even on both wider
  intervals. District 6 is above even at 95% and family-wise, but not once inspector clustering is
  allowed for; District 4 is above even at 95% only (MODEL_CARD.md). The site shows the table, and a
  place page in a City district says how often band 1 places there had a major. Part of a district's
  gap may be how its inspectors cite: the record does not say which inspector made a visit. The staff
  site's district view says the same of its counts of majors, closures and B or C grades: a pattern to
  take to the County as a question, not a ranking of districts.
- **Area proxies cannot see who inside an area bears the errors.** A coarse screen by restaurant name
  (keywords suggesting a cuisine; not the owner's ethnicity, and not a validated measure) found that,
  among City restaurants whose next routine inspection was clean, places with East or Southeast Asian
  names were put in band 1 about 1.9 times as often as places with unclassified names (95% 1.5 to
  2.5), and places with Latin or Mexican names about 1.3 times as often (1.0 to 1.7). (An earlier,
  unscripted screen with other keyword lists found 2 to 3 times and 1.6 times.) The rule is the
  County's own average score, so it passes any gap in those scores
  through unchanged (`tools/name_screen.py` reproduces the screen; [docs/NAME_SCREEN.md](docs/NAME_SCREEN.md)). It
  may be real differences in risk, or differences in how inspectors cite (the temperature item "time
  as a public health control" is cited far more often at the first group); without inspector ids the
  two cannot be separated. The next step is a proper audit: hand-code a stratified sample of places,
  or obtain the County's risk category or menu type, and report the false-positive ratio by group.

Full source list (data, methods, fairness papers): [REFERENCES.md](REFERENCES.md).
