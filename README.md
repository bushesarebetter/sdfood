# San Diego food-inspection risk targeting

Predict which routine food-facility inspections will find a **critical (major) violation**,
so the county can inspect the riskiest places first — catching problems earlier with the
same inspector-hours. San Diego County runs ~32,000 inspections/year on a routine calendar,
not by risk. This is the classic "help a city allocate a scarce resource" ML win (cf. Chicago's
deployed food-inspection model).

**By Ayan Pendharkar.** Built on public data.

## Data

San Diego County DEH inspection results, pulled from the official **sdfoodinfo.org** app's
public JSON API (`/restaurants/search.htm`) — public-record data. One paginated pull returns
every facility with its full nested inspection + violation history.

- **102,755 inspections**, 15,878 facilities, **2023-01 → 2026-09**.
- Per inspection: type, score, completed date, and per-violation major/minor flags.

## Model & honest evaluation

- **Target:** at each *routine* inspection, `major violation found` (rate 11.2%).
- **Features — strictly pre-inspection (no leakage):** business type, ZIP, facility age, month,
  and the facility's prior history (past scores, past violation & major rates, time since last,
  whether it failed last time).
- **Forward-in-time test:** train ≤ 2024, test 2025+ (n = 36,543).
- **Baseline that matters:** the facility's own prior major-violation rate (not just random).

| | Model | Prior-rate baseline | Random |
|---|---|---|---|
| ROC-AUC | **0.740** | 0.629 | 0.500 |

- **Top 20% by predicted risk → 45% of all critical violations found (2.26× lift).**
- Drivers (permutation importance): business type > ZIP > prior violation history > recency.
- **Fairness check:** the model lifts precision *within* the dominant category too
  (restaurants 0.27 vs 0.17 base; deli-markets 0.20 vs 0.11) — genuine risk-ranking, not
  type-profiling.

## The reform

Inspect in risk order instead of by calendar → find critical violations sooner at zero added
cost. Unlike a queue where "slow" is ambiguous, catching a critical violation earlier is
strictly good, so acting on the prediction has no downside.

## Honest limits

- Only ~3.7 years of history, so prior-history features are shallow; more history would likely
  improve it. The API exposes ~3 years.
- The label is what inspectors *found*, not true underlying risk (measurement, not ground truth).
- **Feedback/fairness:** targeting by risk can concentrate inspections; the deployment must audit
  outcomes by geography and facility type over time, and keep a baseline of random/rotating
  inspections so the model doesn't blind itself to places it stops visiting.

## Reproduce

```bash
python fetch_sdfood.py     # pull the public API -> data/ (gitignored)
python model_food.py       # train, forward-test, gains curve -> food_gains.png
```
