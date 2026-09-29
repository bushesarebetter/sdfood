"""Pull the full San Diego County food-inspection dataset from sdfoodinfo.org's
public JSON API (same endpoint the official search app uses). Public-record data.
Robust: small pages, retries, checkpointing. Saves raw JSON + flat inspections CSV.

Access ethics: this is public-record data and the host serves no robots.txt (HTTP 404),
so nothing is crawler-disallowed -- but automated access can still run against a site's
terms of use. We identify honestly (no spoofed browser UA), keep pages small, and
rate-limit. For any production/pilot use, request the dataset officially from the county
rather than scraping; if this honest UA gets blocked, treat that as a 'don't scrape' signal.

    SDFOOD_CONTACT=you@example.org python fetch_sdfood.py            # a fresh pull (~42 pages, about an hour)
    SDFOOD_CONTACT=you@example.org python fetch_sdfood.py --resume   # continue an interrupted pull
    python fetch_sdfood.py --csv-only                                # rebuild the CSV from the saved pull

The last complete pull is never touched while a new one runs. Pages are checkpointed to
data/sd_businesses.partial.json (and data/pull_meta.partial.json); only a complete pull replaces
data/sd_businesses.json and data/pull_meta.json, and each one is kept as a dated, gzipped copy in
data/pulls/ (the last KEEP_PULLS), with its sha256 recorded in pull_meta.json.

A refusal is kept on record in data/PULL_REFUSED.json, and no pull runs while that file exists (nor
while a partial pull's meta, or a set-aside copy of one, records a refusal: it is copied into the file
first). Remove the file only with the County's written OK (docs/RUNBOOK.md, "The pull was refused").
When the County asks in writing to stop, create it by hand (e.g. {"detail": "written request"}).

Exit codes: 0 a complete pull; 1 a crash (--resume is safe); 3 the server refused (401/403/429, or
an HTML page where JSON belongs), now or earlier: stop for good, do not retry or work around it, see
docs/RUNBOOK.md; 4 the pages ran out before every business appeared (the partial is kept)."""
import gzip, hashlib, json, os, pathlib, shutil, sys, time

DATA = pathlib.Path("data")
RAW, PULL = DATA / "sd_businesses.json", DATA / "pull_meta.json"
WORK, WORK_META = DATA / "sd_businesses.partial.json", DATA / "pull_meta.partial.json"
REFUSED = DATA / "PULL_REFUSED.json"
BACKUPS = DATA / "pulls"
KEEP_PULLS = 8
PAGE = 400
EXIT_REFUSED, EXIT_INCOMPLETE = 3, 4
BASE = "https://www.sdfoodinfo.org"


def save(obj, path):
    """Atomic: a kill mid-write never corrupts the checkpoint."""
    path = pathlib.Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as fh:
        json.dump(obj, fh)
    os.replace(tmp, path)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(biz, out=DATA / "sd_inspections.csv"):
    """One row per inspection, with the data rules export_site.py applies (and tests): "No Access"
    and "Incomplete" are not inspections, nor is a "Self Closed" or "Status Verification" record that
    cites nothing; a routine within 30 days of a B/C or a closure is the County's re-grade or
    reopening ("Follow-up"), never a routine label; 0 is "not scored"; same-day records of one type
    are one inspection. insp_type is the pipeline's reading ("Follow-up"; a complaint visit keeps the
    County's own type, "Site Investigation" or "Environmental"; a kept status check is "Status
    Verification", which the research features do not read); county_type is the County's type text
    for every record in the row. closure_order marks every visit that ended in a closure (a County
    order, a Self Closed record with a major, or a closure read from a later "Approved to Reopen",
    closure_inferred). Every research script reads this file, so the site and the research share one
    definition of an inspection."""
    import pandas as pd
    from export_site import load_places, Stats
    kind = {"routine": "Routine", "reinspection": "Re-inspection", "followup": "Follow-up", "complaint": "Site Investigation",
            "status_check": "Status Verification"}
    st = Stats(); rows = []
    for b, p in zip(biz, load_places(biz, st)):
        for v in p["visits"]:
            types = list(dict.fromkeys(r.get("county_type") or "" for r in v["_records"]))
            insp_type = (types[0] or kind["complaint"]) if v["type"] == "complaint" else kind[v["type"]]
            rows.append({"business_id": b["business_id"], "business_type": b.get("business_type"),
                         "zip": str(b.get("zip") or "")[:5], "lat": b.get("lat"), "lng": b.get("long"),
                         "opened_date": b.get("opened_date"), "inspection_id": v["_id"], "insp_type": insp_type,
                         "county_type": "; ".join(t for t in types if t),
                         "status": v["status"], "score": v["score"], "grade": v["grade"], "completed_date": v["date"],
                         "n_violations": v["major"] + v["minor"] + v["grp"], "n_major": v["major"], "n_minor": v["minor"],
                         "n_grp": v["grp"], "closure": v["closure"], "closure_order": v["closure_order"],
                         "closure_inferred": bool(v.get("closure_inferred"))})
    df = pd.DataFrame(rows); df.to_csv(out, index=False)
    print(f"saved {out}: {len(df):,} inspections, {df['business_id'].nunique():,} businesses "
          f"(dropped {sum(st.dropped.values()):,} non-inspections, {st.followups:,} re-grade/reopening visits "
          f"retyped, {st.merged:,} same-day records merged)", flush=True)
    print("date range:", df["completed_date"].min(), "->", df["completed_date"].max(), flush=True)


