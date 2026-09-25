"""Disparate-impact check for the food-inspection risk model.
Question: does the model over-target lower-income / higher-Hispanic areas BEYOND their actual
violation rate (bias), or does its targeting track real risk (calibrated)? Uses out-of-fold 2025+
predictions joined to ZIP-level ACS income + %Hispanic (Census Reporter, keyless). Reports
flag-rate disparity vs actual-rate disparity, per-group calibration, and equal-opportunity
(recall) parity, for four orderings of the same inspections, each flagging its top 20% (ties
split pro rata):
  * the research model (model_food.HEADLINE, no ZIP);
  * the same model with ZIP (model_food.WITH_ZIP): is ZIP the channel for a gap?
  * the one-line rule outreach leads with (model_food.RULE: lowest mean routine score first);
  * persistence (export_site.persistence), what an inspector already has.
Every test inspection is at a facility that still exists (SD Food Info lists only those), so
the recall figures are among survivors; see README, "Survivorship"."""
import pandas as pd, numpy as np, requests, time, json, os
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import model_food as mf

ARMS = {"model": "Model", "zip": "Model with ZIP", "rule": "One-line rule", "persist": "Persistence"}


def acs(zips):
    """ZIP -> median household income and % Hispanic (ACS 5-yr via Census Reporter), cached."""
    if os.path.exists("acs_cache.json"):
        c = json.load(open("acs_cache.json")); print("loaded ACS cache")
        return c["inc"], c["hisp"]
    H = {"User-Agent": "sdfood-inspection-fairness/1.0 (civic research)"}
    URL = "https://api.censusreporter.org/1.0/data/show/latest"
    inc, hisp = {}, {}

    def parse(js):
        for gid, tabs in js.get("data", {}).items():
            z = gid.split("US")[-1]
            v = tabs.get("B19013", {}).get("estimate", {}).get("B19013001")
            if v and v > 0: inc[z] = v
            b = tabs.get("B03002", {}).get("estimate", {})
            tot = b.get("B03002001"); h = b.get("B03002012")
            if tot: hisp[z] = (h or 0) / tot * 100

    def fetch(zlist):
        return requests.get(URL, params={"table_ids": "B19013,B03002", "geo_ids": ",".join("86000US"+z for z in zlist)},
                            headers=H, timeout=90)
    for i in range(0, len(zips), 5):
        batch = zips[i:i+5]
        r = fetch(batch)
        if r.status_code == 200: parse(r.json())
        else:                               # a bad zip in the batch -> try each alone
            for z in batch:
                rr = fetch([z])
                if rr.status_code == 200: parse(rr.json())
                time.sleep(0.15)
        time.sleep(0.25)
    json.dump({"inc": inc, "hisp": hisp}, open("acs_cache.json", "w"))
    return inc, hisp


def zip_groups(t, col, labels):
    """Whole ZIPs into len(labels) ordered groups of about equal inspection counts (the midpoint of
    each ZIP's cumulative share decides its group). A ZIP is never split across groups, which
    pd.qcut on inspection rows did; ZIPs without the ACS value get no group."""
    z = t.dropna(subset=[col]).groupby("zip5").agg(v=(col, "first"), n=(col, "size")).sort_values("v", kind="stable")
    mid = (z["n"].cumsum() - z["n"] / 2) / z["n"].sum()
    k = len(labels)
    z["grp"] = [labels[min(int(m * k), k - 1)] for m in mid]
    return t["zip5"].map(z["grp"])


FLAGS = {"model": "flag", "zip": "zflag", "rule": "rflag", "persist": "pflag"}


