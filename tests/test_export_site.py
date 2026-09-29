"""export_site.py (v3): the data rules, what the site shows, the as-of logic, the rules and bands,
fairness, approval and notices, the prospective gate, archiving and publishing, and end-to-end
builds on an invented county whose output must pass the site's own contract check."""
import csv
import gzip
import json
import re
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

import export_site as es

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "food-dashboard"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def violation(item, tier="minor"):
    status = {"major": "Out of Compliance - Major", "minor": "Out of Compliance - Minor", "grp": "Out of Compliance"}[tier]
    return {"violation": item.split(". ", 1)[-1], "major_violation": "Y" if tier == "major" else "N",
            "status": status, "violation_accela": item}


def note(text):
    return {"violation": text, "major_violation": "N", "status": "Yes", "violation_accela": text}


def inspection(day, kind="Routine", score="95", grade="A", status="Complete", violations=(), iid=None):
    return {"custom_id": "DEH2024-FFPP-000001", "inspection_id": iid or f"{day}-{kind}-{score}-{status}", "type": kind,
            "score": score, "grade": grade, "completed_date": day, "status": status, "violations": list(violations)}


def business(bid, inspections, btype="Restaurant Food Facility", lat="32.7157", lon="-117.1611", status="Permit Renewed",
             name=None, address="1 Main St, SAN DIEGO, CA 92101"):
    for i in inspections:
        i["custom_id"] = f"DEH2024-FFPP-{int(bid):06d}"
    return {"business_id": bid, "name": name or f"Place {bid}", "business_type": btype, "address": address,
            "city": "SAN DIEGO", "zip": "92101-0001", "status": status, "lat": lat, "long": lon,
            "opened_date": "2020-05-01", "inspections": inspections}


def square(lon0, lat0, d=0.05):
    return [[[lon0 - d, lat0 - d], [lon0 + d, lat0 - d], [lon0 + d, lat0 + d], [lon0 - d, lat0 + d], [lon0 - d, lat0 - d]]]


DISTRICTS = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"JUR_NAME": "SAN DIEGO", "DISTRICT": 1}, "geometry": {"type": "Polygon", "coordinates": square(-117.16, 32.72)}},
    {"type": "Feature", "properties": {"JUR_NAME": "SAN DIEGO", "DISTRICT": 2}, "geometry": {"type": "Polygon", "coordinates": square(-117.26, 32.82)}},
    {"type": "Feature", "properties": {"JUR_NAME": "EL CAJON", "DISTRICT": 1}, "geometry": {"type": "Polygon", "coordinates": square(-116.96, 32.79)}},
]}

TEMP = "7. Proper hot & cold holding temperatures"
PESTS = "23. No rodents, insects, birds or animals"


# ── the data rules ────────────────────────────────────────────────────────────────────

def test_visits_that_were_not_inspections_are_dropped():
    st = es.Stats()
    p = es.load_places([business("1", [
        inspection("2024-01-10", status="No Access", score="0", grade=""),
        inspection("2024-02-10", status="Self Closed", score="0", grade=""),
        inspection("2024-03-10", kind="Status Verification", score="0", grade=""),
        inspection("2024-03-11", kind="Status Verification", score="0", grade="", violations=[note("No Valid Permit")]),
        inspection("2024-03-12", kind="Status Verification", status="No Access", score="0", grade="",
                   violations=[violation(PESTS, "major")]),
        inspection("2024-04-10", status="Incomplete"),
        inspection("2024-05-10", score="96"),
    ])], st)[0]
    assert [v["date"] for v in p["visits"]] == ["2024-05-10"], "itemless Self Closed and status checks carry nothing"
    assert sum(st.dropped.values()) == 6 and not st.kept


def test_self_closed_and_status_verification_records_that_carry_information_are_kept():
    """The operator's own closure at a routine that found a major is a closure (health): the days it
    covers are on the record, and the routine a week later is the reopening's re-score, not a routine
    score. A status check citing items is shown and never read; its closure order is a closure."""
    st = es.Stats()
    p = es.load_places([business("1", [
        inspection("2024-04-15", score="95"),
        inspection("2024-10-17", status="Self Closed", score="0", grade="A", violations=[violation(PESTS, "major")]),
        inspection("2024-10-24", kind="Re-inspection", score="0", grade=""),
        inspection("2024-10-24", score="100"),
        inspection("2025-02-03", status="Self Closed", score="0", grade="", violations=[violation(TEMP, "minor")]),
        inspection("2025-03-01", kind="Status Verification", score="0", grade="", violations=[violation(PESTS, "major")]),
        inspection("2025-05-02", kind="Status Verification", score="0", grade="", status="Ordered Closed",
                   violations=[note("No Valid Permit")]),
        _reopen("2025-05-05"),
        inspection("2025-05-05", score="97"),
    ])], st)[0]
    types = {v["date"]: v["type"] for v in p["visits"]}
    assert [v["type"] for v in p["visits"] if v["date"] == "2024-10-24"] == ["reinspection", "followup"]
    assert types["2025-03-01"] == "status_check" and types["2025-02-03"] == "routine"
    self_closed = next(v for v in p["visits"] if v["date"] == "2024-10-17")
    assert (self_closed["status"], self_closed["score"], self_closed["grade"]) == ("Self Closed", None, None), \
        "a Self Closed record carries no score or letter"
    assert (self_closed["closed"], self_closed["closure"], self_closed["closure_order"]) == (True, "health", "health")
    minor_only = next(v for v in p["visits"] if v["date"] == "2025-02-03")
    assert not minor_only["closed"] and minor_only["closure_order"] is None, "Self Closed with no major: shown, no closure"
    shown = es.display_records(p)
    sv_closure = next(r for r in shown if r["date"] == "2025-05-02")
    assert (sv_closure["type"], sv_closure["closed"], sv_closure["closure"], sv_closure["reopened_on"]) == \
        ("status_check", True, "permit", "2025-05-05"), "the status check's closure order, ended by the County's reopening"
    assert sv_closure["county_type"] == "Status Verification" and sv_closure["notes"] == ["No Valid Permit"]
    assert not any(r.get("reopen_without_closure") for r in shown)
    used = es.scores_used(p, "2025-09-01")
    assert [(u["date"], u["score"], u["closure"]) for u in used] == [("2024-04-15", 95, False), ("2024-10-17", 70, True)], \
        "the Self Closed routine reads as 70; the 100 a week later and the reopening-day 97 are re-scores"
    f = es.features_at(p, "2025-09-01")
    assert f["majors"] == 1 and f["theme_vermin"] == 1 and f["health_closures"] == 1, \
        "the Self Closed routine's pest major counts; the status check's is shown, never read"
    assert f["routines"] == 2, "a Self Closed routine is a routine inspection, with a major or not"
    assert st.kept == {"Routine/Self Closed": 2, "Status Verification/Complete": 1, "Status Verification/Ordered Closed": 1}
    assert es.label_at(p, "2024-10-01") == (1, self_closed["_id"]), "the Self Closed routine found a major"


def test_a_reopening_with_no_closure_order_places_the_closure_at_the_unscored_routine_before_it():
    """The County's pattern: a routine marked Complete with no score and a major, then "Approved to
    Reopen" and a re-score. Read as a closure (our reading, marked), counted as 70, and the re-score is
    a re-grade, never a routine score; the pre-pass sees the re-score before the reopening does."""
    st = es.Stats()
    p = es.load_places([business("1", [
        inspection("2025-04-21", score="98"),
        inspection("2026-03-03", score="0", grade="", violations=[violation(PESTS, "major")]),
        _reopen("2026-03-04", iid="z-reopen"),
        inspection("2026-03-04", score="98", iid="a-rescore"),
        inspection("2026-05-19", score="96"),
    ])], st)[0]
    closure = next(v for v in p["visits"] if v["date"] == "2026-03-03")
    assert (closure["closed"], closure["closure"], closure["closure_inferred"], closure["reopened_on"]) == \
        (True, "health", True, "2026-03-04")
    assert [v["type"] for v in p["visits"] if v["date"] == "2026-03-04"] == ["reinspection", "followup"]
    rec = next(r for r in es.display_records(p) if r["date"] == "2026-03-03")
    assert rec["status"] == "Complete" and rec["closure_inferred"] is True, "the County's own status text stays"
    assert [(u["score"], u["county_score"]) for u in es.scores_used(p, "2026-09-29")] == [(98, 98), (70, None), (96, 96)]
    assert es.features_at(p, "2026-09-29")["avg_deficit"] == 100 - int((98 + 70 + 96) / 3 + 0.5) == 12
    assert "closed" in es.flags(es.display_records(p), p["visits"], "2026-09-29")
    assert (st.inferred, st.unplaced) == (1, 0)
    assert all("closure_inferred" not in r for r in es.display_records(p) if r["date"] != "2026-03-03")


def test_a_closure_is_never_placed_on_a_scored_routine_or_far_from_the_reopening():
    """Nothing is guessed: a routine the County scored, a visit more than INFER_DAYS before, or a
    graded routine between leaves the reopening unplaced, and its record says so. Its re-score is
    still a re-grade, unless the place's record starts at the reopening."""
    scored = _place([inspection("2025-09-18", score="90", violations=[violation(TEMP, "major")]),
                     _reopen("2025-09-25"), inspection("2025-09-25", score="97")])
    far = _place([inspection("2025-06-01", score="0", grade="", violations=[violation(VERMIN, "major")]),
                  _reopen("2025-06-20"), inspection("2025-06-20", score="97")])
    between = _place([inspection("2025-06-01", score="0", grade="", violations=[violation(VERMIN, "major")]),
                      inspection("2025-06-03", score="96"), _reopen("2025-06-04")])
    for p in (scored, far, between):
        recs = es.display_records(p)
        assert not any(r["closed"] for r in recs)
        assert [r["date"] for r in recs if r.get("reopen_without_closure")] == \
            [r["date"] for r in recs if r["status"] == "Approved to Reopen"]
    assert [v["type"] for v in scored["visits"]] == ["routine", "reinspection", "followup"], "the re-score is a re-grade"
    assert scored["visits"][0]["score"] == 90, "the County's score stands"
    first = _place([_reopen("2026-01-28"), inspection("2026-01-28", score="94")])
    assert [v["type"] for v in first["visits"]] == ["reinspection", "routine"], \
        "a record that starts at a reopening: its routine is the first inspection on it"
    assert es.display_records(first)[0]["reopen_without_closure"] is True


def test_a_reopening_belongs_to_a_recent_closure_a_graded_routine_ended():
    """Closed, graded again while still closed, then the County's reopening: it is that closure's
    reopening, not a stray one; and a second reopening of a closure already reopened is not flagged."""
    p = _place([_closed("2026-04-28"), inspection("2026-05-07", score="96"), _reopen("2026-05-20")])
    recs = es.display_records(p)
    ep = next(r for r in recs if r["closed"])
    assert (ep["reopened"], ep["reopened_on"]) == (True, "2026-05-20")
    assert not any(r.get("reopen_without_closure") for r in recs)
    twice = _place([_closed("2025-06-03"), _reopen("2025-06-07"), _reopen("2025-06-08"), inspection("2025-06-08", score="98")])
    recs = es.display_records(twice)
    assert [r["reopened_on"] for r in recs if r["closed"]] == ["2025-06-07"]
    assert not any(r.get("reopen_without_closure") for r in recs)
    later = _place([_closed("2025-01-10"), _reopen("2025-01-12"), inspection("2025-01-19", score="0", grade="",
                                                                           violations=[violation(VERMIN, "major")]),
                    _reopen("2025-01-20")])
    assert [(r["date"], r["reopened_on"], r.get("closure_inferred", False)) for r in es.display_records(later) if r["closed"]] == \
        [("2025-01-10", "2025-01-12", False), ("2025-01-19", "2025-01-20", True)], "a new closure after the first reopened"


