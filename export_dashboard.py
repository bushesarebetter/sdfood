"""Export dashboard data. Two distinct things, kept honest:
  (1) STATS/EVIDENCE come from the proper hold-out validation (train<=2024, test 2025+).
  (2) The WORKLIST is FORWARD-LOOKING: a model trained on ALL data scores each currently
      active facility for its NEXT (not-yet-done) inspection, using its full history to date,
      ranked by risk weighted by how overdue it is vs its type's normal cadence.
Rows are DE-IDENTIFIED (type + banded history only; no city, no exact score) so the public
page can't be used to point at a specific named business. The named list runs internally."""
import pandas as pd, numpy as np, json, base64
from sklearn.preprocessing import OrdinalEncoder
from sklearn.ensemble import HistGradientBoostingClassifier

TODAY=pd.Timestamp("2026-09-18")
df=pd.read_csv("data/sd_inspections.csv",low_memory=False)
df["completed_date"]=pd.to_datetime(df["completed_date"],errors="coerce")
df["opened_date"]=pd.to_datetime(df["opened_date"],errors="coerce")
df["score"]=pd.to_numeric(df["score"],errors="coerce")
df=df.dropna(subset=["completed_date"]).sort_values(["business_id","completed_date"])
df["major"]=(df["n_major"]>0).astype(int)
df.loc[df["insp_type"].astype(str)!="Routine","score"]=np.nan  # 0 is a not-scored sentinel off-routine

# ---- per-inspection features (training format) ----
g=df.groupby("business_id",sort=False)
df["prior_n"]=g.cumcount()
df["days_since_last"]=(df["completed_date"]-g["completed_date"].shift(1)).dt.days
df["last_score"]=g["score"].transform(lambda s:s.shift().ffill())  # last real routine score
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
fwd["last_score"]=gg["score"].last()       # last real routine score (skips sentinel NaN)
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

# ---- DUE-DATE-AWARE priority: risk alone would rank a place done last month over one
# 11 months overdue. Weight risk by how far past its type's normal cadence it is. ----
rt=df[df["insp_type"].astype(str)=="Routine"].sort_values(["business_id","completed_date"])
rt_gap=rt.groupby("business_id")["completed_date"].diff().dt.days
type_interval=rt.assign(gap=rt_gap).groupby("business_type")["gap"].median()
med_interval=float(rt_gap.median())                       # overall fallback (~days between routines)
fwd["exp_interval"]=fwd["business_type"].map(type_interval).fillna(med_interval).clip(lower=120)
fwd["overdue_ratio"]=(fwd["days_since_last"]/fwd["exp_interval"]).round(2)
fwd["priority"]=fwd["risk"]*fwd["overdue_ratio"].clip(0.2,2.0)   # not-yet-due downweighted, overdue boosted

fwd=fwd.sort_values("priority",ascending=False)
work=fwd                                   # embed ALL active facilities, not just top 2500
def band_prior(n):                         # de-identify: bands, not exact counts
    return "1" if n<=1 else "2–4" if n<=4 else "5–9" if n<=9 else "10+"
def band_major(pct):
    return None if pct is None else "none" if pct==0 else "low" if pct<15 else "elevated" if pct<35 else "high"
rows=[]
for i,(_,r) in enumerate(work.iterrows(),1):
    pm=None if pd.isna(r["prior_major_rate"]) else round(r["prior_major_rate"]*100)
    rows.append({"id":f"F-{i:05d}","risk":r["risk"],"type":str(r["business_type"]),
        "prior_band":band_prior(int(r["prior_n"])),
        "major_band":band_major(pm),
        "overdue":bool(r["overdue_ratio"]>=1.0),
        "months_since":round(r["days_since_last"]/30.4,1)})

routine_2025=int(d[d["completed_date"].dt.year==2025].shape[0])
crit_2025=int(d[(d["completed_date"].dt.year==2025)&(d["major"]==1)].shape[0])
stats={"n_inspections":int(len(df)),"n_facilities":int(df["business_id"].nunique()),
    "routine_per_yr":routine_2025,"critical_per_yr":crit_2025,"active_facilities":int(len(fwd)),
    "n_overdue":int(sum(1 for r in rows if r["overdue"])),
    "auc":0.745,"auc_rolling":"0.73–0.76","days_earlier":6.3,"days_earlier_ci":[5.9,6.6],
    "days_earlier_q":18.9,"top20_recall":47}
types=sorted(fwd["business_type"].astype(str).unique().tolist())
payload={"generated":"2026-09-21","stats":stats,"worklist":rows,"types":types}
json.dump(payload, open("dashboard_data.json","w"))

# ---- build self-contained dashboard.html: inject data at /*__DATA__*/ and embed the PNGs ----
tpl=open("dashboard.template.html",encoding="utf-8").read()
pre,mark,post=tpl.partition("/*__DATA__*/")     # default literal runs from here to the first ';'
_,_,rest=post.partition(";")
data_js=json.dumps(payload)                     # ascii-safe; no ';' in any value
html=pre+mark+" "+data_js+";"+rest
def datauri(fn): return "data:image/png;base64,"+base64.b64encode(open(fn,"rb").read()).decode()
for ph,fn in [("IMG_GAINS","food_gains.png"),("IMG_DAYS","food_days_earlier.png"),("IMG_FAIRNESS","food_fairness.png")]:
    html=html.replace(ph,datauri(fn))
open("dashboard.html","w",encoding="utf-8").write(html)

print("stats:",stats); print("forward worklist rows:",len(rows),"types:",len(types))
print("overdue (past type cadence) in worklist:", stats["n_overdue"])
print("wrote dashboard.html")
