"""Write an invented export for the food-inspection site, in the shape the real one takes
(docs/FOOD_DATA_CONTRACT.md, version 3.1), so the site can be built and reviewed without
naming a real business.

Every place is fictional. Names carry the word "Sample", streets are made-up names ("Sample
Row", "Example Avenue"), meta.json carries ``"sample": true``, and the site shows a notice on
every page while that flag is set. Nothing here is drawn from any real inspection, and every
figure in meta.json is computed from the invented records, not measured.

What it writes, like the real export (``--out``, default food-dashboard/public/data):
  * ``facilities.geojson``, the index: one Point per listed place with only what the map, the
    list, the filters and the search need (facility_id, name, address, kind, district, last
    visit, the grade on record, record flags, and in ``bands`` mode band and points);
  * ``place/<facility_id>.json``, one file per place: the index entry plus the County's type,
    every County record (one entry per record, with the County's status text), the items cited
    in the 36 months before the last visit, and in ``bands`` mode the worksheet;
  * ``meta.json``: what the export is. In ``bands`` mode, a sample published rule of two counts
    with whole-number weights (``meta.card``), bands cut at tie boundaries so equal points are
    never split, and a backtest: the same rule as of an earlier date, checked against each
    place's next routine inspection, with each band's rate, the rate below the bands, and the
    "average score" comparison.

Only restaurants with a scored routine inspection in the year before the list date are scored;
markets, limited-preparation places and other restaurants carry neither points nor a band. One
banded place is put under review (``on_hold``) so the site's review state can be seen.

The generator is deterministic (seeded).

Usage
  python food-dashboard/scripts/make_sample_export.py                   # bands mode, 1,400 places
  python food-dashboard/scripts/make_sample_export.py --mode record --out /tmp/record/data
"""
from __future__ import annotations

import argparse
import json
import math
import random
import shutil
from datetime import date, timedelta
from pathlib import Path

SITE = Path(__file__).resolve().parents[1]
OUT = SITE / "public" / "data"

# Where invented places sit inside the City of San Diego: lat, lon, council district, a ZIP
# code, and a weight. Only the position is used; no neighbourhood or real street is named.
ANCHORS = [
    (32.827, -117.155, 6, "92111", 3), (32.748, -117.163, 3, "92103", 2), (32.748, -117.129, 3, "92104", 2),
    (32.712, -117.160, 3, "92101", 3), (32.723, -117.168, 3, "92101", 2), (32.797, -117.254, 2, "92109", 2),
    (32.748, -117.249, 2, "92107", 1), (32.735, -117.230, 2, "92106", 1), (32.818, -117.192, 2, "92117", 1),
    (32.785, -117.205, 2, "92110", 1), (32.847, -117.273, 1, "92037", 2), (32.871, -117.212, 1, "92122", 1),
    (32.939, -117.230, 1, "92130", 1), (32.916, -117.145, 6, "92126", 2), (32.833, -117.140, 6, "92123", 1),
    (33.020, -117.078, 5, "92128", 1), (32.906, -117.099, 5, "92131", 1), (32.960, -117.120, 5, "92129", 1),
    (32.768, -117.155, 7, "92108", 2), (32.787, -117.185, 7, "92111", 1), (32.822, -117.096, 7, "92124", 1),
    (32.774, -117.070, 9, "92115", 2), (32.750, -117.100, 9, "92105", 2), (32.762, -117.118, 9, "92116", 1),
    (32.697, -117.140, 8, "92113", 1), (32.552, -117.040, 8, "92173", 2), (32.573, -117.010, 8, "92154", 1),
    (32.712, -117.060, 4, "92114", 1), (32.685, -117.055, 4, "92139", 1), (32.700, -117.040, 4, "92114", 1),
]

# Obviously fictional street names: no invented place may read as a real address.
STREETS = [
    "Sample Row", "Example Avenue", "Placeholder Street", "Specimen Way", "Fictional Boulevard",
    "Mock Lane", "Demo Court", "Pretend Place", "Invented Road", "Testing Terrace",
]

