"""Write an invented export for the food-inspection site, in the shape the real one takes
(docs/FOOD_DATA_CONTRACT.md), so the site can be built and reviewed without naming a real
business.

Every place is fictional. Names carry the word "Sample", streets are made-up names ("Sample
Row", "Example Avenue"), meta.json carries ``"sample": true``, and the site shows a notice on
every page while that flag is set. Nothing here is drawn from any real inspection, and every
figure in meta.json is computed from the invented records, not measured.

What it writes, like the real export (``--out``, default food-dashboard/public/data):
  * ``facilities.geojson``, the index: one Point per listed place with only what the map, the
    list, the filters and the search need (facility_id, name, address, kind, district, last
    visit with the County's own type text on it, the grade on record, record flags counted back
    from the list date, and in ``bands`` mode band and points);
  * ``place/<facility_id>.json``, one file per place: the index entry plus the County's type,
    every record kept (one entry per record, with the County's status text, its inspection
    type as ``county_type`` and its notes as ``notes``, all verbatim; a closure carries
    ``reopened_on``), the items cited in the 36 months before the last visit, each under the
    section of the County's report its item number falls in (at most 150, majors first), the
    counts by theme of every item in that window before the cut (``theme_counts``,
    ``violations_total``), and in ``bands`` mode the worksheet (``scores_used`` with a health
    closure read as 70 and the County's own score beside it);
  * ``meta.json``: what the export is. In ``bands`` mode, a sample of the students' point rule,
    two counts with whole-number weights (``meta.card``), bands cut at tie boundaries so equal
    points are never split, and a backtest: the same rule as of an earlier date, checked against
    each place's next routine inspection, with each band's rate, the rate below the bands, band 1
    split by how its places got there (``band_1_by_route``), the "average score" comparison, two
    estimate curves (``curve`` for places whose scored year includes no health closure,
    ``curve_closure`` for those whose year does, each place's ``estimate.group`` naming the one it
    reads), the rates with the label cut off after 90, 180 and 270 days (``interim``), each
    district's precision and share of the wrongly named with bootstrap intervals (95%, family-wise,
    and family-wise widened for an assumed design effect of 2), and the frozen-rule and drift fields
    the real export carries (drift as export_site.drift_check: the label year month by month, and
    the latest quarter against the label year's months before it).

The record also shows, on a few places each, what the real export keeps and reads since round 5:
a closure only a later "Approved to Reopen" shows (``closure_inferred``), an "Approved to Reopen"
no closure could be placed before (``reopen_without_closure``), the County's "Status Verification"
records that cite items or are "Ordered Closed" (type ``status_check``), "Self Closed" records
(one citing a major starts a closure, read as the operator's own), and a grade whose last closure
has no reopening on record (``grade.open_closure``). They come from their own random stream, and
the records added fall where no count the rule, the flags or the backtest reads can see them, so
the rest of the sample is what it was. In ``bands`` mode, ``monitor_summary.json`` says the
forward test is "too early": the sample has no forward runs, so it has no alert and no figures by
council district.

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
import hashlib
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

# Themes are the sections of the County's own inspection report, in the site's order
# (lib/inspections.js THEMES). "other" is an item no section holds; it is never a flag.
THEMES = ("knowledge", "health", "hands", "handsink", "temperature", "condition", "sanitizing", "supplier", "process",
          "advisory", "hsp", "water", "sewage", "vermin", "grp_staff", "grp_food", "grp_storage", "grp_equipment",
          "grp_facility", "grp_signs", "grp_other", "other")


def _form(spec):
    """{item number: theme} from [(theme, items)], an item a number, a "1a" or an inclusive (lo, hi) range."""
    out = {}
    for theme, items in spec:
        for it in items:
            if isinstance(it, tuple):
                out.update({str(n): theme for n in range(it[0], it[1] + 1)})
            else:
                out[str(it)] = theme
    return out


# The section of each item number on the County's fixed-facility form (47 and on are signs and permits).
FIXED_FORM = _form([
    ("knowledge", ["1a", "1b"]), ("health", [(2, 4)]), ("hands", [5]), ("handsink", [6]), ("temperature", [(7, 11)]),
    ("condition", [12, 13]), ("sanitizing", [14]), ("supplier", [(15, 17)]), ("process", [18]), ("advisory", [19]),
    ("hsp", [20]), ("water", [21]), ("sewage", [22]), ("vermin", [23]), ("grp_staff", [24, 25]), ("grp_food", [(26, 29)]),
    ("grp_storage", [(30, 32)]), ("grp_equipment", [(33, 40)]), ("grp_facility", [(41, 46)]), ("grp_signs", [(47, 99)]),
])
# The mobile form: 1a to 15 as on the fixed form, then its own numbering (39 is fire safety). The
# sample lists no mobile unit; the mapping is here so the two forms are stated in one place.
MOBILE_FORM = {**{k: v for k, v in FIXED_FORM.items() if not k.isdigit() or int(k) <= 15}, **_form([
    ("advisory", [18]), ("water", [19]), ("handsink", [20]), ("sewage", [21]), ("vermin", [22]), ("grp_staff", [23]),
    ("grp_food", [(24, 27)]), ("grp_storage", [28, 29]), ("grp_equipment", [(30, 32), (34, 36)]),
    ("grp_facility", [33, 37, 38, 40]), ("grp_other", [39]), ("grp_signs", [41, 42]),
])}

# Items on the County's fixed-facility report by section, in the County's kind of wording.
ITEMS = {
    "knowledge": [("1a", "Demonstration of knowledge; food safety certification"), ("1b", "Food handler cards")],
    "health": [("2", "Communicable disease; reporting, restrictions and exclusions"), ("3", "No discharge from eyes, nose and mouth"),
               ("4", "Proper eating, tasting, drinking or tobacco use")],
    "hands": [("5", "Hands clean and properly washed; gloves used properly")],
    "handsink": [("6", "Adequate handwashing facilities supplied and accessible")],
    "temperature": [("7", "Proper hot and cold holding temperatures"), ("8", "Time as a public health control; procedures and records"),
                    ("9", "Proper cooling methods"), ("10", "Proper cooking time and temperatures"), ("11", "Proper reheating procedures for hot holding")],
    "condition": [("12", "Returned and reservice of food"), ("13", "Food in good condition, safe and unadulterated")],
    "sanitizing": [("14", "Food contact surfaces clean and sanitized")],
    "supplier": [("15", "Food obtained from approved source"), ("16", "Compliance with shell stock tags, condition, display"),
                 ("17", "Compliance with Gulf Oyster Regulations")],
    "process": [("18", "Compliance with variance, specialized process, and HACCP plan")],
    "advisory": [("19", "Consumer advisory provided for raw or undercooked foods")],
    "hsp": [("20", "Licensed health care facilities and schools: prohibited foods not offered")],
    "water": [("21", "Hot and cold water available")],
    "sewage": [("22", "Sewage and wastewater properly disposed")],
    "vermin": [("23", "No rodents, insects, birds or animals")],
    "grp_staff": [("24", "Person in charge present and performs duties"), ("25", "Personal cleanliness and hair restraints")],
    "grp_food": [("26", "Approved thawing methods used; frozen food"), ("27", "Food separated and protected"),
                 ("28", "Washing fruits and vegetables"), ("29", "Toxic substances properly identified, stored and used")],
    "grp_storage": [("30", "Food storage; food storage containers identified"), ("31", "Consumer self-service"),
                    ("32", "Food properly labeled and honestly presented")],
    "grp_equipment": [("33", "Nonfood-contact surfaces clean"), ("34", "Warewashing facilities installed, maintained and used; test strips"),
                      ("35", "Equipment and utensils approved, installed, clean, good repair"), ("38", "Adequate ventilation and lighting"),
                      ("39", "Thermometers provided and accurate"), ("40", "Wiping cloths properly used and stored")],
    "grp_facility": [("41", "Plumbing; proper backflow devices"), ("42", "Garbage and refuse properly disposed"),
                     ("43", "Toilet facilities properly constructed, supplied and cleaned"), ("44", "Premises; personal and cleaning items; vermin-proofing"),
                     ("45", "Floors, walls and ceilings built, maintained and clean")],
    "grp_signs": [("47", "Signs posted; last inspection report available"), ("49", "Permits available")],
}
# Majors and minors fall on items 1a to 23; good-retail-practice items on 24 and on.
THEMES_BY_SEVERITY = {
    "major": [("temperature", 30), ("sanitizing", 12), ("vermin", 12), ("handsink", 9), ("hands", 5), ("health", 3), ("supplier", 4),
              ("condition", 3), ("process", 1), ("advisory", 1), ("water", 5), ("sewage", 2), ("knowledge", 1)],
    "minor": [("temperature", 26), ("sanitizing", 14), ("knowledge", 12), ("handsink", 8), ("hands", 5), ("health", 4), ("vermin", 6),
              ("water", 3), ("sewage", 2), ("supplier", 3), ("condition", 3), ("process", 1), ("advisory", 3), ("hsp", 1)],
    "grp": [("grp_facility", 30), ("grp_equipment", 30), ("grp_storage", 12), ("grp_food", 12), ("grp_staff", 6), ("grp_signs", 8)],
}
VISIT_TYPES = ("routine", "reinspection", "followup", "complaint", "status_check")
# The County's own inspection type for each visit type (a complaint visit is one of two).
COUNTY_TYPES = {"routine": "Routine", "followup": "Routine", "reinspection": "Re-inspection", "status_check": "Status Verification"}
FIELD_TYPES = ("Site Investigation", "Environmental")
NOTE_PERMIT, NOTE_IMPOUND = "No Valid Permit", "Impoundment"
SEVERITIES = ("major", "minor", "grp")
CLOSURES = ("health", "permit", "other")
ESCALATION_FLAGS = ("major_2", "closures2", "repeat_item", "lt90_2")
RECORD_FLAGS = ("major", "closed", "bc", "repeat", *ESCALATION_FLAGS)
CLOSURE_SCORE = 70   # a routine inspection that started a closure for a health hazard is read as this score
MAX_ITEMS = 150      # items listed per place, majors first (export_site.MAX_VIOLATIONS)

RECORD_START = date(2023, 1, 1)
THROUGH = date(2026, 8, 31)
LIST_DATE = THROUGH + timedelta(days=1)
BACKTEST_AS_OF = date(2025, 9, 1)
YEAR = timedelta(days=365)
# Records added before this day fall outside every window the rule, the flags and the backtest read.
QUIET_BEFORE = BACKTEST_AS_OF - YEAR
TWO_YEARS = timedelta(days=730)   # the escalation facts' window, as export_site.ELIGIBLE_DAYS
SHARES = ((0.025, "1"), (0.075, "2"), (0.175, "3"))
INTERIM_DAYS = (90, 180, 270)      # the monitor's interim label windows, as export_site.INTERIM_DAYS
DRIFT_MIN, DRIFT_SE = 0.02, 3.0    # a rate moves when it moves by more than this or 3 standard errors
REPORT_LAG_DAYS = 30               # a quarter is compared once the County's reporting has had this long, as export_site
QUARTER_MIN = 200                  # quarters with fewer routine inspections are left out, as export_site
FAIR_DEFF = 2.0                    # an assumed design effect for inspector clustering, as export_site.FAIR_DEFF

# The sample's version of the students' point rule: two counts from the record, each with a whole-number weight.
RULE = [
    {"item": "avg_deficit", "label": "Points below 100, average routine score in the last year", "weight": 1,
     "unit": "per point below 100", "feature": "avg_deficit"},
    {"item": "theme_temperature", "label": "Food-temperature citations in the last year", "weight": 2,
     "unit": "per citation", "feature": "theme_temperature"},
]
RULE_TEXT = ("Places get one point for each point their average routine score in the last year fell "
             "below 100, and two points for each food-temperature citation in the last year. A routine inspection "
             "that started a closure for a health hazard (a County closure order, the operator's own closure with a "
             "major cited, or a closure read from a later reopening) counts as 70.")
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


def record(d: date, kind: str, status="Complete", score=None, major=0, minor=0, grp=0, closure=None, reopened=None,
           reopened_on=None, graded=True):
    """One County record, as the contract carries it. A record that starts a closure episode also
    carries `reopened_on`, the date of the "Approved to Reopen" record that ended it, or None."""
    graded = graded and score is not None and kind in ("routine", "followup")
    out = {"date": d.isoformat(), "status": status, "type": kind, "score": score, "grade": grade(score) if graded else None,
           "major": major, "minor": minor, "grp": grp, "closed": closure is not None, "closure": closure,
           "reopened": reopened if closure is not None else None}
    if closure is not None:
        out["reopened_on"] = reopened_on.isoformat() if reopened_on else None
    return out


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
        # Most inspections that find a major still score 90 or more; one that finds two sometimes scores
        # far lower, so a place can reach band 1 on its routine scores alone.
        worse = rng.randint(4, 16) if major > 1 and rng.random() < 0.6 else 0
        score = max(70, min(100, round(100 - 4 * major - worse - minor - 0.5 * grp - rng.choice((0, 0, 0, 1, 2)))))
        if major and rng.random() < 0.02 + 0.3 * latent:   # closures come from places doing worse
            f = d + timedelta(days=rng.randint(1, 4))
            reopened = f <= THROUGH
            # The County scores some closure visits and not others; it grades none of them.
            county = rng.randint(62, 86) if rng.random() < 0.4 else None
            out.append(record(d, "routine", "Ordered Closed", county, major, minor, grp, closure="health", reopened=reopened,
                              reopened_on=f if reopened else None, graded=False))
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


def in_window(violations, inspections):
    """Items cited in the 36 months before the last visit."""
    last = date.fromisoformat(inspections[-1]["date"])
    cutoff = (last - timedelta(days=int(36 * 30.44))).isoformat()
    return [v for v in violations if v["date"] >= cutoff]


def exported(violations, inspections):
    """Items cited in the 36 months before the last visit, as export_site.violations_shown: majors
    first, then the rest, each oldest first; at most MAX_ITEMS, and when the cap cuts, it drops the
    oldest non-major items, never the newest."""
    keep = sorted(in_window(violations, inspections), key=lambda v: v["date"])
    majors = [v for v in keep if v["severity"] == "major"][-MAX_ITEMS:]
    rest = [v for v in keep if v["severity"] != "major"]
    room = MAX_ITEMS - len(majors)
    return majors + (rest[max(len(rest) - room, 0):] if room else [])


def theme_counts(items):
    """{theme: {major, minor, grp, complaint, latest}} over every item in the window, before the cut."""
    out = {}
    for v in items:
        t = out.setdefault(v["theme"], {"major": 0, "minor": 0, "grp": 0, "complaint": 0, "latest": v["date"]})
        t[v["severity"]] += 1
        t["complaint"] += v["visit"] == "complaint"
        t["latest"] = max(t["latest"], v["date"])
    return {k: out[k] for k in THEMES if k in out}


def _day(r):
    return date.fromisoformat(r["date"])


def _free(inspections, d: date, before: int, after: int) -> bool:
    """No record from `before` days before `d` to `after` days after it."""
    return not any(-before <= (_day(r) - d).days <= after for r in inspections)


def _items(rng: random.Random, visit: str, d: date, major=0, minor=0, grp=0, themes=None):
    """Invented items for an added record, as make_violations writes them; `themes` ({severity:
    [themes]}) narrows the sections an added record's items of that severity come from."""
    rows = []
    for sev, n in (("major", major), ("minor", minor), ("grp", grp)):
        for _ in range(n):
            pick = (themes or {}).get(sev)
            theme = rng.choice(pick) if pick else weighted(rng, THEMES_BY_SEVERITY[sev])
            code, desc = rng.choice(ITEMS[theme])
            rows.append({"date": d.isoformat(), "visit": visit, "code": code, "theme": theme, "severity": sev, "description": desc})
    return rows


