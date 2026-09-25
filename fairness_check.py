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


def by_group(t, col, q, labels):
    tt = t.dropna(subset=[col]).copy()
    tt["grp"] = pd.qcut(tt[col], q, labels=labels, duplicates="drop")
    rows = []
    for grp, gp in tt.groupby("grp", observed=True):
        crit = gp[gp["major"] == 1]
        r = {"group": grp, "n": len(gp), "actual_major_%": round(gp["major"].mean()*100, 1),
             "model_flag_%": round(gp["flag"].mean()*100, 1), "mean_risk_%": round(gp["p"].mean()*100, 1),
             "recall_of_crit_%": round(crit["flag"].mean()*100, 1) if len(crit) else np.nan}
        for a, col_ in (("zip", "zflag"), ("rule", "rflag"), ("persist", "pflag")):
            r[f"{a}_flag_%"] = round(gp[col_].mean()*100, 1)
            r[f"{a}_recall_%"] = round(crit[col_].mean()*100, 1) if len(crit) else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def main():
    df = mf.add_features(mf.load())
    d = mf.routine_rows(df)
    d["zip5"] = d["zip"].astype(str).str.extract(r"(\d{5})")[0]
    te = (d["completed_date"] > pd.Timestamp(mf.TRAIN_END)).to_numpy()
    t = d.loc[te].copy()
    t["p"] = mf.fit_predict(d, mf.HEADLINE, mf.train_mask(d, mf.HEADLINE), te)
    t["pz"] = mf.fit_predict(d, mf.WITH_ZIP, mf.train_mask(d, mf.WITH_ZIP), te)
    t["major"] = t["major"].astype(int)
    t["flag"] = mf.top_weights(t["p"].values)                         # "top 20% county-wide"
    t["zflag"] = mf.top_weights(t["pz"].values)
    t["rflag"] = mf.top_weights(t[mf.BASELINES[mf.RULE]].values)      # the one-line rule's top 20%
    t["pflag"] = mf.top_weights(t["persistence"].values)              # persistence's top 20%

    zips = sorted(t["zip5"].dropna().unique().tolist())
    inc, hisp = acs(zips)
    t["income"] = t["zip5"].map(inc); t["pct_hisp"] = t["zip5"].map(hisp)
    cov = t["income"].notna().mean(); matched = len(set(zips) & set(inc))
    print(f"test inspections: {len(t):,}  | income coverage: {cov*100:.0f}%  | zips matched: {matched}/{len(zips)}")
    print(f"model = {mf.HEADLINE}; one-line rule = {mf.RULE}")

    pd.set_option("display.width", 200)
    print("\n=== BY ZIP MEDIAN INCOME (Q1=lowest income) ===")
    gi = by_group(t, "income", 4, ["Q1 low", "Q2", "Q3", "Q4 high"]); print(gi.to_string(index=False))
    print("\n=== BY ZIP % HISPANIC (T3=highest) ===")
    gh = by_group(t, "pct_hisp", 3, ["T1 low", "T2", "T3 high"]); print(gh.to_string(index=False))

    lo, hi = gi.iloc[0], gi.iloc[-1]
    ratio = lambda c: lo[c] / max(hi[c], 1e-9)
    flag_ratio, act_ratio = ratio("model_flag_%"), ratio("actual_major_%")
    print("\n--- disparate-impact read (income) ---")
    print(f"flag rate  low-income / high-income: model {flag_ratio:.2f}x, with ZIP {ratio('zip_flag_%'):.2f}x, "
          f"one-line rule {ratio('rule_flag_%'):.2f}x, persistence {ratio('persist_flag_%'):.2f}x")
    print(f"ACTUAL rate low-income / high-income = {act_ratio:.2f}x")
    print("If those ratios are similar, targeting tracks real risk (calibrated), not bias.")
    cal_gap = (gi["mean_risk_%"] - gi["actual_major_%"])
    print(f"Calibration: mean_risk_% minus actual_major_% by income group: {', '.join(f'{v:+.1f}' for v in cal_gap)} pts")
    print("Equal opportunity, recall of true major violations, lowest to highest income quartile:")
    for a, c in (("model", "recall_of_crit_%"), ("zip", "zip_recall_%"), ("rule", "rule_recall_%"),
                 ("persist", "persist_recall_%")):
        print(f"  {ARMS[a]:18s} {' / '.join(f'{v:.0f}%' for v in gi[c])}   (by % Hispanic, low to high: "
              f"{' / '.join(f'{v:.0f}%' for v in gh[c])})")

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
    fig.text(0.01, 0.01, "SD 2025+ routine inspections (out-of-fold). Income = ZIP median household income (ACS via "
             "Census Reporter). Facilities that still exist only.", fontsize=7, color="#777")
    fig.tight_layout(rect=[0, 0.03, 1, 0.90]); fig.savefig("food_fairness.png", bbox_inches="tight")
    print("\nsaved food_fairness.png")

    rec = lambda frame: frame.assign(group=frame["group"].astype(str)).to_dict("records")
    mf.save_results("fairness", {
        "model": mf.HEADLINE, "rule": mf.RULE,
        "test_n": int(len(t)), "income_coverage": round(float(cov), 3), "zips_matched": matched, "zips": len(zips),
        "flag_ratio": round(float(flag_ratio), 2), "actual_ratio": round(float(act_ratio), 2),
        "zip_flag_ratio": round(float(ratio("zip_flag_%")), 2),
        "rule_flag_ratio": round(float(ratio("rule_flag_%")), 2),
        "persist_flag_ratio": round(float(ratio("persist_flag_%")), 2),
        "income": rec(gi), "hispanic": rec(gh),
        "recall_low": float(lo["recall_of_crit_%"]), "recall_high": float(hi["recall_of_crit_%"]),
        "zip_recall_low": float(lo["zip_recall_%"]), "zip_recall_high": float(hi["zip_recall_%"]),
        "rule_recall_low": float(lo["rule_recall_%"]), "rule_recall_high": float(hi["rule_recall_%"]),
        "persist_recall_low": float(lo["persist_recall_%"]), "persist_recall_high": float(hi["persist_recall_%"])})
    print(f"wrote {mf.RESULTS}")


if __name__ == "__main__":
    main()