TYPES = [("restaurant", 74), ("limited", 11), ("market", 15)]
BUSINESS_TYPES = {
    "restaurant": ["Restaurant Food Facility"],
    "limited": ["Low Risk Food Facility"],
    "market": ["Retail Market with Deli", "Retail Food Processing"],
}
KINDS = {
    "restaurant": ["Kitchen", "Taqueria", "Grill", "Noodle House", "Cafe", "Diner", "Pho House", "Sushi Bar", "Pizzeria", "Cantina"],
    "limited": ["Coffee Bar", "Juice Bar", "Tea House", "Snack Bar"],
    "market": ["Market", "Grocery", "Deli Market", "Carniceria"],
}

# Items on the County's report by theme, in the County's kind of wording.
ITEMS = {
    "temperature": [("7", "Proper hot and cold holding temperatures"), ("9", "Proper cooling methods"), ("10", "Proper cooking time and temperatures")],
    "handwashing": [("5", "Hands clean and properly washed"), ("6", "Adequate handwashing facilities supplied and accessible")],
    "hygiene": [("2", "Communicable disease; reporting, restrictions and exclusions"), ("4", "Proper eating, tasting, drinking or tobacco use")],
    "sanitizing": [("14", "Food contact surfaces clean and sanitized"), ("34", "Warewashing facilities installed, maintained and used"), ("40", "Wiping cloths properly used and stored")],
    "supplier": [("15", "Food obtained from approved source"), ("16", "Compliance with shell stock tags, condition, display")],
    "condition": [("17", "Food in good condition, safe and unadulterated"), ("20", "Returned and re-service of food")],
    "process": [("19", "Compliance with variance, specialized process, and HACCP plan")],
    "vermin": [("23", "No rodents, insects, birds or animals")],
    "plumbing": [("21", "Hot and cold water available"), ("22", "Sewage and wastewater properly disposed")],
    "storage": [("26", "Approved thawing methods used"), ("27", "Food separated and protected"), ("30", "Food storage; food storage containers identified")],
    "equipment": [("35", "Equipment and utensils approved, installed, clean, good repair"), ("38", "Adequate ventilation and lighting"), ("39", "Thermometers provided and accurate")],
    "labeling": [("1", "Demonstration of knowledge; food safety certification"), ("32", "Food properly labeled and honestly presented"), ("47", "Signs posted; last inspection report available")],
    "other": [("44", "Premises; personal and cleaning items"), ("45", "Floors, walls and ceilings built, maintained and clean"), ("42", "Garbage and refuse properly disposed")],
}
THEMES_BY_SEVERITY = {
    "major": [("temperature", 30), ("sanitizing", 14), ("vermin", 12), ("handwashing", 12), ("storage", 8), ("supplier", 4), ("condition", 3), ("process", 1), ("plumbing", 6), ("hygiene", 3)],
    "minor": [("temperature", 28), ("sanitizing", 16), ("handwashing", 14), ("storage", 12), ("labeling", 10), ("vermin", 6), ("plumbing", 6), ("supplier", 3), ("condition", 3), ("process", 1), ("hygiene", 3)],
    "grp": [("other", 35), ("equipment", 30), ("labeling", 15), ("sanitizing", 8), ("storage", 8), ("plumbing", 4)],
}
VISIT_TYPES = ("routine", "reinspection", "followup", "complaint")
SEVERITIES = ("major", "minor", "grp")
CLOSURES = ("health", "permit", "other")
THEMES = tuple(ITEMS)

RECORD_START = date(2023, 1, 1)
THROUGH = date(2026, 8, 31)
LIST_DATE = THROUGH + timedelta(days=1)
BACKTEST_AS_OF = date(2025, 9, 1)
YEAR = timedelta(days=365)
SHARES = ((0.025, "1"), (0.075, "2"), (0.175, "3"))

