"""Refresh the City staff site in one command: pull the County's results, export with the frozen
rule, score earlier lists against what happened since (the monitor), write the month's worklists,
publish to the private repository, and wait until Render serves it (docs/RUNBOOK.md).

    SDFOOD_CONTACT=you@example.org python refresh_city_site.py
    python refresh_city_site.py --check              # what a refresh needs, checked, changing nothing
    python refresh_city_site.py --skip-fetch         # the pull is already complete: export and publish only

An export stays current for about 13 days after its pull: it expires 14 days after the County's
record ends, and the record lags the pull by about a day. Run this weekly. To schedule it on Windows:
    schtasks /Create /SC WEEKLY /D MON /ST 06:00 /TN "sdfood refresh" /TR "cmd /c cd /d <repo> && set SDFOOD_CONTACT=<email> && python refresh_city_site.py > data\\refresh.log 2>&1"

Stops at the first step that fails, and says what to do. A refused pull (fetch_sdfood.py exit 3) is
final: the site keeps serving the last list until it expires, then shows only a search of the
record. An interrupted pull resumes on the next run, unless it was started more than STALE_DAYS
ago: then it is set aside and the pull starts over, so one list never mixes weeks."""
import argparse, json, os, shutil, subprocess, sys, time, urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE_URL = "https://sdfood-city.onrender.com"
PY = sys.executable
PARTIAL = ROOT / "data" / "sd_businesses.partial.json"
PARTIAL_META = ROOT / "data" / "pull_meta.partial.json"
STALE_DAYS = 2


def step(name, cmd, run=subprocess.run):
    print(f"\n== {name}: {' '.join(cmd[1:])}", flush=True)
    return run(cmd, cwd=ROOT).returncode


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
    stamp = time.strftime("%Y%m%dT%H%M%S")
    for p in (PARTIAL, PARTIAL_META):
        if p.exists():
            shutil.move(str(p), str(p.with_name(f"{p.name}.stale-{stamp}")))


def checks(skip_fetch=False, url=SITE_URL, today=None, *, sh=None, fetch=None):
    """(ok, lines): everything a refresh needs, checked without changing anything."""
    import publish_city_site as pcs
    today = today or date.today()
    sh = sh or (lambda cmd: subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True))
    lines, ok = [], True

    def check(good, what, fix=""):
        nonlocal ok
        ok &= bool(good)
        lines.append(f"[{'ok' if good else 'NO'}] {what}" + ("" if good or not fix else f": {fix}"))

    if not skip_fetch:
        check(os.environ.get("SDFOOD_CONTACT", "").strip(), "SDFOOD_CONTACT is set (the scraper's User-Agent contact)",
              "set it to a real email")
    state = partial_state(today)
    lines.append(f"[..] partial pull: {state}" + (" (it will be set aside and the pull starts over)" if state == "stale" else ""))
    approval = pcs._json(pcs.APPROVAL, None)
    problems = pcs.approval_problems(approval, today)
    check(not problems, "docs/STAFF_APPROVAL.json is complete and in date", "; ".join(problems))
    dirty = sh(["git", "status", "--porcelain", "--untracked-files=no"]).stdout.strip()
    check(not dirty, "the code is committed (an export from uncommitted code is refused)", "commit or stash first")
    rule = sh(["git", "show", "HEAD:docs/rule.json"])
    check(rule.returncode == 0, "the frozen rule docs/rule.json is committed",
          "the first export writes it; review and commit it before publishing")
    check(shutil.which("node"), "node is installed (the export's contract check)", "install Node 24")
    check(sh(["gh", "auth", "status"]).returncode == 0, "gh is signed in (the publish pushes to the private repository)",
          "gh auth login")
    for w in pcs.open_items(approval):
        lines.append(f"[..] not yet done: {w}")
    fetch = fetch or (lambda u: json.loads(urllib.request.urlopen(u, timeout=90).read()))
    try:
        h = fetch(f"{url.rstrip('/')}/healthz")
        exp = h.get("expires")
        left = (date.fromisoformat(exp) - today).days if exp else None
        lines.append(f"[..] live: {h.get('run')}, expires {exp} ({left} days left)"
                     + ("; the rule needs a refit" if h.get("refit_needed") else "") + (f"; closed: {h['closed']}" if h.get("closed") else ""))
    except Exception as e:                            # the site asleep or down is not a reason not to refresh
        lines.append(f"[..] live site not reachable ({type(e).__name__}); a refresh will still publish")
    return ok, lines


def main(argv=None, run=subprocess.run):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--skip-fetch", action="store_true", help="export and publish the pull already on disk")
    ap.add_argument("--url", default=SITE_URL, help="the staff site, to wait until it serves the new list")
    ap.add_argument("--no-wait", action="store_true")
    ap.add_argument("--check", action="store_true", help="check what a refresh needs and change nothing")
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
        state = partial_state()
        if state == "stale":
            print(f"A partial pull started more than {STALE_DAYS} days ago: setting it aside and pulling afresh.")
            set_aside_partial()
        code = step("pull", [PY, "fetch_sdfood.py", *(["--resume"] if state == "resume" else [])], run)
        if code == 3:
            print("\nThe County's site refused the pull. That is final: do not retry or work around it. The staff site keeps "
                  "serving the last list until it expires. See docs/RUNBOOK.md, 'The pull was refused'.", file=sys.stderr)
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
        print(f"\nexport failed (exit {code}); nothing after it ran. The live site is unchanged.", file=sys.stderr)
        return code
    # The monitor scores every archived list against the inspections since; it never blocks a refresh.
    if step("monitor", [PY, "export_site.py", "--monitor"], run):
        print("warning: the monitor did not run; see data/site/monitor.md next time", file=sys.stderr)
    for name, cmd in (("worklists", [PY, "export_worklist.py", "--no-backtest"]),
                      ("publish", [PY, "publish_city_site.py", *([] if args.no_wait else ["--wait", args.url])])):
        code = step(name, cmd, run)
        if code:
            print(f"\n{name} failed (exit {code}); nothing after it ran. The live site is unchanged.", file=sys.stderr)
            return code
    print("\nrefreshed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
