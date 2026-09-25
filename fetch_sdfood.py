"""Pull the full San Diego County food-inspection dataset from sdfoodinfo.org's
public JSON API (same endpoint the official search app uses). Public-record data.
Robust: small pages, retries, checkpointing. Saves raw JSON + flat inspections CSV.

Access ethics: this is public-record data and the host serves no robots.txt (HTTP 404),
so nothing is crawler-disallowed -- but automated access can still run against a site's
terms of use. We identify honestly (no spoofed browser UA), keep pages small, and
rate-limit. For any production/pilot use, request the dataset officially from the county
rather than scraping; if this honest UA gets blocked, treat that as a 'don't scrape' signal."""
import requests, json, time, pathlib, os, sys, pandas as pd
# sdfoodinfo.org serves an incomplete TLS chain (its leaf is issued by GoDaddy's "TLS
# Intermediate CA DV - R1v1", but it ships the older "Secure CA - G2" intermediate instead).
# Browsers repair that by fetching the missing intermediate; certifi cannot. truststore
# verifies against the OS trust store, which can -- verification stays on either way.
try:
    import truststore; truststore.inject_into_ssl()
except ImportError:
    print("note: `pip install truststore` if TLS verification fails (see comment above)", file=sys.stderr)

RAW=pathlib.Path("data/sd_businesses.json"); PULL=pathlib.Path("data/pull_meta.json")
def save(obj, path):                       # atomic: a kill mid-write never corrupts the checkpoint
    tmp=path.with_suffix(path.suffix+".tmp"); json.dump(obj, open(tmp,"w")); os.replace(tmp, path)

def write_csv(biz):
    """One row per inspection, with the data rules export_site.py applies (and tests): "No Access",
    "Self Closed" and "Status Verification" are not inspections; a routine within 30 days of a B/C
    or a closure is the County's re-grade or reopening ("Follow-up"), never a routine label; 0 is
    "not scored"; same-day records of one type are one inspection. Every research script reads this
    file, so the site and the research share one definition of an inspection."""
    from export_site import load_places, Stats
    kind={"routine":"Routine","reinspection":"Re-inspection","followup":"Follow-up","complaint":"Site Investigation"}
    st=Stats(); rows=[]
    for b, p in zip(biz, load_places(biz, st)):
        for v in p["visits"]:
            rows.append({"business_id":b["business_id"],"business_type":b.get("business_type"),
                "zip":str(b.get("zip") or "")[:5],"lat":b.get("lat"),"lng":b.get("long"),
                "opened_date":b.get("opened_date"),"inspection_id":v["_id"],"insp_type":kind[v["type"]],
                "status":v["status"],"score":v["score"],"grade":v["grade"],"completed_date":v["date"],
                "n_violations":v["major"]+v["minor"]+v["grp"],"n_major":v["major"],"n_minor":v["minor"],
                "n_grp":v["grp"],"closure":v["closure"]})
    df=pd.DataFrame(rows); df.to_csv("data/sd_inspections.csv", index=False)
    print(f"saved data/sd_inspections.csv: {len(df):,} inspections, {df['business_id'].nunique():,} businesses "
          f"(dropped {sum(st.dropped.values()):,} non-inspections, {st.followups:,} re-grade/reopening visits "
          f"retyped, {st.merged:,} same-day records merged)", flush=True)
    print("date range:", df["completed_date"].min(), "->", df["completed_date"].max(), flush=True)

if "--csv-only" in sys.argv:              # rebuild the CSV from the saved pull, no network
    write_csv(json.load(open(RAW))); sys.exit(0)

BASE="https://www.sdfoodinfo.org"
# Honest, identifying UA. The contact comes from the environment so it is never committed:
#   SDFOOD_CONTACT=you@example.org python fetch_sdfood.py
# The Referer/Origin headers below are what the AJAX endpoint requires to respond --
# functional, not disguise. Interrupted? `python fetch_sdfood.py --resume` picks it back up.
CONTACT=os.environ.get("SDFOOD_CONTACT","").strip()
if not CONTACT:
    sys.exit("Set SDFOOD_CONTACT to a real email before scraping (it goes in the User-Agent).")
UA=f"sdfood-inspection-research/1.0 (civic research; SD County public inspection records; contact: {CONTACT})"
PAGE=400
pathlib.Path("data").mkdir(exist_ok=True)

s=requests.Session(); s.headers.update({"User-Agent":UA})
s.get(f"{BASE}/restaurants/list_restaurants.html", timeout=60)
hdr={"X-Requested-With":"XMLHttpRequest","Referer":f"{BASE}/restaurants/list_restaurants.html",
     "Origin":BASE,"Accept":"application/json, text/javascript, */*; q=0.01",
     "Content-Type":"application/x-www-form-urlencoded; charset=UTF-8"}

class Refused(Exception):
    pass

def page(n):
    for attempt in range(5):
        try:
            r=s.post(f"{BASE}/restaurants/search.htm", headers=hdr, timeout=180,
                     data={"lat":32.7157,"lng":-117.1611,"miles":100,"page_count":PAGE,"page_number":n})
            if r.status_code in (401, 403, 429):   # a refusal or a rate limit: stop for good, never work around it
                raise Refused(f"the server answered {r.status_code} on page {n}")
            r.raise_for_status(); return r.json()
        except Refused as e:
            sys.exit(f"stopped: {e}. Treat this as a 'do not scrape' signal; request the data from the County instead.")
        except Exception as e:
            print(f"    page {n} attempt {attempt+1} failed: {type(e).__name__}; retrying")
            time.sleep(4*(attempt+1))
    raise RuntimeError(f"page {n} failed after retries")


# --resume continues from the checkpoint (a pull is ~42 slow pages; losing it to a dropped
# session is expensive). Records merge by business_id, so a shifted page boundary between
# runs costs a duplicate, never a gap: paging continues until every id is in or a page is empty.
resume="--resume" in sys.argv and RAW.exists()
biz={b["business_id"]:b for b in json.load(open(RAW))} if resume else {}
started=json.load(open(PULL))["started"] if resume and PULL.exists() else time.strftime("%Y-%m-%d")
n=len(biz)//PAGE+1 if resume else 1
if resume: print(f"resuming: {len(biz)} businesses in checkpoint, from page {n}", flush=True)
d=page(n); total=d["total_count"]
while True:
    got=d.get("result") or []
    if not got: break
    for b in got: biz[b["business_id"]]=b
    print(f"  page {n}: +{len(got)}  unique {len(biz)}/{total}", flush=True)
    save(list(biz.values()), RAW); save({"started":started,"total_count":total,"complete":False}, PULL)
    if len(biz)>=total: break
    n+=1; time.sleep(0.4); d=page(n)
if len(biz)<total: print(f"warning: {total-len(biz)} of {total} businesses never appeared in a page", flush=True)

biz=list(biz.values())
save(biz, RAW)
save({"started":started,"finished":time.strftime("%Y-%m-%d"),"total_count":total,"businesses":len(biz),
      "complete":len(biz)>=total}, PULL)
print(f"saved data/sd_businesses.json: {len(biz)} businesses", flush=True)

write_csv(biz)