def test_an_open_closure_is_named_beside_the_last_letter():
    """The County posts no card while it has a place closed: a closure with no reopening and no graded
    routine after it is named on the grade, with the ungraded records after it."""
    p = _place([inspection("2026-05-27", score="96"), _closed("2026-08-21"),
                inspection("2026-09-09", kind="Re-inspection", score="0", grade="")])
    p["district"] = 1
    feat, detail = es.entry(p)
    g = feat["properties"]["grade"]
    assert (g["grade"], g["date"]) == ("A", "2026-05-27"), "the letter stays the last one on the record"
    assert g["open_closure"] == {"date": "2026-08-21", "reason": "health", "later_ungraded": ["2026-09-09"],
                                 "status": "Ordered Closed"}, "with the County's status text on the record that started it"
    assert detail["grade"] == g
    reopened = _place([inspection("2026-05-27", score="96"), _closed("2026-08-21"), _reopen("2026-08-23")])
    regraded = _place([inspection("2026-05-27", score="96"), _closed("2026-08-21"), inspection("2026-09-01", score="95")])
    for q in (reopened, regraded):
        assert es.posted_grade(es.display_records(q), q["visits"])["open_closure"] is None
    self_closed = _place([inspection("2026-05-27", score="96"),
                          inspection("2026-08-21", status="Self Closed", score="0", grade="", violations=[violation(VERMIN, "major")])])
    oc = es.posted_grade(es.display_records(self_closed), self_closed["visits"])["open_closure"]
    assert (oc["date"], oc["status"]) == ("2026-08-21", "Self Closed"), "the operator's own closure is never called a County order"


def test_the_countys_notes_and_inspection_type_are_shown_verbatim():
    p = _place([inspection("2025-06-01", score="93", violations=[violation(TEMP, "minor"), note("Impoundment")]),
                inspection("2025-07-01", kind="Environmental", score="0", grade="", violations=[note("No Valid Permit")]),
                inspection("2025-07-01", kind="Site Investigation", score="0", grade="", violations=[violation(PESTS, "major")])])
    p["district"] = 1
    _, detail = es.entry(p)
    got = [(i["county_type"], i["type"], i["notes"]) for i in detail["inspections"]]
    assert got == [("Routine", "routine", ["Impoundment"]), ("Environmental", "complaint", ["No Valid Permit"]),
                   ("Site Investigation", "complaint", [])], "each record keeps its own type and notes, as published"
    assert json.loads(json.dumps(detail))["inspections"][0]["notes"] == ["Impoundment"]


def test_theme_counts_count_every_item_before_the_cap_and_the_cap_drops_the_oldest():
    grp = "45. Floor, walls and ceilings - built, maintained, clean"
    visits = [inspection(f"2025-{m:02d}-10", score="80", grade="B",
                         violations=[violation(TEMP, "major")] + [violation(grp, "grp")] * 12) for m in range(1, 8)]
    p = _place(visits)
    p["district"] = 1
    _, d = es.entry(p)
    assert d["violations_total"] == 7 * 13 and len(d["violations"]) == es.MAX_VIOLATIONS
    assert d["theme_counts"]["temperature"] == {"major": 7, "minor": 0, "grp": 0, "complaint": 0, "latest": "2025-07-10"}
    assert d["theme_counts"]["grp_facility"]["grp"] == 84, "counted before the 60-item cap"
    kept = [v["date"] for v in d["violations"] if v["severity"] == "grp"]
    assert max(kept) == "2025-07-10" and min(kept) > "2025-01-10", "the cap drops the oldest items, not the newest"
    assert [v["severity"] for v in d["violations"][:7]] == ["major"] * 7
    small = _place([inspection("2025-01-10", violations=[violation(TEMP, "minor")]),
                    inspection("2025-02-10", kind="Site Investigation", score="0", grade="", violations=[violation(PESTS, "major")])])
    small["district"] = 1
    _, d = es.entry(small)
    assert d["violations_total"] == len(d["violations"]) == 2 and d["theme_counts"]["vermin"]["complaint"] == 1


def test_the_fingerprint_county_exercises_the_new_closure_rules(monkeypatch):
    places = es.load_places(es._fingerprint_county())
    recs = {p["id"]: es.display_records(p) for p in places}
    assert any(r["status"] == "Self Closed" and r["closed"] for rs in recs.values() for r in rs)
    assert any(r.get("closure_inferred") for rs in recs.values() for r in rs)
    assert any(r.get("reopen_without_closure") for rs in recs.values() for r in rs)
    assert any(r["type"] == "status_check" for rs in recs.values() for r in rs)
    base = es.behaviour_fingerprint()
    monkeypatch.setattr(es, "INFER_DAYS", 0)
    assert es.behaviour_fingerprint() != base, "the reading of a reopening changes what a point means"
    monkeypatch.undo()
    monkeypatch.setattr(es, "ITEM_STATUS", set())
    assert es.behaviour_fingerprint() != base, "so does keeping the Self Closed closure"


def test_followups_closures_and_reopening():
    p = es.load_places([business("1", [
        inspection("2024-01-10", score="84", grade="B", violations=[violation(TEMP, "major")]),
        inspection("2024-01-16", score="97", grade="A"),                                            # re-grade
        inspection("2024-06-01", score="0", grade="", status="Ordered Closed", violations=[violation(PESTS, "major")]),
        inspection("2024-06-02", kind="Re-inspection", score="0", grade="", status="Ordered Closed"),  # still closed
        inspection("2024-06-03", kind="Re-inspection", score="0", grade="", status="Approved to Reopen"),
        inspection("2024-06-05", score="98", grade="A"),                                            # reopening coded routine
        inspection("2024-08-01", score="0", grade="", status="Ordered Closed", violations=[note("No Valid Permit")]),
        inspection("2024-12-01", score="92", grade="A"),
    ])])[0]
    assert [v["type"] for v in p["visits"]] == ["routine", "followup", "routine", "reinspection", "reinspection", "followup",
                                                "routine", "routine"], "122 days after the permit closure is a routine"
    closed = [(v["date"], v["closure"], v["reopened"]) for v in p["visits"] if v["closed"]]
    assert closed == [("2024-06-01", "health", True), ("2024-08-01", "permit", False)]
    assert es.label_at(p, "2024-01-11") == (1, p["visits"][2]["_id"]), "the label skips the re-grade"


def test_same_day_records_are_one_visit_for_the_model_but_shown_as_published():
    st = es.Stats()
    p = es.load_places([business("1", [
        inspection("2024-03-01", score="97", grade="A", violations=[violation("14. Food contact surfaces clean & sanitized")], iid="a"),
        inspection("2024-03-01", score="82", grade="B", violations=[violation(TEMP, "major")], iid="b"),
    ])], st)[0]
    assert len(p["visits"]) == 1 and st.merged == 1
    assert (p["visits"][0]["score"], p["visits"][0]["major"]) == (82, 1)
    shown = es.display_records(p)
    assert [(r["grade"], r["score"], r["status"]) for r in shown] == [("A", 97, "Complete"), ("B", 82, "Complete")]


def test_tiers_notes_scores_and_grades_are_the_countys():
    p = es.load_places([business("1", [
        inspection("2024-01-10", score="0", grade="", status="Ordered Closed"),
        inspection("2024-02-10", score="100", grade=""),
        inspection("2024-09-01", score="88", grade="B", violations=[
            violation(PESTS, "major"), violation("6. Adequate handwashing facilities supplied & accessible", "minor"),
            violation("45. Floor, walls and ceilings - built, maintained, clean", "grp"), note("Impoundment")]),
    ], btype="Pre-Packaged Retail Market")])[0]
    assert [v["score"] for v in p["visits"]] == [None, 100, 88]
    assert [v["grade"] for v in p["visits"]] == [None, None, "B"], "never derived from a score"
    v = p["visits"][2]
    assert (v["major"], v["minor"], v["grp"]) == (1, 1, 1), "the impound note is not a violation"


def test_every_item_text_in_the_countys_data_maps_to_its_reviewed_theme():
    fixture = json.loads((FIXTURES / "item_themes.json").read_text(encoding="utf-8"))
    assert len(fixture) >= 100
    assert {t: es.theme_of(t) for t in fixture if es.theme_of(t) != fixture[t]} == {}


def test_themes_are_the_countys_report_sections_on_both_forms():
    """The mobile-unit form numbers items differently (22 is pests there, sewage on the fixed form):
    the theme follows the item, not its number."""
    th = es.theme_of
    assert th("22. No rodents, insects, birds or animals") == "vermin"          # mobile 22
    assert th("22. Sewage & wastewater properly disposed") == "sewage"          # fixed 22
    assert th("21. No waste water discharge to the ground; sewage system and connections") == "sewage"
    assert th("19. Potable hot and cold water available") == "water"            # mobile 19
    assert th("19. Consumer advisory provided for raw or undercooked foods") == "advisory"
    assert th("5. Hands clean & properly washed; gloves used properly") == "hands"
    assert th("6. Adequate handwashing facilities supplied & accessible") == "handsink"
    assert th("20. Toilet and handwashing sink facility readily available") == "handsink"
    assert th("14. Food contact surfaces clean & sanitized") == "sanitizing"
    assert th("34. Warewashing facilities -installed, maintained, used; test strips") == "grp_equipment"
    assert th("40. Wiping cloths -properly used, stored") == "grp_equipment"
    assert th("41. Plumbing -proper backflow devices") == "grp_facility"
    assert th("38. Plumbing - proper backflow devices / water tank design and adequate capacity") == "grp_facility"
    assert th("44. Premises, personal / cleaning items, vermin-proofing") == "grp_facility"
    assert th("1a. Food Safety Certification & Exp. Date") == "knowledge"
    assert th("20. Licensed health care facilities / public & private schools - prohibited foods not offered") == "hsp"
    assert th("16. Compliance with shell stock tags, condition, display") == "supplier"
    assert th("13. Food in good condition, safe & unadulterated") == "condition"
    assert th("18. Compliance with:") == "process"
    assert th("39. Compliance with fire safety requirements - first aid kit") == "grp_other"
    assert th("47. Grade card, signs, last inspection report available") == "grp_signs"
    assert es.RISK_THEMES == ("health", "hands", "handsink", "temperature", "condition", "sanitizing", "supplier", "process",
                              "hsp", "water", "sewage", "vermin")
    assert not any(t.startswith("grp_") for t in es.RISK_THEMES) and set(es.RISK_THEMES) <= set(es.THEMES)


