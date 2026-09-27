"""Threshold trade-offs for the risk model. Two things:
  A) GLOBAL: precision / recall / lift as you move the flag cutoff (just reading the gains and PR
     curves at points). AUC is fixed; the threshold only trades precision for recall. The one-line
     rule (model_food.RULE: lowest mean routine score on record first) and the persistence
     ordering (export_site.persistence) are shown beside it: what needs no model.
  B) EQUAL-OPPORTUNITY: per-income-group thresholds that EQUALIZE recall, vs one global threshold
     that doesn't. Shows the fix works, and its cost: to equalize recall you must flag some ZIPs
     MORE (lower their cutoff), i.e. group-conscious decisions using an income/ZIP proxy =
     disparate *treatment*, the legally harder trade-off.
  C) the same, OUT OF SAMPLE: the global top-20% cut and the per-group cuts are set on the 2025
     inspections and applied, unchanged, to 2026's. What equalizing would really have cost, and
     whether it holds, with a 95% interval (resampling whole ZIPs) on the extra flag budget.
Out-of-fold (train <= 2024, test 2025+), the research model (model_food.HEADLINE) as deployed
(trained and scored on features as of the 1st of each inspection's month), with the same whole-ZIP
income groups as fairness_check.py. The per-group cuts in B are set on the test labels themselves,
so B's flag budget is an in-sample figure; C is not."""
import pandas as pd, numpy as np, json, os
from sklearn.metrics import roc_auc_score
import model_food as mf
from fairness_check import zip_groups


GROUPS = ["Q1 low", "Q2", "Q3", "Q4 high"]


def at(score, yv, q):
    """Precision and recall of the top q (ties at the cut split pro rata)."""
    w = mf.top_weights(score, q)
    return (w*yv).sum()/w.sum(), (w*yv).sum()/yv.sum()


def equal_opportunity_cuts(p, y, grp, target):
    """Per-group score cutoffs that flag `target` of each group's positives (score >= cut)."""
    p, y, grp = np.asarray(p, float), np.asarray(y), np.asarray(grp, dtype=object)
    return {g: float(np.quantile(p[(grp == g) & (y == 1)], 1 - target)) for g in pd.unique(grp)}