def add_county_detail(rng: random.Random, inspections, violations):
    """The County's own words on every record, and the rarer records the real export keeps.

    Every record gets ``county_type`` (a complaint visit is a "Site Investigation" or an
    "Environmental" record) and ``notes`` (a permit closure's "No Valid Permit", now and then an
    "Impoundment"). Then, on a few places each: a health closure at an unscored routine becomes one
    only its "Approved to Reopen" shows (``closure_inferred``: the County's status is "Complete");
    a last closure's re-grade is published as "Complete" with no score or grade, so nothing on the
    record ends the closure (``grade.open_closure``); a reinspection becomes an "Approved to Reopen" no closure could be placed before
    (``reopen_without_closure``); a "Status Verification" record is kept ("Ordered Closed" for a
    permit and reopened, or citing good-retail-practice items); and a "Self Closed" routine is kept
    (with a major it starts a closure, which a re-grade a week later ends).

    Nothing here changes a routine score, a label or a count the rule, the flags or the backtest
    read: the converted records keep their type and closure, a Status Verification record is never
    scored and cites only good-retail-practice items, and the closures added (a Status Verification
    "Ordered Closed" and its reopening, a Self Closed routine and its re-grade) fall before
    QUIET_BEFORE."""
    for r in inspections:
        r["county_type"] = COUNTY_TYPES.get(r["type"]) or (FIELD_TYPES[0] if rng.random() < 0.65 else FIELD_TYPES[1])
        notes = []
        if r["closed"] and r["closure"] == "permit":
            notes.append(NOTE_PERMIT)
        elif r["type"] == "complaint" and rng.random() < 0.05:
            notes.append(NOTE_IMPOUND)
        elif r["type"] == "routine" and r["status"] == "Complete" and rng.random() < 0.01:
            notes.append(NOTE_PERMIT)
        r["notes"] = notes
    # A last closure whose reopening the published record does not show: the re-grade after it is
    # "Complete" with no score or grade, so no "Approved to Reopen" and no graded visit end it.
    closed = [k for k, r in enumerate(inspections) if r["closed"]]
    if closed and rng.random() < 0.4:
        c, later = inspections[closed[-1]], inspections[closed[-1] + 1:]
        back = next((r for r in later if r["date"] == c.get("reopened_on") and r["status"] == "Approved to Reopen" and r["type"] == "followup"), None)
        if c["closure"] == "health" and back and not any(r["type"] in ("routine", "followup") and r["grade"] and r is not back for r in later):
            back.update(status="Complete", score=None, grade=None)
            c["reopened"], c["reopened_on"] = False, None
    for r in inspections:
        # The County's pattern: an unscored routine with a major, and "Approved to Reopen" days later.
        if (r["closed"] and r["closure"] == "health" and r["type"] == "routine" and r["score"] is None and r["reopened"]
                and (date.fromisoformat(r["reopened_on"]) - _day(r)).days <= 3 and rng.random() < 0.25):
            r["status"], r["closure_inferred"] = "Complete", True
    last = _day(inspections[-1])
    first = _day(inspections[0])
    added = []
    if rng.random() < 0.02:
        closures = [r for r in inspections if r["closed"]]
        cands = [r for r in inspections if r["type"] == "reinspection" and r["status"] == "Complete"
                 and not any(c["date"] <= r["date"] and (not c["reopened"] or (_day(r) - _day(c)).days <= 60) for c in closures)]
        if cands:
            r = rng.choice(cands)
            r["status"], r["reopen_without_closure"] = "Approved to Reopen", True
    if rng.random() < 0.02:
        d = RECORD_START + timedelta(days=rng.randint(0, (QUIET_BEFORE - RECORD_START).days - 40))
        if d + timedelta(days=2) < min(last, QUIET_BEFORE) and _free(inspections + added, d, 3, 35):
            on = d + timedelta(days=2)
            added.append(record(d, "status_check", "Ordered Closed", closure="permit", reopened=True, reopened_on=on) | {"notes": [NOTE_PERMIT]})
            added.append(record(on, "reinspection", "Approved to Reopen") | {"notes": []})
    if rng.random() < 0.015:
        d = first + timedelta(days=rng.randint(10, 500))
        if d < last and _free(inspections + added, d, 3, 3):
            grp = rng.randint(1, 2)
            added.append(record(d, "status_check", "Complete", grp=grp) | {"notes": [NOTE_PERMIT] if rng.random() < 0.5 else []})
            violations += _items(rng, "status_check", d, grp=grp, themes={"grp": ["grp_signs"]})
    if rng.random() < 0.035:
        d = RECORD_START + timedelta(days=rng.randint(0, (QUIET_BEFORE - RECORD_START).days - 20))
        if d + timedelta(days=8) < min(last, QUIET_BEFORE) and _free(inspections + added, d, 3, 40):
            if rng.random() < 0.7:
                minor, grp = poisson(rng, 0.8), poisson(rng, 1.2)
                added.append(record(d, "routine", "Self Closed", None, 1, minor, grp, closure="health", reopened=False, graded=False) | {"notes": []})
                violations += _items(rng, "routine", d, major=1, minor=minor, grp=grp, themes={"major": ["vermin", "water", "sewage"]})
                added.append(record(d + timedelta(days=7), "reinspection", "Complete") | {"notes": []})
                added.append(record(d + timedelta(days=8), "followup", "Complete", rng.randint(96, 100), 0, 0, poisson(rng, 0.5)) | {"notes": []})
                violations += _items(rng, "followup", d + timedelta(days=8), grp=added[-1]["grp"])
            else:
                minor = rng.randint(1, 2)
                added.append(record(d, "routine", "Self Closed", None, 0, minor, 0, graded=False) | {"notes": []})
                violations += _items(rng, "routine", d, minor=minor)
    for r in added:
        r["county_type"] = COUNTY_TYPES[r["type"]]
    inspections += added
    order = {"routine": 0, "followup": 1, "reinspection": 2, "complaint": 3, "status_check": 4}
    inspections.sort(key=lambda x: (x["date"], order[x["type"]]))


