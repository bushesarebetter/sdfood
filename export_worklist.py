"""Monthly worklists, one per City of San Diego council district: the facilities estimated due
for a routine inspection that month, in the students' point rule's order. The source for the internal
API's worklists, and the frozen list a silent pilot is scored against (docs/PILOT.md).

    python export_worklist.py                    # the month after the data ends
    python export_worklist.py --month 2026-10
    python export_worklist.py --verify data/worklists/2026-10/frozen/<stamp>   # check a frozen copy

Writes data/worklists/<yyyy-mm>/ (gitignored under /data/):
  district-<n>.csv   n = 1..9, a header row, then facility_id, name, address, business_type,
                     last_routine_date, last_routine_score, rule_mean, due_estimate, rule_order,
                     rule_points, why, last_routine_outcome, closures_24m, escalation, last_closure,
                     reopened_on, posted_grade (COLUMNS)
  manifest.json      {month, generated, method, rule, files: {district: sha256}}
  frozen/<stamp>/    a read-only copy of the above plus scoring.csv (every active City facility
                     with each ordering's inputs and positions), with its own manifest.json, so a
                     pilot can be scored later against exactly what was sent.

The record is read strictly before the month's first day.

Which facilities are due (an estimate: the public record has no schedule)
  * Active: visited in the 550 days before the month starts, permit not expired in the pull,
    at least one routine inspection on record, inside a City council district.
  * Interval: for each business type, the Kaplan-Meier median number of days between consecutive
    routine inspections of the same facility on the record before the month, counting each active
    facility's still-open interval (a plain median of finished gaps runs short); all types pooled
    when a type has fewer than 30 finished gaps.
  * due_estimate = the last routine inspection's date + its type's median interval.
  * On the month's list when, on the month's last day, the time since the last routine is at
    least that interval minus 30 days (due within 30 days after the month, or overdue).
  The run prints a backtest of this estimate on 2025-01 .. the last whole month: the share of
  each month's routine inspections (at facilities already on the record) that were on its list,
  and the share of the list inspected that month.

The order within a district
  * First, places that meet the County's own criteria for a closer look ("recurring major
    violations, recurring scores of less than 90%, or recurring facility closures", Retail Food
    Facility Operator's Guide p. 8: the export's escalation facts closures2, repeat_item, lt90_2).
  * Then everything else on ONE scale, 100 minus the mean routine score: a place the students'
    point rule scores (export_site.py's export in data/site) by its points (the two years before
    the list); a place it does not score (markets, limited-preparation places, restaurants without
    two rated routine inspections) by the one-line rule, 100 minus its mean routine score on record
    since 2023-01, to 0.1. So a place that was closed twice is never listed below one averaging 98.
    In both, a routine that ended in a health closure order is counted as 70 by this rule (the
    County gives no score then); a facility with no scored or closed routine counts as 97.
    Ties go to the lower mean, then the earlier due_estimate, then facility_id.
  * A place on hold (docs/holds.json) keeps its County record and loses its points and band.
  * Without data/site (or when it holds the invented sample), every place is ordered by the
    one-line rule, rule_points = 100 minus its mean routine score (to 0.1), and the manifest's
    `method` says so.
  * rule_order = 1..N within the district; why = which ordering placed it, and the facts behind it
    (card points and band, the routine scores on record, how many found a major violation).
  * rule_mean is the mean that ordering read (the points' two-year mean, or the one-line rule's
    mean since 2023-01), closures counted as 70. closures_24m, last_closure and reopened_on are the
    export's closure episodes (one per closure, ended by the County's "Approved to Reopen"), in the
    24 months before the export's list date; posted_grade is the grade on the County's card.

The research model's order (model_food.HEADLINE, fitted on every routine inspection before the
month) and the one-line rule's inputs go only into the frozen scoring.csv, for the pilot's arms."""
import argparse, csv, hashlib, json, os, shutil, stat, sys
from datetime import datetime, timezone
import numpy as np, pandas as pd
import model_food as mf

