"""Refresh the City staff site in one command: pull the County's results, export with the frozen
rule, score earlier lists against what happened since (the monitor), write the month's worklists,
publish to the private repository, and wait until Render serves it (docs/RUNBOOK.md).

    SDFOOD_CONTACT=you@example.org python refresh_city_site.py
    python refresh_city_site.py --check              # what a refresh needs, checked, changing nothing
    python refresh_city_site.py --skip-fetch         # the pull is already complete: export and publish only
    python refresh_city_site.py --repo OWNER/NAME --dir PATH   # another deploy repository (passed to the publish)

An export stays current for about 13 days after its pull: it expires 14 days after the County's
record ends, and the record lags the pull by about a day. Run this weekly. To schedule it on Windows:
    schtasks /Create /SC WEEKLY /D MON /ST 06:00 /TN "sdfood refresh" /TR "cmd /c cd /d <repo> && set SDFOOD_CONTACT=<email> && python refresh_city_site.py > data\\refresh.log 2>&1"
and to stop it (at the take-down, or after a refusal):
    schtasks /Delete /TN "sdfood refresh" /F

Before it pulls anything it runs the checks --check prints, and stops on any line marked NO: nothing is
taken from the County for a list that could not be published (an approval out of date or past its
sunset, uncommitted code, no committed rule, no GitHub CLI). A refused pull (fetch_sdfood.py exit 3) is
final and kept on record in data/PULL_REFUSED.json: every later run stops there, before any request to
the County, until that file is removed, which only the County's written OK allows. The site keeps
serving the last list until it expires, then shows only a search of the record. An interrupted pull
resumes on the next run, unless it was started more than STALE_DAYS ago: then it is set aside and the
pull starts over, so one list never mixes weeks (a partial pull that records a refusal is never set
aside).

Exit codes: 0 refreshed; 2 not ready (a check said NO, or no SDFOOD_CONTACT), nothing pulled; 3 a refusal
is on record, nothing pulled; 4 the County's listing ran out (the partial pull is kept); 5 the publish
pushed, but Render did not serve it in time (do not run this again for that); any other code is the
failing step's, with the live site unchanged."""
import argparse, json, os, shutil, subprocess, sys, time, urllib.request
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
SITE_URL = "https://sdfood-city.onrender.com"
PY = sys.executable
PARTIAL = ROOT / "data" / "sd_businesses.partial.json"
PARTIAL_META = ROOT / "data" / "pull_meta.partial.json"
REFUSED = ROOT / "data" / "PULL_REFUSED.json"        # fetch_sdfood.py keeps a refusal here
MONITOR_SUMMARY = ROOT / "data" / "site" / "monitor_summary.json"
STALE_DAYS = 2
DELETE_TASK = 'schtasks /Delete /TN "sdfood refresh" /F'
EXIT_NOT_SERVED = 5                                   # = publish_city_site.EXIT_NOT_SERVED


def step(name, cmd, run=subprocess.run):
    print(f"\n== {name}: {' '.join(cmd[1:])}", flush=True)
    return run(cmd, cwd=ROOT).returncode


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rel(path):
    try:
        return Path(path).relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def refusal_on_record():
    """The refusal on record, or None: data/PULL_REFUSED.json (a file there that does not parse still
    counts), or a partial pull's meta, or a copy of one set aside, that records a refusal."""
    if REFUSED.exists():
        rec = _read(REFUSED)
        return rec if isinstance(rec, dict) and rec else {"detail": f"{REFUSED.name} is present"}
    for path in sorted(PARTIAL_META.parent.glob(PARTIAL_META.name + "*")):
        meta = _read(path)
        if isinstance(meta, dict) and meta.get("refused"):
            r = meta["refused"]
            return {**(r if isinstance(r, dict) else {"detail": str(r)}), "from": path.name}
    return None


def partial_state(today=None):
    """"none", "resume" (a partial pull started within STALE_DAYS) or "stale"."""
    if not PARTIAL.exists():
        return "none"
    try:
        started = date.fromisoformat(json.loads(PARTIAL_META.read_text(encoding="utf-8")).get("started") or "")
    except (OSError, ValueError):
        return "stale"
    return "resume" if ((today or date.today()) - started).days <= STALE_DAYS else "stale"


def set_aside_partial():
    """Move a stale partial pull aside. Never one whose meta records a refusal: that record must stay."""
    meta = _read(PARTIAL_META)
    if isinstance(meta, dict) and meta.get("refused"):
        return False
    stamp = time.strftime("%Y%m%dT%H%M%S")
    for p in (PARTIAL, PARTIAL_META):
        if p.exists():
            shutil.move(str(p), str(p.with_name(f"{p.name}.stale-{stamp}")))
    return True


