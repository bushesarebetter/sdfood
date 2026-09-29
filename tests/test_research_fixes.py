"""Research-code fixes from the review of model_food.py / export_worklist.py, on toy records."""
import numpy as np
import pandas as pd

import export_site as es
import export_worklist as ew
import model_food as mf


def _row(b, day, typ, score, nmaj, status="Complete", closure=None):
    return dict(business_id=b, business_type="Restaurant Food Facility", zip="92101", lat=32.7, lng=-117.1,
                opened_date="2015-01-01", inspection_id=f"{b}-{day}-{typ}", insp_type=typ, status=status, score=score,
                grade="A", completed_date=day, n_violations=nmaj, n_major=nmaj, n_minor=0, n_grp=0, closure=closure)


def _load(rows, tmp_path):
    p = tmp_path / "insp.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    return mf.load(str(p))


def test_persistence_reads_the_last_score_over_two_years_like_the_card(tmp_path):
    rows = [_row(1, "2024-06-01", "Routine", 75, 0), _row(1, "2025-01-10", "Complaint", None, 0),
            _row(1, "2025-07-01", "Routine", 95, 0)]
    f = mf.add_features(_load(rows, tmp_path))
    place = {"kind": "restaurant", "dates": ["2024-06-01", "2025-01-10"],
             "visits": [{"date": "2024-06-01", "type": "routine", "score": 75, "major": 0, "minor": 5, "grp": 0, "closure": None, "_items": []},
                        {"date": "2025-01-10", "type": "complaint", "score": None, "major": 0, "minor": 0, "grp": 0, "closure": None, "_items": []}]}
    x = es.features_at(place, "2025-07-01")
    X = np.zeros((1, len(es.NUMERIC)))
    for k in ("routines_major", "majors", "last_score"):
        X[0, es.NUMERIC.index(k)] = x[k]
    assert f["persistence"].iloc[2] == es.persistence(X)[0]      # 13 months old: the 75 still counts


def test_a_health_closure_at_routine_is_not_a_typical_A(tmp_path):
    rows = [_row(1, "2025-12-01", "Routine", None, 4, "Ordered Closed", "health"),
            _row(1, "2025-12-02", "Follow-up", None, 0, "Approved to Reopen"),
            _row(2, "2025-12-01", "Routine", 96, 0), _row(3, "2025-12-01", "Routine", 91, 1)]
    insp = _load(rows, tmp_path)
    assert insp.loc[insp["business_id"] == 1, "rated_score"].dropna().tolist() == [float(es.CLOSURE_SCORE)]
    assert insp.loc[insp["business_id"] == 1, "score"].isna().all(), "model features keep real scores only"
    info = pd.DataFrame([{"business_id": b, "facility_id": f"FA{b}", "name": f"P{b}", "address": "x", "status": "Issued"}
                         for b in (1, 2, 3)]).set_index("business_id")
    f = ew.worklist(insp, info, "2026-10", lambda lo, la: 1)
    assert f.loc[1, "rule_order_all"] == 1, "the place closed by a health order comes first"
    assert f.loc[1, "mean_points"] == 100 - es.CLOSURE_SCORE
    assert "closed; the County gave no score, this rule counts it as 70" in f.loc[1, "why"] and "typical A" not in f.loc[1, "why"]
    # and the research rule agrees with the worklist
    nxt = rows + [_row(b, "2026-10-05", "Routine", 95, 0) for b in (1, 2, 3)]
    d = mf.routine_rows(mf.add_features(_load(nxt, tmp_path)))
    last = d[d["completed_date"] == "2026-10-05"].set_index("business_id")
    assert last["rule_mean_all"].idxmax() == 1


def test_interval_medians_count_intervals_still_open(tmp_path):
    """True routine interval: median 290 days. Early in a record that starts 2023-01, a plain
    median of finished gaps runs short; Kaplan-Meier with the open intervals does not."""
    rng = np.random.default_rng(0)
    rows = []
    for b in range(1, 1501):
        t = pd.Timestamp("2023-01-03") + pd.Timedelta(days=int(rng.integers(0, 290)))
        while t < pd.Timestamp("2024-06-30"):
            rows.append(_row(b, t.strftime("%Y-%m-%d"), "Routine", 95, 0))
            t += pd.Timedelta(days=float(290 * np.exp(rng.normal(0, 0.35))))
    insp = _load(rows, tmp_path)
    rt = insp[insp["insp_type"] == "Routine"]
    asof = pd.Timestamp("2024-01-01")
    rt = rt[rt["completed_date"] < asof]
    naive_by, naive = ew.intervals(rt)
    km_by, km = ew.intervals(rt, asof=asof, last_visit=rt.groupby("business_id")["completed_date"].max())
    assert naive < 260, naive                      # biased short
    assert abs(km - 290) < 20, km                   # close to the truth
    assert ew.km_median([10, 20, 30], [True, True, True]) == 20.0
    assert ew.km_median([10, 50, 50, 50], [True, False, False, False]) is None   # never reaches 0.5