OUT = "data/worklists"
SITE = "data/site"
ACTIVE_DAYS = 550
DUE_MARGIN = 30           # days before the estimated due date a facility joins the list
MIN_GAPS = 30             # a type needs this many routine-to-routine gaps for its own median
DISTRICTS = range(1, 10)
COLUMNS = ["facility_id", "name", "address", "business_type", "last_routine_date", "last_routine_score",
           "rule_mean", "due_estimate", "rule_order", "rule_points", "why",
           "last_routine_outcome", "closures_24m", "escalation", "last_closure", "reopened_on", "posted_grade"]
# The County's own criteria for a closer look (Retail Food Facility Operator's Guide p. 8), as the
# export counts them: by closure episode and by distinct routine inspection day, in two years.
ESCALATION = {"closures2": "two or more health closures in two years",
              "repeat_item": "the same major violation at two or more routine inspections in two years",
              "lt90_2": "two or more routine scores below 90 in two years"}
POINT_RULE = "Point rule (the students', not a County rating)"
SCORING = ["district", "facility_id", "business_id", "due_this_month", "due_estimate", "rule_points",
           "rule_order", "rule_order_all", "card_points", "mean_points", "model_risk", "model_order",
           "model_order_all"]
METHOD = ("Due estimate: active facilities (visited in the 550 days before the month, permit not expired in the "
          "pull, at least one routine inspection on record, inside a City council district) are listed when, on "
          "the month's last day, the days since their last routine inspection reach their business type's median "
          "interval between routine inspections minus 30. due_estimate = last routine date + that median. Medians "
          "are Kaplan-Meier medians from the public record before the month, counting each active facility's "
          "still-open interval (all types pooled below 30 finished gaps). Computed from the "
          "County's published results (SD Food Info) strictly before the month's first day.")
MEAN_RULE = ("lowest mean routine inspection score on record (since 2023-01) first; a routine that ended in a "
             "health closure order counts as 70; a facility with no scored or closed routine counts as 97")
FALLBACK = (" No point rule export (data/site) was found, so every district is in the one-line rule's order: "
            "rule_points = 100 minus the mean routine score on record.")


def month_bounds(month):
    start = pd.Timestamp(f"{month}-01")
    return start, start + pd.offsets.MonthEnd(0)


def facility_info(raw):
    """business_id -> facility_id (the County's record id), name, address, permit status, as
    export_site.load_places reads them."""
    rows = []
    for b in raw:
        ids = [i.get("custom_id") for i in b.get("inspections") or [] if i.get("custom_id")]
        rows.append({"business_id": int(b["business_id"]),
                     "facility_id": ids[-1] if ids else str(b.get("business_id")),
                     "name": (b.get("name") or "").strip(), "address": (b.get("address") or "").strip(),
                     "status": b.get("status") or ""})
    return pd.DataFrame(rows).drop_duplicates("business_id").set_index("business_id")


HOLDS = os.path.join("docs", "holds.json")


def load_holds(path=HOLDS):
    try:
        return set(json.load(open(path, encoding="utf-8")).get("facility_ids", []))
    except (OSError, ValueError):
        return set()


def closure_facts(detail, list_date):
    """From a place file: health closure episodes in the 24 months before the list date, and the
    latest one with its reopening (the export's reading: one per closure, ended by the County's
    "Approved to Reopen")."""
    lo = (pd.Timestamp(list_date) - pd.Timedelta(days=730)).strftime("%Y-%m-%d")
    eps = [r for r in detail.get("inspections") or [] if r.get("closed") and r.get("closure") == "health"]
    recent = [r for r in eps if lo <= r["date"] < list_date]
    last = eps[-1] if eps else None
    return {"closures_24m": len(recent), "last_closure": last["date"] if last else "",
            "reopened_on": (last.get("reopened_on") or "") if last else ""}


