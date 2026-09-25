"""Export the de-identified dashboard (dashboard.html). Two things, kept apart:
  (1) STATS/EVIDENCE come from the forward test (train <= 2024, test 2025+), read from
      data/research_results.json, which model_food.py, sim_schedule.py and fairness_check.py write.
      Nothing on the page is typed in by hand.
  (2) The WORKLIST is forward-looking, for the month after the data ends: every active facility in
      the County, in the one-line rule's order (lowest mean routine score on record first; ties to
      the earlier due date), with the same due-this-month estimate as export_worklist.py and the
      research model's risk (fitted on every routine inspection) beside it. The page used to rank
      by risk times an "overdue" ratio; sim_schedule.py backtested that weighting and it found
      majors later than either the plain model or the rule, so it is gone.
Rows are DE-IDENTIFIED (type and banded history only; no name, address, city or exact score) so the
public page can't be used to point at a specific business. Named lists are export_worklist.py's,
for internal use."""
import pandas as pd, numpy as np, json, base64, os, sys
from datetime import date
import model_food as mf
import export_worklist as ew

R = json.load(open(mf.RESULTS)) if os.path.exists(mf.RESULTS) else {}
missing = [k for k in ("model", "sim", "fairness") if k not in R]
if missing:
    sys.exit(f"{mf.RESULTS} lacks {missing}: run model_food.py, sim_schedule.py and fairness_check.py first")


def band_prior(n):                         # de-identify: bands, not exact counts
    return "1" if n <= 1 else "2–4" if n <= 4 else "5–9" if n <= 9 else "10+"


def band_major(pct):
    return None if pct is None else "none" if pct == 0 else "low" if pct < 15 else "elevated" if pct < 35 else "high"


