"""The public site's export (docs/FOOD_DATA_CONTRACT.md). Two modes:

  record  The County's inspection record for every listed City of San Diego restaurant and market,
          with no model and no ordering. The default publishable product.
  bands   The same, plus a published rule that puts some places in bands, with each band's backtest
          hit rate. Gated (docs/PUBLISHING.md); docs/MODEL_CARD.md says what it is and is not for.

What the rule predicts: at least one major ("Out of Compliance - Major") violation at a place's next
routine inspection within a year. Most such inspections still end with an A; the site says so.

Formulation (bands)
  * Snapshots. On the first of each month T every active facility is described by its record in the
    year before T and labelled by its first routine inspection in the year after T. Features mean the
    same thing at every snapshot (a 12-month window; the public record starts in January 2023).
  * Interpretable candidates only, sparsest first: the one-line average-score rule (points = how far
    the average routine score of the last year fell below 100), then a count-based integer score
    (whole points per point below 100 and per citation, fitted with non-negative weights and
    rounded). Logistic regression, monotone gradient boosting and a monotone additive model are
    fitted as the yardstick. The public rule is the sparsest candidate within EPSILON AUC of the best
    model at both validation origins (declared here; the confirmation origin was looked at while the
    pipeline was built, so the prospective test is the one that counts).
  * No ZIP, no neighbourhood, no kind of place, nothing from complaint visits (and a reinspection
    that follows a complaint visit does not count): the score reads only a place's own record.
    Fitted on the listed kinds (restaurants, limited-preparation food service, markets), county-wide.
  * The rule published is the rule tested: frozen at the confirmation origin. Bands are cut at whole
    point values (a tie is never split); adjacent bands whose intervals overlap are merged. Only
    places with two scored routine inspections in the last two years are banded.
  * Naming needs a signed approval bound to this run and this file, a cost ratio (C/B >= 1 unless an
    independent reviewer co-signs), notice to every named place, a band whose hit rate clears
    C/(B+C) and beats the best other baseline's same-size group, district parity, and a registered
    frozen run that held up on later inspections. Nothing is named today.

Data rules (checked against the pull; counts in report.md)
  * "No Access", "Self Closed" and "Status Verification" are not inspections.
  * A routine visit within 30 days after a B/C or a closure is the County's re-grade or reopening
    ("followup"): never a label, and its score is not the place's routine score.
  * For the model, same-day records of one type are one visit; for display, every County record is
    shown as published, with the County's own status text.
  * 0 is "not scored". Grades are the County's letters, never derived. Tiers come from the status
    text; themes from the item text (the mobile-unit report numbers its items differently).
  * A closure is an episode with a reason (a major that day, or a permit note), and `reopened` says
    whether the County's "Approved to Reopen" visit ended it.

  python export_site.py                  # bands review export -> data/site/ (with report.md, archive/)
  python export_site.py --mode record    # the record-only export -> data/site/
  python export_site.py --publish        # ...then, if every gate passes, into food-dashboard/public/data/
  python export_site.py --register       # register this run as the frozen prospective test (commit the file)
  python export_site.py --monitor        # score archived runs against the inspections made since
Needs data/sd_businesses.json (fetch_sdfood.py). Council districts come from SANDAG and are cached
in data/council_districts.geojson on first run."""
from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import json
import math
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "sd_businesses.json"
PULL = ROOT / "data" / "pull_meta.json"
DISTRICTS = ROOT / "data" / "council_districts.geojson"
DISTRICTS_URL = "https://geo.sandag.org/server/rest/directories/downloads/Council_Districts.geojson"
OUT = ROOT / "data" / "site"
SITE_DATA = ROOT / "food-dashboard" / "public" / "data"
CHECK = ROOT / "food-dashboard" / "scripts" / "check-export.mjs"
APPROVAL = ROOT / "docs" / "PUBLISH_APPROVAL.json"
NOTICES = ROOT / "docs" / "notices"          # docs/notices/<run>.csv: notice sent to each named place
HOLDS = ROOT / "docs" / "holds.json"         # facility ids under review: shown without a band
CORRECTIONS = ROOT / "docs" / "corrections.json"
PROSPECTIVE = ROOT / "docs" / "prospective"  # REGISTERED.json names the one frozen run the prospective test uses
RESULTS_URL = "https://www.sandiegocounty.gov/content/sdc/deh/fhd/ffis.html"

WINDOW_DAYS = 365       # counts: the year before T; the record starts 2023-01, so every snapshot sees a whole year
SCORE_WINDOW_DAYS = 730 # scores: the two years before T (a third of routine inspections come more than a year apart)
LABEL_DAYS = 365        # label: the first routine inspection in the year from T
ACTIVE_DAYS = 550       # a candidate was visited in the last ~18 months
FOLLOWUP_DAYS = 30      # a routine this soon after a B/C or a closure is the County's re-grade or reopening
RECORD_DAYS = int(36 * 30.44)
MAX_VIOLATIONS = 60
FRESH_DAYS = 14         # a list older than this is not published, and the site shows search only after it
NOTICE_DAYS = 14        # a named place is told this long before publication
MIN_COST_RATIO = 1.0    # C/B below this only with an independent reviewer's signature
ELIGIBLE_DAYS = 730     # a place is named only with two scored routine inspections in this window
COMPLAINT_DAYS = 60     # a reinspection this soon after a complaint visit does not count for the card
KS = (50, 100, 200, 500, 800, 1000)
K_GATE = 500
BANDS = ((0.025, "1"), (0.075, "2"), (0.175, "3"))   # target cumulative shares; bands never split a tie in points
BOOT = 1000
REFITS = 30
SEED = 0

OK_STATUS = {"Complete", "Ordered Closed", "Approved to Reopen"}
VISIT_TYPES = {"Routine": "routine", "Re-inspection": "reinspection", "Site Investigation": "complaint",
               "Environmental": "complaint"}
RECORD_TYPES = ("routine", "reinspection", "followup")   # the visits features read; complaint visits are shown, not used

# Themes from the County's item text (lower case, number stripped), first match wins. Grouped by the
# CDC's foodborne-illness risk factors, then water and pests, then records; the rest is "other".
THEME_RULES = [
    ("temperature", r"hot (&|and) cold holding|time as a public health control|cooling method|cooking time|reheating"),
    ("handwashing", r"hands clean|handwashing facilit|hand washing station|toilet and handwashing sink"),
    ("hygiene", r"communicable disease|discharge from eyes|eating, tasting|personal cleanliness"),
    ("sanitizing", r"^food contact surfaces|warewashing|wiping cloth"),
    ("supplier", r"approved source|shell ?stock|gulf oyster"),
    ("condition", r"good condition, safe|returned and reservice"),
    # "18. Compliance with:" is the variance / specialized-process / HACCP item; "39. Compliance with
    # fire safety requirements" on the mobile-unit form is not.
    ("process", r"^compliance with:?$"),
    ("vermin", r"rodents, insects"),
    ("plumbing", r"hot (&|and) cold water|potable|sewage|waste ?water|backflow|water tank"),
    ("storage", r"thawing|food separated|food storage|vegetables washed|toxic substances"),
    ("equipment", r"equipment ?/ ?utensils|thermometers|ventilation|commissary"),
    ("labeling", r"food safety certification|food handler|processor course|consumer advisory|labeled|grade card|"
                 r"identification on vehicle|home kitchen|name of cfo|ingredients listed|permit number|common name|"
                 r"person in charge|local agency"),
]
THEME_RES = [(t, re.compile(p)) for t, p in THEME_RULES]
THEMES = [t for t, _ in THEME_RULES]
RISK_THEMES = ("temperature", "handwashing", "hygiene", "sanitizing", "supplier", "condition", "process", "vermin",
               "plumbing", "storage")

# The County's business types as kinds. PUBLIC_KINDS may appear on the public list; the model is
# fitted on every kind here, county-wide. Private homes and places nobody eats at are not scored.
KINDS = {
    "Restaurant Food Facility": "restaurant", "Multiple Kitchen Complex Operation": "restaurant",
    "Low Risk Food Facility": "limited",
    "Retail Market with Deli": "market", "Retail Food Processing": "market",
    "Pre-Packaged Retail Market": "prepackaged",
    "Prepackaged Cart/Truck": "mobile", "Limited Food Prep Cart": "mobile", "Limited Food Prep Truck": "mobile",
    "Mobile Food Facility Prep Unit": "mobile", "Prepackaged Lunch Truck": "mobile",
    "School Processing Food Facility": "school", "School Food Auxiliary Facility": "school",
    "Caterer": "caterer", "Caterer - Direct Sales": "caterer",
    "Satellite Food Service Operation": "venue", "Single Operating Site": "venue", "Host Facility": "venue",
    "Miscellaneous Food Facility": "venue", "Minimal Food Preparation": "venue", "Restricted Food Service Facility": "venue",
    "Boat": "venue",
}
# Never scored: private homes, and places nobody eats at. A type in neither list is left out and
# reported, until someone decides which list it belongs on.
EXCLUDED_TYPES = {"Class A Cottage Food Operation", "Class B Cottage Food Operation", "Microenterprise Home Kitchen",
                  "Vending Machine", "Vending Machine Commissary", "Wholesale Food Warehouse",
                  "Licensed Health Care Facility", "Mobile Food Facility Commissary Processing",
                  "Mobile Food Facility Commissary Non-Processing", ""}
PUBLIC_KINDS = {"restaurant", "limited", "market"}
MODEL_KINDS = ("restaurant", "limited", "market")      # kind dummies for the black-box comparators; the card has no kind item

NUMERIC = (["avg_score", "last_score", "routines", "routines_major", "majors", "health_closures", "reinspections", "grp"]
           + [f"theme_{t}" for t in RISK_THEMES] + [f"kind_{k}" for k in MODEL_KINDS])
MONOTONE = {"avg_score": -1, "last_score": -1, "routines": 0, "routines_major": 1, "majors": 1, "health_closures": 1,
            "reinspections": 1, "grp": 1, **{f"theme_{t}": 1 for t in RISK_THEMES}, **{f"kind_{k}": 0 for k in MODEL_KINDS}}


# ── the record ─────────────────────────────────────────────────────────────────────────

def _int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def theme_of(text):
    t = re.sub(r"^\s*\d+[a-z]?\.\s*", "", (text or "").lower()).strip()
    for theme, rx in THEME_RES:
        if rx.search(t):
            return theme
    return "other"


def parse_item(v):
    """One cited item: (tier, theme, code, description), or None for a permit or impound note."""
    status = (v.get("status") or "").strip()
    if not status.startswith("Out of Compliance"):
        return None
    tier = "major" if status.endswith("Major") else "minor" if status.endswith("Minor") else "grp"
    if tier != "major" and v.get("major_violation") == "Y":
        tier = "major"
    text = (v.get("violation_accela") or v.get("violation") or "").strip()
    m = re.match(r"\s*(\d+[a-z]?)\.\s*(.*)", text)
    return {"code": m[1] if m else None, "theme": theme_of(text), "severity": tier,
            "description": (m[2] if m else text).strip()}


