"""Publish the City staff site: food-dashboard with the real export, to a PRIVATE GitHub repository
that Render builds and serves behind a sign-in (city_site/server.mjs). The real export never enters
this public repository. The staff site is a release of named results like any other, so it has its
own gates (docs/STAFF_SITE.md, docs/PUBLISHING.md "Release path 4").

    python export_site.py && python publish_city_site.py                  # after each refresh
    python publish_city_site.py --wait https://sdfood-city.onrender.com   # and wait until Render serves it

    --repo OWNER/NAME   the private deploy repository (default ChenhaoZhang01/sdfood-city; created,
                        private, on the first run)
    --dir PATH          its local checkout (default ../sdfood-city, next to this repository)
    --force             ship a list with fewer places than the live one (after a real change, say why)

Refuses to push unless:
  * docs/STAFF_APPROVAL.json (gitignored; docs/STAFF_APPROVAL.example.json) names a responsible adult
    and a corrections contact, and a sunset date that has not passed;
  * the export is real, built from a complete pull, at least 2 days from expiry, not older than the
    live one, and not quietly smaller than it (--force);
  * the code that built it was committed (its provenance is not "-dirty"), so the list can be rebuilt;
  * the push goes to a private repository and nowhere else (check_target).
It also ships, in the staff copy of meta.json: who is responsible and whom to write to, the sunset
date, and every public-release gate this list does not pass (review_status), which the site shows.
Holds in docs/holds.json take effect here, without a rebuild: a held place keeps its County record
and loses its points and band.

On Render (once, see docs/HOSTING.md "The City staff site"): a Node web service from that repository,
build `npm ci && npx vite build`, start `node server.mjs`, health check /healthz, env SITE_USERS or
SITE_PASSWORD, SITE_CONTACT, NODE_VERSION=24, VITE_GOOGLE_MAPS_*. Each push redeploys it."""
import argparse, getpass, json, os, re, shutil, subprocess, sys, time, urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "data" / "site"
APPROVAL = ROOT / "docs" / "STAFF_APPROVAL.json"
HOLDS = ROOT / "docs" / "holds.json"
DEPLOY_LOG = ROOT / "data" / "staff_deploys.jsonl"
STAFF_MARKER = "STAFF-SITE-PRIVATE-DO-NOT-PUBLISH"   # = food-dashboard/scripts/exportGate.mjs STAFF_MARKER
MIN_DAYS_LEFT = 2
SHRINK = 0.9                                          # a list under 90% of the live one's places needs --force
KEEP = (".git", ".github")                            # kept across publishes in the private checkout
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
BAND_FIELDS = ("band", "points", "score_card", "scores_used", "estimate", "band_stability")