def test_business_kinds():
    assert es.BAND_KINDS <= es.PUBLIC_KINDS <= set(es.KINDS.values())
    for off in ("Mobile Food Facility Prep Unit", "School Processing Food Facility", "Satellite Food Service Operation"):
        assert es.KINDS[off] not in es.PUBLIC_KINDS
    for home in ("Class A Cottage Food Operation", "Microenterprise Home Kitchen", "Vending Machine"):
        assert home in es.EXCLUDED_TYPES and home not in es.KINDS
    assert not set(es.KINDS) & es.EXCLUDED_TYPES


def test_districts_come_from_the_city_only():
    lookup = es.district_lookup(DISTRICTS)
    assert lookup(-117.16, 32.72) == 1 and lookup(-117.26, 32.82) == 2
    assert lookup(-116.96, 32.79) is None and lookup(None, None) is None


# ── what the site shows ───────────────────────────────────────────────────────────────

def test_posted_grade_names_only_the_grade_a_regrade_replaced():
    recs = lambda rows: [{"date": d, "type": t, "grade": g, "score": s} for d, t, g, s in rows]
    g = es.posted_grade(recs([("2026-05-20", "routine", "B", 81), ("2026-05-28", "followup", "A", 96)]))
    assert (g["grade"], g["replaced"]["grade"]) == ("A", "B")
    g = es.posted_grade(recs([("2026-05-20", "routine", "B", 81), ("2026-05-21", "followup", "A", 96),
                              ("2026-07-29", "followup", "A", 90)]))
    assert g["score"] == 90 and g["replaced"] is None, "a reopening after a closure did not replace the B"
    assert es.posted_grade(recs([("2026-01-01", "routine", None, 100)])) is None


def test_entry_splits_index_and_detail_and_shows_complaint_findings():
    p = es.load_places([business("1", [
        inspection("2025-06-01", score="93", grade="A", violations=[violation(TEMP, "major")]),
        inspection("2025-07-01", kind="Site Investigation", score="0", grade="", violations=[violation(PESTS, "major")]),
        inspection("2025-08-01", score="96", grade="A"),
    ])])[0]
    p["district"] = 1
    feat, detail = es.entry(p, {"band": "1", "points": 12, "score_card": [], "band_stability": 0.9})
    props = feat["properties"]
    assert set(props) == {"facility_id", "name", "address", "facility_type", "council_district", "last_visit", "grade", "flags",
                          "band", "points"}
    assert "score_card" in detail and "band_stability" in detail and "inspections" in detail
    assert {"major", "temperature", "vermin"} <= set(props["flags"])
    visits = {v["theme"]: v["visit"] for v in detail["violations"]}
    assert visits["vermin"] == "complaint", "findings at complaint visits are shown, labelled"
    assert all("status" in r for r in detail["inspections"])


# ── as of a date ──────────────────────────────────────────────────────────────────────

def record_place():
    p = es.load_places([business("1", [
        inspection("2023-06-01", score="99"),
        inspection("2023-09-01", score="92", violations=[violation(TEMP, "major"), violation("33. Nonfood contact surfaces clean", "grp")]),
        inspection("2023-09-12", kind="Re-inspection", score="0", grade=""),
        inspection("2024-01-15", kind="Site Investigation", score="0", grade="", violations=[violation(PESTS, "major")]),
        inspection("2024-01-20", kind="Re-inspection", score="0", grade=""),          # prompted by the complaint
        inspection("2024-03-01", score="86", grade="B", violations=[violation(TEMP, "major")]),
        inspection("2024-03-08", score="98", grade="A"),                                # re-grade
        inspection("2024-05-01", score="0", grade="", status="Ordered Closed", violations=[violation(PESTS, "major")]),
        inspection("2024-06-15", score="95", grade="A"),
        inspection("2025-03-01", score="93", grade="A"),
    ])])[0]
    p["district"] = 1
    return p


def test_features_read_two_years_of_scores_and_count_a_closure_as_a_failing_score():
    f = es.features_at(record_place(), "2024-08-01")
    # routines in the two-year score window: 2023-06-01 (99), 2023-09-01 (92), 2024-03-01 (86),
    # 2024-05-01 (closure -> 70), 2024-06-15 (95); the 2024-03-08 re-grade is not a routine score
    assert f["avg_score"] == pytest.approx((99 + 92 + 86 + 95) / 4), "real scores only"
    assert f["avg_deficit"] == 100 - round((99 + 92 + 86 + es.CLOSURE_SCORE + 95) / 5)
    assert f["last_deficit"] == 5
    assert f["reinspections"] == 1, "the reinspection after the complaint visit does not count"
    assert f["theme_vermin"] == 1, "the closure visit's pests count; the complaint visit's do not"
    assert f["health_closures"] == 1 and f["no_score"] == 0.0
    assert es.eligible(f)
    assert es.features_at(record_place(), "2023-06-01") is None


def test_labels_and_candidates():
    p = record_place()
    assert es.label_at(p, "2024-03-02")[0] == 1, "skips the re-grade; the closure routine found a major"
    assert es.label_at(p, "2025-03-02") == (None, None)
    assert es.active_at(p, "2025-04-01", scope="city_bands")
    p["status"] = "Expired"
    assert not es.active_at(p, "2025-04-01", scope="city_bands", forward=True)
    p["status"], p["district"] = "Permit Renewed", None
    assert not es.active_at(p, "2025-04-01", scope="city") and es.active_at(p, "2025-04-01", scope="train")


def test_month_starts_and_event_weights():
    assert es.month_starts(date(2024, 1, 15), date(2024, 4, 1)) == ["2024-02-01", "2024-03-01", "2024-04-01"]
    assert list(es.event_weights([("a", "x"), ("a", "x"), ("b", "y"), ("c", None)])) == [0.5, 0.5, 1.0, 1.0]


# ── the rules ─────────────────────────────────────────────────────────────────────────

def test_the_average_rule_and_a_fitted_count_score():
    rng = np.random.default_rng(0)
    n = 8000
    F = np.zeros((n, len(es.COUNT_FEATURES)))
    avg = rng.integers(0, 20, n)
    temp = rng.poisson(0.5, n)
    F[:, es.COUNT_FEATURES.index("avg_deficit")] = avg
    F[:, es.COUNT_FEATURES.index("theme_temperature")] = temp
    F[:, es.COUNT_FEATURES.index("grp")] = rng.poisson(2, n)          # noise
    y = (rng.random(n) < 1 / (1 + np.exp(-(-2.5 + 0.12 * avg + 0.5 * temp)))).astype(float)
    assert list(es.AVERAGE_RULE.score(F)[:5]) == list(avg[:5].astype(float))
    r = es.fit_count(F, y, np.ones(n))
    assert "avg_deficit" in r.features and "theme_temperature" in r.features
    assert r.weights[r.features.index("avg_deficit")] >= 1, "one point below 100 is the unit"
    assert all(isinstance(w, int) and 1 <= w <= es.MAX_WEIGHT for w in r.weights)
    assert es.auc(y, r.score(F)) > es.auc(y, es.AVERAGE_RULE.score(F))


def test_worksheet_rows_multiply_and_sum():
    rule = es.Score("count score", ["avg_deficit", "theme_temperature"], [1, 3])
    f = {c: 0.0 for c in es.COUNT_FEATURES}
    f.update(avg_deficit=8.0, theme_temperature=2.0)
    ws = es.worksheet(rule, f)
    assert [(r["item"], r["value"], r["points"], r["met"]) for r in ws] == [("avg_deficit", 8.0, 8.0, True), ("theme_temperature", 2.0, 6.0, True)]
    F = np.array([[f[c] for c in es.COUNT_FEATURES]])
    assert rule.score(F)[0] == sum(r["points"] for r in ws) == 14


def test_bands_never_split_a_tie():
    pts = np.array([20] * 30 + [15] * 60 + [10] * 200 + [5] * 700, dtype=float)
    elig = np.ones(len(pts), bool)
    bands = es.assign_bands(pts, elig, es.band_thresholds(pts))
    for v in np.unique(pts):
        assert len({b for b, p in zip(bands, pts) if p == v}) == 1, "a tie is never split"


def _origins(pts, rates, n=3, seed=0, flat=None):
    """Invented backtest origins: each place's outcome drawn at its points' rate (or one flat rate)."""
    rng = np.random.default_rng(seed)
    p = np.array([flat if flat is not None else rates[v] for v in pts])
    ones = np.ones(len(pts), bool)
    return [(pts, (rng.random(len(pts)) < p).astype(float), ones, ones) for _ in range(n)]


def test_a_real_gradient_keeps_its_bands_at_every_origin():
    pts = np.array([20] * 80 + [15] * 160 + [10] * 400 + [0] * 3000, dtype=float)
    cuts = es.band_thresholds(pts)
    kept = es.validate_bands(cuts, _origins(pts, {20: 0.70, 15: 0.45, 10: 0.30, 0: 0.10}))
    assert kept == cuts, "clear, repeated differences survive"
    rows, rest = es.band_rows(es.assign_bands(pts, np.ones(len(pts), bool), kept), pts, *_origins(pts, {20: 0.7, 15: 0.45, 10: 0.3, 0: 0.1}, n=1)[0][1:])
    assert rest["places"] + sum(r["places"] for r in rows) == len(pts)


def test_a_split_that_reverses_at_one_origin_is_merged():
    pts = np.array([20] * 300 + [10] * 300 + [0] * 3000, dtype=float)
    ones = np.ones(len(pts), bool)
    cuts = [20.0, 10.0]
    def outcomes(r20, r10, seed):
        rng = np.random.default_rng(seed)
        p = np.where(pts == 20, r20, np.where(pts == 10, r10, 0.1))
        return (pts, (rng.random(len(pts)) < p).astype(float), ones, ones)
    kept = es.validate_bands(cuts, [outcomes(0.5, 0.35, 1), outcomes(0.5, 0.35, 2), outcomes(0.30, 0.40, 3)])
    assert kept == [10.0], "bands 1 and 2 swap order at one origin: they are one band"


def test_under_a_flat_rate_bands_are_almost_never_invented():
    """Gelman's check: with no real gradient, the old 'rates in order at one origin' rule returned more
    than one band about two times in three. The rule now must do so (or keep any band at all) rarely."""
    pts = np.array([20] * 40 + [15] * 80 + [10] * 300 + [5] * 600 + [0] * 1500, dtype=float)
    cuts = es.band_thresholds(pts)
    trials = 150
    kept = [es.validate_bands(cuts, _origins(pts, None, seed=t, flat=0.25)) for t in range(trials)]
    assert sum(len(k) > 1 for k in kept) / trials <= 0.02
    assert sum(len(k) >= 1 for k in kept) / trials <= 0.05


def test_the_risk_curve_rises_with_points_and_brackets_its_estimate():
    rng = np.random.default_rng(4)
    pts = rng.integers(0, 25, 3000)
    pos = (rng.random(3000) < 0.05 + 0.02 * pts).astype(float)
    ones = np.ones(3000, bool)
    cl = np.arange(3000)
    c = es.risk_curve(pts, pos, ones, ones, cl, n_boot=60)
    r = np.array(c["rate"])
    assert np.all(np.diff(r) >= -1e-9) and len(r) == pts.max() + 1
    assert all(lo <= m + 1e-9 <= hi + 2e-9 for lo, m, hi in zip(c["low"], c["rate"], c["high"]))
    assert sum(b["labelled"] for b in c["bins"]) == 3000 and c["labelled"] == 3000
    e = es.estimate(c, 99)                          # beyond the backtest's largest: read at the largest
    top = c["groups"][-1]
    assert e == {"rate": c["rate"][-1], "low": c["low"][-1], "high": c["high"][-1], "min_points": top[0], "max_points": top[1]}