@dataclass
class Stats:
    """What the data rules did, for report.md."""
    dropped: Counter = field(default_factory=Counter)
    merged: int = 0
    followups: int = 0
    closures: Counter = field(default_factory=Counter)
    items_by_theme: Counter = field(default_factory=Counter)


def load_places(raw: list[dict], stats: Stats | None = None) -> list[dict]:
    """Every business with its visits in date order, the data rules above applied."""
    stats = stats or Stats()
    places = []
    for b in raw:
        by_key = {}
        for i in b.get("inspections") or []:
            status, day = (i.get("status") or "").strip(), (i.get("completed_date") or "")[:10]
            kind = VISIT_TYPES.get(i.get("type"))
            if not day or not kind or status not in OK_STATUS:
                stats.dropped[f"{i.get('type')}/{status or 'blank'}"] += 1
                continue
            items, notes = [], []
            for v in i.get("violations") or []:
                it = parse_item(v)
                if it:
                    items.append(it)
                else:
                    notes.append(_norm(v.get("violation_accela") or v.get("violation")))
            score = _int(i.get("score"))
            grade = (i.get("grade") or "").strip().upper()
            visit = {"date": day, "type": kind, "status": status,
                     "score": score if kind == "routine" and status == "Complete" and score and score > 0 else None,
                     "grade": grade if grade in ("A", "B", "C") else None,
                     "_items": items, "_notes": notes, "_id": str(i.get("inspection_id") or "")}
            # The County's own record, kept whole for display: the model reads merged visits, the
            # site shows every record as the County published it (one letter per record).
            visit["_records"] = [{"date": day, "status": status, "score": visit["score"], "grade": visit["grade"],
                                  "_items": list(items), "_id": visit["_id"]}]
            key = (day, kind)
            if key in by_key:                       # same day, same type: one visit
                stats.merged += 1
                w = by_key[key]
                w["_records"] += visit["_records"]
                w["_items"] += items
                w["_notes"] += notes
                scores = [s for s in (w["score"], visit["score"]) if s is not None]
                w["score"] = min(scores) if scores else None
                w["grade"] = max((g for g in (w["grade"], visit["grade"]) if g), default=None)
                if status == "Ordered Closed":
                    w["status"] = status
            else:
                by_key[key] = visit
        visits = sorted(by_key.values(), key=lambda v: (v["date"], v["_id"]))
        _followups_and_closures(visits, stats)
        for v in visits:
            v["major"] = sum(it["severity"] == "major" for it in v["_items"])
            v["minor"] = sum(it["severity"] == "minor" for it in v["_items"])
            v["grp"] = sum(it["severity"] == "grp" for it in v["_items"])
            for it in v["_items"]:
                stats.items_by_theme[(it["theme"], it["severity"])] += 1
        ids = [i.get("custom_id") for i in b.get("inspections") or [] if i.get("custom_id")]
        try:
            lat, lon = float(b.get("lat")), float(b.get("long"))
        except (TypeError, ValueError):
            lat = lon = None
        btype = (b.get("business_type") or "").strip()
        places.append({
            "id": str(b.get("business_id")), "facility_id": ids[-1] if ids else str(b.get("business_id")),
            "name": (b.get("name") or "").strip(), "address": (b.get("address") or "").strip(),
            "business_type": btype, "kind": KINDS.get(btype), "lat": lat, "lon": lon,
            "zip": str(b.get("zip") or "")[:5], "status": b.get("status"),
            "visits": visits, "dates": [v["date"] for v in visits],
        })
    return places


def _followups_and_closures(visits, stats):
    """Retype re-grade and reopening visits; mark each closure episode once, with its reason, and
    whether the County's "Approved to Reopen" visit ended it (`reopened`)."""
    trigger = None          # date of the last B/C routine or closure order
    closed = False
    episode = None          # the visit that started the current closure episode
    for v in visits:
        d = date.fromisoformat(v["date"])
        if v["type"] == "routine" and trigger and (d - trigger).days <= FOLLOWUP_DAYS:
            v["type"] = "followup"
            stats.followups += 1
        v["closed"], v["closure"], v["reopened"] = False, None, None
        if v["status"] == "Ordered Closed":
            if not closed:
                majors = any(it["severity"] == "major" for it in v["_items"])
                permit = any("permit" in n for n in v["_notes"])
                v["closed"], v["closure"], v["reopened"] = True, "health" if majors else "permit" if permit else "other", False
                stats.closures[v["closure"]] += 1
                episode = v
            closed = True
            trigger = d
        else:
            if closed and episode is not None and v["status"] == "Approved to Reopen":
                episode["reopened"] = True
            closed = False
            if v["type"] == "routine" and ((v["score"] is not None and v["score"] < 90) or v["grade"] in ("B", "C")):
                trigger = d


def district_lookup(geojson: dict):
    """(lon, lat) -> City of San Diego council district, or None outside the City."""
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree
    polys, nums = [], []
    for f in geojson["features"]:
        p = f["properties"]
        if (p.get("JUR_NAME") or "").upper() == "SAN DIEGO":
            polys.append(shape(f["geometry"]))
            nums.append(int(p["DISTRICT"]))
    if sorted(nums) != list(range(1, len(nums) + 1)):
        raise ValueError(f"expected City districts 1..N, got {sorted(nums)}")
    tree = STRtree(polys)

    def lookup(lon, lat):
        if lon is None or lat is None:
            return None
        hits = tree.query(Point(lon, lat), predicate="intersects")
        return nums[int(min(hits))] if len(hits) else None
    return lookup


def load_districts(path: Path = DISTRICTS) -> dict:
    if not path.exists():
        import requests
        try:
            import truststore
            truststore.inject_into_ssl()
        except ImportError:
            pass
        r = requests.get(DISTRICTS_URL, timeout=120, headers={"User-Agent": "sdfood-inspection-research/1.0"})
        r.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    return json.loads(path.read_text(encoding="utf-8"))


# ── a place as of a date ───────────────────────────────────────────────────────────────

BAND_KINDS = {"restaurant"}   # bands and the rule are for restaurants; the record covers every PUBLIC_KIND
CLOSURE_SCORE = 70            # for the model only: a routine that ended in a closure order counts as a failing C
EPSILON = 0.01                # the public rule must be within this AUC of the best model at every validation origin
MAX_FEATURES = 6
MAX_WEIGHT = 20       # whole points per unit; one point below 100 is the unit
BASELINE_NAMES = ("persistence", "last score")   # compared with the public rule's bands (the average rule is a candidate)


def _d(s):
    return date.fromisoformat(s)


def history(place, T):
    """Visits strictly before T (an ISO date)."""
    return place["visits"][:bisect.bisect_left(place["dates"], T)]


def features_at(place, T):
    """The record in the year before T, as numbers. None when there is no visit in that year.

    Scores are real routine scores; a routine visit that ended in a closure order has none, and
    counts as CLOSURE_SCORE in the averages the rule reads (never shown). A reinspection within
    COMPLAINT_DAYS after a complaint visit does not count: the site must not feed its own rule."""
    h = history(place, T)
    lo = (_d(T) - timedelta(days=WINDOW_DAYS)).isoformat()
    w = [v for v in h if v["date"] >= lo]
    if not w:
        return None
    rec = [v for v in w if v["type"] in RECORD_TYPES]
    routine = [v for v in rec if v["type"] == "routine"]
    lo_s = (_d(T) - timedelta(days=SCORE_WINDOW_DAYS)).isoformat()
    routine_s = [v for v in h if v["type"] == "routine" and v["date"] >= lo_s]
    scored = [v["score"] for v in routine_s if v["score"] is not None]
    rated = [v["score"] if v["score"] is not None else CLOSURE_SCORE for v in routine_s
             if v["score"] is not None or v["closure"] == "health"]
    complaints = [_d(v["date"]) for v in h if v["type"] == "complaint"]

    def prompted(v):
        d = _d(v["date"])
        return any(0 <= (d - c).days <= COMPLAINT_DAYS for c in complaints)
    lo2 = (_d(T) - timedelta(days=ELIGIBLE_DAYS)).isoformat()
    avg = float(np.mean(scored)) if scored else math.nan
    last = float(scored[-1]) if scored else math.nan
    f = {
        "avg_score": avg,
        "last_score": last,
        "avg_deficit": float(100 - round(float(np.mean(rated)))) if rated else 0.0,
        "last_deficit": float(100 - rated[-1]) if rated else 0.0,
        "no_score": 0.0 if rated else 1.0,
        "routines": len(routine),
        "routines_major": sum(v["major"] > 0 for v in routine),
        "majors": sum(v["major"] for v in rec),
        "health_closures": sum(v["closure"] == "health" for v in rec),
        "reinspections": sum(v["type"] == "reinspection" and not prompted(v) for v in rec),
        "grp": sum(v["grp"] for v in routine),
        "rated_2y": sum(v["type"] == "routine" and (v["score"] is not None or v["closure"] == "health")
                        and v["date"] >= lo2 for v in h),
    }
    for t in RISK_THEMES:
        f[f"theme_{t}"] = sum(it["theme"] == t and it["severity"] != "grp" for v in rec for it in v["_items"])
    for k in MODEL_KINDS:
        f[f"kind_{k}"] = float(place["kind"] == k)
    return f


def eligible(f):
    """Scored only with two rated routine inspections in the last two years: a place's points never
    rest on a single inspector's single visit."""
    return f is not None and f["rated_2y"] >= 2


def label_at(place, T):
    """(1 or 0, the inspection's key) from the first routine inspection in the year from T;
    (None, None) when there was none."""
    end = (_d(T) + timedelta(days=LABEL_DAYS)).isoformat()
    for v in place["visits"][bisect.bisect_left(place["dates"], T):]:
        if v["date"] >= end:
            break
        if v["type"] == "routine":
            return int(v["major"] > 0), v["_id"] or v["date"]
    return None, None


SCOPES = {
    "city": lambda p: p["kind"] in PUBLIC_KINDS and p.get("district") is not None,        # the record's places
    "city_bands": lambda p: p["kind"] in BAND_KINDS and p.get("district") is not None,    # the rule's candidates
    "train": lambda p: p["kind"] in BAND_KINDS,                                           # county-wide restaurants
    "county": lambda p: p["kind"] in PUBLIC_KINDS,                                        # the record, county-wide
    "county_bands": lambda p: p["kind"] in BAND_KINDS,                                    # the rule, county-wide
}


def active_at(place, T, *, scope="city", forward=False):
    """A candidate on T: in scope, visited within ACTIVE_DAYS before T, and for today's list a permit
    that has not expired."""
    if place["kind"] is None or not SCOPES[scope](place):
        return False
    h = history(place, T)
    if not h or (_d(T) - _d(h[-1]["date"])).days > ACTIVE_DAYS:
        return False
    return not (forward and (place.get("status") or "").lower() == "expired")


def month_starts(first: date, last: date) -> list[str]:
    out, d = [], date(first.year, first.month, 1)
    if d < first:
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    while d <= last:
        out.append(d.isoformat())
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


