"""The invented export for the food-inspection site keeps the v3.1 contract's shape: a small
index, one place file per place that matches its index entry, County records with the County's
status text, a published rule whose worksheet rows add up, bands cut so equal points are never
split, and nothing that reads as a real address."""
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "food-dashboard"
VISIT_TYPES = {"routine", "reinspection", "followup", "complaint"}
SEVERITIES = {"major", "minor", "grp"}
CLOSURES = {"health", "permit", "other"}
INDEX_KEYS = {"facility_id", "name", "address", "facility_type", "council_district", "last_visit", "grade", "flags", "band", "points", "on_hold"}
DETAIL_KEYS = {"business_type", "inspections", "violations", "score_card", "band_stability"}
FORBIDDEN = {"rank", "percentile", "oof_rank", "score", "shap_features", "is_known_positive"}
REAL_STREETS = ("Convoy", "Garnet", "University Ave", "5th Ave", "India St", "El Cajon", "Adams Ave", "Rosecrans")


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
        assert set(p["flags"]) <= {"major", "closed", "bc", "repeat", *mod.THEMES}
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
        g = f["properties"]["grade"]
        if g:
            record = [i for i in d["inspections"] if i["date"] == g["date"] and i["grade"] == g["grade"] and i["score"] == g["score"]]
            assert record, "the grade shown is one County record's letter"
        assert len(d["violations"]) <= 60
        sev = [v["severity"] for v in d["violations"]]
        assert sev == sorted(sev, key=["major", "minor", "grp"].index), "majors first"
        for v in d["violations"]:
            assert v["theme"] in mod.ITEMS and v["severity"] in SEVERITIES and v["visit"] in VISIT_TYPES
            assert v["code"] and v["description"]
    assert {"Complete", "Ordered Closed", "Approved to Reopen"} <= statuses
    assert {"supplier", "condition", "process"} <= set(mod.ITEMS), "the split themes of contract v3"
    assert "source" not in mod.ITEMS


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
        assert not {"score_card", "band_stability"} & set(places[f["properties"]["facility_id"]])


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
