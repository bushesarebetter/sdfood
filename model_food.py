"""Predict, at a routine food inspection, whether it will find a MAJOR violation (the County's
term), using only what was on the record beforehand. Honest forward-in-time test, compared
against what an inspector already has without a model:
  * the one-line rule: the facility's mean routine score on record (since 2023-01 in the public
    data), lowest first;
  * persistence: routine inspections with a major in the prior 12 months, then majors in the
    prior 12 months, then the lowest last routine score (export_site.persistence, computed per
    inspection from strictly-earlier dates);
  * its mean routine score over the prior 12 months, its last routine score, and its prior
    major-violation rate.
Model minus each baseline gets a paired bootstrap interval (resampling facilities).

Model variants, all tested on the same 2025+ inspections:
  * permit age: the pull's `opened_date` is the permit in force when the data was collected. A
    permit reissued after an inspection (a change of owner, say) gives that inspection a negative
    age, and those inspections found majors about twice as often: the feature told the model the
    future. The age as published is kept only to measure the leak. "Age set to missing" blanks
    the impossible ages, but the blank itself still marks a later reissue, so every variant the
    results use drops permit age.
  * history window: the "since 2023-01" features grow with the record (left-truncated: a 2023
    inspection sees months of history, a 2026 one years). The 12-month-window variant reads the
    365 days before each inspection, as the public site's exporter does, and trains only on
    inspections from 2024-01-03 on, whose year is fully on the record. It is worse: a third of
    routine inspections come more than a year after the facility's previous routine, so the
    window misses the one score that matters most. The headline keeps since-2023 history; its
    forward test stays honest, because each training row saw only what was on the record then.
  * ZIP: with and without. Without ZIP the model ranks slightly better, and its recall of majors
    shows no detectable gap across ZIP income or %-Hispanic groups (fairness_check.py, whose
    intervals resample whole ZIPs); with ZIP it shows one by %-Hispanic. The headline has no
    ZIP, as the public site's card has none.

This file is also the research code's shared library: sim_schedule.py, fairness_check.py,
threshold_tradeoff.py, feedback_check.py, export_dashboard.py and export_worklist.py import the
loader, the features, the variants and the fitting code from here, so a fix lands everywhere.

    python model_food.py     # forward test, variants, baselines, survivorship bound -> food_gains.png
Writes its headline numbers to data/research_results.json for export_dashboard.py."""
import json, os
import pandas as pd, numpy as np
import export_site as es

DATA = "data/sd_inspections.csv"
RAW = "data/sd_businesses.json"
RESULTS = "data/research_results.json"
TRAIN_END = "2024-12-31"        # train on inspections up to here, test on the rest
WINDOW_DAYS = es.WINDOW_DAYS    # 365: the 12-month window, as the public site's exporter
SCORE_WINDOW_DAYS = es.SCORE_WINDOW_DAYS  # 730: how far back persistence reads the last score (as export_site)
WINDOW_FROM = "2024-01-03"      # the record starts 2023-01-03: from here every window is whole
FILL_SCORE = 97.0               # a facility with no routine score ranks as a typical A (as export_site)
BOOT = 1000
MAX_ITER = 300                  # boosting rounds, at most; the count is chosen on the last VAL_MONTHS of training
VAL_MONTHS = 3

CAT = ["business_type", "zip"]
HIST = ["prior_n", "days_since_last", "last_score", "last_major", "prior_major_rate",
        "prior_mean_score", "prior_mean_viol"]                                   # since 2023-01
HIST12 = ["w_prior_n", "w_days_since_last", "w_last_score", "w_last_major", "w_major_rate",
          "w_mean_score", "w_mean_viol"]                                         # prior 365 days

# name -> (label, categorical, numeric, first training date or None)
VARIANTS = {
    "published":     ("As published: since-2023 history, permit age as of the pull (leaks)",
                      CAT, HIST + ["facility_age_asof_pull", "month"], None),
    "age_missing":   ("Since-2023 history, permit age missing when the permit post-dates the inspection",
                      CAT, HIST + ["facility_age_yrs", "month"], None),
    "since2023":     ("Since-2023 history, no permit age", CAT, HIST + ["month"], None),
    "since2023_nozip": ("Since-2023 history, no permit age, no ZIP", ["business_type"], HIST + ["month"], None),
    "window":        ("12-month window, no permit age (trained 2024)", CAT, HIST12 + ["month"], WINDOW_FROM),
    "window_nozip":  ("12-month window, no permit age, no ZIP (trained 2024)", ["business_type"],
                      HIST12 + ["month"], WINDOW_FROM),
    "window_2023":   ("12-month window, no permit age, trained 2023-24 (2023 windows cut short)",
                      CAT, HIST12 + ["month"], None),
}
HEADLINE = "since2023_nozip"    # the variant every other script and the worklist use
WITH_ZIP = "since2023"          # the headline plus ZIP: the ablation, and the fairness comparison
WINDOW = "window_nozip"         # the headline read over a 12-month window

# the one-line rule (what outreach and the worklist lead with) and the other no-model orderings;
# each is a column of the routine rows, higher = inspect first
PERSIST = "Persistence (own record: majors, last 12 mo; last score, 24 mo)"
RULE = "Mean routine score on record (one-line rule)"
BASELINES = {
    PERSIST: "persistence",
    RULE: "rule_mean_all",
    "Mean routine score, last 12 months": "rule_mean12",
    "Last routine score alone": "rule_last",
    "Prior major-violation rate": "rule_major_rate",
}

# ── the record ─────────────────────────────────────────────────────────────────────────

def _order(df):
    """By facility and date; within a day the routine row first (and a stand-in row from
    features_asof last), so a routine inspection's history is strictly earlier dates."""
    later = df["insp_type"].astype(str) != "Routine"
    asof = df["_asof"] if "_asof" in df else pd.Series(False, index=df.index)
    return (df.assign(_later=later, _asof=asof)
              .sort_values(["business_id", "completed_date", "_asof", "_later"], kind="stable")
              .drop(columns="_later").reset_index(drop=True))