@dataclass
class Frame:
    X: np.ndarray                    # NUMERIC features (the comparators)
    F: np.ndarray                    # COUNT_FEATURES (the rules)
    y: np.ndarray                    # label, nan when unlabelled
    keys: list                       # (place id, labelling inspection) for event weights
    idx: list                        # (place index, T)
    feats: list                      # feature dicts


def frame(places, dates, *, scope, labelled, forward=False, cache=None):
    rows, ys, keys, idx, feats = [], [], [], [], []
    for T in dates:
        ck = (T, scope, forward)
        if cache is not None and ck in cache:
            part = cache[ck]
        else:
            part = []
            for i, p in enumerate(places):
                if not active_at(p, T, scope=scope, forward=forward):
                    continue
                f = features_at(p, T)
                if f is None:
                    continue
                lab, event = label_at(p, T)
                part.append((i, f, lab, event))
            if cache is not None:
                cache[ck] = part
        for i, f, lab, event in part:
            if labelled and lab is None:
                continue
            ys.append(np.nan if lab is None else lab)
            keys.append((places[i]["id"], event))
            idx.append((i, T))
            feats.append(f)
    X = np.array([[f[c] for c in NUMERIC] for f in feats], dtype=float).reshape(-1, len(NUMERIC))
    F = np.array([[f[c] for c in COUNT_FEATURES] for f in feats], dtype=float).reshape(-1, len(COUNT_FEATURES))
    return Frame(X, F, np.asarray(ys, dtype=float), keys, idx, feats)


def event_weights(keys):
    """Monthly snapshots put the same inspection under several rows; weight each labelled
    inspection to one in total, so a place inspected rarely does not count more."""
    n = Counter(keys)
    return np.array([1.0 / n[k] for k in keys])


# ── the rules ──────────────────────────────────────────────────────────────────────────

THEME_WORDS = {"temperature": "food-temperature", "handwashing": "hand-washing", "hygiene": "employee-hygiene",
               "sanitizing": "cleaning and sanitizing", "supplier": "food-source", "condition": "food-condition",
               "process": "special-process (HACCP)", "vermin": "pest", "plumbing": "plumbing and water",
               "storage": "food-storage"}
COUNT_FEATURES = (["avg_deficit", "last_deficit", "routines_major", "majors", "health_closures",
                   "reinspections", "grp"] + [f"theme_{t}" for t in RISK_THEMES])
FEATURE_TEXT = {
    "avg_deficit": ("Points below 100, average routine score over the last two years", "per point below 100"),
    "last_deficit": ("Points below 100, last routine score", "per point below 100"),
    "routines_major": ("Routine inspections with a major violation in the last year", "per inspection"),
    "majors": ("Major violations in the last year", "per violation"),
    "health_closures": ("Closure orders on a day a major was cited, last year", "per closure"),
    "reinspections": ("Reinspections in the last year (not after a complaint)", "per reinspection"),
    "grp": ("Good-retail-practice items at routine inspections, last year", "per item"),
    **{f"theme_{t}": (f"{w[0].upper() + w[1:]} citations in the last year", "per citation")
       for t, w in THEME_WORDS.items()},
}
RULE_TEXT = {
    "average score": "Restaurants are ordered by how far their average routine score over the last two years fell below "
                     "100 (a routine inspection that ended in a closure order counts as 70).",
    "count score": "Restaurants get whole points for each point their routine scores fell below 100 and for each "
                   "citation or closure listed, as shown on each worksheet; more points come first.",
}


@dataclass
class Score:
    """A published rule: points = sum of weight x value over its features, weights whole and >= 0."""
    name: str
    features: list
    weights: list
    intercept: float = 0.0
    slope: float = 0.0

    def score(self, F):
        cols = [COUNT_FEATURES.index(c) for c in self.features]
        return F[:, cols] @ np.array(self.weights, dtype=float) if cols else np.zeros(len(F))


AVERAGE_RULE = Score("average score", ["avg_deficit"], [1])


def _nonneg_logistic(Z, y, w, lam, active):
    """Sparse logistic regression with every weight >= 0: minimise the weighted log loss plus
    lam * sum(weights). Returns (intercept, weights over `active`)."""
    from scipy.optimize import minimize
    A = Z[:, active]
    sw = w / w.sum()

    def fun(p):
        z = p[0] + A @ p[1:]
        loss = np.logaddexp(0, z) - y * z
        g = (1 / (1 + np.exp(-z)) - y) * sw
        return float(sw @ loss + lam * p[1:].sum()), np.concatenate([[g.sum()], A.T @ g + lam])
    p0 = np.zeros(1 + A.shape[1])
    p0[0] = math.log(max(y @ sw, 1e-6) / max(1 - y @ sw, 1e-6))
    res = minimize(fun, p0, jac=True, method="L-BFGS-B", bounds=[(None, None)] + [(0, None)] * A.shape[1])
    return res.x[0], res.x[1:]


def fit_count(F, y, w, max_features=MAX_FEATURES, max_weight=MAX_WEIGHT):
    """The count score: choose at most `max_features` along a lasso path on standardised features
    (weights >= 0), refit them unpenalised on their own units, and round to whole points per unit
    with the multiplier that keeps the most likelihood."""
    sd = F.std(axis=0)
    sd[sd == 0] = 1.0
    Zs = F / sd
    allc = np.arange(F.shape[1])
    chosen = np.array([], dtype=int)
    for lam in np.geomspace(0.05, 1e-4, 40):
        _, wts = _nonneg_logistic(Zs, y, w, lam, allc)
        nz = np.flatnonzero(wts > 1e-4)
        if len(nz) > max_features:
            break
        chosen = nz
    if not len(chosen):
        return Score("count score", [], [])
    _, wts = _nonneg_logistic(F, y, w, 0.0, chosen)
    deficits = [k for k, c in enumerate(chosen) if COUNT_FEATURES[c] in ("avg_deficit", "last_deficit")]
    best = None
    for m in np.geomspace(0.5, 400, 320):
        pts = np.round(wts * m).astype(int)
        if pts.max() > max_weight or pts.max() == 0:
            continue
        # One point below 100 is the unit: a chosen score deficit must keep at least a point, or the
        # rounding would silently drop the strongest signal in favour of rare citations.
        if deficits and max(pts[k] for k in deficits) < 1:
            continue
        keep = pts > 0
        total = F[:, chosen[keep]] @ pts[keep]
        a, c = _nonneg_logistic(total[:, None].astype(float), y, w, 0.0, np.array([0]))
        z = a + c[0] * total
        ll = float(w @ (y * z - np.logaddexp(0, z)))
        if best is None or ll > best[0] + 1e-9:
            best = (ll, chosen[keep], pts[keep], a, c[0])
    if best is None:
        return Score("count score", [], [])
    _, cols, pts, a, c = best
    order = np.argsort(-pts, kind="stable")
    return Score("count score", [COUNT_FEATURES[i] for i in cols[order]], [int(p) for p in pts[order]], float(a), float(c))


def fit_logistic(X, y, w):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    m = make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                      LogisticRegression(max_iter=5000, C=0.5))
    return m.fit(X, y, logisticregression__sample_weight=w)


def _hgb(additive):
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=100,
                                          l2_regularization=1.0, early_stopping=False, random_state=SEED,
                                          monotonic_cst=[MONOTONE[c] for c in NUMERIC],
                                          interaction_cst="no_interactions" if additive else None)


def fit_boosted(X, y, w):
    return _hgb(False).fit(X, y, sample_weight=w)


def fit_additive(X, y, w):
    """A monotone additive model: one shape function per feature, no interactions (the most accurate
    interpretable comparator; not published because it has no whole-point form here)."""
    return _hgb(True).fit(X, y, sample_weight=w)


def _col(X, name):
    return X[:, NUMERIC.index(name)]


def persistence(X):
    """What an inspector already has, no model: routine inspections with a major in the last year,
    then majors in the last year, then the lowest last routine score."""
    last = np.nan_to_num(_col(X, "last_score"), nan=97.0)
    return _col(X, "routines_major") * 1e4 + np.minimum(_col(X, "majors"), 99) * 10 + (100 - last) / 100


def last_score_rank(X):
    return -np.nan_to_num(_col(X, "last_score"), nan=97.0)


BASELINES = {"persistence": persistence, "last score": last_score_rank}
PUBLISHABLE = ("average score", "count score")      # sparsest first


def ranking(score, tiebreak):
    """Order by score, then by the lower average routine score, then by input order (catch tables only;
    bands never use a tiebreak)."""
    return np.lexsort((np.arange(len(score)), tiebreak, -score))


def catch_table(order, positive, ks):
    cum = np.cumsum(positive[order])
    total = int(positive.sum())
    return {str(k): {"caught": int(cum[k - 1]), "total": total} for k in ks if k <= len(order)}


def auc(y, s):
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, s)) if len(set(y)) == 2 else None


def wilson(k, n, z=1.96):
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 4), round(c + h, 4))


def clusters(places, idx):
    """Candidates at one street address share inspection days, so bootstraps resample addresses."""
    ids = {}
    return np.array([ids.setdefault(_norm(places[i]["address"]), len(ids)) for i, _ in idx])


def _cluster_draws(cl, n_boot, seed):
    rng = np.random.default_rng(seed)
    groups_ = defaultdict(list)
    for j, c in enumerate(cl):
        groups_[c].append(j)
    keys = np.array(list(groups_))
    for _ in range(n_boot):
        yield np.concatenate([groups_[g] for g in rng.choice(keys, len(keys))])


def catch_interval(order, positive, cl, ks, n_boot=BOOT, seed=SEED):
    """95% interval for caught@K with the ranking held fixed, resampling address clusters."""
    rank_of = np.empty(len(order), int)
    rank_of[order] = np.arange(len(order))
    ks = [k for k in ks if k <= len(order)]
    draws = {k: [] for k in ks}
    for pick in _cluster_draws(cl, n_boot, seed):
        r = rank_of[pick]
        for k in ks:
            draws[k].append(float(positive[pick][r < k].sum()))
    return {str(k): [int(np.percentile(v, 2.5)), int(np.percentile(v, 97.5))] for k, v in draws.items()}


def paired_sets(in_a, in_b, positive, cl, n_boot=BOOT, seed=SEED):
    """95% interval for (hits in set a) - (hits in set b) over the same candidates, resampling addresses."""
    d = [float((positive[p] * in_a[p]).sum() - (positive[p] * in_b[p]).sum()) for p in _cluster_draws(cl, n_boot, seed)]
    return [round(float(np.percentile(d, 2.5)), 2), round(float(np.percentile(d, 97.5)), 2)]


def paired_auc(y, s_a, s_b, labelled, cl, n_boot=BOOT, seed=SEED):
    """95% interval for AUC(a) - AUC(b) on the labelled candidates, resampling addresses."""
    d = []
    for p in _cluster_draws(cl, n_boot, seed):
        lab = p[labelled[p]]
        if len(set(y[lab])) == 2:
            d.append(auc(y[lab], s_a[lab]) - auc(y[lab], s_b[lab]))
    return [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)] if d else [None, None]


# ── one origin: fit everything on what was known, score the City's restaurants ──────────

