"""The invented export for the food-inspection site keeps the contract's shape: a small index, one
place file per place that matches its index entry, County records with the County's status text
(a closure with the date the County reopened it), items under the sections of the County's report,
flags counted back from the list date, a published rule whose worksheet rows add up (a health
closure read as 70), bands cut so equal points are never split, the frozen-rule, drift, route and
district fields the real meta carries, and nothing that reads as a real address."""
import importlib.util
import json
import re
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "food-dashboard"
VISIT_TYPES = {"routine", "reinspection", "followup", "complaint"}
SEVERITIES = {"major", "minor", "grp"}
CLOSURES = {"health", "permit", "other"}
INDEX_KEYS = {"facility_id", "name", "address", "facility_type", "council_district", "last_visit", "grade", "flags", "band", "points", "on_hold"}
DETAIL_KEYS = {"business_type", "inspections", "violations", "score_card", "band_stability", "scores_used", "estimate"}
FORBIDDEN = {"rank", "percentile", "oof_rank", "score", "shap_features", "is_known_positive"}
REAL_STREETS = ("Convoy", "Garnet", "University Ave", "5th Ave", "India St", "El Cajon", "Adams Ave", "Rosecrans")
# The sections of the County's inspection report (food-dashboard/src/lib/inspections.js THEMES).
THEMES = ("knowledge", "health", "hands", "handsink", "temperature", "condition", "sanitizing", "supplier", "process",
          "advisory", "hsp", "water", "sewage", "vermin", "grp_staff", "grp_food", "grp_storage", "grp_equipment",
          "grp_facility", "grp_signs", "grp_other", "other")
RECORD_FLAGS = {"major", "closed", "bc", "repeat", "closures2", "repeat_item", "lt90_2"}


