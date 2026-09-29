"""The invented export for the food-inspection site keeps the contract's shape: a small index, one
place file per place that matches its index entry, County records with the County's status text
(a closure with the date the County reopened it), items under the sections of the County's report,
flags counted back from the list date, the students' point rule with worksheet rows that add up (a
health closure read as 70), bands cut so equal points are never split, the frozen-rule, drift, route
and district fields the real meta carries (drift quarter by quarter; family-wise district intervals,
also widened for an assumed design effect), two estimate curves with each place reading its own
group's, interim rates, and nothing that reads as a real address. Its records carry the County's own
type and notes verbatim, and a few places show each of the rarer records the real export keeps (a
closure only an "Approved to Reopen" shows, a reopening no closure could be placed before, Status
Verification and Self Closed records, a closure with no reopening on record), without moving the
rule, the flags or the backtest."""
import importlib.util
import json
import random
import re
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "food-dashboard"
VISIT_TYPES = {"routine", "reinspection", "followup", "complaint", "status_check"}
SEVERITIES = {"major", "minor", "grp"}
CLOSURES = {"health", "permit", "other"}
INDEX_KEYS = {"facility_id", "name", "address", "facility_type", "council_district", "last_visit", "grade", "flags", "band", "points", "on_hold"}
DETAIL_KEYS = {"business_type", "inspections", "violations", "theme_counts", "violations_total", "score_card", "band_stability", "scores_used", "estimate"}
FORBIDDEN = {"rank", "percentile", "oof_rank", "score", "shap_features", "is_known_positive"}
REAL_STREETS = ("Convoy", "Garnet", "University Ave", "5th Ave", "India St", "El Cajon", "Adams Ave", "Rosecrans")
# The sections of the County's inspection report (food-dashboard/src/lib/inspections.js THEMES).
THEMES = ("knowledge", "health", "hands", "handsink", "temperature", "condition", "sanitizing", "supplier", "process",
          "advisory", "hsp", "water", "sewage", "vermin", "grp_staff", "grp_food", "grp_storage", "grp_equipment",
          "grp_facility", "grp_signs", "grp_other", "other")
RECORD_FLAGS = {"major", "closed", "bc", "repeat", "major_2", "closures2", "repeat_item", "lt90_2"}


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
                # the County's re-grade after a closure; a reinspection after a Status Verification
                # closure, or when no closure could be placed before it (never scored)
                assert i["type"] == "followup" or (i["type"] == "reinspection" and i["score"] is None)
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


COUNTY_TYPES = {"routine": {"Routine"}, "followup": {"Routine"}, "reinspection": {"Re-inspection"},
                "complaint": {"Site Investigation", "Environmental"}, "status_check": {"Status Verification"}}


def test_records_carry_the_countys_own_type_and_notes():
    mod = load()
    _, places, _ = mod.build(1400, seed=9)
    seen_types, seen_notes = set(), set()
    for d in places.values():
        for i in d["inspections"]:
            assert i["county_type"] in COUNTY_TYPES[i["type"]], (i["type"], i["county_type"])
            assert isinstance(i["notes"], list) and all(isinstance(n, str) and n for n in i["notes"])
            seen_types.add(i["county_type"])
            seen_notes |= set(i["notes"])
            if i["closed"] and i["closure"] == "permit":
                assert "No Valid Permit" in i["notes"], "a permit closure shows the note it is read from"
    assert seen_types == {"Routine", "Re-inspection", "Site Investigation", "Environmental", "Status Verification"}
    assert seen_notes == {"No Valid Permit", "Impoundment"}


