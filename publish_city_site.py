"""Publish the City staff site: food-dashboard with the real export, to a PRIVATE GitHub repository
that Render builds and serves behind a sign-in (city_site/server.mjs). The real export never enters
this public repository. The staff site is a release of named results like any other, so it has its
own gates (docs/STAFF_SITE.md, docs/PUBLISHING.md "Release path 4").

    python export_site.py && python publish_city_site.py                  # after each refresh
    python publish_city_site.py --wait https://sdfood-city.onrender.com   # and wait until Render serves it
    python publish_city_site.py --holds-only                              # apply docs/holds.json to what is live now

    --repo OWNER/NAME   the private deploy repository (default ChenhaoZhang01/sdfood-city; created,
                        private, on the first run)
    --dir PATH          its local checkout (default ../sdfood-city, next to this repository)
    --force             ship a list with fewer places than the live one (after a real change, say why)
    --holds-only        apply docs/holds.json to the list that is live, and nothing else: a hold only
                        removes points and bands, so it goes out even when the export could not (never
                        roll back on Render instead: a rollback serves an unchecked build and undoes holds)

Refuses to push unless:
  * docs/STAFF_APPROVAL.json (gitignored; docs/STAFF_APPROVAL.example.json) names a responsible adult
    and a corrections contact, and a sunset date that has not passed and is at most a year away;
  * the export is real, built from a complete pull, at least 2 days from expiry, not older than the
    live one, and not quietly smaller than it (--force);
  * the code that built it was committed (its provenance is not "-dirty"), and the rule it applies
    is the committed docs/rule.json (frozen_problems), so the list can be rebuilt;
  * the push goes to a private repository and nowhere else (check_target).
It also ships, in the staff copy of meta.json: who is responsible and whom to write to, the sunset
date, whether the City has recorded a request for access (access_approved), and every check this
list has not passed (review_status): the public-release gates, and in plain words what has not been
done (no lawyer, no County comment, no owner told, no City request or TRUST determination), which
the site shows on every page. Holds in docs/holds.json take effect here, without a rebuild: a held
place keeps its County record and loses its points and band. Each publish also writes ops/ into the
private repository (not served): the source that built the list, the frozen rule, the pull's meta,
the approval and the holds, so whoever takes the site over can rebuild it without this laptop.

On Render (once, see docs/HOSTING.md "The City staff site"): a Node web service from that repository,
build `npm ci && npx vite build`, start `node server.mjs`, health check /healthz, env SITE_USERS or
SITE_PASSWORD, SITE_CONTACT, NODE_VERSION=24, VITE_GOOGLE_MAPS_*. Each push redeploys it."""
import argparse, getpass, json, os, re, shutil, subprocess, sys, time, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "data" / "site"
APPROVAL = ROOT / "docs" / "STAFF_APPROVAL.json"
HOLDS = ROOT / "docs" / "holds.json"
FROZEN = ROOT / "docs" / "rule.json"
PULL_META = ROOT / "data" / "pull_meta.json"
MAX_SUNSET_DAYS = 366                                 # a staff release is renewed at least yearly
DEPLOY_LOG = ROOT / "data" / "staff_deploys.jsonl"
STAFF_MARKER = "STAFF-SITE-PRIVATE-DO-NOT-PUBLISH"   # = food-dashboard/scripts/exportGate.mjs STAFF_MARKER
MIN_DAYS_LEFT = 2
SHRINK = 0.9                                          # a list under 90% of the live one's places needs --force
KEEP = (".git", ".github", "DEPLOYS.jsonl")           # kept across publishes in the private checkout
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
        sunset = date.fromisoformat(a.get("sunset") or "")
        if sunset < today:
            p.append(f"the sunset date {a['sunset']} has passed: take the site down, or record a City owner and a new date")
        elif sunset > today + timedelta(days=MAX_SUNSET_DAYS):
            p.append(f"the sunset date {a['sunset']} is more than a year away: a staff release is renewed at least yearly")
    except ValueError:
        p.append("sunset needs a date (YYYY-MM-DD): when the site comes down unless a City owner takes it over")
    return p