def load():
    spec = importlib.util.spec_from_file_location("make_sample_export", SITE / "scripts" / "make_sample_export.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_index_and_place_files_are_deterministic_and_match():
    mod = load()
    fc, places, meta = mod.build(300, seed=3)
    fc2, places2, _ = mod.build(300, seed=3)
    assert json.dumps(fc) == json.dumps(fc2) and json.dumps(places) == json.dumps(places2), "same seed, same export"
    assert meta["mode"] == "bands" and meta["sample"] is True and meta["expires"] is None
    assert meta["places"] == len(fc["features"]) == len(places) == 300
    assert meta["publication"] is None and meta["contact"] is None and meta["corrections"] == []
    ids = [f["properties"]["facility_id"] for f in fc["features"]]
    assert len(set(ids)) == len(ids)
    for f in fc["features"]:
        p = f["properties"]
        assert set(p) <= INDEX_KEYS and not (set(p) & FORBIDDEN), "the index carries only what the map, list and search need"
        detail = places[p["facility_id"]]
        assert set(detail) <= INDEX_KEYS | DETAIL_KEYS
        assert all(detail[k] == v for k, v in p.items()), "a place file holds its index entry"
        assert p["name"].startswith("Sample ") and p["facility_id"].startswith("SAMPLE-")
        assert not any(s in p["address"] for s in REAL_STREETS), "no invented place sits on a real street"
        assert any(s in p["address"] for s in mod.STREETS)
        assert p["facility_type"] in {"restaurant", "limited", "market"}
        assert 1 <= p["council_district"] <= 9
        assert p["last_visit"] == {"date": detail["inspections"][-1]["date"], "type": detail["inspections"][-1]["type"]}
        assert set(p["flags"]) <= RECORD_FLAGS | set(THEMES) - {"other"}, "a major's theme is never flagged as other"
        lon, lat = f["geometry"]["coordinates"]
        assert 32.4 < lat < 33.2 and -117.4 < lon < -116.8


def test_records_carry_the_county_status_and_single_record_grades():
    mod = load()
    fc, places, _ = mod.build(300, seed=3)
    statuses = set()
    for f in fc["features"]:
        d = places[f["properties"]["facility_id"]]
        dates = [i["date"] for i in d["inspections"]]
        assert dates == sorted(dates) and dates[0] >= "2023-01-01"
        for i in d["inspections"]:
            statuses.add(i["status"])
            assert i["type"] in VISIT_TYPES
            if i["grade"] is not None:
                assert i["type"] in ("routine", "followup") and i["grade"] == mod.grade(i["score"])
            assert i["closed"] == (i["closure"] is not None)
            assert i["closure"] is None or i["closure"] in CLOSURES
            assert (i["reopened"] is None) == (i["closure"] is None)
            if i["status"] == "Approved to Reopen":
                assert i["type"] == "followup"
            # A closure carries the date of the County's "Approved to Reopen" record that ended it, or None.
            assert ("reopened_on" in i) == i["closed"]
            if i["closed"] and i["reopened"]:
                assert i["reopened_on"] > i["date"]
                assert any(j["date"] == i["reopened_on"] and j["status"] == "Approved to Reopen" for j in d["inspections"])
            elif i["closed"]:
                assert i["reopened_on"] is None
        g = f["properties"]["grade"]
        if g:
            record = [i for i in d["inspections"] if i["date"] == g["date"] and i["grade"] == g["grade"] and i["score"] == g["score"]]
            assert record, "the grade shown is one County record's letter"
        assert len(d["violations"]) <= 60
        sev = [v["severity"] for v in d["violations"]]
        assert sev == sorted(sev, key=["major", "minor", "grp"].index), "majors first"
        for v in d["violations"]:
            assert v["theme"] in THEMES and v["severity"] in SEVERITIES and v["visit"] in VISIT_TYPES
            assert v["code"] and v["description"]
            assert v["theme"] == mod.FIXED_FORM[v["code"]], "an item's theme is its section on the County's form"
            assert v["theme"].startswith("grp_") == (v["severity"] == "grp")
    assert {"Complete", "Ordered Closed", "Approved to Reopen"} <= statuses


def test_themes_follow_the_county_forms():
    mod = load()
    assert mod.THEMES == THEMES
    for old in ("handwashing", "hygiene", "plumbing", "storage", "equipment", "labeling", "source"):
        assert old not in mod.THEMES and old not in mod.ITEMS
    for theme, items in mod.ITEMS.items():
        for code, text in items:
            assert mod.FIXED_FORM[code] == theme, (code, text)
    fixed = {"1a": "knowledge", "1b": "knowledge", "4": "health", "5": "hands", "6": "handsink", "11": "temperature",
             "13": "condition", "14": "sanitizing", "17": "supplier", "18": "process", "19": "advisory", "20": "hsp",
             "21": "water", "22": "sewage", "23": "vermin", "25": "grp_staff", "29": "grp_food", "32": "grp_storage",
             "33": "grp_equipment", "40": "grp_equipment", "46": "grp_facility", "47": "grp_signs", "52": "grp_signs"}
    assert {k: mod.FIXED_FORM[k] for k in fixed} == fixed
    mobile = {"1b": "knowledge", "15": "supplier", "18": "advisory", "19": "water", "20": "handsink", "21": "sewage",
              "22": "vermin", "23": "grp_staff", "27": "grp_food", "29": "grp_storage", "32": "grp_equipment",
              "33": "grp_facility", "34": "grp_equipment", "36": "grp_equipment", "37": "grp_facility", "39": "grp_other",
              "40": "grp_facility", "41": "grp_signs", "42": "grp_signs"}
    assert {k: mod.MOBILE_FORM[k] for k in mobile} == mobile
    assert "16" not in mod.MOBILE_FORM and "17" not in mod.MOBILE_FORM


def test_flags_count_back_from_the_list_date():
    mod = load()
    fc, places, meta = mod.build(1400, seed=9)
    list_date = date.fromisoformat(meta["generated"])
    lo1, lo2 = (list_date - timedelta(days=365)).isoformat(), (list_date - timedelta(days=730)).isoformat()
    seen = set()
    for f in fc["features"]:
        p = f["properties"]
        d = places[p["facility_id"]]
        seen |= set(p["flags"])
        year = [i for i in d["inspections"] if i["date"] >= lo1]
        two = [i for i in d["inspections"] if i["date"] >= lo2]
        assert ("major" in p["flags"]) == any(i["major"] for i in year)
        assert ("closed" in p["flags"]) == any(i["closed"] and i["closure"] == "health" for i in year)
        assert ("closures2" in p["flags"]) == (sum(i["closed"] and i["closure"] == "health" for i in two) >= 2)
        assert ("lt90_2" in p["flags"]) == (sum(i["type"] == "routine" and i["score"] is not None and i["score"] < 90 for i in two) >= 2)
        for t in set(p["flags"]) - RECORD_FLAGS:
            assert any(v["theme"] == t and v["severity"] == "major" and v["date"] >= lo1 for v in d["violations"]), (p["facility_id"], t)
        if "repeat_item" in p["flags"]:
            dates = {}
            for v in d["violations"]:
                if v["severity"] == "major" and v["visit"] == "routine" and v["date"] >= lo2:
                    dates.setdefault(v["code"], set()).add(v["date"])
            assert max(len(s) for s in dates.values()) >= 2
    assert {"closures2", "repeat_item", "lt90_2"} <= seen, "the sample shows every escalation fact"
    # A place whose last visit is more than a year before the list date has none of the 12-month facts.
    stale = [f["properties"] for f in fc["features"] if f["properties"]["last_visit"]["date"] < lo1]
    assert stale and not any({"major", "closed", "bc", "repeat"} & set(p["flags"]) for p in stale)


def test_scores_used_read_a_closure_as_70_beside_the_county_score():
    mod = load()
    _, places, meta = mod.build(1400, seed=9)
    rows = [u for d in places.values() for u in d.get("scores_used", [])]
    assert rows and all(set(u) == {"date", "score", "closure", "county_score"} for u in rows)
    closures = [u for u in rows if u["closure"]]
    assert closures and all(u["score"] == 70 for u in closures)
    assert {u["county_score"] is None for u in closures} == {True, False}, "the County scores some closures and not others"
    assert all(u["score"] == u["county_score"] for u in rows if not u["closure"])
    for d in places.values():
        used = d.get("scores_used")
        if used:
            avg = next(r for r in d["score_card"] if r["item"] == "avg_deficit")
            mean = sum(u["score"] for u in used) / len(used)
            assert avg["value"] == max(0, 100 - int(mean + 0.5))
    assert meta["card"]["closure_score"] == 70


def test_meta_carries_the_frozen_rule_drift_routes_and_district_precision():
    mod = load()
    _, _, meta = mod.build(1400, seed=9)
    f = meta["frozen"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}-[0-9a-f]{8}", f["version"]) and f["version"].startswith(f["frozen_on"]) and f["from_run"]
    dr = meta["drift"]
    for k in ("major_rate_backtest", "major_rate_recent", "band_1_share_backtest", "band_1_share_now"):
        assert dr[k] is None or 0 <= dr[k] <= 1, k
    assert dr["refit_needed"] == bool(dr["reasons"]) and dr["thresholds"] == {"major_rate": 0.05, "band_share": 0.05}
    route = meta["card"]["band_1_by_route"]
    band_1 = next(b for b in meta["card"]["bands"] if b["band"] == "1")
    assert route["closure"]["labelled"] + route["scores"]["labelled"] == band_1["labelled"]
    assert route["closure"]["positives"] + route["scores"]["positives"] == band_1["positives"]
    assert route["closure"]["labelled"] and route["scores"]["labelled"], "the sample shows both routes into band 1"
    for r in route.values():
        assert len(r["interval"]) == 2 and (r["rate"] is None or r["interval"][0] <= r["rate"] <= r["interval"][1])
    by = meta["fairness"]["by_district"]
    assert set(by) == {str(n) for n in range(1, 10)}
    for row in by.values():
        iv = row["precision_interval"]
        assert iv is None or (0 <= iv[0] <= row["precision"] <= iv[1] <= 1)
    _, _, record = mod.build(200, seed=5, mode="record")
    assert not {"frozen", "drift", "fairness"} & set(record)


def test_worksheets_add_up_and_bands_never_split_a_tie():
    mod = load()
    fc, places, meta = mod.build(1400, seed=9)
    card = meta["card"]
    assert card["rule"] and card["baseline_name"] == "average score"
    weights = {it["item"]: it["weight"] for it in card["items"]}
    assert set(weights) == {"avg_deficit", "theme_temperature"}
    by_band = {}
    for f in fc["features"]:
        p = f["properties"]
        d = places[p["facility_id"]]
        if p.get("on_hold"):
            assert "band" not in p and "points" not in p and "score_card" not in d
            continue
        if "points" in p:
            assert p["facility_type"] == "restaurant", "only eligible restaurants are scored"
            rows = d["score_card"]
            assert [r["item"] for r in rows] == list(weights)
            for r in rows:
                assert r["weight"] == weights[r["item"]] and r["points"] == r["weight"] * r["value"] and r["met"] == (r["points"] > 0)
            assert p["points"] == sum(r["points"] for r in rows), "the worksheet adds up"
            assert 0 <= d["band_stability"] <= 1
        else:
            assert "band" not in p and "score_card" not in d, "an unscored place carries neither points nor a band"
        if "band" in p:
            by_band.setdefault(p["band"], []).append(p["points"])
    assert sorted(by_band) == ["1", "2", "3"]
    for b in card["bands"]:
        pts = by_band[b["band"]]
        assert b["min_points"] == min(pts) and b["places_now"] == len(pts)
        assert (b["max_points"] is None) == (b["band"] == "1"), "the top band has no upper limit"
        assert b["max_points"] is None or max(pts) <= b["max_points"]
        assert set(b) >= {"share", "labelled", "positives", "rate", "interval", "baseline_rate", "vs_baseline", "kept_in_refits"}
        assert 0 <= b["interval"][0] <= b["rate"] <= b["interval"][1] <= 1
    assert card["bands"][1]["max_points"] == card["bands"][0]["min_points"] - 1 and card["bands"][2]["max_points"] == card["bands"][1]["min_points"] - 1
    unbanded = [f["properties"]["points"] for f in fc["features"] if "points" in f["properties"] and "band" not in f["properties"]]
    assert max(unbanded) < card["bands"][2]["min_points"], "no tie across the edge of band 3"
    assert sum(1 for f in fc["features"] if f["properties"].get("on_hold")) == 1
    assert card["rest"]["rate"] < card["bands"][0]["rate"]
    gc = meta["grade_context"]
    assert 0.5 < gc["majors_graded_A_share"] < gc["graded_A_share"] <= 1


def test_record_mode_has_nothing_from_a_model():
    mod = load()
    fc, places, meta = mod.build(200, seed=5, mode="record")
    assert meta["mode"] == "record"
    assert not {"card", "catch", "catch_run", "named_bands", "candidates", "model"} & set(meta)
    for f in fc["features"]:
        assert not {"band", "points", "on_hold"} & set(f["properties"])
        assert not {"score_card", "band_stability", "scores_used", "estimate"} & set(places[f["properties"]["facility_id"]])


def test_written_export_passes_the_site_check(tmp_path):
    mod = load()
    for mode in ("bands", "record"):
        out = tmp_path / mode
        mod.write(out, *mod.build(250, seed=4, mode=mode))
        assert len(list((out / "place").glob("*.json"))) == 250
        node = shutil.which("node")
        if node:
            r = subprocess.run([node, str(SITE / "scripts" / "check-export.mjs"), str(out)], capture_output=True, text=True)
            assert r.returncode == 0, r.stdout + r.stderr