def open_closure(inspections):
    """The place's last closure when no "Approved to Reopen" and no graded routine or re-grade on a
    later day follow it: {date, reason, later_ungraded, status: the County's status text on the record
    that started it}; else None. As export_site.open_closure: later_ungraded is the dates of the
    ungraded records on later days, not counting a further closure order in the same closure."""
    closed = [k for k, i in enumerate(inspections) if i["closed"]]
    if not closed:
        return None
    k = closed[-1]
    c, later = inspections[k], inspections[k + 1:]
    if c["reopened"] or any(i["status"] == "Approved to Reopen" for i in later):
        return None
    if any(i["type"] in ("routine", "followup") and i["grade"] and i["date"] > c["date"] for i in later):
        return None
    order = lambda i: i["status"] == "Ordered Closed" or (i["status"] == "Self Closed" and i["major"] > 0)
    out = {"date": c["date"], "reason": c["closure"],
           "later_ungraded": sorted({i["date"] for i in later if i["date"] > c["date"] and not i["grade"] and not order(i)})}
    if not c.get("closure_inferred") and c["status"] in ("Ordered Closed", "Self Closed"):
        out["status"] = c["status"]
    return out


def grade_on_record(inspections):
    """The latest letter from a routine or re-grade record; `replaced` is the routine B or C a
    re-grade replaced, and `open_closure` the place's last closure when nothing after it on the
    record ended it."""
    graded = [i for i in inspections if i["grade"] and i["type"] in ("routine", "followup")]
    if not graded:
        return None
    latest = graded[-1]
    out = {"grade": latest["grade"], "score": latest["score"], "date": latest["date"], "replaced": None,
           "open_closure": open_closure(inspections)}
    if latest["type"] == "followup":
        before = [i for i in graded[:-1] if i["type"] == "routine"]
        if before and before[-1]["grade"] in ("B", "C"):
            r = before[-1]
            out["replaced"] = {"grade": r["grade"], "score": r["score"], "date": r["date"]}
    return out


