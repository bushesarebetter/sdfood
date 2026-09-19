"""Scheduling simulation: if inspectors worked in model-risk order instead of the
calendar, how many DAYS EARLIER would critical violations be found? Plus a
rolling-origin backtest (AUC stability) and a bootstrap CI on days-earlier.

All predictions are out-of-fold (model never trains on the inspection it scores).
The reorder is zero-sum in inspection-days (same slots, same dates) — it just moves
the earliness onto the criticals and the lateness onto the clean facilities."""
import pandas as pd, numpy as np
from sklearn.preprocessing import OrdinalEncoder
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

df = pd.read_csv("data/sd_inspections.csv", low_memory=False)
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
        keep=d[c].value_counts().head(240).index
        d[c]=d[c].where(d[c].isin(keep),"OTHER")
y=d["major"].values

def train_predict(tr_mask, te_mask):
    enc=OrdinalEncoder(handle_unknown="use_encoded_value",unknown_value=-1,encoded_missing_value=-1)
    X=d[cat+num].copy(); enc.fit(X[cat][tr_mask]); X[cat]=enc.transform(X[cat])
    ci=[X.columns.get_loc(c) for c in cat]
    clf=HistGradientBoostingClassifier(max_iter=300,learning_rate=0.08,max_leaf_nodes=48,
        categorical_features=ci,l2_regularization=1.0,early_stopping=True,
        n_iter_no_change=20,random_state=0)
    clf.fit(X[tr_mask],y[tr_mask])
    return clf.predict_proba(X[te_mask])[:,1]

# ---- rolling-origin backtest: is AUC stable across cutoffs? ----
print("=== rolling-origin backtest (train<=cutoff, test next 6 months) ===")
for cut in ["2024-06-30","2024-12-31","2025-06-30"]:
    cd=pd.Timestamp(cut)
    tr=(d["completed_date"]<=cd).values
    te=((d["completed_date"]>cd)&(d["completed_date"]<=cd+pd.Timedelta(days=182))).values
    if te.sum()<500 or y[tr].sum()<50: continue
    p=train_predict(tr,te)
    print(f"  cutoff {cut}: test n={te.sum():>6,}  major_rate={y[te].mean()*100:4.1f}%  AUC={roc_auc_score(y[te],p):.3f}")

# ---- main out-of-fold predictions: train<=2024, test 2025+ ----
tr=(d["completed_date"]<="2024-12-31").values
te=(d["completed_date"]>"2024-12-31").values
p=train_predict(tr,te)
print(f"\nmain out-of-fold: test n={te.sum():,}  AUC={roc_auc_score(y[te],p):.3f}")

# ---- scheduling simulation on the out-of-fold 2025+ set ----
s=d.loc[te,["completed_date","major"]].copy(); s["p"]=p
print("\n=== DAYS EARLIER a critical violation is found under risk-order ===")
print("(reorder within each window; slots = the actual inspection dates)")
rng=np.random.default_rng(0); results=[]
for wlabel,wfreq in [("within-month","M"),("within-quarter","Q")]:
    s2=s.copy(); s2["win"]=s2["completed_date"].dt.to_period(wfreq)
    de_major=[]; de_clean=[]
    for _,gp in s2.groupby("win"):
        dates=np.sort(gp["completed_date"].values)
        order=np.argsort(-gp["p"].values)                 # highest risk first
        assigned=np.empty(len(gp),dtype="datetime64[ns]"); assigned[order]=dates
        de=(gp["completed_date"].values-assigned).astype("timedelta64[D]").astype(float)
        mj=gp["major"].values==1
        de_major.extend(de[mj].tolist()); de_clean.extend(de[~mj].tolist())
    de_major=np.array(de_major)
    boot=[rng.choice(de_major,len(de_major),replace=True).mean() for _ in range(2000)]
    lo,hi=np.percentile(boot,[2.5,97.5])
    print(f"  {wlabel}: criticals found {de_major.mean():+.1f} days earlier on avg "
          f"(95% CI {lo:+.1f} to {hi:+.1f}); {(de_major>0).mean()*100:.0f}% found earlier; "
          f"n={len(de_major)}. Clean facilities: {np.mean(de_clean):+.1f} days (the tradeoff).")
    results.append((wlabel, de_major.mean(), lo, hi, np.mean(de_clean)))

# ---- chart: days earlier (clean horizontal design) ----
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
labels=["Within the monthly cycle","Within the quarter"]
mean=[r[1] for r in results]; clean=[r[4] for r in results]
xerr=[[m-r[2] for m,r in zip(mean,results)],[r[3]-m for m,r in zip(mean,results)]]
ypos=[1,0]                              # monthly on top
fig,ax=plt.subplots(figsize=(8.2,3.7),dpi=150)
ax.barh(ypos,mean,height=0.46,color="#1d6a97",
        xerr=xerr,capsize=6,error_kw=dict(ecolor="#0d3a55",lw=1.6))
for yi,m in zip(ypos,mean):
    ax.text(m+0.45,yi,f"+{m:.1f} days earlier",va="center",ha="left",fontweight="bold",fontsize=12,color="#134d6e")
ax.set_yticks(ypos); ax.set_yticklabels(labels,fontsize=11.5)
ax.set_xlim(0,max(r[3] for r in results)*1.32); ax.set_ylim(-0.6,1.6)
ax.set_xlabel("average days a critical violation is found earlier",fontsize=10)
ax.text(0,1.24,"Risk-ordered inspections catch critical violations sooner",
        transform=ax.transAxes,fontsize=14,fontweight="bold",va="bottom")
ax.text(0,1.09,"San Diego 2025 routine inspections, out-of-fold · n=4,274 critical · 95% CI",
        transform=ax.transAxes,fontsize=9,color="#5a6b78",va="bottom")
for sp in ["top","right","left"]: ax.spines[sp].set_visible(False)
ax.tick_params(left=False); ax.grid(axis="x",color="#eef1f3")
ct=" · ".join(f"{abs(c):.1f} day{'s' if abs(c)>=1.5 else ''} ({l.split()[-1]})" for c,l in zip(clean,labels))
fig.text(0.012,0.015,f"The tradeoff: clean facilities wait only {ct} longer. Reordering is zero-sum in inspector-days.",
         fontsize=8.5,color="#7a8791")
fig.subplots_adjust(left=0.24,right=0.97,top=0.80,bottom=0.20)
fig.savefig("food_days_earlier.png",bbox_inches="tight")
print("saved food_days_earlier.png")
