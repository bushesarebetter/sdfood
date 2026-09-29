# The food-safety site's export contract (version 3.5)

`food-dashboard/` shows City of San Diego restaurants and markets with the County's inspection
record. It has two modes, set by `meta.mode`:

- **`record`, the default publishable product.** The County's record for every listed place,
  with no model and no ordering: search, map, filters on record facts, each place's
  inspections, what inspectors found, and "If you eat here" drawn from the record.
- **`bands`, the gated product.** The same, plus the students' point rule, which puts some places
  in bands, with each band's backtest hit rate and each scored place's estimate. The City staff site
  (docs/STAFF_SITE.md) shows it behind a sign-in; the public site shows it only if every gate passes. It reaches the site only if every gate in
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
  the map, the list, the filters and the search need. What the public site ships must stay under
  3 MB (a published export holds only named City places, far less). An unpublished review or
  City-staff export lists every active place county-wide, about 11,000 places and 4.6 MB in
  September 2026; its limit is 8 MB. Either way the host serves `.geojson` compressed
  (`city_site/server.mjs` gzips it: about 560 KB), so a phone can load it.
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
  - **Themes:** the section of the County's own inspection report the item belongs to, read from
    the item text (the mobile-unit form numbers the same items differently).
  - **Closures:** one per episode, with a reason. An episode starts at a closure order and ends only
    at the County's "Approved to Reopen" (`reopened`, `reopened_on`), at a graded routine or re-grade
    on a later day, or when the next order comes more than 30 days after the last. A complaint visit
    or an ungraded reinspection while a place is closed does not end it, so one closure is never
    counted twice; on one day, a closure order sorts first and a reopening next.
- **Listed places:** restaurants (`restaurant`), limited-preparation food service (`limited`) and
  markets with a deli or food processing (`market`), visited in the last 18 months, with a permit
  that has not expired. A `record` export lists the City's. A `bands` export for review or the
  City staff site lists them county-wide (the site's area toggle shows places outside the City,
  which carry no council district); a **published** `bands` export names only City places, since
  the rule's backtest and its district-parity gate are the City's (`export_site.named_features`,
  and `check-export.mjs` refuses anything else).

## `facilities.geojson` (index)

