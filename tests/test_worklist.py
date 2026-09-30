"""export_worklist.py on a small synthetic inspection table: who is due, the rule's order, the
files the API reads, and the frozen copy a pilot is scored against."""
import csv
import re
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
    assert set(m) == {"month", "generated", "method", "rule", "export_run", "listed_kinds", "files"} and m["month"] == MONTH
    assert "No point rule export" in m["method"]                     # the fallback is stated
    assert m["files"] == {str(n): ew.sha256(os.path.join(folder, f"district-{n}.csv")) for n in range(1, 10)}
    assert ew.verify(frozen) == []
    target = os.path.join(frozen, "district-1.csv")
    mode = os.stat(target).st_mode                                    # frozen files are read-only (mode bits:
    assert not mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)    # os.access is always True for root)
    os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)     # owner read-write (S_IWRITE alone is write-only on POSIX)
    with open(target, "a", encoding="utf-8") as fh:
        fh.write("tampered\n")
    assert ew.verify(frozen) == ["district-1.csv"]
    if os.name != "nt":                                # an unreadable frozen file is reported, not a crash
        os.chmod(target, 0)
        if not os.access(target, os.R_OK):             # (root can still read it)
            assert ew.verify(frozen) == ["district-1.csv"]
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)


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


def test_scored_and_unscored_places_share_one_scale(data, tmp_path):
    """The card's points where it scores a place, else 100 minus its mean routine score: an unscored
    place with a worse record is never listed below a scored one with a better record."""
    insp, info = data
    card = ew.load_card(site_export(tmp_path, {"FA0001": (30, "1"), "FA0003": (30, None), "FA0009": (5, None),
                                               "FA0002": (None, None)}), holds=[])
    f = ew.worklist(insp, info, MONTH, lookup, card=card)
    due = f[f["due_this_month"]]
    d1 = due[due["district"] == 1].sort_values("rule_order")
    assert list(d1.index) == [1, 3, 2]            # 30 pts (mean 91), 30 pts (mean 97), then 18.0 (mean 82)
    assert list(due[due["district"] == 2].sort_values("rule_order").index) == [5, 9], "11.0 (unscored) above 5 points"
    assert f.loc[1, "why"].startswith("Point rule (the students', not a County rating): 30 points, band 1. Routine scores since 2023-01: 92, 90")
    assert f.loc[2, "why"].startswith("Not scored by the point rule; placed on the same scale")
    folder, _ = ew.write_month(f, MONTH, out=str(tmp_path / "worklists"), card=card)
    with open(os.path.join(folder, "district-1.csv"), newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))[1:]
    assert [(r[0], r[ew.COLUMNS.index("rule_order")], r[ew.COLUMNS.index("rule_points")]) for r in rows] == \
        [("FA0001", "1", "30"), ("FA0003", "2", "30"), ("FA0002", "3", "18.0")]
    m = json.load(open(os.path.join(folder, "manifest.json")))
    assert "the students' point rule" in m["rule"] and "No point rule export" not in m["method"]
    assert m["export_run"] == card["run"] and "private home" in m["listed_kinds"]


def _place_file(site, fid, **d):
    place = os.path.join(site, "place")
    os.makedirs(place, exist_ok=True)
    json.dump({"facility_id": fid, **d}, open(os.path.join(place, f"{fid}.json"), "w", encoding="utf-8"))


