# The food-safety site's export contract (version 3.1)

`food-dashboard/` shows City of San Diego restaurants and markets with the County's inspection
record. It has two modes, set by `meta.mode`:

- **`record`, the default publishable product.** The County's record for every listed place,
  with no model and no ordering: search, map, filters on record facts, each place's
  inspections, what inspectors found, and "If you eat here" drawn from the record.
- **`bands`, the gated product.** The same, plus a published point card that puts some places
  in bands, with each band's backtest hit rate. It reaches the site only if every gate in
  [PUBLISHING.md](PUBLISHING.md) passes. As of September 2026 none does, and
  [MODEL_CARD.md](MODEL_CARD.md) says why.

This document is the boundary between the pipeline (`export_site.py`) and the site.
`node food-dashboard/scripts/check-export.mjs <dir>` fails when an export breaks it, and
`tests/test_export_site.py` builds exports from an invented county and runs that check. The
invented sample (`food-dashboard/scripts/make_sample_export.py`) is in `bands` mode with
`sample: true`.

## Files

- **`data/meta.json`:** what the export is (below).
- **`data/facilities.geojson`:** the index. One Point feature per listed place, with only what
  the map, the list, the filters and the search need. It must stay small (well under 2 MB) so a
  phone can load it.
- **`data/place/<facility_id>.json`:** one file per listed place, with the full record. A place
  page loads only its own file.

## Sources and rules

- **Sources.** SD Food Info (pulled by `fetch_sdfood.py`) and SANDAG council districts. Nothing
  else: no reviews, no owner names, no phone numbers, no ZIP code or neighbourhood in any model.
- **Data rules** (`export_site.load_places`, tested, and shared with the research CSV):
  - **Not inspections:** "No Access", "Self Closed" and "Status Verification" visits are
    dropped.
  - **Follow-ups:** a routine within 30 days after a B, a C or a closure is a `followup`
    (re-grade or reopening).
  - **Merges:** same-day records of one type are one visit.
  - **Scores and grades:** 0 means "not scored"; grades are never derived.
  - **Severity tiers:** taken from the status text.
  - **Themes:** taken from the item text.
  - **Closures:** one per episode, with a reason. `reopened` records whether the County's
    "Approved to Reopen" visit ended it.
- **Listed places:** restaurants (`restaurant`), limited-preparation food service (`limited`) and
  markets with a deli or food processing (`market`) inside the City, visited in the last 18
  months, with a permit that has not expired.

## `facilities.geojson` (index)

| property | type | meaning |
|---|---|---|
| `facility_id` | string | the County's permit record id; the key for every link and file |
| `name`, `address` | string | as on the County's record |
| `facility_type` | `restaurant`, `limited`, `market` | the sample may use others |
| `council_district` | int | 1 to 9 |
| `last_visit` | `{ date, type }` | the most recent visit |
| `grade` | `{ grade, score, date, replaced }` or null | the grade on the County's card in the window: the latest letter from a routine or re-grade visit; `replaced` is `{ grade, score, date }` of the routine grade a re-grade replaced, else null |
| `flags` | array | record facts from the 12 months before the last visit: `major` (a major violation), `closed` (a health-hazard closure), `bc` (a B or C at a graded routine), `repeat` (two or more reinspections), and one theme key per theme with a major |
| `band`, `points` | `"1"`, `"2"` …, int | `bands` mode only; absent while `on_hold` |
| `on_hold` | bool | `bands` mode: the place is under review (`docs/holds.json`); the site shows its record and "Under review", no band or points |

There is **no `rank`, `percentile`, `oof_rank`, `score`, `shap_features` or `is_known_positive`**
in any export. The site sorts by band, then name (`bands`), or by name (`record`).

## `place/<facility_id>.json` (detail)

Everything in the index entry, plus:

- **`business_type`:** the County's own type, verbatim.
- **`inspections`:** oldest first, **one entry per County record**. Same-day records are not
  merged for display, so every grade shown is a single County letter:
  `{ date, status, type: "routine" | "reinspection" | "followup" | "complaint", score, grade,
  major, minor, grp, closed, closure: "health" | "permit" | "other" | null, reopened: bool | null }`.
  - `status` is the County's own text ("Complete", "Ordered Closed", "Approved to Reopen"), shown
    verbatim.
  - `type: "followup"`, `closure` and `reopened` are the pipeline's readings, and the site labels
    them "Our reading".
- **`violations`:** items cited in the 36 months before the last visit, majors first, at most 60:
  `{ date, visit, code, theme, severity: "major" | "minor" | "grp", description }`. `visit` is
  the visit type, and findings at complaint visits are included.
- **`score_card`** (`bands` mode only): every card item as
  `{ item, points, met, value }`, where `value` is the place's own number the item tests (its
  average routine score, a count). The points of met items sum to `points`.
- **`band_stability`** (`bands` mode only): the share of refits of the card in which the place
  stayed in its band.

Themes come from the County's item text (`export_site.THEME_RULES`; all 100 texts in the pull are
pinned in `tests/fixtures/item_themes.json`):

| theme | the County's items |
|---|---|
| `temperature` | holding temperatures, time as a public health control, cooling, cooking, reheating |
| `handwashing` | hands washed, hand sinks supplied and accessible, toilet and hand-sink facilities |
| `hygiene` | illness and exclusion, discharges, eating or drinking at the line, personal cleanliness |
| `sanitizing` | food-contact surfaces, warewashing, wiping cloths |
| `supplier` | food from an approved source, shellstock tags, Gulf oyster rules |
| `condition` | food in good condition, safe and unadulterated; no returned or re-served food |
| `process` | "Compliance with:" variance, specialized process or HACCP plan |
| `vermin` | rodents, insects, birds or animals |
| `plumbing` | hot and cold water, potable water, sewage and wastewater, backflow |
| `storage` | thawing, separation and protection, storage, washing produce, toxic substances |
| `equipment` | equipment and utensils, thermometers, ventilation and lighting, commissary |
| `labeling` | certificates and training, consumer advisory, labels, grade card and signs, person in charge |
| `other` | premises, floors, toilets, garbage, and the rest |

## `meta.json`

**Both modes:**
- `mode`, `sample`, `run`, `generated`.
- `places`: the number listed.
- `inspections_through`, and `expires`: `inspections_through` + 14 days. After it, the site
  shows a notice and search only, and no list.
- `source` `{ name, url }`, `grade_context` `{ majors_graded_A_share, graded_A_share }`,
  `data_rules`, `survivorship`.
- `provenance` `{ code_sha, pull_sha256, python, packages }`.
- `contact`: the approved address for owners, or null.
- `operator` `{ name, contact }`: the responsible adult from the approval, or null.
- `corrections` `[{ date, facility_id, what, why }]`: from `docs/corrections.json`.
- **`publication`** `{ run, approval_sha256, facilities_sha256, gates_passed_at }`: written
  **only** by `export_site.py --publish`, after every gate passes. `check-export.mjs` and the
  site's `prebuild` refuse any non-sample export that lacks it, or whose `facilities_sha256` is not
  the sha256 of the shipped `facilities.geojson`.

**`bands` mode adds:**
- **`model`, `label`, `label_window`, `candidates`:** the places scored.
- **`card`:**
  - `items`: `[{ item, label, points, feature, threshold }]`, plus `max_points`, `window`,
    `trained_on` and `eligibility`.
  - `bands`: `[{ band, min_points, max_points, share, places_now, labelled, positives, rate,
    interval, baseline_rate, kept_in_refits }]`, with the rates from the confirmation origin,
    under the card that is published.
  - `rest`.
- **`catch`, `catch_run`, `selection`, `named_bands`, `cost_ratio`, `utility`, `fairness`,
  `measurement`:** as described in MODEL_CARD.md.

`sample: true` puts a notice on every page. It must never be set on a real export, and the check
refuses a non-sample export that contains a place named "Sample …".