def test_month_start_rows_see_nothing_inside_the_month(tmp_path):
    """A complaint visit with majors on 2025-03-03, then the routine on 2025-03-20: evaluated at the
    inspection date the complaint is history; as of 2025-03-01 (the deployed list) it is not."""
    rows = [_row(1, "2024-05-02", "Routine", 94, 0), _row(1, "2025-03-03", "Complaint", None, 2),
            _row(1, "2025-03-20", "Routine", 90, 1), _row(2, "2025-03-10", "Routine", 96, 0)]
    df = mf.add_features(_load(rows, tmp_path))
    d = mf.routine_rows(df)
    at = d[d["completed_date"] == "2025-03-20"].iloc[0]
    assert at["days_since_last"] == 17 and at["last_major"] == 1 and at["prior_n"] == 2
    ms = mf.month_start_rows(df, d)
    m = ms.loc[at.name]
    assert m["days_since_last"] == (pd.Timestamp("2025-03-01") - pd.Timestamp("2024-05-02")).days
    assert m["last_major"] == 0 and m["prior_n"] == 1 and m["month"] == 3
    assert ms.loc[d["business_id"] == 2, "prior_n"].tolist() == [0]      # a first visit still gets a row
    assert list(ms.index) == list(d.index) and (ms["major"] == d["major"]).all()
    # the deployed scorer (features_asof) and month_start_rows agree for the same facility and date
    fx = mf.features_asof(df[df["completed_date"] < "2025-03-01"], "2025-03-01", ids=[1])
    for c in mf.HIST + ["persistence", "rule_mean_all"]:
        a, b = fx.loc[1, c], m[c]
        assert (pd.isna(a) and pd.isna(b)) or a == b, c


def test_feedback_censoring_removes_the_visit_and_the_followups_it_would_have_triggered(tmp_path):
    import feedback_check as fb
    rows = [_row(1, "2024-01-10", "Routine", 88, 1), _row(1, "2024-01-25", "Re-inspection", None, 0),
            _row(1, "2024-06-01", "Complaint", None, 0), _row(1, "2024-09-01", "Routine", 96, 0)]
    raw = _load(rows, tmp_path)
    first = raw.index[(raw["completed_date"] == "2024-01-10")]
    kept = fb.censor(raw, first)
    assert kept["completed_date"].dt.strftime("%Y-%m-%d").tolist() == ["2024-06-01", "2024-09-01"]
    # and the later routine's history is rebuilt from what is left: no score on record any more
    d = mf.routine_rows(mf.add_features(kept))
    assert pd.isna(d.iloc[0]["prior_mean_score"]) and d.iloc[0]["prior_n"] == 1


def test_feedback_censor_keeps_complaint_investigations(tmp_path):
    import feedback_check as fb
    rows = [_row(1, "2024-01-10", "Routine", 88, 1), _row(1, "2024-01-20", "Site Investigation", None, 0),
            _row(1, "2024-01-25", "Re-inspection", None, 0), _row(1, "2024-02-01", "Follow-up", None, 0)]
    raw = _load(rows, tmp_path)
    kept = fb.censor(raw, raw.index[raw["completed_date"] == "2024-01-10"])
    assert kept["insp_type"].tolist() == ["Site Investigation"]


def test_rules_fall_back_to_score_without_a_rated_column(tmp_path):
    rows = [_row(1, "2024-01-10", "Routine", 80, 1), _row(2, "2024-01-10", "Routine", 96, 0)]
    df = _load(rows, tmp_path)
    a = mf.features_asof(df, "2024-06-01")["rule_mean_all"]
    b = mf.features_asof(df.drop(columns="rated_score"), "2024-06-01")["rule_mean_all"]
    assert list(a) == list(b) == [-80.0, -96.0]


def test_km_median_is_exact_at_one_half_and_small_fits_stop_early(tmp_path):
    assert ew.km_median(np.arange(1, 31), np.ones(30, bool)) == 15.0
    rng = np.random.default_rng(0)
    rows = [_row(b, f"2024-{m:02d}-15", "Routine", 90, int(rng.random() < 0.2)) for b in range(60) for m in range(1, 7)]
    d = mf.routine_rows(mf.add_features(_load(rows, tmp_path)))
    m = mf.Model(mf.HEADLINE).fit(d)                     # 360 rows: too few for a time split
    assert m.n_iter < mf.MAX_ITER, "sklearn's early stopping, not a fixed 300 rounds"


def test_facility_interval_resamples_whole_facilities():
    codes = np.repeat(np.arange(40), 5)                  # 40 facilities, 5 rows each
    x = np.repeat(np.linspace(0, 1, 40), 5)              # constant within a facility
    lo, hi = mf.facility_interval(codes, lambda w: (w * x).sum() / w.sum(), boot=400)
    assert lo < x.mean() < hi and hi - lo < 0.4
    assert mf.facility_interval(codes, lambda w: 3.0, boot=50) == [3.0, 3.0]


