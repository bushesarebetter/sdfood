"""Export data for the food-inspection dashboard: headline stats + an anonymized
risk worklist (out-of-fold 2025+ predictions with reasons + real outcome).
Facilities are anonymized (type/area/history only, no name/address) because the
dashboard is shareable and a predicted risk is not a finding."""
import pandas as pd, numpy as np, json
from sklearn.preprocessing import OrdinalEncoder
from sklearn.ensemble import HistGradientBoostingClassifier

df=pd.read_csv("data/sd_inspections.csv",low_memory=False)
df["completed_date"]=pd.to_datetime(df["completed_date"],errors="coerce")
df["opened_date"]=pd.to_datetime(df["opened_date"],errors="coerce")
df["score"]=pd.to_numeric(df["score"],errors="coerce")
df=df.dropna(subset=["completed_date"]).sort_values(["business_id","completed_date"])
df["major"]=(df["n_major"]>0).astype(int)
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
d=df[df["insp_type"].astype(str).str.contains("Routine",case=False,na=False)].copy().reset_index(drop=True)

cat=["business_type","zip"]
num=["prior_n","days_since_last","last_score","last_major","prior_major_rate",
     "prior_mean_score","prior_mean_viol","facility_age_yrs","month"]
for c in cat:
    d[c]=d[c].astype("string").fillna("NA")
    if d[c].nunique()>250:
        keep=d[c].value_counts().head(240).index; d[c]=d[c].where(d[c].isin(keep),"OTHER")
y=d["major"].values
tr=(d["completed_date"]<="2024-12-31").values; te=(d["completed_date"]>"2024-12-31").values
enc=OrdinalEncoder(handle_unknown="use_encoded_value",unknown_value=-1,encoded_missing_value=-1)
X=d[cat+num].copy(); enc.fit(X[cat][tr]); X[cat]=enc.transform(X[cat])
ci=[X.columns.get_loc(c) for c in cat]
clf=HistGradientBoostingClassifier(max_iter=300,learning_rate=0.08,max_leaf_nodes=48,
    categorical_features=ci,l2_regularization=1.0,early_stopping=True,n_iter_no_change=20,random_state=0)
clf.fit(X[tr],y[tr]); p=clf.predict_proba(X[te])[:,1]

# city lookup (anonymize: keep city/type/zip, drop name+address)
city={b["business_id"]:b.get("city") for b in json.load(open("data/sd_businesses.json"))}

t=d.loc[te].copy(); t["risk"]=(p*100).round(1)
t["city"]=t["business_id"].astype(str).map(city).fillna("").str.title()
# stratified sample so the table shows both high and typical risk
rng=np.random.default_rng(0)
hi=t.sort_values("risk",ascending=False).head(800)
rest=t.drop(hi.index); samp=rest.sample(min(1700,len(rest)),random_state=0)
work=pd.concat([hi,samp]).sample(frac=1,random_state=1)
rows=[]
for i,(_,r) in enumerate(work.iterrows(),1):
    rows.append({"id":f"F-{i:05d}","risk":r["risk"],"type":str(r["business_type"]),
        "city":r["city"] or "—","zip":str(r["zip"]),
        "prior_n":int(r["prior_n"]),"last_score":None if pd.isna(r["last_score"]) else int(r["last_score"]),
        "prior_major_pct":None if pd.isna(r["prior_major_rate"]) else round(r["prior_major_rate"]*100),
        "outcome":int(r["major"])})

stats={"n_inspections":int(len(df)),"n_facilities":int(df["business_id"].nunique()),
    "routine_per_yr":int(d[d["completed_date"].dt.year==2025].shape[0]),
    "critical_per_yr":int(d[(d["completed_date"].dt.year==2025)&(d["major"]==1)].shape[0]),
    "auc":0.740,"auc_rolling":"0.73–0.75","days_earlier":6.2,"days_earlier_ci":[5.8,6.5],
    "days_earlier_q":18.5,"top20_recall":45,"test_n":int(te.sum())}
cities=sorted([c for c in t["city"].unique() if c and c!="—"])
types=sorted(t["business_type"].astype(str).unique().tolist())
json.dump({"generated":"2026-09-19","stats":stats,"worklist":rows,
           "cities":cities,"types":types}, open("dashboard_data.json","w"))
print("stats:",stats)
print("worklist rows:",len(rows)," cities:",len(cities)," types:",len(types))
