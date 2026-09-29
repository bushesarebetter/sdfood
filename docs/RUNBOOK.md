# Runbook: keeping the City staff site running

For whoever runs the refresh. What the site is for, and who may use it: [STAFF_SITE.md](STAFF_SITE.md).
How it was set up: [HOSTING.md](HOSTING.md), "The City staff site".

## What is live

| Piece | Where |
|---|---|
| The site | `https://sdfood-city.onrender.com`, a Render web service (`sdfood-city`), Node, `node server.mjs` |
| Its code and data | the PRIVATE repository `ChenhaoZhang01/sdfood-city`, written only by `publish_city_site.py` |
| What it takes to rebuild it | `ops/` in that repository (not served): the source that built the list, the frozen rule, the pull's meta, the approval and the holds |
| Sign-ins | the service's `SITE_USERS` (one `name:token` per person); a form sign-in with a session that ends after 30 idle minutes or 10 hours |
| Health | `https://sdfood-city.onrender.com/healthz`: open, no data; says which export (`run`, `expires`), commit (`source`) and rule version are live, whether the site is `closed`, and whether the rule needs a refit |
| Daily check | `.github/workflows/watch.yml` in the private repository: opens an issue (one per problem, never duplicates) when Render is not serving the latest commit, the export is stale or expires soon, the site is closed, the rule needs a refit, the sunset is near, or the data answers without a sign-in |
| The pipeline | this repository, on one machine: `fetch_sdfood.py`, `export_site.py`, `export_worklist.py`, `publish_city_site.py`, or all of them as `refresh_city_site.py` |
| The frozen rule | `docs/rule.json`, committed: every export applies it unchanged |
| Deploy log | `DEPLOYS.jsonl` in the private repository and `data/staff_deploys.jsonl` here: every publish, with its run, commit, who ran it, what it had not passed, and what was on hold |

## Every week: refresh

An export stays current for about 13 days after its pull: it expires 14 days after the County's record
ends, and the record lags the pull by about a day. Refresh weekly. First check that everything a
refresh needs is in place (this changes nothing):

```bash
python refresh_city_site.py --check
SDFOOD_CONTACT=you@example.org python refresh_city_site.py      # about an hour, mostly the pull
```

On Windows (PowerShell): `$env:SDFOOD_CONTACT = "you@example.org"; python refresh_city_site.py`.

It pulls (resuming an interrupted pull from the last two days, or setting an older one aside and
starting over), exports with the frozen rule, scores earlier lists against what happened since (the
monitor, `data/site/monitor.md`), writes the month's worklists, publishes, and waits until Render serves
the new commit. It stops at the first step that fails; the live site is unchanged until the publish
succeeds. To schedule it, see the command in `refresh_city_site.py`.

Checks that stop a publish, and what to do:

| Message | Meaning | Do |
|---|---|---|
| `no docs/STAFF_APPROVAL.json` or `responsible_adult needs ...` | no adult of record or corrections contact | fill in `docs/STAFF_APPROVAL.json` from the example |
| `the sunset date ... has passed` | the site's agreed end date | take the site down ("Taking the site down"), or record a City owner and a new date |
| `the sunset date ... is more than a year away` | a release is renewed at least yearly | set a date within a year |
| `built from a partial pull` | the pull did not finish | run `refresh_city_site.py` again (it resumes) |
| `expires ...: fetch and export again first` | the export is too old | refresh |
| `built from uncommitted code` | the list could not be rebuilt from a commit | commit, then run it again |
| `the export applies no frozen rule` / `docs/rule.json is not committed` | the first export wrote `docs/rule.json` | read it (`data/site/report.md` explains it), commit it, export again |
| `the export applies rule version X, but the committed docs/rule.json is Y` | the rule changed after the export | export again |
| `places against ... live: pass --force` | the new list is more than 10% smaller | find out why; `--force` only for a real change |
| `origin pushes to ...` or `... is PUBLIC` | the deploy repository is not the private one | stop; nothing was pushed |

`publish_city_site.py` also warns (and publishes) when this repository's commit is not pushed: CI has
not run on the code that built the list. Push it.

## The pull was refused

`fetch_sdfood.py` exits with code 3 on HTTP 401, 403 or 429, or an HTML page where the data belongs.
That is final:

1. Do not retry, change the User-Agent, or pull from another address. Any written request from the
   County or the site's operator to stop is also final.
2. The last complete pull is untouched (`data/sd_businesses.json`, and `data/pulls/`). The live site
   keeps serving its list until it expires, then shows only a search of the record it holds.
3. Tell the City contact the date the site goes search-only (the watch issue shows it).
4. Ask the County for the data: the records-request template is in [outreach.md](../outreach.md).

## The pull is incomplete

`fetch_sdfood.py` exits with code 4 when the County's listing runs out of pages before every business
it counted has appeared. The partial pull is kept, and nothing is exported from it. Run the refresh
again later: it resumes. If it happens twice in a row, the County's listing may have changed shape:
compare `data/pull_meta.partial.json` with the last complete `data/pull_meta.json` before going on.