def test_each_fitted_group_carries_its_counts_and_an_estimate_names_the_group_it_is_read_from():
    """Every place in a fitted group is given the group's rate, so the estimate names the group, and the
    curve says how many labelled places (and how many with a major) each group pools."""
    pts = np.array([0] * 250 + [2] * 120 + [3] * 110 + [9] * 90 + [12] * 130)
    pos = (np.random.default_rng(3).random(len(pts)) < 0.05 + 0.03 * pts).astype(float)
    ones = np.ones(len(pts), bool)
    c = es.risk_curve(pts, pos, ones, ones, np.arange(len(pts)), n_boot=20)
    assert [[g["min_points"], g["max_points"]] for g in c["group_counts"]] == c["groups"]
    assert sum(g["labelled"] for g in c["group_counts"]) == c["labelled"] == len(pts)
    assert sum(g["positives"] for g in c["group_counts"]) == c["positives"]
    for g in c["group_counts"]:
        inside = (pts >= g["min_points"]) & (pts <= g["max_points"])
        assert (g["labelled"], g["positives"]) == (int(inside.sum()), int(pos[inside].sum()))
    for p in range(0, 20):
        e = es.estimate(c, p)
        lo, hi = e["min_points"], e["max_points"]
        assert [lo, hi] in c["groups"] and e["rate"] == c["rate"][lo], f"{p} points read the rate of the group {lo} to {hi}"
    assert es.curve_group(c, 5) == tuple(next(g for g in c["groups"] if g[0] <= 3 <= g[1])), \
        "a value no backtest place had reads the group below"
    assert es.curve_group({"rate": [0.1]}, 3) is None and "min_points" not in es.estimate({"rate": [0.1], "low": [0.1], "high": [0.1]}, 3)


def test_naming_by_cost_ratio():
    rows = [{"band": "1", "interval": (0.45, 0.62)}, {"band": "2", "interval": (0.28, 0.40)}]
    assert es.named_bands(rows, 0.5) == ["1"] and es.named_bands(rows, 0.25) == ["1", "2"] and es.named_bands(rows, 1) == []


def test_the_rule_is_the_sparsest_within_epsilon():
    val = lambda a, c, best: {"as_of": "x", "models": {"average score": {"auc_eligible": a}, "count score": {"auc_eligible": c},
                                                       "logistic": {"auc_eligible": best}}}
    chosen, sel = es.select_rule([val(0.695, 0.70, 0.70), val(0.69, 0.70, 0.699)])
    assert chosen == "average score" and sel["within_epsilon"]
    chosen, sel = es.select_rule([val(0.68, 0.698, 0.70), val(0.69, 0.70, 0.705)])
    assert chosen == "count score" and sel["within_epsilon"]
    chosen, sel = es.select_rule([val(0.60, 0.62, 0.70), val(0.60, 0.62, 0.70)])
    assert chosen == "count score" and not sel["within_epsilon"]
    # Nothing matches the black boxes, and the denser rule is ahead by less than EPSILON: the sparser
    # rule ships (a denser rule is never chosen on a difference inside the declared tolerance).
    chosen, sel = es.select_rule([val(0.696, 0.703, 0.72), val(0.692, 0.690, 0.71)])
    assert chosen == "average score" and not sel["within_epsilon"]


# ── fairness, approval, notices ───────────────────────────────────────────────────────

def test_district_fairness_blocks_on_the_point_estimate():
    fair = {"4": {"named": 22, "false_share_ratio": 2.28, "fpr_ratio": 2.18, "interval": [1.1, 3.2]},
            "3": {"named": 30, "false_share_ratio": 0.9, "fpr_ratio": 0.9, "interval": [0.6, 1.3]},
            "7": {"named": 2, "false_share_ratio": 3.0, "fpr_ratio": 3.0, "interval": [0.0, 5.0]}}
    probs = "\n".join(es.fairness_problems(fair))
    assert "district 4" in probs and "district 3" not in probs and "district 7" not in probs


def good_approval(meta, sha):
    return {"approver": "A B", "date": "2026-10-01", "run": meta["run"], "facilities_sha256": sha,
            "contact": "owners@example.org", "reason": "because", "insurance": "policy 1", "cost_ratio": 1,
            "responsible_adult": {"name": "C D", "contact": "cd@example.org", "relationship": "teacher advisor",
                                  "attests_18_or_older": True},
            "legal_review": {"reviewer": "E", "organization": "F", "date": "2026-09-01", "scope": "all"},
            "county_informed": {"date": "2026-08-01", "person": "G", "method": "email", "what_was_shown": "report",
                                "response": "no objection"}}


def test_the_approval_binds_one_run_and_one_file():
    meta = {"run": "forward_2026-09-20", "generated": "2026-10-02"}
    a = good_approval(meta, "abc")
    assert es.check_approval(a, "bands", meta, "abc") == []
    probs = lambda **over: "\n".join(es.check_approval({**a, **over}, "bands", meta, "abc"))
    assert "not forward_2026-09-20" in probs(run="forward_2026-08-01")
    assert "does not match" in es.check_approval(a, "bands", meta, "other")[0]
    assert "independent_reviewer" in probs(cost_ratio=0.5)
    assert probs(cost_ratio=0.5, independent_reviewer={"name": "X", "affiliation": "Y", "date": "2026-09-30"}) == ""
    assert "cannot be waived" in probs(skip_prospective_reason="soon")
    assert "30 days" in probs(county_informed={**a["county_informed"], "date": "2026-09-25"})
    assert "legal_review" in probs(legal_review={})
    assert "not an email" in probs(contact="nobody")
    assert "not an author" in probs(responsible_adult={**a["responsible_adult"], "name": "Chenhao Zhang"})
    assert "not an author" in probs(responsible_adult={**a["responsible_adult"], "relationship": "author"})
    assert "attests_18_or_older" in probs(responsible_adult={**a["responsible_adult"], "attests_18_or_older": False})
    assert es.check_approval(None, "bands", meta, "abc")
    example = json.loads((ROOT / "docs" / "PUBLISH_APPROVAL.example.json").read_text(encoding="utf-8"))
    assert es.check_approval(example, "bands", meta, "abc"), "the template, unedited, approves nothing"