def load(path=DATA):
    """data/sd_inspections.csv (fetch_sdfood.py; the site's data rules), ready for features."""
    df = pd.read_csv(path, low_memory=False, dtype={"zip": "string"})
    df["completed_date"] = pd.to_datetime(df["completed_date"], errors="coerce")
    df["opened_date"] = pd.to_datetime(df["opened_date"], errors="coerce")
    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df = df.dropna(subset=["completed_date"])
    # score is NaN unless it is a real routine score; a Follow-up (the County's re-grade or
    # reopening visit) keeps its score in the CSV, but that is not the place's routine score.
    df.loc[df["insp_type"].astype(str) != "Routine", "score"] = np.nan
    df["major"] = (df["n_major"] > 0).astype(float)
    # Two routine rows for one facility on one day would let the second see the first's outcome as
    # "history" (add_features works row by row). fetch_sdfood's CSV builder merges them; refuse if not.
    rt_day = df[df["insp_type"].astype(str) == "Routine"].duplicated(["business_id", "completed_date"])
    if rt_day.any():
        raise ValueError(f"{int(rt_day.sum())} same-day duplicate routine rows in {path}: rebuild the CSV "
                         "from the saved pull (python fetch_sdfood.py --csv-only; no network), which merges them")
    # The score the no-model rules read: a routine that ended in a health closure order has no score,
    # and counts as es.CLOSURE_SCORE, as in the published card (export_site.features_at). Without
    # this a place closed at its only routine ranked as a typical A. Model features keep real scores.
    df["rated_score"] = df["score"]
    if "closure" in df.columns:
        closed = ((df["insp_type"].astype(str) == "Routine") & df["score"].isna()
                  & (df["closure"].astype(str).str.lower() == "health"))
        df.loc[closed, "rated_score"] = float(es.CLOSURE_SCORE)
    return _order(df)


def persistence(df, days=WINDOW_DAYS, score_days=SCORE_WINDOW_DAYS):
    """export_site.persistence for every row, from the facility's record in the `days` before the
    row's date (strictly earlier dates): routine inspections with a major, then majors on routine /
    re-inspection / follow-up visits, then the lowest last routine score, read over `score_days`
    as export_site does (a third of routine inspections come more than a year apart). df sorted by _order."""
    t = df["completed_date"].values.astype("datetime64[D]").astype(np.int64)
    typ = df["insp_type"].astype(str).values
    rt_ = typ == "Routine"; rec = np.isin(typ, ["Routine", "Re-inspection", "Follow-up"])
    mj = np.nan_to_num(df["n_major"].values.astype(float)); sc = np.where(rt_, df["score"].values, np.nan)
    out = np.full((len(df), 3), np.nan)
    for ix in df.groupby("business_id", sort=False).indices.values():
        tt = t[ix]; hi = np.searchsorted(tt, tt, "left"); lo = np.searchsorted(tt, tt - days, "left")
        lo_s = np.searchsorted(tt, tt - score_days, "left")
        c1 = np.r_[0, np.cumsum(rt_[ix] & (mj[ix] > 0))]; c2 = np.r_[0, np.cumsum(rec[ix] * mj[ix])]
        s = sc[ix]; lastpos = np.maximum.accumulate(np.where(np.isnan(s), -1, np.arange(len(ix))))
        lp = np.where(hi > 0, lastpos[np.maximum(hi - 1, 0)], -1)
        out[ix] = np.c_[c1[hi] - c1[lo], c2[hi] - c2[lo], np.where(lp >= lo_s, s[np.maximum(lp, 0)], np.nan)]
    X = np.zeros((len(df), len(es.NUMERIC)))
    for j, c in enumerate(["routines_major", "majors", "last_score"]):
        X[:, es.NUMERIC.index(c)] = out[:, j]
    return es.persistence(X)


def window_features(df, days=WINDOW_DAYS):
    """The since-2023 history features, read over the `days` before each row's date instead
    (strictly earlier dates). Also the count of routine scores in the window. df sorted by _order."""
    t = df["completed_date"].values.astype("datetime64[D]").astype(np.int64)
    mj = (np.nan_to_num(df["n_major"].values.astype(float)) > 0).astype(float)
    nv = np.nan_to_num(df["n_violations"].values.astype(float))
    sc = df["score"].values.astype(float); has = ~np.isnan(sc)
    out = np.full((len(df), len(HIST12) + 1), np.nan)
    for ix in df.groupby("business_id", sort=False).indices.values():
        tt = t[ix]; hi = np.searchsorted(tt, tt, "left"); lo = np.searchsorted(tt, tt - days, "left")
        n = (hi - lo).astype(float); prev = np.maximum(hi - 1, 0)
        cm = np.r_[0, np.cumsum(mj[ix])]; cv = np.r_[0, np.cumsum(nv[ix])]
        s, hs = sc[ix], has[ix]
        cs = np.r_[0, np.cumsum(np.where(hs, s, 0.0))]; cn = np.r_[0, np.cumsum(hs)]
        ns = (cn[hi] - cn[lo]).astype(float)
        lastpos = np.maximum.accumulate(np.where(hs, np.arange(len(ix)), -1))
        lp = np.where(hi > 0, lastpos[prev], -1)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[ix] = np.c_[n,
                            np.where(n > 0, tt - tt[prev], np.nan),
                            np.where(lp >= lo, s[np.maximum(lp, 0)], np.nan),
                            np.where(n > 0, mj[ix][prev], np.nan),
                            np.where(n > 0, (cm[hi] - cm[lo]) / n, np.nan),
                            np.where(ns > 0, (cs[hi] - cs[lo]) / ns, np.nan),
                            np.where(n > 0, (cv[hi] - cv[lo]) / n, np.nan),
                            ns]
    return pd.DataFrame(out, columns=HIST12 + ["w_n_scores"], index=df.index)


