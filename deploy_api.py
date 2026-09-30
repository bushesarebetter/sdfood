"""Ship the staff API: build its image with the current export baked in, run it locally the way
Render will and check it, push it to the private registry, and tell Render to deploy exactly that
image. Setup, once: docs/HOSTING.md, "The staff API on Render".

    python deploy_api.py                 # build, check, push, deploy, wait until it is live
    python deploy_api.py --no-deploy     # build, check and push; deploy from Render's dashboard
    python deploy_api.py --no-push       # build and check only (nothing leaves this machine)
    python deploy_api.py --dry-run       # print the steps; run nothing

Set in the environment, never in the repository:
  SDFOOD_IMAGE             the private image repository, e.g. ghcr.io/<github-user>/sdfood-api
  RENDER_DEPLOY_HOOK_URL   the service's deploy hook (Render: the service's Settings, Deploy Hook).
                           It is a secret: anyone holding it can redeploy the service.
  SDFOOD_API_URL           optional: the service's address, to wait until it serves the new image

Refuses, before anything is pushed, when:
  * the staff release's approval (docs/STAFF_APPROVAL.json) is missing, incomplete or past its
    sunset, or the City's request and TRUST answer are not on record (access_approved): the API
    serves the same named list as the staff site, and it has no operator-only view, so every key
    holder would get the whole list;
  * docs/holds.json cannot be read, or a place on hold still carries points or a band, in the export
    (a hold added after the export: export again) or in a worklist the image carries
    (data/worklists/<month>/district-<n>.csv: write that month's worklists again);
  * data/site holds no export, the invented sample, an incomplete export or an expired one;
  * the worklists or data/research_results.json are missing (the image carries both);
  * the registry package exists and is not private (the image holds the export);
  * the built image does not serve this export on Render's port, or serves data without a key.
Before the build it writes data/site/api_release.json (RELEASE_FILE): the approval's sunset, access_approved
and the held ids, and removes it once the build has read it. The image carries it (api/Dockerfile names
it, so a build without it stops), and the API serves no data past that sunset, without access_approved,
or without the file at all (503, as the staff site closes itself), and /health says so; the local check
refuses an image whose /health does not report that sunset. This script is the only way to build and
ship the image.
After the push it checks again that the package is private, moves the `latest` tag to the new image
and deploys it by digest, so Render runs exactly the image that was checked. The Render service's
Image URL names `latest`: Render goes back to that for any later deploy (saving an environment
variable, say), so it must always be the last image this script checked."""
import argparse, csv, json, os, re, secrets, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "data" / "site"
WORKLISTS = ROOT / "data" / "worklists"
RESEARCH = ROOT / "data" / "research_results.json"
RENDER_PORT = 10000        # the PORT Render sets by default; the local check runs the image on it
SERVICE_TAG = "latest"     # the tag the Render service's Image URL names
LIVE_TIMEOUT = 900         # seconds to wait for Render to serve the new image
RELEASE_FILE = "api_release.json"   # in data/site: what the image may serve, and until when (api/main.py reads it)
# A worklist's `why` that gives the points or band away: "12 points", "band 1".
POINTS_OR_BAND = re.compile(r"\b\d+(?:\.\d+)?\s+points?\b|\bband\s+\d", re.I)


class Refused(Exception):
    """A check failed; nothing after it runs."""


def preflight(site=SITE, worklists=WORKLISTS, research=RESEARCH, today=None, allow_expired=False):
    """The export the image would carry must be real, complete and current. Returns its meta.json."""
    meta_file = site / "meta.json"
    if not meta_file.is_file():
        raise Refused(f"no export in {site}: run export_site.py first")
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    if meta.get("sample"):
        raise Refused(f"{site} holds the invented sample, not an export of the County's record")
    if not (site / "facilities.geojson").is_file() or not (site / "place").is_dir():
        raise Refused(f"the export in {site} is incomplete: run export_site.py again")
    if not any(worklists.glob("*/manifest.json")):
        raise Refused(f"no worklists in {worklists}: run export_worklist.py first")
    if not research.is_file():
        raise Refused(f"{research} is missing: run model_food.py and sim_schedule.py first")
    expires = meta.get("expires")
    today = (today or date.today()).isoformat()
    if not allow_expired and (not expires or today > expires):    # the API's own test for stale
        raise Refused(f"the export expired on {expires}: fetch and export again, or pass --allow-expired")
    return meta