def test_notices_must_be_sent_early_enough(tmp_path):
    ids = ["DEH-1", "DEH-2"]
    assert "no notice log" in es.notice_problems(ids, "run1", date(2026, 10, 1), tmp_path)[0]
    with open(tmp_path / "run1.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["facility_id", "date_sent", "method"])
        w.writerow(["DEH-1", "2026-09-01", "mail"])
        w.writerow(["DEH-2", "2026-09-25", "mail"])
    assert "not told" in es.notice_problems(ids, "run1", date(2026, 10, 1), tmp_path)[0]
    assert es.notice_problems(ids, "run1", date(2026, 10, 15), tmp_path) == []
    assert es.notice_problems([], "run1", date(2026, 10, 1), tmp_path) == []


# ── end to end, on an invented county ─────────────────────────────────────────────────

def invented_county(n=420, seed=3):
    rng = np.random.default_rng(seed)
    raw = []
    kinds = ["Restaurant Food Facility", "Restaurant Food Facility", "Retail Market with Deli", "Low Risk Food Facility",
             "Mobile Food Facility Prep Unit"]
    for i in range(n):
        risk = rng.beta(2, 6)
        kind = kinds[i % len(kinds)]
        city = i % 6 != 0
        lon, lat = (-117.16 + rng.uniform(-0.04, 0.04), 32.72 + rng.uniform(-0.04, 0.04)) if city else (-116.96, 32.79)
        d, visits = date(2023, 1, 5) + timedelta(days=int(rng.integers(0, 150))), []
        while d < date(2026, 9, 10):
            majors = int(rng.random() < risk)
            items = [violation(TEMP, "major")] * majors
            if rng.random() < risk:
                items.append(violation("14. Food contact surfaces clean & sanitized", "minor"))
            items += [violation("45. Floor, walls and ceilings - built, maintained, clean", "grp")] * int(rng.integers(0, 4))
            score = 100 - 4 * majors - 2 * sum(v["status"].endswith("Minor") for v in items) - sum(v["status"] == "Out of Compliance" for v in items)
            visits.append(inspection(d.isoformat(), score=str(score), grade="A" if score >= 90 else "B", violations=items))
            if majors:
                visits.append(inspection((d + timedelta(days=10)).isoformat(), kind="Re-inspection", score="0", grade=""))
            d += timedelta(days=int(rng.integers(120, 260)))
        raw.append(business(str(i), visits, btype=kind, lat=str(lat), lon=str(lon), name=f"Invented {i}",
                            address=f"{i} Test St, SAN DIEGO, CA 92101"))
    return raw


PULL = {"started": "2026-09-20", "finished": "2026-09-21", "complete": True}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    # A real export must carry the sha256 of the pull it was built from. Hand the build an invented
    # pull file, so the test does not depend on a data/ folder that only exists on the author's machine.
    raw = invented_county()
    pull = tmp_path_factory.mktemp("pull") / "sd_businesses.json"
    pull.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(es, "RAW", pull)
        return es.build(raw, DISTRICTS, pull=PULL, approval=None, today=date(2026, 9, 22), refits=2, log=lambda *_: None)


def test_build_lists_every_county_place_with_scores_where_eligible(built):
    fc, details, meta, extra = built
    props = [f["properties"] for f in fc["features"]]
    # City places carry their council district; the rest of the county has none (the site's area toggle)
    assert props and all(p["facility_type"] in es.PUBLIC_KINDS and p["council_district"] in (1, 2, None) for p in props)
    assert any(p["council_district"] in (1, 2) for p in props)
    assert {p["facility_type"] for p in props} >= {"restaurant", "market"}
    assert all("rank" not in p and "percentile" not in p for p in props)
    for p in props:
        d = details[p["facility_id"]]
        if "points" in p:
            assert p["facility_type"] == "restaurant"
            assert sum(r["points"] for r in d["score_card"]) == p["points"]
        else:
            assert "band" not in p
    banded = [p for p in props if "band" in p]
    assert banded, "some restaurants are in a band"
    by_points = {}
    for p in banded:
        by_points.setdefault(p["points"], set()).add(p["band"])
    assert all(len(b) == 1 for b in by_points.values()), "no tie straddles a band edge"
    assert meta["mode"] == "bands"
    assert meta["expires"] == (date.fromisoformat(meta["inspections_through"]) + timedelta(days=es.FRESH_DAYS)).isoformat()
    assert meta["selection"]["chosen"] in es.PUBLISHABLE
    assert {b["band"] for b in meta["card"]["bands"]} == {p["band"] for p in banded}


def test_record_build():
    fc, details, meta, _ = es.build_record(invented_county(), DISTRICTS, pull=PULL, today=date(2026, 9, 22), log=lambda *_: None)
    assert meta["mode"] == "record" and "card" not in meta
    assert fc["features"] and all("band" not in f["properties"] and "points" not in f["properties"] for f in fc["features"])
    assert len(details) == len(fc["features"])


def node_check(dirpath, review):
    return subprocess.run(["node", str(SITE / "scripts" / "check-export.mjs"), str(dirpath)] + (["--review"] if review else []),
                          capture_output=True, text=True)


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_the_review_export_passes_the_sites_contract_check(built, tmp_path):
    fc, details, meta, _ = built
    es.write_export(tmp_path, fc, details, meta)
    res = node_check(tmp_path, review=True)
    assert res.returncode == 0, res.stdout + res.stderr
    assert node_check(tmp_path, review=False).returncode != 0, "an unapproved real export never passes without --review"


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_publish_stages_named_bands_with_a_publication_stamp(built, tmp_path, monkeypatch):
    fc, details, meta, _ = built
    meta = {**meta, "named_bands": ["1"], "contact": "owners@example.org",
            "operator": {"name": "C D", "contact": "cd@example.org"}}
    # a band-1 place outside the City (the staff export lists the county): publishing never names it
    city = next(f for f in fc["features"] if f["properties"].get("band") == "1")
    county = json.loads(json.dumps(city))
    county["properties"].update(facility_id="DEH2099-FFPP-000001", council_district=None)
    fc = {**fc, "features": fc["features"] + [county]}
    details = {**details, "DEH2099-FFPP-000001": {**details[city["properties"]["facility_id"]],
                                                   "facility_id": "DEH2099-FFPP-000001", "council_district": None}}
    approval = tmp_path / "approval.json"
    approval.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(es, "SITE_DATA", tmp_path / "public_data")
    problems = es.publish(tmp_path / "out", fc, details, meta, approval_path=approval, today=date(2026, 9, 22))
    assert problems == [], problems
    shipped = json.loads((tmp_path / "public_data" / "meta.json").read_text(encoding="utf-8"))
    idx = json.loads((tmp_path / "public_data" / "facilities.geojson").read_text(encoding="utf-8"))
    assert shipped["publication"]["facilities_sha256"] == es.sha256_file(tmp_path / "public_data" / "facilities.geojson")
    assert idx["features"] and all(f["properties"]["band"] == "1" for f in idx["features"])
    assert all(f["properties"]["council_district"] is not None for f in idx["features"])
    assert not (tmp_path / "public_data" / "place" / "DEH2099-FFPP-000001.json").exists()


def _as_of(meta, run_day):
    """The same archived list, as if drawn up on `run_day` (to test the monitor's windows)."""
    return {**meta, "run": f"forward_{run_day}-{meta['run'][-8:]}"}


def test_archive_is_write_once_and_registration_is_one_per_rule_version(built, tmp_path):
    fc, details, meta, extra = built
    d, new = es.archive(tmp_path, meta, extra["ranking"])
    assert new and (d / "manifest.json").exists()
    assert es.archive(tmp_path, meta, extra["ranking"])[1] is False, "never overwritten"
    with gzip.open(d / "ranking.csv.gz", "rt", encoding="utf-8") as fh:
        header = fh.readline().strip().split(",")
    assert {"facility_id", "business_id", "points", "band", "average_rule", "persistence", "district", "closure_2y"} <= set(header)
    day = es.run_date(meta["run"])
    v1 = {**meta, "frozen": {"version": "2026-09-19-aaaaaaaa", "frozen_on": day}}
    reg = es.register(tmp_path, v1, prospective_dir=tmp_path / "prospective", today=date(2026, 9, 22))
    regs = json.loads(reg.read_text(encoding="utf-8"))["registrations"]
    assert [(r["run"], r["version"]) for r in regs] == [(meta["run"], "2026-09-19-aaaaaaaa")]
    with pytest.raises(SystemExit, match="already registers rule version"):
        es.register(tmp_path, v1, prospective_dir=tmp_path / "prospective", today=date(2026, 9, 22))
    with pytest.raises(SystemExit, match="before rule version .* was frozen"):
        es.register(tmp_path, {**meta, "frozen": {"version": "2027-01-05-bbbbbbbb", "frozen_on": "2027-01-05"}},
                    prospective_dir=tmp_path / "prospective", today=date(2027, 1, 6))
    with pytest.raises(SystemExit, match="more than 14 days old"):
        es.register(tmp_path, {**meta, "frozen": {"version": "2026-09-19-cccccccc", "frozen_on": day}},
                    prospective_dir=tmp_path / "prospective", today=date(2027, 1, 6))
    es.register(tmp_path, {**meta, "frozen": {"version": "2026-09-19-dddddddd", "frozen_on": day}},
                prospective_dir=tmp_path / "prospective", today=date(2026, 9, 20))
    assert len(es._registrations(reg)) == 2, "a refit rule gets its own registration; the first is kept"


def test_the_monitor_waits_for_the_record_and_sets_like_against_like(built, tmp_path):
    fc, details, meta, extra = built
    places = extra["places"]
    through = max(p["dates"][-1] for p in places if p["dates"])
    too_soon = es.monitor(tmp_path, places, log=lambda *_: None) if False else None
    es.archive(tmp_path, meta, extra["ranking"])                                # drawn up after the record ends
    early = _as_of(meta, (es._d(through) - timedelta(days=150)).isoformat())    # 150 days of record since
    es.archive(tmp_path, early, extra["ranking"])
    old = _as_of(meta, (es._d(through) - timedelta(days=400)).isoformat())      # a whole label year since
    es.archive(tmp_path, old, extra["ranking"])
    res = {r["run"]: r for r in es.monitor(tmp_path, places, log=lambda *_: None)}
    assert res[meta["run"]]["window_days"] is None and "city" not in res[meta["run"]], "no record since: too early"
    e = res[early["run"]]
    assert e["complete"] is False and e["window_days"] == 90, "interim: the longest window the record covers"
    assert e["city"]["bands"].get("1", {}).get("expected") == meta["card"]["interim"]["90"]["1"]["rate"], \
        "set against the backtest's rate over the same 90 days"
    o = res[old["run"]]
    assert o["complete"] is True and o["window_days"] == es.LABEL_DAYS
    assert o["city"]["labelled"] + o["outside"]["labelled"] == o["labelled"]
    assert "observed_over_expected" in o["city"] and o["city"]["observed_over_expected"]["expected"] > 0
    if o["city"]["bands"].get("1"):
        assert o["city"]["bands"]["1"]["expected"] == meta["card"]["bands"][0]["rate"]
        assert len(o["city"]["band_1_minus_persistence"]) == 2
    out_b1 = o["outside"]["bands"].get("1")
    if out_b1 and meta["card"]["outside"]["bands"]:
        assert out_b1["expected"] == meta["card"]["outside"]["bands"][0]["rate"], "outside places against outside rates"
    gone = {r["run"]: r for r in es.monitor(tmp_path, places[1:], log=lambda *_: None)}[old["run"]]
    assert sum(gone["missing_from_later_pull"].values()) >= 1, "a place gone from the later pull is counted, not dropped"
    assert "| area |" in (tmp_path / "monitor.md").read_text(encoding="utf-8")


def test_an_older_single_registration_is_still_read(tmp_path):
    (tmp_path / "REGISTERED.json").write_text(json.dumps({"run": "forward_2026-09-01", "ranking_sha256": "x"}))
    assert [r["run"] for r in es._registrations(tmp_path / "REGISTERED.json")] == ["forward_2026-09-01"]
    assert es._registrations(tmp_path / "missing.json") == []


def _monitor_row(run, *, days=400, complete=True, b1=(400, [0.55, 0.8], 0.70), all_rate=0.2, oe=1.02, vp=(3.0, 20.0)):
    n, interval, rate = b1
    return {"run": run, "days": days, "complete": complete, "labelled": 2000, "positives": 500, "bands": {},
            "city": {"labelled": 1500, "all_rate": all_rate, "bands": {"1": {"labelled": n, "positives": int(n * rate),
                                                                          "rate": rate, "interval": interval}},
                     "observed_over_expected": {"observed": 100, "expected": 100 / oe, "ratio": oe},
                     "band_1_minus_persistence": list(vp)},
            "rule_minus_average": [0.01, 0.03]}


def test_the_prospective_gate(built, tmp_path, monkeypatch):
    fc, details, meta, extra = built
    ok, why = es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p")
    assert not ok and "no registered run" in why
    es.archive(tmp_path, meta, extra["ranking"])
    v = "2026-09-19-aaaaaaaa"
    frozen = {**meta, "frozen": {"version": v, "frozen_on": es.run_date(meta["run"])}}
    es.register(tmp_path, frozen, prospective_dir=tmp_path / "p", today=date(2026, 9, 22))
    assert "for rule version 2027" in es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p", version="2027-01-01-cccccccc")[1], \
        "a registration tests only the rule version it was made for"
    monkeypatch.setattr(es, "_pushed_date", lambda path, needle, activity=None: None)
    assert "cannot be read from GitHub" in es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p", version=v)[1]
    monkeypatch.setattr(es, "_pushed_date", lambda path, needle, activity=None: date(2026, 11, 30))
    assert "committed 72 days after its list" in es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p", version=v)[1], \
        "a registration made after part of its label year could be seen does not count"
    monkeypatch.setattr(es, "_pushed_date", lambda path, needle, activity=None: date(2026, 9, 22))
    assert "90" in es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p", today=date(2026, 10, 1), version=v)[1]
    later = date(2027, 11, 1)
    mon = tmp_path / "monitor.json"
    mon.write_text(json.dumps([_monitor_row(meta["run"], days=200, complete=False)]))
    assert "label year is not over" in es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p", today=later, version=v)[1]
    mon.write_text(json.dumps([_monitor_row(meta["run"], b1=(120, [0.55, 0.7], 0.62))]))
    assert "fewer than 300" in es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p", today=later, version=v)[1], \
        "300 later inspections of band 1 City places, not 300 of anything"
    mon.write_text(json.dumps([_monitor_row(meta["run"])]))
    ok, why = es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p", today=later, version=v)
    assert ok, why
    assert not es.prospective_ok(tmp_path, 3.0, prospective_dir=tmp_path / "p", today=later, version=v)[0], "0.55 < 0.75"
    mon.write_text(json.dumps([_monitor_row(meta["run"], all_rate=0.58)]))
    assert "not clearly above" in es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p", today=later, version=v)[1], \
        "band 1 must beat all scored City places, not only the cost bar"
    backtest_b1 = meta["card"]["bands"][0]["rate"]
    mon.write_text(json.dumps([_monitor_row(meta["run"], b1=(400, [backtest_b1 - 0.11, backtest_b1 - 0.01], backtest_b1 - 0.06),
                                            all_rate=0.1)]))
    got = es.prospective_ok(tmp_path, 0.1, prospective_dir=tmp_path / "p", today=later, version=v)[1]
    assert "more than 5 points below its backtest rate" in got, "the observed rate, not the upper end of its interval"
    mon.write_text(json.dumps([_monitor_row(meta["run"], b1=(400, [backtest_b1 - 0.09, backtest_b1 + 0.01], backtest_b1 - 0.04),
                                            all_rate=0.1)]))
    assert es.prospective_ok(tmp_path, 0.1, prospective_dir=tmp_path / "p", today=later, version=v)[0], "4 points below passes"
    mon.write_text(json.dumps([_monitor_row(meta["run"], oe=0.7)]))
    assert "not calibrated" in es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p", today=later, version=v)[1]
    mon.write_text(json.dumps([_monitor_row(meta["run"], vp=(-4.0, 9.0))]))
    assert "recent major violations' same-size group" in es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p",
                                                                             today=later, version=v)[1]