def origin_dates(places):
    first = _d(min(p["dates"][0] for p in places if p["dates"]))
    through = max(_d(p["dates"][-1]) for p in places if p["dates"])
    snap_first = first + timedelta(days=WINDOW_DAYS)
    confirm = month_starts(through - timedelta(days=LABEL_DAYS + 31), through - timedelta(days=LABEL_DAYS))[-1]
    c = _d(confirm)
    validate = [date(c.year - (c.month <= m), (c.month - m - 1) % 12 + 1, 1).isoformat() for m in (6, 3)]
    return snap_first, through, validate, confirm


def train_frame(places, snap_first, T, cache):
    dates = month_starts(snap_first, _d(T) - timedelta(days=LABEL_DAYS))
    return frame(places, dates, scope="train", labelled=True, cache=cache), dates


def fit_all(fr):
    w = event_weights(fr.keys)
    rated = np.array([f["no_score"] == 0.0 for f in fr.feats])   # the rules only ever score rated places
    return {"count score": fit_count(fr.F[rated], fr.y[rated], w[rated]), "logistic": fit_logistic(fr.X, fr.y, w),
            "boosted": fit_boosted(fr.X, fr.y, w), "additive": fit_additive(fr.X, fr.y, w)}


def score_all(models, fr):
    s = {"average score": AVERAGE_RULE.score(fr.F), "count score": models["count score"].score(fr.F)}
    for m in ("logistic", "boosted", "additive"):
        s[m] = models[m].predict_proba(fr.X)[:, 1]
    for name, fn in BASELINES.items():
        s[name] = fn(fr.X)
    return s


def run_origin(places, snap_first, T, cache, log=print):
    tr, dates = train_frame(places, snap_first, T, cache)
    if not dates or len(set(tr.y)) < 2:
        raise SystemExit(f"not enough history for an origin at {T}")
    models = fit_all(tr)
    te = frame(places, [T], scope="city_bands", labelled=False, cache=cache)
    scores = score_all(models, te)
    tiebreak = np.nan_to_num(_col(te.X, "avg_score"), nan=97.0)
    orders = {m: ranking(s, tiebreak) for m, s in scores.items()}
    labelled = ~np.isnan(te.y)
    positive = np.nan_to_num(te.y, nan=0.0)
    elig = np.array([eligible(f) for f in te.feats])
    ks = sorted(set(KS) | {min(K_GATE, len(te.y))})
    res = {"as_of": T, "trained_on": f"{dates[0]} to {dates[-1]} ({len(dates)} monthly snapshots, "
                                       f"{len(tr.y):,} labelled rows, county-wide restaurants)",
           "candidates": len(te.y), "eligible": int(elig.sum()), "labelled": int(labelled.sum()),
           "positives": int(positive.sum()), "count_rule": models["count score"], "models": {}}
    for m, s in scores.items():
        res["models"][m] = {"auc": auc(te.y[labelled], s[labelled]),
                            "auc_eligible": auc(te.y[labelled & elig], s[labelled & elig]),
                            "catch": catch_table(orders[m], positive, ks)}
    res.update(_te=te, _tr=tr, _scores=scores, _orders=orders, _positive=positive, _labelled=labelled, _eligible=elig,
               _models=models)
    log(f"origin {T}: {res['candidates']:,} City restaurants ({res['eligible']:,} eligible), {res['positives']:,} "
        f"positives; AUC " + ", ".join(f"{m} {v['auc']:.3f}" for m, v in res["models"].items() if v["auc"]))
    return res


def select_rule(validation):
    """The rule, fixed here: the sparsest publishable candidate whose AUC is within EPSILON of the best
    model's at every validation origin. If none is, the most accurate publishable one, flagged."""
    table = [{"as_of": r["as_of"], **{m: v["auc_eligible"] for m, v in r["models"].items()}} for r in validation]
    for m in PUBLISHABLE:
        if all(row[m] is not None and row[m] >= max(v for k, v in row.items() if k != "as_of" and v is not None) - EPSILON
               for row in table):
            return m, {"rule": f"the sparsest of {', '.join(PUBLISHABLE)} within {EPSILON} AUC of the best model at "
                               "every validation origin", "within_epsilon": True, "validation": table}
    best = max(PUBLISHABLE, key=lambda m: np.mean([row[m] for row in table]))
    return best, {"rule": f"the sparsest of {', '.join(PUBLISHABLE)} within {EPSILON} AUC of the best model at every "
                          "validation origin (none was: the most accurate publishable rule is shown, flagged)",
                  "within_epsilon": False, "validation": table}


# ── bands, stability, utility, fairness ────────────────────────────────────────────────

def band_thresholds(points, shares=BANDS):
    """Whole-point cut-offs nearest each target share of the eligible list, never splitting a tie."""
    s = np.sort(points)[::-1]
    n = len(s)
    values = np.unique(s)[::-1]
    cum = [(v, int((s >= v).sum())) for v in values]
    cuts = []
    for share, _ in shares:
        target = share * n
        v, c = min(cum, key=lambda vc: (abs(vc[1] - target), -vc[0]))
        if cuts and v >= cuts[-1]:
            continue
        cuts.append(float(v))
    return cuts


def assign_bands(points, elig, cuts):
    """Band keys ("1", "2", ...) by cut-off; None below the last cut or when not eligible."""
    out = np.full(len(points), None, dtype=object)
    for j, p in enumerate(points):
        if not elig[j]:
            continue
        for b, c in enumerate(cuts):
            if p >= c:
                out[j] = str(b + 1)
                break
    return out


def band_rows(bands, points, positive, labelled, elig, baseline_order=None, cl=None):
    """Hit rate by band among the eligible, with Wilson intervals; and the baseline's same-size group
    of eligible places, with the paired difference in hits."""
    keys = sorted({b for b in bands if b is not None}, key=int)
    rows, prev = [], 0
    el_order = [j for j in (baseline_order if baseline_order is not None else []) if elig[j]]
    for k in keys:
        inb = np.array([b == k for b in bands])
        n, lab, pos = int(inb.sum()), int((inb & labelled).sum()), int((positive * inb).sum())
        row = {"band": k, "min_points": int(points[inb].min()), "max_points": int(points[inb].max()), "places": n,
               "labelled": lab, "positives": pos, "rate": round(pos / lab, 4) if lab else None,
               "interval": wilson(pos, lab), "baseline_rate": None, "baseline_interval": None, "vs_baseline": None}
        if el_order:
            group = np.zeros(len(points), bool)
            group[el_order[prev:prev + n]] = True
            bl, bp = int((group & labelled).sum()), int((positive * group).sum())
            row.update(baseline_rate=round(bp / bl, 4) if bl else None, baseline_interval=wilson(bp, bl),
                       vs_baseline=paired_sets(inb, group, positive, cl) if cl is not None else None)
        prev += n
        rows.append(row)
    rest = elig & np.array([b is None for b in bands])
    lab, pos = int((rest & labelled).sum()), int((positive * rest).sum())
    rest_row = {"band": "rest", "places": int(rest.sum()), "labelled": lab, "positives": pos,
                "rate": round(pos / lab, 4) if lab else None, "interval": wilson(pos, lab)}
    return rows, rest_row


def merge_overlapping(cuts, points, positive, labelled, elig):
    """Merge adjacent bands whose intervals overlap, until none do: a band must mean something the
    band below it does not. Merging bands k and k+1 removes the cut between them (band k's)."""
    cuts = list(cuts)
    while len(cuts) > 1:
        rows, _ = band_rows(assign_bands(points, elig, cuts), points, positive, labelled, elig)
        pair = next((i for i, (a, b) in enumerate(zip(rows, rows[1:]))
                     if a["interval"][0] is not None and b["interval"][1] is not None and a["interval"][0] <= b["interval"][1]), None)
        if pair is None:
            break
        del cuts[pair]
    return cuts


def named_bands(rows, cost_ratio):
    """Bands whose interval clears p > C/(B+C): naming a place is worth it in expectation only when
    a hit is that likely. `cost_ratio` is C/B."""
    bar = cost_ratio / (1 + cost_ratio)
    return [r["band"] for r in rows if r["interval"][0] is not None and r["interval"][0] > bar]


def utility_table(rows, ratios=(0.25, 0.5, 1, 2, 3)):
    return [{"cost_ratio": r, "bar": round(r / (1 + r), 4), "named": named_bands(rows, r)} for r in ratios]


def stability(rule, fr_train, fr_now, elig_now, band_now, refits=REFITS, seed=SEED):
    """For a fitted rule: refit on facility-resampled training data and recut bands at the same shares
    of today's eligible list; how often each place keeps its band. A fixed rule (the average rule) has
    nothing to refit: 1.0."""
    if rule.name != "count score" or not refits:
        return np.where(np.array([b is not None for b in band_now]), 1.0, np.nan), None
    rng = np.random.default_rng(seed)
    w = event_weights(fr_train.keys)
    by_place = defaultdict(list)
    for j, k in enumerate(fr_train.keys):
        by_place[k[0]].append(j)
    ids = np.array(list(by_place))
    shares = [(float(np.mean(np.array([b is not None and int(b) <= int(k) for b in band_now])[elig_now])), k)
              for k in sorted({b for b in band_now if b is not None}, key=int)]
    same = np.zeros(len(band_now))
    for _ in range(refits):
        pick = np.concatenate([by_place[i] for i in rng.choice(ids, len(ids))])
        r = fit_count(fr_train.F[pick], fr_train.y[pick], w[pick])
        pts = r.score(fr_now.F)
        cuts = band_thresholds(pts[elig_now], shares)
        b = assign_bands(pts, elig_now, cuts)
        same += np.array([x == y for x, y in zip(b, band_now)])
    return same / refits, shares


def district_fairness(places, idx, positive, labelled, named, n_boot=2000, seed=SEED):
    """For a named list the harm is a place named that turns out clean. By council district: named,
    precision, the false-positive rate against the City's, and the district's share of the wrongly
    named over its share of candidates, with an address-cluster bootstrap interval."""
    g = np.array([str(places[i]["district"]) for i, _ in idx])
    fp = named & labelled & (positive == 0)
    neg = labelled & (positive == 0)
    fpr_all = fp.sum() / max(1, neg.sum())
    out = {}
    for name in sorted(set(g), key=lambda x: int(x) if x.isdigit() else 99):
        m = g == name
        nm = int((named & m).sum())
        out[name] = {"candidates": int(m.sum()), "named": nm, "named_positive": int((named & m & (positive == 1)).sum()),
                     "false_named": int((fp & m).sum()),
                     "precision": round(float((named & m & (positive == 1)).sum() / max(1, (named & m & labelled).sum())), 3) if nm else None,
                     "fpr_ratio": round(float((fp & m).sum() / max(1, (neg & m).sum()) / fpr_all), 2) if fpr_all else None,
                     "false_share_ratio": round(float(((fp & m).sum() / max(1, fp.sum())) / (m.sum() / len(g))), 2) if fp.sum() else None,
                     "interval": None}
    cl = clusters(places, idx)
    draws = defaultdict(list)
    for p in _cluster_draws(cl, n_boot, seed):
        tot = fp[p].sum()
        if not tot:
            continue
        for name in out:
            m = g[p] == name
            if m.sum():
                draws[name].append((fp[p][m].sum() / tot) / (m.sum() / len(p)))
    for name, v in draws.items():
        out[name]["interval"] = [round(float(np.percentile(v, 2.5)), 2), round(float(np.percentile(v, 97.5)), 2)]
    return out