def by_group(t, grp, labels):
    rows = []
    for g in labels:
        gp = t[grp == g]
        if not len(gp):
            continue
        crit, clean = gp[gp["major"] == 1], gp[gp["major"] == 0]
        r = {"group": g, "n": len(gp), "zips": int(gp["zip5"].nunique()), "actual_major_%": round(gp["major"].mean()*100, 1),
             "model_flag_%": round(gp["flag"].mean()*100, 1), "mean_risk_%": round(gp["p"].mean()*100, 1),
             "recall_of_crit_%": round(crit["flag"].mean()*100, 1) if len(crit) else np.nan,
             "model_fpr_%": round(clean["flag"].mean()*100, 1) if len(clean) else np.nan}
        for a, col_ in (("zip", "zflag"), ("rule", "rflag"), ("persist", "pflag")):
            r[f"{a}_flag_%"] = round(gp[col_].mean()*100, 1)
            r[f"{a}_recall_%"] = round(crit[col_].mean()*100, 1) if len(crit) else np.nan
            r[f"{a}_fpr_%"] = round(clean[col_].mean()*100, 1) if len(clean) else np.nan
        for a in ("model", "rule"):
            r[f"{a}_days_sooner"] = round(float(crit[f"days_{a}"].mean()), 2) if len(crit) else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def cluster_cis(t, grp, labels, boot=None, seed=0):
    """95% intervals that resample whole ZIPs (the unit the groups are made of): recall, false
    positive rate and flag rate per group and arm, the lowest-minus-highest recall gap, the
    lowest/highest flag-rate and actual-rate ratios, and days sooner for majors per group."""
    boot = boot or mf.BOOT
    m = grp.notna().to_numpy()
    tt, g = t[m], grp[m].to_numpy()
    codes, uniq = pd.factorize(tt["zip5"])
    nz = len(uniq)
    zg = pd.Series(g).groupby(codes).first().reindex(range(nz)).to_numpy()
    y = tt["major"].to_numpy().astype(float)
    per = lambda v: np.bincount(codes, weights=v, minlength=nz)
    C = np.random.default_rng(seed).integers(0, nz, (boot, nz))
    C = np.stack([np.bincount(r, minlength=nz) for r in C]).astype(float)
    ci = lambda v: [round(float(x), 2) for x in np.nanpercentile(v, [2.5, 97.5])]
    out = {}
    n_z, y_z = per(np.ones(len(y))), per(y)
    G = {lab: (zg == lab).astype(float) for lab in labels}
    tot = lambda z: {lab: C @ (z * G[lab]) for lab in labels}
    N, Y = tot(n_z), tot(y_z)
    out["actual_ratio"] = ci((Y[labels[0]] / N[labels[0]]) / (Y[labels[-1]] / N[labels[-1]]))
    for a, col in FLAGS.items():
        f = tt[col].to_numpy()
        F, FY = tot(per(f)), tot(per(f * y))
        rec = {lab: 100 * FY[lab] / Y[lab] for lab in labels}
        fpr = {lab: 100 * (F[lab] - FY[lab]) / (N[lab] - Y[lab]) for lab in labels}
        out[a] = {"recall_%": {lab: ci(rec[lab]) for lab in labels},
                  "fpr_%": {lab: ci(fpr[lab]) for lab in labels},
                  "recall_gap_low_minus_high_pts": ci(rec[labels[0]] - rec[labels[-1]]),
                  "flag_ratio_low_over_high": ci((F[labels[0]] / N[labels[0]]) / (F[labels[-1]] / N[labels[-1]]))}
    for a in ("model", "rule"):
        dsum = tot(per(tt[f"days_{a}"].to_numpy() * y))
        out[a]["days_sooner"] = {lab: ci(dsum[lab] / Y[lab]) for lab in labels}
    return out