def record_flags(inspections, violations, as_of: date = LIST_DATE):
    """Record facts counted back from the list date, as the index carries them: over the 12 months
    before it, a major, a health closure, a routine B or C, two or more reinspections, and the theme
    of each major; over the 24 months before it, the escalation facts, our counts of the patterns the
    County's Retail Food Facility Operator's Guide names (p. 8: "recurring major violations, recurring
    scores of less than 90%, or recurring facility closures"; the County sets no count or period, and
    meeting one is not a County finding): major violations at two or more routine inspection dates,
    two or more health-closure episodes, the same major item at two or more routine inspection
    dates, and two or more routine inspections scored below 90."""
    hi, lo1, lo2 = as_of.isoformat(), (as_of - YEAR).isoformat(), (as_of - TWO_YEARS).isoformat()
    year = [i for i in inspections if lo1 <= i["date"] <= hi]
    two = [i for i in inspections if lo2 <= i["date"] <= hi]
    flags = []
    if any(i["major"] > 0 for i in year):
        flags.append("major")
    if any(i["closed"] and i["closure"] == "health" for i in year):
        flags.append("closed")
    if any(i["type"] == "routine" and i["grade"] in ("B", "C") for i in year):
        flags.append("bc")
    if sum(1 for i in year if i["type"] == "reinspection") >= 2:
        flags.append("repeat")
    if len({i["date"] for i in two if i["type"] == "routine" and i["major"]}) >= 2:
        flags.append("major_2")
    if sum(1 for i in two if i["closed"] and i["closure"] == "health") >= 2:
        flags.append("closures2")
    item_dates = {}
    for v in violations:
        if v["severity"] == "major" and v["visit"] == "routine" and lo2 <= v["date"] <= hi:
            item_dates.setdefault(v["code"], set()).add(v["date"])
    if any(len(ds) >= 2 for ds in item_dates.values()):
        flags.append("repeat_item")
    if sum(1 for i in two if i["type"] == "routine" and i["score"] is not None and i["score"] < 90) >= 2:
        flags.append("lt90_2")
    majors = {v["theme"] for v in violations if v["severity"] == "major" and lo1 <= v["date"] <= hi}
    flags.extend(t for t in THEMES if t in majors and t != "other")
    return flags


