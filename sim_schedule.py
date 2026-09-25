"""Scheduling simulation: if inspectors worked a period's already-scheduled routine inspections
in a ranked order instead of the order they were actually done, how much sooner within that
period would major violations surface? This is a DETECTION-LATENCY figure, not prevented
illness. Plus a rolling-origin backtest (AUC stability) and the silent pilot's power estimate.

Orderings (arms), all out-of-fold (a model never trains on the inspection it scores):
  * Model: the research model (model_food.HEADLINE: history since 2023-01, no permit age, no ZIP);
  * the same model with ZIP, read over a 12-month window, and as published (with ZIP and the
    permit age as of the pull, a leak), for the README's ablation table;
  * the one-line rule (model_food.RULE): lowest mean routine score on record (since 2023-01)
    first; and the mean routine score over the prior 12 months;
  * persistence: routine inspections with a major in the prior 12 months, then majors in the
    prior 12 months, then the lowest last routine score (export_site.persistence);
  * Model x overdue: the weighting the de-identified dashboard used to rank by (risk times the
    time since the last visit over the type's median routine interval, clipped to 0.2-2), never
    tested before. Its time since the last visit is taken at the start of the month, from visits
    before that date, and the type intervals come from 2023-24.
The model's gain over each other arm is a paired bootstrap over reorder windows.

The reorder is zero-sum in inspection-days (same slots, same dates): it moves earliness onto the
majors and lateness onto the clean facilities. It assumes a facility's finding does not depend on
which day of the month it is inspected, and it ignores routing: a reordered month may cost more
driving than the order actually worked. The magnitude scales with the reorder window, so it
measures the reorder horizon, not a bigger real-world benefit. Three windows:
  * within a month, county-wide: one pool per month;
  * within a month, within an area: inspectors work areas, not one county-wide pool, so each month
    is split by City of San Diego council district (export_site.district_lookup) and, outside the
    City, by ZIP3; each area's month is reordered on its own (the headline). The County's real
    unit is an inspector's territory, which the public record does not carry;
  * within a quarter, county-wide: shown only to make the window-dependence explicit.
Tied scores share their slots' mean date (the expectation under a random order within the tie).

Power (docs/PILOT.md): from the City council district-months of the test period, the spread of the
per-district-month difference between an ordering and the order actually worked, and the number of
district-months a silent pilot needs to detect a 2-day difference; and, for a later randomized
phase, the spread of the mean day of the month on which majors were found, and the district-months
per arm it needs.

Writes its headline numbers to data/research_results.json for export_dashboard.py."""
import numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
import export_site as es
import model_food as mf

BOOT = 2000
Z = 1.959964 + 0.841621          # two-sided 5%, 80% power
H, RULE = mf.HEADLINE, mf.RULE
OVERDUE = "Model x overdue (old dashboard)"


def assigned(slots, score):
    """Slot date (days) each inspection gets when the batch is worked highest score first; a tie
    shares its slots' mean date (the expectation under a random order within the tie)."""
    order = np.argsort(-score, kind="stable"); sc = score[order]
    starts = np.r_[0, np.flatnonzero(np.diff(sc) != 0) + 1]; ends = np.r_[starts[1:], len(sc)]
    c = np.r_[0, np.cumsum(slots)]
    out = np.empty(len(sc)); out[order] = np.repeat((c[ends] - c[starts]) / (ends - starts), ends - starts)
    return out


def areas(rows):
    """Council district inside the City of San Diego ("D3"), ZIP3 outside it ("Z920")."""
    lookup = es.district_lookup(es.load_districts())
    biz = rows.drop_duplicates("business_id").set_index("business_id")
    dist = {b: lookup(r["lng"] if pd.notna(r["lng"]) else None, r["lat"] if pd.notna(r["lat"]) else None)
            for b, r in biz[["lat", "lng"]].iterrows()}
    di = rows["business_id"].map(dist)
    return pd.Series(np.where(di.notna(), "D" + di.astype("Int64").astype(str),
                              "Z" + rows["zip"].astype("string").str[:3].fillna("NA")), index=rows.index), di


