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
    assert "health closure" in f.loc[1, "why"] and "typical A" not in f.loc[1, "why"]
    # and the research rule agrees with the worklist
    nxt = rows + [_row(b, "2026-10-05", "Routine", 95, 0) for b in (1, 2, 3)]
    d = mf.routine_rows(mf.add_features(_load(nxt, tmp_path)))
    last = d[d["completed_date"] == "2026-10-05"].set_index("business_id")
    assert last["rule_mean_all"].idxmax() == 1
