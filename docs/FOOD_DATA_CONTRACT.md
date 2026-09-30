# The food-safety site's export contract (version 3.6)

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
`sample: true`, and carries every field below, with a few invented places for each new kind of
record (a closure read from a reopening, a reopening with no closure placed, status verifications,
"Self Closed" records, a closure with no reopening on record).

Version 3.6 (2026-09-29) adds, all optional so an older export still passes the check: the County's
`county_type` and `notes` on every inspection record, and `county_type` on the index's `last_visit`;
`closure_inferred` and `reopen_without_closure`;
the visit type `status_check`; kept "Self Closed" records; `grade.open_closure`; `theme_counts` and
`violations_total`; `estimate.min_points` and `max_points`; the curves' `group_counts`; the drift
note's own baseline; `monitor_summary.json`, and in the staff copy `monitor`.

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
- **`data/monitor_summary.json`** (optional): the monitor's summary, `{ status: "too early" | "interim"
  | "complete" | "failed", runs, alerts, next_window_date, rule_version, inspections_through,
  by_district }` (below, "The monitor's summary").
  `export_site.py --monitor` writes it in `data/site/`; the staff copy of `meta.json` carries it as
  `monitor`; the sample ships one (`"too early"`, no runs).

## Sources and rules

- **Sources.** SD Food Info (pulled by `fetch_sdfood.py`) and SANDAG council districts. Nothing
  else: no reviews, no owner names, no phone numbers, no ZIP code or neighbourhood in any model.
- **Data rules** (`export_site.load_places`, tested, and shared with the research CSV):
  - **Not inspections:** "No Access" and "Incomplete" records, and "Self Closed" or "Status
    Verification" records that cite no item, are dropped. A "Self Closed" record that cites items is
    kept, with no score or letter. A "Status Verification" record is kept when it cites items or is a
    closure order ("Ordered Closed"); its visit type is `status_check`: shown, never scored, never read
    by the rule or the labels. `meta.data_rules` counts what was dropped and kept.
  - **Visit types:** the County's "Routine" is `routine` (or `followup`, below), "Re-inspection" is
    `reinspection`, "Site Investigation" and "Environmental" are `complaint` (our reading: a complaint
    or other field visit), and "Status Verification" is `status_check`. Each record also carries the
    County's own type as `county_type`.
  - **Follow-ups:** a routine within 30 days after a B, a C or a closure is a `followup`
    (re-grade or reopening), and so is a routine within 30 days after an "Approved to Reopen" that no
    closure could be placed before, unless the place's record starts at that reopening.
  - **Merges:** same-day records of one type are one visit.
  - **Scores and grades:** 0 means "not scored"; grades are never derived.
  - **Severity tiers:** taken from the status text.
  - **Themes:** the section of the County's own inspection report the item belongs to, read from
    the item text (the mobile-unit form numbers the same items differently).
  - **Closures:** one per episode, with a reason. An episode starts at a County closure order; at a
    "Self Closed" record that cited a major (the operator's own closure, reason health); or, when the
    County's "Approved to Reopen" has no closure before it, at the latest visit with no County score
    that cited a major in the 14 days before it (`INFER_DAYS`; our reading, `closure_inferred`; never a
    scored routine, and never past a closure, a reopening or a graded routine). An "Approved to Reopen"
    with none of these is marked `reopen_without_closure`, and nothing is guessed; a second reopening
    of a closure already reopened is not marked. An episode ends only at the County's "Approved to
    Reopen" (`reopened`, `reopened_on`; when a graded routine ended the latest episode first, a
    reopening within 30 days of that episode's latest closure, with nothing reopened since, is still
    its reopening), at a graded routine or re-grade on a later day, or when the next closure comes more
    than 30 days after the last. A complaint visit or an ungraded reinspection while a place is closed
    does not end it, so one closure is never counted twice; on one day, a closure sorts first and a
    reopening next. The reason: `health` when a major was cited that day, `permit` when a note mentions
    a permit, otherwise `other` (no major and no permit note: the County's record gives no reason).
    Only a `health` closure counts as 70 at a routine, and only `health` closures count in `closed` and
    `closures2`.
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
| `last_visit` | `{ date, type, county_type }` | the most recent County record; `type` is a visit type (`status_check` included), our reading; `county_type` is the County's own inspection type on that record, verbatim ("Routine", "Site Investigation", ...; absent in an older export). The staff CSV's `last_visit_type` gives both in words: "complaint or other field visit (our reading; County type: Site Investigation)" |
| `grade` | `{ grade, score, date, replaced, open_closure }` or null | the latest letter on the County's record in the window, from a routine or re-grade visit; `replaced` is `{ grade, score, date }` of the routine grade a re-grade replaced, else null. `open_closure` is the place's last closure when nothing on the record ended it (no "Approved to Reopen", no graded routine or re-grade after it), else null: `{ date, reason, later_ungraded, status? }`, where `later_ungraded` lists the dates of the ungraded records after it, each strictly after the closure (a further closure order excluded), and `status`, when given, is the County's status text on the record that started it ("Ordered Closed" or "Self Closed"; absent for a closure read from a reopening). The County posts no grade card while it has a place closed, so the letter is then the one from before the closure: the site leads with the closure, and never says the place is closed now. A place with no graded record has `grade: null`, and an open closure there shows only in its records |
| `flags` | array | record facts measured back from the list date (`inspections_through` + 1 day). From the 12 months before it: `major` (a major violation), `closed` (a health-hazard closure), `bc` (a B or C at a graded routine), `repeat` (two or more reinspections), and the theme key of every major's theme (never `other`). From the 24 months before it, our counts of the patterns the County's Operator's Guide names ("recurring major violations, recurring scores of less than 90%, or recurring facility closures", p. 8; the County sets no count or period, and meeting one is not a County finding): `major_2` (major violations at two or more distinct routine inspection days), `closures2` (two or more health-closure episodes), `repeat_item` (the same major item at two or more distinct routine inspection days) and `lt90_2` (two or more routine inspection days scored below 90). A day the County recorded twice counts once. |
| `band`, `points` | `"1"`, `"2"` …, int | `bands` mode only; absent while `on_hold` |
| `on_hold` | bool | `bands` mode: the place is under review (`docs/holds.json`); the site shows its record and "Under review", no band or points |

There is **no `rank`, `percentile`, `oof_rank`, `score`, `shap_features` or `is_known_positive`**
in any export. The site sorts by band, then points (highest first), then name (`bands`; a place on
hold has no band or points, so it sorts with the places that have none), or by name (`record`).

## `place/<facility_id>.json` (detail)

Everything in the index entry, plus:

- **`business_type`:** the County's own type, verbatim.
- **`inspections`:** oldest first, **one entry per County record**. Same-day records are not
  merged for display, so every grade shown is a single County letter:
  `{ date, status, type: "routine" | "reinspection" | "followup" | "complaint" | "status_check",
  county_type, score, grade, major, minor, grp, notes, closed, closure: "health" | "permit" |
  "other" | null, reopened: bool | null, reopened_on: "YYYY-MM-DD" | null, closure_inferred?,
  reopen_without_closure? }`. `closed` marks the record that starts a closure episode;
  `reopened_on` is the date of the County's "Approved to Reopen" that ended it.
  - `status` is the County's own text ("Complete", "Ordered Closed", "Approved to Reopen", "Self
    Closed"), `county_type` the County's inspection type ("Routine", "Re-inspection", "Site
    Investigation", "Environmental", "Status Verification"), and `notes` the County's own note texts
    on the record ("No Valid Permit", "Impoundment", ...; `[]` when none), all shown verbatim.
    `county_type` agrees with `type`: routine and followup are "Routine", reinspection
    "Re-inspection", complaint "Site Investigation" or "Environmental", status_check "Status
    Verification".
  - `closure_inferred: true` (present only when true) marks a closure no order shows, read from a
    later "Approved to Reopen": it is `closed`, never "Ordered Closed", and has `reopened: true` and
    `reopened_on`. `reopen_without_closure: true` (present only when true) marks an "Approved to
    Reopen" that no closure could be placed before.
  - A record that starts a closure is "Ordered Closed", "Self Closed" with a major cited on that
    record, or `closure_inferred`. A kept "Self Closed" or `status_check` record cites items or is
    "Ordered Closed", and a `status_check` has no score.
  - `type` (`followup`, `complaint`, `status_check`), `closure`, `reopened`, `reopened_on`,
    `closure_inferred` and `reopen_without_closure` are the pipeline's readings, and the site labels
    them "Our reading".
- **`violations`:** items cited in the 36 months before the last visit, majors first, at most 150
  (`MAX_VIOLATIONS`): `{ date, visit, code, theme, severity: "major" | "minor" | "grp", description }`.
  `visit` is the visit type (`status_check` included), and findings at complaint visits are included.
  When the cap cuts, it drops the oldest items that are not majors, never the newest, and
  `export_site.py` prints a warning. The most any place held in the September 2026 pull is 83, so no
  real place is cut today.
- **`violations_total`:** how many items the same window holds before the cap (at least the number
  listed, and equal to it when fewer than 150 are listed).
- **`theme_counts`:** `{ theme: { major, minor, grp, complaint, latest } }` over every item in the
  window, before the cap: items by severity, how many were found at complaint visits, and the latest
  date. They add up to `violations_total` and are never below the items listed. The site counts
  themes from them, and says so when a view has to count from a list that was cut.
- **`score_card`** (`bands` mode only): every card item as
  `{ item, points, met, value }`, where `value` is the place's own number the item tests (its
  average routine score, a count). The points of met items sum to `points`.
- **`band_stability`** (`bands` mode only): the share of refits of the card in which the place
  stayed in its band; null for a fixed rule (the average-score rule has nothing to refit).
- **`scores_used`** (`bands` mode, scored places): `[{ date, score, closure, county_score }]`, oldest
  first: the routine scores the averages read, the two years before the list. A routine inspection
  that started a closure for a health hazard (a County closure order, the operator's own closure with
  a major cited, or a closure read from a later reopening) has `closure: true` and `score: 70`, every
  time: the County usually gives no score that day, and `county_score` is its own score when it gave
  one (else null). A routine that ended in a `permit` or `other` closure is averaged only if the
  County scored it. The site says
  "this rule counts it as 70", never that the County scored it 70. `avg_deficit` on the worksheet is
  100 minus their mean rounded half up, and `last_deficit` is 100 minus the last; `check-export.mjs`
  checks both, so every worksheet can be checked by hand.
- **`estimate`** (`bands` mode, scored places):
  `{ rate, low, high, group, min_points, max_points }`, what places in this place's group of points
  did in the backtest. `min_points` and `max_points` (optional; whole points,
  `min_points <= max_points`) are the fitted group the rate is read from: every place in a group gets
  the group's rate. `group` is `"closure"` when the place's `scores_used` include a health closure
  (counted as 70), read from `meta.card.curve_closure`, and `"scores"` otherwise, read from
  `meta.card.curve` (outside the City, from `meta.card.outside`'s curves): places carried by a
  closure had a major next time far less often than places with the same points from routine scores
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
  `data_rules` (`dropped`, `self_closed_and_status_checks_kept`, `same_day_merged_for_the_model`,
  `followups_retyped`, `closure_episodes`, `closures_read_from_a_reopening`,
  `reopenings_with_no_closure_placed`, `unknown_business_types`), `survivorship`.
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
  - `items`: `[{ item, label, weight, unit, feature }]`, plus `rule`, `window`, `trained_on` and
    `eligibility`.
  - `bands`: `[{ band, min_points, max_points, share, places_now, places_now_county, labelled,
    positives, rate, interval, baseline_rate, vs_baseline, kept_in_refits }]`, with the rates from
    the confirmation origin, under the rule that is shown. `places_now` counts City places;
    `places_now_county` every listed place.
  - `rest`, and `base_rate`: the rate among all scored places (the comparison the site states).
  - `proposed_cuts`, `band_rule`: the cuts at fixed shares of the list, and the rule that kept or
    merged them (a split survives only if it holds at every backtest origin).
  - `by_origin`: `[{ as_of, "1": {positives, labelled, rate}, …, rest }]`, the kept bands at every
    backtest origin, not only the one reported.
  - `curve`: `{ model, groups, group_counts, rate[], low[], high[], bins[], labelled, positives }`:
    the rate by points (index = points) for places whose two scored years include no health closure,
    a monotone (isotonic) fit over point values pooled into `groups` of 200 or more labelled places
    (`[[min_points, max_points], ...]`), with a 95% interval. `group_counts` (optional) gives, for each
    group in order, `{ min_points, max_points, labelled, positives }`, the counts every place in that
    group is read from; `bins` are finer raw rates, which no place is read from. `curve_closure`: the
    same for places whose two years include one (or null).
  - `interim`: `{ "90" | "180" | "270": { "1": {labelled, positives, rate}, all: {...} } }`: band 1's
    rate and the rate for all eligible places at the confirmation origin with the label cut off after
    that many days, which a later list's early rates are set against (the monitor).
  - `closure_score`: 70, the rule's reading of a routine inspection that started a health closure.
  - `band_1_by_route`: `{ closure, scores }`, each `{ labelled, positives, rate, interval }`: band 1
    at the confirmation origin split into places there only because a health closure counted as 70
    (without their closures their average would be under the cut) and places there on routine scores
    alone.
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
- **`drift`** `{ status, major_rate_backtest, major_rate_backtest_n, backtest_span,
  major_rate_recent, recent_quarters, band_1_share_backtest, band_1_share_now, latest_quarter,
  latest_rate, latest_n, latest_baseline, latest_baseline_n, latest_baseline_span, refit_needed,
  reasons, note, thresholds }`: two weekly signals that need no new labels, each against max(2 points,
  3 standard errors) (`thresholds`). The routine major rate over the last one or two complete quarters
  that start after the backtest's label year (`recent_quarters`, `major_rate_recent`) is compared with
  the rate over the label year's own months (`major_rate_backtest`, on `major_rate_backtest_n`
  routine inspections, `backtest_span` such as "September 2025 to August 2026"). A quarter counts once
  the County's record has run 30 days past its end; until one does, `status` is
  `"not_yet_measurable"`, never a clean result. Band 1's share of scored City restaurants is the
  other signal. Either sets `refit_needed` and a line in `reasons`. `note` is a sentence the site
  shows beside every estimate when the latest quarter's rate (`latest_rate`, on `latest_n`) differs
  clearly from `latest_baseline`, the rate over the label year's months before that quarter (on
  `latest_baseline_n`, `latest_baseline_span` such as "September 2025 to June 2026"), so the two
  share no inspection. It says whether the rates "may be low" or "may be high", which the staff notice
  turns into an instruction. Without monthly counts the baselines fall back to the label year's
  quarters.

**The staff copy** (`publish_city_site.py` rewrites `meta.json` in the private repository only):
`audience: "staff"`, `operator { name, role, email }`, `contact { name, email }`, `sunset`,
`access_approved`, `monitor`, `review_status` and `staff_release { at, by }`.

- `access_approved` is `true` or `false`, never anything else: `true` only with a City request for
  access (the requestor's name, and a date), and a TRUST Ordinance answer with who gave it and a date:
  "does not apply", or "applies" with the Council's approval (a resolution, and the date of the vote).
  Every date is YYYY-MM-DD on or before the day of publishing. Until it is `true` the server shows the
  named list only to the site's operators; it opens the list for the value `true` and no other.
- `monitor` is `data/site/monitor_summary.json` as the monitor wrote it, or, when the monitor has not
  run for this list or wrote a summary that cannot be read, `{ status: "failed", runs: 0, alerts:
  ["The monitor has not run for this list."], next_window_date: null }` (or "... wrote a summary that
  cannot be read."). A summary whose `inspections_through` or `rule_version` is not this export's
  (`inspections_through`, `frozen.version`), or that has neither, is the previous run's (an
  `export_site.py` with no `--monitor` after it): it ships as `"failed"` too, its sentence saying which
  record or rule it scored and to run `export_site.py --monitor`.
- `review_status` lists, in plain words, what has not been done (no City request, no TRUST
  determination, no lawyer, no County comment, no owner told), whether the rule needs a refit, and
  every public-release gate this list does not pass.

The site then shows the staff banner with that guidance, the contact and the staff terms; the drift
note and a monitor alert on a list the monitor has scored (`interim` or `complete`) become
instructions too, not counted as open checks. The server closes the site's data after `sunset` or
without `audience: "staff"`. Its open `/healthz` gives, with no data: `ok`, `run`,
`inspections_through`, `expires`, `stale`, `source`, `server`, `sunset`, `closed`, `refit_needed`,
`drift_note` (true when `drift.note` is set; the note stays behind the sign-in), `monitor` (the
status, or null for an older export), `monitor_alert` (true for any alert, or status `"failed"`),
`rule_version`, `access_approved` and `named_list` (both count only the value `true`).

`run` names its content: `forward_<list date>-<8 hex>`, a hash of the rule, the cuts and the list, so
two different lists never share a run id. The downloaded CSV carries it on every row (`list_run`).

`sample: true` puts a notice on every page. It must never be set on a real export, and the check
refuses a non-sample export that contains a place named "Sample …".

## The monitor's summary

`monitor_summary.json`, written by every `export_site.py --monitor` run, even when no archived list
can be scored yet:

- `status`: `"too early"` (no archived list has a window yet, or there is none), `"interim"` (a list
  has a 90, 180 or 270-day window, set against `card.interim`), `"complete"` (a list's label year has
  passed in the record, plus 30 days), or `"failed"` (the monitor step errored: `export_site.py
  --monitor` and `refresh_city_site.py` write it then, so last week's summary is never shipped).
- `runs`: how many archived lists it read, scored or not yet (a whole number, 0 or more).
- `alerts`: plain sentences, one per kind of finding, each naming the latest list that shows it and
  how many earlier lists do too: band 1's City rate with the top of its 95% interval below its
  expectation (interim or complete); observed over expected outside 0.85 to 1.15 on a complete list,
  the City and outside it apart; band 1 behind the same number of places with the most recent major
  violations, the top of the difference's 95% interval below 0. Only a list whose frozen rule version
  is the current `docs/rule.json` version raises an alert: a list from an earlier version, or from
  before any rule was frozen, is still scored and counted in `runs` and `monitor.md`, but raises
  none, so the alerts clear once a refit's new version is live.
- `next_window_date`: `"YYYY-MM-DD"`, the date the County's record must reach for any list's next
  window (90, 180, 270 or 365 days, each plus 30), or null when every list is complete.
- `rule_version`: the frozen rule version the alerts were read for (`docs/rule.json`), or null before
  any rule is frozen; `inspections_through`: the last day of the record the monitor scored. The staff
  publish matches both to the export it ships (above). A `"failed"` summary has neither.
- `by_district`: the City by council district on the latest scored list drawn up under the current
  rule, or null before one is scored: `{ run, window_days, districts: { "<district>": { labelled,
  positives, rate, banded: { bands, labelled, positives, rate, interval, expected } } } }`. `labelled`
  and `positives` count the later routine inspections of that district's scored City places and those
  that found a major; `banded` does the same for the bands the backtest's district audit read
  (`fairness.bands_used`), with a 95% Wilson `interval` and, on a complete list only, `expected`, that
  audit's rate in the district (null otherwise). Figures to read, never an alert: a district holds
  about 20 to 150 banded places, so one of nine would cross any fixed line by chance every few lists.

## What the contract check enforces for the fields of version 3.6

`check-export.mjs` accepts an export without any of these fields. Where they are present it fails
on: `notes` that are not a list of non-empty texts; a `county_type` that is not one of the County's
types for the record's visit type; a `closure_inferred` that is not on a record starting a closure,
is on an "Ordered Closed" record, or has no `reopened: true` and `reopened_on`; a
`reopen_without_closure` that is not on an "Approved to Reopen" record; a closure on a record that
is neither "Ordered Closed" nor "Self Closed" (with a major) and not `closure_inferred`; a kept
"Self Closed" or `status_check` record with no items and no closure order, or a `status_check` with
a score; a `grade.open_closure` of the wrong shape, dated before the grade, with a `later_ungraded`
date not after it, or that is not the place's last closure as its records show it (its reason and
`status` included, with no reopening and no graded visit after it); `theme_counts` of the wrong
shape, below the items listed, or not adding up to `violations_total`; a `violations_total` below
the items listed, or above them when fewer than 150 are listed; a `last_visit.county_type` in the
index that is not one of the County's types for `last_visit.type`, or not the place file's last
record's `county_type`; an estimate whose `min_points` and `max_points` are not whole points in
order; `group_counts` that are not one entry per fitted group, in order; and a
`monitor_summary.json` outside the shape above.