def test_a_frozen_rule_is_applied_unchanged(built):
    """Every export applies docs/rule.json as frozen: the same rule, cuts and estimates, and on the same
    record the same list and run id; only --refit chooses again."""
    fc, details, meta, extra = built
    rec = json.loads(json.dumps(es.frozen_record(extra["fitted"], meta["run"], date(2026, 9, 22)), default=str))
    assert re.fullmatch(r"2026-09-22-[0-9a-f]{8}", rec["version"]) and rec["from_run"] == meta["run"]
    assert "_train" not in rec and set(es.FROZEN_KEYS) <= set(rec)
    fc2, details2, meta2, extra2 = es.build(invented_county(), DISTRICTS, pull=PULL, approval=None, today=date(2026, 9, 22),
                                            refits=2, log=lambda *_: None, frozen=rec)
    assert meta2["frozen"] == {"version": rec["version"], "frozen_on": "2026-09-22", "from_run": meta["run"]}
    same = lambda x: json.loads(json.dumps(x, default=str))
    assert meta2["model"] == meta["model"] and same(meta2["card"]["bands"]) == same(meta["card"]["bands"])
    assert same(meta2["card"]["curve"]) == same(meta["card"]["curve"]) and meta2["run"] == meta["run"]
    assert [f["properties"].get("band") for f in fc2["features"]] == [f["properties"].get("band") for f in fc["features"]]
    # A frozen cut is applied, not re-chosen: raise it, and fewer places are in band 1.
    higher = json.loads(json.dumps(rec))
    higher["cuts"] = [c + 5 for c in higher["cuts"]]
    fc3 = es.build(invented_county(), DISTRICTS, pull=PULL, approval=None, today=date(2026, 9, 22), refits=2,
                   log=lambda *_: None, frozen=higher)[0]
    n = lambda fc_: sum(1 for f in fc_["features"] if f["properties"].get("band") == "1")
    assert n(fc3) < n(fc) or n(fc) == 0


def test_the_version_names_the_rule(built):
    fc, details, meta, extra = built
    a = es.frozen_record(extra["fitted"], meta["run"], date(2026, 9, 22))
    other = {**extra["fitted"], "cuts": [c + 1 for c in extra["fitted"]["cuts"]]}
    b = es.frozen_record(other, meta["run"], date(2026, 9, 22))
    assert a["version"] != b["version"], "two different rules frozen on one day never share a version"


def test_drift_compares_only_quarters_after_the_label_year_with_a_threshold_from_the_counts():
    fitted = {"confirm": "2025-01-01", "label_quarters": ["2025Q1", "2025Q2", "2025Q3", "2025Q4"],
              "card": {"rows": [{"band": "1", "share": 0.12}]}, "catch_run": {"eligible": 3000}}
    rates = {"2025Q1": 0.20, "2025Q2": 0.20, "2025Q3": 0.20, "2025Q4": 0.20, "2026Q1": 0.205, "2026Q2": 0.21}
    m = {"major_rate_by_quarter": dict(rates), "routine_n_by_quarter": {q: 2000 for q in rates}}
    d = es.drift_check(m, fitted, 0.12, through="2025-12-20", n_now=3000)
    assert d["status"] == "not_yet_measurable" and d["refit_needed"] is False, "no complete quarter after the label year"
    d = es.drift_check(m, fitted, 0.12, through="2026-07-15", n_now=3000)
    assert d["recent_quarters"] == ["2026Q1"], "2026Q2 ended June 30: its reporting has 30 days to catch up"
    d = es.drift_check(m, fitted, 0.12, through="2026-08-15", n_now=3000)
    assert d["status"] == "ok" and d["recent_quarters"] == ["2026Q1", "2026Q2"] and d["major_rate_recent"] == 0.2075
    m["major_rate_by_quarter"].update({"2026Q1": 0.26, "2026Q2": 0.27})
    d = es.drift_check(m, fitted, 0.12, through="2026-08-15", n_now=3000)
    assert d["refit_needed"] and d["status"] == "refit" and "routine major rate 26.5%" in d["reasons"][0]
    assert d["note"] and "may be low" in d["note"] and "2026 Q3" not in d["note"], "the latest quarter with data (Q2)"
    d = es.drift_check({"major_rate_by_quarter": {}}, fitted, 0.20, n_now=3000)
    assert d["refit_needed"] and "band 1 holds 20.0%" in d["reasons"][0]
    small = es.drift_check({"major_rate_by_quarter": {}}, fitted, 0.135, n_now=3000)
    assert not small["refit_needed"], "1.5 points on 3,000 places is within the threshold"
    assert es.drift_check({}, {"card": {"rows": []}}, None)["status"] == "not_yet_measurable"


def test_the_frozen_rule_covers_the_code_that_gives_points_their_meaning(built, monkeypatch):
    fc, details, meta, extra = built
    rec = json.loads(json.dumps(es.frozen_record(extra["fitted"], meta["run"], date(2026, 9, 22)), default=str))
    assert es.spec_problems(rec) == []
    monkeypatch.setattr(es, "CLOSURE_SCORE", 80)
    assert es.spec_problems(rec) and "refit" in es.spec_problems(rec)[0]
    with pytest.raises(SystemExit, match="changed since rule version"):
        es.build(invented_county(), DISTRICTS, pull=PULL, approval=None, today=date(2026, 9, 22), refits=0,
                 log=lambda *_: None, frozen=rec)
    monkeypatch.undo()
    old = {k: v for k, v in rec.items() if k != "feature_spec"}
    assert "frozen without its feature code" in es.spec_problems(old)[0]


def test_each_place_reads_the_estimate_curve_for_its_own_group(built):
    """Places whose two scored years include a health closure read their own curve: they had a major
    next time less often than places with the same points from routine scores alone."""
    fc, details, meta, extra = built
    groups = {d["estimate"]["group"] for d in details.values() if d.get("estimate")}
    assert groups <= {"scores", "closure"} and groups
    for d in details.values():
        e = d.get("estimate")
        if not e:
            continue
        has = any(u["closure"] for u in d["scores_used"])
        assert e["group"] == ("closure" if has else "scores")
        outside = d["council_district"] is None
        src = meta["card"]["outside"] if outside else meta["card"]
        c = src.get("curve_closure") if has else src.get("curve")
        if c:
            j = min(d["points"], len(c["rate"]) - 1)
            assert e["rate"] == c["rate"][j]


def test_interim_rates_for_the_monitor_are_stored_with_the_rule(built):
    fc, details, meta, extra = built
    interim = meta["card"]["interim"]
    assert set(interim) == {"90", "180", "270"}
    assert interim["90"]["all"]["labelled"] <= interim["180"]["all"]["labelled"] <= interim["270"]["all"]["labelled"]


def test_a_fixed_rule_has_no_refit_stability(built):
    fc, details, meta, extra = built
    if meta["selection"]["chosen"] == "average score":
        assert all(b["kept_in_refits"] is None for b in meta["card"]["bands"]), "nothing is refitted: no 100%"
        assert all(f["properties"].get("band_stability") is None for f in fc["features"])


def test_the_export_freezes_a_fresh_fit_and_applies_it_after(tmp_path, monkeypatch):
    raw = invented_county()
    pull = tmp_path / "sd_businesses.2026-09-29.json"
    pull.write_text(json.dumps(raw), encoding="utf-8")
    (tmp_path / "pull_meta.2026-09-29.json").write_text(json.dumps({"complete": True, "sha256": es.sha256_pull(pull)}), encoding="utf-8")
    frozen = tmp_path / "docs" / "rule.json"
    monkeypatch.setattr(es, "FROZEN", frozen)
    monkeypatch.setattr(es, "APPROVAL", tmp_path / "none.json")
    monkeypatch.setattr(es, "load_districts", lambda *a, **k: DISTRICTS)
    monkeypatch.setattr(es, "contract_check", lambda *a, **k: [])
    args = ["--pull", str(pull), "--out", str(tmp_path / "out"), "--refits", "0"]
    assert es.main(args) == 0 and frozen.exists()
    first = json.loads(frozen.read_text(encoding="utf-8"))
    shipped = json.loads((tmp_path / "out" / "meta.json").read_text(encoding="utf-8"))
    assert shipped["frozen"]["version"] == first["version"]
    frozen.write_text(json.dumps({**first, "version": "2026-01-01-feedface"}), encoding="utf-8")
    assert es.main(args) == 0
    assert json.loads((tmp_path / "out" / "meta.json").read_text(encoding="utf-8"))["frozen"]["version"] == "2026-01-01-feedface", \
        "an existing docs/rule.json is applied, never overwritten"
    assert es.main(args + ["--refit"]) == 0
    assert json.loads(frozen.read_text(encoding="utf-8"))["version"] != "2026-01-01-feedface", "--refit writes a new version"


def test_the_committed_site_data_is_the_invented_sample():
    """Real names never enter the repository: the site's committed data is the sample."""
    meta = json.loads((SITE / "public" / "data" / "meta.json").read_text(encoding="utf-8"))
    assert meta["sample"] is True
    # ...and proven to be, not just flagged: the flag alone switches off every publication gate.
    assert meta["run"] == "sample" and meta["source"]["url"] is None and meta["provenance"]["code_sha"] == "sample"
    fc = json.loads((SITE / "public" / "data" / "facilities.geojson").read_text(encoding="utf-8"))
    ids = [f["properties"]["facility_id"] for f in fc["features"]]
    assert ids and all(re.fullmatch(r"SAMPLE-FFPP-\d{5}", i) for i in ids)
    assert all(f["properties"]["name"].startswith("Sample ") for f in fc["features"])
    places = sorted(p.stem for p in (SITE / "public" / "data" / "place").glob("*.json"))
    assert places == sorted(ids), "no place file outside the sample index"


def test_facility_ids_are_unique_even_when_the_county_repeats_one():
    raw = [business("1", [inspection("2025-06-01")]), business("2", [inspection("2025-06-01")])]
    for b in raw:
        for i in b["inspections"]:
            i["custom_id"] = "DEH2024-FFPP-000009"
    places, _, _ = es.prepare(raw, DISTRICTS)
    assert len({p["facility_id"] for p in places}) == 2


# ── escalation facts, the worksheet's scores, the outside-City check, the run id, the pull ──────

VERMIN = "23. No rodents, insects, birds, or animals"


def _place(raw_visits, btype="Restaurant Food Facility"):
    st = es.Stats()
    return es.load_places([business("7", raw_visits, btype=btype)], st)[0]


def _closed(day, kind="Routine"):
    return inspection(day, kind=kind, score="0", grade="", status="Ordered Closed", violations=[violation(VERMIN, "major")])


def _reopen(day, **kw):
    return inspection(day, kind="Re-inspection", score="0", grade="", status="Approved to Reopen", **kw)