def test_the_rarer_records_the_real_export_keeps():
    mod = load()
    fc, places, _ = mod.build(1400, seed=9)
    found = {k: 0 for k in ("inferred", "reopen_only", "sv_closed", "sv_items", "self_closure", "self_items", "open")}
    for f in fc["features"]:
        d = places[f["properties"]["facility_id"]]
        recs = d["inspections"]
        for k, i in enumerate(recs):
            if i.get("closure_inferred"):
                # no closure order on the record: an unscored routine with a major, and the County's reopening days later
                found["inferred"] += 1
                assert i["closed"] and i["status"] == "Complete" and i["type"] == "routine" and i["score"] is None and i["major"]
                assert i["reopened"] and any(j["date"] == i["reopened_on"] and j["status"] == "Approved to Reopen" for j in recs)
            if i.get("reopen_without_closure"):
                found["reopen_only"] += 1
                assert i["status"] == "Approved to Reopen" and not i["closed"] and i["type"] == "reinspection"
                assert not any(j["closed"] and j["date"] <= i["date"] and (not j["reopened"] or j["reopened_on"] == i["date"]) for j in recs[:k])
            if i["type"] == "status_check":
                assert i["score"] is None and i["grade"] is None, "a status verification is never scored"
                if i["status"] == "Ordered Closed":
                    found["sv_closed"] += 1
                    assert i["closed"] and i["closure"] == "permit" and i["notes"] == ["No Valid Permit"] and i["reopened"]
                else:
                    found["sv_items"] += 1
                    assert i["grp"] > 0, "a status verification is kept only with items, or ordered closed"
            if i["status"] == "Self Closed":
                assert i["type"] == "routine" and i["score"] is None and i["grade"] is None and i["major"] + i["minor"] > 0
                assert i["date"] < mod.QUIET_BEFORE.isoformat()
                if i["major"]:
                    # the operator's own closure: a health closure a re-grade days later ends
                    found["self_closure"] += 1
                    assert i["closed"] and i["closure"] == "health" and i["reopened"] is False
                    assert any(j["type"] == "followup" and j["grade"] and 0 < (date.fromisoformat(j["date"]) - date.fromisoformat(i["date"])).days <= 30 for j in recs)
                else:
                    found["self_items"] += 1
                    assert not i["closed"]
        g = f["properties"]["grade"]
        assert g is None or "open_closure" in g
        assert d["grade"] == g
        if g and g["open_closure"]:
            found["open"] += 1
            oc = g["open_closure"]
            last = [i for i in recs if i["closed"]][-1]
            assert oc["date"] == last["date"] and oc["reason"] == last["closure"] and last["reopened"] is False
            after = recs[recs.index(last) + 1:]
            assert not any(i["status"] == "Approved to Reopen" for i in after)
            assert not any(i["type"] in ("routine", "followup") and i["grade"] and i["date"] > oc["date"] for i in after)
            assert oc["later_ungraded"] == sorted({i["date"] for i in after if not i["grade"]})
            assert oc["date"] >= g["date"]
            assert oc.get("status") == last["status"] in ("Ordered Closed", "Self Closed"), \
                "the County's status text on the record that started it, so a Self Closed one is never called an order"
    assert all(found.values()), found


def test_theme_counts_count_every_item_before_the_cut():
    mod = load()
    _, places, _ = mod.build(400, seed=9)
    for d in places.values():
        tc, listed = d["theme_counts"], d["violations"]
        assert d["violations_total"] == sum(c["major"] + c["minor"] + c["grp"] for c in tc.values())
        assert d["violations_total"] >= len(listed) and (len(listed) == 60 or d["violations_total"] == len(listed))
        if len(listed) == 60:
            continue                                        # cut: the counts hold more than the list
        for theme, c in tc.items():
            items = [v for v in listed if v["theme"] == theme]
            assert (c["major"], c["minor"], c["grp"]) == tuple(sum(v["severity"] == s for v in items) for s in ("major", "minor", "grp"))
            assert c["complaint"] == sum(v["visit"] == "complaint" for v in items)
            assert c["latest"] == max(v["date"] for v in items)
    # Past the cut, the counts keep what the list drops.
    items = [{"date": f"2026-0{1 + k % 8}-01", "visit": "routine", "code": "40", "theme": "grp_equipment", "severity": "grp",
              "description": "x"} for k in range(70)] + [{"date": "2026-02-01", "visit": "complaint", "code": "7", "theme": "temperature",
                                                         "severity": "major", "description": "y"}]
    inspections = [{"date": "2026-08-01"}]
    assert len(mod.exported(items, inspections)) == 60
    tc = mod.theme_counts(mod.in_window(items, inspections))
    assert tc["grp_equipment"]["grp"] == 70 and tc["temperature"] == {"major": 1, "minor": 0, "grp": 0, "complaint": 1, "latest": "2026-02-01"}