def test_a_place_meeting_an_escalation_fact_comes_first(data, tmp_path):
    insp, info = data
    site = site_export(tmp_path, {"FA0001": (30, "1"), "FA0003": (3, None), "FA0002": (None, None)})
    fc = json.loads(open(os.path.join(site, "facilities.geojson")).read())
    for ft in fc["features"]:
        if ft["properties"]["facility_id"] == "FA0003":
            ft["properties"]["flags"] = ["closures2", "lt90_2"]
            ft["properties"]["grade"] = {"grade": "A", "date": "2026-05-30", "score": 98, "open_closure": None}
        if ft["properties"]["facility_id"] == "FA0001":
            ft["properties"]["grade"] = {"grade": "A", "date": "2026-02-10", "score": 94, "replaced": None,
                                         "open_closure": {"date": "2026-03-02", "reason": "health", "later_ungraded": []}}
    open(os.path.join(site, "facilities.geojson"), "w").write(json.dumps(fc))
    _place_file(site, "FA0003", inspections=[
        {"date": "2024-05-01", "closed": True, "closure": "health", "reopened": True, "reopened_on": "2024-05-03"},
        {"date": "2025-01-05", "closed": True, "closure": "health", "reopened": True, "reopened_on": "2025-01-07"},
        {"date": "2026-03-02", "closed": True, "closure": "health", "reopened": False, "reopened_on": None}])
    card = ew.load_card(site, holds=[])
    f = ew.worklist(insp, info, MONTH, lookup, card=card)
    d1 = f[f["due_this_month"] & (f["district"] == 1)].sort_values("rule_order")
    assert list(d1.index)[0] == 3, "a place meeting an escalation fact (our count) comes first, whatever its points"
    r = f.loc[3]
    assert r["escalation"].startswith("two or more health closures in two years; two or more routine scores below 90 in two years")
    assert r["why"].startswith("First: two or more health closures")
    assert "the County sets no count or period" in r["why"] and "not a County finding" in r["why"]
    assert (r["closures_24m"], r["last_closure"], r["reopened_on"], r["posted_grade"]) == (2, "2026-03-02", "", "A (2026-05-30)"), \
        "the export's episodes in the 24 months before its list date (2026-09-20): the 2024 closure is older"
    assert r["no_reopen_on_record"] == "", "no open closure on its grade"
    # A last closure nothing on the record ended: its date, beside the letter from before it.
    fa1 = f[f["facility_id"] == "FA0001"].iloc[0]
    assert (fa1["posted_grade"], fa1["no_reopen_on_record"]) == ("A (2026-02-10)", "2026-03-02")
    folder, _ = ew.write_month(f, MONTH, out=str(tmp_path / "wl"), freeze=False, card=card)
    with open(os.path.join(folder, f"district-{int(fa1['district'])}.csv"), encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0])[-1] == "no_reopen_on_record"
    if fa1["due_this_month"]:
        assert {x["facility_id"]: x["no_reopen_on_record"] for x in rows}["FA0001"] == "2026-03-02"


def test_a_held_place_keeps_its_record_and_loses_its_points(data, tmp_path):
    insp, info = data
    card = ew.load_card(site_export(tmp_path, {"FA0001": (30, "1"), "FA0003": (3, None)}), holds=["FA0001"])
    assert "FA0001" not in card["points"] and "FA0001" not in card["band"] and card["held"] == {"FA0001"}
    f = ew.worklist(insp, info, MONTH, lookup, card=card)
    assert f.loc[1, "why"] == "On hold at the owner's request: its points, band and order are withheld while the request is reviewed."
    assert pd.isna(f.loc[1, "rule_points"]) and pd.isna(f.loc[1, "rule_mean"]), "no number that gives the points away"
    d1 = f[f["district"] == 1].sort_values("rule_order_all")
    assert list(d1.index)[-1] == 1, "and no place in the order: listed after every other place in its district"


def test_holds_are_read_strictly_so_a_broken_file_never_releases_them(tmp_path):
    path = tmp_path / "holds.json"
    assert ew.load_holds(path) == set(), "no file: nothing on hold"
    path.write_text(json.dumps({"facility_ids": ["FA0001 "]}), encoding="utf-8")
    assert ew.load_holds(path) == {"FA0001"}
    for broken in ('{"facility_ids": ["FA0001",]}', '{"facility_ids": "FA0001"}', '{"ids": ["FA0001"]}'):
        path.write_text(broken, encoding="utf-8")
        with pytest.raises(SystemExit, match="would release every hold"):
            ew.load_holds(path)


def test_a_closure_reads_as_the_rules_70_not_the_countys_score():
    used = [(95, False, 95), (70, True, None), (70, True, 94)]
    why = ew._why([95], 0, 3, points=12, band="1", card=True, used=used)
    assert "70 (a health closure, our reading; the County gave no score, this rule counts it as 70)" in why
    assert "70 (a health closure, our reading; the County's score that day 94, this rule counts it as 70)" in why
    assert "mean 78.3" in why


def test_the_invented_sample_is_never_used_as_the_card(tmp_path):
    assert ew.load_card(site_export(tmp_path, {"FA0001": (30, "1")}, sample=True)) is None
    assert ew.load_card(str(tmp_path / "missing")) is None