def load_card(site=SITE, holds=None):
    """The students' point rule's export (export_site.py, data/site): facility_id -> points, band,
    flags, the scores the points average, closure facts and posted grade, and the rule. None when
    there is no real export (missing, or the invented sample). A place on hold keeps its record and
    loses its points and band."""
    fc_path, meta_path = os.path.join(site, "facilities.geojson"), os.path.join(site, "meta.json")
    if not (os.path.exists(fc_path) and os.path.exists(meta_path)):
        return None
    meta = json.load(open(meta_path, encoding="utf-8"))
    if meta.get("sample"):
        return None
    held = load_holds() if holds is None else set(holds)
    props = [ft["properties"] for ft in json.load(open(fc_path, encoding="utf-8"))["features"]]
    card = meta.get("card") or {}
    through = meta.get("inspections_through")
    list_date = (pd.Timestamp(through) + pd.Timedelta(days=1)).strftime("%Y-%m-%d") if through else None
    scores, facts = {}, {}             # from each place's file: the scores its points average, its closures
    for p in props:
        pf = os.path.join(site, "place", f"{p['facility_id']}.json")
        if not os.path.exists(pf):
            continue
        d = json.load(open(pf, encoding="utf-8"))
        used = d.get("scores_used")
        if used is not None and p.get("points") is not None and p["facility_id"] not in held:
            scores[p["facility_id"]] = [(u["score"], bool(u["closure"]), u.get("county_score")) for u in used]
        if list_date:
            facts[p["facility_id"]] = closure_facts(d, list_date)
    grade = lambda g: f"{g['grade']} ({g['date']})" if isinstance(g, dict) and g.get("grade") else ""
    return {"points": {p["facility_id"]: p["points"] for p in props if p.get("points") is not None and p["facility_id"] not in held},
            "band": {p["facility_id"]: p["band"] for p in props if p.get("band") and p["facility_id"] not in held},
            "held": held & {p["facility_id"] for p in props},
            "flags": {p["facility_id"]: p.get("flags") or [] for p in props}, "scores": scores, "facts": facts,
            "grade": {p["facility_id"]: grade(p.get("grade")) for p in props},
            "rule": card.get("rule", ""), "eligibility": card.get("eligibility", ""),
            "run": meta.get("run") or meta.get("generated"), "through": through, "list_date": list_date}


def rule_text(card):
    """The manifest's `rule`."""
    if card is None:
        return (f"One-line rule: {MEAN_RULE}. rule_points = 100 minus that mean, rounded to 0.1, highest first; "
                "ties by earlier due_estimate, then facility_id. rule_order is 1..N per district.")
    return (f"First, places meeting the County's own criteria for a closer look ({'; '.join(ESCALATION.values())}). "
            f"Then everything on one scale, 100 minus the mean routine score: places the students' point rule scores "
            f"(not a County rating; export_site.py export {card['run']}, inspections through {card['through']}: "
            f"{card['rule']}) by their points; places it does not score (it scores {card['eligibility']}) by the "
            f"one-line rule, {MEAN_RULE}, rule_points to 0.1. Ties by the lower mean, then earlier due_estimate, then "
            "facility_id. rule_order is 1..N per district; why says which ordering placed each row.")


def km_median(durations, events):
    """Kaplan-Meier median in days: the first time the survival estimate falls to 0.5 or below.
    None when it never does (too few intervals have ended)."""
    d = np.asarray(durations, dtype=float)
    e = np.asarray(events, dtype=bool)
    s = 1.0
    for t in np.unique(d[e]):
        s *= 1.0 - ((d == t) & e).sum() / (d >= t).sum()
        if s <= 0.5 + 1e-9:                  # exactly one half, up to float rounding
            return float(t)
    return None


