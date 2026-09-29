"""Refresh the City staff site in one command: pull the County's results, export, write the month's
worklists, publish to the private repository, and wait until Render serves it (docs/RUNBOOK.md).

    SDFOOD_CONTACT=you@example.org python refresh_city_site.py
    python refresh_city_site.py --skip-fetch         # the pull is already complete: export and publish only

An export stays current for about 9 days after its pull (it expires 14 days after the County's record
ends, and the record lags the pull by about 5), so run this weekly. To schedule it on Windows:
    schtasks /Create /SC WEEKLY /D MON /ST 06:00 /TN "sdfood refresh" /TR "cmd /c cd /d <repo> && set SDFOOD_CONTACT=<email> && python refresh_city_site.py > data\\refresh.log 2>&1"

Stops at the first step that fails, and says what to do. A refused pull (fetch_sdfood.py exit 3) is
final: the site keeps serving the last list until it expires, then shows only a search of the record."""
import argparse, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE_URL = "https://sdfood-city.onrender.com"
PY = sys.executable


def step(name, cmd, run=subprocess.run):
    print(f"\n== {name}: {' '.join(cmd[1:])}", flush=True)
    return run(cmd, cwd=ROOT).returncode


def main(argv=None, run=subprocess.run):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--skip-fetch", action="store_true", help="export and publish the pull already on disk")
    ap.add_argument("--url", default=SITE_URL, help="the staff site, to wait until it serves the new list")
    ap.add_argument("--no-wait", action="store_true")
    args = ap.parse_args(argv)
    if not args.skip_fetch:
        if not os.environ.get("SDFOOD_CONTACT", "").strip():
            print("Set SDFOOD_CONTACT to a real email (it goes in the scraper's User-Agent).", file=sys.stderr)
            return 2
        resume = ["--resume"] if (ROOT / "data" / "sd_businesses.partial.json").exists() else []
        code = step("pull", [PY, "fetch_sdfood.py", *resume], run)
        if code == 3:
            print("\nThe County's site refused the pull. That is final: do not retry or work around it. The staff site keeps "
                  "serving the last list until it expires. See docs/RUNBOOK.md, 'The pull was refused'.", file=sys.stderr)
            return 3
        if code:
            print("\nThe pull stopped before it finished. Run this again: it resumes where it stopped.", file=sys.stderr)
            return code
    for name, cmd in (("export", [PY, "export_site.py"]),
                      ("worklists", [PY, "export_worklist.py", "--no-backtest"]),
                      ("publish", [PY, "publish_city_site.py", *([] if args.no_wait else ["--wait", args.url])])):
        code = step(name, cmd, run)
        if code:
            print(f"\n{name} failed (exit {code}); nothing after it ran. The live site is unchanged.", file=sys.stderr)
            return code
    print("\nrefreshed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