def checks(skip_fetch=False, url=SITE_URL, today=None, *, sh=None, fetch=None, live=True):
    """(ok, lines): everything a refresh needs, checked without changing anything. `live` also reads the
    live site's /healthz (for information only; it never makes a check fail)."""
    import publish_city_site as pcs
    today = today or date.today()
    raw_sh = sh or (lambda cmd: subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True))

    def sh(cmd):                                      # a missing tool is a NO line, never a crash
        try:
            return raw_sh(cmd)
        except OSError as e:
            return SimpleNamespace(returncode=127, stdout="", stderr=f"{cmd[0]}: {e}")

    lines, ok = [], True

    def check(good, what, fix=""):
        nonlocal ok
        ok &= bool(good)
        lines.append(f"[{'ok' if good else 'NO'}] {what}" + ("" if good or not fix else f": {fix}"))

    if not skip_fetch:
        check(os.environ.get("SDFOOD_CONTACT", "").strip(), "SDFOOD_CONTACT is set (the scraper's User-Agent contact)",
              "set it to a real email")
        refused = refusal_on_record()
        check(refused is None, "no refusal of the pull is on record",
              f"{json.dumps(refused)}: that is final; remove {_rel(REFUSED)} only with the County's written OK "
              "(docs/RUNBOOK.md, 'The pull was refused')")
        state = partial_state(today)
        lines.append(f"[..] partial pull: {state}" + (" (it will be set aside and the pull starts over)" if state == "stale" else ""))
    approval = pcs._json(pcs.APPROVAL, None)
    problems = pcs.approval_problems(approval, today)
    check(not problems, "docs/STAFF_APPROVAL.json is complete and in date", "; ".join(problems))
    status = sh(["git", "status", "--porcelain", "--untracked-files=no"])
    check(status.returncode == 0 and not status.stdout.strip(), "the code is committed (an export from uncommitted code is refused)",
          "commit or stash first" if status.returncode == 0 else "git is not installed, or this is not a checkout")
    rule = sh(["git", "show", "HEAD:docs/rule.json"])
    check(rule.returncode == 0, "the frozen rule docs/rule.json is committed",
          "the first export writes it; review and commit it before publishing")
    check(shutil.which("node"), "node is installed (the export's contract check)", "install Node 24")
    gh = shutil.which("gh")
    check(gh, "gh is installed (the publish pushes to the private repository)",
          "install the GitHub CLI, then gh auth login as an account that can push to the private repository")
    if gh:
        check(sh(["gh", "auth", "status"]).returncode == 0, "gh is signed in", "gh auth login")
    for w in pcs.entry_problems(approval, today) + pcs.open_items(approval, today):
        lines.append(f"[..] not yet done: {w}")
    if live:
        fetch = fetch or (lambda u: json.loads(urllib.request.urlopen(u, timeout=90).read()))
        try:
            h = fetch(f"{url.rstrip('/')}/healthz")
            exp = h.get("expires")
            left = (date.fromisoformat(exp) - today).days if exp else None
            lines.append(f"[..] live: {h.get('run')}, expires {exp} ({left} days left)"
                         + ("; the rule needs a refit" if h.get("refit_needed") else "")
                         + ("; the monitor has an alert" if h.get("monitor_alert") else "")
                         + (f"; closed: {h['closed']}" if h.get("closed") else ""))
        except Exception as e:                        # the site asleep or down is not a reason not to refresh
            lines.append(f"[..] live site not reachable ({type(e).__name__}); a refresh will still publish")
    return ok, lines


def monitor_headline(path=None):
    """The monitor's summary in a line or two, for every run's log (data/site/monitor_summary.json)."""
    s = _read(MONITOR_SUMMARY if path is None else path)
    if not isinstance(s, dict):
        return ["monitor: no summary (data/site/monitor_summary.json)"]
    out = [f"monitor: {s.get('status')}, {s.get('runs', 0)} archived list(s) scored"
           + (f"; next window {s['next_window_date']}" if s.get("next_window_date") else "")]
    return out + [f"monitor alert: {a}" for a in s.get("alerts") or []]


def monitor_failed(path=None):
    """The monitor did not run for this list: say so in its summary, so the publish ships status "failed"
    and the daily check opens an issue, rather than last week's summary."""
    path = MONITOR_SUMMARY if path is None else path
    if path.parent.is_dir():
        path.write_text(json.dumps({"status": "failed", "runs": 0, "alerts": ["The monitor did not run for this list."],
                                    "next_window_date": None}, indent=2), encoding="utf-8")