def worklist_hold_problems(worklists, held):
    """Held places in a worklist the image carries (data/worklists/<month>/district-<n>.csv; the frozen
    pilot copies are not served) that still show points or a band: rule_points or rule_mean filled in,
    or a `why` that states the points or the band."""
    bad = []
    for path in sorted(worklists.glob("*/district-*.csv")):
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                fid = (row.get("facility_id") or "").lstrip("'")
                if fid in held and ((row.get("rule_points") or "").strip() or (row.get("rule_mean") or "").strip()
                                    or POINTS_OR_BAND.search(row.get("why") or "")):
                    bad.append(f"{path.parent.name}/{path.name}: {fid}")
    return bad


def release_problems(site=SITE, today=None, approval=None, holds=None, worklists=None):
    """The staff site's own release gates, for the image that carries the same list: an adult of
    record, a corrections contact, a sunset date; the City's request and TRUST answer on record (the
    API has no operator-only view); and every hold applied, in the export and in the worklists shipped."""
    import publish_city_site as pcs
    today = today or date.today()
    approval = pcs._json(pcs.APPROVAL, None) if approval is None else approval
    p = pcs.approval_problems(approval, today)
    if not pcs.access_approved(approval, today):
        p.append("no City request and TRUST answer are on record (access_approved in docs/STAFF_APPROVAL.json): the API "
                 "has no operator-only view, so every key holder would get the named list")
    if holds is None:
        held, problem = pcs.read_holds()
        if problem:
            p.append(problem)
    else:
        held = set(holds)
    if held:
        fc = json.loads((site / "facilities.geojson").read_text(encoding="utf-8"))
        still = sorted(f["properties"]["facility_id"] for f in fc.get("features", [])
                       if f["properties"]["facility_id"] in held and ("band" in f["properties"] or "points" in f["properties"]))
        if still:
            p.append(f"{len(still)} place(s) on hold still carry points or a band in {site} ({', '.join(still[:3])}): "
                     "export again, then deploy")
        rows = worklist_hold_problems(WORKLISTS if worklists is None else worklists, held)
        if rows:
            p.append(f"{len(rows)} worklist row(s) of a place on hold still carry its points or band ({', '.join(rows[:3])}): "
                     "write those months' worklists again (python export_worklist.py --month <yyyy-mm>), then deploy")
    return p


def release_record(approval, held, today=None):
    """What the image may serve, and until when: api/main.py reads it from data/site/api_release.json."""
    import publish_city_site as pcs
    today = today or date.today()
    return {"sunset": (approval or {}).get("sunset"), "access_approved": pcs.access_approved(approval, today),
            "held": sorted(held), "written": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}


def write_release(site, release, dry=False):
    """data/site/api_release.json, which the image carries (api/Dockerfile copies data/site/)."""
    path = site / RELEASE_FILE
    print(f"$ write {path} (sunset {release['sunset']}, access_approved {release['access_approved']}, "
          f"{len(release['held'])} held)", flush=True)
    if not dry:
        path.write_text(json.dumps(release, indent=2), encoding="utf-8")


def clear_release(site, dry=False):
    """Remove data/site/api_release.json once the build has read it: it is on disk only while this script
    builds, so an image built by hand later, from a release this script checked another day, stops at the
    Dockerfile's COPY of it instead."""
    if not dry:
        (site / RELEASE_FILE).unlink(missing_ok=True)


