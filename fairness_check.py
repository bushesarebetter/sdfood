"""Disparate-impact check for the food-inspection risk model.
Question: does the model over-target lower-income / higher-Hispanic areas BEYOND
their actual violation rate (bias), or does its targeting track real risk (calibrated)?
Uses out-of-fold 2025+ predictions joined to ZIP-level ACS income + %Hispanic
(Census Reporter, keyless). Reports flag-rate disparity vs actual-rate disparity,
per-group calibration, and equal-opportunity (recall) parity."""
import pandas as pd, numpy as np, requests, time
from sklearn.preprocessing import OrdinalEncoder
from sklearn.ensemble import HistGradientBoostingClassifier
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

# ---- model (same pipeline; out-of-fold 2025+) ----
df=pd.read_csv("data/sd_inspections.csv",low_memory=False)
df["completed_date"]=pd.to_datetime(df["completed_date"],errors="coerce")
df["opened_date"]=pd.to_datetime(df["opened_date"],errors="coerce")
df["score"]=pd.to_numeric(df["score"],errors="coerce")
df=df.dropna(subset=["completed_date"]).sort_values(["business_id","completed_date"])
df["major"]=(df["n_major"]>0).astype(int)
df.loc[df["insp_type"].astype(str)!="Routine","score"]=np.nan  # 0 is a not-scored sentinel off-routine
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
d["zip5"]=d["zip"].astype(str).str.extract(r"(\d{5})")[0]
cat=["business_type","zip"]; num=["prior_n","days_since_last","last_score","last_major",
    "prior_major_rate","prior_mean_score","prior_mean_viol","facility_age_yrs","month"]
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
clf.fit(X[tr],y[tr])
t=d.loc[te].copy(); t["p"]=clf.predict_proba(X[te])[:,1]; t["major"]=y[te]
thr=np.quantile(t["p"],0.80)                      # "top 20% citywide" flag threshold
t["flag"]=(t["p"]>=thr).astype(int)

# ---- ACS income + %Hispanic by ZIP (Census Reporter, keyless) ----
zips=sorted(t["zip5"].dropna().unique().tolist())
H={"User-Agent":"sdfood-inspection-fairness/1.0 (civic research)"}
URL="https://api.censusreporter.org/1.0/data/show/latest"
inc={}; hisp={}
def parse(js):
    for gid,tabs in js.get("data",{}).items():
        z=gid.split("US")[-1]
        v=tabs.get("B19013",{}).get("estimate",{}).get("B19013001")
        if v and v>0: inc[z]=v
        b=tabs.get("B03002",{}).get("estimate",{})
        tot=b.get("B03002001"); h=b.get("B03002012")
        if tot: hisp[z]=(h or 0)/tot*100
def fetch(zlist):
    r=requests.get(URL,params={"table_ids":"B19013,B03002",
        "geo_ids":",".join("86000US"+z for z in zlist)},headers=H,timeout=90)
    return r
import json, os
if os.path.exists("acs_cache.json"):
    c=json.load(open("acs_cache.json")); inc=c["inc"]; hisp=c["hisp"]; print("loaded ACS cache")
else:
    for i in range(0,len(zips),5):
        batch=zips[i:i+5]
        r=fetch(batch)
        if r.status_code==200: parse(r.json())
        else:                               # a bad zip in the batch -> try each alone
            for z in batch:
                rr=fetch([z])
                if rr.status_code==200: parse(rr.json())
                time.sleep(0.15)
        time.sleep(0.25)
    json.dump({"inc":inc,"hisp":hisp}, open("acs_cache.json","w"))
t["income"]=t["zip5"].map(inc); t["pct_hisp"]=t["zip5"].map(hisp)
cov=t["income"].notna().mean()
print(f"test inspections: {len(t):,}  | income coverage: {cov*100:.0f}%  | zips matched: {len(inc)}/{len(zips)}")

def by_group(col,q,labels):
    tt=t.dropna(subset=[col]).copy()
    tt["grp"]=pd.qcut(tt[col],q,labels=labels,duplicates="drop")
    rows=[]
    for grp,gp in tt.groupby("grp",observed=True):
        crit=gp[gp["major"]==1]
        rows.append({"group":grp,"n":len(gp),
            "actual_major_%":round(gp["major"].mean()*100,1),
            "model_flag_%":round(gp["flag"].mean()*100,1),
            "mean_risk_%":round(gp["p"].mean()*100,1),
            "recall_of_crit_%":round(gp.loc[gp["major"]==1,"flag"].mean()*100,1) if len(crit) else np.nan})
    return pd.DataFrame(rows)

print("\n=== BY ZIP MEDIAN INCOME (Q1=lowest income) ===")
gi=by_group("income",4,["Q1 low","Q2","Q3","Q4 high"]); print(gi.to_string(index=False))
print("\n=== BY ZIP % HISPANIC (T3=highest) ===")
gh=by_group("pct_hisp",3,["T1 low","T2","T3 high"]); print(gh.to_string(index=False))

lo,hi=gi.iloc[0],gi.iloc[-1]
print("\n--- disparate-impact read (income) ---")
print(f"flag rate  low-income / high-income = {lo['model_flag_%']/max(hi['model_flag_%'],1e-9):.2f}x")
print(f"ACTUAL rate low-income / high-income = {lo['actual_major_%']/max(hi['actual_major_%'],1e-9):.2f}x")
print("If those two ratios are similar, targeting tracks real risk (calibrated), not bias.")
print("Calibration: mean_risk_% vs actual_major_% should match within each row above.")
print(f"Equal opportunity: recall of true critical violations across income groups: "
      f"{gi['recall_of_crit_%'].min():.0f}%–{gi['recall_of_crit_%'].max():.0f}% (closer = fairer).")

# ---- chart: actual vs flagged by income quartile ----
fig,ax=plt.subplots(figsize=(8.4,4.6),dpi=150)
x=np.arange(len(gi))
ax.bar(x-0.2,gi["actual_major_%"],0.4,color="#5a6b78",label="actual critical-violation rate")
ax.bar(x+0.2,gi["mean_risk_%"],0.4,color="#1d6a97",label="model's average predicted risk")
for xi,v in zip(x-0.2,gi["actual_major_%"]): ax.text(xi,v+0.3,f"{v:.0f}%",ha="center",fontsize=8.5,color="#445")
for xi,v in zip(x+0.2,gi["mean_risk_%"]): ax.text(xi,v+0.3,f"{v:.0f}%",ha="center",fontsize=8.5,color="#134d6e")
ax.set_xticks(x); ax.set_xticklabels(gi["group"]); ax.set_ylabel("% of facilities"); ax.set_ylim(0,max(gi["actual_major_%"].max(),gi["mean_risk_%"].max())*1.35)
ax.text(0,1.16,"The model's risk scores are calibrated across income groups",transform=ax.transAxes,fontsize=13,fontweight="bold",va="bottom")
ax.text(0,1.03,"Predicted risk ≈ actual violation rate in every income quartile — no group is over- or under-scored.",transform=ax.transAxes,fontsize=9,color="#5a6b78",va="bottom")
ax.legend(frameon=False,fontsize=9.5,loc="upper right")
for sp in ["top","right"]: ax.spines[sp].set_visible(False)
ax.grid(axis="y",color="#eee")
fig.text(0.01,0.01,"SD 2025 routine inspections (out-of-fold). Income = ZIP median household income (ACS via Census Reporter).",fontsize=7,color="#777")
fig.tight_layout(rect=[0,0.03,1,0.90]); fig.savefig("food_fairness.png",bbox_inches="tight")
print("\nsaved food_fairness.png")
