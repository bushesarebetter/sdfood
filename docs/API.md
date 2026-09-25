# San Diego Food Inspection API

The API is an internal service for City of San Diego staff. It covers every listed restaurant and
market in the City, and for each one gives:

- the County's inspection record;
- the published scoring rule's points and band;
- council-district summaries;
- monthly worklists for each district.

Interactive documentation, where you can try every endpoint, is served at `/docs`.

The data comes from the County of San Diego's published inspection results (SD Food Info) and
SANDAG's council districts. This is an independent student project by Chenhao Zhang and Ayan
Pendharkar, and is not affiliated with or endorsed by the County of San Diego.

## Access

Every data endpoint needs an `X-API-Key` header. The keys are set by whoever runs the service:

```bash
SDFOOD_API_KEYS=key-for-council-office,key-for-staff uvicorn api.main:app --port 8000
curl -H "X-API-Key: key-for-staff" "http://localhost:8000/v1/districts"
```

- `/health` and the documentation (`/docs`, `/redoc`, `/openapi.json`) are open, and carry no data.
- With no keys configured, data endpoints return 503, so a deployment without keys serves nothing.
- The service is meant to be reached by staff only. Do not link it from a public page.

## Endpoints

| endpoint | what it returns |
|---|---|
| `GET /health` | status, the export being served, and whether it is past its expiry date |
| `GET /v1/summary` | the export, the published rule (in words and item by item), and each band with its backtest rate and lift over other restaurants |
| `GET /v1/results` | headline results: band rates and lift; the research model's head start within a district's month, when `data/research_results.json` is present |
| `GET /v1/facilities` | the list, filtered and paged: `district`, `band`, `kind` (restaurant, limited, market), `flag` (major, closed, bc, repeat, or a theme such as temperature), `q` (words in the name or address), `sort` (band, points, name), `limit`, `offset` |
| `GET /v1/facilities/{facility_id}` | one place: every County inspection record with the County's own status text; what inspectors found, by theme; and, for a scored restaurant, its points worksheet |
| `GET /v1/export.csv` | the filtered list as CSV, stamped with the run and its expiry date |
| `GET /v1/districts` | every council district: places, places in each band, and places with a major violation, a closure for a health hazard, or a B or C in the last year |
| `GET /v1/districts/{n}` | one district's summary and its places in bands, highest points first |
| `GET /v1/worklists` | the months that have worklists |
| `GET /v1/worklists/{month}/districts/{n}` | one district's worklist for a month, in the rule's order; add `format=csv` for a spreadsheet |
| `POST /v1/admin/reload` | reload the data from disk after a refresh |

Examples:

```bash
K="X-API-Key: key-for-staff"; B=http://localhost:8000
curl -H "$K" "$B/v1/facilities?district=3&band=1&sort=points&limit=20"
curl -H "$K" "$B/v1/facilities?flag=major&flag=temperature&district=9"
curl -H "$K" "$B/v1/facilities/DEH2015-FFPP-006053"
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
- **Grade.** The grade is the one on the County's card in the window. When a re-grade replaced a B
  or C, `replaced` shows the grade it replaced.
- **Our reading.** A few fields are the pipeline's reading of the County's record, not the
  County's own words:
  - `type: "followup"` (a re-grade or reopening visit);
  - closure reasons;
  - themes;
  - flags;
  - points and bands.

  The County's own record is in each inspection's `status`, `score` and `grade`, and in each
  violation's `description` and `severity`.

## Running it

**Locally:**

```bash
pip install -r requirements.txt
SDFOOD_CONTACT=you@example.org python fetch_sdfood.py   # the data (about an hour; --resume if interrupted)
python export_site.py                                     # -> data/site/
python export_worklist.py                                 # -> data/worklists/<month>/
SDFOOD_API_KEYS=choose-a-key uvicorn api.main:app --port 8000
```

**Deployed, for staff.** The data is not in the public repository, by design. The image is built
where the data is, checked, pushed to a private registry and deployed on Render by one command,
`python deploy_api.py`. The one-time setup is in [HOSTING.md](HOSTING.md). The same image runs on
any container host, with `SDFOOD_API_KEYS` set as a secret; it listens on `PORT` (8000 when unset):

```bash
docker build --platform linux/amd64 -f api/Dockerfile -t sdfood-api .
docker run -p 8000:8000 -e SDFOOD_API_KEYS=... sdfood-api
```

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

**Refreshing, monthly.**
1. `fetch_sdfood.py --resume`
2. `export_site.py`
3. `export_worklist.py`
4. Rebuild the image, or copy the new `data/` and call `POST /v1/admin/reload`.

Tests: `python -m pytest tests/test_api.py`.