def run(cmd, cwd):
    print("$ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True).stdout


def github_repo(url):
    """OWNER/NAME (lowercase) for a github.com remote URL in https, ssh or scp form; None otherwise."""
    m = re.fullmatch(r"(?:https://(?:[^@/]+@)?github\.com/|ssh://git@github\.com/|git@github\.com:)"
                     r"([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?", (url or "").strip())
    return f"{m.group(1)}/{m.group(2)}".lower() if m else None


def push_urls(checkout):
    """Every URL `git push origin` would send to: the push URLs (pushurl, or url when there is none),
    with insteadOf / pushInsteadOf already applied by git."""
    out = subprocess.run(["git", "remote", "get-url", "--push", "--all", "origin"], cwd=checkout,
                         capture_output=True, text=True).stdout
    return [u.strip() for u in out.splitlines() if u.strip()]


def check_target(remote_urls, repo, visibility):
    """Refuse unless every URL origin pushes to IS --repo and that repository is private. (Checking
    --repo while pushing to whatever origin says would send the real export somewhere unchecked.)"""
    urls = [remote_urls] if isinstance(remote_urls, str) else list(remote_urls)
    if not urls:
        sys.exit("origin has no push URL: refusing to push the real export")
    targets = {github_repo(u) for u in urls}
    if None in targets:
        bad = [u for u in urls if github_repo(u) is None]
        sys.exit(f"origin pushes to {bad!r}, not a github.com repository: refusing to push the real export there")
    if targets != {repo.lower()}:
        sys.exit(f"origin pushes to {sorted(targets)}, but --repo is {repo}: refusing to push the real export to a "
                 "repository other than the one whose privacy was checked")
    target = targets.pop()
    vis = visibility(target)
    if vis != "PRIVATE":
        sys.exit(f"{target} is {vis}: the real export only goes to a private repository")
    return target


# ── the staff release's gates ───────────────────────────────────────────────────────────────

def approval_problems(a, today):
    """What docs/STAFF_APPROVAL.json lacks. Minors can disaffirm what they agree to, so the City
    needs an adult it can hold to the site's terms, and owners need someone to write to."""
    if not a:
        return [f"no {APPROVAL.relative_to(ROOT)}: copy docs/STAFF_APPROVAL.example.json and fill it in "
                "(a responsible adult, a corrections contact, a sunset date)"]
    p = []
    adult = a.get("responsible_adult") or {}
    if not (adult.get("name") or "").strip() or not EMAIL.fullmatch((adult.get("email") or "").strip()):
        p.append("responsible_adult needs a name and an email: an adult the City can hold to the site's terms")
    if not EMAIL.fullmatch(((a.get("corrections_contact") or {}).get("email") or "").strip()):
        p.append("corrections_contact needs an email: where an owner or staff member reports an error")
    try:
        if date.fromisoformat(a.get("sunset") or "") < today:
            p.append(f"the sunset date {a['sunset']} has passed: take the site down, or record a City owner and a new date")
    except ValueError:
        p.append("sunset needs a date (YYYY-MM-DD): when the site comes down unless a City owner takes it over")
    return p


def approval_warnings(a):
    w = []
    if not ((a or {}).get("city_requestor") or {}).get("name"):
        w.append("no city_requestor yet: record who at the City asked for access, and when, before issuing sign-ins")
    if not ((a or {}).get("trust_determination") or {}).get("date"):
        w.append("no trust_determination yet: ask the City whether its TRUST Ordinance (SDMC ch. 2, art. 10, div. 1) applies")
    return w


def export_problems(meta, live, today, force=False):
    """Why this export may not replace what staff see now."""
    p = []
    if meta.get("sample"):
        p.append("data/site holds the invented sample; run export_site.py first")
        return p
    if "PARTIAL PULL" in ((meta.get("source") or {}).get("name") or ""):
        p.append("the export was built from a partial pull: finish fetch_sdfood.py --resume, then export again")
    exp = meta.get("expires")
    if not exp or (date.fromisoformat(exp) - today).days < MIN_DAYS_LEFT:
        p.append(f"the export expires {exp}: fetch and export again first (it needs {MIN_DAYS_LEFT}+ days left)")
    code = ((meta.get("provenance") or {}).get("code_sha") or "")
    if not code or code.endswith("-dirty") or code == "unknown":
        p.append(f"the export was built from uncommitted code ({code or 'no code sha'}): commit, then export again, "
                 "so the list can be rebuilt from a commit")
    if live:
        if (meta.get("inspections_through") or "") < (live.get("inspections_through") or ""):
            p.append(f"the export's record ends {meta.get('inspections_through')}, before the live one's "
                     f"({live.get('inspections_through')})")
        if live.get("places") and meta.get("places", 0) < SHRINK * live["places"] and not force:
            p.append(f"{meta.get('places')} places against {live['places']} live: pass --force if that is a real change")
    return p


def review_status(meta, today):
    """The public-release gates this list does not pass. The staff site shows them: staff should
    know what the list has and has not been shown to do."""
    import export_site as es
    pull = {"complete": "PARTIAL PULL" not in ((meta.get("source") or {}).get("name") or "")}
    try:
        problems = es.gates(meta, SITE, pull, today, None, None, [])
    except Exception as e:                            # never block a staff release on the review itself
        problems = [f"the public-release gates could not be evaluated ({type(e).__name__})"]
    return [q for q in problems if "approval" not in q and "PUBLISH_APPROVAL" not in q]


def apply_holds(fc, details, held):
    """A held place keeps its County record and loses its points and band, at once."""
    for f in fc["features"]:
        p = f["properties"]
        if p["facility_id"] in held and any(k in p for k in BAND_FIELDS):
            for k in BAND_FIELDS:
                p.pop(k, None)
            p["on_hold"] = True
    changed = {}
    for fid in held:
        d = details.get(fid)
        if d is not None:
            d = {k: v for k, v in d.items() if k not in BAND_FIELDS}
            d["on_hold"] = True
            changed[fid] = d
    return changed


def staff_meta(meta, approval, status, published_by):
    a = approval or {}
    adult, corr = a.get("responsible_adult") or {}, a.get("corrections_contact") or {}
    return {**meta, "audience": "staff", "sunset": a.get("sunset"),
            "operator": {"name": adult.get("name"), "role": adult.get("relationship") or "responsible adult",
                         "email": adult.get("email")},
            "contact": {"name": corr.get("name"), "email": corr.get("email")},
            "review_status": status,
            "staff_release": {"at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "by": published_by}}


def wait_live(url, commit, timeout=900, every=20):
    """Until the service's /healthz reports the commit just pushed (a free instance wakes on the first call)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(f"{url.rstrip('/')}/healthz", timeout=90) as r:
                h = json.loads(r.read())
            if h.get("source") == commit:
                return h
        except Exception:
            pass
        time.sleep(every)
    return None


def _json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default="ChenhaoZhang01/sdfood-city")
    ap.add_argument("--dir", default=str(ROOT.parent / "sdfood-city"))
    ap.add_argument("--force", action="store_true", help="ship a list with fewer places than the live one")
    ap.add_argument("--wait", metavar="URL", help="wait until the service at URL serves this commit")
    args = ap.parse_args(argv)
    today = date.today()
    meta = json.loads((SITE / "meta.json").read_text(encoding="utf-8"))
    out = Path(args.dir)
    live = _json(out / "public" / "data" / "meta.json", None)
    approval = _json(APPROVAL, None)
    problems = approval_problems(approval, today) + export_problems(meta, live, today, force=args.force)
    if problems:
        sys.exit("NOT PUBLISHED to the staff site:\n  - " + "\n  - ".join(problems))
    for w in approval_warnings(approval):
        print(f"warning: {w}")
    if "onedrive" in str(ROOT).lower():
        print("warning: this checkout, and the real export in it, sit in a OneDrive-synced folder (see docs/STAFF_SITE.md)")

    out.mkdir(parents=True, exist_ok=True)
    if not (out / ".git").exists():
        run(["git", "init", "-b", "main"], out)
    # Refuse to push the real export anywhere public.
    remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=out, capture_output=True, text=True).stdout.strip()
    if not remote:
        exists = subprocess.run(["gh", "repo", "view", args.repo], capture_output=True).returncode == 0
        if not exists:
            run(["gh", "repo", "create", args.repo, "--private"], out)
        run(["git", "remote", "add", "origin", f"https://github.com/{args.repo}.git"], out)
        remote = f"https://github.com/{args.repo}.git"
    check_target(push_urls(out) or [remote], args.repo,
                 lambda r: run(["gh", "repo", "view", r, "--json", "visibility", "--jq", ".visibility"], out).strip())

    for p in out.iterdir():                                   # a clean copy each time, keeping .git and .github
        if p.name in KEEP:
            continue
        if p.is_dir():                                        # OneDrive may hold an emptied folder: leave it
            shutil.rmtree(p, onexc=lambda fn, path, exc: None if fn is os.rmdir else (_ for _ in ()).throw(exc))
        else:
            p.unlink()
    # Tracked files only: an untracked local file (a review export, a scratch config) is never shipped.
    for rel in run(["git", "ls-files", "--cached", "food-dashboard"], ROOT).splitlines():
        rel = Path(rel).relative_to("food-dashboard")
        if rel.parts[:2] == ("public", "data"):
            continue
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "food-dashboard" / rel, out / rel)
    data = out / "public" / "data"
    data.mkdir(parents=True, exist_ok=True)
    fc = json.loads((SITE / "facilities.geojson").read_text(encoding="utf-8"))
    shutil.copytree(SITE / "place", data / "place", dirs_exist_ok=True)
    held = set(_json(HOLDS, {}).get("facility_ids", []))
    details = {fid: _json(SITE / "place" / f"{fid}.json", None) for fid in held}
    for fid, d in apply_holds(fc, details, held).items():
        (data / "place" / f"{fid}.json").write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    (data / "facilities.geojson").write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
    status = review_status(meta, today)
    shipped = staff_meta(meta, approval, status, getpass.getuser())
    (data / "meta.json").write_text(json.dumps(shipped, indent=2), encoding="utf-8")
    shutil.copy2(ROOT / "city_site" / "server.mjs", out / "server.mjs")
    shutil.copy2(ROOT / "city_site" / "render.yaml", out / "render.yaml")
    (out / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "city_site" / "watch.yml", out / ".github" / "workflows" / "watch.yml")
    # Only here, in the private repository: tells the site's build (scripts/exportGate.mjs, vite.config.js)
    # that this is the signed-in staff site, whose unpublished export is checked in review mode.
    (out / STAFF_MARKER).write_text("The City staff site. Private: never publish this repository or its build.\n",
                                    encoding="utf-8")
    (out / "README.md").write_text(
        "# San Diego Food Inspection Record: City staff site\n\nPRIVATE. Generated by publish_city_site.py in "
        "the sdfood repository; do not edit here. Holds the real export: never make this repository public, "
        "fork it, or connect it to a public repository.\n", encoding="utf-8")

    run(["git", "add", "-A"], out)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=out).returncode == 0:
        print("nothing changed")
        return 0
    source = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    run(["git", "commit", "-q", "-m", f"City site: {meta['run']}, inspections through {meta['inspections_through']}, "
                                      f"from sdfood@{source}"], out)
    run(["git", "push", "-q", "-u", "origin", "main"], out)
    commit = run(["git", "rev-parse", "HEAD"], out).strip()
    DEPLOY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DEPLOY_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": shipped["staff_release"]["at"], "run": meta["run"], "places": meta.get("places"),
                             "commit": commit, "source": source, "by": shipped["staff_release"]["by"],
                             "review_status": status, "held": sorted(held)}) + "\n")
    print(f"pushed {meta['run']} ({meta['places']} places) to {args.repo} as {commit[:7]}"
          + (f"; {len(status)} public-release gates not passed, shown to staff" if status else ""))
    if args.wait:
        h = wait_live(args.wait, commit)
        if not h:
            sys.exit(f"{args.wait} did not serve {commit[:7]} within 15 minutes: check the deploy on Render")
        print(f"live: {args.wait} serves {h.get('run')} (expires {h.get('expires')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