def fairness_problems(fair, min_named=10):
    """Block on the point estimate, not on proof of harm: a district with enough named places whose
    share of the wrongly named, or false-positive rate, runs well above even; or any district whose
    interval reaches twice its share."""
    out = []
    for g, e in fair.items():
        if e["named"] >= min_named and e["false_share_ratio"] is not None and e["false_share_ratio"] > 1.25:
            out.append(f"district {g}: {e['false_share_ratio']}x its share of wrongly named places ({e['named']} named)")
        if e["named"] >= min_named and e["fpr_ratio"] is not None and e["fpr_ratio"] > 1.5:
            out.append(f"district {g}: false-positive rate {e['fpr_ratio']}x the City's")
        if e["interval"] and e["interval"][1] > 2.0 and e["named"] >= 3:
            out.append(f"district {g}: the share of wrongly named places could be up to {e['interval'][1]}x even")
    return out


# ── measurement checks (report only) ──────────────────────────────────────────────────

def measurement(places):
    """What the label is made of: score heaping at the A line, repeatability, the share of majors
    that still got an A, agreement between co-located places on the same day against a different-day
    control, and the base rate by quarter."""
    scores, a_major, graded_major, by_q = Counter(), 0, 0, defaultdict(lambda: [0, 0])
    graded, a_total, pairs = 0, 0, []
    by_addr = defaultdict(list)
    for p in places:
        prev = None
        for v in p["visits"]:
            if v["type"] != "routine":
                continue
            if v["score"] is not None:
                scores[v["score"]] += 1
            if v["grade"]:
                graded += 1
                a_total += v["grade"] == "A"
                if v["major"]:
                    graded_major += 1
                    a_major += v["grade"] == "A"
            q = f"{v['date'][:4]}Q{(int(v['date'][5:7]) - 1) // 3 + 1}"
            by_q[q][0] += 1
            by_q[q][1] += v["major"] > 0
            if prev is not None:
                pairs.append((prev > 0, v["major"] > 0))
            prev = v["major"]
            by_addr[_norm(p["address"])].append((v["date"], p["id"], v["major"] > 0))
    same, apart = [], []
    for vs in by_addr.values():
        if len(vs) > 60:
            continue
        for i in range(len(vs)):
            for j in range(i + 1, len(vs)):
                (d1, b1, m1), (d2, b2, m2) = vs[i], vs[j]
                if b1 == b2:
                    continue
                gap = abs((_d(d1) - _d(d2)).days)
                if gap == 0:
                    same.append((m1, m2))
                elif gap >= 60:
                    apart.append((m1, m2))
    after = lambda cond: (sum(b for a, b in pairs if a == cond) / max(1, sum(1 for a, _ in pairs if a == cond)))
    corr = lambda ps: round(float(np.corrcoef(np.array(ps, float).T)[0, 1]), 3) if len(ps) > 30 else None
    return {
        "scores_86_to_92": {str(s): scores[s] for s in range(86, 93)},
        "graded_A_share": round(a_total / graded, 4) if graded else None,
        "majors_graded_A_share": round(a_major / graded_major, 4) if graded_major else None,
        "major_after_major": round(after(True), 4), "major_after_clean": round(after(False), 4),
        "same_day_pairs": len(same), "same_day_corr": corr(same),
        "different_day_pairs": len(apart), "different_day_corr": corr(apart),
        "major_rate_by_quarter": {q: round(v[1] / v[0], 4) for q, v in sorted(by_q.items()) if v[0] >= 200},
    }


# ── what the site shows ────────────────────────────────────────────────────────────────

def display_records(place):
    """One entry per County record, in date order, with the County's own status text. The type
    (followup), closure reason and reopening are the pipeline's readings of the merged visit."""
    out = []
    for v in place["visits"]:
        first_closed = True
        for r in v["_records"]:
            closed = v["closed"] and r["status"] == "Ordered Closed" and first_closed
            if closed:
                first_closed = False
            items = r["_items"]
            out.append({"date": r["date"], "status": r["status"], "type": v["type"],
                        "score": r["score"] if v["type"] in ("routine", "followup") else None, "grade": r["grade"],
                        "major": sum(i["severity"] == "major" for i in items),
                        "minor": sum(i["severity"] == "minor" for i in items),
                        "grp": sum(i["severity"] == "grp" for i in items),
                        "closed": closed, "closure": v["closure"] if closed else None,
                        "reopened": v["reopened"] if closed else None, "_items": items})
    return out


def posted_grade(records):
    """The grade on the County's card in the window: the latest letter from a routine or re-grade
    record; `replaced` is the routine B or C that a re-grade directly followed."""
    graded = [r for r in records if r["grade"] and r["type"] in ("routine", "followup")]
    if not graded:
        return None
    g = graded[-1]
    replaced = None
    if g["type"] == "followup" and len(graded) > 1 and graded[-2]["type"] == "routine" and graded[-2]["grade"] in ("B", "C"):
        prev = graded[-2]
        replaced = {"grade": prev["grade"], "score": prev["score"], "date": prev["date"]}
    return {"grade": g["grade"], "score": g["score"], "date": g["date"], "replaced": replaced}


def flags(records, visits):
    """Record facts from the 12 months before the last visit, for the site's filters."""
    if not records:
        return []
    lo = (_d(records[-1]["date"]) - timedelta(days=WINDOW_DAYS)).isoformat()
    rec = [r for r in records if r["date"] >= lo]
    out = []
    if any(r["major"] for r in rec):
        out.append("major")
    if any(r["closed"] and r["closure"] == "health" for r in rec):
        out.append("closed")
    if any(r["type"] == "routine" and r["grade"] in ("B", "C") for r in rec):
        out.append("bc")
    if sum(v["type"] == "reinspection" for v in visits if v["date"] >= lo) >= 2:
        out.append("repeat")
    out += sorted({i["theme"] for r in rec for i in r["_items"] if i["severity"] == "major" and i["theme"] != "other"})
    return out


def violations_shown(records):
    if not records:
        return []
    cutoff = (_d(records[-1]["date"]) - timedelta(days=RECORD_DAYS)).isoformat()
    viol = [{"date": r["date"], "visit": r["type"], **i} for r in records if r["date"] >= cutoff for i in r["_items"]]
    majors = [x for x in viol if x["severity"] == "major"]
    rest = [x for x in viol if x["severity"] != "major"]
    return (majors + rest)[:MAX_VIOLATIONS]


def entry(place, extra=None):
    """(index feature, detail) for one place."""
    recs = display_records(place)
    last = recs[-1] if recs else None
    idx_props = {"facility_id": place["facility_id"], "name": place["name"], "address": place["address"],
                 "facility_type": place["kind"], "council_district": place["district"],
                 "last_visit": {"date": last["date"], "type": last["type"]} if last else None,
                 "grade": posted_grade(recs), "flags": flags(recs, place["visits"])}
    detail_only = {}
    for k, v in (extra or {}).items():
        (idx_props if k in ("band", "points", "on_hold") else detail_only).__setitem__(k, v)
    feature = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(place["lon"], 6), round(place["lat"], 6)]},
               "properties": idx_props}
    detail = {**idx_props, "business_type": place["business_type"],
              "inspections": [{k: v for k, v in r.items() if k != "_items"} for r in recs],
              "violations": violations_shown(recs), **detail_only}
    return feature, detail


def worksheet(rule, f):
    return [{"item": c, "weight": w, "value": f[c], "points": w * f[c], "met": w * f[c] > 0}
            for c, w in zip(rule.features, rule.weights)]


def dedupe(order, places, idx):
    """One entry per business name at one address (a restaurant and its bar can hold two permits)."""
    seen, out = set(), []
    for j in order:
        p = places[idx[j][0]]
        k = (_norm(p["name"]), _norm(p["address"]))
        if k in seen:
            continue
        seen.add(k)
        out.append(j)
    return out


# ── provenance, approval, holds, notices ───────────────────────────────────────────────