def add_features(df):
    """Every feature, for every row, from strictly earlier dates. df from load() (or _order)."""
    df = df.copy()
    g = df.groupby("business_id", sort=False)
    df["prior_n"]          = g.cumcount()
    df["days_since_last"]  = (df["completed_date"] - g["completed_date"].shift(1)).dt.days
    df["last_score"]       = g["score"].transform(lambda s: s.shift().ffill())   # last real routine score
    df["last_major"]       = (g["n_major"].shift(1) > 0).astype("float")
    df["prior_major_rate"] = g["major"].transform(lambda s: s.shift().expanding().mean())
    df["prior_mean_score"] = g["score"].transform(lambda s: s.shift().expanding().mean())
    df["prior_mean_viol"]  = g["n_violations"].transform(lambda s: s.shift().expanding().mean())
    rated = df["rated_score"] if "rated_score" in df.columns else df["score"]
    df["prior_mean_rated"] = rated.groupby(df["business_id"], sort=False).transform(lambda s: s.shift().expanding().mean())
    df["last_rated"]       = rated.groupby(df["business_id"], sort=False).transform(lambda s: s.shift().ffill())
    age = (df["completed_date"] - df["opened_date"]).dt.days / 365.25
    df["facility_age_asof_pull"] = age               # the permit in force at the pull: leaks, kept to measure it
    df["facility_age_yrs"] = age.where(age >= 0)     # missing when the permit was issued after the inspection
    df["month"] = df["completed_date"].dt.month
    w = window_features(df)
    df[w.columns] = w
    w_rated = window_features(df.assign(score=rated))["w_mean_score"]
    df["persistence"] = persistence(df)
    # the no-model rules, higher = first; they read closures as es.CLOSURE_SCORE (rated), like the card
    df["rule_mean12"] = -w_rated.fillna(FILL_SCORE)
    df["rule_mean_all"] = -df["prior_mean_rated"].fillna(FILL_SCORE)
    df["rule_last"] = -df["last_rated"].fillna(FILL_SCORE)
    return df


def routine_rows(df):
    """The routine inspections (the ones the County schedules and could reorder), categories as
    strings. "Follow-up" re-grade / reopening visits are not routine labels."""
    d = df[df["insp_type"].astype(str) == "Routine"].copy()
    for c in CAT:
        d[c] = d[c].astype("string").fillna("NA")
    return d


def features_asof(df, T, ids=None):
    """Features for a hypothetical routine inspection of each facility on date T (after its last
    visit), computed by the same code as the training rows: a stand-in row per facility is added
    at T and add_features reads its history, strictly before T. Indexed by business_id."""
    T = pd.Timestamp(T)
    base = df[[c for c in df.columns if c in ("business_id", "business_type", "zip", "lat", "lng", "opened_date",
                                               "insp_type", "completed_date", "score", "rated_score", "n_major",
                                               "n_violations", "major")]]
    last = base.groupby("business_id", sort=False).tail(1)
    if ids is not None:
        last = last[last["business_id"].isin(ids)]
    last = last[last["completed_date"] < T]
    stub = last[["business_id", "business_type", "zip", "lat", "lng", "opened_date"]].copy()
    stub = stub.assign(insp_type="Routine", completed_date=T, score=np.nan, n_major=np.nan,
                       n_violations=np.nan, major=np.nan, _asof=True)
    if "rated_score" in base.columns:        # only when the record has it: add_features falls back to score
        stub["rated_score"] = np.nan
    full = _order(pd.concat([base[base["business_id"].isin(stub["business_id"])].assign(_asof=False), stub],
                            ignore_index=True))
    f = add_features(full)
    f = f[f["_asof"].astype(bool)].drop(columns="_asof")
    for c in CAT:
        f[c] = f[c].astype("string").fillna("NA")
    return f.set_index("business_id")


STATIC = ["business_id", "business_type", "zip", "lat", "lng", "opened_date"]


def month_start_rows(df, d):
    """Each routine row of `d`, with every feature recomputed as of the first day of its month:
    what a list scored that morning sees. History is strictly before the 1st, so no visit made
    inside the month (a complaint two weeks before the routine, say) is used. add_features runs
    on one stand-in row per facility and month, so training and the deployed list
    (export_worklist.model_orders -> features_asof) read features the same way. Aligned to d.index;
    the label and the real inspection date stay d's own."""
    cols = [c for c in ("business_id", "business_type", "zip", "lat", "lng", "opened_date", "insp_type",
                        "completed_date", "score", "rated_score", "n_major", "n_violations", "major", "closure")
            if c in df.columns]
    base = df[cols]
    T = d["completed_date"].dt.to_period("M").dt.start_time
    out = []
    for t, idx in T.groupby(T).groups.items():
        ids = d.loc[idx, "business_id"].unique()
        hist = base[base["business_id"].isin(ids) & (base["completed_date"] < t)]
        stub = d.loc[idx, [c for c in STATIC if c in d.columns]].drop_duplicates("business_id")
        stub = stub.assign(insp_type="Routine", completed_date=t, score=np.nan, n_major=np.nan,
                           n_violations=np.nan, major=np.nan, _asof=True)
        if "rated_score" in base.columns:
            stub["rated_score"] = np.nan
        full = _order(pd.concat([hist.assign(_asof=False), stub], ignore_index=True))
        f = add_features(full)
        out.append(f[f["_asof"].astype(bool)].drop(columns="_asof").assign(_month=t))
    feats = pd.concat(out, ignore_index=True).set_index(["business_id", "_month"])
    key = pd.MultiIndex.from_arrays([d["business_id"].to_numpy(), T.to_numpy()])
    m = feats.reindex(key)
    m.index = d.index
    keep = [c for c in m.columns if c not in ("insp_type", "completed_date", "score", "rated_score", "n_major",
                                              "n_violations", "major", "closure")]
    r = d[["insp_type", "completed_date", "major"] + [c for c in ("n_major",) if c in d.columns]].join(m[keep])
    for c in CAT:
        r[c] = r[c].astype("string").fillna("NA")
    return r