def intervals(rt, asof=None, last_visit=None):
    """Median days between consecutive routine inspections of the same facility, by type.

    Only finished gaps are observed, and within a record that starts in 2023 the long ones are the
    ones still open at the cutoff, so a plain median of finished gaps runs short (worse the earlier
    the cutoff). With ``asof``, each active facility's open interval (last routine to asof) enters
    as censored and the median is Kaplan-Meier. A facility not seen for ACTIVE_DAYS is taken to
    have closed and adds no open interval."""
    gap = rt.groupby("business_id")["completed_date"].diff().dt.days
    g = rt.assign(gap=gap).dropna(subset=["gap"])
    if asof is None:
        by = g.groupby("business_type")["gap"].agg(["median", "size"])
        overall = float(g["gap"].median()) if len(g) else 365.0
        return by.loc[by["size"] >= MIN_GAPS, "median"].to_dict(), overall
    last = rt.groupby("business_id").agg(business_type=("business_type", "last"), last=("completed_date", "max"))
    if last_visit is not None:
        last = last[(pd.Timestamp(asof) - last_visit.reindex(last.index)).dt.days <= ACTIVE_DAYS]
    open_ = pd.DataFrame({"business_type": last["business_type"], "gap": (pd.Timestamp(asof) - last["last"]).dt.days,
                          "event": False})
    allg = pd.concat([g[["business_type", "gap"]].assign(event=True), open_], ignore_index=True)
    overall = km_median(allg["gap"], allg["event"])
    if overall is None:
        overall = float(g["gap"].median()) if len(g) else 365.0
    out = {}
    for t, gt in allg.groupby("business_type"):
        if gt["event"].sum() >= MIN_GAPS:
            m = km_median(gt["gap"], gt["event"])
            if m is not None:
                out[t] = m
    return out, overall


def _closed_text(county):
    """How a closure reads in a worksheet line: the rule's 70, never the County's score."""
    c = mf.es.CLOSURE_SCORE
    return (f" (closed; the County gave no score, this rule counts it as {c})" if county is None
            else f" (closed; the County's score that day {county:g}, this rule counts a closure as {c})")


def _why(scores, majors, n, *, closures=0, points=None, band=None, card=False, used=None, escalation="", held=False):
    """Which ordering placed the row, and the facts behind it. For a scored place, the same scores
    its worksheet averages (the two years before the list; a closure order counted as 70 by this
    rule, not scored 70 by the County), so the points can be checked by hand from this line alone."""
    first = f"First: {escalation} (the County's own criteria for a closer look). " if escalation else ""
    if points is not None and used:
        listed = ", ".join(f"{u[0]:g}{_closed_text(u[2] if len(u) > 2 else None) if u[1] else ''}" for u in used)
        mean = sum(u[0] for u in used) / len(used)
        return (first + f"{POINT_RULE}: {int(points)} points{f', band {band}' if band else ''}. It averages the routine "
                f"scores of the two years before the list: {listed}; mean {mean:.1f}, and 100 minus the mean, "
                f"rounded, is its points."
                + (f" {majors} of {n} routine inspections since 2023-01 found a major violation." if majors else ""))
    lead = (f"{POINT_RULE}: {int(points)} points{f', band {band}' if band else ''}. " if points is not None
            else "On hold: its points and band are withheld while a request is reviewed; placed by the one-line rule. "
            if held else "Not scored by the point rule; placed on the same scale by 100 minus its mean routine score. "
            if card else "")
    lead = first + lead
    rated = scores + [float(mf.es.CLOSURE_SCORE)] * closures
    shut = (f" {closures} routine inspection{'s' if closures > 1 else ''} ended in a health closure order "
            f"(the County gave no score; this rule counts {'each' if closures > 1 else 'it'} as {mf.es.CLOSURE_SCORE})."
            if closures else "")
    if scores:
        rec = f"Routine scores since 2023-01: {', '.join(f'{v:g}' for v in scores)} (mean {np.mean(rated):.1f}).{shut}"
    elif closures:
        rec = f"No scored routine inspection on record since 2023-01.{shut} Mean {np.mean(rated):.1f}."
    else:
        rec = "No scored routine inspection on record since 2023-01; counted as a typical A (97)."
    return lead + rec + (f" {majors} of {n} routine inspections found a major violation." if majors else "")