def check_image_name(image):
    """The repository alone, as registries spell it: lowercase, no tag, no digest."""
    if not image:
        raise Refused("set SDFOOD_IMAGE (for example ghcr.io/<github-user>/sdfood-api) or pass --image")
    last = image.rsplit("/", 1)[-1]
    if image != image.lower() or "/" not in image or ":" in last or "@" in image:
        raise Refused(f"--image {image!r}: give the repository only, lowercase, without a tag or digest")
    return image


def build_tag(meta, now=None):
    """forward_2026-09-20-20260924T213000Z: the export's run, and when this image was built."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"{meta['run']}-{stamp}"


# ── the registry ──────────────────────────────────────────────────────────────────────────

def _gh(args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, cwd=ROOT).stdout


def registry_host(image):
    """(host, path) as Docker reads a repository name: the first component is a registry host only if
    it has a dot or a colon or is localhost (so "someone/x" is Docker Hub). A port is dropped."""
    first, _, rest = image.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        return first.split(":", 1)[0].lower(), rest
    return "docker.io", image


def github_package(image):
    """(owner, name) for a GitHub Container Registry image; None for any other registry."""
    host, path = registry_host(image)
    if host != "ghcr.io" or "/" not in path:
        return None
    owner, name = path.split("/", 1)
    return owner, name


def package_visibility(image, gh=_gh):
    """The GitHub package's visibility ('private', 'public' or 'internal'); None before its first push."""
    owner, name = github_package(image)
    me = gh(["api", "user", "--jq", ".login"]).strip().lower()
    base = "/user" if owner == me else f"/orgs/{owner}"
    try:
        return gh(["api", f"{base}/packages/container/{urllib.parse.quote(name, safe='')}",
                   "--jq", ".visibility"]).strip()
    except subprocess.CalledProcessError as e:
        if "HTTP 404" in (e.stderr or ""):
            return None
        raise Refused("could not read the package's visibility on GitHub "
                      f"({(e.stderr or '').strip()}). Grant the scopes: gh auth refresh -s read:packages,write:packages")


def ensure_private(image, pushed, gh=_gh, confirmed_private=False):
    """The image holds the export, so its package must be private (a new GitHub package is). On any
    other registry this script cannot check, so it refuses unless the operator confirms it."""
    if github_package(image) is None:
        host, _ = registry_host(image)
        if not confirmed_private:
            raise Refused(f"{image} is on {host}, where this script cannot check that the repository is private "
                          "(new Docker Hub repositories are public). Use ghcr.io, or create the repository as "
                          "private yourself and pass --registry-is-private")
        print(f"note: {image} is on {host}; you confirmed that repository is private")
        return
    vis = package_visibility(image, gh)
    if vis == "private" or (vis is None and not pushed):
        return
    if vis is None:
        raise Refused(f"pushed, but GitHub does not list the package for {image}: check it is private before deploying")
    raise Refused(f"the package for {image} is {vis}, and GitHub cannot make a public package private again. "
                  "Delete it now (GitHub: your profile, Packages, the package, Package settings, Delete this "
                  "package), then push to a new name, which starts private")


# ── docker and http ───────────────────────────────────────────────────────────────────────

def sh(cmd, dry=False, capture=False):
    print("$ " + " ".join(cmd), flush=True)
    if dry:
        return ""
    return subprocess.run(cmd, check=True, text=True, capture_output=capture, cwd=ROOT).stdout or ""


def http(url, headers=None, method="GET", timeout=30):
    """(status, parsed JSON or None). Never raises on an HTTP error status."""
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, body = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read()
    try:
        return status, json.loads(body)
    except ValueError:
        return status, None


def wait_for(fetch, done, timeout, every=2.0):
    """Call fetch() until done(result); the last result, or None on timeout."""
    end = time.monotonic() + timeout
    while True:
        try:
            got = fetch()
            if done(got):
                return got
        except OSError:
            pass
        if time.monotonic() > end:
            return None
        time.sleep(every)