# The sample's published rule: two counts from the record, each with a whole-number weight.
RULE = [
    {"item": "avg_deficit", "label": "Points below 100, average routine score in the last year", "weight": 1,
     "unit": "per point below 100", "feature": "avg_deficit"},
    {"item": "theme_temperature", "label": "Food-temperature citations in the last year", "weight": 2,
     "unit": "per citation", "feature": "theme_temperature"},
]
RULE_TEXT = ("Places get one point for each point their average routine score in the last year fell "
             "below 100, and two points for each food-temperature citation in the last year.")
ELIGIBILITY = "restaurants with a scored routine inspection in the year before the list date"
INDEX_KEYS = ("facility_id", "name", "address", "facility_type", "council_district", "last_visit", "grade", "flags", "band", "points", "on_hold")


def grade(score: int) -> str:
    """The County's letter for a score. Used only when the sample invents a graded visit."""
    return "A" if score >= 90 else "B" if score >= 80 else "C"


def weighted(rng: random.Random, pairs):
    total = sum(w for _, w in pairs)
    x = rng.uniform(0, total)
    for item, w in pairs:
        x -= w
        if x <= 0:
            return item
    return pairs[-1][0]


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def record(d: date, kind: str, status="Complete", score=None, major=0, minor=0, grp=0, closure=None, reopened=None):
    """One County record, as the contract carries it."""
    graded = score is not None and kind in ("routine", "followup")
    return {"date": d.isoformat(), "status": status, "type": kind, "score": score, "grade": grade(score) if graded else None,
            "major": major, "minor": minor, "grp": grp, "closed": closure is not None, "closure": closure,
            "reopened": reopened if closure is not None else None}


def make_visits(rng: random.Random, latent: float):
    """County records from January 2023 to THROUGH: routine about once a year (twice for some), the
    County's re-grade visit after a B or C, its "Approved to Reopen" visit after a closure,
    reinspections (some on the same day, kept as their own record), and complaint visits."""
    out = []
    twice = rng.random() < 0.15
    d = RECORD_START + timedelta(days=rng.randint(0, 330))
    p_major = min(0.85, 0.04 + 1.1 * latent ** 2)
    while d <= THROUGH:
        major = (1 + (rng.random() < 0.15)) if rng.random() < p_major else 0
        minor = poisson(rng, 0.3 + 1.5 * latent)
        grp = poisson(rng, 1.0 + 3.0 * latent)
        # Most inspections that find a major still score 90 or more, as in the County's record.
        score = max(70, min(100, round(100 - 4 * major - minor - 0.5 * grp - rng.choice((0, 0, 0, 1, 2)))))
        if major and rng.random() < 0.15:
            f = d + timedelta(days=rng.randint(1, 4))
            reopened = f <= THROUGH
            out.append(record(d, "routine", "Ordered Closed", None, major, minor, grp, closure="health", reopened=reopened))
            if reopened:
                out.append(record(f, "followup", "Approved to Reopen", rng.randint(88, 97), 0, poisson(rng, 0.5), poisson(rng, 1.0)))
        elif rng.random() < 0.004:
            out.append(record(d, "routine", "Ordered Closed", score, major, minor, grp, closure="permit", reopened=False))
        else:
            out.append(record(d, "routine", "Complete", score, major, minor, grp))
            if score < 90:
                f = d + timedelta(days=rng.randint(7, 25))
                if f <= THROUGH:
                    out.append(record(f, "followup", "Complete", min(100, score + rng.randint(6, 12)), 0, poisson(rng, 0.4), poisson(rng, 1.0)))
        if major and rng.random() < 0.7:
            r = d + timedelta(days=rng.choice((0, 0, rng.randint(3, 14))))
            if r <= THROUGH:
                out.append(record(r, "reinspection", "Complete", None, int(rng.random() < 0.1), poisson(rng, 0.3), 0))
        if rng.random() < 0.03 + 0.2 * latent:
            c = d + timedelta(days=rng.randint(20, 200))
            if c <= THROUGH:
                out.append(record(c, "complaint", "Complete", None, poisson(rng, 0.2 * latent), poisson(rng, 0.4), poisson(rng, 0.3)))
        gap = (182 if twice else 365) * rng.uniform(0.75, 1.3)
        d = d + timedelta(days=int(gap))
    if not out:
        out.append(record(THROUGH - timedelta(days=rng.randint(30, 300)), "routine", "Complete", rng.randint(92, 100), 0, poisson(rng, 0.5), poisson(rng, 1.0)))
    order = {"routine": 0, "followup": 1, "reinspection": 2, "complaint": 3}
    out.sort(key=lambda x: (x["date"], order[x["type"]]))
    return out