def test_calibration_table_orders_groups_and_reports_the_gap():
    rng = np.random.default_rng(1)
    g = np.array(["b"] * 500 + ["a"] * 500)
    p = np.r_[np.full(500, 0.10), np.full(500, 0.30)]
    y = (rng.random(1000) < np.r_[np.full(500, 0.20), np.full(500, 0.30)]).astype(int)
    codes = np.arange(1000)
    t = mf.calibration_table(p, y, g, codes, order=["b", "a"], boot=200)
    assert list(t) == ["b", "a"] and t["b"]["predicted_pct"] == 10.0
    assert t["b"]["actual_minus_predicted_pts"] == round(100 * (y[:500].mean() - 0.10), 1)
    lo, hi = t["b"]["ci_pts"]
    assert lo > 0 and lo <= t["b"]["actual_minus_predicted_pts"] <= hi       # under-predicted, detectably
    assert t["a"]["ci_pts"][0] < 0 < t["a"]["ci_pts"][1]                     # calibrated: covers 0
    assert list(mf.calibration_table(p, y, g, codes, boot=10)) == ["a", "b"]  # no order given: sorted


def test_equal_opportunity_cuts_hit_the_target_recall_in_every_group():
    import threshold_tradeoff as tt
    rng = np.random.default_rng(2)
    grp = np.repeat(["low", "high"], 2000)
    y = (rng.random(4000) < 0.2).astype(int)
    p = rng.random(4000) + 0.5 * y + np.where(grp == "high", 0.3, 0.0)   # different score scales per group
    cuts = tt.equal_opportunity_cuts(p, y, grp, 0.5)
    for g in ("low", "high"):
        m = (grp == g) & (y == 1)
        assert abs((p[m] >= cuts[g]).mean() - 0.5) < 0.01
    assert cuts["high"] > cuts["low"]


def test_feedback_paired_interval_is_zero_for_identical_arms_and_sees_a_real_loss():
    import feedback_check as fb
    rng = np.random.default_rng(3)
    y = (rng.random(3000) < 0.2).astype(int)
    codes = np.arange(3000) // 3
    good = rng.random(3000) + y
    assert fb.paired_auc_interval(y, codes, good, [good.copy()], boot=100) == [0.0, 0.0]
    worse = good + rng.normal(0, 1.5, 3000)
    lo, hi = fb.paired_auc_interval(y, codes, good, [worse], boot=200)
    assert hi < 0                                         # the noisier arm is detectably worse


def test_within_window_auc_compares_majors_and_clean_inspections_inside_each_window_only():
    import sim_schedule as ss
    rng = np.random.default_rng(4)
    win = np.repeat(np.arange(60), 20)
    y = (rng.random(1200) < 0.2).astype(int)
    assert ss.within_window_auc(y + 0.0, [win], y, boot=50)[0] == 1.0          # majors always first
    assert ss.within_window_auc(-y + 0.0, [win], y, boot=50)[0] == 0.0
    a, (lo, hi), n = ss.within_window_auc(rng.random(1200), [win], y, boot=300)
    assert lo < 0.5 < hi and abs(a - 0.5) < 0.05                               # a random order: no ranking
    # a window-level shift (every inspection in a high-major window scored higher) is not a ranking within it
    shifted = win.astype(float) + rng.random(1200) * 0.01
    y2 = (win % 2 == 0).astype(int) * (rng.random(1200) < 0.5)
    a2, _, n2 = ss.within_window_auc(shifted, [win], y2, boot=50)
    assert abs(a2 - 0.5) < 0.1 and n2 == 30                                    # windows with no major are skipped


def test_within_window_spearman_sees_an_order_that_follows_x_and_none_that_does_not():
    import sim_schedule as ss
    rng = np.random.default_rng(5)
    win = np.repeat(np.arange(40), 25)
    x = rng.random(1000)
    day = np.empty(1000)
    for w in range(40):                                   # each window worked in descending x: x first
        ix = np.flatnonzero(win == w)
        day[ix[np.argsort(-x[ix])]] = np.arange(1, 26)
    r, (lo, hi), n = ss.within_window_spearman(x, [win], day, boot=200)
    assert r > 0.99 and n == 40
    r0, (lo0, hi0), _ = ss.within_window_spearman(rng.random(1000), [win], day, boot=300)
    assert lo0 < 0 < hi0                                   # an unrelated x: no ordering


def test_every_routine_health_closure_reads_as_70_even_with_a_same_day_score(tmp_path):
    """The CSV's closure_order marks every visit that ended in a closure order (closure marks only an
    episode's first): the research rules read each routine health closure as 70, like the card."""
    rows = [dict(_row(1, "2025-11-06", "Routine", 94, 1, "Ordered Closed", "health"), closure_order="health"),
            dict(_row(2, "2025-11-06", "Routine", 94, 0), closure_order=None)]
    insp = _load(rows, tmp_path)
    assert insp.loc[insp["business_id"] == 1, "rated_score"].tolist() == [float(es.CLOSURE_SCORE)]
    assert insp.loc[insp["business_id"] == 1, "score"].tolist() == [94], "the County's own score is kept"
    assert insp.loc[insp["business_id"] == 2, "rated_score"].tolist() == [94.0]