def check_served(base, meta, build, key, get=http, release=None):
    """What Render will be asked to run: this export and build, carrying this release's sunset (so it
    closes itself on time), and nothing without a key."""
    status, h = get(f"{base}/health")
    if status != 200 or (h or {}).get("status") != "ok":
        raise Refused(f"/health answered {status} {h}")
    want = {"run": meta["run"], "places": meta["places"], "build": build,
            **({"sunset": release["sunset"]} if release is not None else {})}
    got = {k: h.get(k) for k in want}
    if got != want:
        raise Refused(f"the image serves {got}, expected {want}")
    if get(f"{base}/v1/summary")[0] != 401:
        raise Refused("the image served /v1/summary without a key")
    status, months = get(f"{base}/v1/worklists", {"X-API-Key": key})
    if status != 200 or not months:
        raise Refused(f"/v1/worklists answered {status} with {months!r}: the image has no worklists")


def smoke_test(ref, meta, build, dry, release=None):
    """Run the image as Render will (PORT set, a key configured) and check what it serves."""
    key = secrets.token_urlsafe(18)   # a throwaway key for this local check only
    cid = sh(["docker", "run", "-d", "--rm", "-e", f"PORT={RENDER_PORT}", "-e", f"SDFOOD_API_KEYS={key}",
              "-p", f"127.0.0.1::{RENDER_PORT}", ref], dry, capture=True).strip()
    if dry:
        return
    try:
        port = sh(["docker", "port", cid, str(RENDER_PORT)], capture=True).splitlines()[0].rsplit(":", 1)[1]
        base = f"http://127.0.0.1:{port}"
        if wait_for(lambda: http(f"{base}/health", timeout=5), lambda r: r[0] == 200, timeout=90) is None:
            out = subprocess.run(["docker", "logs", cid], capture_output=True, text=True)
            logs = (out.stdout + out.stderr)[-2000:]
            raise Refused(f"the image did not answer on port {RENDER_PORT} within 90 s:\n{logs}")
        check_served(base, meta, build, key, release=release)
        print(f"checked: the image serves {meta['run']} ({meta['places']} places) on port {RENDER_PORT}, "
              "and nothing without a key")
    finally:
        subprocess.run(["docker", "stop", cid], capture_output=True)


def pushed_digest(image, ref):
    """image@sha256:...: the exact image just pushed."""
    digests = json.loads(sh(["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", ref], capture=True))
    for d in digests or []:
        if d.split("@", 1)[0] == image:
            return d
    raise Refused(f"docker lists no digest for {image} after the push: {digests}")


def hook_url(hook, image_ref):
    """The deploy hook, told which image to deploy (Render's imgURL parameter, URL-encoded)."""
    parts = urllib.parse.urlsplit(hook)
    if parts.scheme != "https" or not parts.netloc:
        raise Refused("RENDER_DEPLOY_HOOK_URL is not an https URL")
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k != "imgURL"]
    query.append(("imgURL", image_ref))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query, quote_via=urllib.parse.quote)))


def deploy(hook, image_ref, dry, post=http):
    print(f"$ POST <RENDER_DEPLOY_HOOK_URL>&imgURL={image_ref}", flush=True)   # the hook itself is a secret
    if dry:
        return
    status, body = post(hook_url(hook, image_ref), method="POST")
    if status not in (200, 202):   # 202: queued behind a deploy already running
        why = {400: "a bad imgURL", 401: "a wrong hook key", 404: "an unknown service or image", 409: "a suspended service"}
        raise Refused(f"Render's deploy hook answered {status} ({why.get(status, 'see the service on Render')}): {body}")
    body = body if isinstance(body, dict) else {}
    dep = (body.get("deploy") or {}).get("id") or body.get("id")
    print(f"Render {'queued' if status == 202 else 'accepted'} the deploy{f' ({dep})' if dep else ''}")