def make_violations(rng: random.Random, inspections):
    """One row per item cited at every County record. `visit` is the record's visit type."""
    rows = []
    for insp in inspections:
        for sev in SEVERITIES:
            for _ in range(insp[sev]):
                theme = weighted(rng, THEMES_BY_SEVERITY[sev])
                code, desc = rng.choice(ITEMS[theme])
                rows.append({"date": insp["date"], "visit": insp["type"], "code": code, "theme": theme, "severity": sev, "description": desc})
    return rows


def exported(violations, inspections):
    """Items cited in the 36 months before the last visit, majors first, then newest, at most 60."""
    last = date.fromisoformat(inspections[-1]["date"])
    cutoff = (last - timedelta(days=int(36 * 30.44))).isoformat()
    keep = [v for v in violations if v["date"] >= cutoff]
    rank = {s: i for i, s in enumerate(SEVERITIES)}
    keep.sort(key=lambda v: v["date"], reverse=True)
    keep.sort(key=lambda v: rank[v["severity"]])
    return keep[:60]


def in_year_before(d: str, end: date) -> bool:
    return (end - YEAR).isoformat() <= d <= end.isoformat()


def grade_on_record(inspections):
    """The latest letter from a routine or re-grade record; `replaced` is the routine B or C a
    re-grade replaced."""
    graded = [i for i in inspections if i["grade"] and i["type"] in ("routine", "followup")]
    if not graded:
        return None
    latest = graded[-1]
    out = {"grade": latest["grade"], "score": latest["score"], "date": latest["date"], "replaced": None}
    if latest["type"] == "followup":
        before = [i for i in graded[:-1] if i["type"] == "routine"]
        if before and before[-1]["grade"] in ("B", "C"):
            r = before[-1]
            out["replaced"] = {"grade": r["grade"], "score": r["score"], "date": r["date"]}
    return out


def record_flags(inspections, violations):
    """Record facts from the 12 months before the last visit, as the index carries them."""
    last = date.fromisoformat(inspections[-1]["date"])
    window = [i for i in inspections if in_year_before(i["date"], last)]
    flags = []
    if any(i["major"] > 0 for i in window):
        flags.append("major")
    if any(i["closed"] and i["closure"] == "health" for i in window):
        flags.append("closed")
    if any(i["type"] == "routine" and i["grade"] in ("B", "C") for i in window):
        flags.append("bc")
    if sum(1 for i in window if i["type"] == "reinspection") >= 2:
        flags.append("repeat")
    majors = {v["theme"] for v in violations if v["severity"] == "major" and in_year_before(v["date"], last)}
    flags.extend(t for t in THEMES if t in majors)
    return flags


def rule_values(place, as_of: date):
    """The rule's counts for a place from its record in the year before `as_of`, or None when the
    place is not scored (not a restaurant, or no scored routine inspection in that year)."""
    if place["facility_type"] != "restaurant":
        return None
    lo, hi = (as_of - YEAR).isoformat(), as_of.isoformat()
    scores = [i["score"] for i in place["inspections"] if i["type"] == "routine" and i["score"] is not None and lo <= i["date"] < hi]
    if not scores:
        return None
    avg = sum(scores) / len(scores)
    temp = sum(1 for v in place["all_violations"] if v["theme"] == "temperature" and v["severity"] != "grp" and lo <= v["date"] < hi)
    return {"avg_deficit": max(0, round(100 - avg)), "theme_temperature": temp}, avg


