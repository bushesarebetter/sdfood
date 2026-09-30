# Runbook: keeping the City staff site running

For whoever runs the refresh (the operator). What the site is for, and who may use it:
[STAFF_SITE.md](STAFF_SITE.md). How it was set up: [HOSTING.md](HOSTING.md), "The City staff site".

## What is live

| Piece | Where |
|---|---|
| The site | `https://sdfood-city.onrender.com`, a Render web service (`sdfood-city`), Node, `node server.mjs` |
| Its code and data | the PRIVATE repository `ChenhaoZhang01/sdfood-city`, written only by `publish_city_site.py` |
| What it takes to rebuild it | `ops/` in that repository (not served): the source of the site and of the list, the frozen rule, the pull's meta, the approval, the holds (and `holds_applied.json`, every id a publish has held on its list), the monitor's output and every archived list (`ops/README.md` says which is which) |
| Sign-ins | the service's `SITE_USERS` (one `id:token` per person) and `SITE_OPERATORS` ("Sign-ins" below); a form sign-in with a session that ends after 30 idle minutes or 10 hours |
| Health | `https://sdfood-city.onrender.com/healthz`: open, no data. It says which export (`run`, `expires`), commit (`source`), server build and rule version are live; whether the site is `closed`; whether the rule needs a refit (`refit_needed`) or there is a drift note (`drift_note`); the monitor's status and whether it has an alert (`monitor`, `monitor_alert`); and whether the named list is open to signed-in staff (`access_approved`, `named_list`) |
| Daily check | `.github/workflows/watch.yml` in the private repository ("The daily check" below) |
| The pipeline | this repository, on one machine: `fetch_sdfood.py`, `export_site.py` (and `--monitor`), `export_worklist.py`, `publish_city_site.py`, or all of them as `refresh_city_site.py` |
| The frozen rule | `docs/rule.json`, committed: every export applies it unchanged |
| Deploy log | `DEPLOYS.jsonl` in the private repository and `data/staff_deploys.jsonl` here: every publish, with its run, the commit that built the site (`site_code_sha`) and the one that built the list (`export_code_sha`), who ran it, what it had not passed, what was on hold (`held`) and which of those were on the list (`held_on_list`) (and, in `DEPLOYS.jsonl`, the monitor's status) |

## The daily check

`watch.yml` runs every morning (about 07:23 in San Diego) and reads only the live site. It fails,
and opens one issue titled "staff site check failed" that lists every failed check (a later failure
comments on the issue already open, so a problem that lasts a week is one issue), when:

- the site does not answer, or the check does not finish in its 10 minutes (a site that hangs is
  treated as down);
- Render is not serving the private repository's latest commit (a deploy failed or is stuck);
- the site is closed (past its sunset, or not serving the staff export), its export is stale, or the
  export expires in under 4 days;
- the rule needs a refit (`refit_needed`);
- the data answers without a sign-in.

A check that runs out of its 10 minutes counts as failed: it still opens or comments on that issue,
which then says the check did not finish.

Without failing, it opens a separate issue, once while it is open, when the sunset is under 30 days
away, when there is a drift note ("Drift, and when the rule needs a refit"), and when the monitor has
an alert or did not run for the live list ("Reading the monitor"). Close each once it is dealt with.

The site's address is the private repository's variable `SITE_URL` (Settings, Secrets and variables,
Actions, Variables), or `https://sdfood-city.onrender.com` when it is unset.

## Every week: refresh

An export stays current for about 13 days after its pull: it expires 14 days after the County's record
ends, and the record lags the pull by about a day. Refresh weekly. First check that everything a
refresh needs is in place (this changes nothing):

```bash
python refresh_city_site.py --check
SDFOOD_CONTACT=you@example.org python refresh_city_site.py      # about an hour, mostly the pull
```

On Windows (PowerShell): `$env:SDFOOD_CONTACT = "you@example.org"; python refresh_city_site.py`.

Before it takes anything from the County, the refresh stops if a refusal of the pull is on record
("The pull was refused"), then runs the checks `--check` prints and stops on any line marked NO:
`SDFOOD_CONTACT` set, the approval complete and within its sunset, no uncommitted change to a tracked
file, the frozen rule committed, Node installed, and the GitHub CLI installed and signed in. Nothing is
pulled for a list that could not be published. Then it pulls (resuming an interrupted pull from the
last two days, or setting an older one aside and starting over, never one that records a refusal),
exports with the frozen rule, runs the monitor and prints its status and alerts ("Reading the
monitor"), writes the month's worklists, publishes, and waits until Render serves the new commit. It
stops at the first step that fails, except the monitor, which never stops a refresh.

To schedule it weekly, see the command in `refresh_city_site.py`. To stop the scheduled run:
`schtasks /Delete /TN "sdfood refresh" /F`. `--repo OWNER/NAME` and `--dir PATH` pass another deploy
repository and its checkout to the publish, and `--url` is the address it waits for ("Handing the
site over").

| exit | meaning | do |
|---|---|---|
| 0 | refreshed | nothing |
| 1 (`--check`) | a check says NO | fix the lines marked NO |
| 2 | not ready: a check said NO, or `SDFOOD_CONTACT` is not set. Nothing was pulled | fix the lines marked NO (`--check` lists them). If the sunset has passed, take the site down ("Taking it down") |
| 3 | a refusal of the pull is on record. Nothing was pulled | "The pull was refused" |
| 4 | the County's listing ran out before every business appeared | "The pull is incomplete" |
| 5 | the publish pushed, but Render did not serve the new commit within 15 minutes | check the service's Events on Render and `/healthz`. Do not run the refresh again for this (it would pull again); if the deploy failed, "A deploy failed" |
| other | the failing step's own code (the pull, the export, the worklists or the publish) | read its message. Unless the publish printed "pushed", the live site is unchanged. A pull that stopped resumes on the next run; after the pull has finished, run again with `--skip-fetch` |

Checks that stop a publish, and what to do:

| Message | Meaning | Do |
|---|---|---|
| `no docs/STAFF_APPROVAL.json` or `responsible_adult needs ...` | no adult of record or corrections contact | fill in `docs/STAFF_APPROVAL.json` from the example |
| `the sunset date ... has passed` | the site's agreed end date | take the site down ("Taking it down"), or record a City owner and a new date |
| `the sunset date ... is more than a year away` | a release is renewed at least yearly | set a date within a year |
| `built from a partial pull` | the pull did not finish | run `refresh_city_site.py` again (it resumes) |
| `expires ...: fetch and export again first` | the export is too old | refresh |
| `built from uncommitted code` | the list could not be rebuilt from a commit | commit, then export again |
| `... tracked file(s) have uncommitted changes: commit or stash first` | the site's code is taken from HEAD (`git archive`), never from disk, so an uncommitted change would not be what ships | commit, then publish again |
| `the export applies no frozen rule` / `docs/rule.json is not committed` | the first export wrote `docs/rule.json` | read it (`data/site/report.md` explains it), commit it, export again |
| `the export applies rule version X, but the committed docs/rule.json is Y` | the rule changed after the export | export again |
| `stopped: docs/holds.json cannot be read ...` / `... is not in the holds format` | a holds file read as empty would release every hold | fix it: `{"facility_ids": ["DEH2022-FFPP-000001", ...]}` (`docs/holds.example.json`) |
| `docs/holds.json holds X, which is not on the list: did you mean Y?` | a held id differs from a listed one only in case (ids are case-sensitive) | copy the id exactly as the list shows it |
| `NOT APPLIED: ... X is not on the live list, and no publish has held it` (`--holds-only`) | the id matches no listed place, and no publish has ever held it (`ops/holds_applied.json`), so it may be a typo | copy the id from the place's page. If the place has left the list, take the id out of `docs/holds.json` and keep the request in the corrections log |
| `X: the list still carries its points or band` / `X: it has no place file` | a held place would still show its points | export again |
| `the archive of the registered run R is missing` (or `... its hash differs`) | the prospective test scores exactly that file, and nothing can rebuild it | restore `data/site/archive/R/` from the private repository's `ops/archive/` |
| `places against ... live: pass --force` | the new list is more than 10% smaller | find out why; `--force` only for a real change |
| `origin pushes to ...` or `... is PUBLIC` | the deploy repository is not the private one | stop; nothing was pushed |
| `the GitHub CLI (gh) is not installed` | the publish pushes with it | install it, then `gh auth login` |

The export itself stops with `the ... that decide what a point means changed since rule version X was
frozen: refit` when the code that decides what a point means (a data rule, a window, a constant, a
theme) has changed since the rule was frozen: see "Drift, and when the rule needs a refit".

`publish_city_site.py` also warns, and publishes, when: this repository's commit is not pushed (CI has
not run on the code that built the list: push it); an entry in the approval is filled in but not
counted (a date still to come, "tbd", no `by` or `resolution`: fix the entry; `--check` lists these
too); the list was built by another commit than the site (`ops/` keeps the source of both); a held id
is not on the list (the warning says whether a publish held it before, and so saw it leave the list;
if none has, check the id); or the public site's privacy page does not carry the corrections contact's
email, which staff then see as an open item too ("The corrections contact changes").

`export_site.py` warns, and goes on, when a place has more items in its 36-month window than its
place file lists (`MAX_VIOLATIONS`, 150; the most in the September 2026 pull is 83, so none is cut):
that place's page still counts every item by theme, and says its list is cut. Each export also gives
every place's last visit the County's own inspection type (`last_visit.county_type`), which the staff
CSV's `last_visit_type` names beside our reading; a list exported before that has only our reading.

## The pull was refused

`fetch_sdfood.py` exits with code 3 on HTTP 401, 403 or 429, or an HTML page where the data belongs.
That is final:

1. Do not retry, change the User-Agent, or pull from another address. Any written request from the
   County or the site's operator to stop is also final.
2. The refusal is kept on record in `data/PULL_REFUSED.json` (the first one: a later refusal never
   overwrites it). While that file exists, even empty or unreadable, and while a partial pull's meta
   (or a copy of one set aside) records a refusal, `fetch_sdfood.py` and `refresh_city_site.py` stop
   with exit 3 before any request to the County, and `--check` shows it as a NO line.
   `fetch_sdfood.py --csv-only`, which makes no request, still runs. Remove the file only with the
   County's written OK. When the County asks in writing to stop, create the file by hand, for example
   `{"detail": "written request, <date>"}`.
3. Stop the scheduled run: `schtasks /Delete /TN "sdfood refresh" /F` (the refresh prints this too).
4. The last complete pull is untouched (`data/sd_businesses.json`, and `data/pulls/`). The live site
   keeps serving its list until it expires, then shows only a search of the record it holds.
5. Tell the City contact the date the site goes search-only (the watch issue shows it).
6. Ask the County for the data: the records-request template is in [outreach.md](../outreach.md).

## The pull is incomplete

`fetch_sdfood.py` exits with code 4 when the County's listing runs out of pages before every business
it counted has appeared. The partial pull is kept, and nothing is exported from it. Run the refresh
again later: it resumes. If it happens twice in a row, the County's listing may have changed shape:
compare `data/pull_meta.partial.json` with the last complete `data/pull_meta.json` before going on.

## A deploy failed

Render keeps serving the previous deploy. The watch workflow opens an issue within a day. Read the
deploy's log in the Render dashboard (Events), fix the cause, commit the fix (a full publish refuses
uncommitted changes to tracked files), and run `publish_city_site.py --wait
https://sdfood-city.onrender.com` again. When a publish exits 5 ("pushed ..., but ... did not serve it
within 15 minutes"), the push has happened: check Events and `/healthz` before doing anything else.
The build itself checks the export (`scripts/exportGate.mjs`): an expired or malformed export, or a
staff export past its sunset, fails the build, never the live site.

## Bad data went live, or a place must come off at once

**Do not roll back on Render.** A rollback serves an older build that no gate checked today, and it
undoes every hold since. Instead:

- **One place** (an owner's request, an error): add its `facility_id` to `docs/holds.json`
  (`{"facility_ids": [...]}`, as in `docs/holds.example.json`; ids are case-sensitive, so copy it from
  the place's page) and run `python publish_city_site.py --holds-only --wait
  https://sdfood-city.onrender.com`. It changes nothing but the held places, and goes out even when a
  full export could not (an export near expiry, uncommitted code). Every request goes on hold the same
  business day it arrives.
  - It refuses, changing and pushing nothing ("NOT APPLIED"), a held id that is not on the live list
    and that no publish has held, or one that matches a listed id only in case (it names the listed
    one). Every publish records the ids it held while they were on the list in the private repository's
    `ops/holds_applied.json`; an id there whose place has since left the list only gets a warning. What
    was asked for (`ops/holds.json`) does not count: a typo in it never became a hold.
  - It checks that no held place keeps its points or band in the list or in its place file, prints
    `held now: <id>` for each newly held place and how many of the held ids are on the live list, and
    pushes nothing when nothing changed.
  - Check the place on the live site before telling the owner it is on hold.
  - The weekly refresh applies the same holds to the export and the worklists. If the staff API is
    deployed, the same day export again (`python export_site.py`), write each month's worklists the
    image carries again (`python export_worklist.py --month <yyyy-mm>`), and run `python
    deploy_api.py`, which refuses while a held place still shows its points or band in the export or a
    worklist. If the export cannot run that day, suspend the API service (Render dashboard, the
    service, Settings, Suspend) until `deploy_api.py` has shipped the hold, then resume it.
  - The frozen pilot copies (`data/worklists/<month>/frozen/`) are read-only and never changed by a
    hold. They are not served, and the API image leaves them out.
- **The whole list:** suspend the service (Render dashboard, the service, Settings, Suspend). Then find
  the cause, fix it, publish again, and resume.

## Drift, and when the rule needs a refit

Two signals, each against 2 points or 3 standard errors, whichever is larger (`DRIFT_MIN` and
`DRIFT_SE` in `export_site.py`, `meta.drift.thresholds`):

- **The formal check** (`meta.drift.refit_needed`): the routine major rate over the last one or two
  complete quarters that start after the backtest's label year (September 2025 to August 2026),
  against the rate over the label year's own months; or band 1's share of scored City restaurants now,
  against its share in the backtest. A quarter counts once it is over and the County's record has run
  30 days past its end, so the first, October to December 2026, counts from 2027-01-30. Until then the
  rate signal reads "not yet measurable", never a clean result. When it fires, `/healthz` says
  `refit_needed`, the watch fails and opens its issue, and the staff notice tells staff the rates may
  be out of date.
- **The drift note** (`meta.drift.note`), meanwhile: the latest quarter's routine major rate (a
  quarter still under way included) against the rate over the label year's months before that
  quarter, so the two never share an inspection. When they differ by more than the threshold, the site
  shows the note beside every estimate, the staff notice turns it into an instruction (every rate on
  the site is probably low, or high), `/healthz` says `drift_note: true`, and the watch opens "the
  latest quarter's major-violation rate differs from the label year's months before it" without
  failing. A note is not a refit trigger. Read it, and tell the City's requestor or owner of the site,
  once there is one.

The export also stops and asks for a refit when the code that decides what a point means has changed
since the rule was frozen ("Every week: refresh", the note under the table). Then:

```bash
python export_site.py --refit        # chooses and checks the rule afresh; writes a new docs/rule.json
```

Read `data/site/report.md`, commit `docs/rule.json` (its version names its content), export again
without `--refit`, run `python export_site.py --monitor`, and publish. Register the new version for its
own prospective test the same week (`export_site.py --register`, within 14 days of the list's date),
then commit and push `docs/prospective/REGISTERED.json` within those 14 days: the test dates a
registration by GitHub's own record of the push that carried it, and a registration tests only the
rule version it was made for. Never edit `docs/rule.json` by hand. Then say what changed: a dated
entry in the Privacy page's list of changes (`food-dashboard/src/Privacy.jsx`), and a note to the
City's requestor or owner of the site, once there is one; otherwise staff see the new version only
in About.

## Reading the monitor

`export_site.py --monitor` (every refresh runs it after the export) scores every archived list
(`data/site/archive/forward_*`) on the routine inspections made since, the City and outside it apart,
each against its own backtest. It writes `data/site/monitor.md` (the tables), `monitor.json` (every
figure) and `monitor_summary.json`, every time, even before any list can be scored:

- **`status`**: `too early` (no list has a window yet), `interim` (a list has a 90, 180 or 270-day
  window, set against the backtest's rates for the same window, `card.interim`), `complete` (a list's
  whole label year has passed in the record), or `failed` (the `--monitor` step errored, or the publish
  found no summary, one it could not read, or one for another export: its `inspections_through` or
  `rule_version` is not the export's, as after `python export_site.py` with no `--monitor` after it). A
  window counts once the County's record has run 30 days past its end.
- **`alerts`**: one plain sentence per kind of finding, naming the latest list that shows it and how
  many earlier lists do too. Only a list drawn up under the current rule version (its frozen version is
  the one in `docs/rule.json`) raises an alert: lists from an earlier version, or from before any rule
  was frozen, are still scored and listed in `monitor.md`, but raise none, so an alert clears once a
  refit's new version is live:
  - band 1's City rate, over an interim or complete window, with the top of its 95% interval below
    what the backtest expected for that window;
  - on a complete list, the estimates' observed over expected outside 0.85 to 1.15, the City and
    outside it separately;
  - band 1 against the same number of places with the most recent major violations, with the top of
    the difference's 95% interval below 0.
- **`next_window_date`**: the date the County's record must reach for any list's next window (90,
  180, 270 or 365 days, each plus 30), or null once every list is complete.
- **`rule_version`** and **`inspections_through`**: the rule the alerts were read for and the last day
  of the record scored, so the publish can tell this run's summary from an earlier one.
- **`by_district`**: the City by council district on the latest scored list under the current rule
  (also a table in `monitor.md`): per district, the share of later routine inspections that found a
  major, and the same for the bands the backtest's district audit read, with its 95% interval and, on
  a complete list, the audit's rate. Read it with the district audit ([FAIRNESS.md](../FAIRNESS.md));
  it raises no alert, since a district holds about 20 to 150 banded places and one of nine districts
  would cross any fixed line by chance every few lists.

Where it goes: the refresh prints the status and every alert on each run. The publish copies the three
files to the private repository's `ops/` and ships the summary in the staff `meta.json` as `monitor`.
`/healthz` reports `monitor` (the status) and `monitor_alert` (any alert, or `failed`), and the watch
then opens "the monitor has an alert", once while it is open. On the staff site, an alert on a list
the monitor has scored (`interim` or `complete`) becomes an instruction in the staff notice; a
`failed` monitor does not, since it says nothing about the list's rates.

Who reads it: the operator, after every refresh and whenever the watch opens that issue. What to do:

- **`failed`**: the refresh log shows the monitor's error. Fix it, run `python export_site.py
  --monitor`, then publish (`python publish_city_site.py --wait https://sdfood-city.onrender.com`).
  Until then the staff site ships `failed` and the issue stays open.
- **An alert**: read `monitor.md` for the list and the window. Within a week, tell the responsible
  adult and the City's requestor or owner of the site (once there is one), in writing, which list and
  what it found; the staff notice already tells staff. If the same kind of alert shows on a complete
  list, or on two lists in a row, refit ("Drift, and when the rule needs a refit"). After a refit the
  older version's lists raise no alert; if the new version's own lists show the same alert, suspend
  the service and say why.
- **`too early`, or no alert**: nothing, until `next_window_date`.

The prospective test ([MODEL_CARD.md](MODEL_CARD.md)) reads the same `monitor.json` for its
registered list; its result is one of the checks the staff notice lists.

## Sign-ins

- Add a person: generate a token (`python -c "import secrets; print(secrets.token_urlsafe(24))"`), add
  `id:token` to `SITE_USERS`, Save and deploy. Use a pseudonymous id (`u01`, `u02`, ...) and keep the
  list of who is who off the service (the operator keeps it until a City office owns the site): the
  access log then names ids, not people, in a student's Render account. Send the id and token by a
  channel the City approves, and say in the message that they are this site's sign-in id and access
  token, not the person's City account: nobody should type a City password into this site.
- Remove a person: delete their entry, Save and deploy. Do it the day they leave.
- Rotate everything: every 90 days, or at once if a token may have leaked.
- Before the City has recorded its request and TRUST answer (`access_approved`), only the ids in
  `SITE_OPERATORS` (comma-separated) see the named list; every other sign-in sees the Withheld page.
- `SITE_PASSWORD` (user `SITE_USER`, default `city`) is the operator's own older sign-in: never give it
  to anyone. With `SITE_OPERATORS` unset it is an operator only while it is the only sign-in (no
  `SITE_USERS`). Before adding the first `SITE_USERS` entry, add your own id there and name it in
  `SITE_OPERATORS`, in the same save; once it works, remove `SITE_PASSWORD`. (`SITE_OPERATORS` can
  still name the `SITE_PASSWORD` user; name your own id instead.) At startup the server logs a warning
  while `SITE_PASSWORD` is set alongside `SITE_USERS` (saying whether it is an operator), when
  `SITE_OPERATORS` names an id no sign-in has, and when no sign-in is an operator.
- `SITE_CONTACT` is whom to ask for access, shown on the sign-in page ("For access, ask ..."). Without
  it the page says to ask the person who sent the link. Set it on the service, and check `/login`.
- The server refuses to start with a sign-in shorter than 16 characters. After 10 failed sign-ins in 15
  minutes for one name from one address, that name is locked out from that address for the rest of
  the window; other people at the same office are not.
- A session ends after 30 idle minutes, after 10 hours, at "Sign out" (a POST from the site's own
  page: a link from anywhere else only asks), and whenever the service restarts (the free plan sleeps
  after 15 idle minutes, which also signs everyone out). The cookie is `__Host-s`.
- The site's dates are San Diego's: it closes at midnight Pacific after its sunset date.

## The access log

Every sign-in and sign-out, with its network address; every refused sign-in (a wrong id or token, or
too many tries), with the address and the id typed only when it is one of the site's ids (anything
else is logged as `<not an id>`, so a City user name typed by mistake never reaches the log); every
data file fetched (each place's record is its own file, so this shows which places a person opened);
every request answered with the Withheld page; every address lookup (not the address typed); and every
CSV download and print (a list printout with its row count, never the search typed) is logged with the
sign-in's id (`sign-in user=...`, `sign-out user=...`, `sign-in failed user=...`, `sign-in refused
user=...: too many ...`, `access user=...`, a lookup as `access user=... geocode`, `withheld
user=...`, `audit user=... event=csv` or `event=print`) in the service's logs. The sign-in page and the
Withheld page say what is logged, that the operator and anyone with access to the hosting account can
read it, and that a pilot's analysis may use it by sign-in id. On the free plan Render keeps those logs
only briefly and loses them on restart: to keep them, add a log stream (Render dashboard, Workspace
settings, Log Streams) to a store the operator controls (the City's owner of the site, once there is
one).

## The corrections contact changes

Update `corrections_contact` in `docs/STAFF_APPROVAL.json` and publish: the staff site shows it. On the
public site (Render, the static site's Environment) set `VITE_OWNER_CONTACT` to the same address and
choose "Save, rebuild, and deploy": the address is built into the page, and a public build on Render
stops without an email address there. Check that the public site's privacy page shows it. Every staff
publish checks this too: until a script the public page loads carries the corrections contact's email,
the publish warns, and the staff notice lists "the public site does not yet give an owner an email
address to ask whether their business is on this list" as an open item.

## The machine is lost

Anyone with write access to both repositories can run the refresh from a new machine:

1. Install Python, Node 24, git and the GitHub CLI, and run `gh auth login` as an account that can
   push to the private repository. Clone this repository, `pip install -r requirements.txt`, `cd
   food-dashboard && npm ci`.
2. From `ops/` in the private repository, restore `STAFF_APPROVAL.json` and `holds.json` to `docs/`
   (`docs/rule.json` is committed here), `archive/*` to `data/site/archive/`, and `monitor.json`,
   `monitor.md` and `monitor_summary.json` to `data/site/`. The prospective test and the monitor score
   the archived lists, no later export can rebuild them, and a publish refuses while a registered
   list's archive is missing.
3. `python refresh_city_site.py --check`, then `python refresh_city_site.py`. `publish_city_site.py`
   clones the private repository next to this one if it is missing, keeping its deploy history.
   Without a pull backup the pull starts from scratch (about an hour).

If this repository itself is gone, `ops/source.tar.gz` in the private repository is the commit that
built the site (`site_code_sha` in `DEPLOYS.jsonl`), and `ops/export_source.tar.gz`, when it is there,
the commit that built the list (`export_code_sha`): rebuild the list from that one.

## Handing the site over, and taking it down

- **Handover.** The sunset date in `docs/STAFF_APPROVAL.json` is when the site comes down unless a City
  office takes it over. A new owner needs: write access to both repositories and the Render service,
  `ops/` (everything else, the archived lists included), this runbook, and
  [STAFF_SITE.md](STAFF_SITE.md). On another GitHub account or Render service, pass `--repo
  OWNER/NAME`, `--dir PATH` and `--url https://...` to `refresh_city_site.py` (it passes them on to the
  publish), and set the private repository's variable `SITE_URL` to the new address so the daily check
  reads the right site. Record the new owner and a new sunset in `docs/STAFF_APPROVAL.json` and
  publish.
- **Taking it down.** On the sunset date, or at any request from the City, the County, or the adult of
  record:
  1. Stop the scheduled refresh: `schtasks /Delete /TN "sdfood refresh" /F` (after the sunset the
     refresh stops before pulling and prints this command).
  2. Suspend the Render service (the server also closes the data by itself after the sunset: every
     page says the site is closed).
  3. Revoke every `SITE_USERS` entry and `SITE_PASSWORD`, then delete the service. If the staff API
     is deployed, suspend and delete it too (it serves no data past the sunset either).
  4. Keep the private repository private and archived for the City's records schedule; never make it
     public.

## The public repository's history

`tools/purge_history.sh` rewrote the history to remove old facility-level dashboards, and checks
GitHub's pull-request refs afterwards (it exits non-zero, "NOT verified", if it cannot fetch them).
Those refs (`refs/pull/N/head`) are read-only to everyone but GitHub. `refs/pull/1/head` and
`refs/pull/2/head` still reach the old per-restaurant dashboards: the repository's owner must make it
private and ask GitHub Support to remove them ([PUBLISHING.md](PUBLISHING.md), "The research
dashboard, and its history").