def test_escalation_flags_follow_the_countys_own_criteria():
    p = _place([inspection("2025-01-10", violations=[violation(VERMIN, "major")]), _closed("2025-06-02"), _reopen("2025-06-05"),
                inspection("2025-11-03", violations=[violation(VERMIN, "major")]), _closed("2026-05-04")])
    f = es.flags(es.display_records(p), p["visits"], "2026-09-29")
    assert "closures2" in f, "two closure episodes in two years"
    assert "repeat_item" in f, "item 23 major at two routine inspection days"
    q = _place([inspection("2025-01-10", violations=[violation(VERMIN, "major")]), inspection("2025-11-03")])
    assert not set(es.ESCALATION_FLAGS) & set(es.flags(es.display_records(q), q["visits"], "2026-09-29"))


def test_one_closure_is_one_episode_until_the_county_reopens_it():
    """A complaint visit, a second order or an ungraded reinspection while a place is closed does not
    end the episode; the County's reopening does, and the day it came is kept."""
    p = _place([_closed("2025-06-06"),
                inspection("2025-06-07", kind="Site Investigation", score="0", grade=""),
                _closed("2025-06-07", kind="Re-inspection"),
                inspection("2025-06-08", kind="Re-inspection", score="0", grade="", iid="b-rescore"),
                _reopen("2025-06-08", iid="a-reopen")])
    recs = es.display_records(p)
    episodes = [r for r in recs if r["closed"]]
    assert len(episodes) == 1 and episodes[0]["date"] == "2025-06-06"
    assert episodes[0]["reopened"] is True and episodes[0]["reopened_on"] == "2025-06-08",         "a same-day record merged with the reopening must not hide it"
    assert "closures2" not in es.flags(recs, p["visits"], "2025-09-01")


def test_a_graded_inspection_or_a_long_gap_ends_an_episode():
    graded = _place([_closed("2025-03-03"), inspection("2025-03-20", score="96"), _closed("2025-05-01")])
    assert sum(r["closed"] for r in es.display_records(graded)) == 2, "graded again on a later day: open"
    assert [r["reopened"] for r in es.display_records(graded) if r["closed"]] == [False, False], "no reopening was recorded"
    gap = _place([_closed("2025-03-03"), inspection("2025-03-10", kind="Site Investigation", score="0", grade=""),
                  _closed("2025-05-01", kind="Re-inspection")])
    assert sum(r["closed"] for r in es.display_records(gap)) == 2, f"orders {es.EPISODE_GAP_DAYS}+ days apart are two episodes"
    rec = es.display_records(gap)
    assert "closures2" in es.flags(rec, gap["visits"], "2025-09-01")


def test_escalation_flags_are_measured_from_the_list_date():
    """Two years back from the list, not from the place's last visit: closures older than that do
    not count, however long ago the last visit was."""
    p = _place([_closed("2024-03-01"), _reopen("2024-03-04"), _closed("2024-08-01"), _reopen("2024-08-03"),
                inspection("2025-02-01", score="96")])
    rec = es.display_records(p)
    assert "closures2" in es.flags(rec, p["visits"], "2025-06-01")
    assert "closures2" not in es.flags(rec, p["visits"], "2026-09-29"), "both closures are over two years before the list"
    assert "closed" not in es.flags(rec, p["visits"], "2026-09-29")


def test_repeat_item_and_scores_below_90_count_inspection_days_not_records():
    twice_one_day = [inspection("2026-05-18", score="85", grade="B", violations=[violation(VERMIN, "major")], iid="x1"),
                     inspection("2026-05-18", score="85", grade="B", violations=[violation(VERMIN, "major")], iid="x2")]
    p = _place(twice_one_day + [inspection("2026-08-01", score="95")])
    f = es.flags(es.display_records(p), p["visits"], "2026-09-29")
    assert "repeat_item" not in f and "lt90_2" not in f, "one inspection the County recorded twice counts once"
    q = _place([inspection("2025-03-07", score="88", grade="B", violations=[violation(VERMIN, "major")]),
                inspection("2025-09-01", score="97"), inspection("2026-01-10", score="96"),
                inspection("2026-04-28", score="86", grade="B", violations=[violation(VERMIN, "major")])])
    f = es.flags(es.display_records(q), q["visits"], "2026-09-29")
    assert "repeat_item" in f, "the same major item at two routine inspection days in two years, clean ones between"
    assert "lt90_2" in f, "two routine scores below 90 in two years (the Guide's middle criterion)"
    assert "major_2" in f, "majors at two routine inspection days (the Guide's first criterion, any items)"
    one = _place([inspection("2025-09-01", score="88", grade="B", violations=[violation(VERMIN, "major")]),
                  inspection("2026-03-01", score="95", violations=[violation(TEMP, "minor")])])
    assert "major_2" not in es.flags(es.display_records(one), one["visits"], "2026-09-29")


def test_every_routine_health_closure_counts_as_70_and_keeps_the_countys_score():
    """A closure order the County also scored that day counts as 70 like any other: one rule for
    every closure. The worksheet keeps the County's own score beside it."""
    p = _place([inspection("2025-02-01", score="95"),
                inspection("2025-11-06", score="94", grade="A", iid="c1"),
                inspection("2025-11-06", score="0", grade="", status="Ordered Closed", violations=[violation(VERMIN, "major")], iid="c2"),
                _reopen("2025-11-08")])
    used = es.scores_used(p, "2026-09-20")
    assert [(u["score"], u["closure"], u["county_score"]) for u in used] == [(95, False, 95), (70, True, 94)]
    assert es.features_at(p, "2026-09-20")["avg_deficit"] == 100 - int((95 + 70) / 2 + 0.5)


def test_the_worksheet_lists_the_scores_it_averages_and_rounds_half_up():
    p = _place([inspection("2025-02-01", score="95"), inspection("2025-08-01", score="94"),
                inspection("2026-01-15", score="0", grade="", status="Ordered Closed", violations=[violation(VERMIN, "major")])])
    used = es.scores_used(p, "2026-09-20")
    assert [u["score"] for u in used] == [95, 94, es.CLOSURE_SCORE] and [u["closure"] for u in used] == [False, False, True]
    assert [u["county_score"] for u in used] == [95, 94, None], "the County gave no score the day it closed the place"
    f = es.features_at(p, "2026-09-20")
    mean = sum(u["score"] for u in used) / len(used)             # 86.33
    assert f["avg_deficit"] == 100 - int(mean + 0.5) and f["last_deficit"] == 100 - es.CLOSURE_SCORE
    two = _place([inspection("2025-02-01", score="95"), inspection("2025-08-01", score="94")])
    assert es.features_at(two, "2026-03-01")["avg_deficit"] == 5, "94.5 rounds up to 95, as a person would"


def test_places_outside_the_city_get_a_band_only_where_bands_were_checked_there(built):
    fc, details, meta, extra = built
    out = meta["card"]["outside"]
    assert {"bands_shown", "bands", "rest", "curve", "base_rate"} <= set(out)
    outside = [f["properties"] for f in fc["features"] if f["properties"]["council_district"] is None]
    assert outside, "the invented county has places outside the City"
    if not out["bands_shown"]:
        assert not any("band" in p for p in outside)
    for p in (f["properties"] for f in fc["features"]):
        if "points" in p:
            e = details[p["facility_id"]]["estimate"]
            assert e is None or 0 <= e["low"] <= e["rate"] <= e["high"] <= 1


def test_the_run_id_names_its_content_and_every_shown_band_is_audited(built):
    fc, details, meta, extra = built
    assert re.fullmatch(r"forward_\d{4}-\d{2}-\d{2}-[0-9a-f]{8}", meta["run"])
    assert es.run_date(meta["run"]) == meta["run"][8:18] and es.run_date("forward_2026-09-20") == "2026-09-20"
    assert meta["fairness"]["bands_used"] == [r["band"] for r in meta["card"]["bands"]]
    assert meta["card"]["base_rate"] is not None and meta["card"]["curve"]["rate"]
    assert all(set(o) >= {"as_of"} for o in meta["card"]["by_origin"]) and len(meta["card"]["by_origin"]) == 3


def test_the_export_refuses_a_pull_that_is_not_complete(tmp_path, monkeypatch):
    pull = tmp_path / "sd_businesses.2026-09-29.json"
    pull.write_text("[]", encoding="utf-8")
    (tmp_path / "pull_meta.2026-09-29.json").write_text(json.dumps({"complete": False}), encoding="utf-8")
    with pytest.raises(SystemExit, match="not recorded as complete"):
        es.main(["--pull", str(pull), "--out", str(tmp_path / "out")])
    (tmp_path / "pull_meta.2026-09-29.json").write_text(json.dumps({"complete": True, "sha256": "0" * 64}), encoding="utf-8")
    with pytest.raises(SystemExit, match="does not match the sha256"):
        es.main(["--pull", str(pull), "--out", str(tmp_path / "out")])
    lone = tmp_path / "sd_businesses.nometa.json"
    lone.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit, match="no pull meta"):
        es.main(["--pull", str(lone), "--out", str(tmp_path / "out")])



def test_the_risk_curve_levels_off_where_risk_does():
    """A curve that must keep rising overstated the top of the list (the real rates level off near
    40%); the isotonic fit follows them."""
    rng = np.random.default_rng(2)
    fits = []
    for seed in range(8):
        rng = np.random.default_rng(seed)
        pts = np.concatenate([rng.integers(0, 8, 3000), rng.integers(8, 26, 900)])
        pos = (rng.random(len(pts)) < np.where(pts < 8, 0.05 + 0.04 * pts, 0.37)).astype(float)
        ones = np.ones(len(pts), bool)
        c = es.risk_curve(pts, pos, ones, ones, np.arange(len(pts)), n_boot=20)
        fits.append([c["rate"][x] for x in (0, 4, 8, 16, 25)])
        assert all(g[1] - g[0] >= 0 for g in c["groups"])
    mean = np.array(fits).mean(axis=0)
    assert abs(mean[0] - 0.05) < 0.03 and abs(mean[1] - 0.21) < 0.03
    assert abs(mean[3] - 0.37) < 0.04 and abs(mean[4] - 0.37) < 0.06, "no climb past the plateau"



def test_the_risk_curve_covers_every_point_value_even_without_places_at_zero():
    pts = np.array([3] * 120 + [5] * 150 + [9] * 130)
    pos = (np.random.default_rng(1).random(len(pts)) < 0.2).astype(float)
    ones = np.ones(len(pts), bool)
    c = es.risk_curve(pts, pos, ones, ones, np.arange(len(pts)), n_boot=20)
    assert len(c["rate"]) == 10 and all(0 <= lo <= r <= hi <= 1 for lo, r, hi in zip(c["low"], c["rate"], c["high"]))
    assert c["rate"][0] == c["rate"][3], "below the lowest group, a place reads that group's rate"


