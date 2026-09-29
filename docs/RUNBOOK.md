# Runbook: keeping the City staff site running

For whoever runs the refresh. What the site is for, and who may use it: [STAFF_SITE.md](STAFF_SITE.md).
How it was set up: [HOSTING.md](HOSTING.md), "The City staff site".

## What is live

| Piece | Where |
|---|---|
| The site | `https://sdfood-city.onrender.com`, a Render web service (`sdfood-city`), Node, `node server.mjs` |
| Its code and data | the PRIVATE repository `ChenhaoZhang01/sdfood-city`, written only by `publish_city_site.py` |
| Sign-ins | the service's `SITE_USERS` (one `name:token` per person) and `SITE_PASSWORD` (the older shared one) |
| Health | `https://sdfood-city.onrender.com/healthz`: open, no data; says which export (`run`, `expires`) and commit (`source`) are live |
| Daily check | `.github/workflows/watch.yml` in the private repository: opens an issue when Render is not serving the latest commit, or the export expires in under 4 days |
| The pipeline | this repository, on one machine: `fetch_sdfood.py`, `export_site.py`, `export_worklist.py`, `publish_city_site.py`, or all four as `refresh_city_site.py` |
| Deploy log | `data/staff_deploys.jsonl`: every publish, with its run, commit, who ran it, and the gates it did not pass |

## Every week: refresh

An export stays current for about 9 days after its pull (it expires 14 days after the County's record
ends, and the record lags the pull by about 5 days). Refresh weekly:

```bash
SDFOOD_CONTACT=you@example.org python refresh_city_site.py      # about an hour, mostly the pull
```

It pulls (resuming a pull that was interrupted), exports, writes the month's worklists, publishes, and
waits until Render serves the new commit. It stops at the first step that fails; the live site is
unchanged until the publish succeeds. To schedule it, see the command in `refresh_city_site.py`.

Checks that stop a publish, and what to do:

| Message | Meaning | Do |
|---|---|---|
| `no docs/STAFF_APPROVAL.json` or `responsible_adult needs ...` | no adult of record or corrections contact | fill in `docs/STAFF_APPROVAL.json` from the example |
| `the sunset date ... has passed` | the site's agreed end date | take the site down, or record a City owner and a new date |
| `built from a partial pull` | the pull did not finish | run `refresh_city_site.py` again (it resumes) |
| `expires ...: fetch and export again first` | the export is too old | refresh |
| `built from uncommitted code` | the list could not be rebuilt from a commit | commit, then run it again |
| `places against ... live: pass --force` | the new list is more than 10% smaller | find out why; `--force` only for a real change |
| `origin pushes to ...` or `... is PUBLIC` | the deploy repository is not the private one | stop; nothing was pushed |

## The pull was refused

`fetch_sdfood.py` exits with code 3 on HTTP 401, 403 or 429, or an HTML page where the data belongs.
That is final:

1. Do not retry, change the User-Agent, or pull from another address. Any written request from the
   County or the site's operator to stop is also final.
2. The last complete pull is untouched (`data/sd_businesses.json`, and `data/pulls/`). The live site
   keeps serving its list until it expires, then shows only a search of the record it holds.
3. Tell the City contact the date the site goes search-only (the watch issue shows it).
4. Ask the County for the data: the records-request template is in [outreach.md](../outreach.md).

## A deploy failed

Render keeps serving the previous deploy. The watch workflow opens an issue within a day. Read the
deploy's log in the Render dashboard (Events), fix, and run `publish_city_site.py` again. The build
itself checks the export (`scripts/exportGate.mjs`): an expired or malformed export fails the build,
never the live site.

## Bad data went live

Render dashboard, the service, Events: roll back to the previous deploy (seconds). Then find the cause,
fix it, and publish again. A single place that must come off at once: add its `facility_id` to
`docs/holds.json` and run `publish_city_site.py` (no rebuild needed).

## Sign-ins

- Add a person: generate a token (`python -c "import secrets; print(secrets.token_urlsafe(24))"`), add
  `name:token` to `SITE_USERS`, Save and deploy. Send the token by a channel the City approves.
- Remove a person: delete their entry, Save and deploy. Do it the day they leave.
- Rotate everything: every 90 days, or at once if a token may have leaked.
- The server refuses to start with a sign-in shorter than 16 characters, and blocks a client after 10
  failed sign-ins in 15 minutes.

## The machine is lost

Anyone with write access to both repositories can run the refresh from a new machine: clone this
repository, `pip install -r requirements.txt`, `cd food-dashboard && npm ci`, restore
`docs/STAFF_APPROVAL.json` and (if you have it) the latest `data/pulls/` backup, then
`python refresh_city_site.py`. Without a backup the pull starts from scratch (about an hour).

## The public repository's history

`tools/purge_history.sh` rewrote the history to remove old facility-level dashboards, and now checks
GitHub's pull-request refs afterwards. Those refs (`refs/pull/N/head`) are read-only to everyone but
GitHub: if any still reaches a removed file, make the repository private and ask GitHub Support to
remove them ([PUBLISHING.md](PUBLISHING.md), "The research dashboard, and its history").