## A deploy failed

Render keeps serving the previous deploy. The watch workflow opens an issue within a day. Read the
deploy's log in the Render dashboard (Events), fix, and run `publish_city_site.py` again. The build
itself checks the export (`scripts/exportGate.mjs`): an expired or malformed export, or a staff export
past its sunset, fails the build, never the live site.

## Bad data went live, or a place must come off at once

**Do not roll back on Render.** A rollback serves an older build that no gate checked today, and it
undoes every hold since. Instead:

- **One place** (an owner's request, an error): add its `facility_id` to `docs/holds.json` and run
  `python publish_city_site.py --holds-only`. It changes nothing but the held places, and goes out
  even when a full export could not (an export near expiry, uncommitted code). Every request goes on
  hold the same business day it arrives.
- **The whole list:** suspend the service (Render dashboard, the service, Settings, Suspend). Then find
  the cause, fix it, publish again, and resume.

## The rule needs a refit

`/healthz` says `refit_needed`, the watch opens an issue, and the staff banner tells staff, when the
County's record has moved away from the backtest (the routine major rate of the last two full quarters,
or band 1's share of scored City restaurants, more than 5 points from the backtest's). Then:

```bash
python export_site.py --refit        # chooses and checks the rule afresh; writes a new docs/rule.json
```

Read `data/site/report.md`, commit `docs/rule.json` (its version names its content), export again
without `--refit`, and publish. Register the new version for its own prospective test
(`export_site.py --register`, then commit `docs/prospective/REGISTERED.json`): a registration tests
only the rule version it was made for. Never edit `docs/rule.json` by hand.

## Sign-ins

- Add a person: generate a token (`python -c "import secrets; print(secrets.token_urlsafe(24))"`), add
  `id:token` to `SITE_USERS`, Save and deploy. Use a pseudonymous id (`u01`, `u02`, ...) and let the
  City's owner of the site keep the list of who is who: the access log then names ids, not people, in a
  student's Render account. Send the token by a channel the City approves.
- Remove a person: delete their entry, Save and deploy. Do it the day they leave.
- Rotate everything: every 90 days, or at once if a token may have leaked.
- `SITE_PASSWORD`, the older shared sign-in, defeats the per-person log: remove it once everyone has
  their own.
- The server refuses to start with a sign-in shorter than 16 characters. After 10 failed sign-ins in 15
  minutes for one name from one address, that name is locked out from that address for the rest of
  the window; other people at the same office are not.
- A session ends after 30 idle minutes, after 10 hours, at "Sign out", and whenever the service
  restarts (the free plan sleeps after 15 idle minutes, which also signs everyone out).

## The access log

Every data request, every CSV download and every print is logged with the sign-in's id
(`access user=...`, `audit user=... event=csv`) in the service's logs. On the free plan Render keeps
those logs only briefly and loses them on restart: to keep them, add a log stream (Render dashboard,
Workspace settings, Log Streams) to a store the City's owner controls. The log shows which files were
fetched, not which places a person looked at: the list itself loads every name and band at once.

## The machine is lost

Anyone with write access to both repositories can run the refresh from a new machine:

1. Clone this repository, `pip install -r requirements.txt`, `cd food-dashboard && npm ci`.
2. Restore `docs/STAFF_APPROVAL.json` and `docs/holds.json` from `ops/` in the private repository
   (`docs/rule.json` is committed here).
3. `python refresh_city_site.py --check`, then `python refresh_city_site.py`. `publish_city_site.py`
   clones the private repository next to this one if it is missing, keeping its deploy history.
   Without a pull backup the pull starts from scratch (about an hour).

If this repository itself is gone, `ops/source.tar.gz` in the private repository is the code that
built the live list.

## Handing the site over, and taking it down

- **Handover.** The sunset date in `docs/STAFF_APPROVAL.json` is when the site comes down unless a City
  office takes it over. A new owner needs: write access to both repositories and the Render service,
  `ops/` (everything else), this runbook, and [STAFF_SITE.md](STAFF_SITE.md). Record the new
  owner and a new sunset in `docs/STAFF_APPROVAL.json` and publish.
- **Taking it down.** On the sunset date, or at any request from the City, the County, or the adult of
  record: suspend the Render service (the server also closes the data by itself after the sunset:
  every page says the site is closed), revoke every `SITE_USERS` entry, then delete the service. Keep
  the private repository private and archived for the City's records schedule; never make it public.

## The public repository's history

`tools/purge_history.sh` rewrote the history to remove old facility-level dashboards, and checks
GitHub's pull-request refs afterwards (it exits non-zero, "NOT verified", if it cannot fetch them).
Those refs (`refs/pull/N/head`) are read-only to everyone but GitHub. `refs/pull/1/head` and
`refs/pull/2/head` still reach the old per-restaurant dashboards: the repository's owner must make it
private and ask GitHub Support to remove them ([PUBLISHING.md](PUBLISHING.md), "The research
dashboard, and its history").