def worklist(insp, info, month, lookup, *, card=None, use_status=True, why=True, city_only=True, listed_only=True):
    """Every active City facility as of the month's first day, with its due estimate, rule points
    and order. insp: model_food.load() rows; info: facility_info(); lookup(lon, lat) -> district;
    card: load_card() or None for the one-line rule alone. city_only=False keeps facilities outside
    the City too, as district 0 (the dashboard). listed_only keeps only the kinds of place the site
    lists (restaurants, limited-preparation places, markets with food prep): never a private home
    (home kitchens, cottage food), a health-care kitchen, a school or a food truck at its commissary,
    which follow other rules and have no place on a list sent to City staff."""
    start, end = month_bounds(month)
    h = insp[insp["completed_date"] < start]
    last_visit = h.groupby("business_id")["completed_date"].max()
    rt = h[h["insp_type"].astype(str) == "Routine"].sort_values(["business_id", "completed_date"])
    if rt.empty:
        return pd.DataFrame()
    by_type, overall = intervals(rt, asof=start, last_visit=last_visit)
    g = rt.groupby("business_id")
    last = g.tail(1).set_index("business_id")
    f = pd.DataFrame({"business_type": last["business_type"].astype(str),
                      "last_routine_date": last["completed_date"], "last_routine_score": last["score"],
                      "lat": last["lat"], "lng": last["lng"]})
    if listed_only:
        f = f[f["business_type"].map(mf.es.KINDS).isin(mf.es.PUBLIC_KINDS)]
    closure = last["closure"] if "closure" in last.columns else pd.Series(index=last.index, dtype=object)
    status = last["status"] if "status" in last.columns else pd.Series("", index=last.index)
    f["last_routine_outcome"] = [f"{st}{' (health closure)' if cl == 'health' else ''}"
                                 for st, cl in zip(status.reindex(f.index).fillna(""), closure.reindex(f.index))]
    if "closure" in h.columns:
        h24 = h[(h["completed_date"] >= start - pd.Timedelta(days=730)) & (h["closure"].astype(str) == "health")]
        f["closures_24m"] = h24.groupby("business_id").size().reindex(f.index).fillna(0).astype(int)
    else:
        f["closures_24m"] = 0
    f["mean_all"] = g["score"].mean()
    # the rule's mean counts a routine that ended in a health closure as CLOSURE_SCORE, as the card does
    f["mean_rated"] = (g["rated_score"] if "rated_score" in rt.columns else g["score"]).mean()
    f["last_visit"] = last_visit
    f = f[(start - f["last_visit"]).dt.days <= ACTIVE_DAYS]
    if use_status:
        st = info["status"].reindex(f.index).fillna("").str.lower()
        f = f[st != "expired"]
    f["district"] = [lookup(lo if pd.notna(lo) else None, la if pd.notna(la) else None)
                     for lo, la in zip(f["lng"], f["lat"])]
    f = f[f["district"].notna()].copy() if city_only else f.assign(district=f["district"].fillna(0))
    f["district"] = f["district"].astype(int)
    f["interval"] = f["business_type"].map(by_type).fillna(overall)
    f["due_estimate"] = f["last_routine_date"] + pd.to_timedelta(f["interval"].round(), unit="D")
    f["due_this_month"] = (end - f["last_routine_date"]).dt.days >= f["interval"] - DUE_MARGIN
    f["mean_points"] = (100 - f["mean_rated"].fillna(mf.FILL_SCORE)).round(1)
    f = f.join(info[["facility_id", "name", "address"]], how="left")
    f["facility_id"] = f["facility_id"].fillna(pd.Series(f.index.astype(str), index=f.index))
    f["card_points"] = f["facility_id"].map(card["points"]) if card else np.nan
    f["card_band"] = f["facility_id"].map(card["band"]) if card else None
    # one scale for every row: the card's points where it scores the place, else the one-line rule's
    f["rule_points"] = f["card_points"].fillna(f["mean_points"]) if card else f["mean_points"]
    used_mean = {fid: sum(u[0] for u in used) / len(used) for fid, used in (card["scores"].items() if card else []) if used}
    f["rule_mean"] = [used_mean.get(fid, m) for fid, m in zip(f["facility_id"], f["mean_rated"].fillna(mf.FILL_SCORE))]
    f["escalation"] = (["; ".join(v for k, v in ESCALATION.items() if k in card["flags"].get(fid, []))
                        for fid in f["facility_id"]] if card else "")
    f["last_closure"], f["reopened_on"], f["posted_grade"] = "", "", ""
    if card:
        facts = [card["facts"].get(fid) for fid in f["facility_id"]]
        f["closures_24m"] = [x["closures_24m"] if x else c for x, c in zip(facts, f["closures_24m"])]
        f["last_closure"] = [x["last_closure"] if x else "" for x in facts]
        f["reopened_on"] = [x["reopened_on"] if x else "" for x in facts]
        f["posted_grade"] = [card["grade"].get(fid, "") for fid in f["facility_id"]]
        f["last_routine_outcome"] = [o + (f"; reopened {r}" if lc and r and lc == d.strftime("%Y-%m-%d") else "")
                                     for o, lc, r, d in zip(f["last_routine_outcome"], f["last_closure"], f["reopened_on"],
                                                            f["last_routine_date"])]
    if why:
        rows = rt[rt["business_id"].isin(f.index)]
        sc = rows.groupby("business_id")["score"].apply(lambda s: [float(v) for v in s.dropna()])
        cl = (rows.assign(_c=rows["rated_score"].notna() & rows["score"].isna())
                  .groupby("business_id")["_c"].sum() if "rated_score" in rows.columns else pd.Series(dtype=int))
        mj = rows.groupby("business_id")["n_major"].apply(lambda s: int((s > 0).sum()))
        nr = rows.groupby("business_id").size()
        f["why"] = [_why(sc.get(b, []), mj.get(b, 0), nr.get(b, 0), closures=int(cl.get(b, 0)),
                         points=None if pd.isna(p) else p, band=None if pd.isna(bd) else bd, card=bool(card),
                         used=card["scores"].get(fid) if card else None, escalation=esc,
                         held=bool(card) and fid in card["held"])
                    for b, p, bd, fid, esc in zip(f.index, f["card_points"], f["card_band"], f["facility_id"], f["escalation"])]
    return rank(f)