# ── the model ──────────────────────────────────────────────────────────────────────────

class Model:
    """HistGradientBoosting on one variant's features (the settings used since the first run)."""
    def __init__(self, variant=HEADLINE):
        self.variant = variant
        _, self.cat, self.num, self.train_from = VARIANTS[variant]

    def _X(self, rows):
        X = rows[self.cat + self.num].copy()
        X[self.cat] = self.enc.transform(X[self.cat])
        return X

    def _clf(self, X, max_iter):
        from sklearn.ensemble import HistGradientBoostingClassifier
        return HistGradientBoostingClassifier(
            max_iter=max_iter, learning_rate=0.08, max_leaf_nodes=48,
            categorical_features=[X.columns.get_loc(c) for c in self.cat], l2_regularization=1.0,
            early_stopping=False, random_state=0)

    def fit(self, rows, y=None, sample_weight=None):
        """Early stopping on TIME: the number of boosting rounds is chosen on the last VAL_MONTHS of
        the training rows (a random 10% split, sklearn's default, puts a facility's inspections on
        both sides and wastes 10% of the data), then the model is refit on every training row."""
        from sklearn.metrics import log_loss
        from sklearn.preprocessing import OrdinalEncoder
        self.enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-1)
        self.enc.fit(rows[self.cat])
        X = self._X(rows)
        yv = np.asarray(rows["major"].values if y is None else y)
        w = None if sample_weight is None else np.asarray(sample_weight)
        self.n_iter = None
        if "completed_date" in rows:
            dt = pd.to_datetime(rows["completed_date"]).to_numpy()
            cut = dt.max() - np.timedelta64(VAL_MONTHS * 30, "D")
            fit_m, val_m = dt <= cut, dt > cut
            if fit_m.sum() >= 1000 and val_m.sum() >= 300 and 0 < yv[val_m].sum() < val_m.sum():
                c = self._clf(X, MAX_ITER).fit(X[fit_m], yv[fit_m], sample_weight=None if w is None else w[fit_m])
                losses = [log_loss(yv[val_m], p[:, 1], labels=[0, 1], sample_weight=None if w is None else w[val_m])
                          for p in c.staged_predict_proba(X[val_m])]
                self.n_iter = int(np.argmin(losses)) + 1
        if self.n_iter is None:              # too few rows for a time split: sklearn's own early stopping
            from sklearn.ensemble import HistGradientBoostingClassifier
            self.clf = HistGradientBoostingClassifier(
                max_iter=MAX_ITER, learning_rate=0.08, max_leaf_nodes=48,
                categorical_features=[X.columns.get_loc(c) for c in self.cat], l2_regularization=1.0,
                early_stopping=True, n_iter_no_change=20, random_state=0).fit(X, yv, sample_weight=w)
            self.n_iter = int(self.clf.n_iter_)
            return self
        self.clf = self._clf(X, self.n_iter).fit(X, yv, sample_weight=w)
        return self

    def predict(self, rows):
        return self.clf.predict_proba(self._X(rows))[:, 1]


def train_mask(d, variant, end=TRAIN_END, start=None):
    """Routine rows a variant trains on: up to `end`, and from its first date (or `start`)."""
    m = (d["completed_date"] <= pd.Timestamp(end)).to_numpy()
    first = start or VARIANTS[variant][3]
    if first:
        m = m & (d["completed_date"] >= pd.Timestamp(first)).to_numpy()
    return m


def fit_predict(d, variant, tr, te):
    return Model(variant).fit(d[tr]).predict(d[te])


# ── ranking measures ───────────────────────────────────────────────────────────────────

def top_weights(score, frac=0.20):
    """1 for rows in the top `frac` by score, 0 below; a tie straddling the cut gets its pro-rata
    share (the expectation under a random order within the tie, so baselines with many ties are
    not helped or hurt by an arbitrary tiebreak)."""
    score = np.asarray(score, dtype=float)
    n = len(score); k = frac * n
    order = np.argsort(-score, kind="stable"); s = score[order]
    starts = np.r_[0, np.flatnonzero(np.diff(s) != 0) + 1]; ends = np.r_[starts[1:], n]
    frac_in = np.clip((k - starts) / (ends - starts), 0, 1)
    w = np.empty(n); w[order] = np.repeat(frac_in, ends - starts)
    return w


def capture(score, yv, frac=0.20):
    w = top_weights(score, frac)
    return float((w * yv).sum() / yv.sum())


def gains(score, yv):
    """Cumulative-gains points at tie-group ends (straight lines inside a tie = random order)."""
    order = np.argsort(-score, kind="stable"); s = score[order]
    ends = np.r_[np.flatnonzero(np.diff(s) != 0) + 1, len(s)]
    cum = np.cumsum(yv[order])
    return np.r_[0, ends / len(s)] * 100, np.r_[0, cum[ends - 1] / yv.sum()] * 100


def business_status(path=RAW):
    """business_id -> permit status in the pull (Active, Expired, ...)."""
    raw = json.load(open(path))
    return {int(b["business_id"]): (b.get("status") or "?") for b in raw}


def save_results(key, value, path=RESULTS):
    out = json.load(open(path)) if os.path.exists(path) else {}
    out[key] = value
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(out, open(path, "w"), indent=1)


# ── the analysis ───────────────────────────────────────────────────────────────────────