def used_scores(place, lo: str, hi: str, closures: bool = True):
    """The routine scores the rule reads in [lo, hi): a routine that started a closure for a health
    hazard (a County closure order, the operator's own closure with a major cited, or a closure read
    from a later reopening) is read as CLOSURE_SCORE (`closure: true`), beside the County's own score
    that day, if any. With `closures=False`, those routines are left out: the record on routine
    scores alone."""
    used = []
    for i in place["inspections"]:
        if i["type"] != "routine" or not lo <= i["date"] < hi:
            continue
        if i["closed"] and i["closure"] == "health":
            if closures:
                used.append({"date": i["date"], "score": CLOSURE_SCORE, "closure": True, "county_score": i["score"]})
        elif i["score"] is not None:
            used.append({"date": i["date"], "score": i["score"], "closure": False, "county_score": i["score"]})
    return used


def rule_values(place, as_of: date, closures: bool = True):
    """The rule's counts for a place from its record in the year before `as_of`, or None when the
    place is not scored (not a restaurant, or no routine score in that year)."""
    if place["facility_type"] != "restaurant":
        return None
    lo, hi = (as_of - YEAR).isoformat(), as_of.isoformat()
    used = used_scores(place, lo, hi, closures)
    if not used:
        return None
    avg = sum(u["score"] for u in used) / len(used)
    temp = sum(1 for v in place["all_violations"] if v["theme"] == "temperature" and v["severity"] != "grp" and lo <= v["date"] < hi)
    # rounded half up, as a person checking the worksheet by hand would (and as export_site.py does)
    return {"avg_deficit": max(0, 100 - math.floor(avg + 0.5)), "theme_temperature": temp}, avg, used


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


def next_routine(place, as_of: date, days: int = 365):
    """The first routine inspection in the year (or `days`) from `as_of`: the backtest's label."""
    lo, hi = as_of.isoformat(), (as_of + timedelta(days=days)).isoformat()
    for i in place["inspections"]:
        if i["type"] == "routine" and lo <= i["date"] < hi:
            return i
    return None


def make_place(rng: random.Random, i: int, seed: int = 9):
    lat, lon, district, zipcode, _ = weighted(rng, [(a, a[4]) for a in ANCHORS])
    ftype = weighted(rng, TYPES)
    latent = min(0.98, max(0.02, rng.betavariate(2, 5) + {"restaurant": 0.06, "limited": -0.08}.get(ftype, 0.0)))
    inspections = make_visits(rng, latent)
    violations_all = make_violations(rng, inspections)
    # Its own stream, so the main one (and every place after this one) is what it was.
    add_county_detail(random.Random(f"county-detail:{seed}:{i}"), inspections, violations_all)
    window = in_window(violations_all, inspections)
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
        "theme_counts": theme_counts(window),
        "violations_total": len(window),
    }


def scored_order(places, as_of):
    """Eligible places with their rule values, points high first, then name (the site's order)."""
    rows = []
    for j, p in enumerate(places):
        got = rule_values(p, as_of)
        if got is None:
            continue
        values, avg, used = got
        sheet, pts = worksheet(values)
        rows.append({"j": j, "points": pts, "avg": avg, "sheet": sheet, "name": p["name"], "used": used})
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
    lab = [r for r in rows if r["labelled"]]
    # Two estimate curves, as export_site: places whose scored year includes a routine inspection that
    # started a health closure (counted as 70) read their own, and every other place reads `curve`.
    closure = [(r["points"], int(r["positive"])) for r in lab if any(u["closure"] for u in r["used"])]
    scores = [(r["points"], int(r["positive"])) for r in lab if not any(u["closure"] for u in r["used"])]
    extra = {"base_rate": round(sum(r["positive"] for r in lab) / len(lab), 4) if lab else None,
             "curve": risk_curve(scores) if scores else None,
             "curve_closure": risk_curve(closure) if closure else None,
             "interim": interim_rates(places, rows, stops[0]),
             "band_1_share": round(stops[0] / len(rows), 4) if rows else None,
             "by_route": band_1_by_route(places, rows[:stops[0]]),
             "by_district": district_precision(places, rows, stops[-1])}
    return bands, rest_row, {"candidates": len(rows), "eligible": len(rows), "positives": positives, "labelled": len(lab), **extra}


def interim_rates(places, rows, band_1_stop):
    """Band 1's rate and the rate for all scored places with the label cut off after 90, 180 and 270
    days, as export_site.interim_rates: what a later list can be set against before its year is over."""
    out = {}
    for days in INTERIM_DAYS:
        c = {"1": [0, 0], "all": [0, 0]}
        for pos, r in enumerate(rows):
            nxt = next_routine(places[r["j"]], BACKTEST_AS_OF, days)
            if nxt is None:
                continue
            for k in (["1"] if pos < band_1_stop else []) + ["all"]:
                c[k][0] += int(nxt["major"] > 0)
                c[k][1] += 1
        out[str(days)] = {k: {"labelled": n, "positives": k_, "rate": round(k_ / n, 4) if n else None} for k, (k_, n) in c.items()}
    return out


def route_stats(members):
    lab = [r for r in members if r["labelled"]]
    k = sum(1 for r in lab if r["positive"])
    return {"labelled": len(lab), "positives": k, "rate": round(k / len(lab), 4) if lab else None, "interval": wilson(k, len(lab))}


def band_1_by_route(places, band_1):
    """Band 1's backtest places split in two: those in the band because a closure was read as 70 (on
    routine scores alone their points fall below the band's cut), and those in it on routine scores
    alone."""
    if not band_1:
        return None
    cut = min(r["points"] for r in band_1)
    closure, scores = [], []
    for r in band_1:
        alone = rule_values(places[r["j"]], BACKTEST_AS_OF, closures=False)
        pts = worksheet(alone[0])[1] if alone else None
        (scores if pts is not None and pts >= cut else closure).append(r)
    return {"closure": route_stats(closure), "scores": route_stats(scores)}


def percentile(values, q):
    """The q-th percentile (0 to 100) of `values`, interpolated linearly as numpy's default."""
    v = sorted(values)
    pos = (len(v) - 1) * q / 100
    lo = math.floor(pos)
    return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (pos - lo)