def test_the_added_records_leave_the_rule_the_flags_and_the_backtest_as_they_were(monkeypatch):
    mod = load()
    fc, places, meta = mod.build(1400, seed=9)

    class NoExtras(random.Random):
        """Every draw above every threshold: the County's types and notes only, nothing added or converted."""
        def random(self):
            return 0.99

    real = mod.add_county_detail
    monkeypatch.setattr(mod, "add_county_detail", lambda rng, ins, vio: real(NoExtras(0), ins, vio))
    fc0, places0, meta0 = mod.build(1400, seed=9)
    assert meta == meta0, "the rule, its bands, the backtest, drift and the district figures are unchanged"
    for f, f0 in zip(fc["features"], fc0["features"]):
        p, p0 = f["properties"], f0["properties"]
        assert {k: v for k, v in p.items() if k != "grade"} == {k: v for k, v in p0.items() if k != "grade"}
        for k in ("score_card", "scores_used", "estimate"):
            assert places[p["facility_id"]].get(k) == places0[p0["facility_id"]].get(k)


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
        assert ("major_2" in p["flags"]) == (len({i["date"] for i in two if i["type"] == "routine" and i["major"]}) >= 2)
        assert ("lt90_2" in p["flags"]) == (sum(i["type"] == "routine" and i["score"] is not None and i["score"] < 90 for i in two) >= 2)
        for t in set(p["flags"]) - RECORD_FLAGS:
            assert any(v["theme"] == t and v["severity"] == "major" and v["date"] >= lo1 for v in d["violations"]), (p["facility_id"], t)
        if "repeat_item" in p["flags"]:
            dates = {}
            for v in d["violations"]:
                if v["severity"] == "major" and v["visit"] == "routine" and v["date"] >= lo2:
                    dates.setdefault(v["code"], set()).add(v["date"])
            assert max(len(s) for s in dates.values()) >= 2
    assert {"major_2", "closures2", "repeat_item", "lt90_2"} <= seen, "the sample shows every escalation fact"
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
    for k in ("major_rate_backtest", "major_rate_recent", "band_1_share_backtest", "band_1_share_now", "latest_rate"):
        assert dr[k] is None or 0 <= dr[k] <= 1, k
    assert dr["refit_needed"] == bool(dr["reasons"]) and dr["thresholds"] == {"min": 0.02, "standard_errors": 3.0}
    assert dr["status"] in ("ok", "refit", "not_yet_measurable") and (dr["status"] == "refit") == dr["refit_needed"]
    # The sample's record ends with the backtest's label year (August 31, 2026): no complete quarter after it.
    assert dr["status"] == "not_yet_measurable" and dr["recent_quarters"] == [] and dr["major_rate_recent"] is None
    assert dr["latest_quarter"] == "2026Q3" and isinstance(dr["latest_n"], int) and dr["latest_n"] >= 200
    assert dr["note"] is None or re.fullmatch(r"In the latest quarter \(2026 Q3, through August 31\) \d+\.\d% of routine .* may be (low|high)\.", dr["note"])
    assert meta["catch_run"]["eligible"] == meta["catch_run"]["candidates"], "the sample's backtest rows are its scored places"
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


