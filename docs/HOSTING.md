# Hosting on Render

Three services can run in one Render workspace. The first is what the City uses.

| | City staff site (live) | Staff API (optional) | Public site |
|---|---|---|---|
| What | `food-dashboard/` with the real export, behind a sign-in (`city_site/server.mjs`) | `api/`: the real export as JSON and CSV, every request keyed ([API.md](API.md)) | `food-dashboard/`: the invented sample |
| Render service | Web Service (Node) | Web Service, from an existing image | Static Site |
| Built from | the PRIVATE repository `ChenhaoZhang01/sdfood-city`, written by `publish_city_site.py` | a private image on ghcr.io, built by `deploy_api.py` | this public repository |
| Address | `https://sdfood-city.onrender.com` | `https://sdfood-api.onrender.com` | `https://sdfood.onrender.com` |

The real export never goes to this public repository: `/data/` is ignored, and the copies that carry it
live in a private repository and a private image package.

## 0. The City staff site

Use policy: [STAFF_SITE.md](STAFF_SITE.md). Running it week to week: [RUNBOOK.md](RUNBOOK.md).

### Once: the approval

Copy `docs/STAFF_APPROVAL.example.json` to `docs/STAFF_APPROVAL.json` (gitignored) and fill in a
responsible adult, a corrections contact and a sunset date. `publish_city_site.py` refuses to publish
without them.

### Once: the private repository

`python export_site.py && python publish_city_site.py` creates `ChenhaoZhang01/sdfood-city` (private) on
its first run, and pushes the built site's sources, the real export, `server.mjs`, a record of the
Render settings (`render.yaml`) and a daily check (`.github/workflows/watch.yml`). It refuses to push to
any repository that is not that one, and not private. Then, on GitHub:

- Settings: turn off "Allow forking" (`gh repo edit ChenhaoZhang01/sdfood-city --allow-forking=false`).
  Never make it public: a public repository cannot hide its history.
- Add the co-author and the responsible adult as collaborators, and have them watch the repository, so
  the daily check's issues reach them.

### Once: the Render service