def share_draws(units, districts, n_boot, seed):
    """Bootstrap draws of each district's share of the wrongly named over its share of the labelled
    places, resampling `units` (each {district: [wrongly named, labelled]}: one per place, as the
    sample has one place per address) with replacement."""
    rng = random.Random(seed)
    draws = {d: [] for d in districts}
    for _ in range(n_boot):
        fp, lab = dict.fromkeys(districts, 0), dict.fromkeys(districts, 0)
        for u in (rng.choice(units) for _ in units):
            for d, (f, n) in u.items():
                fp[d] += f
                lab[d] += n
        tot_fp, tot_lab = sum(fp.values()), sum(lab.values())
        if not tot_fp or not tot_lab:
            continue
        for d in districts:
            if lab[d]:
                draws[d].append((fp[d] / tot_fp) / (lab[d] / tot_lab))
    return draws


def district_precision(places, rows, named_stop, n_boot=300, seed=21):
    """By council district, as export_site.district_fairness: the backtest's places in a band, how
    many had a major, precision with its interval, the false-positive rate against the City's, and
    the district's share of the wrongly named (a place in a band with no major next time) over its
    share of the labelled scored places, with a bootstrap 95% interval, a family-wise one (Bonferroni
    over the districts), and the family-wise one widened for an assumed design effect (FAIR_DEFF:
    the draws' spread around their median scaled by its square root), since places one inspector
    visits may be cited alike and the record has no inspector ids. `evidence_above_even` only when
    both family-wise intervals start above 1."""
    named = {id(r) for r in rows[:named_stop]}
    is_fp = lambda r: id(r) in named and r["labelled"] and not r["positive"]
    fp_all = sum(1 for r in rows if is_fp(r))
    neg_all = sum(1 for r in rows if r["labelled"] and not r["positive"])
    lab_all = sum(1 for r in rows if r["labelled"])
    fpr_all = fp_all / max(1, neg_all)
    district = lambda r: str(places[r["j"]]["district"])
    districts = sorted({district(r) for r in rows}, key=int)
    by_place = [{district(r): [int(is_fp(r)), int(r["labelled"])]} for r in rows]
    alpha = 0.05 / max(1, len(districts))
    draws = share_draws(by_place, districts, n_boot, seed)
    band = lambda v, lo, hi: [round(percentile(v, lo), 2), round(percentile(v, hi), 2)] if v else None
    widen = lambda v: [percentile(v, 50) + (x - percentile(v, 50)) * math.sqrt(FAIR_DEFF) for x in v]
    out = {}
    for d in districts:
        m = [r for r in rows if district(r) == d]
        nm = [r for r in m if id(r) in named]
        nm_lab = [r for r in nm if r["labelled"]]
        k = sum(1 for r in nm_lab if r["positive"])
        fp = sum(1 for r in nm_lab if not r["positive"])
        neg = sum(1 for r in m if r["labelled"] and not r["positive"])
        lab = sum(1 for r in m if r["labelled"])
        family = band(draws[d], 100 * alpha / 2, 100 * (1 - alpha / 2))
        family_deff = band(widen(draws[d]), 100 * alpha / 2, 100 * (1 - alpha / 2)) if draws[d] else None
        lows = [iv[0] for iv in (family, family_deff) if iv]
        out[d] = {"candidates": len(m), "labelled": lab, "named": len(nm), "named_positive": k, "false_named": fp,
                  "precision": round(k / len(nm_lab), 3) if nm_lab else None,
                  "precision_interval": wilson(k, len(nm_lab)) if nm_lab else None,
                  "fpr_ratio": round((fp / max(1, neg)) / fpr_all, 2) if fpr_all else None,
                  "false_share_ratio": round((fp / fp_all) / (lab / lab_all), 2) if fp_all and lab else None,
                  "interval": band(draws[d], 2.5, 97.5), "interval_family": family, "interval_family_deff": family_deff,
                  "evidence_above_even": len(lows) == 2 and min(lows) > 1}
    return out