def worksheet(values):
    rows = []
    for it in RULE:
        v = values[it["feature"]]
        pts = it["weight"] * v
        rows.append({"item": it["item"], "weight": it["weight"], "value": v, "points": pts, "met": pts > 0})
    return rows, sum(r["points"] for r in rows)


def band_cuts(points_desc):
    """Band stops over a list of points sorted high first, each moved to the nearest boundary
    between tie groups so equal points are never split across a band edge."""
    n = len(points_desc)
    bounds = [0] + [i for i in range(1, n) if points_desc[i] != points_desc[i - 1]] + [n]
    stops, prev = [], 0
    for share, _ in SHARES:
        target = round(share * n)
        best = min((b for b in bounds if b >= prev), key=lambda b: (abs(b - target), b))
        stops.append(best)
        prev = best
    return stops


def band_for(position, stops):
    for (share, key), stop in zip(SHARES, stops):
        if position < stop:
            return key
    return None


def wilson(k: int, n: int):
    if not n:
        return [None, None]
    z, p = 1.96, k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, mid - half), 4), round(min(1.0, mid + half), 4)]


def next_routine(place, as_of: date):
    """The first routine inspection in the year from `as_of`: the backtest's label."""
    lo, hi = as_of.isoformat(), (as_of + YEAR).isoformat()
    for i in place["inspections"]:
        if i["type"] == "routine" and lo <= i["date"] < hi:
            return i
    return None


def make_place(rng: random.Random, i: int):
    lat, lon, district, zipcode, _ = weighted(rng, [(a, a[4]) for a in ANCHORS])
    ftype = weighted(rng, TYPES)
    latent = min(0.98, max(0.02, rng.betavariate(2, 5) + {"restaurant": 0.06, "limited": -0.08}.get(ftype, 0.0)))
    inspections = make_visits(rng, latent)
    violations_all = make_violations(rng, inspections)
    return {
        "id": f"SAMPLE-FFPP-{i:05d}",
        "name": f"Sample {rng.choice(KINDS[ftype])} {i:04d}",
        "address": f"{rng.randint(100, 9899)} {rng.choice(STREETS)}, San Diego, CA {zipcode}",
        "facility_type": ftype,
        "business_type": rng.choice(BUSINESS_TYPES[ftype]),
        "district": district,
        "coords": [round(lon + rng.gauss(0, 0.007), 6), round(lat + rng.gauss(0, 0.006), 6)],
        "inspections": inspections,
        "all_violations": violations_all,
        "violations": exported(violations_all, inspections),
    }


def scored_order(places, as_of):
    """Eligible places with their rule values, points high first, then name (the site's order)."""
    rows = []
    for j, p in enumerate(places):
        got = rule_values(p, as_of)
        if got is None:
            continue
        values, avg = got
        sheet, pts = worksheet(values)
        rows.append({"j": j, "points": pts, "avg": avg, "sheet": sheet, "name": p["name"]})
    rows.sort(key=lambda r: (-r["points"], r["name"]))
    return rows


def backtest(places):
    """The same rule as of BACKTEST_AS_OF, checked against each place's next routine inspection."""
    rows = scored_order(places, BACKTEST_AS_OF)
    stops = band_cuts([r["points"] for r in rows])
    for r in rows:
        nxt = next_routine(places[r["j"]], BACKTEST_AS_OF)
        r["labelled"] = nxt is not None
        r["positive"] = bool(nxt and nxt["major"] > 0)
    base_rows = sorted(rows, key=lambda r: (r["avg"], r["name"]))

    def stats(members):
        lab = [r for r in members if r["labelled"]]
        k = sum(1 for r in lab if r["positive"])
        return len(members), len(lab), k, (round(k / len(lab), 4) if lab else None), wilson(k, len(lab))

    bands, start = {}, 0
    for (share, key), stop in zip(SHARES, stops):
        members = rows[start:stop]
        n, n_lab, k, rate, iv = stats(members)
        b_n, b_lab, b_k, b_rate, _ = stats(base_rows[start:stop])
        d = k - b_k
        se = 1.96 * math.sqrt(max(1, k + b_k) * 0.5)
        bands[key] = {"places": n, "labelled": n_lab, "positives": k, "rate": rate, "interval": iv,
                      "baseline_rate": b_rate, "vs_baseline": [round(d - se, 3), round(d + se, 3)]}
        start = stop
    rest = rows[start:]
    n, n_lab, k, rate, iv = stats(rest)
    rest_row = {"band": "rest", "places": n, "labelled": n_lab, "positives": k, "rate": rate, "interval": iv}
    positives = sum(1 for r in rows if r["positive"])
    return bands, rest_row, {"candidates": len(rows), "positives": positives, "labelled": sum(1 for r in rows if r["labelled"])}


