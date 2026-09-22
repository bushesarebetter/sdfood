"""Pull the full San Diego County food-inspection dataset from sdfoodinfo.org's
public JSON API (same endpoint the official search app uses). Public-record data.
Robust: small pages, retries, checkpointing. Saves raw JSON + flat inspections CSV.

Access ethics: this is public-record data and the host serves no robots.txt (HTTP 404),
so nothing is crawler-disallowed -- but automated access can still run against a site's
terms of use. We identify honestly (no spoofed browser UA), keep pages small, and
rate-limit. For any production/pilot use, request the dataset officially from the county
rather than scraping; if this honest UA gets blocked, treat that as a 'don't scrape' signal."""
import requests, json, time, pathlib, pandas as pd

BASE="https://www.sdfoodinfo.org"
# Honest, identifying UA (add a real contact before running). The Referer/Origin headers
# below are what the AJAX endpoint requires to respond -- functional, not disguise.
UA="sdfood-inspection-research/1.0 (civic research; SD County public inspection records; contact: [add-your-email])"
PAGE=400
pathlib.Path("data").mkdir(exist_ok=True)

s=requests.Session(); s.headers.update({"User-Agent":UA})
s.get(f"{BASE}/restaurants/list_restaurants.html", timeout=60)
hdr={"X-Requested-With":"XMLHttpRequest","Referer":f"{BASE}/restaurants/list_restaurants.html",
     "Origin":BASE,"Accept":"application/json, text/javascript, */*; q=0.01",
     "Content-Type":"application/x-www-form-urlencoded; charset=UTF-8"}

def page(n):
    for attempt in range(5):
        try:
            r=s.post(f"{BASE}/restaurants/search.htm", headers=hdr, timeout=180,
                     data={"lat":32.7157,"lng":-117.1611,"miles":100,"page_count":PAGE,"page_number":n})
            r.raise_for_status(); return r.json()
        except Exception as e:
            print(f"    page {n} attempt {attempt+1} failed: {type(e).__name__}; retrying")
            time.sleep(4*(attempt+1))
    raise RuntimeError(f"page {n} failed after retries")

first=page(1); total=first["total_count"]
biz={b["business_id"]:b for b in first["result"]}
print(f"total_count={total}; page 1 -> {len(biz)}", flush=True)
n=2
while len(biz)<total:
    d=page(n); got=d.get("result") or []
    if not got: break
    for b in got: biz[b["business_id"]]=b
    print(f"  page {n}: +{len(got)}  unique {len(biz)}/{total}", flush=True)
    if n%5==0: json.dump(list(biz.values()), open("data/sd_businesses.json","w"))  # checkpoint
    n+=1; time.sleep(0.4)

biz=list(biz.values())
json.dump(biz, open("data/sd_businesses.json","w"))
print(f"saved data/sd_businesses.json: {len(biz)} businesses", flush=True)

rows=[]
for b in biz:
    for ins in (b.get("inspections") or []):
        vios=ins.get("violations") or []
        rows.append({"business_id":b["business_id"],"business_type":b.get("business_type"),
            "zip":str(b.get("zip") or "")[:5],"lat":b.get("lat"),"lng":b.get("long"),
            "opened_date":b.get("opened_date"),"inspection_id":ins.get("inspection_id"),
            "insp_type":ins.get("type"),"score":ins.get("score"),"grade":ins.get("grade"),
            "completed_date":ins.get("completed_date"),"n_violations":len(vios),
            "n_major":sum(1 for v in vios if str(v.get("major_violation","")).upper()=="Y")})
df=pd.DataFrame(rows); df.to_csv("data/sd_inspections.csv", index=False)
print(f"saved data/sd_inspections.csv: {len(df):,} inspections, {df['business_id'].nunique():,} businesses", flush=True)
print("date range:", df["completed_date"].min(), "->", df["completed_date"].max(), flush=True)