New, Web Service, from the private repository (Render's GitHub App needs access to it):

| Setting | Value |
|---|---|
| Name | `sdfood-city` |
| Region | Oregon (US West) |
| Instance type | Free today (`render.yaml` says so): it sleeps after 15 idle minutes, takes up to a minute to wake, and every sleep signs everyone out and resets the failure counters and caches; Render says Free is not for production. Starter ($7 a month) stays awake |
| Build command | `npm ci && npx vite build` |
| Start command | `node server.mjs` |
| Health check path | `/healthz` (a new deploy that does not answer never replaces the live one) |
| Environment | `NODE_VERSION` = `24`; `SITE_USERS` = `id:token,...` (one per person, pseudonymous ids such as `u01`, tokens 16+ characters); `SITE_CONTACT` = who to ask for access (a role address, shown on the sign-in page); `VITE_GOOGLE_MAPS_API_KEY` and `VITE_GOOGLE_MAPS_MAP_ID` (section 4; add `https://sdfood-city.onrender.com/*` to the key's allowed websites). `SITE_OPERATORS` = the ids that see the named list before the City's request and TRUST answer are on record (default: the `SITE_PASSWORD` user). Never set `SESSION_IDLE_MS`, `SESSION_MAX_MS`, `GEOCODE_UPSTREAM` or `GEOCODE_FAIL_MS` on Render: they exist for the tests |

The build checks the export it ships (`scripts/exportGate.mjs`, in review mode because of the staff
marker file; a staff export past its sunset fails the build) and turns off the offline cache
(`vite.config.js`; the staff build also removes any service worker and cache an earlier version left).

**Signing in.** The server shows its own sign-in page (`/login`) and keeps a session in memory: a
random id in an `HttpOnly; Secure; SameSite=Strict` cookie, ended by "Sign out" (`/logout`), 30 idle
minutes, 10 hours, or any restart (a redeploy, a free-plan sleep, a change to the environment: removing
someone from `SITE_USERS` takes effect then). Because the cookie is `SameSite=Strict`, a link opened
from email or Teams shows the sign-in page even to someone signed in. After 10 failed sign-ins in 15
minutes, one name is locked out from one address (not the whole office); past 300 failures in 15
minutes, every sign-in reply waits 2 seconds. `SITE_PASSWORD` (one shared sign-in, user `city`) still
works while people move to their own; remove it once they have. The server refuses to start if any
sign-in is shorter than 16 characters, and closes the site's data after the sunset date in the
deployed `meta.json`. Turn on two-factor sign-in for the Render and GitHub accounts: anyone who can
open the Render dashboard can read the sign-ins. To keep the access log, add a log stream (RUNBOOK.md).

From a terminal (Basic auth, `curl -u`, no longer works):

```bash
curl -c jar -b jar -d user=u01 --data-urlencode password@- https://sdfood-city.onrender.com/login   # type the token, then Ctrl-D; 303 = signed in
curl -b jar https://sdfood-city.onrender.com/data/meta.json
curl -b jar -c jar -X POST https://sdfood-city.onrender.com/logout
```

### Checks

- `https://sdfood-city.onrender.com/healthz` answers `{"ok": true, "run": ..., "expires": ..., "source": ...,
  "sunset": ..., "closed": null, "refit_needed": false, "rule_version": ..., "access_approved": ...}`.
- The site shows its sign-in page; your sign-in opens it; "Sign out" signs you out, in every browser.
- `curl -i https://sdfood-city.onrender.com/data/meta.json` without a sign-in answers 401.
- The banner at the top of every page names the contact and says, as instructions, what the list has
  not passed.
- The watch workflow (`.github/workflows/watch.yml` in the private repository) runs daily; run it once
  by hand after setup (`gh workflow run watch.yml -R ChenhaoZhang01/sdfood-city`).

## 1. The staff API

### Once: the private registry

1. **A token to push with.** Create a classic personal access token with only `write:packages`:
   <https://github.com/settings/tokens/new?scopes=write:packages&description=sdfood-api%20push>.
   (GitHub's registry does not accept fine-grained tokens, and picking `write:packages` by hand
   also ticks `repo`; the link does not.) Give it an expiry, then log Docker in with it, pasting
   the token when asked for a password (Docker Desktop keeps it in Windows Credential Manager):

   ```bash
   docker login ghcr.io -u <github-user>
   ```

2. **Let `deploy_api.py` read the package's visibility**, so it can refuse to ship to a public
   one. This opens a browser once:

   ```bash
   gh auth refresh -h github.com -s read:packages
   ```

3. **Tell the script where the image goes.** The name must be lowercase, under your own account:

   | variable | value |
   |---|---|
   | `SDFOOD_IMAGE` | `ghcr.io/<github-user, lowercase>/sdfood-api` |

   In PowerShell: `$env:SDFOOD_IMAGE = "ghcr.io/..."` for this window, or
   `[Environment]::SetEnvironmentVariable("SDFOOD_IMAGE", "ghcr.io/...", "User")` to keep it.

4. **The first push.** With a current export in `data/` (section 3):

   ```bash
   python deploy_api.py --no-deploy
   ```

   It builds the image for `linux/amd64` (what Render runs), starts it on Render's port 10000 and
   checks that it serves this export and nothing without a key, pushes it with two tags (the
   export's run and build time, and `latest`), and checks the package is private.

5. **Check it yourself once**, at `https://github.com/users/<github-user>/packages/container/package/sdfood-api`:
   it must say **Private**. Never change that (a public package cannot be made private again), and
   never use "Connect repository" on it: a package linked to this public repository shares the
   repository's read access.

### Once: the Render service

1. **A token for Render to pull with**, separate from yours: a classic token with only
   `read:packages` (<https://github.com/settings/tokens/new?scopes=read:packages&description=render%20pull>).
   Give it an expiry and put the date on a calendar: when it lapses, Render cannot pull the image
   and deploys and restarts fail with "Image Pull Failed".
2. Render dashboard, **Workspace Settings, Container Registry Credentials, Add**: Name `ghcr`,
   Registry GitHub, Username your GitHub user, Token the read-only token.
3. **New, Web Service, Existing Image:**

   | field | value |
   |---|---|
   | Image URL | `ghcr.io/<github-user, lowercase>/sdfood-api:latest` (type the `ghcr.io/` host: without it Render looks on Docker Hub) |
   | Credential | `ghcr`, then Connect |
   | Name | `sdfood-api` (the address becomes `https://sdfood-api.onrender.com` if it is free) |
   | Region | Oregon (US West), the nearest to San Diego |
   | Instance type | Free to try it: it sleeps after 15 minutes without requests and takes about a minute to wake, and Render says Free is not for production. For staff use, the smallest paid type (0.5 CPU, 512 MB, formerly "Starter", $7 a month) stays awake. The API uses about 60 MB. |
   | Environment variable | `SDFOOD_API_KEYS`: the keys, comma-separated (below) |
   | Advanced, Health Check Path | `/health` |

   Leave `PORT` unset: Render sets it to 10000 and the image listens on it.
4. **Check it:** `https://sdfood-api.onrender.com/health` answers `"status": "ok"` with the export's
   run and the image's build. At `/docs`, **Authorize** with a key and try `/v1/summary`.
5. **The deploy hook:** the service's **Settings, Deploy Hook**. Copy it into your environment
   (it is a secret: anyone holding it can redeploy the service; Render can regenerate it):

   | variable | value |
   |---|---|
   | `RENDER_DEPLOY_HOOK_URL` | the deploy hook |
   | `SDFOOD_API_URL` | `https://sdfood-api.onrender.com`, so the script waits until the new image is live |

### Keys: giving and taking back access

Make one key per person or team, so any one can be withdrawn without the others:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put them in `SDFOOD_API_KEYS`, comma-separated, on the service's **Environment** page, and choose
**Save and deploy**. That redeploys `latest`, which is always the last image `deploy_api.py`
checked, so it takes seconds. To withdraw a key, delete it the same way. Send keys by a channel the
City approves, never in a public place.

The key is the only gate: Render's IP allowlists for web services need a Scale or Enterprise
workspace. `/docs` and `/health` are open and carry no data.

### Every refresh

The export expires 14 days after it is made. After that, the API marks every response
`X-Data-Stale: true`, and `deploy_api.py` refuses to ship it. So refresh at least every two weeks:

```bash
SDFOOD_CONTACT=you@example.org python fetch_sdfood.py   # the pull (about an hour; --resume if interrupted)
python export_site.py                                     # data/site/
python export_worklist.py                                 # data/worklists/<month>/
python deploy_api.py                                      # build, check, push, deploy, wait
```

`deploy_api.py` stops, before anything is pushed, if the export is missing, is the sample, is
incomplete or has expired, or if the image does not serve it correctly on port 10000. After the push
it checks again that the package is private. Then it moves `latest` to the new image, has Render
deploy that exact image by its digest through the hook, and waits until `/health` reports the new
build. `--dry-run` prints every step without running any.

**Why `latest`.** When the hook names an image, Render deploys it once. Any later deploy (saving an
environment variable, say) goes back to the Image URL in the service's settings, which is
`latest`. And `latest` only ever moves to an image that passed the checks.

**Never roll back.** A rollback serves an image that no gate checked today, and it undoes every hold
since. Fix the export (or add the hold) and run `deploy_api.py` again; to take the API down at once,
suspend the service.

## 2. The public site

### Before the first build

- **`food-dashboard/` has to be in git**, with its sample in `public/data/`: Render builds from
  GitHub, and the build checks the sample. Commit and push to `main`.
- **Render has to see the repository.** Render reads GitHub through its GitHub App. Only the
  repository's owner can give that app access to a personal repository, so if
  `bushesarebetter/sdfood` is missing from Render's list, the owner adds it under the app's
  Repository access.

### The service's settings

The site already exists on Render. Point it at this repository in its **Settings**, or use the
same values for a new **Static Site**:

| setting | value |
|---|---|
| Source (Build & Deploy, Source, Edit) | `bushesarebetter/sdfood`, branch `main` |
| Root Directory | `food-dashboard` |
| Build Command | `npm ci && npm run build` |
| Publish Directory | `dist` (relative to the root directory) |
| Environment | `NODE_VERSION` = `24`. Set it explicitly: an older service defaults to the Node version from when it was created. `SKIP_INSTALL_DEPS` = `true`: the build command installs from the lockfile itself, so Render need not install first. Also `VITE_GOOGLE_MAPS_API_KEY` and `VITE_GOOGLE_MAPS_MAP_ID` (section 4) |
| Redirects/Rewrites | Source `/*`, Destination `/index.html`, Action **Rewrite** (not Redirect), so a deep link such as `/place/SAMPLE-FFPP-00011` loads the app. Render does not read `vercel.json`. |
| Headers | `/assets/*` `Cache-Control: public, max-age=31536000, immutable`; `/data/*` `Cache-Control: public, max-age=3600, must-revalidate`; `/*` `X-Content-Type-Options: nosniff` and `Referrer-Policy: strict-origin-when-cross-origin` |
| Previews | Off: a preview copies the site's environment and runs the pull request's build scripts |

Vite writes `VITE_*` values into the build, so after changing one choose **Save, rebuild, and
deploy** ("Save and deploy" reuses the old build). A root directory also means only changes under
`food-dashboard/` redeploy the site.

The rewrite also answers a missing `/data/place/<id>.json` with the page (200, `text/html`)
instead of a 404. The site reads that as "no such place".

### Showing real data on it

Don't. Real data is for City staff, through the API. The public site shows it only after every gate
in [PUBLISHING.md](PUBLISHING.md) has passed. Then publish locally, build locally, and deploy the
built `dist/` from a private build. The real export never enters `public/data/` or git:

```bash
python export_site.py --publish     # stages data/site-publish/ (git-ignored) only if every gate passes, stamped
cd food-dashboard && SDFOOD_SITE_DATA=../data/site-publish npm run build
# the build checks that export (expiry and contract, including the stamp) and puts it in dist/data/
# deploy dist/ from a private build
```

The checks run inside the build (`scripts/exportGate.mjs`), on the data the build actually ships,
so `npx vite build` or a config with another `publicDir` cannot skip them. A test fails if the
committed `public/data/` is not provably the sample (ids, names, provenance), not just flagged as one.

## 3. Costs and limits

- **Render.**
  - Static sites are free to deploy but count against the workspace's outbound bandwidth: 5 GB a
    month on Hobby, then $0.15 a GB. Without a payment method, going over spins the services down
    until the next month.
  - Free web services share 750 hours a month per workspace; hours while asleep don't count.
  - The smallest always-on web service is $7 a month.
- **GitHub.** Private container images are currently free to store and pull. GitHub promises a
  month's notice before that changes.

## 4. Google Maps credentials

The site builds without them, but the map shows an error panel.

1. In the Google Cloud console, create a project and **enable billing** (Maps serves
   degraded, watermarked tiles without it, even inside the free allowance).
2. Enable exactly: **Maps JavaScript API** (basemap and deck.gl overlay), **Street View
   Static API** (the pano in the place panel), **Places API (New)** (address suggestions in
   "Near an address") and **Geocoding API** (an address typed rather than picked).
3. Create an API key and restrict it:
   - Application restrictions, Websites: `https://sdfood.onrender.com/*`,
     `https://sdfood-city.onrender.com/*` and `http://localhost:5173/*`.
   - API restrictions: the four APIs above. A key restricted to fewer fails with
     `REQUEST_DENIED` on the missing ones.
   The key is necessarily visible in the client bundle; the referrer restriction is what
   protects it.
4. Google Maps Platform, Map Management: create a **Map ID** (JavaScript, Vector). deck.gl's
   overlay needs vector rendering, and map styling lives on the Map ID.
5. Set a **daily quota cap** on Maps JavaScript and Street View Static and a **$1 budget alert** in
   Google Cloud billing. Maps bills per SKU with a monthly free allowance per API. The referrer
   restriction is the real defence; the cap and the alert are how you find out if it failed.
   Prices: <https://developers.google.com/maps/billing-and-pricing/pricing>.

If the site moves to another domain, change `siteUrl` in `src/site.js`, the `og:url` and `og:image`
tags in `index.html`, and the key's referrer list.

## 5. Before sending anyone a link

Staff API:
- [ ] `/health` shows `"status": "ok"` and `"stale": false`
- [ ] `/v1/summary` answers 401 without a key and 200 with one
- [ ] The package page on GitHub says Private
- [ ] The Render pull token's expiry is on a calendar

Public site:
- [ ] The map renders with the Map ID's style, not the "for development purposes only" watermark
- [ ] A deep link such as `/place/SAMPLE-FFPP-00011` loads the app (the rewrite works)
- [ ] The browser console is clean, in particular no `RefererNotAllowedMapError`
- [ ] It works on a phone
- [ ] The data is the sample
- [ ] The Google Cloud budget alert is set