def sha256_file(path: Path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def provenance(raw_path=RAW):
    def git(*a):
        try:
            return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:
            return ""
    sha = git("rev-parse", "HEAD") or "unknown"
    dirty = bool(git("status", "--porcelain", "--", "export_site.py"))
    pkgs = {}
    for m in ("numpy", "scipy", "sklearn", "shapely"):
        try:
            pkgs[m] = __import__(m).__version__
        except Exception:
            pkgs[m] = None
    return {"code_sha": sha + ("-dirty" if dirty else ""), "pull_sha256": sha256_file(raw_path) if Path(raw_path).exists() else None,
            "python": sys.version.split()[0], "packages": pkgs}


def _json(path, default):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else default


def load_holds(path=HOLDS):
    return set(_json(path, {}).get("facility_ids", []))


def load_corrections(path=CORRECTIONS):
    return _json(path, [])


APPROVAL_FIELDS = ("approver", "date", "run", "facilities_sha256", "contact", "reason", "insurance")


def check_approval(a, mode, meta, facilities_sha):
    """Every reason docs/PUBLISH_APPROVAL.json does not approve this export ([] when it does)."""
    if not a:
        return ["no docs/PUBLISH_APPROVAL.json: naming or publishing is a decision people sign (docs/PUBLISHING.md)"]
    p = []
    for k in APPROVAL_FIELDS:
        if not a.get(k) or any(t in str(a[k]) for t in ("Full names", "an address that", "YYYY", "sha256 of")):
            p.append(f"approval field `{k}` is missing or still the template")
    try:
        date.fromisoformat(str(a.get("date")))
    except ValueError:
        p.append("approval `date` is not a date")
    if "@" not in str(a.get("contact", "")):
        p.append("approval `contact` is not an email address")
    if a.get("run") != meta["run"]:
        p.append(f"the approval is for run {a.get('run')}, not {meta['run']}: an approval covers one list")
    if a.get("facilities_sha256") != facilities_sha:
        p.append("the approval's facilities_sha256 does not match data/site/facilities.geojson: approve the file you read")
    for k, fields in (("responsible_adult", ("name", "contact")), ("legal_review", ("reviewer", "organization", "date", "scope")),
                      ("county_informed", ("date", "person", "method", "what_was_shown", "response"))):
        v = a.get(k) if isinstance(a.get(k), dict) else {}
        missing = [f for f in fields if not v.get(f)]
        if missing:
            p.append(f"approval `{k}` needs {', '.join(missing)}")
    ci = a["county_informed"].get("date") if isinstance(a.get("county_informed"), dict) else None
    try:
        if ci and (date.fromisoformat(meta["generated"]) - date.fromisoformat(ci)).days < 30:
            p.append("the County was told less than 30 days before this export")
    except ValueError:
        p.append("approval `county_informed.date` is not a date")
    if mode == "bands":
        try:
            ratio = float(a.get("cost_ratio"))
        except (TypeError, ValueError):
            ratio = None
            p.append("approval `cost_ratio` (C/B) is missing")
        ind = a.get("independent_reviewer") if isinstance(a.get("independent_reviewer"), dict) else {}
        if ratio is not None and ratio < MIN_COST_RATIO and not all(ind.get(f) for f in ("name", "affiliation", "date")):
            p.append(f"a cost ratio below {MIN_COST_RATIO} needs an `independent_reviewer` (name, affiliation, date)")
    if a.get("skip_prospective_reason"):
        p.append("`skip_prospective_reason` is not accepted: the prospective test cannot be waived")
    return p


def notice_problems(named_ids, run, today, notices_dir=NOTICES):
    path = Path(notices_dir) / f"{run}.csv"
    if not named_ids:
        return []
    if not path.exists():
        return [f"no notice log {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}: every named place is told first"]
    sent = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sent[row.get("facility_id")] = row.get("date_sent")
    late = [f for f in named_ids if not sent.get(f) or (today - date.fromisoformat(sent[f])).days < NOTICE_DAYS]
    return [f"{len(late)} named places were not told at least {NOTICE_DAYS} days ago (e.g. {late[0]})"] if late else []


# ── the export ────────────────────────────────────────────────────────────────────────

def _common_meta(mode, run, today, through, pull, places_n, measurement_, stats, unknown, approval, corrections):
    return {
        "mode": mode, "sample": False, "run": run, "generated": today.isoformat(), "places": places_n,
        "inspections_through": through.isoformat(), "expires": (through + timedelta(days=FRESH_DAYS)).isoformat(),
        "source": {"name": f"SD Food Info (sdfoodinfo.org), the County's published results, collected "
                           f"{(pull or {}).get('finished') or (pull or {}).get('started') or 'unknown date'}"
                           + ("" if (pull or {}).get("complete", False) else "; PARTIAL PULL"),
                   "url": RESULTS_URL},
        "grade_context": {"majors_graded_A_share": measurement_["majors_graded_A_share"],
                          "graded_A_share": measurement_["graded_A_share"]},
        "data_rules": {"dropped": dict(stats.dropped.most_common()), "same_day_merged_for_the_model": stats.merged,
                       "followups_retyped": stats.followups, "closure_episodes": dict(stats.closures),
                       "unknown_business_types": unknown},
        "survivorship": "SD Food Info lists only facilities that exist today, so the test list holds only places that "
                        "survived until the data was collected. Places that closed earlier are missing, and the few "
                        "closing places that remain had more major violations, so the test may flatter the list.",
        "provenance": provenance(),
        "contact": (approval or {}).get("contact"),
        "operator": ((approval or {}).get("responsible_adult") or None),
        "corrections": corrections,
    }


def prepare(raw, districts_geojson):
    stats = Stats()
    places = load_places(raw, stats)
    lookup = district_lookup(districts_geojson)
    for p in places:
        p["district"] = lookup(p["lon"], p["lat"]) if p["kind"] else None
    unknown = sorted({p["business_type"] for p in places if p["kind"] is None} - set(KINDS) - EXCLUDED_TYPES)
    counts = Counter(p["facility_id"] for p in places)
    for p in places:                         # the key for every link and file must be unique
        if counts[p["facility_id"]] > 1:
            p["facility_id"] = f"{p['facility_id']}-{p['id']}"
    return places, stats, unknown


def build_record(raw, districts_geojson, *, pull=None, approval=None, today=None, log=print):
    """Every listed place with the County's record, no model."""
    today = today or date.today()
    places, stats, unknown = prepare(raw, districts_geojson)
    through = max(_d(p["dates"][-1]) for p in places if p["dates"])
    t_now = (through + timedelta(days=1)).isoformat()
    now = [i for i, p in enumerate(places) if active_at(p, t_now, scope="city", forward=True)]
    order = sorted(now, key=lambda i: (_norm(places[i]["name"]), places[i]["address"]))
    seen, listed = set(), []
    for i in order:                          # one entry per business name at one address
        k = (_norm(places[i]["name"]), _norm(places[i]["address"]))
        if k not in seen:
            seen.add(k)
            listed.append(i)
    features, details = [], {}
    for i in listed:
        f, d = entry(places[i])
        features.append(f)
        details[f["properties"]["facility_id"]] = d
    meta = _common_meta("record", f"record_{t_now}", today, through, pull, len(features),
                        measurement([p for p in places if p["kind"] in PUBLIC_KINDS]), stats, unknown, approval,
                        load_corrections())
    log(f"record as of {t_now}: {len(features):,} City restaurants and markets")
    return {"type": "FeatureCollection", "features": features}, details, meta, {"places": places, "ranking": []}


def build(raw, districts_geojson, *, pull=None, approval=None, today=None, refits=REFITS, log=print):
    """The bands review export (never published unless every gate passes)."""
    today = today or date.today()
    places, stats, unknown = prepare(raw, districts_geojson)
    snap_first, through, validate, confirm = origin_dates(places)
    cache = {}
    validation = [run_origin(places, snap_first, T, cache, log) for T in validate]
    chosen, selection = select_rule(validation)
    conf = run_origin(places, snap_first, confirm, cache, log)
    rule = AVERAGE_RULE if chosen == "average score" else conf["count_rule"]
    log(f"public rule: {chosen} (validation {', '.join(validate)}; frozen and confirmed at {confirm}): "
        + ", ".join(f"{c} x{w}" for c, w in zip(rule.features, rule.weights)))

    # The confirmation origin, under the rule that is published.
    te, pos, lab, elig = conf["_te"], conf["_positive"], conf["_labelled"], conf["_eligible"]
    pts_c = rule.score(te.F)
    cl = clusters(places, te.idx)
    best_base = max(BASELINE_NAMES, key=lambda b: conf["models"][b]["auc_eligible"] or 0)
    cuts = merge_overlapping(band_thresholds(pts_c[elig]), pts_c, pos, lab, elig)
    bands_c = assign_bands(pts_c, elig, cuts)
    rows, rest = band_rows(bands_c, pts_c, pos, lab, elig, conf["_orders"][best_base], cl)
    for k, row in enumerate(rows):            # a band is its cut-offs; the top band has no upper limit
        row["min_points"] = int(cuts[k])
        row["max_points"] = int(cuts[k - 1]) - 1 if k else None
    cost_ratio = float((approval or {}).get("cost_ratio")) if (approval or {}).get("cost_ratio") is not None else None
    named_keys = named_bands(rows, cost_ratio) if cost_ratio is not None else []
    review_keys = named_keys or (["1"] if rows else [])
    named_c = np.array([b in review_keys for b in bands_c])
    fair = district_fairness(places, te.idx, pos, lab, named_c)
    rest_eligible_auc = {m: conf["models"][m]["auc_eligible"] for m in conf["models"]}
    vs_avg = paired_auc(np.nan_to_num(te.y), pts_c, AVERAGE_RULE.score(te.F), lab & elig, cl) if chosen != "average score" else None
    vs_base = paired_auc(np.nan_to_num(te.y), pts_c, conf["_scores"][best_base], lab & elig, cl)

    # Today's list: the frozen rule on today's restaurants, county-wide. Places outside the City carry
    # no council district; the site shows them when its area toggle is on. Band counts stay the City's.
    t_now = (through + timedelta(days=1)).isoformat()
    now = frame(places, [t_now], scope="county_bands", labelled=False, forward=True)
    elig_now = np.array([eligible(f) for f in now.feats])
    pts_now = rule.score(now.F)
    bands_now = assign_bands(pts_now, elig_now, cuts)
    holds = load_holds()
    stab, _ = stability(rule, conf["_tr"], now, elig_now, bands_now, refits=refits)
    keep = {r["band"]: (round(float(np.mean(stab[np.array([b == r["band"] for b in bands_now])])), 3)
                        if any(b == r["band"] for b in bands_now) else None) for r in rows}
    order = sorted(range(len(pts_now)), key=lambda j: (-(pts_now[j]), _norm(places[now.idx[j][0]]["name"])))
    # Every listed City place gets its County record; an eligible restaurant also gets its points and
    # worksheet, and a band when it is in one. (A published public export keeps only named bands.)
    scored = {now.idx[j][0]: j for j in range(len(pts_now)) if elig_now[j]}
    everyone = [i for i, p in enumerate(places) if active_at(p, t_now, scope="county", forward=True)]
    everyone.sort(key=lambda i: (-(pts_now[scored[i]]) if i in scored else 1, _norm(places[i]["name"]), places[i]["address"]))
    seen, features, details = set(), [], {}
    for i in everyone:
        p = places[i]
        k = (_norm(p["name"]), _norm(p["address"]))
        if k in seen:                        # one entry per business name at one address
            continue
        seen.add(k)
        extra = {}
        if i in scored:
            j = scored[i]
            if p["facility_id"] in holds:
                extra = {"on_hold": True}
            else:
                extra = {"points": int(pts_now[j]), "score_card": worksheet(rule, now.feats[j]),
                         "band_stability": None if np.isnan(stab[j]) else round(float(stab[j]), 2)}
                if bands_now[j] is not None:
                    extra["band"] = bands_now[j]
        f, d = entry(p, extra)
        features.append(f)
        details[p["facility_id"]] = d
    features.sort(key=lambda f: (int(f["properties"].get("band") or 99), -(f["properties"].get("points") or -1),
                                 _norm(f["properties"]["name"])))
    log(f"forward as of {t_now}: {len(pts_now):,} City restaurants, {int(elig_now.sum()):,} eligible; "
        + ", ".join(f"band {r['band']} >= {r['min_points']} points: {sum(1 for b in bands_now if b == r['band'])}" for r in rows))

    in_city = lambda j: places[now.idx[j][0]].get("district") is not None
    run = f"forward_{t_now}"
    m_ = measurement([p for p in places if p["kind"] in PUBLIC_KINDS])
    meta = _common_meta("bands", run, today, through, pull, len(features), m_, stats, unknown, approval, load_corrections())
    k_gate = min(K_GATE, conf["candidates"])
    meta.update({
        "model": f"{chosen}: " + " + ".join(f"{w} x {c}" for c, w in zip(rule.features, rule.weights)),
        "label": "at least one major violation at the next routine inspection",
        "label_window": f"{t_now} to {(_d(t_now) + timedelta(days=LABEL_DAYS - 1)).isoformat()}",
        "candidates": int(len(pts_now)),
        "card": {
            "rule": RULE_TEXT[chosen],
            "items": [{"item": c, "label": FEATURE_TEXT[c][0], "weight": w, "unit": FEATURE_TEXT[c][1], "feature": c}
                      for c, w in zip(rule.features, rule.weights)],
            "window": "the year before the list date",
            "eligibility": "restaurants with two rated routine inspections in the last two years",
            "trained_on": conf["trained_on"],
            "bands": [{**r, "share": round(float(np.mean(np.array([b is not None and int(b) <= int(r["band"]) for b in bands_c])[elig])), 4),
                       "places_now": sum(1 for j, b in enumerate(bands_now) if b == r["band"] and in_city(j)),
                       "places_now_county": sum(1 for b in bands_now if b == r["band"]), "kept_in_refits": keep.get(r["band"])}
                      for r in rows],
            "rest": rest,
            "baseline_name": best_base,
        },
        "catch": conf["models"][chosen]["catch"],
        "catch_run": {
            "as_of": confirm, "candidates": conf["candidates"], "eligible": conf["eligible"], "positives": conf["positives"],
            "labelled": conf["labelled"], "unlabelled": conf["candidates"] - conf["labelled"],
            "label_window": f"{confirm} to {(_d(confirm) + timedelta(days=LABEL_DAYS - 1)).isoformat()}",
            "trained_on": conf["trained_on"], "baseline_name": best_base,
            "baseline": conf["models"][best_base]["catch"],
            "interval": catch_interval(conf["_orders"][chosen], pos, cl, KS),
            "vs_baseline": {"baseline": best_base, "auc": vs_base, "k": k_gate},
            "vs_average_rule": vs_avg,
            "models": {m: {"auc": v["auc"], "auc_eligible": v["auc_eligible"],
                           "caught": v["catch"].get(str(k_gate), {}).get("caught")} for m, v in conf["models"].items()},
            "count_rule_at_origin": {"features": conf["count_rule"].features, "weights": conf["count_rule"].weights},
        },
        "selection": {**selection, "chosen": chosen, "confirm": confirm},
        "named_bands": named_keys, "cost_ratio": cost_ratio, "utility": utility_table(rows),
        "fairness": {"by_district": fair, "bands_used": review_keys,
                     "problems": fairness_problems(fair)},
        "measurement": m_,
        "survivorship_bound": _survivorship(places, conf, rows),
    })
    base_now = persistence(now.X)
    ranking_rows = [{"facility_id": places[now.idx[j][0]]["facility_id"], "business_id": places[now.idx[j][0]]["id"],
                     "points": round(float(pts_now[j]), 2), "band": bands_now[j] or "", "eligible": int(elig_now[j]),
                     "average_rule": round(float(AVERAGE_RULE.score(now.F)[j]), 2), "persistence": round(float(base_now[j]), 4),
                     "last_score": now.feats[j]["last_score"], "district": places[now.idx[j][0]]["district"]}
                    for j in order]
    return ({"type": "FeatureCollection", "features": features}, details, meta,
            {"ranking": ranking_rows, "validation": validation, "confirm": conf, "places": places, "rule": rule})


def _survivorship(places, conf, rows):
    """Positive rates by the pull's permit status at the confirmation origin, and band 1's rate if 5% or
    10% of its places had been closers missing from the pull, at the expired-permit group's rate."""
    out = defaultdict(lambda: [0, 0])
    for j, (i, _) in enumerate(conf["_te"].idx):
        if conf["_labelled"][j]:
            s = places[i].get("status") or "?"
            out[s][0] += 1
            out[s][1] += int(conf["_positive"][j])
    by_status = {s: {"labelled": n, "rate": round(k / n, 3)} for s, (n, k) in out.items()}
    r_exp = by_status.get("Expired", {}).get("rate")
    b1 = rows[0]["rate"] if rows else None
    bound = {f"{int(m * 100)}% missing": round((1 - m) * b1 + m * r_exp, 3) for m in (0.05, 0.10)} if (b1 and r_exp) else {}
    return {"by_permit_status": by_status, "band_1_rate_if": bound}


# ── report, gates, archive, registration, monitor, publication ─────────────────────────

def _fmt(x, nd=3):
    return "n/a" if x is None else f"{x:.{nd}f}"


def report(meta, extra):
    L = [f"# Site export report, {meta['run']} ({meta['mode']} mode)", "",
         f"{meta['source']['name']}. Inspections through {meta['inspections_through']}; this list expires "
         f"{meta['expires']}. {meta['places']:,} places.", "",
         f"Provenance: code {meta['provenance']['code_sha']}, pull sha256 {meta['provenance']['pull_sha256']}.", ""]
    m = meta["measurement"]
    if meta["mode"] == "bands":
        c, r, s = meta["card"], meta["catch_run"], meta["selection"]
        L += ["## The public rule", "", f"**{s['chosen']}**: {c['rule']}", "", "| item | weight | unit |", "|---|---|---|"]
        L += [f"| {i['label']} | {i['weight']} | {i['unit']} |" for i in c["items"]]
        L += ["", f"Eligible for a band: {c['eligibility']}.", "", "## Choosing it", "", f"Rule: {s['rule']}.", "",
              "| origin | " + " | ".join(extra["confirm"]["models"]) + " |", "|---|" + "---|" * len(extra["confirm"]["models"])]
        for res in extra["validation"] + [extra["confirm"]]:
            k = str(min(K_GATE, res["candidates"]))
            L.append(f"| {res['as_of']} AUC | " + " | ".join(_fmt(v["auc"]) for v in res["models"].values()) + " |")
            L.append(f"| {res['as_of']} AUC, eligible | " + " | ".join(_fmt(v["auc_eligible"]) for v in res["models"].values()) + " |")
            L.append(f"| {res['as_of']} caught@{k} of {res['positives']} | "
                     + " | ".join(str(v["catch"].get(k, {}).get("caught", "")) for v in res["models"].values()) + " |")
        L += ["", f"The count score fitted at the confirmation origin: {r['count_rule_at_origin']}.", "",
              f"## Confirmation origin, {r['as_of']} (frozen rule)", "",
              f"{r['candidates']:,} City restaurants, {r['eligible']:,} eligible for a band; {r['labelled']:,} had a routine "
              f"inspection in {r['label_window']} and {r['positives']:,} of those found a major. Trained on {r['trained_on']}.", "",
              f"Rule minus {r['vs_baseline']['baseline']} (AUC, eligible, 95% paired bootstrap over addresses): {r['vs_baseline']['auc']}."
              + (f" Rule minus the average-score rule: {r['vs_average_rule']}." if r.get("vs_average_rule") else ""), "",
              f"| band | points | places | labelled | major next | rate | 95% interval | {c['baseline_name']} same-size rate | "
              "hits minus baseline, 95% | kept in refits | places now |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for b in c["bands"]:
            L.append(f"| {b['band']} | {b['min_points']}{'-' + str(b['max_points']) if b['max_points'] is not None else '+'} | {b['places']} | {b['labelled']} | {b['positives']} | "
                     f"{_fmt(b['rate'])} | {b['interval']} | {_fmt(b['baseline_rate'])} | {b['vs_baseline']} | "
                     f"{b['kept_in_refits'] if b['kept_in_refits'] is not None else ''} | {b['places_now']} |")
        L.append(f"| below the bands | | {c['rest']['places']} | {c['rest']['labelled']} | {c['rest']['positives']} | "
                 f"{_fmt(c['rest']['rate'])} | {c['rest']['interval']} | | | | |")
        L += ["", "## Naming, by cost ratio", "", "A band is named when the low end of its interval clears C/(B+C).", "",
              "| C/B | bar | bands named |", "|---|---|---|"]
        L += [f"| {u['cost_ratio']} | {u['bar']} | {', '.join(u['named']) or 'none'} |" for u in meta["utility"]]
        f = meta["fairness"]
        L += ["", f"## Who would be named without a major (bands {', '.join(f['bands_used'])}, confirmation origin)", "",
              "| district | candidates | named | precision | FPR vs City | false share | 95% interval |", "|---|---|---|---|---|---|---|"]
        for g, e in f["by_district"].items():
            L.append(f"| {g} | {e['candidates']} | {e['named']} | {_fmt(e['precision'])} | {e['fpr_ratio']} | "
                     f"{e['false_share_ratio']} | {e['interval']} |")
        L += ["", "Fairness problems: " + ("; ".join(f["problems"]) or "none"), "",
              "## Survivorship", "", meta["survivorship"], f" By permit status and bound: {meta['survivorship_bound']}.", ""]
    L += ["## What the label is made of", "",
          f"- {m['graded_A_share']:.1%} of graded routine inspections are an A, including {m['majors_graded_A_share']:.1%} of those "
          "that found a major.",
          f"- Routine scores 86 to 92: {m['scores_86_to_92']} (scores heap at the A line).",
          f"- A major after a major: {m['major_after_major']:.1%}; after a clean routine: {m['major_after_clean']:.1%}.",
          f"- Different businesses at one address agree on majors: {_fmt(m['same_day_corr'])} on the same day "
          f"({m['same_day_pairs']:,} pairs) against {_fmt(m['different_day_corr'])} 60+ days apart ({m['different_day_pairs']:,} "
          "pairs). The records carry no inspector id, so a place cannot be separated from how strictly its inspector cites.",
          f"- Share of routine inspections with a major, by quarter: {m['major_rate_by_quarter']}.", "",
          "## Data rules applied", "", f"{meta['data_rules']}", ""]
    return "\n".join(L) + "\n"


def write_export(out: Path, fc, details, meta):
    out.mkdir(parents=True, exist_ok=True)
    pdir = out / "place"
    pdir.mkdir(exist_ok=True)
    for old in pdir.glob("*.json"):       # emptied, not removed: a synced folder (OneDrive) may hold the directory
        old.unlink()
    for fid, d in details.items():
        (pdir / f"{fid}.json").write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    (out / "facilities.geojson").write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def archive(out: Path, meta, ranking_rows):
    """Every run's full ranking, written once and never overwritten, with a manifest of hashes."""
    d = out / "archive" / meta["run"]
    if (d / "manifest.json").exists():
        return d, False
    d.mkdir(parents=True, exist_ok=True)
    with gzip.open(d / "ranking.csv.gz", "wt", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ranking_rows[0]))
        w.writeheader()
        w.writerows(ranking_rows)
    (d / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    manifest = {"run": meta["run"], "generated": meta["generated"], "ranking_sha256": sha256_file(d / "ranking.csv.gz"),
                "meta_sha256": sha256_file(d / "meta.json"), "code_sha": meta["provenance"]["code_sha"],
                "pull_sha256": meta["provenance"]["pull_sha256"]}
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return d, True


def register(out: Path, meta, prospective_dir=PROSPECTIVE):
    """Name this archived run as the one frozen prospective test. One registration only; the file
    carries no business names and is meant to be committed, so its commit date is public."""
    path = Path(prospective_dir) / "REGISTERED.json"
    if path.exists():
        raise SystemExit(f"{path} already names a run; the prospective test is registered once")
    man = json.loads((out / "archive" / meta["run"] / "manifest.json").read_text(encoding="utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**man, "registered": date.today().isoformat(), "rule": meta["model"],
                                "bands": [{k: b[k] for k in ("band", "min_points", "rate", "interval")} for b in meta["card"]["bands"]]},
                               indent=2), encoding="utf-8")
    return path


def _git_date(path: Path):
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", str(path)], cwd=ROOT, capture_output=True,
                             text=True, timeout=20).stdout.strip()
        return date.fromisoformat(out) if out else None
    except Exception:
        return None