# What has not been done, in plain words, from docs/STAFF_APPROVAL.json. Shown to staff on every page
# (StaffBanner): a list of open checks is not a substitute for doing them, but staff must know.
OPEN_ITEMS = (
    ("legal_review", "date", "no lawyer has reviewed naming these businesses (legal_review)"),
    ("county_informed", "date", "the County has not commented on this list (county_informed)"),
    ("owner_notice", "date", "no business on the list has been told it is on it (owner_notice)"),
)


def open_items(a):
    a = a or {}
    out = []
    if not _requested(a):
        out.append("no City request for access is on record (city_requestor)")
    if _trust(a) is None:
        out.append("no TRUST Ordinance determination is on record (trust_determination)")
    elif _trust(a) == "applies" and not _council_approved(a):
        out.append("the TRUST Ordinance applies and the Council has not approved this use (council_approval)")
    return out + [text for key, field, text in OPEN_ITEMS if not ((a.get(key) or {}).get(field) or "").strip()]


def access_approved(a):
    """Someone at the City asked for access in writing (name and date), and the City has answered
    whether its TRUST Ordinance applies: "does not apply", or "applies" with the Council's approval
    on record. One predicate for the banner, the open items and the server (which, until then, shows
    the named list only to the site's operators)."""
    return _requested(a) and (_trust(a) == "does not apply" or (_trust(a) == "applies" and _council_approved(a)))


def drift_items(meta):
    d = meta.get("drift") or {}
    return ([f"the County's record has moved since the rule was frozen: {'; '.join(d.get('reasons') or [])}; "
             "refit with export_site.py --refit"] if d.get("refit_needed") else [])


def frozen_problems(meta, show=None):
    """A bands list applies the committed frozen rule (docs/rule.json), so it can be rebuilt and its
    rule has a public date. `show(path)` returns the committed file's text, or None."""
    if meta.get("mode") != "bands":
        return []
    fr = meta.get("frozen") or {}
    if not fr.get("version"):
        return ["the export applies no frozen rule: run export_site.py (it writes docs/rule.json), review and commit "
                "docs/rule.json, then export again"]
    if show is None:
        def show(path):
            r = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            return r.stdout if r.returncode == 0 else None
    text = show("docs/rule.json")
    if text is None:
        return ["docs/rule.json is not committed: commit the frozen rule this list applies, then export again"]
    try:
        committed = json.loads(text).get("version")
    except ValueError:
        committed = None
    if committed != fr["version"]:
        return [f"the export applies rule version {fr['version']}, but the committed docs/rule.json is {committed}: "
                "commit the rule the list applies (or export again with the committed one)"]
    return []