def rank(f):
    """rule_order (among the month's list) and rule_order_all (among every active facility) within
    each district: places meeting the County's escalation criteria first, then everything on one
    scale (rule_points: the card's points, or the one-line rule's 100 minus the mean), highest
    first; ties to the lower mean score, the earlier due_estimate, then facility_id."""
    esc = f["escalation"].astype(str).str.len() > 0 if "escalation" in f.columns else pd.Series(False, index=f.index)
    f = (f.assign(_esc=esc)
          .sort_values(["district", "_esc", "rule_points", "mean_points", "due_estimate", "facility_id"],
                       ascending=[True, False, False, False, True, True], na_position="last")
          .drop(columns="_esc"))
    f["rule_order_all"] = f.groupby("district").cumcount() + 1
    due = f[f["due_this_month"]]
    f["rule_order"] = (due.groupby("district").cumcount() + 1).reindex(f.index)
    return f


def model_orders(insp, month, f):
    """The research model's risk for each active facility's next routine inspection, fitted on
    every routine inspection before the month, and its order within each district. It trains on
    features as of the 1st of each inspection's month (month_start_rows), the way it scores the
    list (features_asof), so training and scoring read the record the same way."""
    start, _ = month_bounds(month)
    h = insp[insp["completed_date"] < start]
    hf = mf.add_features(h)
    model = mf.fit_as_deployed(mf.month_start_rows(hf, mf.routine_rows(hf)))
    fx = mf.features_asof(h, start, ids=f.index)
    f = f.copy()
    f["model_risk"] = pd.Series(model.predict(fx), index=fx.index).reindex(f.index).round(4)
    f["model_order_all"] = f.groupby("district")["model_risk"].rank(ascending=False, method="first").astype(int)
    due = f[f["due_this_month"]]
    f["model_order"] = due.groupby("district")["model_risk"].rank(ascending=False, method="first").reindex(f.index)
    return f


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _fmt(v, nd=1):
    """A CSV cell: blank when missing, a date as YYYY-MM-DD, a number without trailing zeros."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ""
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, (float, np.floating, int, np.integer)):
        return f"{float(v):.{nd}f}".rstrip("0").rstrip(".") if nd else str(int(round(float(v))))
    return str(v)


def _points(r):
    """rule_points as written: the card's whole points, or the one-line rule's to 0.1."""
    if pd.isna(r["rule_points"]):
        return ""
    return str(int(r["rule_points"])) if pd.notna(r["card_points"]) else f"{r['rule_points']:.1f}"


def csv_text(v):
    """Scraped text as a CSV cell: a leading =, +, -, @, tab or carriage return would make a
    spreadsheet run the cell as a formula, so such text gets a leading apostrophe."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        try:
            float(v)
        except ValueError:
            return "'" + v
    return v


