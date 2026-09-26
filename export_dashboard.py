"""Export the de-identified dashboard (dashboard.html). Two things, kept apart:
  (1) STATS/EVIDENCE come from the forward test (train <= 2024, test 2025+), read from
      data/research_results.json, which model_food.py, sim_schedule.py and fairness_check.py write.
      Nothing on the page is typed in by hand.
  (2) THIS MONTH'S LIST IN AGGREGATE: for the month after the data ends, how many active
      facilities of each type are estimated due, how many have a major on record, and how the
      research model's risk is distributed. The list itself, facility by facility in the one-line
      rule's order, is export_worklist.py's and reaches City staff only through the key-protected
      staff API (docs/API.md).
The page used to embed one row per active facility (type, risk to 0.1, banded history, months
since the last visit). Those rows were not de-identified: 80% were unique on the fields shown, and
SD Food Info publishes every facility's name and inspection dates, so a row links to a named
business. Everything published now passes privacy_gate.check (aggregates only, counts under 11
suppressed), and tests/test_dashboard_privacy.py runs the gate on the committed dashboard.html."""
import pandas as pd, numpy as np, json, base64, os, sys
from datetime import date
import privacy_gate as pg

RISK_BINS = [0, 5, 10, 15, 20, 30, 40, 100]          # model risk, percent


def suppress_columns(rows, keys):
    """Primary suppression (counts 1 to MIN_CELL-1 become None), then complementary: the column
    totals are published, so a column with exactly one hidden cell would give it away by
    subtraction; the smallest other non-zero cell in that column is hidden too. Returns the keys
    whose single hidden cell had no partner (their total must then be withheld)."""
    exposed = []
    for k in keys:
        vals = [int(r[k]) for r in rows]
        hide = [0 < v < pg.MIN_CELL for v in vals]
        if sum(hide) == 1:
            others = [i for i, v in enumerate(vals) if not hide[i] and v > 0]
            if others:
                hide[min(others, key=lambda i: vals[i])] = True
            else:
                exposed.append(k)
        for r, v, h in zip(rows, vals, hide):
            r[k] = None if h else v
    return exposed


def aggregate(f):
    """This month's list as published: counts only, never a row per facility.

    ``f`` has one row per active facility with ``business_type``, ``due_this_month`` (bool),
    ``prior_major_rate`` (NaN with no routine on record) and ``model_risk`` (0-1). Types with fewer
    than MIN_CELL facilities are pooled into "Other types"; any count from 1 to MIN_CELL-1 is
    published as null ("<11")."""
    f = f.assign(_type=f["business_type"].astype(str),
                 _major=f["prior_major_rate"].fillna(0) > 0,
                 _due=f["due_this_month"].astype(bool))
    sizes = f["_type"].value_counts()
    small = sizes[sizes < pg.MIN_CELL].index
    f["_type"] = f["_type"].where(~f["_type"].isin(small), "Other types")
    by_type = []
    for t, g in f.groupby("_type"):
        by_type.append({"type": t, "facilities": int(len(g)), "due": int(g["_due"].sum()),
                        "with_prior_major": int(g["_major"].sum())})
    by_type.sort(key=lambda r: (r["type"] == "Other types", -r["facilities"], r["type"]))
    pct = f["model_risk"].astype(float) * 100
    risk_bins = []
    for lo, hi in zip(RISK_BINS[:-1], RISK_BINS[1:]):
        m = (pct >= lo) & ((pct < hi) if hi < 100 else (pct <= hi))
        risk_bins.append({"from": lo, "to": hi, "facilities": int(m.sum()), "due": int((m & f["_due"]).sum())})
    # with_prior_major has no published total, so primary suppression is enough for it
    exposed = suppress_columns(by_type, ["facilities", "due"]) + suppress_columns(risk_bins, ["facilities", "due"])
    suppress_columns(by_type, ["with_prior_major"])
    total = {"facilities": int(len(f)), "due": int(f["_due"].sum())}
    for k in set(exposed):                   # a lone hidden cell with no partner: withhold the total instead
        total[k] = None
    return {**total, "by_type": by_type, "risk_bins": risk_bins}


def render(payload, template="dashboard.template.html", out="dashboard.html"):
    """Inject the (gated) payload and the committed charts into the template."""
    pg.check(payload)
    tpl = open(template, encoding="utf-8").read()
    pre, mark, post = tpl.partition("/*__DATA__*/")     # default literal runs from here to the first ';'
    _, _, rest = post.partition(";")
    data_js = json.dumps(payload).replace("</", "<\\/")  # ascii-safe; "</script>" in a value cannot end the block
    assert ";" not in data_js, "a ';' in the data would end the injected literal early"
    html = pre + mark + " " + data_js + ";" + rest

    def datauri(fn):
        return "data:image/png;base64," + base64.b64encode(open(fn, "rb").read()).decode()
    for ph, fn in [("IMG_GAINS", "food_gains.png"), ("IMG_DAYS", "food_days_earlier.png"), ("IMG_FAIRNESS", "food_fairness.png")]:
        html = html.replace(ph, datauri(fn))
    assert pg.dashboard_payload(html) == json.loads(data_js)
    open(out, "w", encoding="utf-8", newline="\n").write(html)   # LF, as committed
    return out