def unpushed_warning():
    """This repository's HEAD is not on its origin: the list can still be rebuilt from ops/source.tar.gz
    in the private repository, but CI has not run on the code that built it."""
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    on = subprocess.run(["git", "branch", "-r", "--contains", head], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return None if on else (f"sdfood@{head[:7]} is not on any remote branch: push it so CI runs on the code that built "
                            "this list (its source is in the private repository's ops/ either way)")


TRUST_RESULTS = ("does not apply", "applies")


def _requested(a):
    r = (a or {}).get("city_requestor") or {}
    return bool((r.get("name") or "").strip() and (r.get("date") or "").strip())


def _trust(a):
    """The City's TRUST Ordinance answer: "does not apply", "applies", or None when none is recorded."""
    res = (((a or {}).get("trust_determination") or {}).get("result") or "").strip().lower()
    return res if res in TRUST_RESULTS else None


def _council_approved(a):
    return bool((((a or {}).get("council_approval") or {}).get("date") or "").strip())


def approval_warnings(a):
    w = []
    if not _requested(a):
        w.append("no city_requestor yet (name and date): record who at the City asked for access, and when, before issuing sign-ins")
    if _trust(a) is None:
        w.append(f"no trust_determination yet (result: one of {', '.join(TRUST_RESULTS)}): ask the City whether its TRUST "
                 "Ordinance (SDMC 210.0101-210.0112) applies")
    elif _trust(a) == "applies" and not _council_approved(a):
        w.append("the TRUST Ordinance applies and no council_approval is on record: Privacy Advisory Board review and a Council "
                 "vote come before any staff use")
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
    """A held place keeps its County record and loses its points and band, at once, and moves to the
    end of the list file, so its position does not give its points away."""
    # Held places last, in facility-id order: keeping their order by points would give the points away.
    fc["features"].sort(key=lambda f: (f["properties"]["facility_id"] in held or bool(f["properties"].get("on_hold")),
                                       f["properties"]["facility_id"] if (f["properties"]["facility_id"] in held
                                                                           or f["properties"].get("on_hold")) else ""))
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


def independence_problems(a):
    """Shown to staff, not a refusal: the operator named is one of the students who built the list."""
    adult = (a or {}).get("responsible_adult") or {}
    rel = (adult.get("relationship") or "").strip().lower()
    authors = {"chenhao zhang", "ayan pendharkar"}
    if rel in ("author", "student", "self") or (adult.get("name") or "").strip().lower() in authors:
        return ["no independent responsible adult: the operator named is a student author of the list"]
    return []


def staff_meta(meta, approval, status, published_by):
    a = approval or {}
    adult, corr = a.get("responsible_adult") or {}, a.get("corrections_contact") or {}
    return {**meta, "audience": "staff", "sunset": a.get("sunset"), "access_approved": access_approved(a),
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


OPS_README = """# ops/: what it takes to rebuild and run this site

Written by publish_city_site.py on every publish. Not served: the web server only serves dist/, which
the build makes from public/. Private, like the rest of this repository: it names the people
responsible (STAFF_APPROVAL.json) and the places on hold (holds.json).

- source.tar.gz: the sdfood code that built this list (`git archive` of the commit in DEPLOYS.jsonl).
- rule.json: the frozen rule the list applies (docs/rule.json).
- pull_meta.json: the County pull the list was built from (date, count, sha256).
- STAFF_APPROVAL.json, holds.json: the release's approval and the places on hold.

To rebuild: unpack source.tar.gz, `pip install -r requirements.txt`, put rule.json, STAFF_APPROVAL.json
and holds.json in docs/, then `python refresh_city_site.py` (it pulls, exports with the frozen rule,
writes worklists and publishes here). docs/RUNBOOK.md in the source says the rest, including how to
hand the site over and how to take it down.
"""


def write_ops(out):
    """ops/ in the private checkout: the source, frozen rule, pull meta, approval and holds."""
    ops = out / "ops"
    ops.mkdir(exist_ok=True)
    for old in ops.iterdir():
        if old.is_file():
            old.unlink()
    subprocess.run(["git", "archive", "--format=tar.gz", "-o", str(ops / "source.tar.gz"), "HEAD"], cwd=ROOT, check=True)
    for src in (FROZEN, PULL_META, APPROVAL, HOLDS):
        if src.exists():
            shutil.copy2(src, ops / src.name)
    (ops / "README.md").write_text(OPS_README, encoding="utf-8")


def ensure_checkout(out, repo):
    """The private repository's local checkout: cloned when it is missing and the repository exists
    (a fresh machine keeps the deploy history), created private on the very first run."""
    out.mkdir(parents=True, exist_ok=True)
    if (out / ".git").exists():
        return
    exists = subprocess.run(["gh", "repo", "view", repo], capture_output=True).returncode == 0
    if exists and not any(out.iterdir()):
        run(["git", "clone", "-q", f"https://github.com/{repo}.git", str(out)], out.parent)
        return
    if exists:
        sys.exit(f"{out} is not empty and is not a checkout of {repo}: move it aside, and the next run clones it")
    run(["git", "init", "-b", "main"], out)


def commit_and_push(out, message):
    run(["git", "add", "-A"], out)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=out).returncode == 0:
        return None
    run(["git", "commit", "-q", "-m", message], out)
    run(["git", "push", "-q", "-u", "origin", "main"], out)
    return run(["git", "rev-parse", "HEAD"], out).strip()


def holds_only(out, approval, today, repo):
    """Apply docs/holds.json to the list that is live, and nothing else."""
    problems = approval_problems(approval, today)
    if problems:
        sys.exit("NOT PUBLISHED to the staff site:\n  - " + "\n  - ".join(problems))
    data = out / "public" / "data"
    if not (data / "facilities.geojson").exists():
        sys.exit(f"{data} holds no live list: publish a full release first")
    check_target(push_urls(out), repo,
                 lambda r: run(["gh", "repo", "view", r, "--json", "visibility", "--jq", ".visibility"], out).strip())
    fc = json.loads((data / "facilities.geojson").read_text(encoding="utf-8"))
    held = set(_json(HOLDS, {}).get("facility_ids", []))
    details = {fid: _json(data / "place" / f"{fid}.json", None) for fid in held}
    changed = apply_holds(fc, details, held)
    for fid, d in changed.items():
        (data / "place" / f"{fid}.json").write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    (data / "facilities.geojson").write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
    meta = _json(data / "meta.json", {})
    at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    history = out / "DEPLOYS.jsonl"
    prior = history.read_text(encoding="utf-8") if history.exists() else ""
    history.write_text(prior + json.dumps({"at": at, "run": meta.get("run"), "holds_only": True, "by": getpass.getuser(),
                                           "held": sorted(held)}) + "\n", encoding="utf-8")
    if HOLDS.exists():
        (out / "ops").mkdir(exist_ok=True)
        shutil.copy2(HOLDS, out / "ops" / HOLDS.name)
    return commit_and_push(out, f"City site: holds only ({len(held)} held), {meta.get('run')}"), meta, held


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default="ChenhaoZhang01/sdfood-city")
    ap.add_argument("--dir", default=str(ROOT.parent / "sdfood-city"))
    ap.add_argument("--force", action="store_true", help="ship a list with fewer places than the live one")
    ap.add_argument("--wait", metavar="URL", help="wait until the service at URL serves this commit")
    ap.add_argument("--holds-only", action="store_true", help="apply docs/holds.json to the live list, and nothing else")
    args = ap.parse_args(argv)
    today = date.today()
    out = Path(args.dir)
    approval = _json(APPROVAL, None)
    if args.holds_only:
        ensure_checkout(out, args.repo)
        commit, meta, held = holds_only(out, approval, today, args.repo)
        print(f"holds applied ({len(held)} held)" + (f"; pushed {commit[:7]}" if commit else "; nothing changed"))
        if commit and args.wait:
            h = wait_live(args.wait, commit)
            if not h:
                sys.exit(f"{args.wait} did not serve {commit[:7]} within 15 minutes: check the deploy on Render")
            print(f"live: {args.wait} serves {h.get('run')} with the holds")
        return 0
    meta = json.loads((SITE / "meta.json").read_text(encoding="utf-8"))
    live = _json(out / "public" / "data" / "meta.json", None)
    problems = (approval_problems(approval, today) + export_problems(meta, live, today, force=args.force)
                + frozen_problems(meta))
    if problems:
        sys.exit("NOT PUBLISHED to the staff site:\n  - " + "\n  - ".join(problems))
    for w in approval_warnings(approval) + [w for w in [unpushed_warning()] if w]:
        print(f"warning: {w}")
    if "onedrive" in str(ROOT).lower():
        print("warning: this checkout, and the real export in it, sit in a OneDrive-synced folder (see docs/STAFF_SITE.md)")

    ensure_checkout(out, args.repo)
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

    for p in out.iterdir():                                   # a clean copy each time, keeping .git, .github, the history
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
    status = open_items(approval) + independence_problems(approval) + drift_items(meta) + review_status(meta, today)
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
    write_ops(out)
    (out / "README.md").write_text(
        "# San Diego Food Inspection Record: City staff site\n\nPRIVATE. Generated by publish_city_site.py in "
        "the sdfood repository; do not edit here. Holds the real export: never make this repository public, "
        "fork it, or connect it to a public repository.\n", encoding="utf-8")

    # The deploy history travels with the site, so whoever owns it at the City can see every release.
    history = out / "DEPLOYS.jsonl"
    prior = history.read_text(encoding="utf-8") if history.exists() else ""
    history.write_text(prior + json.dumps({"at": shipped["staff_release"]["at"], "run": meta["run"],
                                           "places": meta.get("places"), "by": shipped["staff_release"]["by"],
                                           "review_status": status, "held": sorted(held)}) + "\n", encoding="utf-8")
    source = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    commit = commit_and_push(out, f"City site: {meta['run']}, inspections through {meta['inspections_through']}, "
                                  f"from sdfood@{source}")
    if commit is None:
        print("nothing changed")
        return 0
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
