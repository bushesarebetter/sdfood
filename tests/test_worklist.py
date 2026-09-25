"""export_worklist.py on a small synthetic inspection table: who is due, the rule's order, the
files the API reads, and the frozen copy a pilot is scored against."""
import csv
import json
import os
import stat

import pandas as pd
import pytest

import export_worklist as ew
import model_food as mf

MONTH = "2026-10"          # starts 2026-10-01; every routine gap below is 180 days, so a facility
                           # is due when its last routine is on or before 2026-10-31 - 150 days
COLS = ["business_id", "business_type", "zip", "lat", "lng", "opened_date", "inspection_id", "insp_type",
        "status", "score", "grade", "completed_date", "n_violations", "n_major", "n_minor", "n_grp", "closure"]

# business_id: (district marker as lat, [(date, type, score, majors)], permit status)
FACILITIES = {
    1: (1, [("2025-06-05", "Routine", 92, 0), ("2025-12-02", "Routine", 90, 1),
            ("2025-12-20", "Re-inspection", None, 0)], "Permit Renewed"),                   # due, 9.0 pts
    2: (1, [("2025-09-01", "Routine", 80, 0), ("2026-02-28", "Routine", 84, 0)], "Permit Renewed"),  # due, 18.0
    3: (1, [("2025-12-01", "Routine", 96, 0), ("2026-05-30", "Routine", 98, 0)], "Issued"),  # due (154 d), 3.0
    4: (1, [("2026-01-05", "Routine", 95, 0), ("2026-07-04", "Routine", 93, 0),
            ("2026-10-05", "Routine", 50, 3)], "Permit Renewed"),                           # not due; Oct row is the future
    5: (2, [("2025-03-01", "Routine", 88, 0), ("2025-08-28", "Routine", 90, 0)], "Permit Renewed"),  # due, 11.0
    9: (2, [("2025-05-01", "Routine", 89, 0), ("2025-10-28", "Routine", 89, 0)], "Permit Renewed"),  # due, 11.0, later
    6: (0, [("2025-09-01", "Routine", 80, 0), ("2026-02-28", "Routine", 84, 0)], "Permit Renewed"),  # outside the City
    7: (2, [("2025-09-01", "Routine", 80, 0), ("2026-02-28", "Routine", 84, 0)], "Expired"),         # permit expired
    8: (2, [("2024-01-10", "Routine", 85, 0), ("2024-07-08", "Routine", 85, 0)], "Permit Renewed"),  # not active
}


def lookup(lon, lat):
    return {1: 1, 2: 2}.get(int(lat)) if lat is not None else None


@pytest.fixture
def data(tmp_path):
    rows, n = [], 0
    for b, (lat, visits, _) in FACILITIES.items():
        for day, typ, score, majors in visits:
            n += 1
            rows.append({"business_id": b, "business_type": "Restaurant Food Facility", "zip": "92101",
                         "lat": lat, "lng": -117.0, "opened_date": "2020-01-01", "inspection_id": n,
                         "insp_type": typ, "status": "Complete", "score": score, "grade": "A",
                         "completed_date": day, "n_violations": majors, "n_major": majors, "n_minor": 0,
                         "n_grp": 0, "closure": None})
    path = tmp_path / "inspections.csv"
    pd.DataFrame(rows, columns=COLS).to_csv(path, index=False)
    info = pd.DataFrame([{"business_id": b, "facility_id": f"FA{b:04d}", "name": f"Sample Place {b}",
                          "address": f"{b} Test St", "status": st} for b, (_, _, st) in FACILITIES.items()]
                        ).set_index("business_id")
    return mf.load(str(path)), info


def test_due_estimate_and_the_one_line_rule(data):
    """Without the card export, every district is in the one-line rule's order."""
    insp, info = data
    f = ew.worklist(insp, info, MONTH, lookup)
    assert set(f.index) == {1, 2, 3, 4, 5, 9}                       # 6 outside, 7 expired, 8 inactive
    due = f[f["due_this_month"]]
    assert set(due.index) == {1, 2, 3, 5, 9}
    assert f.loc[1, "due_estimate"] == pd.Timestamp("2026-05-31")     # last routine + the 180-day median
    d1 = due[due["district"] == 1].sort_values("rule_order")
    assert list(d1.index) == [2, 1, 3] and list(d1["rule_order"]) == [1, 2, 3]
    assert list(d1["rule_points"]) == [18.0, 9.0, 3.0]
    d2 = due[due["district"] == 2].sort_values("rule_order")
    assert list(d2.index) == [5, 9]                                   # a tie at 11.0: the earlier due date first
    assert f.loc[4, "last_routine_score"] == 93                       # the October row is not read
    assert f.loc[1, "why"] == ("Routine scores since 2023-01: 92, 90 (mean 91.0). "
                                 "1 of 2 routine inspections found a major violation.")