def test_band_1_is_split_by_route_and_districts_carry_precision_intervals(built):
    fc, details, meta, extra = built
    c = meta["card"]
    assert c["closure_score"] == es.CLOSURE_SCORE
    if meta["selection"]["chosen"] == "average score" and c["bands"]:
        r = c["band_1_by_route"]
        assert set(r) == {"closure", "scores"}
        assert r["closure"]["labelled"] + r["scores"]["labelled"] == c["bands"][0]["labelled"]
    for d, e in meta["fairness"]["by_district"].items():
        assert "labelled" in e and "interval_family" in e and "interval_family_deff" in e
        assert e["evidence_above_even"] == bool(e["interval_family"] and e["interval_family_deff"]
                                                and min(e["interval_family"][0], e["interval_family_deff"][0]) > 1)
        if e["interval_family"] and e["interval_family_deff"]:
            assert e["interval_family_deff"][0] <= e["interval_family"][0] and e["interval_family"][1] <= e["interval_family_deff"][1]
        if e["precision"] is not None:
            lo, hi = e["precision_interval"]
            assert lo <= e["precision"] <= hi
        if e["interval"] and e["interval_family"]:
            assert e["interval_family"][0] <= e["interval"][0] and e["interval"][1] <= e["interval_family"][1],                 "the family-wise interval is the wider one"


def test_the_countys_point_formula_for_a_closure(monkeypatch):
    v = {"closure_order": "health", "score": None,
         "_items": [{"severity": "major"}, {"severity": "major"}, {"severity": "minor"}, {"severity": "grp"}]}
    assert es.rated_score(v) == es.CLOSURE_SCORE
    monkeypatch.setattr(es, "CLOSURE_VALUE", "county")
    assert es.rated_score(v) == 100 - 8 - 2 - 1
    monkeypatch.setattr(es, "CLOSURE_VALUE", 90)
    assert es.rated_score(v) == 90
    assert es.rated_score({"closure_order": None, "score": 93, "_items": []}) == 93


def test_the_band_rule_rarely_keeps_a_band_that_is_not_there():
    """No gradient, three overlapping origins as in the real backtest: a band survives rarely."""
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import band_null_sim as sim
    rng = np.random.default_rng(7)
    kept = sum(bool(sim.one(rng, 3300, 0.21, 0.6)) for _ in range(300))
    assert kept / 300 < 0.02, f"{kept} of 300 null simulations kept a band"


def test_the_drift_baseline_is_the_label_years_own_months():
    """Not the whole quarters around it: a label year from September 1 does not borrow July and August."""
    fitted = {"confirm": "2025-09-01", "label_quarters": ["2025Q3", "2025Q4", "2026Q1", "2026Q2", "2026Q3"],
              "card": {"rows": []}, "catch_run": {"eligible": 3000}}
    months = {f"2025-{m:02d}": [1000, 300] for m in (7, 8)}                  # before the label year: 30%
    months.update({f"2025-{m:02d}": [1000, 150] for m in (9, 10, 11, 12)})   # the label year: 15%
    months.update({f"2026-{m:02d}": [1000, 150] for m in range(1, 9)})
    months["2026-09"] = [1000, 400]                                          # after it: 40%
    m = {"routine_by_month": months, "major_rate_by_quarter": {"2026Q3": 0.25}, "routine_n_by_quarter": {"2026Q3": 3000}}
    d = es.drift_check(m, fitted, None, through="2026-09-28")
    assert d["major_rate_backtest"] == 0.15 and d["status"] == "not_yet_measurable"


def test_the_drift_notes_baseline_never_shares_an_inspection_with_the_quarter_it_is_set_against():
    """The latest quarter (2026 Q3) falls inside the label year: the note compares it with the label
    year's months before it (September 2025 to June 2026), on their own count."""
    fitted = {"confirm": "2025-09-01", "label_quarters": ["2025Q3", "2025Q4", "2026Q1", "2026Q2", "2026Q3"],
              "card": {"rows": []}, "catch_run": {"eligible": 3000}}
    months = {f"2025-{m:02d}": [1000, 150] for m in (7, 8, 9, 10, 11, 12)}
    months.update({f"2026-{m:02d}": [1000, 150] for m in range(1, 7)})
    months.update({"2026-07": [1000, 300], "2026-08": [1000, 300], "2026-09": [900, 270]})     # the latest quarter: 30%
    m = {"routine_by_month": months, "major_rate_by_quarter": {"2026Q2": 0.15, "2026Q3": 0.3},
         "routine_n_by_quarter": {"2026Q2": 3000, "2026Q3": 2900}}
    d = es.drift_check(m, fitted, None, through="2026-09-28")
    assert d["latest_quarter"] == "2026Q3" and d["latest_baseline"] == 0.15 and d["latest_baseline_n"] == 10_000
    assert d["latest_baseline_span"] == "September 2025 to June 2026"
    assert d["major_rate_backtest"] == round((10 * 150 + 600) / 12_000, 4), "the refit baseline is still the whole label year"
    assert "against 15.0% over the backtest's label year before that quarter (September 2025 to June 2026)" in d["note"]
    assert "may be low" in d["note"]
    quiet = es.drift_check({**m, "major_rate_by_quarter": {"2026Q2": 0.15, "2026Q3": 0.16}}, fitted, None, through="2026-09-28")
    assert quiet["note"] is None, "one point on these counts is within the threshold"


def _summary_row(run, *, complete=False, window=90, b1=(200, 0.2, [0.15, 0.26], 0.31), oe=None, vp=(1.0, 9.0), outside_oe=None):
    n, rate, interval, expected = b1
    city = {"labelled": 1000, "bands": {"1": {"labelled": n, "positives": int(n * rate), "rate": rate, "interval": interval,
                                               "expected": expected}},
            "band_1_minus_persistence": list(vp)}
    if oe is not None:
        city["observed_over_expected"] = {"observed": int(100 * oe), "expected": 100.0, "ratio": oe}
    out = {"labelled": 800, "bands": {}}
    if outside_oe is not None:
        out["observed_over_expected"] = {"observed": int(100 * outside_oe), "expected": 100.0, "ratio": outside_oe}
    return {"run": run, "complete": complete, "window_days": window, "record_days": 0, "city": city, "outside": out}


def test_the_monitor_summary_says_how_far_the_monitor_got_and_what_it_found():
    too_early = [{"run": "forward_2026-09-29-aaaaaaaa", "complete": False, "window_days": None}]
    s = es.monitor_summary(too_early)
    assert s == {"status": "too early", "runs": 1, "alerts": [], "next_window_date": "2027-01-27"}, "90 + 30 days after the list"
    assert es.monitor_summary([])["status"] == "too early" and es.monitor_summary([])["next_window_date"] is None
    fine = [_summary_row("forward_2026-06-01-bbbbbbbb", b1=(200, 0.3, [0.24, 0.37], 0.31))] + too_early
    s = es.monitor_summary(fine)
    assert s["status"] == "interim" and s["alerts"] == [] and s["next_window_date"] == "2026-12-28", \
        "the 180-day window of the June list comes before the first window of the September one"
    low = [_summary_row("forward_2026-05-01-cccccccc"), _summary_row("forward_2026-06-01-bbbbbbbb")] + too_early
    s = es.monitor_summary(low)
    assert len(s["alerts"]) == 1 and "list of 2026-06-01" in s["alerts"][0] and "below the 31.0%" in s["alerts"][0]
    assert "So did 1 earlier list." in s["alerts"][0], "one sentence per kind of finding, not one per list"
    done = [_summary_row("forward_2025-06-01-dddddddd", complete=True, window=365, b1=(400, 0.3, [0.26, 0.35], 0.31),
                         oe=0.8, vp=(-9.0, -1.0), outside_oe=1.2)]
    s = es.monitor_summary(done)
    assert s["status"] == "complete" and s["next_window_date"] is None and len(s["alerts"]) == 3
    assert "in the City" in s["alerts"][0] and "outside 0.85 to 1.15" in s["alerts"][0]
    assert "outside the City" in s["alerts"][1]
    assert "the most recent major violations" in s["alerts"][2] and "-9.0 to -1.0" in s["alerts"][2]
    ok = [_summary_row("forward_2025-06-01-dddddddd", complete=True, window=365, b1=(400, 0.3, [0.26, 0.35], 0.31),
                       oe=1.1, vp=(-3.0, 8.0))]
    assert es.monitor_summary(ok)["alerts"] == [], "an interval that crosses 0 is not clearly negative"
    for text in (a for r in (low, done) for a in es.monitor_summary(r)["alerts"]):
        assert "—" not in text and "risk" not in text.lower() and "fail" not in text.lower()


def test_the_monitor_writes_its_summary_and_a_monitor_that_did_not_run_says_so(built, tmp_path, monkeypatch):
    fc, details, meta, extra = built
    es.monitor(tmp_path, extra["places"], log=lambda *_: None)
    s = json.loads((tmp_path / "monitor_summary.json").read_text(encoding="utf-8"))
    assert s == {"status": "too early", "runs": 0, "alerts": [], "next_window_date": None}, "written even with nothing to score"
    raw = invented_county(n=20)
    pull = tmp_path / "sd_businesses.2026-09-29.json"
    pull.write_text(json.dumps(raw), encoding="utf-8")
    (tmp_path / "pull_meta.2026-09-29.json").write_text(json.dumps({"complete": True, "sha256": es.sha256_pull(pull)}),
                                                       encoding="utf-8")

    def broken(*a, **k):
        raise ValueError("no")
    monkeypatch.setattr(es, "monitor", broken)
    with pytest.raises(ValueError):
        es.main(["--pull", str(pull), "--out", str(tmp_path / "out"), "--monitor"])
    s = json.loads((tmp_path / "out" / "monitor_summary.json").read_text(encoding="utf-8"))
    assert s["status"] == "failed" and s["alerts"] == ["The monitor did not run (ValueError)."]


def test_the_registration_counts_from_githubs_record_of_the_push():
    """A commit date is whatever its author set; GitHub's push timestamp is not."""
    path = ROOT / "docs" / "prospective" / "REGISTERED.json"
    run = "forward_2026-09-29-91e1bb95"                  # added by an early commit in this repository's history
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    first = subprocess.run(["git", "log", "--reverse", "--format=%H", "-S", run, "--", str(path)], cwd=ROOT,
                           capture_output=True, text=True).stdout.split()
    if not first:
        pytest.skip("the registration is not in this checkout's history")
    carried = [{"before": "0" * 40, "after": head, "timestamp": "2026-10-03T17:00:00Z"}]
    assert es._pushed_date(path, run, activity=carried) == date(2026, 10, 3)
    earlier = [{"before": first[0], "after": head, "timestamp": "2026-10-09T00:00:00Z"}] + carried
    assert es._pushed_date(path, run, activity=earlier) == date(2026, 10, 3), "a later push that did not add it is not the date"
    assert es._pushed_date(path, run, activity=[]) is None, "never pushed: no date"
    assert es._pushed_date(path, "no-such-run-anywhere", activity=carried) is None



def test_the_export_reads_holds_strictly_so_a_broken_file_never_releases_them(tmp_path):
    """The export applies docs/holds.json with the same strict loader as the publish, the worklists and
    the API deploy: no file is no hold, and a file that is not {"facility_ids": [...]} stops the run."""
    assert es.load_holds(tmp_path / "none.json") == set()
    good = tmp_path / "holds.json"
    good.write_text(json.dumps({"facility_ids": [" DEH2022-FFPP-000001 "]}), encoding="utf-8")
    assert es.load_holds(good) == {"DEH2022-FFPP-000001"}
    for bad in ('{"facility_ids": "DEH2022-FFPP-000001"}', "{not json", '{"facility_ids": [""]}', "[]"):
        good.write_text(bad, encoding="utf-8")
        with pytest.raises(SystemExit):
            es.load_holds(good)