class Refused(Exception):
    """The server said no. Never retried, never worked around."""

    def __init__(self, status, page, detail=""):
        super().__init__(f"the server answered {status} on page {page}{f' ({detail})' if detail else ''}")
        self.status, self.page, self.detail = status, page, detail


def refusal(status, content_type, body_start):
    """Why a response is a refusal, or None. A 200 carrying an HTML page where the API's JSON belongs
    is a block page, not a transient error, and counts as a refusal too."""
    if status in (401, 403, 429):
        return str(status)
    if status == 200 and ("html" in (content_type or "").lower() or (body_start or "").lstrip()[:1] == "<"):
        return "an HTML page instead of JSON"
    return None


def make_client(contact):
    """(session, page(n)): the identified session and a page fetcher with retries."""
    import requests
    # sdfoodinfo.org serves an incomplete TLS chain (its leaf is issued by GoDaddy's "TLS
    # Intermediate CA DV - R1v1", but it ships the older "Secure CA - G2" intermediate instead).
    # Browsers repair that by fetching the missing intermediate; certifi cannot. truststore
    # verifies against the OS trust store, which can -- verification stays on either way.
    try:
        import truststore; truststore.inject_into_ssl()
    except ImportError:
        print("note: `pip install truststore` if TLS verification fails (see comment above)", file=sys.stderr)
    s = requests.Session()
    s.headers.update({"User-Agent": f"sdfood-inspection-research/1.0 (civic research; SD County public inspection "
                                    f"records; contact: {contact})"})
    first = s.get(f"{BASE}/restaurants/list_restaurants.html", timeout=60)
    if first.status_code in (401, 403, 429):
        raise Refused(first.status_code, 0, "the search page")
    # The Referer/Origin headers are what the AJAX endpoint requires to respond: functional, not disguise.
    hdr = {"X-Requested-With": "XMLHttpRequest", "Referer": f"{BASE}/restaurants/list_restaurants.html",
           "Origin": BASE, "Accept": "application/json, text/javascript, */*; q=0.01",
           "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}

    def page(n):
        for attempt in range(5):
            try:
                r = s.post(f"{BASE}/restaurants/search.htm", headers=hdr, timeout=180,
                           data={"lat": 32.7157, "lng": -117.1611, "miles": 100, "page_count": PAGE, "page_number": n})
                why = refusal(r.status_code, r.headers.get("Content-Type"), r.text[:200])
                if why:
                    raise Refused(r.status_code, n, why)
                r.raise_for_status()
                return r.json()
            except Refused:
                raise
            except Exception as e:
                print(f"    page {n} attempt {attempt + 1} failed: {type(e).__name__}; retrying", flush=True)
                time.sleep(4 * (attempt + 1))
        raise RuntimeError(f"page {n} failed after retries")
    return s, page


def _read_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError):
        return None


def refusal_on_record():
    """The refusal on record, or None: data/PULL_REFUSED.json, or else the refusal a partial pull's
    meta records (data/pull_meta.partial.json, or a copy set aside as pull_meta.partial.json.stale-*),
    which is then copied into PULL_REFUSED.json so that setting the partial aside cannot lose it. A
    PULL_REFUSED.json that does not parse still counts: its being there is the record."""
    if REFUSED.exists():
        rec = _read_json(REFUSED)
        return rec if isinstance(rec, dict) and rec else {"detail": "data/PULL_REFUSED.json is present"}
    for meta_path in sorted(DATA.glob(WORK_META.name + "*")):
        meta = _read_json(meta_path)
        if isinstance(meta, dict) and meta.get("refused"):
            rec = {**meta["refused"], "from": meta_path.name} if isinstance(meta["refused"], dict) else {"detail": str(meta["refused"])}
            record_refusal(rec)
            return rec
    return None


def record_refusal(rec):
    """Keep a refusal on record (data/PULL_REFUSED.json). The first one is kept: never overwritten."""
    if not REFUSED.exists():
        DATA.mkdir(parents=True, exist_ok=True)
        save(rec, REFUSED)
    return REFUSED


