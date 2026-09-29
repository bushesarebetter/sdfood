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
    assert e == {"rate": c["rate"][-1], "low": c["low"][-1], "high": c["high"][-1]}


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


def test_archive_is_write_once_and_registration_is_one_per_rule_version(built, tmp_path):
    fc, details, meta, extra = built
    d, new = es.archive(tmp_path, meta, extra["ranking"])
    assert new and (d / "manifest.json").exists()
    assert es.archive(tmp_path, meta, extra["ranking"])[1] is False, "never overwritten"
    with gzip.open(d / "ranking.csv.gz", "rt", encoding="utf-8") as fh:
        header = fh.readline().strip().split(",")
    assert {"facility_id", "points", "band", "average_rule", "persistence", "district"} <= set(header)
    v1 = {**meta, "frozen": {"version": "2026-09-22-aaaaaaaa"}}
    reg = es.register(tmp_path, v1, prospective_dir=tmp_path / "prospective")
    regs = json.loads(reg.read_text(encoding="utf-8"))["registrations"]
    assert [(r["run"], r["version"]) for r in regs] == [(meta["run"], "2026-09-22-aaaaaaaa")]
    with pytest.raises(SystemExit, match="already registers rule version"):
        es.register(tmp_path, v1, prospective_dir=tmp_path / "prospective")
    es.register(tmp_path, {**meta, "frozen": {"version": "2027-01-05-bbbbbbbb"}}, prospective_dir=tmp_path / "prospective")
    assert len(es._registrations(reg)) == 2, "a refit rule gets its own registration; the first is kept"
    results = es.monitor(tmp_path, extra["places"], today=date(2027, 3, 1), log=lambda *_: None)
    r = results[0]
    assert r["run"] == meta["run"] and (tmp_path / "monitor.json").exists()
    assert r["complete"] is False, "fewer than 365 days after the list: interim"
    assert set(r) >= {"city", "outside", "missing_from_later_pull"}
    assert r["city"]["labelled"] + r["outside"]["labelled"] == r["labelled"]
    gone = es.monitor(tmp_path, extra["places"][1:], today=date(2027, 3, 1), log=lambda *_: None)[0]
    assert sum(gone["missing_from_later_pull"].values()) >= 1, "a place gone from the later pull is counted, not dropped"


def test_an_older_single_registration_is_still_read(tmp_path):
    (tmp_path / "REGISTERED.json").write_text(json.dumps({"run": "forward_2026-09-01", "ranking_sha256": "x"}))
    assert [r["run"] for r in es._registrations(tmp_path / "REGISTERED.json")] == ["forward_2026-09-01"]
    assert es._registrations(tmp_path / "missing.json") == []


def _monitor_row(run, *, days=400, complete=True, b1=(400, [0.55, 0.7], 0.62), all_rate=0.2):
    n, interval, rate = b1
    return {"run": run, "days": days, "complete": complete, "labelled": 2000, "positives": 500, "bands": {},
            "city": {"labelled": 1500, "all_rate": all_rate, "bands": {"1": {"labelled": n, "positives": int(n * rate),
                                                                          "rate": rate, "interval": interval}}},
            "rule_minus_average": [0.01, 0.03]}


def test_the_prospective_gate(built, tmp_path, monkeypatch):
    fc, details, meta, extra = built
    ok, why = es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p")
    assert not ok and "no registered run" in why
    es.archive(tmp_path, meta, extra["ranking"])
    frozen = {**meta, "frozen": {"version": "2026-09-22-aaaaaaaa"}}
    es.register(tmp_path, frozen, prospective_dir=tmp_path / "p")
    v = "2026-09-22-aaaaaaaa"
    assert "for rule version 2027" in es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p", version="2027-01-01-cccccccc")[1], \
        "a registration tests only the rule version it was made for"
    monkeypatch.setattr(es, "_git_date", lambda path: None)
    assert "not committed" in es.prospective_ok(tmp_path, 1.0, prospective_dir=tmp_path / "p", version=v)[1]
    monkeypatch.setattr(es, "_git_date", lambda path: date(2026, 9, 22))
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


def test_drift_asks_for_a_refit_when_the_record_moves():
    fitted = {"label_quarters": ["2025Q1", "2025Q2"], "card": {"rows": [{"band": "1", "share": 0.12}]}}
    m = {"major_rate_by_quarter": {"2025Q1": 0.20, "2025Q2": 0.22, "2026Q1": 0.21, "2026Q2": 0.20, "2026Q3": 0.05}}
    d = es.drift_check(m, fitted, 0.13)
    assert d["refit_needed"] is False and d["major_rate_backtest"] == 0.21 and d["major_rate_recent"] == 0.205
    m["major_rate_by_quarter"].update({"2026Q1": 0.30, "2026Q2": 0.31})
    d = es.drift_check(m, fitted, 0.13)
    assert d["refit_needed"] and "routine major rate" in d["reasons"][0], "the last full quarters, not the one in progress"
    d = es.drift_check({"major_rate_by_quarter": {}}, fitted, 0.25)
    assert d["refit_needed"] and "band 1 holds 25.0%" in d["reasons"][0]
    assert es.drift_check({}, {"card": {"rows": []}}, None)["refit_needed"] is False


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


def test_escalation_flags_follow_the_countys_own_criteria():
    closed = lambda day: inspection(day, score="0", grade="", status="Ordered Closed", violations=[violation(VERMIN, "major")])
    p = _place([inspection("2025-01-10", violations=[violation(VERMIN, "major")]), closed("2025-06-02"),
                inspection("2025-06-05", kind="Re-inspection", score="0", grade="", status="Approved to Reopen"),
                inspection("2025-11-03", violations=[violation(VERMIN, "major")]), closed("2026-05-04")])
    recs = es.display_records(p)
    f = es.flags(recs, p["visits"])
    assert "closures2" in f, "two closure orders in two years"
    assert "repeat_item" in f, "item 23 major at 2 of the last 3 routine inspections"
    q = _place([inspection("2025-01-10", violations=[violation(VERMIN, "major")]), inspection("2025-11-03")])
    assert not {"closures2", "repeat_item"} & set(es.flags(es.display_records(q), q["visits"]))


def test_the_worksheet_lists_the_scores_it_averages_and_rounds_half_up():
    p = _place([inspection("2025-02-01", score="95"), inspection("2025-08-01", score="94"),
                inspection("2026-01-15", score="0", grade="", status="Ordered Closed", violations=[violation(VERMIN, "major")])])
    used = es.scores_used(p, "2026-09-20")
    assert [u["score"] for u in used] == [95, 94, es.CLOSURE_SCORE] and [u["closure"] for u in used] == [False, False, True]
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
