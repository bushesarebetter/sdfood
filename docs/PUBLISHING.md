# Publishing: the staff API, and the gated public site

There are two ways the real data leaves this machine.

1. **The staff API** ([API.md](API.md)). This is internal, for City of San Diego staff. It is
   reached with a key and deployed from a privately built image, and it serves every listed place
   with its record, its points and band, and the monthly worklists.
2. **The public site** (`food-dashboard/`). It ships an invented sample. A real export reaches it
   only through `python export_site.py --publish`, which refuses unless every gate below passes,
   and stamps the export so that the site's own build refuses anything else.

**Real exports never enter git.** `/data/` is ignored. The committed `food-dashboard/public/data/`
must stay the sample, and a test checks this (`tests/test_export_site.py`). If a real export is
ever published, deploy the built site from a private build rather than committing the data.

## The staff API

- Build `data/site/` (`export_site.py`) and `data/worklists/` (`export_worklist.py`).
- Ship it with `python deploy_api.py`: it builds the image (`api/Dockerfile`), checks it, pushes it
  to a private registry and deploys it on Render, where `SDFOOD_API_KEYS` is set as a secret
  ([HOSTING.md](HOSTING.md)).
- Give each office its own key, so access can be withdrawn one office at a time.
- Refresh at least every two weeks. After 14 days without a refresh, every response carries
  `X-Data-Stale: true`, and `deploy_api.py` refuses to ship the expired export.

## The public site's gates

| gate | why |
|---|---|
| `docs/PUBLISH_APPROVAL.json`, filled in, naming **this run** and the **sha256 of the `data/site/facilities.geojson` that was read** | An approval covers one list, the one someone actually read. |
| The approval names a responsible adult (18 or older, not an author), a legal review, insurance, and a contact that answers owners within five business days | Publishing named businesses has legal consequences that someone must be prepared for. |
| `county_informed` records the date, the person, the method, what was shown and the County's response, at least 30 days before | The County hears about it before the public does. |
| The pull is complete and at most 14 days old | Places reinspected since would otherwise be misdescribed. |
| The published rule is within 0.01 AUC of the best model at both validation origins, and a fitted rule beats the average-score rule | The simplest rule that works is the one published. |
| A named band's interval clears the cost ratio, and it catches more than the baseline's same-size group | See the cost ratio, below. |
| A cost ratio C/B below 1 is co-signed by an independent reviewer | The people who built the list do not set their own threshold. |
| Every named band keeps at least 80% of its places across refits | A band that reshuffles is not a fact about the places in it. |
| No council district carries more than 1.25 times its share of wrongly named places, or 1.5 times the City's false-positive rate, and no district's interval reaches 2 | The cost of a named list should not fall on one part of the City. |
| Every named place was sent a notice at least 14 days earlier (`docs/notices/<run>.csv`: `facility_id,date_sent,method`) | Owners hear first, and can respond. |
| A frozen run was registered (`export_site.py --register`, with `docs/prospective/REGISTERED.json` committed) at least 90 days before, and held up on 300 or more later routine inspections (`--monitor`) | Only inspections made after a list was frozen are untouched evidence. |
| The site's contract check passes on the staged export, which carries `meta.publication` | The site can render every field, and its build accepts only a stamped export. |

### The cost ratio

C/B compares two things:
- **C:** the cost of naming a restaurant whose next routine inspection finds no major violation;
- **B:** the benefit of naming one whose next routine inspection does.

Naming a band is worth it only when its hit rate p satisfies p > C/(B+C), and the exporter requires
the **low end** of the band's 95% interval to clear that bar. `report.md` tabulates which bands
clear it at C/B = 0.25, 0.5, 1, 2 and 3.

### Owners: holds, notices and corrections

- **`docs/holds.json`** (`{"facility_ids": [...]}`) lists places under review. A place on hold is
  shown without a band or points, and is left out of a published export.
- **`docs/notices/<run>.csv`** logs the notice sent to each named place.
- **`docs/corrections.json`** (`[{date, facility_id, what, why}]`) is published on the site's
  corrections page.

## Monitoring

- Every run is archived once under `data/site/archive/<run>/`, with a manifest of hashes, and is
  never overwritten.
- `export_site.py --monitor` scores every archived run against the routine inspections made after
  it, and writes `monitor.md` and `monitor.json`.
- If the registered run's band falls below the cost bar on those inspections, take the names down.

## Taking the public site down

```bash
python food-dashboard/scripts/make_sample_export.py
```

Then redeploy. The site's build refuses a real export once its `expires` date has passed, and the
site shows search only after it.