def load_checkpoint(resume):
    """(businesses by id, started) to continue from: the partial checkpoint; or, from a pull started
    before checkpoints had their own file, an incomplete data/sd_businesses.json."""
    if not resume:
        return {}, time.strftime("%Y-%m-%d")
    meta_path, raw_path = WORK_META, WORK
    if not WORK.exists() and RAW.exists() and PULL.exists() and not json.loads(PULL.read_text()).get("complete", True):
        meta_path, raw_path = PULL, RAW
    if not raw_path.exists():
        return {}, time.strftime("%Y-%m-%d")
    biz = {b["business_id"]: b for b in json.loads(raw_path.read_text())}
    started = json.loads(meta_path.read_text()).get("started") if meta_path.exists() else time.strftime("%Y-%m-%d")
    return biz, started or time.strftime("%Y-%m-%d")


def run_pull(page, biz, started, *, sleep=time.sleep, log=print):
    """Page until every business is in or a page comes back empty, checkpointing each page to WORK.
    Returns (businesses, total). Raises Refused, recording it in WORK_META first."""
    n = len(biz) // PAGE + 1 if biz else 1
    if biz:
        log(f"resuming: {len(biz)} businesses in checkpoint, from page {n}")
    total = None
    try:
        d = page(n)
        total = d["total_count"]
        while True:
            got = d.get("result") or []
            if not got:
                break
            for b in got:
                biz[b["business_id"]] = b
            log(f"  page {n}: +{len(got)}  unique {len(biz)}/{total}")
            save(list(biz.values()), WORK)
            save({"started": started, "total_count": total, "businesses": len(biz), "complete": False}, WORK_META)
            if len(biz) >= total:
                break
            n += 1
            sleep(0.4)
            d = page(n)
    except Refused as e:
        refused = {"status": e.status, "page": e.page, "detail": e.detail, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        save({"started": started, "total_count": total, "businesses": len(biz), "complete": False, "refused": refused},
             WORK_META)
        record_refusal(refused)
        raise
    return biz, total


def promote(businesses, started, total):
    """Replace the last complete pull with this one, keep a dated gzipped copy, drop older copies."""
    save(businesses, RAW)
    digest = sha256_file(RAW)
    finished = time.strftime("%Y-%m-%d")
    BACKUPS.mkdir(parents=True, exist_ok=True)
    gz = BACKUPS / f"sd_businesses.{finished}.json.gz"
    if gz.exists():
        gz = BACKUPS / f"sd_businesses.{finished}T{time.strftime('%H%M%S')}.json.gz"
    with open(RAW, "rb") as src, gzip.open(gz, "wb") as dst:
        shutil.copyfileobj(src, dst)
    meta = {"started": started, "finished": finished, "total_count": total, "businesses": len(businesses),
            "complete": True, "sha256": digest, "backup": gz.as_posix()}
    save(meta, PULL)
    stamp = gz.name.removeprefix("sd_businesses.").removesuffix(".json.gz")
    save(meta, BACKUPS / f"pull_meta.{stamp}.json")       # so export_site.py --pull <backup> can check it
    for old in sorted(BACKUPS.glob("sd_businesses.*.json.gz"))[:-KEEP_PULLS]:
        old.unlink()
        (BACKUPS / f"pull_meta.{old.name.removeprefix('sd_businesses.').removesuffix('.json.gz')}.json").unlink(missing_ok=True)
    for p in (WORK, WORK_META):
        p.unlink(missing_ok=True)
    return meta


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--csv-only" in argv:                         # rebuild the CSV from the saved pull, no network
        write_csv(json.loads(RAW.read_text()))
        return 0
    earlier = refusal_on_record()
    if earlier is not None:
        print(f"a refusal is on record ({json.dumps(earlier)}): not pulling. Remove {REFUSED} only with the County's written "
              "OK (docs/RUNBOOK.md, 'The pull was refused'); the last complete pull is untouched.", file=sys.stderr)
        return EXIT_REFUSED
    contact = os.environ.get("SDFOOD_CONTACT", "").strip()
    if not contact:
        sys.exit("Set SDFOOD_CONTACT to a real email before scraping (it goes in the User-Agent).")
    DATA.mkdir(exist_ok=True)
    biz, started = load_checkpoint("--resume" in argv)
    try:
        _, page = make_client(contact)
        biz, total = run_pull(page, biz, started, log=lambda m: print(m, flush=True))
    except Refused as e:
        record_refusal({"status": e.status, "page": e.page, "detail": e.detail, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
        print(f"stopped: {e}. Treat this as a 'do not scrape' signal: do not retry or change anything; the last "
              f"complete pull ({RAW}) is untouched. The refusal is kept in {REFUSED}, and no later run pulls while it "
              f"is there. Request the data from the County (docs/RUNBOOK.md).", file=sys.stderr)
        return EXIT_REFUSED
    if total is None or len(biz) < total:
        print(f"incomplete: {len(biz)} of {total} businesses appeared; the partial pull is in {WORK} and the last "
              f"complete pull ({RAW}) is untouched. Run again with --resume.", file=sys.stderr)
        return EXIT_INCOMPLETE
    meta = promote(list(biz.values()), started, total)
    print(f"saved {RAW}: {meta['businesses']} businesses (sha256 {meta['sha256'][:12]}), backup {meta['backup']}", flush=True)
    write_csv(json.loads(RAW.read_text()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
