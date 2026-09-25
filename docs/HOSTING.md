# Hosting on Render

Two services in one Render workspace:

| | Staff API | Public site |
|---|---|---|
| What | `api/`: the real export, for City staff; every data request needs a key ([API.md](API.md)) | `food-dashboard/`: the invented sample |
| Render service | Web Service, deployed from an existing image | Static Site |
| Built from | a **private** image on GitHub's container registry (ghcr.io), built on the machine that holds `data/` by `deploy_api.py` | this public repository, on every push to `main` |
| Address | `https://sdfood-api.onrender.com` (the name you choose) | `https://sd-food-safety-risk.onrender.com` |

The real export never goes to GitHub: `/data/` is ignored, and the image that carries it lives in a
private package. The public repository only builds the site, with the sample.

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

**Rolling back.** The service's **Events** page can roll back to an earlier deploy, as long as its
image version is still in the registry, so don't delete recent versions. Roll back to a deploy
`deploy_api.py` made: those name the image by its digest, so they bring back exactly that image. A
deploy that named `latest` (a key change, say) would pull whatever `latest` is now. And `latest`
still points to the newer image, so the next key change brings it back: fix the export and run
`deploy_api.py` again.

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
built `dist/` from a private build (never commit `public/data/`):

```bash
python export_site.py --publish     # writes public/data/ only if every gate passes, stamped
cd food-dashboard && npm run build  # prebuild refuses an unstamped or expired real export
# deploy dist/ from a private build; do not commit public/data/
python food-dashboard/scripts/make_sample_export.py   # put the sample back afterwards
```

A test fails if the committed `public/data/` is not the sample.

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
   - Application restrictions, Websites: `https://sd-food-safety-risk.onrender.com/*` and
     `http://localhost:5173/*`.
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