def main():
    import model_food as mf
    import export_worklist as ew
    import export_site as es
    R = json.load(open(mf.RESULTS)) if os.path.exists(mf.RESULTS) else {}
    missing = [k for k in ("model", "sim", "fairness") if k not in R]
    if missing:
        sys.exit(f"{mf.RESULTS} lacks {missing}: run model_food.py, sim_schedule.py and fairness_check.py first")
    insp = mf.load()
    info = ew.facility_info(json.load(open(mf.RAW)))
    data_to = insp["completed_date"].max()
    month = (data_to + pd.offsets.MonthBegin(1)).strftime("%Y-%m")
    start, _ = ew.month_bounds(month)
    f = ew.worklist(insp, info, month, es.district_lookup(es.load_districts()), why=False, city_only=False)
    f = ew.model_orders(insp, month, f)
    h = insp[insp["completed_date"] < start].groupby("business_id")
    f["prior_major_rate"] = h["major"].mean().reindex(f.index)
    summary = aggregate(f)

    # ---- evidence numbers, all from the research runs ----
    M, S, F = R["model"], R["sim"], R["fairness"]
    # scored as deployed (features as of the 1st), like the days-sooner figures from sim_schedule.py
    rk = (M.get("as_deployed") or {}).get("rankings") or M["rankings"]; P = mf.PERSIST; RL = mf.RULE
    area = S["windows"]["month_area"]; A = area["arms"]; MM = area["model_minus"]
    roll = [r["auc"] for r in S["rolling"]]; roll_r = [r["auc_rule"] for r in S["rolling"]]
    pct = lambda v: f"{v*100:.0f}%"
    rng2 = lambda v: f"{min(v):.2f}–{max(v):.2f}"
    ci2 = lambda c: f"{c[0]:.1f}–{c[1]:.1f}"
    # days sooner as a share of the gap between routine inspections (277 d after a major, 303 after none)
    gap = (M["premise"]["gap_after_major"], M["premise"]["gap_after_clean"])
    share = lambda days, nd=1: f"{days/gap[1]*100:.{nd}f}–{days/gap[0]*100:.{nd}f}%"
    CI = F["ci_income"]
    rgap = lambda k, lo, hi: (f"{F[lo] - F[hi]:+.1f} pts (95% CI {CI[k]['recall_gap_low_minus_high_pts'][0]:+.1f} to "
                              f"{CI[k]['recall_gap_low_minus_high_pts'][1]:+.1f})")
    zab = M["ablation"]["with ZIP"]
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
        "gap": f"{gap[0]}–{gap[1]}", "days_share": share(A["Model"]["days_earlier"]),
        "days_rule_share": share(A[RL]["days_earlier"]), "days_over_rule_share": share(MM[RL]["days"], 2),
        "recall_gap": rgap("model", "recall_low", "recall_high"),
        "recall_gap_rule": rgap("rule", "rule_recall_low", "rule_recall_high"),
        "zip_auc": f"{zab['auc']:+.3f}, 95% CI {zab['auc_ci'][0]:+.3f} to {zab['auc_ci'][1]:+.3f}",
        "flag_ratio": f"{F['flag_ratio']:.2f}×", "rule_flag_ratio": f"{F['rule_flag_ratio']:.2f}×",
        "actual_ratio": f"{F['actual_ratio']:.2f}×",
        "recall_model": rec("recall_of_crit_%"), "recall_rule": rec("rule_recall_%"), "recall_zip": rec("zip_recall_%"),
        "cal_max": f"{max(cal):+.1f}", "cal_min": f"{min(cal):+.1f}",
        "n_due": f"{int(f['due_this_month'].sum()):,}", "month": pd.Timestamp(start).strftime("%B %Y"),
    }
    payload = {"generated": date.today().isoformat(), "as_of": str(data_to.date()), "stats": stats,
               "summary": summary}
    json.dump(payload, open("dashboard_data.json", "w"))
    render(payload)

    print("stats:", {k: v for k, v in stats.items() if k != "t"}); print("text:", stats["t"])
    print(f"this month's list, in aggregate: {summary['facilities']:,} active facilities, {summary['due']:,} "
          f"estimated due in {month}; {len(summary['by_type'])} type rows; data through {data_to.date()}")
    print("wrote dashboard.html")


if __name__ == "__main__":
    main()
