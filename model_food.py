"""Predict, at a routine food inspection, whether it will find a MAJOR (critical)
violation -- using only info available beforehand. Honest forward-in-time test,
compared against the facility's own prior-violation-rate (the baseline that matters).

The point: if inspectors worked in the model's risk order, would they find critical
violations EARLIER than the routine calendar? (cumulative gains)."""
import pandas as pd, numpy as np
from sklearn.preprocessing import OrdinalEncoder
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, average_precision_score
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

df = pd.read_csv("data/sd_inspections.csv", low_memory=False)
df["completed_date"] = pd.to_datetime(df["completed_date"], errors="coerce")
df["opened_date"]    = pd.to_datetime(df["opened_date"], errors="coerce")
df["score"] = pd.to_numeric(df["score"], errors="coerce")
df = df.dropna(subset=["completed_date"]).sort_values(["business_id","completed_date"])
df["major"] = (df["n_major"] > 0).astype(int)
# score is a "not-scored" sentinel (0) on 100% of non-routine inspections; null it so
# score-based priors reflect only real routine scores, not re-inspection zeros.
df.loc[df["insp_type"].astype(str) != "Routine", "score"] = np.nan
print(f"inspections: {len(df):,}  businesses: {df['business_id'].nunique():,}")
print("date range:", df['completed_date'].min().date(), "->", df['completed_date'].max().date())
print("overall major-violation rate:", f"{df['major'].mean()*100:.1f}%")

# ---- leak-free prior-history features (strictly before current inspection) ----
g = df.groupby("business_id", sort=False)
df["prior_n"]          = g.cumcount()
df["days_since_last"]  = (df["completed_date"] - g["completed_date"].shift(1)).dt.days
df["last_score"]       = g["score"].transform(lambda s: s.shift().ffill())  # last real routine score
df["last_major"]       = (g["n_major"].shift(1) > 0).astype("float")
df["prior_major_rate"] = g["major"].transform(lambda s: s.shift().expanding().mean())
df["prior_mean_score"] = g["score"].transform(lambda s: s.shift().expanding().mean())
df["prior_mean_viol"]  = g["n_violations"].transform(lambda s: s.shift().expanding().mean())
df["facility_age_yrs"] = (df["completed_date"] - df["opened_date"]).dt.days/365.25
df["month"] = df["completed_date"].dt.month

# model only ROUTINE inspections (the ones the county schedules and could reorder)
d = df[df["insp_type"].astype(str).str.contains("Routine", case=False, na=False)].copy()
print(f"routine inspections modeled: {len(d):,}  major rate: {d['major'].mean()*100:.1f}%")

cat = ["business_type","zip"]
num = ["prior_n","days_since_last","last_score","last_major","prior_major_rate",
       "prior_mean_score","prior_mean_viol","facility_age_yrs","month"]
for c in cat:
    d[c] = d[c].astype("string").fillna("NA")
    if d[c].nunique() > 250:
        keep = d[c].value_counts().head(240).index
        d[c] = d[c].where(d[c].isin(keep), "OTHER")

# forward-in-time split
tr = d["completed_date"] <= "2024-12-31"
te = d["completed_date"] >  "2024-12-31"
print(f"train (<=2024): {tr.sum():,}   test (2025+): {te.sum():,}   test major rate: {d.loc[te,'major'].mean()*100:.1f}%")

enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-1)
X = d[cat+num].copy(); enc.fit(X[cat][tr.values]); X[cat] = enc.transform(X[cat])
cat_idx = [X.columns.get_loc(c) for c in cat]
y = d["major"].values

clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=48,
        categorical_features=cat_idx, l2_regularization=1.0,
        early_stopping=True, n_iter_no_change=20, random_state=0)
clf.fit(X[tr.values], y[tr.values])
p = clf.predict_proba(X[te.values])[:,1]
yte = y[te.values]