def test_the_model_trains_on_features_as_of_the_first(tmp_path, monkeypatch):
    """The list is scored on the 1st (features_asof), so the model trains the same way: a visit
    earlier in an inspection's own month is not part of that training row's history."""
    visits = [("2026-03-02", "Routine", 90), ("2026-08-03", "Re-inspection", None), ("2026-08-20", "Routine", 88)]
    rows = [{"business_id": 10, "business_type": "Restaurant Food Facility", "zip": "92101", "lat": 1,
             "lng": -117.0, "opened_date": "2020-01-01", "inspection_id": i, "insp_type": t, "status": "Complete",
             "score": s, "grade": "A" if s else None, "completed_date": day, "n_violations": 0, "n_major": 0,
             "n_minor": 0, "n_grp": 0, "closure": None} for i, (day, t, s) in enumerate(visits)]
    path = tmp_path / "inspections.csv"
    pd.DataFrame(rows, columns=COLS).to_csv(path, index=False)

    class Stop(Exception):
        pass

    seen = {}

    def fit(self, rows, *a, **k):
        seen["rows"] = rows
        raise Stop

    monkeypatch.setattr(mf.Model, "fit", fit)
    with pytest.raises(Stop):
        ew.model_orders(mf.load(str(path)), MONTH, pd.DataFrame())
    r = seen["rows"].set_index("completed_date").loc[pd.Timestamp("2026-08-20")]
    assert r["prior_n"] == 1                             # the 2026-08-03 visit is after the 1st
    assert r["days_since_last"] == (pd.Timestamp("2026-08-01") - pd.Timestamp("2026-03-02")).days


def test_private_homes_and_other_unlisted_kinds_never_reach_a_list(data):
    insp, info = data
    homes = insp.copy()
    homes.loc[homes["business_id"] == 2, "business_type"] = "Microenterprise Home Kitchen Operation"
    homes.loc[homes["business_id"] == 5, "business_type"] = "Cottage Food Operation - Class B"
    f = ew.worklist(homes, info, MONTH, lookup)
    assert 2 not in f.index and 5 not in f.index and 1 in f.index
    assert 2 in ew.worklist(homes, info, MONTH, lookup, listed_only=False).index    # the counts-only dashboard


def test_a_scored_row_explains_its_points_from_the_scores_its_worksheet_averages(data, tmp_path):
    insp, info = data
    site = site_export(tmp_path, {"FA0001": (9, "1")})
    place = os.path.join(site, "place")
    os.makedirs(place, exist_ok=True)
    json.dump({"facility_id": "FA0001", "scores_used": [{"date": "2025-06-05", "score": 92, "closure": False},
                                                         {"date": "2025-12-02", "score": 90, "closure": False}]},
              open(os.path.join(place, "FA0001.json"), "w", encoding="utf-8"))
    card = ew.load_card(site, holds=[])
    f = ew.worklist(insp, info, MONTH, lookup, card=card)
    assert "It averages the routine scores of the two years before the list: 92, 90; mean 91.0" in f.loc[1, "why"]
    assert f.loc[1, "last_routine_outcome"] == "Complete" and f.loc[1, "closures_24m"] == 0


def test_every_explanation_averages_the_same_readings_as_its_number(data, tmp_path):
    """A closure the County also scored reads as 70 in the number, so it reads as 70 in the line too,
    with the County's score beside it: the explanation's mean is always the row's rule_mean."""
    insp, info = data
    closed = insp["business_id"] == 3
    insp = insp.copy()
    insp["closure_order"] = None
    last = insp[closed].index[-1]
    insp.loc[last, ["closure_order", "rated_score"]] = ["health", 70.0]            # scored 98 that day, and closed
    f = ew.worklist(insp, info, MONTH, lookup)
    for b, r in f.iterrows():
        m = re.search(r"\(mean ([0-9.]+)\)", r["why"])
        if m:
            assert abs(float(m.group(1)) - (100 - r["mean_points"])) < 0.051, (b, r["why"], r["mean_points"])
    assert "70 (a health closure, our reading; the County's score that day 98, this rule counts it as 70)" in f.loc[3, "why"]