def test_files_for_the_api_and_the_frozen_copy(data, tmp_path):
    insp, info = data
    f = ew.worklist(insp, info, MONTH, lookup)
    folder, frozen = ew.write_month(f, MONTH, out=str(tmp_path / "worklists"))
    assert sorted(os.listdir(folder)) == sorted([f"district-{n}.csv" for n in range(1, 10)] + ["manifest.json", "frozen"])
    with open(os.path.join(folder, "district-1.csv"), newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ew.COLUMNS
    assert [r[0] for r in rows[1:]] == ["FA0002", "FA0001", "FA0003"]
    assert rows[1][ew.COLUMNS.index("due_estimate")] == "2026-08-27"
    assert rows[1][ew.COLUMNS.index("rule_points")] == "18.0"
    with open(os.path.join(folder, "district-3.csv"), newline="", encoding="utf-8") as fh:
        assert list(csv.reader(fh)) == [ew.COLUMNS]                  # every district has a file
    m = json.load(open(os.path.join(folder, "manifest.json")))
    assert set(m) == {"month", "generated", "method", "rule", "files"} and m["month"] == MONTH
    assert "No published card export" in m["method"]                 # the fallback is stated
    assert m["files"] == {str(n): ew.sha256(os.path.join(folder, f"district-{n}.csv")) for n in range(1, 10)}
    assert ew.verify(frozen) == []
    target = os.path.join(frozen, "district-1.csv")
    assert not os.access(target, os.W_OK)                             # frozen files are read-only
    os.chmod(target, stat.S_IWRITE)
    with open(target, "a", encoding="utf-8") as fh:
        fh.write("tampered\n")
    assert ew.verify(frozen) == ["district-1.csv"]


def test_scoring_file_holds_every_active_facility(data, tmp_path):
    insp, info = data
    f = ew.worklist(insp, info, MONTH, lookup)
    _, frozen = ew.write_month(f, MONTH, out=str(tmp_path / "worklists"))
    sc = pd.read_csv(os.path.join(frozen, "scoring.csv"))
    assert list(sc.columns) == ew.SCORING
    assert set(sc["business_id"]) == {1, 2, 3, 4, 5, 9}
    assert sc.loc[sc["business_id"] == 4, "due_this_month"].item() == 0
    assert sc.loc[sc["business_id"] == 4, "rule_order"].isna().item()
    assert list(sc.loc[sc["district"] == 1, "business_id"]) == [2, 1, 4, 3]   # 4 (6.0 pts) ranks among all active


def site_export(tmp_path, points, sample=False):
    """A minimal export_site.py export: facilities.geojson with points and bands, meta.json."""
    site = tmp_path / "site"
    site.mkdir()
    feats = [{"type": "Feature", "geometry": None,
              "properties": {"facility_id": fid, "points": pts, "band": band}} for fid, (pts, band) in points.items()]
    (site / "facilities.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    (site / "meta.json").write_text(json.dumps({"sample": sample, "run": "forward_2026-09-20",
                                                "inspections_through": "2026-09-19",
                                                "card": {"rule": "Restaurants get whole points.",
                                                         "eligibility": "restaurants with two rated routines"}}))
    return str(site)


def test_card_points_first_then_the_one_line_rule(data, tmp_path):
    insp, info = data
    card = ew.load_card(site_export(tmp_path, {"FA0001": (30, "1"), "FA0003": (30, None), "FA0009": (5, None),
                                               "FA0002": (None, None)}))
    f = ew.worklist(insp, info, MONTH, lookup, card=card)
    due = f[f["due_this_month"]]
    d1 = due[due["district"] == 1].sort_values("rule_order")
    assert list(d1.index) == [1, 3, 2]            # 30 pts (mean 91), 30 pts (mean 97), then no points
    assert list(due[due["district"] == 2].sort_values("rule_order").index) == [9, 5]
    assert f.loc[1, "why"].startswith("Published card: 30 points, band 1. Routine scores since 2023-01: 92, 90")
    assert f.loc[2, "why"].startswith("Not scored by the published card; placed after its places")
    folder, _ = ew.write_month(f, MONTH, out=str(tmp_path / "worklists"), card=card)
    with open(os.path.join(folder, "district-1.csv"), newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))[1:]
    assert [(r[0], r[ew.COLUMNS.index("rule_order")], r[ew.COLUMNS.index("rule_points")]) for r in rows] ==         [("FA0001", "1", "30"), ("FA0003", "2", "30"), ("FA0002", "3", "")]
    m = json.load(open(os.path.join(folder, "manifest.json")))
    assert m["rule"].startswith("Published point card") and "No published card export" not in m["method"]


def test_the_invented_sample_is_never_used_as_the_card(tmp_path):
    assert ew.load_card(site_export(tmp_path, {"FA0001": (30, "1")}, sample=True)) is None
    assert ew.load_card(str(tmp_path / "missing")) is None