def main():
    from sklearn.metrics import roc_auc_score, average_precision_score
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

    df = add_features(load())
    print(f"inspections: {len(df):,}  businesses: {df['business_id'].nunique():,}")
    print("date range:", df['completed_date'].min().date(), "->", df['completed_date'].max().date())
    print("by type:", df["insp_type"].value_counts().to_dict())
    print("overall major-violation rate:", f"{df['major'].mean()*100:.1f}%")

    # ---- the premise: does a facility's own record move its routine cadence? ----
    rt = df[df["insp_type"] == "Routine"]
    on_record = df.groupby("business_id")["completed_date"]
    span = (on_record.max() - on_record.min()).dt.days / 365.25
    fac = pd.DataFrame({"n": rt.groupby("business_id").size(), "rate": rt.groupby("business_id")["major"].mean(),
                        "type": rt.groupby("business_id")["business_type"].first()}).join(span.rename("span"))
    fac = fac[fac["span"] >= 3]                           # on the record ~the whole window
    fac["per_yr"] = fac["n"] / fac["span"]
    gap = rt.groupby("business_id")["completed_date"].diff().dt.days
    prev = rt.groupby("business_id")["major"].shift()
    premise = {"facilities": int(len(fac)), "corr": round(float(fac["rate"].corr(fac["per_yr"])), 3),
               "median_per_yr": round(float(fac["per_yr"].median()), 2),
               "school_per_yr": round(float(fac.loc[fac["type"] == "School Processing Food Facility", "per_yr"].median()), 2),
               "gap_after_major": int(gap[prev == 1].median()), "gap_after_clean": int(gap[prev == 0].median())}
    print(f"\n=== premise (facilities on the record >=3 yr, n={premise['facilities']:,}) ===")
    print(f"routine inspections/yr: median {premise['median_per_yr']}, school processing {premise['school_per_yr']}")
    print(f"corr(facility's routine major rate, its routine inspections/yr) = {premise['corr']:+.3f}")
    print(f"median days to the next routine: {premise['gap_after_major']} after a routine with a major, "
          f"{premise['gap_after_clean']} after one without")

    d = routine_rows(df)
    y = d["major"].values.astype(int)
    te = (d["completed_date"] > pd.Timestamp(TRAIN_END)).values
    yte = y[te]; dt = d.loc[te]
    print(f"\nroutine inspections modeled: {len(d):,}  major rate: {d['major'].mean()*100:.1f}%")
    print(f"test (2025+): {te.sum():,}  test major rate: {yte.mean()*100:.1f}%")

    # ---- the permit-age leak ----
    age = d["facility_age_asof_pull"]
    trn = (d["completed_date"] <= pd.Timestamp(TRAIN_END)).values
    neg = (age < 0).values
    leak = {"train_negative": int((neg & trn).sum()), "train_negative_major_rate": round(float(y[neg & trn].mean()), 3),
            "train_other_major_rate": round(float(y[~neg & trn].mean()), 3),
            "test_negative": int((neg & te).sum()), "test_negative_major_rate": round(float(y[neg & te].mean()), 3),
            "missing_opened": int(age.isna().sum())}
    print(f"\n=== permit age as of the pull ===\n{leak['train_negative']} training routine inspections predate their "
          f"permit (major rate {leak['train_negative_major_rate']*100:.1f}% vs {leak['train_other_major_rate']*100:.1f}%); "
          f"{leak['test_negative']} in the test set ({leak['test_negative_major_rate']*100:.1f}%); "
          f"{leak['missing_opened']} with no permit date.")

    # ---- the history window: left truncation ----
    trunc = {str(yr): {"median_prior_n": float(g["prior_n"].median()), "median_w_prior_n": float(g["w_prior_n"].median())}
             for yr, g in d.groupby(d["completed_date"].dt.year)}
    print("median prior visits on record, since 2023 vs last 12 months, by year:",
          {k: (v["median_prior_n"], v["median_w_prior_n"]) for k, v in trunc.items()})
    miss12 = float(dt["w_mean_score"].isna().mean())
    print(f"test inspections with no routine score in the prior 12 months: {miss12*100:.1f}% "
          f"(since 2023: {dt['prior_mean_score'].isna().mean()*100:.1f}%)")

    # ---- every variant on the same test set ----
    P = {}; var_rows = {}
    print("\n=== model variants, same 2025+ test set ===")
    for v, (label, cat, num, first) in VARIANTS.items():
        tr = train_mask(d, v)
        P[v] = fit_predict(d, v, tr, te)
        var_rows[v] = {"label": label, "train_n": int(tr.sum()), "auc": round(float(roc_auc_score(yte, P[v])), 4),
                       "top20_recall": round(capture(P[v], yte), 4),
                       "pr_auc": round(float(average_precision_score(yte, P[v])), 4)}
        r = var_rows[v]
        print(f"  {v:16s} train {r['train_n']:>6,}  AUC {r['auc']:.3f}  top-20% {r['top20_recall']*100:4.1f}%  "
              f"PR-AUC {r['pr_auc']:.3f}   {label}")
    p = P[HEADLINE]

    # ---- the headline model against the no-model orderings ----
    scores = {"Model": p}
    for k, c in BASELINES.items():
        scores[k] = dt[c].values if c != "rule_major_rate" else dt["prior_major_rate"].fillna(
            d.loc[trn, "major"].mean()).values
    W = {k: top_weights(v) for k, v in scores.items()}
    rows = [{"ranking": k, "auc": roc_auc_score(yte, v), "top20_recall": (W[k]*yte).sum()/yte.sum(),
             "top20_precision": (W[k]*yte).sum()/W[k].sum()} for k, v in scores.items()]
    tab = pd.DataFrame(rows).set_index("ranking")
    tab["lift"] = tab["top20_precision"] / yte.mean()
    print(f"\n=== TEST (2025+, n={te.sum():,}, {yte.sum():,} with a major, base rate {yte.mean():.3f}); "
          f"model = {HEADLINE} ===")
    print(tab.round(3).to_string())
    print(f"PR-AUC   model={average_precision_score(yte,p):.3f}   base_rate={yte.mean():.3f}")

    # ---- the same test, scored AS DEPLOYED: features as of the 1st of each inspection's month ----
    # (the table above reads each row's history up to the inspection date, so a complaint visit two
    # weeks earlier in the same month counts; the monthly list cannot know it on the 1st)
    dm = month_start_rows(df, dt)
    pm = Model(HEADLINE).fit(d[train_mask(d, HEADLINE)]).predict(dm)
    # the deployed list (export_worklist.model_orders) also TRAINS on month-start rows; the research
    # figures train on inspection-date rows. Same test, both scored as of the 1st:
    pm_ms = Model(HEADLINE).fit(month_start_rows(df, d[train_mask(d, HEADLINE)])).predict(dm)
    deployed_scores = {"Model": pm}
    for k, c in BASELINES.items():
        deployed_scores[k] = dm[c].values if c != "rule_major_rate" else dm["prior_major_rate"].fillna(
            d.loc[trn, "major"].mean()).values
    as_deployed = {}
    for k, v in deployed_scores.items():
        wk = top_weights(v)
        prec = float((wk * yte).sum() / wk.sum())
        as_deployed[k] = {"auc": round(float(roc_auc_score(yte, v)), 4),
                          "top20_recall": round(float((wk * yte).sum() / yte.sum()), 4),
                          "top20_precision": round(prec, 4), "lift": round(prec / float(yte.mean()), 4)}
    changed = float((dt["prior_n"].values > dm["prior_n"].values).mean())   # a visit between the 1st and the inspection
    print(f"\n=== the same test AS DEPLOYED (features as of the 1st of the month; {changed*100:.1f}% of test rows "
          f"have a visit inside their month before the inspection) ===")
    for k, r in as_deployed.items():
        print(f"  {k:45s} AUC {r['auc']:.3f} (inspection-date features {tab.loc[k, 'auc']:.3f})  "
              f"top-20% {r['top20_recall']*100:4.1f}%")

    # ---- paired bootstrap over facilities ----
    base_names = list(BASELINES)
    best_auc = max(base_names, key=lambda k: tab.loc[k, "auc"])
    best_cap = max(base_names, key=lambda k: tab.loc[k, "top20_recall"])
    comps = sorted({best_auc, best_cap, PERSIST, RULE}, key=base_names.index)
    # variant pairs that differ in one thing: (a, b) reports a minus b
    pairs = {"permit age as published": ("published", "since2023"),
             "permit age missing when impossible": ("age_missing", "since2023"),
             "with ZIP": (WITH_ZIP, HEADLINE),
             "12-month window": (WINDOW, HEADLINE)}
    EW = {v: top_weights(P[v]) for pr in pairs.values() for v in pr}
    WD = {k: top_weights(v) for k, v in deployed_scores.items()}
    WMS = top_weights(pm_ms)
    codes = pd.factorize(dt["business_id"])[0]; ncl = codes.max() + 1
    rng = np.random.default_rng(0)
    draws = {k: {"auc": [], "cap": []} for k in comps + list(pairs)}
    ddraws = {k: {"auc": [], "cap": []} for k in comps}   # the same pairs, scored as deployed
    dtrain = {"auc": [], "cap": []}                       # month-start minus inspection-date training
    for _ in range(BOOT):
        wt = np.bincount(rng.integers(0, ncl, ncl), minlength=ncl)[codes].astype(float)
        am = roc_auc_score(yte, p, sample_weight=wt); cm = (wt*W["Model"]*yte).sum() / (wt*yte).sum()
        for k in comps:
            draws[k]["auc"].append(am - roc_auc_score(yte, scores[k], sample_weight=wt))
            draws[k]["cap"].append(cm - (wt*W[k]*yte).sum() / (wt*yte).sum())
        amd = roc_auc_score(yte, pm, sample_weight=wt); cmd = (wt*WD["Model"]*yte).sum() / (wt*yte).sum()
        for k in comps:
            ddraws[k]["auc"].append(amd - roc_auc_score(yte, deployed_scores[k], sample_weight=wt))
            ddraws[k]["cap"].append(cmd - (wt*WD[k]*yte).sum() / (wt*yte).sum())
        dtrain["auc"].append(roc_auc_score(yte, pm_ms, sample_weight=wt) - amd)
        dtrain["cap"].append((wt*WMS*yte).sum() / (wt*yte).sum() - cmd)
        va = {v: roc_auc_score(yte, P[v], sample_weight=wt) for v in EW}
        vc = {v: (wt*EW[v]*yte).sum() / (wt*yte).sum() for v in EW}
        for k, (a, b) in pairs.items():
            draws[k]["auc"].append(va[a] - va[b]); draws[k]["cap"].append(vc[a] - vc[b])
    ci = lambda v: [round(float(x), 4) for x in np.percentile(v, [2.5, 97.5])]
    diffs = {}
    print(f"\n=== model minus baseline, 95% paired bootstrap over {ncl:,} facilities ({BOOT} draws) ===")
    for k in comps:
        da, dc = tab.loc["Model", "auc"] - tab.loc[k, "auc"], tab.loc["Model", "top20_recall"] - tab.loc[k, "top20_recall"]
        diffs[k] = {"auc": round(float(da), 4), "auc_ci": ci(draws[k]["auc"]),
                    "top20_recall": round(float(dc), 4), "top20_recall_ci": ci(draws[k]["cap"])}
        tag = " (best AUC baseline)" * (k == best_auc) + " (best top-20% baseline)" * (k == best_cap)
        print(f"  vs {k}{tag}: AUC {da:+.3f} [{diffs[k]['auc_ci'][0]:+.3f}, {diffs[k]['auc_ci'][1]:+.3f}]   "
              f"top-20% capture {dc*100:+.1f} pts [{diffs[k]['top20_recall_ci'][0]*100:+.1f}, {diffs[k]['top20_recall_ci'][1]*100:+.1f}]")
    ddiffs = {}
    print("=== the same, AS DEPLOYED (features as of the 1st of the month) ===")
    for k in comps:
        m, b = as_deployed["Model"], as_deployed[k]
        da, dc = m["auc"] - b["auc"], m["top20_recall"] - b["top20_recall"]
        ddiffs[k] = {"auc": round(da, 4), "auc_ci": ci(ddraws[k]["auc"]),
                     "top20_recall": round(dc, 4), "top20_recall_ci": ci(ddraws[k]["cap"])}
        print(f"  vs {k}: AUC {da:+.3f} [{ddiffs[k]['auc_ci'][0]:+.3f}, {ddiffs[k]['auc_ci'][1]:+.3f}]   "
              f"top-20% capture {dc*100:+.1f} pts [{ddiffs[k]['top20_recall_ci'][0]*100:+.1f}, {ddiffs[k]['top20_recall_ci'][1]*100:+.1f}]")
    ms = {"auc": round(float(roc_auc_score(yte, pm_ms)), 4), "top20_recall": round(capture(pm_ms, yte), 4)}
    ms["minus_inspection_date_training"] = {
        "auc": round(ms["auc"] - as_deployed["Model"]["auc"], 4), "auc_ci": ci(dtrain["auc"]),
        "top20_recall": round(ms["top20_recall"] - as_deployed["Model"]["top20_recall"], 4),
        "top20_recall_ci": ci(dtrain["cap"])}
    t = ms["minus_inspection_date_training"]
    print(f"  the deployed list's training (month-start rows): AUC {ms['auc']:.3f}, top-20% {ms['top20_recall']*100:.1f}%; "
          f"minus inspection-date training: AUC {t['auc']:+.3f} [{t['auc_ci'][0]:+.3f}, {t['auc_ci'][1]:+.3f}]   "
          f"top-20% {t['top20_recall']*100:+.1f} pts [{t['top20_recall_ci'][0]*100:+.1f}, {t['top20_recall_ci'][1]*100:+.1f}]")
    vdiffs = {}
    print("=== one change at a time (variant a minus variant b), same bootstrap ===")
    for k, (a, b) in pairs.items():
        da = var_rows[a]["auc"] - var_rows[b]["auc"]; dc = var_rows[a]["top20_recall"] - var_rows[b]["top20_recall"]
        vdiffs[k] = {"a": a, "b": b, "auc": round(float(da), 4), "auc_ci": ci(draws[k]["auc"]),
                     "top20_recall": round(float(dc), 4), "top20_recall_ci": ci(draws[k]["cap"])}
        print(f"  {k:36s} ({a} - {b}) AUC {da:+.3f} [{vdiffs[k]['auc_ci'][0]:+.3f}, {vdiffs[k]['auc_ci'][1]:+.3f}]   "
              f"top-20% {dc*100:+.1f} pts [{vdiffs[k]['top20_recall_ci'][0]*100:+.1f}, {vdiffs[k]['top20_recall_ci'][1]*100:+.1f}]")

    # ---- survivorship: SD Food Info lists only facilities that exist today ----
    status = business_status()
    last_seen = df.groupby("business_id")["completed_date"].max()
    dt_status = dt["business_id"].map(status).fillna("?").str.lower()
    exp = (dt_status == "expired").values
    r_exp, r_act = float(yte[exp].mean()), float(yte[~exp].mean())
    opened = df.drop_duplicates("business_id").set_index("business_id")["opened_date"]
    active_2024 = last_seen.index[(df.groupby("business_id")["completed_date"].min() <= "2024-12-31")]
    opened_2024 = int(((opened >= "2024-01-01") & (opened <= "2024-12-31")).sum())
    surv = {"businesses": int(len(last_seen)), "last_seen_before_2025": int((last_seen < "2025-01-01").sum()),
            "status_counts": {k: int(v) for k, v in pd.Series(status).value_counts().items()},
            "test_expired_n": int(exp.sum()), "test_expired_major_rate": round(r_exp, 4),
            "test_other_major_rate": round(r_act, 4), "on_record_by_2024": int(len(active_2024)),
            "permits_opened_2024": opened_2024,
            "turnover_2024": round(opened_2024 / max(len(active_2024), 1), 3), "scenarios": {}}
    print(f"\n=== survivorship ===\n{surv['last_seen_before_2025']} of {surv['businesses']:,} businesses were last "
          f"seen before 2025 (a full record would hold every place that closed in 2023-24).")
    print(f"permit status in the pull: {surv['status_counts']}")
    print(f"test inspections at facilities whose permit has since expired: {exp.sum():,}, major rate "
          f"{r_exp*100:.1f}% vs {r_act*100:.1f}%")
    print(f"permits opened in 2024: {opened_2024:,} ({surv['turnover_2024']*100:.1f}% of the {len(active_2024):,} "
          f"facilities on the record by 2024): in a stable population about as many close each year.")
    # add X% more test inspections from missing (closed) facilities, at the expired group's major
    # rate: (a) like the expired facilities that are still listed (their inspections resampled,
    # score and outcome together), (b) worst case, the same rate but every one ranked last.
    # Re-cut the top 20% and recompute its share of majors.
    rs = np.random.default_rng(1)
    idx_exp = np.flatnonzero(exp)
    for X in (0.05, 0.10, 0.20):
        M = int(round(X * te.sum())); row = {}
        for arm, sc in (("Model", p), (RULE, scores[RULE]), (PERSIST, scores[PERSIST])):
            like = []
            for _ in range(20):
                pick = rs.choice(idx_exp, M, replace=True)
                like.append(capture(np.r_[sc, sc[pick]], np.r_[yte, yte[pick]]))
            worst = capture(np.r_[sc, np.full(M, sc.min() - 1)], np.r_[yte, (rs.random(M) < r_exp).astype(float)])
            row[arm] = {"like_expired": round(float(np.mean(like)), 4), "worst": round(float(worst), 4)}
        surv["scenarios"][f"{int(X*100)}%"] = row
        print(f"  +{int(X*100):2d}% missing inspections at {r_exp*100:.0f}% major: top-20% capture "
              + "; ".join(f"{a.split(' (')[0]} {tab.loc[a if a != 'Model' else 'Model','top20_recall']*100:.1f}% -> "
                          f"{r['like_expired']*100:.1f}% (worst {r['worst']*100:.1f}%)" for a, r in row.items()))

    # ---- cumulative gains, with the baselines ----
    fig, ax = plt.subplots(figsize=(7.6, 5.4), dpi=150)
    style = {"Model": ("#1d6a97", 2.6, "-"), PERSIST: ("#c9741a", 2.0, "-"), RULE: ("#2f7d5b", 2.0, "-."),
             "Mean routine score, last 12 months": ("#6e9e86", 1.1, ":"),
             "Prior major-violation rate": ("#8a6fae", 1.2, "--"), "Last routine score alone": ("#5a6b78", 1.2, ":")}
    for k, v in scores.items():
        gx, gy = gains(v, yte); col, lw, ls = style[k]
        ax.plot(gx, gy, color=col, lw=lw, ls=ls, label=f"{k} (top 20% → {tab.loc[k,'top20_recall']*100:.0f}%)")
    ax.plot([0, 100], [0, 100], ls="--", color="#b8c2c9", lw=1.2, label="Routine calendar, no targeting (20%)")
    m20, s20, p20 = (tab.loc[k, "top20_recall"]*100 for k in ("Model", RULE, PERSIST))
    ax.axvline(20, color="#d7e0e6", lw=1, zorder=0)
    ax.scatter([20, 20, 20], [m20, s20, p20], color=["#1d6a97", "#2f7d5b", "#c9741a"], zorder=5, s=36)
    ax.annotate(f"Top 20%: model {m20:.0f}%, one-line rule {s20:.0f}%,\npersistence {p20:.0f}% of all major violations",
                (20, m20), xytext=(4, 84), fontsize=9.2, color="#333", arrowprops=dict(arrowstyle="->", color="#1d6a97"))
    ax.set_xlabel("% of routine inspections done, in ranked order")
    ax.set_ylabel("% of all major violations found")
    ax.set_title("Risk-ranking vs what an inspector already knows\n"
                 "San Diego County, forward test on 2025+ routine inspections", fontsize=12.5, fontweight="bold", loc="left")
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.legend(frameon=False, fontsize=7.6, loc="lower right")
    for sp in ["top", "right"]: ax.spines[sp].set_visible(False)
    ax.grid(color="#eee")
    fig.text(0.01, 0.01, f"Source: sdfoodinfo.org (SD County DEH). n={len(yte):,} routine inspections the model never saw. "
             "Model: history since 2023-01, no permit age, no ZIP. One-line rule: lowest mean routine score on record (since "
             "2023-01) first. Persistence: routine inspections with a major, then majors, in the prior 12 months, "
             "then lowest last score.", fontsize=6.3, color="#777", wrap=True)
    fig.tight_layout(rect=[0, 0.05, 1, 1]); fig.savefig("food_gains.png", bbox_inches="tight")
    print("saved food_gains.png")

    # ---- what drives it + precision within type ----
    from sklearn.inspection import permutation_importance
    m = Model(HEADLINE).fit(d[train_mask(d, HEADLINE)])
    Xte = m._X(dt); idx = np.random.default_rng(0).choice(len(Xte), min(8000, len(Xte)), replace=False)
    pi = permutation_importance(m.clf, Xte.iloc[idx], yte[idx], n_repeats=5, scoring="roc_auc", random_state=0)
    imp = pd.Series(pi.importances_mean, index=Xte.columns).sort_values(ascending=False)
    print("\n=== permutation importance (AUC drop) ===")
    print(imp.round(4).to_string())

    res = pd.DataFrame({"p": p, "y": yte, "type": dt["business_type"].astype(str).values})
    flagged = res.sort_values("p", ascending=False).head(int(0.2*len(res)))
    print("\n=== is the flagged top-20% just one business type? ===")
    comp = pd.DataFrame({"flagged_top20%": flagged["type"].value_counts(normalize=True),
                         "overall": res["type"].value_counts(normalize=True)}).fillna(0)
    print((comp.sort_values("overall", ascending=False)*100).round(1).head(8).to_string())
    print("\n=== precision by business type (top-20% flagged) ===")
    within = {}
    for t, gp in res.assign(flag=res.index.isin(flagged.index)).groupby("type"):
        if len(gp) >= 300:
            fl = gp[gp["flag"]]
            if len(fl) >= 30:
                print(f"  {t[:34]:34s} flagged {len(fl):4d}  precision {fl['y'].mean():.2f}  base {gp['y'].mean():.2f}")
                within[t] = {"precision": round(float(fl['y'].mean()), 3), "base": round(float(gp['y'].mean()), 3)}

    save_results("model", {
        "n_inspections": int(len(df)), "n_facilities": int(df["business_id"].nunique()),
        "n_routine": int(len(d)), "major_rate": round(float(d["major"].mean()), 4),
        "data_from": str(df["completed_date"].min().date()), "data_to": str(df["completed_date"].max().date()),
        "headline": HEADLINE, "headline_label": VARIANTS[HEADLINE][0], "rule": RULE,
        "train_n": var_rows[HEADLINE]["train_n"], "test_n": int(te.sum()), "test_major_rate": round(float(yte.mean()), 4),
        "pr_auc": round(float(average_precision_score(yte, p)), 4),
        "rankings": {k: {c: round(float(tab.loc[k, c]), 4) for c in tab.columns} for k in tab.index},
        "as_deployed": {"rankings": as_deployed, "rows_with_a_visit_inside_the_month": round(changed, 4), "vs": ddiffs,
                        "trained_on_month_start_rows": ms,
                        "note": "features as of the 1st of each test inspection's month (month_start_rows)"},
        "best_auc_baseline": best_auc, "best_top20_baseline": best_cap, "vs": diffs,
        "variants": var_rows, "ablation": vdiffs, "age_leak": leak, "truncation": trunc,
        "test_no_12mo_score": round(miss12, 4), "survivorship": surv,
        "importance": {k: round(float(v), 4) for k, v in imp.head(6).items()}, "within_type": within,
        "premise": premise,
    })
    print(f"\nwrote {RESULTS}")


if __name__ == "__main__":
    main()