def main(argv=None, run=subprocess.run):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--skip-fetch", action="store_true", help="export and publish the pull already on disk")
    ap.add_argument("--url", default=SITE_URL, help="the staff site, to wait until it serves the new list")
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--check", action="store_true", help="check what a refresh needs and change nothing")
    ap.add_argument("--repo", help="the private deploy repository, OWNER/NAME (passed to publish_city_site.py)")
    ap.add_argument("--dir", help="its local checkout (passed to publish_city_site.py)")
    args = ap.parse_args(argv)
    if args.check:
        ok, lines = checks(args.skip_fetch, args.url)
        print("\n".join(lines))
        print("\nready to refresh." if ok else "\nnot ready: fix the lines marked NO.")
        return 0 if ok else 1
    if not args.skip_fetch:
        if not os.environ.get("SDFOOD_CONTACT", "").strip():
            print("Set SDFOOD_CONTACT to a real email (it goes in the scraper's User-Agent).", file=sys.stderr)
            return 2
        refused = refusal_on_record()
        if refused is not None:
            print(f"A refusal of the pull is on record ({json.dumps(refused)}): not pulling. That is final: do not retry or "
                  f"work around it. Remove {_rel(REFUSED)} only with the County's written OK (docs/RUNBOOK.md, "
                  f"'The pull was refused'). Stop the scheduled run: {DELETE_TASK}", file=sys.stderr)
            return 3
    # Nothing is pulled for a list that could not be published. The live site is not read here.
    ok, lines = checks(args.skip_fetch, args.url, live=False)
    if not ok:
        no = [line for line in lines if line.startswith("[NO]")]
        print("Not refreshing, and nothing was pulled: fix the lines marked NO first "
              "(python refresh_city_site.py --check).\n" + "\n".join(no), file=sys.stderr)
        if any("has passed" in line for line in no):
            print(f"The sunset date has passed: take the site down (docs/RUNBOOK.md, 'Taking it down'), starting with the "
                  f"scheduled run: {DELETE_TASK}", file=sys.stderr)
        return 2
    if not args.skip_fetch:
        state = partial_state()
        if state == "stale":
            print(f"A partial pull started more than {STALE_DAYS} days ago: setting it aside and pulling afresh.")
            set_aside_partial()
        code = step("pull", [PY, "fetch_sdfood.py", *(["--resume"] if state == "resume" else [])], run)
        if code == 3:
            print("\nThe County's site refused the pull. That is final: do not retry or work around it. It is kept on record "
                  f"({_rel(REFUSED)}), so no later run pulls. The staff site keeps serving the last list until it "
                  f"expires. Stop the scheduled run: {DELETE_TASK}. See docs/RUNBOOK.md, 'The pull was refused'.",
                  file=sys.stderr)
            return 3
        if code == 4:
            print("\nThe County's listing ran out before every business appeared (exit 4). The partial pull is kept; run this "
                  "again later and it resumes. If it happens twice, see docs/RUNBOOK.md, 'The pull is incomplete'.", file=sys.stderr)
            return 4
        if code:
            print("\nThe pull stopped before it finished. Run this again: it resumes where it stopped.", file=sys.stderr)
            return code
    code = step("export", [PY, "export_site.py"], run)
    if code:
        print(f"\nexport failed (exit {code}); nothing after it ran. The live site is unchanged. Once it is fixed, run this "
              "again with --skip-fetch: the pull is complete.", file=sys.stderr)
        return code
    # The monitor scores every archived list against the inspections since; it never blocks a refresh, but a
    # monitor that did not run is said in the staff copy of meta.json (meta.monitor, status "failed"), on the
    # staff site's /healthz (monitor_alert) and by the daily check.
    if step("monitor", [PY, "export_site.py", "--monitor"], run):
        monitor_failed()
        print("warning: the monitor did not run (its error is above); the staff site's health check and the daily check "
              "will say so (docs/RUNBOOK.md, 'Reading the monitor')", file=sys.stderr)
    for line in monitor_headline():
        print(line)
    publish = [PY, "publish_city_site.py", *(["--repo", args.repo] if args.repo else []),
               *(["--dir", args.dir] if args.dir else []), *([] if args.no_wait else ["--wait", args.url])]
    for name, cmd in (("worklists", [PY, "export_worklist.py", "--no-backtest"]), ("publish", publish)):
        code = step(name, cmd, run)
        if name == "publish" and code == EXIT_NOT_SERVED:
            print(f"\nThe publish pushed the new list, but Render did not serve it within 15 minutes. It may still deploy: "
                  f"check the service's Events on Render and {args.url.rstrip('/')}/healthz. Do not run the refresh again "
                  "for this (it would pull from the County again); if the deploy failed, fix the cause and deploy again on "
                  "Render.", file=sys.stderr)
            return code
        if code:
            print(f"\n{name} failed (exit {code}); nothing after it ran. Unless the publish printed \"pushed\" above, the live "
                  "site is unchanged. Once it is fixed, run this again with --skip-fetch: the pull is complete.",
                  file=sys.stderr)
            return code
    print("\nrefreshed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
