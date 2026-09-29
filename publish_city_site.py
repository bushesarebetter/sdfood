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
  * this working tree has no uncommitted change to a tracked file: the site (food-dashboard, city_site/)
    is copied from HEAD with git archive, never from disk, and DEPLOYS.jsonl records both commits (the
    one that built the list and the one that built the site);
  * docs/holds.json is readable and in its format ({"facility_ids": [...]}), names no id that differs
    from a listed one only in case, and every held place on the list loses its points and band;
  * every run registered for the prospective test (docs/prospective/REGISTERED.json) has its archive,
    with its registered hash, here or in the private repository's ops/archive/;
  * the push goes to a private repository and nowhere else (check_target).
--holds-only also refuses a newly held id that is not on the live list (ids are case-sensitive), before
it changes anything.
It also ships, in the staff copy of meta.json: who is responsible and whom to write to, the sunset
date, whether the City has recorded a request for access (access_approved: dated, attributed entries
on or before the day of publishing), the monitor's summary (monitor), and every check this list has
not passed (review_status): the public-release gates, and in plain words what has not been done (no
lawyer, no County comment, no owner told, no City request or TRUST determination), which the site
shows on every page. Holds in docs/holds.json take effect here, without a rebuild: a held place keeps
its County record and loses its points and band. Each publish also writes ops/ into the private
repository (not served): the source that built the site and the list, the frozen rule, the pull's
meta, the approval, the holds, the monitor's output and every archived list, so whoever takes the
site over can rebuild it, and score the prospective test, without this laptop.

Exit codes: 0 published (or nothing changed); 1 refused, nothing pushed; 5 pushed, but the service
did not serve the new commit within 15 minutes (--wait): it may still deploy, so check Render's Events
and /healthz before doing anything else.

