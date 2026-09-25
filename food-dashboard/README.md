# San Diego Food Inspection Record

A working tool for City of San Diego staff: the County's inspection record for every listed
restaurant, limited-preparation food place and market in the City, place by place, with the
County's own status text on every record and the site's readings labelled "Our reading". Vite,
React, Tailwind, Google Maps with a deck.gl overlay, no router, installable.

## Modes

The export sets `meta.mode` ([docs/FOOD_DATA_CONTRACT.md](../docs/FOOD_DATA_CONTRACT.md),
version 3.1):

- **`record`**, the default: search, the map with every place drawn alike, filters on record
  facts (kind of place, district, and the index's flags for the last year of the record), the list
  by name, and each place's County records. Nothing from a model.
- **`bands`**: the same, plus a published rule (`meta.card.rule`) that gives eligible places points
  from their own record, bands cut by points, each place's worksheet, and each band's backtest
  rate beside the rate below the bands. Lists are ordered by band, then points, then name; no list
  shows a position.

An unknown or missing mode is shown as `record`.

## Data

`public/data/` holds:

- `meta.json`: what the export is.
- `facilities.geojson`: the index, only what the map, the list, the filters and the search need.
- `place/<facility_id>.json`: one file per place, loaded when the place is opened.

**What ships in the repository is an invented sample** in `bands` mode:
`python scripts/make_sample_export.py` writes it (`--mode record` for a record-mode sample,
`--out <dir>` for somewhere else). Every place is named "Sample …" on made-up streets, and a
notice sits on every page.

**A real export reaches `public/data/` only through `python export_site.py --publish`** at the
repository root, which writes `meta.publication` after every gate in
[docs/PUBLISHING.md](../docs/PUBLISHING.md) passes. Never copy `../data/site/` into `public/`: the
build refuses a real export without a matching `meta.publication`.

## Checks

```
npm test                                          # node --test tests/*.test.mjs
npm run check                                     # public/data against the contract
node scripts/check-export.mjs ../data/site --review   # an unpublished export
npm run build                                     # runs the prebuild checks first
```

`scripts/check-export.mjs` fails on anything outside the contract (a position or score field,
a place file missing or out of step with the index, worksheet rows that do not add up, a tie in
points split across a band edge, enums, an index over 3 MB) and refuses a real export that is not
approved for publication. `--review` reports the publication gates as a warning and runs every
other check. `npm run build` first runs `scripts/check-expiry.mjs`, which stops a build of a real
export whose `meta.expires` has passed, and then the contract check without `--review`.

## Run it

```
cp .env.example .env        # the Google Maps key and Map ID
npm install
npm run dev                 # http://localhost:5173
```

To look at an unpublished export, keep it out of the repository: copy `public/` to a scratch
folder outside it, put the export in that folder's `data/`, and point a throwaway Vite config's
`publicDir` at the folder. Delete the config afterwards.

The Google key needs the Maps JavaScript, Street View Static, Places (New) and Geocoding APIs,
restricted to this site's domains. Serve `.geojson` and `.json` compressed. Hosting:
[docs/HOSTING.md](../docs/HOSTING.md).

## Pages

- `/`: what the site holds, a search, the count and dates, and the way into the map and the list;
  it names no place
- `/map`: filters, "Near an address", the map, the list with CSV download (every row carries the
  list date and the expiry date), and the place panel; a phone gets its own shell, which shows
  the list when the map cannot load
- `/place/<facility_id>`: one place as a page, not indexed by search engines; a key that is not a
  listed facility_id is a page that is not found
- `/privacy`: privacy, the County's words and ours, corrections routing, terms, operator,
  changes; `/corrections`: the corrections log from `meta.corrections`
- once `meta.expires` has passed, the front page and the map become a notice and a search of the
  record the export holds (`src/lib/expiry.js`)

## Where things are

- `src/site.js`: facts about the place and the regulator, including the County's SD Food Info
  disclaimer as quoted on every place page
- `src/lib/framing.js`: the headline, the lines under a place's name, and the mode; pure and tested
- `src/lib/bands.js`, `card.js`: bands, their backtest rates, and a place's worksheet
- `src/lib/grades.js`: every view's grade text
- `src/lib/recordFacts.js`: "What the County's record shows" for a place
- `src/lib/placeData.js`, `src/usePlace.js`: loading one place's file, with its failure states
- `src/lib/inspections.js`, `filters.js`, `search.js`, `format.js`, `links.js`, `ask.js`
- `src/Dialog.jsx`: the one modal dialog (focus, Tab trap, Escape, focus restored)
- `scripts/check-export.mjs`, `scripts/check-expiry.mjs`, `scripts/make_sample_export.py`

## Design

[AVOID.md](AVOID.md) is the list of things this site does not do. In practice: warm paper, ink,
one band ramp; hairlines instead of cards; no gradients, emojis, icon packs, rounded corners or
pastel; system fonts only; a custom 404; a title and description per page; a favicon set; robots
and a sitemap; a cookie note, a privacy page and terms; loading, empty and error states; mobile
breakpoints with a sticky mobile button; no em dashes in copy.