def quarter_of(d: date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def quarter_bounds(q: str):
    """The first and last day of a quarter such as "2026Q3"."""
    y, n = int(q[:4]), int(q[-1])
    return date(y, 3 * (n - 1) + 1, 1), date(y + (n == 4), (3 * n) % 12 + 1, 1) - timedelta(days=1)


def quarters_between(a: date, b: date):
    """The quarters from the one holding `a` to the one holding `b`: ["2025Q3", ..., "2026Q3"]."""
    out, d = [], date(a.year, 3 * ((a.month - 1) // 3) + 1, 1)
    while d <= b:
        out.append(quarter_of(d))
        d = quarter_bounds(out[-1])[1] + timedelta(days=1)
    return out


def major_rate_by_quarter(places):
    """({quarter: share of routine inspections with a major}, {quarter: routine inspections}) through
    THROUGH, leaving out a quarter with fewer than QUARTER_MIN, as export_site.measurement."""
    by = {}
    for p in places:
        for i in p["inspections"]:
            if i["type"] == "routine" and i["date"] <= THROUGH.isoformat():
                c = by.setdefault(quarter_of(date.fromisoformat(i["date"])), [0, 0])
                c[0] += 1
                c[1] += int(i["major"] > 0)
    keep = {q: v for q, v in sorted(by.items()) if v[0] >= QUARTER_MIN}
    return {q: round(k / n, 4) for q, (n, k) in keep.items()}, {q: n for q, (n, _) in keep.items()}


def pooled(qs, by_q, n_q):
    n = sum(n_q.get(q, 0) for q in qs)
    return (sum(by_q[q] * n_q.get(q, 0) for q in qs) / n, n) if n else (None, 0)


def routine_by_month(places):
    """{"YYYY-MM": [routine inspections, with a major]} through THROUGH, as export_site.measurement."""
    by = {}
    for p in places:
        for i in p["inspections"]:
            if i["type"] == "routine" and i["date"] <= THROUGH.isoformat():
                c = by.setdefault(i["date"][:7], [0, 0])
                c[0] += 1
                c[1] += int(i["major"] > 0)
    return dict(sorted(by.items()))


def month_name(ym: str) -> str:
    """"2025-09" -> "September 2025"."""
    return f"{date(int(ym[:4]), int(ym[5:7]), 1).strftime('%B')} {ym[:4]}"


def drift(places, share_then, share_now, n_then, n_now):
    """As export_site.drift_check: the routine major rate in complete quarters that start after the
    backtest's label year (complete REPORT_LAG_DAYS after they end), against the rate over the label
    year's own months ("not_yet_measurable" until such a quarter exists), and band 1's share of
    scored restaurants now against its share then, each against max(DRIFT_MIN, 3 standard errors).
    The latest quarter's rate is also set against the label year's months that fall before that
    quarter, with their own count, so the two samples never share an inspection; a clear difference
    gets a note the site shows beside every estimate."""
    by_q, n_q = major_rate_by_quarter(places)
    by_m = routine_by_month(places)
    label_end = BACKTEST_AS_OF + YEAR - timedelta(days=1)
    latest = list(by_q)[-1] if by_q else None
    latest_start = quarter_bounds(latest)[0].isoformat()[:7] if latest else None
    label_months = [m for m in by_m if BACKTEST_AS_OF.isoformat()[:7] <= m <= label_end.isoformat()[:7]]
    n_label = sum(by_m[m][0] for m in label_months)
    base_then = sum(by_m[m][1] for m in label_months) / n_label if n_label else None
    before = [m for m in label_months if latest_start is None or m < latest_start]
    n_note = sum(by_m[m][0] for m in before)
    base_note = sum(by_m[m][1] for m in before) / n_note if n_note else None
    span_then = f"{month_name(label_months[0])} to {month_name(label_months[-1])}" if label_months else None
    span_note = f"{month_name(before[0])} to {month_name(before[-1])}" if before else None
    after = [q for q in by_q if quarter_bounds(q)[0] > label_end
             and quarter_bounds(q)[1] + timedelta(days=REPORT_LAG_DAYS) <= THROUGH][-2:]
    base_now, n_recent = pooled(after, by_q, n_q)
    thr = lambda p1, n1, p0, n0: max(DRIFT_MIN, DRIFT_SE * math.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0))
    reasons = []
    measurable = base_now is not None and base_then is not None
    if measurable and abs(base_now - base_then) > thr(base_now, n_recent, base_then, n_label):
        reasons.append(f"routine major rate {base_now:.1%} in {', '.join(after)} against {base_then:.1%} over the backtest's "
                       f"label year ({span_then})")
    if share_then is not None and share_now is not None and n_now and n_then and \
            abs(share_now - share_then) > thr(share_now, n_now, share_then, n_then):
        reasons.append(f"band 1 holds {share_now:.1%} of scored City restaurants against {share_then:.1%} in the backtest")
    note = None
    if latest and base_note is not None and n_q.get(latest):
        lr, ln = by_q[latest], n_q[latest]
        if abs(lr - base_note) > thr(lr, ln, base_note, n_note):
            end = quarter_bounds(latest)[1]
            upto = "" if THROUGH >= end else f", through {THROUGH.strftime('%B')} {THROUGH.day}"
            note = (f"In the latest quarter ({latest[:4]} Q{latest[-1]}{upto}) {lr:.1%} of routine inspections found a major "
                    f"violation, against {base_note:.1%} over the backtest's label year before that quarter ({span_note}), "
                    f"so the rates here may be {'low' if lr > base_note else 'high'}.")
    return {"major_rate_backtest": round(base_then, 4) if base_then is not None else None,
            "major_rate_backtest_n": n_label or None, "backtest_span": span_then,
            "major_rate_recent": round(base_now, 4) if base_now is not None else None, "recent_quarters": after,
            "band_1_share_backtest": share_then, "band_1_share_now": share_now,
            "latest_quarter": latest, "latest_rate": by_q.get(latest) if latest else None,
            "latest_n": n_q.get(latest) if latest else None,
            "latest_baseline": round(base_note, 4) if base_note is not None else None, "latest_baseline_n": n_note or None,
            "latest_baseline_span": span_note,
            "status": "refit" if reasons else ("ok" if measurable else "not_yet_measurable"),
            "refit_needed": bool(reasons), "reasons": reasons, "note": note,
            "thresholds": {"min": DRIFT_MIN, "standard_errors": DRIFT_SE}}


def isotonic(rates, weights):
    """Pool adjacent violators: the closest non-decreasing sequence (as export_site._isotonic)."""
    blocks = []
    for r, w in zip(rates, weights):
        blocks.append([w, r * w, 1])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][0] > blocks[-1][1] / blocks[-1][0]:
            w2, s2, c2 = blocks.pop()
            blocks[-1] = [blocks[-1][0] + w2, blocks[-1][1] + s2, blocks[-1][2] + c2]
    out = []
    for w, s_, c in blocks:
        out += [s_ / w] * c
    return out


def step_fit(pairs, groups, top):
    rates, weights = [], []
    for lo, hi in groups:
        ys = [y for p, y in pairs if lo <= p <= hi]
        rates.append(sum(ys) / len(ys) if ys else 0.0)
        weights.append(max(len(ys), 1))
    fit = [0.0] * (top + 1)
    for (lo, hi), r in zip(groups, isotonic(rates, weights)):
        for j in range(lo, hi + 1):
            fit[j] = r
    for j in range(1, top + 1):
        if not any(lo <= j <= hi for lo, hi in groups):
            fit[j] = fit[j - 1]
    return fit


def risk_curve(pairs, n_boot=60, seed=5, min_n=30):
    """The rate by points, as export_site.risk_curve: isotonic over point values pooled into groups of
    at least `min_n` places (sample: resampling places, not addresses)."""
    top = max(p for p, _ in pairs)
    counts = {}
    for p, _ in pairs:
        counts[p] = counts.get(p, 0) + 1
    groups, hi, n = [], None, 0
    for v in sorted(counts, reverse=True):
        hi = v if hi is None else hi
        n += counts[v]
        if n >= min_n:
            groups.append((v, hi))
            hi, n = None, 0
    if hi is not None:
        groups.append((0, hi)) if not groups else groups.__setitem__(-1, (0, groups[-1][1]))
    groups = sorted(groups)
    fit = step_fit(pairs, groups, top)
    rng = random.Random(seed)
    draws = [step_fit([rng.choice(pairs) for _ in pairs], groups, top) for _ in range(n_boot)]
    col = lambda j: sorted(d[j] for d in draws)
    lo = [min(col(j)[int(0.025 * (n_boot - 1))], fit[j]) for j in range(top + 1)]
    hi_ = [max(col(j)[int(round(0.975 * (n_boot - 1)))], fit[j]) for j in range(top + 1)]
    r4 = lambda v: [round(x, 4) for x in v]
    group_counts = [{"min_points": g_lo, "max_points": g_hi, "labelled": sum(1 for p, _ in pairs if g_lo <= p <= g_hi),
                     "positives": sum(y for p, y in pairs if g_lo <= p <= g_hi)} for g_lo, g_hi in groups]
    return {"model": "sample: isotonic rate by points on the invented backtest", "rate": r4(fit), "low": r4(lo),
            "high": r4(hi_), "groups": [list(g) for g in groups], "group_counts": group_counts, "bins": curve_bins(pairs),
            "labelled": len(pairs), "positives": sum(y for _, y in pairs)}


def curve_bins(pairs, bins=8):
    """The raw rates in `bins` groups of about equal size (quantile edges of the points), to check the
    fit against the counts, as export_site.risk_curve's `bins`."""
    pts = sorted(p for p, _ in pairs)
    edges = sorted({int(percentile(pts, 100 * i / bins)) for i in range(bins + 1)})
    if len(edges) == 1:
        edges = edges * 2
    table = []
    for i in range(len(edges) - 1):              # [edge, next edge), the last one closed
        last = i == len(edges) - 2
        inb = [(p, y) for p, y in pairs if edges[i] <= p and (p <= edges[i + 1] if last else p < edges[i + 1])]
        if inb:
            k = sum(y for _, y in inb)
            table.append({"min_points": min(p for p, _ in inb), "max_points": max(p for p, _ in inb), "labelled": len(inb),
                          "positives": k, "rate": round(k / len(inb), 4), "interval": wilson(k, len(inb))})
    return table


def estimate(curve, pts, group):
    """The curve read at a place's points, with the group whose curve it is and, as
    export_site.estimate, the fitted group of points it is read from (min_points, max_points: the
    group holding its points, else the one below; the lowest below every group); None without a curve."""
    if not curve or not curve.get("rate"):
        return None
    j = min(max(int(pts), 0), len(curve["rate"]) - 1)
    out = {"rate": curve["rate"][j], "low": curve["low"][j], "high": curve["high"][j], "group": group}
    groups = sorted(tuple(g) for g in curve.get("groups") or [])
    if groups:
        g = next((g for g in reversed(groups) if g[0] <= int(pts)), groups[0])
        out["min_points"], out["max_points"] = g
    return out


def rule_tag(meta_bands) -> str:
    """Eight hex digits naming the rule and its cuts, as export_site's frozen version does."""
    body = {"rule": RULE, "cuts": [b["min_points"] for b in meta_bands]}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:8]