def test_district_shares_of_the_wrongly_named_are_over_labelled_scored_places_with_family_wise_intervals():
    mod = load()
    _, _, meta = mod.build(1400, seed=9)
    by = meta["fairness"]["by_district"]
    lab_all = sum(r["labelled"] for r in by.values())
    fp_all = sum(r["false_named"] for r in by.values())
    assert lab_all == meta["catch_run"]["labelled"]
    for d, r in by.items():
        assert r["false_share_ratio"] == round((r["false_named"] / fp_all) / (r["labelled"] / lab_all), 2), d
        for k in ("interval", "interval_family"):
            assert r[k] is None or (len(r[k]) == 2 and 0 <= r[k][0] <= r[k][1]), (d, k)
        assert "interval_family_zip" not in r, "the ZIP-code bootstrap is gone"
        iv, fam, deff = r["interval"], r["interval_family"], r["interval_family_deff"]
        assert fam[0] <= iv[0] and iv[1] <= fam[1], "family-wise is wider than 95%"
        assert deff[0] < fam[0] and fam[1] < deff[1], "and widened again for the design effect (its low end may fall below 0)"
        assert r["evidence_above_even"] is (fam[0] > 1 and deff[0] > 1), d
    # District 5's share of the wrongly named is above even, but its intervals span 1: no evidence
    assert by["5"]["false_share_ratio"] > 1.5 and by["5"]["interval"][0] < 1 and by["5"]["evidence_above_even"] is False


def test_each_place_reads_the_estimate_curve_for_its_own_group():
    mod = load()
    _, places, meta = mod.build(1400, seed=9)
    card = meta["card"]
    for key in ("curve", "curve_closure"):
        c = card[key]
        assert len(c["rate"]) == len(c["low"]) == len(c["high"]) and c["bins"]
        assert all(lo <= r <= hi for r, lo, hi in zip(c["rate"], c["low"], c["high"]))
        assert all(a <= b for a, b in zip(c["rate"], c["rate"][1:])), "monotone"
        assert sum(b["labelled"] for b in c["bins"]) == c["labelled"]
        # the counts each fitted group pools, as export_site.risk_curve's group_counts
        assert [[g["min_points"], g["max_points"]] for g in c["group_counts"]] == c["groups"]
        assert sum(g["labelled"] for g in c["group_counts"]) == c["labelled"]
        assert sum(g["positives"] for g in c["group_counts"]) == c["positives"]
    assert card["curve"]["labelled"] + card["curve_closure"]["labelled"] == meta["catch_run"]["labelled"]
    seen = set()
    for d in places.values():
        e = d.get("estimate")
        if "points" not in d:
            assert e is None
            continue
        group = "closure" if any(u["closure"] for u in d["scores_used"]) else "scores"
        assert e["group"] == group
        c = card["curve_closure" if group == "closure" else "curve"]
        j = min(d["points"], len(c["rate"]) - 1)
        assert (e["rate"], e["low"], e["high"]) == (c["rate"][j], c["low"][j], c["high"][j])
        # the fitted group it is read from: every place in it gets the rate at its lowest points
        assert [e["min_points"], e["max_points"]] in c["groups"] and e["rate"] == c["rate"][e["min_points"]]
        assert e["min_points"] <= d["points"] <= e["max_points"] or d["points"] > e["max_points"]
        seen.add(group)
    assert seen == {"scores", "closure"}, "the sample shows both groups"


def test_interim_rates_cut_the_label_off_after_90_180_and_270_days():
    mod = load()
    _, _, meta = mod.build(1400, seed=9)
    interim = meta["card"]["interim"]
    assert list(interim) == ["90", "180", "270"]
    assert interim["90"]["all"]["labelled"] <= interim["180"]["all"]["labelled"] <= interim["270"]["all"]["labelled"] <= meta["catch_run"]["labelled"]
    for window in interim.values():
        assert set(window) == {"1", "all"}
        for g in window.values():
            assert g["positives"] <= g["labelled"] and (g["rate"] is None or g["rate"] == round(g["positives"] / g["labelled"], 4))


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
        monitor = out / "monitor_summary.json"
        if mode == "bands":
            assert json.loads(monitor.read_text(encoding="utf-8")) == {"status": "too early", "runs": 0, "alerts": [], "next_window_date": None}
        else:
            assert not monitor.exists(), "a record export has no forward test"
        node = shutil.which("node")
        if node:
            r = subprocess.run([node, str(SITE / "scripts" / "check-export.mjs"), str(out)], capture_output=True, text=True)
            assert r.returncode == 0, r.stdout + r.stderr