def overdue_ratio(df, rows, interval):
    """Days from the facility's last visit before the start of the row's month to that month's
    start, over its type's median routine interval (floor 120 days), clipped to 0.2-2, as the old
    dashboard did from its as-of date. 1 when there is no earlier visit."""
    ms = rows["completed_date"].dt.to_period("M").dt.start_time
    left = pd.DataFrame({"business_id": rows["business_id"].values, "ms": ms.values, "i": np.arange(len(rows))})
    right = df[["business_id", "completed_date"]].rename(columns={"completed_date": "last"})
    m = pd.merge_asof(left.sort_values("ms"), right.sort_values("last"), left_on="ms", right_on="last",
                      by="business_id", allow_exact_matches=False, direction="backward").sort_values("i")
    days = (m["ms"] - m["last"]).dt.days.values
    iv = rows["business_type"].astype(str).map(interval).fillna(interval.median()).clip(lower=120).values
    return np.clip(np.where(np.isnan(days), iv, days) / iv, 0.2, 2.0)


def main():
    df = mf.add_features(mf.load())
    d = mf.routine_rows(df).reset_index(drop=True)
    y = d["major"].values.astype(int)
    date = d["completed_date"]

    # ---- rolling-origin backtest: is AUC stable across cutoffs? ----
    print("=== rolling-origin backtest (train <= cutoff, test the next 6 months) ===")
    rolling = []
    for cut in ["2024-06-30", "2024-12-31", "2025-06-30"]:
        cd = pd.Timestamp(cut)
        te = ((date > cd) & (date <= cd + pd.Timedelta(days=182))).values
        row = {"cutoff": cut, "n": int(te.sum())}
        for v, key in ((H, "auc"), (mf.WINDOW, "auc_window")):
            tr = mf.train_mask(d, v, end=cut)
            row[key] = round(roc_auc_score(y[te], mf.fit_predict(d, v, tr, te)), 3)
            if v == H:
                row["train_n"] = int(tr.sum())
        for c, key in (("persistence", "auc_persistence"), ("rule_mean_all", "auc_rule"), ("rule_mean12", "auc_rule_12m")):
            row[key] = round(roc_auc_score(y[te], d.loc[te, c]), 3)
        rolling.append(row)
        print(f"  cutoff {cut}: train {row['train_n']:>6,} test {row['n']:>6,} major {y[te].mean()*100:4.1f}%  AUC model "
              f"{row['auc']:.3f}  12-month model {row['auc_window']:.3f}  persistence {row['auc_persistence']:.3f}  "
              f"rule {row['auc_rule']:.3f}  12-month mean score {row['auc_rule_12m']:.3f}")

    # ---- main out-of-fold predictions: train <= 2024, test 2025+ ----
    te = (date > pd.Timestamp(mf.TRAIN_END)).values
    P = {v: mf.fit_predict(d, v, mf.train_mask(d, v), te) for v in (H, mf.WITH_ZIP, mf.WINDOW, "published")}
    rt_tr = d[~te].sort_values(["business_id", "completed_date"])
    interval = (rt_tr.assign(gap=rt_tr.groupby("business_id")["completed_date"].diff().dt.days)
                .groupby("business_type")["gap"].median())
    ratio = overdue_ratio(df, d[te], interval)
    s = d.loc[te, ["business_id", "completed_date", "major", "zip", "lat", "lng"]].copy()
    s["area"], s["district"] = areas(s)
    ARMS = {"Model": P[H], "Model with ZIP": P[mf.WITH_ZIP], "Model, 12-month window": P[mf.WINDOW],
            "Model as published (age leak)": P["published"], RULE: d.loc[te, mf.BASELINES[RULE]].values,
            "Mean routine score, last 12 months": d.loc[te, "rule_mean12"].values,
            "Persistence": d.loc[te, "persistence"].values, OVERDUE: P[H] * ratio}
    print(f"\nmain out-of-fold: test n={te.sum():,}  " + "  ".join(
        f"{a} AUC {roc_auc_score(y[te], v):.3f}" for a, v in ARMS.items()))
    print(f"areas: {s.loc[s['district'].notna(), 'district'].nunique()} council districts "
          f"({s['district'].notna().mean()*100:.0f}% of test inspections) + "
          f"{s.loc[s['district'].isna(), 'area'].nunique()} ZIP3 areas outside the City")

    def simulate(label, wfreq, by_area):
        """Days earlier than the actual order, per arm, with paired bootstrap CIs over windows."""
        s2 = s.copy(); s2["win"] = s2["completed_date"].dt.to_period(wfreq)
        keys = ["win", "area"] if by_area else ["win"]
        t = s2["completed_date"].values.astype("datetime64[D]").astype(float)
        de = {a: np.zeros(len(s2)) for a in ARMS}
        groups = s2.groupby(keys, sort=False).indices
        wid = np.empty(len(s2), dtype=int)
        for w, ix in enumerate(groups.values()):
            wid[ix] = w
            slots = np.sort(t[ix])
            for a, sc in ARMS.items():
                de[a][ix] = t[ix] - assigned(slots, sc[ix])        # >0: found earlier than it actually was
        mj = s2["major"].values == 1
        wins = pd.factorize(s2["win"])[0]; nw = wins.max() + 1
        N = np.bincount(wins, weights=mj, minlength=nw)
        Sm = {a: np.bincount(wins, weights=de[a]*mj, minlength=nw) for a in ARMS}
        rng = np.random.default_rng(0)
        C = np.stack([np.bincount(rng.integers(0, nw, nw), minlength=nw) for _ in range(BOOT)])   # windows resampled
        ci = lambda v: [round(float(x), 2) for x in np.percentile(v, [2.5, 97.5])]
        res = {"label": label, "windows": int(nw), "n_critical": int(mj.sum()), "arms": {}, "model_minus": {}}
        for a in ARMS:
            res["arms"][a] = {"days_earlier": round(float(de[a][mj].mean()), 2), "ci": ci(C @ Sm[a] / (C @ N)),
                              "share_earlier": round(float((de[a][mj] > 0).mean()), 3),
                              "clean_days": round(float(de[a][~mj].mean()), 2)}
        for a in ARMS:
            if a == "Model":
                continue
            res["model_minus"][a] = {"days": round(float(de["Model"][mj].mean() - de[a][mj].mean()), 2),
                                     "ci": ci(C @ (Sm["Model"] - Sm[a]) / (C @ N))}
        print(f"\n  {label}  ({nw} windows, {mj.sum():,} majors)")
        for a, r in res["arms"].items():
            print(f"    {a:32s} majors {r['days_earlier']:+.1f} days earlier than the actual order "
                  f"(95% CI {r['ci'][0]:+.1f} to {r['ci'][1]:+.1f}); {r['share_earlier']*100:.0f}% found earlier; "
                  f"clean facilities {r['clean_days']:+.1f} days")
        for a, r in res["model_minus"].items():
            print(f"    model minus {a:32s} {r['days']:+.1f} days (paired 95% CI {r['ci'][0]:+.1f} to {r['ci'][1]:+.1f})")
        return res, pd.DataFrame({"w": wid, "major": mj, "t": t, "area": s2["area"].values,
                                  "ms": s2["completed_date"].dt.to_period("M").dt.start_time.values
                                  .astype("datetime64[D]").astype(float), **{a: de[a] for a in ARMS}})

    print("\n=== DETECTION LATENCY: how much sooner majors surface under each ordering ===")
    print("(reorder a window's scheduled inspections; slots = the actual inspection dates; CIs resample windows.)")
    month, _ = simulate("within-month, county-wide pool", "M", False)
    area, per = simulate("within-month, within council district / ZIP3 area", "M", True)
    quarter, _ = simulate("within-quarter, county-wide (window-sensitivity)", "Q", False)
    results = [month, area, quarter]

    # ---- power for the pilot (docs/PILOT.md), from the City council district-months ----
    mj = per[per["major"] & per["area"].str.startswith("D")]
    w = mj.groupby("w").agg(n=("major", "size"), rule=(RULE, "mean"), model=("Model", "mean"),
                            day=("t", "mean"), ms=("ms", "mean"))
    w["model_minus_rule"] = w["model"] - w["rule"]
    w["day"] = w["day"] - w["ms"]                 # mean day of the month a major was found, usual order
    rng = np.random.default_rng(3)

    def n_needed(sd, delta, arms=1):
        return int(np.ceil(arms * (Z * sd / delta) ** 2))

    def emp_power(vals, n, delta, reps=4000):
        """Share of pilots of n district-months (resampled, shifted to a true mean of delta) whose
        one-sample t-test rejects 0 at 5%."""
        x = vals - vals.mean() + delta
        smp = x[rng.integers(0, len(x), (reps, n))]
        tstat = smp.mean(1) / (smp.std(1, ddof=1) / np.sqrt(n))
        from scipy.stats import t as tdist
        return float((np.abs(tstat) > tdist.ppf(0.975, n - 1)).mean())

    big = w[w["n"] >= 3]                          # district-months with at least 3 majors
    sd_rule, sd_mm, sd_day = float(w["rule"].std()), float(w["model_minus_rule"].std()), float(w["day"].std())
    power = {"windows": int(len(w)), "majors_per_window_median": float(w["n"].median()),
             "rule_mean": round(float(w["rule"].mean()), 2), "rule_sd": round(sd_rule, 2),
             "model_minus_rule_mean": round(float(w["model_minus_rule"].mean()), 2),
             "model_minus_rule_sd": round(sd_mm, 2),
             "day_mean": round(float(w["day"].mean()), 2), "day_sd": round(sd_day, 2),
             "silent_n_for_2d": n_needed(sd_rule, 2.0),
             "silent_n_for_observed_rule": n_needed(sd_rule, float(w["rule"].mean())),
             "silent_power_observed": {str(n): round(emp_power(w["rule"].values, n, float(w["rule"].mean())), 3)
                                       for n in (3, 6, 9)},
             "silent_n_for_2d_model_vs_rule": n_needed(sd_mm, 2.0),
             "silent_n_for_observed_model_vs_rule": n_needed(sd_mm, max(abs(float(w["model_minus_rule"].mean())), 0.05)),
             "randomized_n_per_arm_for_2d": n_needed(sd_day, 2.0, arms=2),
             "silent_power_2d": {str(n): round(emp_power(w["rule"].values, n, 2.0), 3) for n in (3, 6, 9, 12, 18, 27)},
             "big_windows": int(len(big)), "big_rule_sd": round(float(big["rule"].std()), 2),
             "big_silent_n_for_2d": n_needed(float(big["rule"].std()), 2.0)}
    print("\n=== power for a silent pilot (City council district-months with at least one major, 2025+) ===")
    print(f"  {power['windows']:,} district-months, median {power['majors_per_window_median']:.0f} majors each")
    print(f"  one-line rule vs the order worked, per district-month: mean {power['rule_mean']:+.1f} d, SD {sd_rule:.1f} d "
          f"-> {power['silent_n_for_2d']} district-months to detect 2 days (5%, 80%); empirical power at n = "
          + ", ".join(f"{k}: {v:.2f}" for k, v in power["silent_power_2d"].items()))
    print(f"  at the observed {power['rule_mean']:+.1f} d: {power['silent_n_for_observed_rule']} district-months; empirical "
          "power at n = " + ", ".join(f"{k}: {v:.2f}" for k, v in power["silent_power_observed"].items()))
    print(f"  (district-months with 3+ majors: SD {power['big_rule_sd']:.1f} d -> {power['big_silent_n_for_2d']})")
    print(f"  model minus rule, per district-month: mean {power['model_minus_rule_mean']:+.2f} d, SD {sd_mm:.1f} d -> "
          f"{power['silent_n_for_2d_model_vs_rule']} to detect 2 days, {power['silent_n_for_observed_model_vs_rule']:,} "
          f"to detect the observed difference")
    print(f"  randomized phase: mean day of the month a major is found, usual order: {power['day_mean']:.1f}, "
          f"SD across district-months {sd_day:.1f} d -> {power['randomized_n_per_arm_for_2d']} district-months per arm "
          f"to detect 2 days")

    # ---- chart: days earlier by ordering and window ----
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    rows = ["Within the month,\nwithin a district / ZIP3 area", "Within the month,\ncounty-wide pool",
            "Within the quarter,\ncounty-wide pool"]
    order = [area, month, quarter]
    arms = [("Model", "#1d6a97", "Research model"),
            (RULE, "#2f7d5b", "One-line rule: lowest mean routine score on record"),
            ("Persistence", "#c9741a", "Persistence: prior-year majors, then last score"),
            (OVERDUE, "#9aa7b1", "Model x overdue (old dashboard weighting)")]
    fig, ax = plt.subplots(figsize=(8.6, 6.3), dpi=150)
    hgt = 0.2
    for i, r in enumerate(order):
        base = len(order) - 1 - i
        for j, (a, col, lab) in enumerate(arms):
            v = r["arms"][a]; yv = base + (1.5 - j) * hgt
            ax.barh(yv, v["days_earlier"], height=hgt*0.92, color=col, label=lab if i == 0 else None,
                    xerr=[[v["days_earlier"] - v["ci"][0]], [v["ci"][1] - v["days_earlier"]]], capsize=3,
                    error_kw=dict(ecolor="#33434f", lw=1))
            ax.text(max(v["ci"][1], 0) + 0.3, yv, f"{v['days_earlier']:+.1f} d", va="center", fontsize=8.2, color="#243542")
    ax.set_yticks([len(order) - 1 - i for i in range(len(order))]); ax.set_yticklabels(rows, fontsize=10)
    ax.set_xlim(min(0, min(r["arms"][a]["ci"][0] for r in order for a, *_ in arms) * 1.2),
                max(r["arms"][a]["ci"][1] for r in order for a, *_ in arms) * 1.2)
    ax.set_xlabel("average days a major violation is found earlier than in the order actually worked", fontsize=9)
    mm = area["model_minus"]["Persistence"]; ms = area["model_minus"][RULE]
    ax.text(0, 1.13, "Most of the head start needs no model", transform=ax.transAxes, fontsize=13,
            fontweight="bold", va="bottom")
    ax.text(0, 1.03, f"Within a district's month the model adds {mm['days']:+.1f} d over persistence ({mm['ci'][0]:+.1f} to "
            f"{mm['ci'][1]:+.1f}) and {ms['days']:+.1f} d over the one-line rule ({ms['ci'][0]:+.1f} to {ms['ci'][1]:+.1f}). "
            "95% CIs over months.", transform=ax.transAxes, fontsize=8.2, color="#5a6b78", va="bottom")
    ax.legend(frameon=False, fontsize=7.8, loc="upper center", bbox_to_anchor=(0.45, -0.11), ncol=2)
    for sp in ["top", "right", "left"]: ax.spines[sp].set_visible(False)
    ax.tick_params(left=False); ax.grid(axis="x", color="#eef1f3")
    fig.text(0.012, 0.012, f"SD 2025+ routine inspections, out-of-fold, n={month['n_critical']:,} with a major. Zero-sum reorder "
             f"of the same dates: clean facilities wait {abs(area['arms']['Model']['clean_days']):.1f} d longer (district "
             "month). Assumes findings do not depend on the day; ignores routing. Detection latency, not prevented illness.",
             fontsize=6.8, color="#7a8791", wrap=True)
    fig.subplots_adjust(left=0.25, right=0.97, top=0.86, bottom=0.25)
    fig.savefig("food_days_earlier.png", bbox_inches="tight")
    print("saved food_days_earlier.png")

    mf.save_results("sim", {"rolling": rolling, "windows": {k: r for k, r in zip(["month", "month_area", "quarter"], results)},
                            "power": power, "overdue_interval_from": "2023-24 routine gaps by type"})
    print(f"wrote {mf.RESULTS}")


if __name__ == "__main__":
    main()