PROSPECTIVE_DAYS = 90
PROSPECTIVE_MIN = 300


def monitor(out: Path, places, today=None, log=print):
    """Score every archived run on the routine inspections made after it: by band, the hit rate
    against the backtest's; and the published rule against the average-score rule on the same
    places. Writes monitor.md and monitor.json (the prospective gate reads the registered run)."""
    today = today or date.today()
    by_fid = {p["facility_id"]: p for p in places}
    rows, results = [], []
    for d in sorted((out / "archive").glob("forward_*")):
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        t = meta["run"].split("_", 1)[1]
        with gzip.open(d / "ranking.csv.gz", "rt", encoding="utf-8") as fh:
            ranked = [r for r in csv.DictReader(fh) if r.get("eligible") in ("1", None)]
        ys, pts, avg, addr, bands = [], [], [], [], []
        for r in ranked:
            p = by_fid.get(r["facility_id"])
            lab = label_at(p, t)[0] if p else None
            if lab is None:
                continue
            ys.append(lab)
            pts.append(float(r["points"]))
            avg.append(float(r["average_rule"]))
            addr.append(_norm(p["address"]))
            bands.append(r["band"] or "rest")
        ys = np.array(ys, float)
        res = {"run": meta["run"], "days": (today - _d(t)).days, "labelled": int(len(ys)), "positives": int(ys.sum()),
               "bands": {}}
        for b in sorted(set(bands)):
            m = np.array([x == b for x in bands])
            n, k = int(m.sum()), int(ys[m].sum())
            res["bands"][b] = {"labelled": n, "positives": k, "rate": round(k / n, 4) if n else None, "interval": wilson(k, n)}
            expect = next((x["rate"] for x in meta["card"]["bands"] if x["band"] == b), meta["card"]["rest"]["rate"] if b == "rest" else None)
            rows.append(f"| {meta['run']} | {b} | {n} | {k} | {_fmt(k / n if n else None)} | {_fmt(expect)} | {wilson(k, n)} |")
        if len(set(ys)) == 2:
            ids = {}
            cl = np.array([ids.setdefault(a, len(ids)) for a in addr])
            pts_a, avg_a = np.array(pts), np.array(avg)
            res.update(rule_auc=auc(ys, pts_a), average_rule_auc=auc(ys, avg_a),
                       rule_minus_average=paired_auc(ys, pts_a, avg_a, np.ones(len(ys), bool), cl))
        results.append(res)
    text = "\n".join(["# Monitor", "", "| run | band | inspected since | major | rate | backtest rate | 95% interval |",
                      "|---|---|---|---|---|---|---|"] + rows
                     + ["", "| run | days since | inspected | majors | rule AUC | average-rule AUC | difference, 95% |", "|---|---|---|---|---|---|---|"]
                     + [f"| {r['run']} | {r['days']} | {r['labelled']} | {r['positives']} | {_fmt(r.get('rule_auc'))} | "
                        f"{_fmt(r.get('average_rule_auc'))} | {r.get('rule_minus_average', '')} |" for r in results]) + "\n"
    (out / "monitor.md").write_text(text, encoding="utf-8")
    (out / "monitor.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    log(text)
    return results


def prospective_ok(out: Path, cost_ratio, prospective_dir=PROSPECTIVE, today=None):
    """The registered frozen run, committed at least PROSPECTIVE_DAYS ago, held up on at least
    PROSPECTIVE_MIN later inspections: band 1's rate cleared the cost bar at the low end of its
    interval, and a fitted rule beat the average-score rule. (ok, why)"""
    today = today or date.today()
    reg_path = Path(prospective_dir) / "REGISTERED.json"
    if not reg_path.exists():
        return False, "no registered run (export_site.py --register, then commit docs/prospective/REGISTERED.json)"
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    committed = _git_date(reg_path)
    if committed is None:
        return False, "docs/prospective/REGISTERED.json is not committed: its commit date is the registration's timestamp"
    if (today - committed).days < PROSPECTIVE_DAYS:
        return False, f"the registration was committed {(today - committed).days} days ago; it needs {PROSPECTIVE_DAYS}"
    arch = out / "archive" / reg["run"] / "ranking.csv.gz"
    if not arch.exists() or sha256_file(arch) != reg["ranking_sha256"]:
        return False, "the registered run's archive is missing or does not match its registered hash"
    mon = next((r for r in _json(out / "monitor.json", []) if r["run"] == reg["run"]), None)
    if not mon or mon["labelled"] < PROSPECTIVE_MIN:
        return False, f"the registered run has fewer than {PROSPECTIVE_MIN} later routine inspections (run --monitor)"
    if cost_ratio is None:
        return False, "no approved cost ratio to test the registered bands against"
    bar = cost_ratio / (1 + cost_ratio)
    b1 = mon["bands"].get("1")
    if not b1 or b1["interval"][0] is None or b1["interval"][0] <= bar:
        return False, f"band 1 of the registered run did not clear C/(B+C) = {bar:.3f} on later inspections ({b1})"
    if "average score" not in reg.get("rule", "") and not (mon.get("rule_minus_average") and mon["rule_minus_average"][0] > 0):
        return False, f"the registered rule did not beat the average-score rule on later inspections ({mon.get('rule_minus_average')})"
    return True, f"{reg['run']}: held up on {mon['labelled']} later inspections"


def gates(meta, out: Path, pull, today: date, approval, facilities_sha, named_ids):
    """Every reason this export may not be published ([] when it may)."""
    p = list(check_approval(approval, meta["mode"], meta, facilities_sha))
    if not (pull or {}).get("complete"):
        p.append("the pull is partial or unrecorded (data/pull_meta.json): finish fetch_sdfood.py --resume")
    age = (today - _d(meta["inspections_through"])).days
    if age > FRESH_DAYS:
        p.append(f"the record is {age} days old; a list is published within {FRESH_DAYS} days of its data")
    if meta["mode"] == "record":
        return p
    s, r, c = meta["selection"], meta["catch_run"], meta["card"]
    if not s.get("within_epsilon"):
        p.append(f"no publishable rule is within {EPSILON} AUC of the best model at every validation origin")
    va = r.get("vs_average_rule")
    if va is not None and not (va[0] is not None and va[0] > 0):
        p.append(f"the fitted rule does not beat the average-score rule (AUC difference {va}): publish the simpler rule or nothing")
    vb = r["vs_baseline"]["auc"]
    if not (vb[0] is not None and vb[0] > 0):
        p.append(f"the rule does not beat {r['vs_baseline']['baseline']} on AUC among eligible restaurants ({vb})")
    if not meta["named_bands"]:
        p.append("no band's interval clears the approved cost ratio: nothing to name")
    for b in c["bands"]:
        if b["band"] not in meta["named_bands"]:
            continue
        if not (b["vs_baseline"] and b["vs_baseline"][0] > 0):
            p.append(f"band {b['band']} does not catch more than {c['baseline_name']}'s same-size group ({b['vs_baseline']})")
        if b["kept_in_refits"] is not None and b["kept_in_refits"] < 0.8:
            p.append(f"band {b['band']} keeps only {b['kept_in_refits']} of its places across refits")
    p += meta["fairness"]["problems"]
    p += notice_problems(named_ids, meta["run"], today)
    ok, why = prospective_ok(out, meta.get("cost_ratio"), today=today)
    if not ok:
        p.append(f"prospective test: {why}")
    return p


def contract_check(dirpath: Path, review=False):
    node = shutil.which("node")
    if not node:
        return ["node is not installed, so the export contract check cannot run"]
    res = subprocess.run([node, str(CHECK), str(dirpath)] + (["--review"] if review else []), capture_output=True, text=True)
    return [] if res.returncode == 0 else ["the export contract check failed:\n" + (res.stdout + res.stderr).strip()]


def publish(out: Path, fc, details, meta, approval_path=APPROVAL, today=None):
    """Stage the shipped files (named bands only), stamp meta.publication, check them, then copy."""
    today = today or date.today()
    shipped = fc
    if meta["mode"] == "bands":
        shipped = {"type": "FeatureCollection",
                   "features": [f for f in fc["features"] if f["properties"].get("band") in meta["named_bands"]]}
    stage = out / "publish"
    if stage.exists():
        shutil.rmtree(stage)
    keep = {f["properties"]["facility_id"] for f in shipped["features"]}
    meta = {**meta, "places": len(shipped["features"])}
    write_export(stage, shipped, {k: v for k, v in details.items() if k in keep}, meta)
    meta["publication"] = {"run": meta["run"], "approval_sha256": sha256_file(approval_path),
                           "facilities_sha256": sha256_file(stage / "facilities.geojson"),
                           "gates_passed_at": today.isoformat()}
    (stage / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    problems = contract_check(stage)
    if problems:
        return problems
    if SITE_DATA.exists():
        shutil.rmtree(SITE_DATA)
    shutil.copytree(stage, SITE_DATA)
    return []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("bands", "record"), default="bands")
    ap.add_argument("--publish", action="store_true", help="copy into food-dashboard/public/data/ if every gate passes")
    ap.add_argument("--register", action="store_true", help="register this bands run as the frozen prospective test")
    ap.add_argument("--monitor", action="store_true", help="score archived runs against the inspections made since")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--refits", type=int, default=REFITS)
    args = ap.parse_args(argv)
    if not RAW.exists():
        sys.exit(f"{RAW} is missing: run fetch_sdfood.py first")
    raw = json.loads(RAW.read_text())
    if args.monitor:
        monitor(args.out, load_places(raw))
        return 0
    pull = _json(PULL, None)
    approval = _json(APPROVAL, None)
    if args.mode == "record":
        fc, details, meta, extra = build_record(raw, load_districts(), pull=pull, approval=approval)
    else:
        fc, details, meta, extra = build(raw, load_districts(), pull=pull, approval=approval, refits=args.refits)
    write_export(args.out, fc, details, meta)
    (args.out / "report.md").write_text(report(meta, extra), encoding="utf-8")
    facilities_sha = sha256_file(args.out / "facilities.geojson")
    if meta["mode"] == "bands":
        d, new = archive(args.out, meta, extra["ranking"])
        print(f"archive {'written' if new else 'already exists, left unchanged'}: {d}")
        if args.register:
            print(f"registered {meta['run']} in {register(args.out, meta)}: commit it now; its commit date starts the clock")
            return 0
    size = (args.out / "facilities.geojson").stat().st_size / 1e6
    print(f"wrote {args.out} ({len(fc['features'])} places, index {size:.1f} MB) and report.md; facilities sha256 {facilities_sha}")
    named_ids = [f["properties"]["facility_id"] for f in fc["features"] if f["properties"].get("band") in meta.get("named_bands", [])]
    problems = gates(meta, args.out, pull, date.today(), approval, facilities_sha, named_ids)
    problems += contract_check(args.out, review=True)
    if not args.publish:
        print("not published" + (":\n  - " + "\n  - ".join(problems) if problems else "; every gate passes, rerun with --publish"))
        return 0
    if problems:
        print("NOT PUBLISHED:\n  - " + "\n  - ".join(problems))
        return 1
    problems = publish(args.out, fc, details, meta)
    if problems:
        print("NOT PUBLISHED:\n  - " + "\n  - ".join(problems))
        return 1
    print(f"published to {SITE_DATA}. Before pushing: read {args.out / 'report.md'}, and see docs/PUBLISHING.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