def main():
    import export_site as es
    insp = mf.load()
    info = ew.facility_info(json.load(open(mf.RAW)))
    data_to = insp["completed_date"].max()
    month = (data_to + pd.offsets.MonthBegin(1)).strftime("%Y-%m")
    start, _ = ew.month_bounds(month)
    f = ew.worklist(insp, info, month, es.district_lookup(es.load_districts()), why=False, city_only=False)
    f = ew.model_orders(insp, month, f)
    h = insp[insp["completed_date"] < start].groupby("business_id")
    f["prior_n"] = h.size().reindex(f.index)
    f["prior_major_rate"] = h["major"].mean().reindex(f.index)
    f["days_since"] = (start - f["last_visit"]).dt.days
    f = f.sort_values(["rule_points", "due_estimate", "facility_id"], ascending=[False, True, True])

    rows = []
    for i, (_, r) in enumerate(f.iterrows(), 1):
        pm = None if pd.isna(r["prior_major_rate"]) else round(r["prior_major_rate"]*100)
        rows.append({"id": f"F-{i:05d}", "risk": round(float(r["model_risk"])*100, 1), "type": str(r["business_type"]),
                     "prior_band": band_prior(int(r["prior_n"])), "major_band": band_major(pm),
                     "due": bool(r["due_this_month"]), "months_since": round(r["days_since"]/30.4, 1)})

    # ---- evidence numbers, all from the research runs ----
    M, S, F = R["model"], R["sim"], R["fairness"]
    rk = M["rankings"]; P = mf.PERSIST; RL = mf.RULE
    area = S["windows"]["month_area"]; A = area["arms"]; MM = area["model_minus"]
    roll = [r["auc"] for r in S["rolling"]]; roll_r = [r["auc_rule"] for r in S["rolling"]]
    pct = lambda v: f"{v*100:.0f}%"
    rng2 = lambda v: f"{min(v):.2f}–{max(v):.2f}"
    ci2 = lambda c: f"{c[0]:.1f}–{c[1]:.1f}"
    d = insp[insp["insp_type"].astype(str) == "Routine"]
    routine_2025 = int((d["completed_date"].dt.year == 2025).sum())
    major_2025 = int(((d["completed_date"].dt.year == 2025) & (d["major"] == 1)).sum())
    cal = [r["mean_risk_%"] - r["actual_major_%"] for r in F["income"]]
    rec = lambda key: " / ".join(f"{r[key]:.0f}%" for r in F["income"])
    stats = {"n_inspections": int(len(insp)), "n_facilities": int(insp["business_id"].nunique()),
             "routine_per_yr": routine_2025, "major_per_yr": major_2025, "active_facilities": int(len(f)),
             "n_due": int(f["due_this_month"].sum()), "month": month,
             "top20_rule": round(rk[RL]["top20_recall"]*100), "days_rule": round(A[RL]["days_earlier"], 1)}
    stats["t"] = {   # preformatted phrases the template drops into its text (data-s="key")
        "test_n": f"{M['test_n']:,}", "train_span": "Jan 2023 – Dec 2024",
        "test_span": f"Jan 2025 – {pd.Timestamp(M['data_to']):%b %Y}",
        "top20": pct(rk["Model"]["top20_recall"]), "top20_rule": pct(rk[RL]["top20_recall"]),
        "top20_persistence": pct(rk[P]["top20_recall"]),
        "lift": f"{rk['Model']['lift']:.1f}×", "lift_rule": f"{rk[RL]['lift']:.1f}×",
        "prec_rule": pct(rk[RL]["top20_precision"]), "base_rate": pct(M["test_major_rate"]),
        "auc": f"{rk['Model']['auc']:.2f}", "auc_rule": f"{rk[RL]['auc']:.2f}", "auc_persistence": f"{rk[P]['auc']:.2f}",
        "auc_rolling": rng2(roll), "auc_rolling_rule": rng2(roll_r),
        "days": f"{A['Model']['days_earlier']:.1f}", "days_ci": ci2(A["Model"]["ci"]),
        "days_rule": f"{A[RL]['days_earlier']:.1f}", "days_rule_ci": ci2(A[RL]["ci"]),
        "days_persistence": f"{A['Persistence']['days_earlier']:.1f}",
        "days_over_rule": f"{MM[RL]['days']:.1f}", "days_over_rule_ci": ci2(MM[RL]["ci"]),
        "days_overdue": f"{A['Model x overdue (old dashboard)']['days_earlier']:.1f}",
        "clean_wait": f"{abs(A[RL]['clean_days']):.1f}",
        "flag_ratio": f"{F['flag_ratio']:.2f}×", "rule_flag_ratio": f"{F['rule_flag_ratio']:.2f}×",
        "actual_ratio": f"{F['actual_ratio']:.2f}×",
        "recall_model": rec("recall_of_crit_%"), "recall_rule": rec("rule_recall_%"), "recall_zip": rec("zip_recall_%"),
        "cal_max": f"{max(cal):+.1f}", "cal_min": f"{min(cal):+.1f}",
        "n_due": f"{int(f['due_this_month'].sum()):,}", "month": pd.Timestamp(start).strftime("%B %Y"),
    }
    types = sorted(f["business_type"].astype(str).unique().tolist())
    payload = {"generated": date.today().isoformat(), "as_of": str(data_to.date()), "stats": stats,
               "worklist": rows, "types": types}
    json.dump(payload, open("dashboard_data.json", "w"))

    # ---- build self-contained dashboard.html: inject data at /*__DATA__*/ and embed the PNGs ----
    tpl = open("dashboard.template.html", encoding="utf-8").read()
    pre, mark, post = tpl.partition("/*__DATA__*/")     # default literal runs from here to the first ';'
    _, _, rest = post.partition(";")
    data_js = json.dumps(payload)                       # ascii-safe; no ';' in any value
    assert ";" not in data_js, "a ';' in the data would end the injected literal early"
    html = pre + mark + " " + data_js + ";" + rest

    def datauri(fn):
        return "data:image/png;base64," + base64.b64encode(open(fn, "rb").read()).decode()
    for ph, fn in [("IMG_GAINS", "food_gains.png"), ("IMG_DAYS", "food_days_earlier.png"), ("IMG_FAIRNESS", "food_fairness.png")]:
        html = html.replace(ph, datauri(fn))
    open("dashboard.html", "w", encoding="utf-8", newline="\n").write(html)   # LF, as committed

    print("stats:", {k: v for k, v in stats.items() if k != "t"}); print("text:", stats["t"])
    print(f"worklist rows: {len(rows):,} active facilities, {stats['n_due']:,} estimated due in {month}; "
          f"{len(types)} types; data through {data_to.date()}")
    print("wrote dashboard.html")


if __name__ == "__main__":
    main()
