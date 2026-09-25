"""export_site.py (v3): the data rules, what the site shows, the as-of logic, the rules and bands,
fairness, approval and notices, the prospective gate, archiving and publishing, and end-to-end
builds on an invented county whose output must pass the site's own contract check."""
import csv
import gzip
import json
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
        inspection("2024-04-10", status="Incomplete"),
        inspection("2024-05-10", score="96"),
    ])], st)[0]
    assert [v["date"] for v in p["visits"]] == ["2024-05-10"]
    assert sum(st.dropped.values()) == 4


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


def test_themes_on_the_two_report_forms():
    th = es.theme_of
    assert th("22. No rodents, insects, birds or animals") == "vermin"
    assert th("22. Sewage & wastewater properly disposed") == "plumbing"
    assert th("19. Potable hot and cold water available") == "plumbing"
    assert th("30. Warewashing facilities - installed, maintained, used; Test strips available") == "sanitizing"
    assert th("16. Compliance with shell stock tags, condition, display") == "supplier"
    assert th("13. Food in good condition, safe & unadulterated") == "condition"
    assert th("18. Compliance with:") == "process"
    assert th("39. Compliance with fire safety requirements - first aid kit") == "other"
    assert th("20. Toilet and handwashing sink facility readily available") == "handwashing"


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


def test_bands_never_split_a_tie_and_overlapping_bands_merge():
    pts = np.array([20] * 30 + [15] * 60 + [10] * 200 + [5] * 700, dtype=float)
    elig = np.ones(len(pts), bool)
    cuts = es.band_thresholds(pts)
    bands = es.assign_bands(pts, elig, cuts)
    for v in np.unique(pts):
        assert len({b for b, p in zip(bands, pts) if p == v}) == 1, "a tie is never split"
    positive = np.zeros(len(pts))
    positive[:15] = 1                   # 20 points: 50%
    positive[30:45] = 1                 # 15 points: 25%
    positive[90:140] = 1                # 10 points: 25%
    merged = es.merge_overlapping(cuts, pts, positive, elig, elig)
    rows, rest = es.band_rows(es.assign_bands(pts, elig, merged), pts, positive, elig, elig)
    for a, b in zip(rows, rows[1:]):
        assert a["interval"][0] > b["interval"][1], "adjacent bands are distinguishable"
    assert rest["places"] + sum(r["places"] for r in rows) == len(pts)


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
            "responsible_adult": {"name": "C D", "contact": "cd@example.org"},
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
def built():
    return es.build(invented_county(), DISTRICTS, pull=PULL, approval=None, today=date(2026, 9, 22), refits=2, log=lambda *_: None)


def test_build_lists_every_city_place_with_scores_where_eligible(built):
    fc, details, meta, extra = built
    props = [f["properties"] for f in fc["features"]]
    assert props and all(p["facility_type"] in es.PUBLIC_KINDS and p["council_district"] in (1, 2) for p in props)
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
    approval = tmp_path / "approval.json"
    approval.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(es, "SITE_DATA", tmp_path / "public_data")
    problems = es.publish(tmp_path / "out", fc, details, meta, approval_path=approval, today=date(2026, 9, 22))
    assert problems == [], problems
    shipped = json.loads((tmp_path / "public_data" / "meta.json").read_text(encoding="utf-8"))
    idx = json.loads((tmp_path / "public_data" / "facilities.geojson").read_text(encoding="utf-8"))
    assert shipped["publication"]["facilities_sha256"] == es.sha256_file(tmp_path / "public_data" / "facilities.geojson")
    assert idx["features"] and all(f["properties"]["band"] == "1" for f in idx["features"])


def test_archive_is_write_once_and_registration_is_single(built, tmp_path):
    fc, details, meta, extra = built
    d, new = es.archive(tmp_path, meta, extra["ranking"])
    assert new and (d / "manifest.json").exists()
    assert es.archive(tmp_path, meta, extra["ranking"])[1] is False, "never overwritten"
    with gzip.open(d / "ranking.csv.gz", "rt", encoding="utf-8") as fh:
        header = fh.readline().strip().split(",")
    assert {"facility_id", "points", "band", "average_rule", "persistence"} <= set(header)
    reg = es.register(tmp_path, meta, prospective_dir=tmp_path / "prospective")
    assert json.loads(reg.read_text(encoding="utf-8"))["run"] == meta["run"]
    with pytest.raises(SystemExit):
        es.register(tmp_path, meta, prospective_dir=tmp_path / "prospective")
    results = es.monitor(tmp_path, extra["places"], today=date(2027, 3, 1), log=lambda *_: None)
    assert results and results[0]["run"] == meta["run"] and (tmp_path / "monitor.json").exists()


def test_the_prospective_gate(built, tmp_path, monkeypatch):
    fc, details, meta, extra = built
    ok, why = es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p")
    assert not ok and "no registered run" in why
    es.archive(tmp_path, meta, extra["ranking"])
    es.register(tmp_path, meta, prospective_dir=tmp_path / "p")
    monkeypatch.setattr(es, "_git_date", lambda path: None)
    assert "not committed" in es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p")[1]
    monkeypatch.setattr(es, "_git_date", lambda path: date(2026, 9, 22))
    assert "90" in es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p", today=date(2026, 10, 1))[1]
    (tmp_path / "monitor.json").write_text(json.dumps([{"run": meta["run"], "labelled": 400, "positives": 150,
                                                         "bands": {"1": {"interval": [0.55, 0.7]}}, "rule_minus_average": [0.01, 0.03]}]))
    ok, why = es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p", today=date(2027, 1, 1))
    assert ok, why
    assert not es.prospective_ok(tmp_path, 3.0, prospective_dir=tmp_path / "p", today=date(2027, 1, 1))[0], "0.55 < 0.75"


def test_the_committed_site_data_is_the_invented_sample():
    """Real names never enter the repository: the site's committed data is the sample."""
    meta = json.loads((SITE / "public" / "data" / "meta.json").read_text(encoding="utf-8"))
    assert meta["sample"] is True


def test_facility_ids_are_unique_even_when_the_county_repeats_one():
    raw = [business("1", [inspection("2025-06-01")]), business("2", [inspection("2025-06-01")])]
    for b in raw:
        for i in b["inspections"]:
            i["custom_id"] = "DEH2024-FFPP-000009"
    places, _, _ = es.prepare(raw, DISTRICTS)
    assert len({p["facility_id"] for p in places}) == 2