def build(n_places: int = 1400, seed: int = 9, mode: str = "bands"):
    """(index FeatureCollection, {facility_id: place file}, meta) for `n_places` invented places."""
    if mode not in ("bands", "record"):
        raise ValueError(f"mode must be bands or record, not {mode!r}")
    rng = random.Random(seed)
    places = [make_place(rng, i + 1) for i in range(n_places)]

    band_of, points_of, sheet_of, stability_of = {}, {}, {}, {}
    meta_bands, rest_row, cr = [], None, None
    if mode == "bands":
        now = scored_order(places, LIST_DATE)
        stops = band_cuts([r["points"] for r in now])
        for pos, r in enumerate(now):
            pid = places[r["j"]]["id"]
            points_of[pid] = r["points"]
            sheet_of[pid] = r["sheet"]
            key = band_for(pos, stops)
            if key:
                band_of[pid] = key
            stability_of[pid] = round(min(1.0, max(0.0, 0.55 + 0.4 * rng.random())), 2)
        # One banded place is put under review, so the site's review state can be seen.
        held = sorted(pid for pid, b in band_of.items() if b == "2")[:1]
        back_bands, rest_row, cr = backtest(places)
        # Bands are cut-offs: min_points is the band's cut-off, max_points the next higher band's
        # cut-off minus one, and the top band has no upper limit (max_points null).
        higher = None
        for (share, key), stop in zip(SHARES, stops):
            mine = [points_of[pid] for pid, b in band_of.items() if b == key and pid not in held]
            cut = min(points_of[pid] for pid, b in band_of.items() if b == key) if any(b == key for b in band_of.values()) else None
            row = {"band": key, "min_points": cut, "max_points": None if higher is None else higher - 1,
                   "share": share, "places_now": len(mine)}
            if cut is not None:
                higher = cut
            row.update(back_bands[key])
            kept = [stability_of[pid] for pid, b in band_of.items() if b == key and pid not in held]
            row["kept_in_refits"] = round(sum(kept) / len(kept), 3) if kept else None
            meta_bands.append(row)
    else:
        held = []

    features, place_files = [], {}
    for p in places:
        props = {
            "facility_id": p["id"],
            "name": p["name"],
            "address": p["address"],
            "facility_type": p["facility_type"],
            "council_district": p["district"],
            "last_visit": {"date": p["inspections"][-1]["date"], "type": p["inspections"][-1]["type"]},
            "grade": grade_on_record(p["inspections"]),
            "flags": record_flags(p["inspections"], p["all_violations"]),
        }
        detail = {"business_type": p["business_type"], "inspections": p["inspections"], "violations": p["violations"]}
        if p["id"] in held:
            props["on_hold"] = True
        elif p["id"] in points_of:
            if p["id"] in band_of:
                props["band"] = band_of[p["id"]]
            props["points"] = points_of[p["id"]]
            detail["score_card"] = sheet_of[p["id"]]
            detail["band_stability"] = stability_of[p["id"]]
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": p["coords"]}, "properties": props})
        place_files[p["id"]] = {**props, **detail}

    graded = [i for p in places for i in p["inspections"] if i["type"] == "routine" and i["grade"]]
    graded_major = [i for i in graded if i["major"] > 0]
    grade_context = {
        "majors_graded_A_share": round(sum(1 for i in graded_major if i["grade"] == "A") / len(graded_major), 4) if graded_major else None,
        "graded_A_share": round(sum(1 for i in graded if i["grade"] == "A") / len(graded), 4) if graded else None,
    }
    meta = {
        "mode": mode,
        "sample": True,
        "run": "sample",
        "generated": LIST_DATE.isoformat(),
        "places": len(features),
        "inspections_through": THROUGH.isoformat(),
        "expires": None,
        "source": {"name": "invented sample; no real facility or inspection", "url": None},
        "grade_context": grade_context,
        "data_rules": {"note": "sample: invented records, one entry per County record, statuses as the County writes them"},
        "survivorship": "In this sample every place is invented, so none is missing. A real export's backtest holds only places that still exist when the County's results are collected.",
        "provenance": {"code_sha": "sample", "pull_sha256": None, "python": None, "packages": {}},
        "contact": None,
        "operator": None,
        "corrections": [],
        "publication": None,
    }
    if mode == "bands":
        meta.update({
            "model": f"sample published rule ({len(RULE)} counts, whole-number weights), invented",
            "label": "at least one major violation at the next routine inspection",
            "label_window": f"{LIST_DATE.isoformat()} to {(LIST_DATE + YEAR - timedelta(days=1)).isoformat()}",
            "candidates": len(points_of),
            "card": {
                "items": RULE,
                "rule": RULE_TEXT,
                "window": "the year before the list date",
                "trained_on": "sample: invented weights",
                "eligibility": ELIGIBILITY,
                "baseline_name": "average score",
                "bands": meta_bands,
                "rest": rest_row,
            },
            "catch": {},
            "catch_run": {
                "as_of": BACKTEST_AS_OF.isoformat(),
                "candidates": cr["candidates"],
                "positives": cr["positives"],
                "labelled": cr["labelled"],
                "unlabelled": cr["candidates"] - cr["labelled"],
                "label_window": f"{BACKTEST_AS_OF.isoformat()} to {(BACKTEST_AS_OF + YEAR - timedelta(days=1)).isoformat()}",
                "trained_on": "sample: the rule is invented, not fitted",
                "baseline_name": "average score",
            },
            "selection": {"rule": "sample: no selection was run", "chosen": "sample rule"},
            "named_bands": [key for _, key in SHARES],
            "cost_ratio": None,
            "utility": None,
            "fairness": {},
            "measurement": dict(grade_context),
        })
    return {"type": "FeatureCollection", "features": features}, place_files, meta