def build(n_places: int = 1400, seed: int = 9, mode: str = "bands"):
    """(index FeatureCollection, {facility_id: place file}, meta) for `n_places` invented places."""
    if mode not in ("bands", "record"):
        raise ValueError(f"mode must be bands or record, not {mode!r}")
    rng = random.Random(seed)
    places = [make_place(rng, i + 1, seed) for i in range(n_places)]

    band_of, points_of, sheet_of, stability_of, used_of = {}, {}, {}, {}, {}
    meta_bands, rest_row, cr = [], None, None
    if mode == "bands":
        now = scored_order(places, LIST_DATE)
        stops = band_cuts([r["points"] for r in now])
        for pos, r in enumerate(now):
            pid = places[r["j"]]["id"]
            points_of[pid] = r["points"]
            sheet_of[pid] = r["sheet"]
            used_of[pid] = r["used"]
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
        share_now = round(stops[0] / len(now), 4) if now else None
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
            "last_visit": {"date": p["inspections"][-1]["date"], "type": p["inspections"][-1]["type"],
                           "county_type": p["inspections"][-1]["county_type"]},
            "grade": grade_on_record(p["inspections"]),
            "flags": record_flags(p["inspections"], p["all_violations"]),
        }
        detail = {"business_type": p["business_type"], "inspections": p["inspections"], "violations": p["violations"],
                  "theme_counts": p["theme_counts"], "violations_total": p["violations_total"]}
        if p["id"] in held:
            props["on_hold"] = True
        elif p["id"] in points_of:
            if p["id"] in band_of:
                props["band"] = band_of[p["id"]]
            props["points"] = points_of[p["id"]]
            detail["score_card"] = sheet_of[p["id"]]
            detail["band_stability"] = stability_of[p["id"]]
            detail["scores_used"] = used_of[p["id"]]
            group = "closure" if any(u["closure"] for u in used_of[p["id"]]) else "scores"
            detail["estimate"] = estimate(cr["curve_closure"] if group == "closure" else cr["curve"], points_of[p["id"]], group)
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
            "model": f"sample of the students' point rule ({len(RULE)} counts, whole-number weights), invented",
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
                "base_rate": cr["base_rate"],
                "curve": cr["curve"],
                "curve_closure": cr["curve_closure"],
                "interim": cr["interim"],
                "closure_score": CLOSURE_SCORE,
                "band_1_by_route": cr["by_route"],
            },
            "catch": {},
            "catch_run": {
                "as_of": BACKTEST_AS_OF.isoformat(),
                "candidates": cr["candidates"],
                "eligible": cr["eligible"],
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
            "fairness": {"by_district": cr["by_district"], "bands_used": [key for _, key in SHARES], "problems": []},
            "measurement": dict(grade_context),
            # The rule as frozen (docs/rule.json in the real pipeline); its version names its content.
            "frozen": {"version": f"{LIST_DATE.isoformat()}-{rule_tag(meta_bands)}", "frozen_on": LIST_DATE.isoformat(), "from_run": "sample"},
            "drift": drift(places, cr["band_1_share"], share_now, cr["eligible"], len(points_of)),
        })
    return {"type": "FeatureCollection", "features": features}, place_files, meta


def monitor_summary(meta):
    """What export_site.monitor writes, for the sample: the forward test has had no runs, so it is too
    early to say anything, there is nothing to alert on and no list to break down by district."""
    return {"status": "too early", "runs": 0, "alerts": [], "next_window_date": None,
            "rule_version": (meta.get("frozen") or {}).get("version"), "inspections_through": meta.get("inspections_through"),
            "by_district": None}


def write(out: Path, fc, place_files, meta) -> None:
    """Write the export in the v3 layout, replacing any earlier place files (and, in bands mode, the
    monitor summary; a record export has none)."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "facilities.geojson").write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
    # newline="\n": the committed sample is LF (.gitattributes), on Windows too
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8", newline="\n")
    monitor = out / "monitor_summary.json"
    if meta.get("mode") == "bands":
        monitor.write_text(json.dumps(monitor_summary(meta), indent=2), encoding="utf-8", newline="\n")
    elif monitor.exists():
        monitor.unlink()
    pdir = out / "place"
    pdir.mkdir(exist_ok=True)
    for old in pdir.glob("*.json"):       # emptied, not removed: a synced folder (OneDrive) may hold the directory
        old.unlink()
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