def write_month(f, month, out=OUT, generated=None, freeze=True, card=None):
    """district-<n>.csv for n in 1..9 and manifest.json; with freeze, a read-only timestamped
    copy with scoring.csv. Returns the month's folder and the frozen folder (or None)."""
    generated = generated or datetime.now(timezone.utc).replace(microsecond=0)
    folder = os.path.join(out, month)
    os.makedirs(folder, exist_ok=True)
    files = {}
    for n in DISTRICTS:
        path = os.path.join(folder, f"district-{n}.csv")
        rows = f[(f["district"] == n) & f["due_this_month"]].sort_values("rule_order")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            wr = csv.writer(fh)
            wr.writerow(COLUMNS)
            for _, r in rows.iterrows():
                wr.writerow([csv_text(r["facility_id"]), csv_text(r["name"]), csv_text(r["address"]),
                             csv_text(r["business_type"]),
                             _fmt(r["last_routine_date"]), _fmt(r["last_routine_score"]),
                             _fmt(r.get("rule_mean")), _fmt(r["due_estimate"]),
                             int(r["rule_order"]), _points(r), csv_text(r["why"]),
                             csv_text(r.get("last_routine_outcome", "")), _fmt(r.get("closures_24m"), 0),
                             csv_text(r.get("escalation", "")), csv_text(r.get("last_closure", "")),
                             csv_text(r.get("reopened_on", "")), csv_text(r.get("posted_grade", ""))])
        files[str(n)] = sha256(path)
    manifest = {"month": month, "generated": generated.isoformat(),
                "method": METHOD + (FALLBACK if card is None else ""), "rule": rule_text(card),
                "export_run": card["run"] if card else None,
                "listed_kinds": "restaurants, limited-preparation places and markets with food prep; never a private home",
                "files": files}
    json.dump(manifest, open(os.path.join(folder, "manifest.json"), "w"), indent=1)
    if not freeze:
        return folder, None
    frozen = os.path.join(folder, "frozen", generated.strftime("%Y%m%dT%H%M%SZ"))
    os.makedirs(frozen, exist_ok=False)
    for n in DISTRICTS:
        shutil.copyfile(os.path.join(folder, f"district-{n}.csv"), os.path.join(frozen, f"district-{n}.csv"))
    sc = f.rename_axis("business_id").reset_index().sort_values(["district", "rule_order_all"])
    with open(os.path.join(frozen, "scoring.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(SCORING)
        for _, r in sc.iterrows():
            wr.writerow([int(r["district"]), r["facility_id"], r["business_id"], int(bool(r["due_this_month"])),
                         _fmt(r["due_estimate"]), _points(r), _fmt(r["rule_order"], 0),
                         int(r["rule_order_all"]), _fmt(r["card_points"], 0), f"{r['mean_points']:.1f}",
                         _fmt(r.get("model_risk"), 4), _fmt(r.get("model_order"), 0), _fmt(r.get("model_order_all"), 0)])
    fz = dict(manifest, files={**files, "scoring": sha256(os.path.join(frozen, "scoring.csv"))})
    json.dump(fz, open(os.path.join(frozen, "manifest.json"), "w"), indent=1)
    for name in os.listdir(frozen):
        os.chmod(os.path.join(frozen, name), stat.S_IREAD)
    return folder, frozen


def verify(frozen):
    """Names of the files in a frozen copy whose sha256 no longer matches its manifest. A file that is
    missing or cannot be read no longer matches: it is reported, never a crash."""
    with open(os.path.join(frozen, "manifest.json"), encoding="utf-8") as fh:
        m = json.load(fh)
    name = lambda k: "scoring.csv" if k == "scoring" else f"district-{k}.csv"

    def matches(path, h):
        try:
            return sha256(path) == h
        except OSError:
            return False

    return [name(k) for k, h in m["files"].items() if not matches(os.path.join(frozen, name(k)), h)]


def backtest(insp, info, lookup, months):
    """For each past month: the share of the City's routine inspections that month (at facilities
    already on the record) whose facility was on the month's list, and the share of the list
    inspected that month."""
    rows = []
    for m in months:
        start, end = month_bounds(m)
        f = worklist(insp, info, m, lookup, use_status=False, why=False)
        done = insp[(insp["insp_type"].astype(str) == "Routine") & (insp["completed_date"] >= start)
                    & (insp["completed_date"] <= end)]["business_id"].unique()
        active = f.index[f.index.isin(done)]
        listed = f.index[f["due_this_month"]]
        rows.append({"month": m, "listed": len(listed), "inspected": len(active),
                     "coverage": len(set(active) & set(listed)) / max(len(active), 1),
                     "precision": len(set(active) & set(listed)) / max(len(listed), 1)})
    return pd.DataFrame(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--month", help="yyyy-mm (default: the month after the data ends)")
    ap.add_argument("--verify", metavar="FROZEN_DIR", help="check a frozen copy against its manifest")
    ap.add_argument("--no-backtest", action="store_true")
    a = ap.parse_args(argv)
    if a.verify:
        bad = verify(a.verify)
        print("frozen copy intact" if not bad else f"CHANGED since frozen: {bad}")
        return 1 if bad else 0

    import export_site as es
    insp = mf.load()
    info = facility_info(json.load(open(mf.RAW)))
    lookup = es.district_lookup(es.load_districts())
    data_to = insp["completed_date"].max()
    month = a.month or (data_to + pd.offsets.MonthBegin(1)).strftime("%Y-%m")
    card = load_card()
    print(f"data through {data_to.date()}; worklists for {month}; "
          + (f"card export {card['run']} ({len(card['points']):,} places with points)" if card
             else "no card export: one-line rule only"))

    if not a.no_backtest:
        last_whole = (data_to + pd.Timedelta(days=1)).to_period("M") - 1
        months = pd.period_range("2025-01", last_whole, freq="M").strftime("%Y-%m").tolist()
        bt = backtest(insp, info, lookup, months)
        print("\n=== backtest of the due estimate (City districts) ===")
        print(bt.assign(coverage=(bt["coverage"]*100).round(1), precision=(bt["precision"]*100).round(1)).to_string(index=False))
        print(f"mean over {len(bt)} months: {bt['coverage'].mean()*100:.0f}% of each month's routine inspections were "
              f"on its list; {bt['precision'].mean()*100:.0f}% of a list was inspected that month; median list "
              f"{bt['listed'].median():,.0f} vs {bt['inspected'].median():,.0f} inspected")
        mf.save_results("worklist_backtest", {"months": len(bt), "coverage": round(float(bt["coverage"].mean()), 3),
                                              "precision": round(float(bt["precision"].mean()), 3),
                                              "coverage_range": [round(float(bt["coverage"].min()), 3),
                                                                 round(float(bt["coverage"].max()), 3)],
                                              "listed_median": float(bt["listed"].median()),
                                              "inspected_median": float(bt["inspected"].median())})

    f = worklist(insp, info, month, lookup, card=card)
    f = model_orders(insp, month, f)
    folder, frozen = write_month(f, month, card=card)
    due = f[f["due_this_month"]]
    print(f"\n{len(f):,} active City facilities; {len(due):,} estimated due in {month} "
          f"({int(due['card_points'].notna().sum()):,} with card points):")
    print(due.groupby("district").size().to_string())
    print(f"wrote {folder}/district-1..9.csv and manifest.json; frozen copy {frozen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
