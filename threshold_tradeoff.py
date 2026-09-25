"""Threshold trade-offs for the risk model. Two things:
  A) GLOBAL: precision / recall / lift as you move the flag cutoff (just reading the gains and PR
     curves at points). AUC is fixed; the threshold only trades precision for recall. The one-line
     rule (model_food.RULE: lowest mean routine score on record first) and the persistence
     ordering (export_site.persistence) are shown beside it: what needs no model.
  B) EQUAL-OPPORTUNITY: per-income-group thresholds that EQUALIZE recall, vs one global threshold
     that doesn't. Shows the fix works, and its cost: to equalize recall you must flag some ZIPs
     MORE (lower their cutoff), i.e. group-conscious decisions using an income/ZIP proxy =
     disparate *treatment*, the legally harder trade-off.
Out-of-fold (train <= 2024, test 2025+), the research model (model_food.HEADLINE)."""
import pandas as pd, numpy as np, json, os
from sklearn.metrics import roc_auc_score
import model_food as mf


def at(score, yv, q):
    """Precision and recall of the top q (ties at the cut split pro rata)."""
    w = mf.top_weights(score, q)
    return (w*yv).sum()/w.sum(), (w*yv).sum()/yv.sum()


def main():
    df = mf.add_features(mf.load())
    d = mf.routine_rows(df)
    d["zip5"] = d["zip"].astype(str).str.extract(r"(\d{5})")[0]
    te = (d["completed_date"] > pd.Timestamp(mf.TRAIN_END)).to_numpy()
    p = mf.fit_predict(d, mf.HEADLINE, mf.train_mask(d, mf.HEADLINE), te)
    yt = d.loc[te, "major"].values.astype(int); base = yt.mean()
    pers = d.loc[te, "persistence"].values; rule = d.loc[te, mf.BASELINES[mf.RULE]].values

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
    inc = json.load(open("acs_cache.json")).get("inc", {}) if os.path.exists("acs_cache.json") else {}
    t = pd.DataFrame({"p": p, "y": yt, "zip5": d.loc[te, "zip5"].values, "pw": mf.top_weights(pers),
                      "rw": mf.top_weights(rule), "flag": mf.top_weights(p)})
    t["income"] = t["zip5"].map(inc)
    t = t.dropna(subset=["income"])
    t["grp"] = pd.qcut(t["income"], 4, labels=["Q1 low", "Q2", "Q3", "Q4 high"])
    crit_all = t[t["y"] == 1]
    TARGET = round(float(crit_all.groupby("grp", observed=True)["flag"].mean().max()), 2)   # best group's recall
    print(f"\n=== B) recall by income group: ONE global cut (top 20%) vs PER-GROUP equal-opportunity ===")
    print(f"(equal-opp targets recall={TARGET:.0%} in every group, the best group's recall under the global cut)")
    print(f"{'group':8} {'global flag%':>12} {'global recall':>14}   |{'eq-opp flag%':>13} {'eq-opp recall':>14}"
          f"   | rule flag% recall%  | persistence flag% recall%")
    tot_g = []; tot_e = []; groups = {}
    for grp, gp in t.groupby("grp", observed=True):
        crit = gp[gp["y"] == 1]
        g_flag = gp["flag"].mean(); g_rec = crit["flag"].mean()
        ethr = np.quantile(crit["p"], 1-TARGET)            # per-group cut hitting TARGET recall
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
    mf.save_results("threshold", {"global": glob, "target_recall": TARGET, "by_income": groups,
                                  "eq_total_flag": round(sum(tot_e)/len(t)*100, 1)})


if __name__ == "__main__":
    main()