def write(out: Path, fc, place_files, meta) -> None:
    """Write the export in the v3 layout, replacing any earlier place files."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "facilities.geojson").write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    pdir = out / "place"
    if pdir.exists():
        shutil.rmtree(pdir)
    pdir.mkdir()
    for pid, doc in place_files.items():
        (pdir / f"{pid}.json").write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--places", type=int, default=1400, help="listed places")
    ap.add_argument("--seed", type=int, default=9)
    ap.add_argument("--mode", choices=("bands", "record"), default="bands")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    fc, place_files, meta = build(args.places, args.seed, args.mode)
    write(args.out, fc, place_files, meta)
    size = (args.out / "facilities.geojson").stat().st_size
    print(f"wrote {len(fc['features'])} sample places ({args.mode} mode) to {args.out}: index {size / 1e6:.2f} MB, {len(place_files)} place files")
    if args.mode == "bands":
        def points(b):
            return f"{b['min_points']} points or more" if b["max_points"] is None else f"{b['min_points']} to {b['max_points']} points"
        print("bands: " + ", ".join(f"{b['band']} {b['places_now']} places, {points(b)}, rate {b['rate']}" for b in meta["card"]["bands"])
              + f"; rest rate {meta['card']['rest']['rate']}; {meta['candidates']} scored")


if __name__ == "__main__":
    main()