# baseline that matters: the facility's own prior major-violation rate
base = d.loc[te,"prior_major_rate"].fillna(d.loc[tr,"major"].mean()).values
auc_m, auc_b = roc_auc_score(yte,p), roc_auc_score(yte,base)
print(f"\n=== TEST (2025+, n={te.sum():,}) ===")
print(f"ROC-AUC  model={auc_m:.3f}   prior-rate baseline={auc_b:.3f}   random=0.500")
print(f"PR-AUC   model={average_precision_score(yte,p):.3f}   base_rate={yte.mean():.3f}")

k=int(0.20*len(yte)); order=np.argsort(-p)
top=order[:k]
print(f"top-20% by risk: precision={yte[top].mean():.2f}  recall_of_major={yte[top].sum()/yte.sum():.2f}  "
      f"lift={yte[top].mean()/yte.mean():.2f}x")

# cumulative gains
cum=np.cumsum(yte[order])/yte.sum(); frac=np.arange(1,len(yte)+1)/len(yte)
i=np.linspace(0,len(frac)-1,400).astype(int); i20=int(.2*len(frac))-1
fig,ax=plt.subplots(figsize=(7.6,5.2),dpi=150)
ax.plot(frac[i]*100,cum[i]*100,color="#1d6a97",lw=2.4,label="Model risk-ranking")
ax.plot([0,100],[0,100],ls="--",color="#9aa7b0",lw=1.4,label="Routine calendar (no targeting)")
ax.scatter([20],[cum[i20]*100],color="#c9741a",zorder=5,s=64)
ax.annotate(f"Inspect the 20% highest-risk first\n→ find {cum[i20]*100:.0f}% of all critical violations",
            (20,cum[i20]*100),xytext=(26,cum[i20]*100-24),fontsize=9.5,color="#333",
            arrowprops=dict(arrowstyle="->",color="#c9741a"))
ax.set_xlabel("% of routine inspections done, in model-risk order")
ax.set_ylabel("% of all critical violations found")
ax.set_title("Targeting food inspections by risk finds problems sooner\n"
             "San Diego County — forward test on 2025+ inspections",fontsize=12.5,fontweight="bold",loc="left")
ax.set_xlim(0,100);ax.set_ylim(0,100);ax.legend(frameon=False,fontsize=9.5,loc="lower right")
for sp in ["top","right"]:ax.spines[sp].set_visible(False)
ax.grid(color="#eee")
fig.text(0.01,0.01,"Source: sdfoodinfo.org (SD County DEH). Critical = major violation. Leak-free prior-history features.",fontsize=7,color="#777")
fig.tight_layout(rect=[0,0.03,1,1]);fig.savefig("food_gains.png",bbox_inches="tight")
print("saved food_gains.png")

# ---- reasoning checks: what drives it + fairness ----
from sklearn.inspection import permutation_importance
Xte=X[te.values]; idx=np.random.default_rng(0).choice(len(Xte),min(8000,len(Xte)),replace=False)
pi=permutation_importance(clf, Xte.iloc[idx], yte[idx], n_repeats=5, scoring="roc_auc", random_state=0)
imp=pd.Series(pi.importances_mean, index=X.columns).sort_values(ascending=False)
print("\n=== permutation importance (AUC drop) ===")
print(imp.round(4).to_string())

res=pd.DataFrame({"p":p,"y":yte,"type":d.loc[te,"business_type"].astype(str).values})
flagged=res.sort_values("p",ascending=False).head(int(0.2*len(res)))
print("\n=== fairness: is the flagged top-20% just one business type? ===")
comp=pd.DataFrame({"flagged_top20%":flagged["type"].value_counts(normalize=True),
                   "overall":res["type"].value_counts(normalize=True)}).fillna(0)
print((comp*100).round(1).head(8).to_string())
print("\n=== precision by business type (top-20% flagged) ===")
for t,gp in res.assign(flag=res.index.isin(flagged.index)).groupby("type"):
    if len(gp)>=300:
        fl=gp[gp["flag"]]
        if len(fl)>=30:
            print(f"  {t[:34]:34s} flagged {len(fl):4d}  precision {fl['y'].mean():.2f}  base {gp['y'].mean():.2f}")
