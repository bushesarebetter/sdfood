# San Diego food-inspection risk targeting

Predict which routine food-facility inspections will find a **critical (major) violation**,
so the county can prioritize the riskiest places first — catching problems earlier with the
same inspector-hours. This is the classic "help a public agency allocate a scarce resource"
ML setup (cf. Chicago's deployed food-inspection model).

**By Ayan Pendharkar.** Built on public data. Independent analysis — not a County document.

## What this is (and isn't)

San Diego County already sets routine inspection **frequency by facility category** (higher-risk
categories are visited more often — e.g. school-processing facilities ~2.3×/yr vs the ~1.6×/yr
median). What it does **not** do is move a facility up or down based on its *own* track record:
across facilities, the correlation between a facility's historical major-violation rate and how
often it's inspected is ~**0.06** — essentially zero. This model closes that gap. It is a way to
**prioritize *within* the county's required schedule**, not a replacement for mandated frequencies.

## Data

SD County DEH inspection results, pulled from the official **sdfoodinfo.org** app's public JSON
API (`/restaurants/search.htm`) — public-record data. One paginated pull returns every facility
with its full nested inspection + violation history. See `fetch_sdfood.py` for the access-ethics
note (public record; no robots.txt on the host; honest UA; request officially for production use).

- **102,755 inspections**, 15,878 facilities, **2023-01 → 2026-09** (~3.7 yr; the API exposes ~3 yr).
- **71,761 routine** inspections (~20,900/yr); the rest are re-inspections and other follow-ups.
- Per inspection: type, score, completed date, and per-violation major/minor flags.
- **Data hygiene:** `score` is a not-scored sentinel (`0`) on 100% of non-routine inspections, so
  score-based history features are computed from **real routine scores only** (see `model_food.py`).

## Model & honest evaluation

- **Target:** at each *routine* inspection, `major violation found` (rate 11.2%).
- **Features — strictly pre-inspection (no leakage):** business type, ZIP, facility age, month,
  and the facility's prior history (last/mean routine score, prior violation & major rates, time
  since last, whether it failed last time). Built with per-facility shifted/expanding stats.
- **Forward-in-time test:** trained on **Jan 2023 – Dec 2024** (35,218 routine), tested on
  **Jan 2025 – Sep 2026** (36,543 inspections the model never saw).
- **Deploy/worklist model** is fitted on **all** routine inspections and scores each active
  facility as of Sep 2026 — standard train-all-for-deployment; the accuracy claims come only
  from the held-out split above.
- **Baseline that matters:** the facility's own prior major-violation rate (not just random).

| | Model | Prior-rate baseline | Random |
|---|---|---|---|
| ROC-AUC | **0.745** | 0.629 | 0.500 |
| PR-AUC | **0.264** | — | 0.117 (base rate) |

- **Top 20% by predicted risk → ~47% of all critical violations found (2.36× lift).**
- **Precision is modest, and that's fine for reordering:** at a top-20% cut, ~**28%** of flagged
  routine inspections find a major violation (vs 11% base) — so ~**3 in 4 flagged are still clean**.
  That's acceptable because this **reorders** visits everyone already gets; it is **not** a license
  to *skip* the low-scored facilities.
- **Stable:** rolling-origin backtest AUC **0.73–0.76** across three cutoffs, not one lucky split.
- **Drivers (permutation importance):** business type > ZIP > last routine score > prior mean score
  > prior violation count.
- **Within-type lift (not just type-profiling):** restaurants precision 0.28 vs 0.17 base;
  retail-with-deli 0.22 vs 0.11.

## The operational claim (stated carefully)

Working a period's already-scheduled routine inspections in **risk order** surfaces critical
violations **~6.3 days sooner within the monthly cycle** (bootstrap 95% CI 5.9–6.6), while clean
facilities wait ~0.8 day longer. This is a **detection-latency** figure within an already-scheduled
batch — **not** prevented illness and **not** a dollar figure. The effect scales with the reorder
window (it's ~19 days if you pretend a whole quarter is one free pool), which is exactly why the
honest, operationally realistic number is the **within-month** one. Inspectors already have
discretion over the order they work a month's list; this informs that order.

## Fairness (see FAIRNESS.md)

The model is **calibrated** across ZIP income and ethnicity and flags low-income ZIPs **0.64×** as
often as high-income ones (actual rates are ~flat, 0.96×) — it tracks real risk, not income. The
real caveat is **equal protection**: recall of true criticals is lower in lower-income / higher-
Hispanic areas (**38% vs 54%**) under a single global threshold, because the model has less signal
there. Mitigation: keep baseline routine inspections everywhere and monitor recall by group.

## Feedback loop (see feedback_check.py)

The labels are generated by the inspections you allocate, so pure targeting can go blind to places
it stops visiting. A one-round censoring test shows this effect is **small** here (low-income recall
moves ~1 pt), and a random baseline keeps it stable — but a single-round test can't capture
multi-cycle compounding, so recall-by-group must be **monitored live** after deployment.

## Honest limits

- Only ~3.7 years of history, so prior-history features are shallow.
- The label is what inspectors *found*, not true underlying risk (measurement, not ground truth).
- The AUC-0.745 lift over an experienced program's own knowledge of repeat offenders is real but
  modest — this is a prioritization aid, not an oracle.

## Reproduce

```bash
python fetch_sdfood.py     # pull the public API -> data/ (gitignored). Add a contact UA first.
python model_food.py       # train, forward-test, gains curve -> food_gains.png
python sim_schedule.py     # rolling backtest + detection-latency sim -> food_days_earlier.png
python fairness_check.py   # disparate-impact / calibration / recall -> food_fairness.png
python threshold_tradeoff.py # global precision/recall trade + per-group equal-opportunity
python feedback_check.py   # feedback-loop stress test (needs acs_cache.json)
python export_dashboard.py # de-identified, due-aware worklist -> dashboard.html
```