def wait_live(api_url, build, timeout=LIVE_TIMEOUT):
    """Until the service's /health reports the new build (a sleeping free instance wakes on the first call)."""
    print(f"waiting for {api_url} to serve {build} (up to {timeout // 60} min)", flush=True)
    got = wait_for(lambda: http(f"{api_url.rstrip('/')}/health", timeout=60),
                   lambda r: r[0] == 200 and (r[1] or {}).get("build") == build, timeout, every=15)
    if got is None:
        raise Refused(f"{api_url} did not serve {build} within {timeout // 60} min: check the deploy's logs on Render")
    print(f"live: {api_url} serves {got[1]['run']}, {got[1]['places']} places, build {build}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--image", default=os.environ.get("SDFOOD_IMAGE"),
                    help="the private image repository (default: $SDFOOD_IMAGE)")
    ap.add_argument("--no-push", action="store_true", help="build and check only")
    ap.add_argument("--no-deploy", action="store_true", help="push, but do not call Render's deploy hook")
    ap.add_argument("--dry-run", action="store_true", help="print the steps; run nothing")
    ap.add_argument("--allow-expired", action="store_true", help="ship an export past its expiry date")
    ap.add_argument("--registry-is-private", action="store_true",
                    help="for a registry other than ghcr.io: you have made the repository private yourself")
    args = ap.parse_args(argv)
    dry = args.dry_run
    try:
        image = check_image_name(args.image)
        meta = preflight(SITE, WORKLISTS, RESEARCH, allow_expired=args.allow_expired)
        import publish_city_site as pcs
        approval = pcs._json(pcs.APPROVAL, None)
        problems = release_problems(SITE, approval=approval, worklists=WORKLISTS)
        if problems:
            raise Refused("the staff release's gates:\n  - " + "\n  - ".join(problems))
        release = release_record(approval, pcs.read_holds()[0])
        hook, api_url = os.environ.get("RENDER_DEPLOY_HOOK_URL"), os.environ.get("SDFOOD_API_URL")
        if not (args.no_push or args.no_deploy or hook or dry):
            raise Refused("set RENDER_DEPLOY_HOOK_URL (the service's Settings, Deploy Hook), or pass --no-deploy")
        build = build_tag(meta)
        ref = f"{image}:{build}"
        print(f"export {meta['run']}: {meta['places']} places, inspections through "
              f"{meta['inspections_through']}, expires {meta['expires']}")
        if not (args.no_push or dry):
            ensure_private(image, pushed=False, confirmed_private=args.registry_is_private)
        write_release(SITE, release, dry)
        try:
            sh(["docker", "build", "--platform", "linux/amd64", "--provenance=false", "--build-arg", f"SDFOOD_BUILD={build}",
                "-f", "api/Dockerfile", "-t", ref, "."], dry)
        finally:
            clear_release(SITE, dry)
        smoke_test(ref, meta, build, dry, release)
        if args.no_push:
            print(f"built and checked {ref}; not pushed")
            return 0
        sh(["docker", "push", ref], dry)
        if not dry:
            ensure_private(image, pushed=True, confirmed_private=args.registry_is_private)
        sh(["docker", "tag", ref, f"{image}:{SERVICE_TAG}"], dry)
        sh(["docker", "push", f"{image}:{SERVICE_TAG}"], dry)
        if dry:
            if not args.no_deploy:
                deploy(hook, f"{image}@sha256:<digest>", dry)
            return 0
        image_ref = pushed_digest(image, ref)
        if args.no_deploy:
            print(f"pushed {image_ref} as {image}:{SERVICE_TAG}. Render picks it up on its next deploy "
                  "(Manual Deploy, Deploy latest reference) or restart")
            return 0
        deploy(hook, image_ref, dry)
        if api_url:
            wait_live(api_url, build)
        return 0
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as e:
        print(f"failed ({e.returncode}): {' '.join(map(str, e.cmd))}\n{(e.stderr or '').strip()}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"failed: {e.filename} is not installed or not on PATH", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