def main():
    df = mf.add_features(mf.load())
    d = mf.routine_rows(df)
    d["zip5"] = d["zip"].astype(str).str.extract(r"(\d{5})")[0]
    te = (d["completed_date"] > pd.Timestamp(mf.TRAIN_END)).to_numpy()
    ms = mf.month_start_rows(df, d)
    dm = ms[te]
    p = mf.fit_as_deployed(ms, mf.train_mask(d, mf.HEADLINE)).predict(dm)
    yt = d.loc[te, "major"].values.astype(int); base = yt.mean()
    pers = dm["persistence"].values; rule = dm[mf.BASELINES[mf.RULE]].values

    print(f"test n={len(yt):,}  base rate={base:.3f}  AUC model={roc_auc_score(yt,p):.3f}  "
          f"one-line rule={roc_auc_score(yt,rule):.3f}  persistence={roc_auc_score(yt,pers):.3f}\n")
    print("=== A) GLOBAL threshold: one knob, precision <-> recall (AUC is fixed) ===")
    print(f"{'flag %':>7} {'precision':>10} {'recall':>8} {'lift':>6}   | rule: {'precision':>9} {'recall':>7}"
          f"   | persistence: {'precision':>9} {'recall':>7}")
    glob = {}
    for q in [0.10, 0.20, 0.30, 0.40, 0.50]:
        pm, rm = at(p, yt, q); pr, rr = at(rule, yt, q); pp, rp = at(pers, yt, q)
        glob[f"{int(q*100)}%"] = {"model": [round(pm, 3), round(rm, 3)], "rule": [round(pr, 3), round(rr, 3)],
                                   "persistence": [round(pp, 3), round(rp, 3)]}
        print(f"{q*100:6.0f}% {pm:10.2f} {rm:8.2f} {pm/base:5.2f}x   | {'':6} {pr:9.2f} {rr:7.2f}   | {'':13} {pp:9.2f} {rp:7.2f}")

    # ---- B) per-group equal-opportunity vs one global threshold ----
    inc = {}
    if os.path.exists("acs_cache.json"):
        with open("acs_cache.json", encoding="utf-8") as fh:
            inc = json.load(fh).get("inc", {})
    t = pd.DataFrame({"p": p, "y": yt, "zip5": d.loc[te, "zip5"].values, "pw": mf.top_weights(pers),
                      "rw": mf.top_weights(rule), "flag": mf.top_weights(p),
                      "year": d.loc[te, "completed_date"].dt.year.values})
    t["income"] = t["zip5"].map(inc)
    t = t.dropna(subset=["income"])
    t["grp"] = pd.Categorical(zip_groups(t, "income", GROUPS), categories=GROUPS, ordered=True)
    crit_all = t[t["y"] == 1]
    TARGET = round(float(crit_all.groupby("grp", observed=True)["flag"].mean().max()), 2)   # best group's recall
    print(f"\n=== B) recall by income group: ONE global cut (top 20%) vs PER-GROUP equal-opportunity ===")
    print(f"(equal-opp targets recall={TARGET:.0%} in every group, the best group's recall under the global cut)")
    print(f"{'group':8} {'global flag%':>12} {'global recall':>14}   |{'eq-opp flag%':>13} {'eq-opp recall':>14}"
          f"   | rule flag% recall%  | persistence flag% recall%")
    tot_g = []; tot_e = []; groups = {}
    cuts = equal_opportunity_cuts(t["p"], t["y"], t["grp"].astype(str), TARGET)
    for grp, gp in t.groupby("grp", observed=True):
        crit = gp[gp["y"] == 1]
        g_flag = gp["flag"].mean(); g_rec = crit["flag"].mean()
        ethr = cuts[str(grp)]                              # per-group cut hitting TARGET recall
        e_flag = (gp["p"] >= ethr).mean(); e_rec = (crit["p"] >= ethr).mean()
        tot_g.append(g_flag*len(gp)); tot_e.append(e_flag*len(gp))
        groups[str(grp)] = {"global_flag": round(g_flag*100, 1), "global_recall": round(g_rec*100, 1),
                            "eq_flag": round(e_flag*100, 1), "eq_recall": round(e_rec*100, 1),
                            "rule_flag": round(gp["rw"].mean()*100, 1), "rule_recall": round(crit["rw"].mean()*100, 1),
                            "persist_flag": round(gp["pw"].mean()*100, 1), "persist_recall": round(crit["pw"].mean()*100, 1)}
        print(f"{grp:8} {g_flag*100:11.1f}% {g_rec*100:13.1f}%   |{e_flag*100:12.1f}% {e_rec*100:13.1f}%   | "
              f"{gp['rw'].mean()*100:10.1f}% {crit['rw'].mean()*100:6.1f}%  | {gp['pw'].mean()*100:17.1f}% {crit['pw'].mean()*100:6.1f}%")
        assert abs(e_rec-TARGET) < 0.06, "per-group threshold missed target recall"
    print(f"{'TOTAL':8} {sum(tot_g)/len(t)*100:11.1f}% {'(unequal)':>13}   |{sum(tot_e)/len(t)*100:12.1f}% {'(equalized)':>14}")
    print("\nRead: equal-opp flattens recall across groups, but the flag% RISES MOST for the groups the")
    print("global cut under-serves (their cutoff is lowered): that is the disparate-*treatment* cost of")
    print("using income to set cutoffs, and it spends more total inspection capacity. The rule and")
    print("persistence columns spend the same top-20% budget on the record alone.")

    # ---- C) out of sample: every cut set on 2025, applied unchanged to 2026 ----
    fit, ev = t[t["year"] == 2025], t[t["year"] >= 2026].copy()
    g_cut = float(np.quantile(fit["p"], 0.80))                      # 2025's top-20% score
    fit_rec = fit[fit["y"] == 1].groupby("grp", observed=True)["p"].apply(lambda s: (s >= g_cut).mean())
    target_oos = round(float(fit_rec.max()), 2)
    cuts_oos = equal_opportunity_cuts(fit["p"], fit["y"], fit["grp"].astype(str), target_oos)
    ev["g"] = (ev["p"] >= g_cut).astype(float)
    ev["e"] = (ev["p"] >= ev["grp"].astype(str).map(cuts_oos)).astype(float)
    oos = {"cuts_set_on": "2025", "applied_to": f"2026 ({len(ev):,} inspections)", "target_recall": target_oos,
           "global": {"flag_pct": round(100 * ev["g"].mean(), 1)}, "equal_opportunity": {"flag_pct": round(100 * ev["e"].mean(), 1)}}
    for k in ("global", "equal_opportunity"):
        c = "g" if k == "global" else "e"
        oos[k]["recall_pct"] = {str(g): round(100 * float(gp.loc[gp["y"] == 1, c].mean()), 1)
                                for g, gp in ev.groupby("grp", observed=True)}
        oos[k]["flag_pct_by_group"] = {str(g): round(100 * float(gp[c].mean()), 1) for g, gp in ev.groupby("grp", observed=True)}
    zc = pd.factorize(ev["zip5"])[0]
    oos["extra_flag_pts"] = round(oos["equal_opportunity"]["flag_pct"] - oos["global"]["flag_pct"], 1)
    oos["extra_flag_pts_ci"] = [round(100 * v, 1) for v in mf.facility_interval(
        zc, lambda w: ((w * ev["e"].values).sum() - (w * ev["g"].values).sum()) / w.sum())]
    for k in ("global", "equal_opportunity"):
        r = oos[k]["recall_pct"].values()
        oos[k]["recall_spread_pts"] = round(max(r) - min(r), 1)
    print(f"\n=== C) OUT OF SAMPLE: cuts set on 2025, applied to {oos['applied_to']} (target recall {target_oos:.0%}) ===")
    print(f"{'group':8} {'global flag%':>12} {'recall':>7}   | {'eq-opp flag%':>12} {'recall':>7}")
    for g in oos["global"]["recall_pct"]:
        print(f"{g:8} {oos['global']['flag_pct_by_group'][g]:11.1f}% {oos['global']['recall_pct'][g]:6.1f}%   | "
              f"{oos['equal_opportunity']['flag_pct_by_group'][g]:11.1f}% {oos['equal_opportunity']['recall_pct'][g]:6.1f}%")
    print(f"{'TOTAL':8} {oos['global']['flag_pct']:11.1f}% {'':7}   | {oos['equal_opportunity']['flag_pct']:11.1f}%")
    print(f"recall spread across groups: global {oos['global']['recall_spread_pts']:.1f} pts, equal-opportunity "
          f"{oos['equal_opportunity']['recall_spread_pts']:.1f} pts; extra flag budget {oos['extra_flag_pts']:+.1f} pts "
          f"(95% CI {oos['extra_flag_pts_ci'][0]:+.1f} to {oos['extra_flag_pts_ci'][1]:+.1f}, whole ZIPs resampled)")
    mf.save_results("threshold", {"global": glob, "target_recall": TARGET, "by_income": groups,
                                  "eq_total_flag": round(sum(tot_e)/len(t)*100, 1), "out_of_sample": oos})


if __name__ == "__main__":
    main()
