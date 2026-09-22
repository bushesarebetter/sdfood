"""Threshold trade-offs for the risk model. Two things:
  A) GLOBAL: precision / recall / lift as you move the flag cutoff (just reading the
     gains+PR curves at points). AUC is fixed; the threshold only trades precision <-> recall.
  B) EQUAL-OPPORTUNITY: per-income-group thresholds that EQUALIZE recall, vs one global
     threshold that doesn't. Shows the fix works -- and its cost: to equalize recall you
     must flag lower-income ZIPs MORE (lower their cutoff), i.e. group-conscious decisions
     using an income/ZIP proxy = disparate *treatment*, the legally harder tradeoff.
Out-of-fold (train<=2024, test 2025+), same pipeline as model_food.py / fairness_check.py."""
import pandas as pd, numpy as np, json, os
from sklearn.preprocessing import OrdinalEncoder
from sklearn.ensemble import HistGradientBoostingClassifier

df=pd.read_csv("data/sd_inspections.csv",low_memory=False)
df["completed_date"]=pd.to_datetime(df["completed_date"],errors="coerce")
df["opened_date"]=pd.to_datetime(df["opened_date"],errors="coerce")
df["score"]=pd.to_numeric(df["score"],errors="coerce")
df=df.dropna(subset=["completed_date"]).sort_values(["business_id","completed_date"])
df["major"]=(df["n_major"]>0).astype(int)
df.loc[df["insp_type"].astype(str)!="Routine","score"]=np.nan
g=df.groupby("business_id",sort=False)
df["prior_n"]=g.cumcount()
df["days_since_last"]=(df["completed_date"]-g["completed_date"].shift(1)).dt.days
df["last_score"]=g["score"].transform(lambda s:s.shift().ffill())
df["last_major"]=(g["n_major"].shift(1)>0).astype("float")
df["prior_major_rate"]=g["major"].transform(lambda s:s.shift().expanding().mean())
df["prior_mean_score"]=g["score"].transform(lambda s:s.shift().expanding().mean())
df["prior_mean_viol"]=g["n_violations"].transform(lambda s:s.shift().expanding().mean())
df["facility_age_yrs"]=(df["completed_date"]-df["opened_date"]).dt.days/365.25
df["month"]=df["completed_date"].dt.month
d=df[df["insp_type"].astype(str)=="Routine"].copy()
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
p=clf.predict_proba(X[te])[:,1]; yt=y[te]; base=yt.mean()

def pr_at(pv,yv,flag_rate):
    thr=np.quantile(pv,1-flag_rate); f=pv>=thr
    rec=yv[f].sum()/max(yv.sum(),1); prec=yv[f].mean() if f.sum() else 0.0
    return thr,f.mean(),prec,rec

print(f"test n={len(yt):,}  base rate={base:.3f}\n")
print("=== A) GLOBAL threshold: one knob, precision <-> recall (AUC is fixed) ===")
print(f"{'flag %':>7} {'precision':>10} {'recall':>8} {'lift':>6}")
for q in [0.10,0.20,0.30,0.40,0.50]:
    _,fr,prec,rec=pr_at(p,yt,q)
    print(f"{fr*100:6.0f}% {prec:10.2f} {rec:8.2f} {prec/base:6.2f}x")

# ---- B) per-group equal-opportunity vs one global threshold ----
inc=json.load(open("acs_cache.json")).get("inc",{}) if os.path.exists("acs_cache.json") else {}
t=pd.DataFrame({"p":p,"y":yt,"zip5":d.loc[te,"zip5"].values})
t["income"]=t["zip5"].map(inc)
t=t.dropna(subset=["income"])
t["grp"]=pd.qcut(t["income"],4,labels=["Q1 low","Q2","Q3","Q4 high"])
gthr=np.quantile(t["p"],0.80)                       # status-quo: one global top-20% cut
TARGET=0.55                                         # equalize everyone to ~best-group recall
print(f"\n=== B) recall by income group: ONE global cut (top 20%) vs PER-GROUP equal-opportunity ===")
print(f"(equal-opp targets recall={TARGET:.0%} in every group)")
print(f"{'group':8} {'global flag%':>12} {'global recall':>14}   |{'eq-opp flag%':>13} {'eq-opp recall':>14}")
tot_g=[]; tot_e=[]
for grp,gp in t.groupby("grp",observed=True):
    crit=gp[gp["y"]==1]
    g_flag=(gp["p"]>=gthr).mean(); g_rec=(crit["p"]>=gthr).mean()
    ethr=np.quantile(crit["p"],1-TARGET)            # per-group cut hitting TARGET recall
    e_flag=(gp["p"]>=ethr).mean(); e_rec=(crit["p"]>=ethr).mean()
    tot_g.append(g_flag*len(gp)); tot_e.append(e_flag*len(gp))
    print(f"{grp:8} {g_flag*100:11.1f}% {g_rec*100:13.1f}%   |{e_flag*100:12.1f}% {e_rec*100:13.1f}%")
    assert abs(e_rec-TARGET)<0.06, "per-group threshold missed target recall"
print(f"{'TOTAL':8} {sum(tot_g)/len(t)*100:11.1f}% {'(unequal)':>13}   |{sum(tot_e)/len(t)*100:12.1f}% {'(equalized)':>14}")
print("\nRead: equal-opp flattens recall across groups, but note the eq-opp flag% is HIGHER for")
print("lower-income groups -- that is the disparate-*treatment* cost of using income to set cutoffs,")
print("and it also spends more total inspection capacity. Global cut is simpler but leaves the gap.")