def main():
    import sim_schedule as ss
    df = mf.add_features(mf.load())
    d = mf.routine_rows(df)
    d["zip5"] = d["zip"].astype(str).str.extract(r"(\d{5})")[0]
    te = (d["completed_date"] > pd.Timestamp(mf.TRAIN_END)).to_numpy()
    # scored as deployed: features as of the 1st of each inspection's month (model_food.month_start_rows)
    dm = mf.month_start_rows(df, d[te])
    t = d.loc[te, ["business_id", "completed_date", "major", "zip", "zip5", "lat", "lng"]].copy()
    t["p"] = mf.Model(mf.HEADLINE).fit(d[mf.train_mask(d, mf.HEADLINE)]).predict(dm)
    t["pz"] = mf.Model(mf.WITH_ZIP).fit(d[mf.train_mask(d, mf.WITH_ZIP)]).predict(dm)
    t["rule"] = dm[mf.BASELINES[mf.RULE]].values
    t["pers"] = dm["persistence"].values
    t["major"] = t["major"].astype(int)
    t["flag"] = mf.top_weights(t["p"].values)                         # "top 20% county-wide"
    t["zflag"] = mf.top_weights(t["pz"].values)
    t["rflag"] = mf.top_weights(t["rule"].values)                     # the one-line rule's top 20%
    t["pflag"] = mf.top_weights(t["pers"].values)                     # persistence's top 20%
    # the policy actually proposed: reorder each council district's (or ZIP3 area's) month
    t["area"], _ = ss.areas(t)
    pools = t["completed_date"].dt.to_period("M").astype(str) + "|" + t["area"].astype(str)
    days = t["completed_date"].values.astype("datetime64[D]").astype(float)
    for a, col in (("model", "p"), ("rule", "rule")):
        gain = np.zeros(len(t))
        for ix in t.groupby(pools.values, sort=False).indices.values():
            gain[ix] = days[ix] - ss.assigned(np.sort(days[ix]), t[col].values[ix])
        t[f"days_{a}"] = gain

    zips = sorted(t["zip5"].dropna().unique().tolist())
    inc, hisp = acs(zips)
    t["income"] = t["zip5"].map(inc); t["pct_hisp"] = t["zip5"].map(hisp)
    cov = t["income"].notna().mean(); matched = len(set(zips) & set(inc))
    print(f"test inspections: {len(t):,}  | income coverage: {cov*100:.0f}%  | zips matched: {matched}/{len(zips)}")
    print(f"model = {mf.HEADLINE}; one-line rule = {mf.RULE}; scored as deployed (features as of the 1st of the month)")

    INC, HIS = ["Q1 low", "Q2", "Q3", "Q4 high"], ["T1 low", "T2", "T3 high"]
    gi_grp, gh_grp = zip_groups(t, "income", INC), zip_groups(t, "pct_hisp", HIS)
    pd.set_option("display.width", 220)
    print("\n=== BY ZIP MEDIAN INCOME (Q1=lowest income; whole ZIPs per group) ===")
    gi = by_group(t, gi_grp, INC); print(gi.to_string(index=False))
    print("\n=== BY ZIP % HISPANIC (T3=highest) ===")
    gh = by_group(t, gh_grp, HIS); print(gh.to_string(index=False))
    ci_i, ci_h = cluster_cis(t, gi_grp, INC), cluster_cis(t, gh_grp, HIS, seed=1)

    lo, hi = gi.iloc[0], gi.iloc[-1]
    ratio = lambda c: lo[c] / max(hi[c], 1e-9)
    flag_ratio, act_ratio = ratio("model_flag_%"), ratio("actual_major_%")
    print("\n--- disparate-impact read (income; 95% intervals resample whole ZIPs) ---")
    print(f"flag rate  low-income / high-income: model {flag_ratio:.2f}x {ci_i['model']['flag_ratio_low_over_high']}, "
          f"with ZIP {ratio('zip_flag_%'):.2f}x, one-line rule {ratio('rule_flag_%'):.2f}x "
          f"{ci_i['rule']['flag_ratio_low_over_high']}, persistence {ratio('persist_flag_%'):.2f}x")
    print(f"ACTUAL rate low-income / high-income = {act_ratio:.2f}x {ci_i['actual_ratio']}")
    cal_gap = (gi["mean_risk_%"] - gi["actual_major_%"])
    print(f"Calibration-in-the-large: mean_risk_% minus actual_major_% by income group: "
          f"{', '.join(f'{v:+.1f}' for v in cal_gap)} pts")
    print("Recall of true major violations (top 20% county-wide), lowest to highest income quartile, with the gap's CI:")
    for a, c in (("model", "recall_of_crit_%"), ("zip", "zip_recall_%"), ("rule", "rule_recall_%"),
                 ("persist", "persist_recall_%")):
        print(f"  {ARMS[a]:18s} {' / '.join(f'{v:.0f}%' for v in gi[c])}   gap low minus high "
              f"{gi[c].iloc[0] - gi[c].iloc[-1]:+.1f} pts {ci_i[a]['recall_gap_low_minus_high_pts']}")
    print("Days sooner for majors, reordering each district's month (the proposed use), lowest to highest income:")
    for a in ("model", "rule"):
        print(f"  {ARMS[a]:18s} " + " / ".join(f"{v:+.1f} d {ci_i[a]['days_sooner'][g]}" for g, v in
                                                 zip(gi['group'], gi[f'{a}_days_sooner'])))
    print("If an interval covers equality (0 for a gap, 1 for a ratio), the data cannot tell the groups apart.")

    # ---- chart: actual vs predicted by income quartile ----
    fig, ax = plt.subplots(figsize=(8.4, 4.6), dpi=150)
    x = np.arange(len(gi))
    ax.bar(x-0.2, gi["actual_major_%"], 0.4, color="#5a6b78", label="actual major-violation rate")
    ax.bar(x+0.2, gi["mean_risk_%"], 0.4, color="#1d6a97", label="model's average predicted risk")
    for xi, v in zip(x-0.2, gi["actual_major_%"]): ax.text(xi, v+0.3, f"{v:.1f}%", ha="center", fontsize=8.5, color="#445")
    for xi, v in zip(x+0.2, gi["mean_risk_%"]): ax.text(xi, v+0.3, f"{v:.1f}%", ha="center", fontsize=8.5, color="#134d6e")
    ax.set_xticks(x); ax.set_xticklabels(gi["group"]); ax.set_ylabel("% of routine inspections")
    ax.set_ylim(0, max(gi["actual_major_%"].max(), gi["mean_risk_%"].max())*1.35)
    ax.text(0, 1.16, "Predicted vs actual major-violation rate, by ZIP income", transform=ax.transAxes, fontsize=13,
            fontweight="bold", va="bottom")
    ax.text(0, 1.03, f"Predicted minus actual: {', '.join(f'{g} {v:+.1f}' for g, v in zip(gi['group'], cal_gap))} pts. "
            f"{'No group is scored below its actual rate.' if cal_gap.min() > -0.5 else ''}",
            transform=ax.transAxes, fontsize=8.8, color="#5a6b78", va="bottom")
    ax.legend(frameon=False, fontsize=9.5, loc="upper right")
    for sp in ["top", "right"]: ax.spines[sp].set_visible(False)
    ax.grid(axis="y", color="#eee")
    fig.text(0.01, 0.01, "SD 2025+ routine inspections (out-of-fold, scored as of the 1st of each month). Income = ZIP "
             "median household income (ACS). Whole ZIPs per group. Facilities that still exist only.", fontsize=7, color="#777")
    fig.tight_layout(rect=[0, 0.03, 1, 0.90]); fig.savefig("food_fairness.png", bbox_inches="tight")
    print("\nsaved food_fairness.png")

    rec = lambda frame: frame.assign(group=frame["group"].astype(str)).to_dict("records")
    mf.save_results("fairness", {
        "model": mf.HEADLINE, "rule": mf.RULE, "scored": "as deployed: features as of the 1st of each month",
        "grouping": "whole ZIPs, about equal inspection counts per group",
        "test_n": int(len(t)), "income_coverage": round(float(cov), 3), "zips_matched": matched, "zips": len(zips),
        "flag_ratio": round(float(flag_ratio), 2), "actual_ratio": round(float(act_ratio), 2),
        "zip_flag_ratio": round(float(ratio("zip_flag_%")), 2),
        "rule_flag_ratio": round(float(ratio("rule_flag_%")), 2),
        "persist_flag_ratio": round(float(ratio("persist_flag_%")), 2),
        "income": rec(gi), "hispanic": rec(gh), "ci_income": ci_i, "ci_hispanic": ci_h,
        "recall_low": float(lo["recall_of_crit_%"]), "recall_high": float(hi["recall_of_crit_%"]),
        "zip_recall_low": float(lo["zip_recall_%"]), "zip_recall_high": float(hi["zip_recall_%"]),
        "rule_recall_low": float(lo["rule_recall_%"]), "rule_recall_high": float(hi["rule_recall_%"]),
        "persist_recall_low": float(lo["persist_recall_%"]), "persist_recall_high": float(hi["persist_recall_%"])})
    print(f"wrote {mf.RESULTS}")


if __name__ == "__main__":
    main()
