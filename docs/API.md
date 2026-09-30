# San Diego Food Inspection API

The API is a key-protected service for City of San Diego staff (not deployed today; the staff site,
[STAFF_SITE.md](STAFF_SITE.md), is the service offered to the City, and no City office has access
yet). It covers every listed restaurant and market in San Diego County
(City places carry a council district; the rest have none), and for each one gives:

- the County's inspection record;
- the students' point rule's points and band (not a County grade or rating);
- council-district summaries;
- monthly worklists for each district.

Interactive documentation, where you can try every endpoint, is served at `/docs`.

The data comes from the County of San Diego's published inspection results (SD Food Info) and
SANDAG's council districts. By Chenhao Zhang and Ayan Pendharkar. Independent student project, not
affiliated with or endorsed by the City of San Diego or the County of San Diego.

## Access

Every data endpoint needs an `X-API-Key` header. The keys are set by whoever runs the service:

```bash
SDFOOD_API_LOCAL=1 SDFOOD_API_KEYS=key-for-council-office,key-for-staff uvicorn api.main:app --port 8000
curl -H "X-API-Key: key-for-staff" "http://localhost:8000/v1/districts"
```

- `/health` and the documentation (`/docs`, `/redoc`, `/openapi.json`) are open, and carry no data.
- With no keys configured, data endpoints return 503, so a deployment without keys serves nothing.
- A deployed image carries `api_release.json` in its data folder (written by `deploy_api.py`): the
  staff release's sunset date, whether the City's request and TRUST answer are on record
  (`access_approved`), and the ids on hold. Every data endpoint answers 503 ("This service is closed:
  ...") once the date in San Diego is past that sunset, when `access_approved` is not `true`, or when
  the file cannot be read. The key is checked first. Without the file it is closed too ("it has no
  release record"): an image built, or a data folder refreshed, any other way has passed none of
  `deploy_api.py`'s checks. Only a run on your own machine opens without it, and only when it says so
  (`SDFOOD_API_LOCAL=1`, and no `SDFOOD_BUILD`, which `deploy_api.py` stamps into every image).
- The service is meant to be reached by staff only. Do not link it from a public page.

## Endpoints

| endpoint | what it returns |
|---|---|
| `GET /health` | status, the export being served (`run`, `inspections_through`), whether it is past its expiry date (`stale`), the image's build, the release's `sunset`, and `closed`: why no data is served, or null |
| `GET /v1/summary` | the export, the students' point rule (in words and item by item), and each band with its backtest rate and lift over other restaurants |
| `GET /v1/results` | headline results: band rates and lift; the research model's head start within a district's month, when `data/research_results.json` is present |
| `GET /v1/facilities` | the list, filtered and paged: `district`, `band`, `kind` (restaurant, limited, market), `flag` (major, closed, bc, repeat, or a theme such as temperature), `q` (words in the name or address), `sort` (band, points, name), `limit`, `offset` |
| `GET /v1/facilities/{facility_id}` | one place: every County inspection record with the County's own status text, inspection type (`county_type`) and notes (`notes`); what inspectors found, by theme (`theme_counts`, counted before the list of items is cut at 150; `violations_total`); the grade, with `open_closure` when the place's last closure has no "Approved to Reopen" and no graded visit after it; and, for a scored restaurant, its points worksheet and estimate |
| `GET /v1/export.csv` | the filtered list as CSV, stamped with the run and its expiry date, and a column `about_band_points` on every row saying that the band and points are the students' point rule, a summary of the County's record, not a County grade or rating. `open_closure_date` is the date of a closure with no reopening on record (the grade is then the letter from before it); `last_visit_type` is in words, as the staff site's CSV writes it, our reading marked with the County's own type: "complaint or other field visit (our reading; County type: Site Investigation)" |
| `GET /v1/districts` | every council district: places, places in each band, and places with a major violation, a closure for a health hazard, or a B or C in the last year |
| `GET /v1/districts/{n}` | one district's summary and its places in bands, highest points first |
| `GET /v1/worklists` | the months that have worklists |
| `GET /v1/worklists/{month}/districts/{n}` | one district's worklist for a month, in the rule's order; add `format=csv` for a spreadsheet. First the places showing a pattern the County's Operator's Guide names (p. 8), by our counts in the 24 months before the list date (`escalation`: `major_2`, major violations at two or more routine inspections; `closures2`, two or more health closures; `repeat_item`, the same major item at two or more routine inspections; `lt90_2`, two or more routine scores below 90). The County sets no count or period, and meeting one is not a County finding. Then every other place on one scale (`rule_points`: the point rule's points, or 100 minus the mean routine score where it does not score a place), and places on hold last. Columns: `export_worklist.COLUMNS`, including `rule_mean`, `closures_24m`, `last_closure`, `reopened_on`, `posted_grade` and `no_reopen_on_record` (the date of the last closure when no "Approved to Reopen" and no graded visit follow it); a worklist written before `rule_mean` has `mean_routine_score_12m` instead |
| `POST /v1/admin/reload` | reload the data from disk, for a local run (a deployed image is refreshed only by `deploy_api.py`) |

Examples:

```bash
K="X-API-Key: key-for-staff"; B=http://localhost:8000
curl -H "$K" "$B/v1/facilities?district=3&band=1&sort=points&limit=20"
curl -H "$K" "$B/v1/facilities?flag=major&flag=temperature&district=9"
curl -H "$K" "$B/v1/facilities/SAMPLE-FFPP-00011"
curl -H "$K" "$B/v1/worklists/2026-10/districts/3?format=csv" -o district-3-october.csv
```

Once the data is past its expiry date (14 days after its last inspection), every response carries
the `X-Data-Stale: true` header and the list responses say `"stale": true`. Refresh the data then.

## What the fields mean

The full field list is in [FOOD_DATA_CONTRACT.md](FOOD_DATA_CONTRACT.md).

- **Band.** A band is a group of restaurants by the rule's points.
  - `/v1/summary` gives each band's rate: the share of the band that had a major violation at its
    next routine inspection, in the backtest.
  - It also gives the band's lift over other restaurants.
  - What the rule is and how it was tested: [MODEL_CARD.md](MODEL_CARD.md).
- **Points.** Only restaurants with two rated routine inspections in the last two years are
  scored. The worksheet shows each item as value × weight = points.
- **Grade.** The grade is the latest letter on the County's record in the window, from a routine
  inspection or a re-grade. When a re-grade replaced a B or C, `replaced` shows the grade it replaced.
  When the place's last closure has no "Approved to Reopen" and no graded visit after it,
  `open_closure` gives that closure (`date`, our reading of its `reason`, the County's `status` on the
  record that started it, and `later_ungraded`, the dates of ungraded records since), and the letter
  is the one from before it: the County posts no card while a place is closed.
- **Our reading.** A few fields are the pipeline's reading of the County's record, not the
  County's own words:
  - `type: "followup"` (a re-grade or reopening visit), `"complaint"` (the County's "Site
    Investigation" and "Environmental" records, read as complaint or other field visits) and
    `"status_check"` (a kept "Status Verification" record: shown, never scored);
  - closure reasons, `closure_inferred` (a closure read from a later "Approved to Reopen", which no
    closure order shows) and `reopen_without_closure` (an "Approved to Reopen" no closure could be
    placed before);
  - `grade.open_closure`;
  - themes;
  - flags, including the escalation facts, which are our counts, not County findings;
  - points and bands.

  The County's own record is in each inspection's `status`, `county_type`, `notes`, `score` and
  `grade`, and in each violation's `description` and `severity`.

## Running it

**Locally:**

```bash
pip install -r requirements.txt
SDFOOD_CONTACT=you@example.org python fetch_sdfood.py   # the data (about an hour; --resume if interrupted)
python export_site.py                                     # -> data/site/
python export_worklist.py                                 # -> data/worklists/<month>/
SDFOOD_API_LOCAL=1 SDFOOD_API_KEYS=choose-a-key uvicorn api.main:app --port 8000   # your own machine only
```

**Deployed, for staff.** The data is not in the public repository, by design. The image is built
where the data is, checked, pushed to a private registry and deployed on Render by one command,
`python deploy_api.py`. It refuses, before anything is pushed, without the staff release's approval
(an adult of record, a corrections contact, a sunset date) and without the City's request and TRUST
answer on record (`access_approved`): the API has no operator-only view, so every key holder would get
the named list. It also refuses while a place on hold still shows its points or band in the export or
in a worklist the image carries (`data/worklists/<month>/district-<n>.csv`; the frozen pilot copies
are not in the image). It writes `data/site/api_release.json` before the build, and removes it once
the build has read it. The one-time setup is in [HOSTING.md](HOSTING.md). `deploy_api.py` is the only
way to build and ship the image: `api/Dockerfile` names `data/site/api_release.json`, so a build
without it stops, and the API serves no data without it. On the host, set `SDFOOD_API_KEYS` as a
secret; the image listens on `PORT` (8000 when unset).

`/health` reports the export's run and the image's build (`SDFOOD_BUILD`, stamped by
`deploy_api.py`), so anyone can see which export and image a deployment serves.

Environment variables:

| variable | meaning |
|---|---|
| `SDFOOD_API_KEYS` | comma-separated keys; required |
| `SDFOOD_DATA_DIR` | the export folder (default `data/site`) |
| `SDFOOD_WORKLISTS_DIR` | the worklists folder (default `data/worklists`) |
| `SDFOOD_RESEARCH_FILE` | the research results file (default `data/research_results.json`) |
| `SDFOOD_CORS` | comma-separated origins allowed to call it from a browser (none by default) |
| `SDFOOD_API_LOCAL` | `1` on your own machine only: the service opens without a release record. Never set it on a host; an image `deploy_api.py` built ignores it |
| `SDFOOD_BUILD` | stamped into the image by `deploy_api.py`; `/health` reports it |

**Refreshing, every week.** The export expires 14 days after its last inspection, and `deploy_api.py`
refuses an expired one, so refresh with the staff site, at least every two weeks
([HOSTING.md](HOSTING.md), "Every refresh"):
1. `fetch_sdfood.py --resume`
2. `export_site.py`
3. `export_worklist.py`
4. `deploy_api.py`, which checks the release again, writes a new release record and ships a new image.
   Never copy data into a running service instead: it would skip every check.

Tests: `python -m pytest tests/test_api.py`.

## Security notes

- **Keys** are compared in constant time over every configured key, as bytes. Each request logs
  an 8-character hash of the key that made it, so access can be traced to an office without the
  key itself appearing in the log.
- **No rate limit** is built in. Put one in front of the service (the host's or a proxy's), at
  least for failed authentications.
- **Client addresses in the log** come from `X-Forwarded-For` (`--forwarded-allow-ips='*'` in the
  Dockerfile), which a caller can set. Treat them as a hint unless the host's proxy strips the
  header.
- **Docs:** `/docs`, `/redoc` and `/openapi.json` are open by default. They list the endpoints but no
  data, and Swagger UI loads from a CDN. Set `SDFOOD_API_DOCS=0` in production to turn them off.
- **Expiry:** after `meta.expires` the data is still served, marked `X-Data-Stale: true`.
  `deploy_api.py` refuses to ship an expired export; refresh before that.
- **Sunset and approval:** past the release's sunset (the date in San Diego), without
  `access_approved`, or without a release record at all, the image serves no data (503), as the staff
  site closes itself.
- **Holds** are applied when the image is built, not when a request is served: a place put on hold
  after the build keeps its points in the running image until `deploy_api.py` ships a new one
  ([RUNBOOK.md](RUNBOOK.md), "One place"). If that cannot happen the same day (the export cannot run,
  say), suspend the API service on Render until it has.
- **Worklists** are addressed only as `yyyy-mm` and districts 1 to 9, and the resolved file must
  lie inside the worklists folder.
- **CSV downloads** prefix text that a spreadsheet would run as a formula with `'`.