On Render (once, see docs/HOSTING.md "The City staff site"): a Node web service from that repository,
build `npm ci && npx vite build`, start `node server.mjs`, health check /healthz, NODE_VERSION=24,
VITE_GOOGLE_MAPS_*, and the sign-ins (city_site/render.yaml lists them): SITE_USERS, one id and token
per person; SITE_OPERATORS, the ids that see the named list before access_approved; SITE_PASSWORD and
SITE_USER, the operator's own older sign-in, never given to anyone (by default an operator only while
it is the only sign-in); SITE_CONTACT, whom to ask for access. Each push redeploys it."""
import argparse, getpass, hashlib, io, json, os, re, shutil, subprocess, sys, tarfile, time, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "data" / "site"
APPROVAL = ROOT / "docs" / "STAFF_APPROVAL.json"
HOLDS = ROOT / "docs" / "holds.json"
FROZEN = ROOT / "docs" / "rule.json"
PULL_META = ROOT / "data" / "pull_meta.json"
REGISTERED = ROOT / "docs" / "prospective" / "REGISTERED.json"
MAX_SUNSET_DAYS = 366                                 # a staff release is renewed at least yearly
DEPLOY_LOG = ROOT / "data" / "staff_deploys.jsonl"
STAFF_MARKER = "STAFF-SITE-PRIVATE-DO-NOT-PUBLISH"   # = food-dashboard/scripts/exportGate.mjs STAFF_MARKER
MIN_DAYS_LEFT = 2
SHRINK = 0.9                                          # a list under 90% of the live one's places needs --force
# Kept across publishes in the private checkout. ops/ keeps its archive/ (write-once lists); write_ops
# replaces the files at its top.
KEEP = (".git", ".github", "DEPLOYS.jsonl", "ops")
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
BAND_FIELDS = ("band", "points", "score_card", "scores_used", "estimate", "band_stability")
EXIT_NOT_SERVED = 5                                   # pushed, but not served within the wait: never "unchanged"
MONITOR_FILES = ("monitor.json", "monitor.md", "monitor_summary.json")
MONITOR_STATUSES = ("too early", "interim", "complete", "failed")
HOLDS_FORMAT = '{"facility_ids": ["DEH2022-FFPP-000001", ...]} (ids exactly as the list shows them)'


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


def open_items(a, today):
    """What has not been done, for staff. An entry filled in but not counted (a date still to come, a
    placeholder, no attribution) is not done: approval_warnings tells the operator what is wrong with it."""
    a = a or {}
    out = []
    if not _requested(a, today):
        out.append("no City request for access is on record (city_requestor)")
    if _trust(a, today) is None:
        out.append("no TRUST Ordinance determination is on record (trust_determination)")
    elif _trust(a, today) == "applies" and not _council_approved(a, today):
        out.append("the TRUST Ordinance applies and the Council has not approved this use (council_approval)")
    return out + [text for key, field, text in OPEN_ITEMS if not _text(_section(a, key), field)]


def access_approved(a, today):
    """Someone at the City asked for access in writing (a name, and a date on or before `today`), and
    the City has answered whether its TRUST Ordinance applies, by whom and when: "does not apply", or
    "applies" with the Council's approval (a resolution, and its date) on record. Every date is
    YYYY-MM-DD on or before `today`: a scheduled vote or a placeholder ("soon", "tbd") is not an event
    on record. One predicate for the banner, the open items and the server (which, until then, shows
    the named list only to the site's operators, and opens it only for the value true)."""
    t = _trust(a, today)
    return bool(_requested(a, today) and (t == "does not apply" or (t == "applies" and _council_approved(a, today))))


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


def _section(a, key):
    s = (a or {}).get(key)
    return s if isinstance(s, dict) else {}


def _text(section, field):
    v = section.get(field)
    return v.strip() if isinstance(v, str) else ""


def _filled(section):
    """Any field but a _note is filled in."""
    return any(_text(section, k) for k in section if not k.startswith("_"))


def _past_date(v, today):
    """The date, when `v` is YYYY-MM-DD on or before `today`; otherwise None."""
    if not isinstance(v, str) or not ISO_DATE.fullmatch(v.strip()):
        return None
    try:
        d = date.fromisoformat(v.strip())
    except ValueError:
        return None
    return d if d <= today else None


def _date_problem(key, section, today):
    """Why `key`.date does not count, or None."""
    raw = _text(section, "date")
    if not raw:
        return f"{key}.date is empty"
    try:
        d = date.fromisoformat(raw) if ISO_DATE.fullmatch(raw) else None
    except ValueError:
        d = None
    if d is None:
        return f"{key}.date {raw!r} is not a date (YYYY-MM-DD)"
    if d > today:
        return f"{key}.date {raw} is after today ({today.isoformat()}): an event still to come is not on record"
    return None


def _requested(a, today):
    r = _section(a, "city_requestor")
    return bool(_text(r, "name")) and _past_date(r.get("date"), today) is not None


def _trust(a, today):
    """The City's TRUST Ordinance answer: "does not apply" or "applies", with who gave it and when; None
    when no such answer is recorded."""
    t = _section(a, "trust_determination")
    res = _text(t, "result").lower()
    if res in TRUST_RESULTS and _text(t, "by") and _past_date(t.get("date"), today) is not None:
        return res
    return None


def _council_approved(a, today):
    c = _section(a, "council_approval")
    return bool(_text(c, "resolution")) and _past_date(c.get("date"), today) is not None


def entry_problems(a, today):
    """Sections filled in but not counted, each said plainly, so that a typo or a date still to come reads
    as not done rather than silently as absent."""
    out = []
    r = _section(a, "city_requestor")
    if _filled(r) and not _requested(a, today):
        why = ([] if _text(r, "name") else ["city_requestor.name is empty"]) + [p for p in [_date_problem("city_requestor", r, today)] if p]
        out.append("city_requestor is filled in but not counted: " + "; ".join(why))
    t = _section(a, "trust_determination")
    if _filled(t) and _trust(a, today) is None:
        res = _text(t, "result")
        why = ([] if res.lower() in TRUST_RESULTS else
               [f"trust_determination.result {res!r} is not one of: {', '.join(TRUST_RESULTS)}" if res
                else "trust_determination.result is empty"])
        why += ([] if _text(t, "by") else ["trust_determination.by is empty (who at the City gave the answer)"])
        why += [p for p in [_date_problem("trust_determination", t, today)] if p]
        out.append("trust_determination is filled in but not counted: " + "; ".join(why))
    c = _section(a, "council_approval")
    if _filled(c) and not _council_approved(a, today):
        why = ([] if _text(c, "resolution") else ["council_approval.resolution is empty"])
        why += [p for p in [_date_problem("council_approval", c, today)] if p]
        out.append("council_approval is filled in but not counted: " + "; ".join(why))
    return out


def approval_warnings(a, today):
    """For the operator, not staff: what the approval lacks before any staff sign-in sees the named list."""
    w = entry_problems(a, today)
    if not _requested(a, today):
        w.append("no city_requestor yet (name and date): record who at the City asked for access, and when, before issuing sign-ins")
    if _trust(a, today) is None:
        w.append(f"no trust_determination yet (result: one of {', '.join(TRUST_RESULTS)}, by, date): ask the City whether its "
                 "TRUST Ordinance (SDMC 210.0101-210.0112) applies")
    elif _trust(a, today) == "applies" and not _council_approved(a, today):
        w.append("the TRUST Ordinance applies and no council_approval is on record (resolution and date): Privacy Advisory "
                 "Board review and a Council vote come before any staff use")
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
        if p["facility_id"] in held:
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


def read_holds(path=None):
    """(ids, problem): the facility ids on hold in docs/holds.json, and why the file cannot be used (or
    None). No file: nothing is on hold. A file that is there but unreadable, or not {"facility_ids":
    [non-empty strings]}, is a problem, never an empty set: an empty set would release every hold."""
    path = Path(HOLDS if path is None else path)
    if not path.exists():
        return set(), None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return set(), f"{path} cannot be read ({type(e).__name__}: {e}); expected {HOLDS_FORMAT}"
    ids = raw.get("facility_ids") if isinstance(raw, dict) else None
    if not isinstance(ids, list) or not all(isinstance(i, str) and i.strip() for i in ids):
        return set(), f"{path} is not in the holds format; expected {HOLDS_FORMAT}"
    return {i.strip() for i in ids}, None


def load_holds_strict(path=None):
    """The ids on hold, for publish_city_site, deploy_api and export_worklist alike; stops the run when
    docs/holds.json cannot be used, since going on would release every hold."""
    held, problem = read_holds(path)
    if problem:
        sys.exit(f"stopped: {problem}. Fix it first: a holds file that cannot be read would release every hold.")
    return held


def hold_matches(held, listed):
    """(missing, typos): held ids not on the list, and {id: listed id} for those that match a listed id
    apart from case, which is a typo (ids are case-sensitive), never a place gone from the list."""
    missing = sorted(held - listed)
    lower = {}
    for fid in sorted(listed):
        lower.setdefault(fid.lower(), fid)
    return missing, {fid: lower[fid.lower()] for fid in missing if fid.lower() in lower}


def hold_problems(fc, details, held):
    """Held places on the list that would still show points or a band, in the list or in their place
    file (`details`: the place files as they will be written); a held place with no place file too."""
    bad = []
    for f in fc["features"]:
        p = f["properties"]
        fid = p["facility_id"]
        if fid not in held:
            continue
        if any(k in p for k in BAND_FIELDS) or not p.get("on_hold"):
            bad.append(f"{fid}: the list still carries its points or band")
        d = details.get(fid)
        if d is None:
            bad.append(f"{fid}: it has no place file")
        elif any(k in d for k in BAND_FIELDS) or not d.get("on_hold"):
            bad.append(f"{fid}: its place file still carries its points or band")
    return bad


def independence_problems(a):
    """Shown to staff, not a refusal: the operator named is one of the students who built the list."""
    adult = (a or {}).get("responsible_adult") or {}
    rel = (adult.get("relationship") or "").strip().lower()
    authors = {"chenhao zhang", "ayan pendharkar"}
    if rel in ("author", "student", "self") or (adult.get("name") or "").strip().lower() in authors:
        return ["no independent responsible adult: the operator named is a student author of the list"]
    return []


def monitor_summary(site=None):
    """The monitor's summary (export_site.py --monitor writes data/site/monitor_summary.json) for the staff
    copy of meta.json, as meta.monitor. A monitor that has not run, or whose summary cannot be read, is
    shipped as "failed" with a sentence saying so: /healthz reports it and the daily check opens an issue."""
    path = Path(SITE if site is None else site) / "monitor_summary.json"
    s = _json(path, None)
    nxt = s.get("next_window_date") if isinstance(s, dict) else None
    if (isinstance(s, dict) and s.get("status") in MONITOR_STATUSES
            and isinstance(s.get("runs"), int) and not isinstance(s.get("runs"), bool) and s["runs"] >= 0
            and isinstance(s.get("alerts"), list) and all(isinstance(a, str) and a.strip() for a in s["alerts"])
            and (nxt is None or (isinstance(nxt, str) and ISO_DATE.fullmatch(nxt)))):
        return s
    why = "has not run for this list" if not path.exists() else "wrote a summary that cannot be read"
    return {"status": "failed", "runs": 0, "alerts": [f"The monitor {why}."], "next_window_date": None}


def staff_meta(meta, approval, status, published_by, today, monitor=None):
    a = approval or {}
    adult, corr = a.get("responsible_adult") or {}, a.get("corrections_contact") or {}
    return {**meta, "audience": "staff", "sunset": a.get("sunset"), "access_approved": access_approved(a, today),
            "operator": {"name": adult.get("name"), "role": adult.get("relationship") or "responsible adult",
                         "email": adult.get("email")},
            "contact": {"name": corr.get("name"), "email": corr.get("email")},
            "review_status": status, **({"monitor": monitor} if monitor is not None else {}),
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

- source.tar.gz: the sdfood commit that built this site (`git archive` of site_code_sha in DEPLOYS.jsonl):
  food-dashboard, city_site/ and the scripts.
- export_source.tar.gz: only when it differs from that commit, the sdfood commit that built the list
  (export_code_sha in DEPLOYS.jsonl). To rebuild the list, use this one when it is here.
- rule.json: the frozen rule the list applies (docs/rule.json).
- pull_meta.json: the County pull the list was built from (date, count, sha256).
- STAFF_APPROVAL.json, holds.json: the release's approval and the places on hold.
- monitor.json, monitor.md, monitor_summary.json: the monitor's last scoring of the archived lists (the
  summary is also in the live meta.json, as monitor).
- archive/<run>/: every archived list (ranking.csv.gz, meta.json, manifest.json), written once and never
  changed. The prospective test scores the run registered in docs/prospective/REGISTERED.json against its
  hash there, and the monitor scores them all: no later export can rebuild them.

To rebuild: unpack source.tar.gz (or export_source.tar.gz), `pip install -r requirements.txt`, put
rule.json, STAFF_APPROVAL.json and holds.json in docs/, copy archive/* to data/site/archive/ and the
monitor files to data/site/, then `python refresh_city_site.py` (it pulls, exports with the frozen rule,
scores the archived lists, writes worklists and publishes here). docs/RUNBOOK.md in the source says the
rest, including how to hand the site over and how to take it down.
"""


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def registrations(path=None):
    """Every run registered for the prospective test (an older REGISTERED.json held a single one)."""
    reg = _json(REGISTERED if path is None else path, None)
    if reg is None:
        return []
    regs = reg.get("registrations", [reg]) if isinstance(reg, dict) else reg
    return [r for r in regs if isinstance(r, dict) and r.get("run")] if isinstance(regs, list) else []


def archive_problems(dirs, path=None):
    """Each registered run's ranking.csv.gz must be in one of `dirs` (archive folders) with its registered
    hash: the prospective test scores exactly that file, and nothing can rebuild it."""
    out = []
    for reg in registrations(path):
        found = [d / reg["run"] / "ranking.csv.gz" for d in dirs if (d / reg["run"] / "ranking.csv.gz").is_file()]
        if not any(_sha256(f) == reg.get("ranking_sha256") for f in found):
            out.append(f"the archive of the registered run {reg['run']} is " + ("not the registered file (its hash differs)"
                       if found else "missing") + f": restore data/site/archive/{reg['run']}/ from the private repository's "
                       "ops/archive/; the prospective test cannot be scored without it")
    return out


def copy_archives(ops, site=None):
    """Every archived list into ops/archive/, write-once: a run already there (with its manifest) is left
    exactly as it is. Returns the runs copied now."""
    src = Path(SITE if site is None else site) / "archive"
    copied = []
    for d in sorted(src.glob("forward_*")) if src.is_dir() else []:
        dest = ops / "archive" / d.name
        if d.is_dir() and not (dest / "manifest.json").exists():
            shutil.copytree(d, dest, dirs_exist_ok=True)
            copied.append(d.name)
    return copied


def write_ops(out, commit="HEAD", export_commit=None):
    """ops/ in the private checkout: the source of the site (`commit`) and, when it differs, of the list
    (`export_commit`), the frozen rule, pull meta, approval, holds, the monitor's output and every archived
    list. Stops, before anything is pushed, when a registered run's archive is not there with its hash."""
    ops = out / "ops"
    ops.mkdir(exist_ok=True)
    for old in ops.iterdir():
        if old.is_file():
            old.unlink()
    subprocess.run(["git", "archive", "--format=tar.gz", "-o", str(ops / "source.tar.gz"), commit], cwd=ROOT, check=True)
    if export_commit and export_commit != commit:
        r = subprocess.run(["git", "archive", "--format=tar.gz", "-o", str(ops / "export_source.tar.gz"), export_commit],
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode:
            (ops / "export_source.tar.gz").unlink(missing_ok=True)
            print(f"warning: the commit that built the list, {export_commit[:12]}, is not in this repository: "
                  "ops/ holds only the site's source")
    for src in (FROZEN, PULL_META, APPROVAL, HOLDS, *(SITE / name for name in MONITOR_FILES)):
        if src.exists():
            shutil.copy2(src, ops / src.name)
    for run_name in copy_archives(ops):
        print(f"ops/archive/{run_name}: copied")
    problems = archive_problems([ops / "archive"])
    if problems:
        sys.exit("NOT PUBLISHED to the staff site (nothing was pushed):\n  - " + "\n  - ".join(problems))
    (ops / "README.md").write_text(OPS_README, encoding="utf-8")


def head_commit():
    """This repository's HEAD, resolved once: the site's code, its archive and the record all name it."""
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def tree_problems():
    """A tracked file changed and not committed: the site is built from HEAD, so it would not ship."""
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    if not dirty:
        return []
    return [f"{len(dirty.splitlines())} tracked file(s) have uncommitted changes: commit or stash first; the staff site "
            "(food-dashboard, city_site/) is built from HEAD, so an uncommitted change would not be what ships"]


def site_code(commit):
    """{path: bytes} for every file of food-dashboard/ and city_site/ at `commit` (git archive): tracked
    files only, exactly as committed, whatever is on disk."""
    raw = subprocess.run(["git", "archive", "--format=tar", commit, "food-dashboard", "city_site"], cwd=ROOT,
                         capture_output=True, check=True).stdout
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as t:
        for m in t.getmembers():
            if m.isfile():
                files[m.name] = t.extractfile(m).read()
    return files


def write_site_code(out, files):
    """The site's code into the private checkout: food-dashboard/ (not its public/data, the sample) at the
    top, and server.mjs, render.yaml and the daily check from city_site/."""
    for name, body in files.items():
        path = PurePosixPath(name)
        if path.parts[0] != "food-dashboard" or path.parts[1:3] == ("public", "data"):
            continue
        dest = out.joinpath(*path.parts[1:])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
    for name, dest in (("city_site/server.mjs", out / "server.mjs"), ("city_site/render.yaml", out / "render.yaml"),
                       ("city_site/watch.yml", out / ".github" / "workflows" / "watch.yml")):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(files[name])


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
    """Apply docs/holds.json to the list that is live, and nothing else. A newly held id that is not on the
    live list (a typo, a wrong case) stops it before anything changes, and the result is checked before
    anything is written. Returns (the commit pushed or None, the live meta, the held ids, the ids newly held)."""
    problems = approval_problems(approval, today)
    if problems:
        sys.exit("NOT PUBLISHED to the staff site:\n  - " + "\n  - ".join(problems))
    data = out / "public" / "data"
    if not (data / "facilities.geojson").exists():
        sys.exit(f"{data} holds no live list: publish a full release first")
    held = load_holds_strict()
    check_target(push_urls(out), repo,
                 lambda r: run(["gh", "repo", "view", r, "--json", "visibility", "--jq", ".visibility"], out).strip())
    fc = json.loads((data / "facilities.geojson").read_text(encoding="utf-8"))
    listed = {f["properties"]["facility_id"] for f in fc["features"]}
    before, _ = read_holds(out / "ops" / HOLDS.name)             # the holds the last publish applied
    missing, typos = hold_matches(held, listed)
    # A new id must be on the list; an older one may have left it since (the County dropped the place).
    refused = [f"{fid} is not on the live list: did you mean {typos[fid]}? (ids are case-sensitive)" if fid in typos
               else f"{fid} is not on the live list (ids are case-sensitive: copy it from the place's page)"
               for fid in missing if fid in typos or fid not in before]
    if refused:
        sys.exit("NOT APPLIED: nothing was changed or pushed, so no hold is in place for:\n  - " + "\n  - ".join(refused))
    for fid in missing:
        print(f"warning: {fid} is held but no longer on the live list (it left the list after it was held)")
    was_held = {f["properties"]["facility_id"] for f in fc["features"] if f["properties"].get("on_hold")}
    details = {fid: _json(data / "place" / f"{fid}.json", None) for fid in held & listed}
    changed = apply_holds(fc, details, held)
    bad = hold_problems(fc, changed, held)
    if bad:
        sys.exit("NOT APPLIED: nothing was changed or pushed:\n  - " + "\n  - ".join(bad))
    for fid, d in changed.items():
        (data / "place" / f"{fid}.json").write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    (data / "facilities.geojson").write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
    if HOLDS.exists():
        (out / "ops").mkdir(exist_ok=True)
        shutil.copy2(HOLDS, out / "ops" / HOLDS.name)
    newly = sorted((held & listed) - was_held)
    for fid in newly:
        print(f"held now: {fid}")
    meta = _json(data / "meta.json", {})
    if not subprocess.run(["git", "status", "--porcelain"], cwd=out, capture_output=True, text=True).stdout.strip():
        return None, meta, held, newly                               # nothing changed: no record, no push
    at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    history = out / "DEPLOYS.jsonl"
    prior = history.read_text(encoding="utf-8") if history.exists() else ""
    history.write_text(prior + json.dumps({"at": at, "run": meta.get("run"), "holds_only": True, "by": getpass.getuser(),
                                           "held": sorted(held), "newly_held": newly}) + "\n", encoding="utf-8")
    commit = commit_and_push(out, f"City site: holds only ({len(held)} held, {len(newly)} newly held), {meta.get('run')}")
    return commit, meta, held, newly


def wait_or_say(url, commit, done):
    """Wait until `url` serves `commit`. When it does not in time, the push has happened all the same: say
    so, and return EXIT_NOT_SERVED (never "the live site is unchanged")."""
    h = wait_live(url, commit)
    if not h:
        print(f"pushed {commit[:7]}, but {url} did not serve it within 15 minutes. It may still deploy: check the "
              f"service's Events on Render and {url.rstrip('/')}/healthz. Do not publish or refresh again for this; if "
              "the deploy failed, fix the cause and deploy again on Render, then check /healthz.", file=sys.stderr)
        return EXIT_NOT_SERVED
    print(done(h))
    return 0


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
    if not shutil.which("gh"):
        sys.exit(f"NOT PUBLISHED: the GitHub CLI (gh) is not installed. Install it, then run gh auth login as an account "
                 f"that can push to {args.repo}.")
    if args.holds_only:
        ensure_checkout(out, args.repo)
        commit, meta, held, newly = holds_only(out, approval, today, args.repo)
        print(f"holds: {len(held)} held, {len(newly)} newly held" + (f" ({', '.join(newly)})" if newly else "")
              + (f"; pushed {commit[:7]}" if commit else "; nothing changed, nothing pushed"))
        if commit and args.wait:
            return wait_or_say(args.wait, commit, lambda h: f"live: {args.wait} serves {h.get('run')} with the holds")
        return 0
    meta = json.loads((SITE / "meta.json").read_text(encoding="utf-8"))
    live = _json(out / "public" / "data" / "meta.json", None)
    head = head_commit()                                      # the site's code, its archive and the record: one commit
    export_sha = (meta.get("provenance") or {}).get("code_sha") or ""
    problems = (approval_problems(approval, today) + export_problems(meta, live, today, force=args.force)
                + frozen_problems(meta) + tree_problems())
    held, holds_problem = read_holds()
    problems += [holds_problem] if holds_problem else []
    fc = json.loads((SITE / "facilities.geojson").read_text(encoding="utf-8"))
    missing, typos = hold_matches(held, {f["properties"]["facility_id"] for f in fc["features"]})
    problems += [f"docs/holds.json holds {fid}, which is not on the list: did you mean {typos[fid]}? (ids are "
                 "case-sensitive)" for fid in sorted(typos)]
    details = {fid: _json(SITE / "place" / f"{fid}.json", None) for fid in held - set(missing)}
    changed = apply_holds(fc, details, held)
    problems += hold_problems(fc, changed, held)
    problems += archive_problems([SITE / "archive", out / "ops" / "archive"])
    if problems:
        sys.exit("NOT PUBLISHED to the staff site:\n  - " + "\n  - ".join(problems))
    for fid in missing:
        if fid not in typos:
            print(f"warning: docs/holds.json holds {fid}, which is not on this list (it left the list after it was held)")
    for w in approval_warnings(approval, today) + [w for w in [unpushed_warning()] if w]:
        print(f"warning: {w}")
    if export_sha != head:
        print(f"warning: the list was built by sdfood@{export_sha[:7]} and the site is sdfood@{head[:7]}: ops/ keeps "
              "the source of both, and DEPLOYS.jsonl names both")
    if "onedrive" in str(ROOT).lower():
        print("warning: this checkout, and the real export in it, sit in a OneDrive-synced folder (see docs/STAFF_SITE.md)")
    code = site_code(head)

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

    for p in out.iterdir():                                   # a clean copy each time, keeping .git, .github, ops, the history
        if p.name in KEEP:
            continue
        if p.is_dir():                                        # OneDrive may hold an emptied folder: leave it
            shutil.rmtree(p, onexc=lambda fn, path, exc: None if fn is os.rmdir else (_ for _ in ()).throw(exc))
        else:
            p.unlink()
    # The site's code as committed at `head`, never the working tree: an uncommitted edit cannot ship.
    write_site_code(out, code)
    data = out / "public" / "data"
    data.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SITE / "place", data / "place", dirs_exist_ok=True)
    for fid, d in changed.items():
        (data / "place" / f"{fid}.json").write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    (data / "facilities.geojson").write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
    status = (open_items(approval, today) + independence_problems(approval) + drift_items(meta)
              + review_status(meta, today))
    shipped = staff_meta(meta, approval, status, getpass.getuser(), today, monitor_summary())
    (data / "meta.json").write_text(json.dumps(shipped, indent=2), encoding="utf-8")
    # Only here, in the private repository: tells the site's build (scripts/exportGate.mjs, vite.config.js)
    # that this is the signed-in staff site, whose unpublished export is checked in review mode.
    (out / STAFF_MARKER).write_text("The City staff site. Private: never publish this repository or its build.\n",
                                    encoding="utf-8")
    write_ops(out, head, export_sha)
    (out / "README.md").write_text(
        "# San Diego Food Inspection Record: City staff site\n\nPRIVATE. Generated by publish_city_site.py in "
        "the sdfood repository; do not edit here. Holds the real export: never make this repository public, "
        "fork it, or connect it to a public repository.\n", encoding="utf-8")

    # The deploy history travels with the site, so whoever owns it at the City can see every release, and
    # which code built the site and which built the list.
    shas = {"site_code_sha": head, "export_code_sha": export_sha}
    history = out / "DEPLOYS.jsonl"
    prior = history.read_text(encoding="utf-8") if history.exists() else ""
    history.write_text(prior + json.dumps({"at": shipped["staff_release"]["at"], "run": meta["run"],
                                           "places": meta.get("places"), "by": shipped["staff_release"]["by"], **shas,
                                           "review_status": status, "held": sorted(held),
                                           "monitor": shipped.get("monitor", {}).get("status")}) + "\n", encoding="utf-8")
    commit = commit_and_push(out, f"City site: {meta['run']}, inspections through {meta['inspections_through']}, "
                                  f"site from sdfood@{head[:7]}, list from sdfood@{export_sha[:7]}")
    if commit is None:
        print("nothing changed")
        return 0
    DEPLOY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DEPLOY_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": shipped["staff_release"]["at"], "run": meta["run"], "places": meta.get("places"),
                             "commit": commit, "source": head[:7], **shas, "by": shipped["staff_release"]["by"],
                             "review_status": status, "held": sorted(held)}) + "\n")
    print(f"pushed {meta['run']} ({meta['places']} places) to {args.repo} as {commit[:7]}"
          + (f"; {len(status)} public-release gates not passed, shown to staff" if status else ""))
    if args.wait:
        return wait_or_say(args.wait, commit, lambda h: f"live: {args.wait} serves {h.get('run')} (expires {h.get('expires')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