| property | type | meaning |
|---|---|---|
| `facility_id` | string | the County's permit record id; the key for every link and file |
| `name`, `address` | string | as on the County's record |
| `facility_type` | `restaurant`, `limited`, `market` | the sample may use others |
| `council_district` | int or null | 1 to 9; null outside the City (unpublished `bands` exports only) |
| `last_visit` | `{ date, type }` | the most recent visit |
| `grade` | `{ grade, score, date, replaced }` or null | the grade on the County's card in the window: the latest letter from a routine or re-grade visit; `replaced` is `{ grade, score, date }` of the routine grade a re-grade replaced, else null |
| `flags` | array | record facts measured back from the list date (`inspections_through` + 1 day). From the 12 months before it: `major` (a major violation), `closed` (a health-hazard closure), `bc` (a B or C at a graded routine), `repeat` (two or more reinspections), and the theme key of every major's theme (never `other`). From the 24 months before it, our counts of the patterns the County's Operator's Guide names ("recurring major violations, recurring scores of less than 90%, or recurring facility closures", p. 8; the County sets no count or period, and meeting one is not a County finding): `major_2` (major violations at two or more distinct routine inspection days), `closures2` (two or more health-closure episodes), `repeat_item` (the same major item at two or more distinct routine inspection days) and `lt90_2` (two or more routine inspection days scored below 90). A day the County recorded twice counts once. theme with a major; and two escalation facts over the two years before the last visit, the County's own criteria for a closer look (Operator's Guide p. 8): `closures2` (two or more health-hazard closures, any visit type) and `repeat_item` (the same major item at 2 of the last 3 routine inspections) |
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
  major, minor, grp, closed, closure: "health" | "permit" | "other" | null, reopened: bool | null,
  reopened_on: "YYYY-MM-DD" | null }`. `closed` marks the record that starts a closure episode;
  `reopened_on` is the date of the County's "Approved to Reopen" that ended it.
  - `status` is the County's own text ("Complete", "Ordered Closed", "Approved to Reopen"), shown
    verbatim.
  - `type: "followup"`, `closure`, `reopened` and `reopened_on` are the pipeline's readings, and
    the site labels them "Our reading".
- **`violations`:** items cited in the 36 months before the last visit, majors first, at most 60:
  `{ date, visit, code, theme, severity: "major" | "minor" | "grp", description }`. `visit` is
  the visit type, and findings at complaint visits are included.
- **`score_card`** (`bands` mode only): every card item as
  `{ item, points, met, value }`, where `value` is the place's own number the item tests (its
  average routine score, a count). The points of met items sum to `points`.
- **`band_stability`** (`bands` mode only): the share of refits of the card in which the place
  stayed in its band; null for a fixed rule (the average-score rule has nothing to refit).
- **`scores_used`** (`bands` mode, scored places): `[{ date, score, closure, county_score }]`, oldest
  first: the routine scores the averages read, the two years before the list. A routine that ended in
  a health closure order has `closure: true` and `score: 70`, every time: the County usually gives
  no score that day, and `county_score` is its own score when it gave one (else null). The site says
  "this rule counts it as 70", never that the County scored it 70. `avg_deficit` on the worksheet is
  100 minus their mean rounded half up, and `last_deficit` is 100 minus the last; `check-export.mjs`
  checks both, so every worksheet can be checked by hand.
- **`estimate`** (`bands` mode, scored places): `{ rate, low, high, group }`, what places with about
  this many points did in the backtest. `group` is `"closure"` when the place's `scores_used` include
  a health closure (counted as 70), read from `meta.card.curve_closure`, and `"scores"` otherwise,
  read from `meta.card.curve` (outside the City, from `meta.card.outside`'s curves): places carried by
  a closure had a major next time far less often than places with the same points from routine scores
  alone, so one pooled curve would misread both. `0 <= low <= rate <= high <= 1`.

Themes are the sections of the County's own inspection report (Retail Food Facility Operator's
Guide, pp. 8-28), read from the item text (`export_site.THEME_RULES`; all 100 texts in the pull are
pinned in `tests/fixtures/item_themes.json`). Items 1-23 are the foodborne-illness items that can be
cited as major; 24 and up are good retail practice (`grp_*`). Item numbers are the fixed-facility
form's; the mobile-unit form numbers the same items differently (22 is pests there, sewage here), which
is why the text, not the number, decides.

| theme | label | fixed form | mobile form |
|---|---|---|---|
| `knowledge` | Food safety certificate and food handler cards | 1a, 1b | 1a, 1b |
| `health` | Employee health and hygiene | 2-4 | 2-4 |
| `hands` | Hands washed, gloves used | 5 | 5 |
| `handsink` | Hand sinks stocked and accessible | 6 | 6, 20 |
| `temperature` | Food temperatures | 7-11 | 7-11 |
| `condition` | Food condition | 12, 13 | 12, 13 |
| `sanitizing` | Food-contact surfaces cleaned and sanitized | 14 | 14 |
| `supplier` | Food source and shellfish tags | 15-17 | 15, 16 |
| `process` | Special processes (HACCP) | 18 | |
| `advisory` | Consumer advisory | 19 | 18 |
| `hsp` | Foods not allowed for highly susceptible people | 20 | |
| `water` | Hot and cold water | 21 | 19 |
| `sewage` | Sewage and wastewater | 22 | 21 |
| `vermin` | Pests | 23 | 22 |
| `grp_staff` | Supervision and personal cleanliness (good retail practice) | 24, 25 | 23 |
| `grp_food` | Food handling and chemicals (good retail practice) | 26-29 | 24-27 |
| `grp_storage` | Food storage, display and labels (good retail practice) | 30-32 | 28, 29 |
| `grp_equipment` | Equipment, utensils and dishwashing (good retail practice) | 33-40 | 30-32, 34-36 |
| `grp_facility` | Building and premises (good retail practice) | 41-46 | 33, 37, 38, 40 |
| `grp_signs` | Signs, grade card and permits (good retail practice) | 47 | 41, 42 |
| `grp_other` | Other (good retail practice) | | 39 (fire safety) |
| `other` | Other (home-kitchen and cottage-food labelling items, and anything unmatched) | | |

The model's theme features count only the foodborne-illness sections (`RISK_THEMES`: `health`,
`hands`, `handsink`, `temperature`, `condition`, `sanitizing`, `supplier`, `process`, `hsp`, `water`,
`sewage`, `vermin`), never good retail practice.

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
  - `bands`: `[{ band, min_points, max_points, share, places_now, places_now_county, labelled,
    positives, rate, interval, baseline_rate, vs_baseline, kept_in_refits }]`, with the rates from
    the confirmation origin, under the rule that is shown. `places_now` counts City places;
    `places_now_county` every listed place.
  - `rest`, and `base_rate`: the rate among all scored places (the comparison the site states).
  - `proposed_cuts`, `band_rule`: the cuts at fixed shares of the list, and the rule that kept or
    merged them (a split survives only if it holds at every backtest origin).
  - `by_origin`: `[{ as_of, "1": {positives, labelled, rate}, …, rest }]`, the kept bands at every
    backtest origin, not only the one reported.
  - `curve`: `{ model, groups, rate[], low[], high[], bins[], labelled, positives }`: the rate by
    points (index = points) for places whose two scored years include no health closure, a monotone
    (isotonic) fit over point values pooled into groups of 200 or more places, with a 95% interval,
    and the raw rates in bins. `curve_closure`: the same for places whose two years include one (or
    null).
  - `interim`: `{ "90" | "180" | "270": { "1": {labelled, positives, rate}, all: {...} } }`: band 1's
    rate and the rate for all eligible places at the confirmation origin with the label cut off after
    that many days, which a later list's early rates are set against (the monitor).
  - `closure_score`: 70, the rule's reading of a routine inspection that ended in a health closure.
  - `band_1_by_route`: `{ closure, scores }`, each `{ labelled, positives, rate, interval }`: band 1
    at the confirmation origin split into places there only because a closure counted as 70 (without
    their closures their average would be under the cut) and places there on routine scores alone.
    Null when the rule is not the average-score rule. How much the list leans on the 70:
    [CLOSURE_SENSITIVITY.md](CLOSURE_SENSITIVITY.md).
  - `outside`: `{ bands_shown, candidates, eligible, labelled, base_rate, bands, rest, curve,
    curve_closure, auc }`: the same rule and cuts checked on restaurants outside the City, each band
    with its persistence baseline as in the City. Places outside the City get a band only when
    `bands_shown`.
- **`catch`, `catch_run`, `selection`, `named_bands`, `cost_ratio`, `utility`, `fairness`,
  `measurement`:** as described in MODEL_CARD.md. Each `fairness.by_district[d]` carries `labelled`
  (labelled, scored places), `precision` with a Wilson `precision_interval`, `fpr_ratio`, and
  `false_share_ratio` (its share of the wrongly named over its share of the labelled scored places)
  with a 95% `interval`, a family-wise `interval_family` over all the districts compared (address
  bootstrap, 10,000 draws), and `interval_family_deff`, that interval widened by an assumed design
  effect of 2 for inspector clustering (never below 0); `evidence_above_even` is true only when both
  family-wise intervals clear 1.
- **`frozen`** `{ version, frozen_on, from_run }`: the frozen rule (`docs/rule.json`) the list
  applies; every export applies it unchanged, and only `export_site.py --refit` writes a new version.
  `docs/rule.json` also holds `feature_spec`: the constants and a hash of the code that decide what a
  point means (the closure reading, the windows, the episode rule, the themes); an export refuses to
  apply a rule whose feature code has changed since it was frozen.
- **`drift`** `{ status, major_rate_backtest, major_rate_recent, recent_quarters,
  band_1_share_backtest, band_1_share_now, latest_quarter, latest_rate, latest_n, refit_needed,
  reasons, note, thresholds }`: two weekly signals that need no new labels, each against max(2 points,
  3 standard errors). The routine major rate compares complete quarters that start after the
  backtest's label year with the label year's own; until such a quarter exists `status` is
  `"not_yet_measurable"`, never a clean result. `note` is a sentence the site shows beside every
  estimate when the latest quarter's rate differs clearly from the backtest year's.

**The staff copy** (`publish_city_site.py` rewrites `meta.json` in the private repository only):
`audience: "staff"`, `operator { name, role, email }`, `contact { name, email }`, `sunset`,
`access_approved` (a City request for access with its name and date, and a TRUST Ordinance answer of
"does not apply", or "applies" with the Council's approval: until then the server shows the named list
only to the site's operators),
`review_status` and `staff_release { at, by }`. `review_status` lists, in plain words, what has not
been done (no City request, no TRUST determination, no lawyer, no County comment, no owner told),
whether the rule needs a refit, and every public-release gate this list does not pass. The site then
shows the staff banner with that guidance, the contact and the staff terms; the server closes the
site's data after `sunset` or without `audience: "staff"`.

`run` names its content: `forward_<list date>-<8 hex>`, a hash of the rule, the cuts and the list, so
two different lists never share a run id. The downloaded CSV carries it on every row (`list_run`).

`sample: true` puts a notice on every page. It must never be set on a real export, and the check
refuses a non-sample export that contains a place named "Sample …".
