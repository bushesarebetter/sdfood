"""Export dashboard data. Two distinct things, kept honest:
  (1) STATS/EVIDENCE come from the proper hold-out validation (train<=2024, test 2025+).
  (2) The WORKLIST is FORWARD-LOOKING: a model trained on ALL data scores each currently
      active facility for its NEXT (not-yet-done) inspection, using its full history to date.
Facilities are anonymized (type/area/history only) because the page is shareable."""
import pandas as pd, numpy as np, json
from sklearn.preprocessing import OrdinalEncoder
from sklearn.ensemble import HistGradientBoostingClassifier

TODAY=pd.Timestamp("2026-09-18")
df=pd.read_csv("data/sd_inspections.csv",low_memory=False)
df["completed_date"]=pd.to_datetime(df["completed_date"],errors="coerce")
df["opened_date"]=pd.to_datetime(df["opened_date"],errors="coerce")
df["score"]=pd.to_numeric(df["score"],errors="coerce")
df=df.dropna(subset=["completed_date"]).sort_values(["business_id","completed_date"])
df["major"]=(df["n_major"]>0).astype(int)

# ---- per-inspection features (training format) ----
g=df.groupby("business_id",sort=False)
df["prior_n"]=g.cumcount()
df["days_since_last"]=(df["completed_date"]-g["completed_date"].shift(1)).dt.days
df["last_score"]=g["score"].shift(1)
df["last_major"]=(g["n_major"].shift(1)>0).astype("float")
df["prior_major_rate"]=g["major"].transform(lambda s:s.shift().expanding().mean())
df["prior_mean_score"]=g["score"].transform(lambda s:s.shift().expanding().mean())
df["prior_mean_viol"]=g["n_violations"].transform(lambda s:s.shift().expanding().mean())
df["facility_age_yrs"]=(df["completed_date"]-df["opened_date"]).dt.days/365.25
df["month"]=df["completed_date"].dt.month
d=df[df["insp_type"].astype(str).str.contains("Routine",case=False,na=False)].copy()

cat=["business_type","zip"]
num=["prior_n","days_since_last","last_score","last_major","prior_major_rate",
     "prior_mean_score","prior_mean_viol","facility_age_yrs","month"]
for c in cat:
    d[c]=d[c].astype("string").fillna("NA")
    if d[c].nunique()>250:
        keep=d[c].value_counts().head(240).index; d[c]=d[c].where(d[c].isin(keep),"OTHER")

# ---- DEPLOY model: train on ALL routine inspections ----
enc=OrdinalEncoder(handle_unknown="use_encoded_value",unknown_value=-1,encoded_missing_value=-1)
X=d[cat+num].copy(); enc.fit(X[cat]); X[cat]=enc.transform(X[cat])
ci=[X.columns.get_loc(c) for c in cat]
clf=HistGradientBoostingClassifier(max_iter=300,learning_rate=0.08,max_leaf_nodes=48,
    categorical_features=ci,l2_regularization=1.0,early_stopping=True,n_iter_no_change=20,random_state=0)
clf.fit(X,d["major"].values)

# ---- FORWARD features: one row per facility, as of TODAY, for its NEXT inspection ----
allowed=set(d["business_type"].unique()); allowed_zip=set(d["zip"].unique())
gg=df.groupby("business_id")
last=gg.tail(1).set_index("business_id")
fwd=pd.DataFrame(index=last.index)
fwd["business_type"]=last["business_type"].astype("string")
fwd["business_type"]=fwd["business_type"].where(fwd["business_type"].isin(allowed),"OTHER")
fwd["zip"]=last["zip"].astype("string")
fwd["zip"]=fwd["zip"].where(fwd["zip"].isin(allowed_zip),"OTHER")
fwd["prior_n"]=gg.size()
fwd["last_completed"]=gg["completed_date"].max()
fwd["days_since_last"]=(TODAY-fwd["last_completed"]).dt.days
fwd["last_score"]=last["score"]
fwd["last_major"]=(last["n_major"]>0).astype(float)
fwd["prior_major_rate"]=gg["major"].mean()
fwd["prior_mean_score"]=gg["score"].mean()
fwd["prior_mean_viol"]=gg["n_violations"].mean()
fwd["facility_age_yrs"]=(TODAY-gg["opened_date"].min()).dt.days/365.25
fwd["month"]=TODAY.month

# active = inspected within last ~18 months (still operating)
fwd=fwd[fwd["days_since_last"]<=550].copy()
Xf=fwd[cat+num].copy(); Xf[cat]=enc.transform(Xf[cat])
fwd["risk"]=(clf.predict_proba(Xf)[:,1]*100).round(1)

city={str(b["business_id"]):b.get("city") for b in json.load(open("data/sd_businesses.json"))}
fwd["city"]=pd.Series(fwd.index.astype(str),index=fwd.index).map(city).fillna("").str.title()

fwd=fwd.sort_values("risk",ascending=False)
work=fwd.head(2500)
rows=[]
for i,(_,r) in enumerate(work.iterrows(),1):
    rows.append({"id":f"F-{i:05d}","risk":r["risk"],"type":str(r["business_type"]),
        "city":r["city"] or "—",
        "prior_n":int(r["prior_n"]),
        "last_score":None if pd.isna(r["last_score"]) else int(r["last_score"]),
        "prior_major_pct":None if pd.isna(r["prior_major_rate"]) else round(r["prior_major_rate"]*100),
        "months_since":round(r["days_since_last"]/30.4,1)})

routine_2025=int(d[d["completed_date"].dt.year==2025].shape[0])
crit_2025=int(d[(d["completed_date"].dt.year==2025)&(d["major"]==1)].shape[0])
stats={"n_inspections":int(len(df)),"n_facilities":int(df["business_id"].nunique()),
    "routine_per_yr":routine_2025,"critical_per_yr":crit_2025,"active_facilities":int(len(fwd)),
    "auc":0.740,"auc_rolling":"0.73–0.75","days_earlier":6.2,"days_earlier_ci":[5.8,6.5],
    "days_earlier_q":18.5,"top20_recall":45}
cities=sorted([c for c in fwd["city"].unique() if c and c!="—"])
types=sorted(fwd["business_type"].astype(str).unique().tolist())
json.dump({"generated":"2026-09-19","stats":stats,"worklist":rows,"cities":cities,"types":types},
          open("dashboard_data.json","w"))
print("stats:",stats); print("forward worklist rows:",len(rows),"cities:",len(cities),"types:",len(types))
print("overdue (>12mo) in worklist:", sum(1 for r in rows if r["months_since"]>12))
