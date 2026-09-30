"""refresh_city_site.py: the checks run before any pull and stop it on any NO; the steps run in order and
stop at the first failure; a refused pull is final and stays on record; a stale partial pull is set aside
(never one that records a refusal); a push Render did not serve in time is said as such; and --check
changes nothing, even without the GitHub CLI."""
import json
from datetime import date
from types import SimpleNamespace

import pytest

import refresh_city_site as r


def runner(codes):
    ran = []

    def run(cmd, cwd=None):
        name = " ".join(cmd[1:3]) if cmd[1:3] == ["export_site.py", "--monitor"] else cmd[1]
        ran.append(" ".join(cmd[1:]))
        return SimpleNamespace(returncode=codes.get(name, 0))
    run.ran = ran
    return run


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Every path a refresh reads or writes is in tmp_path; the checks pass unless a test says otherwise."""
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    monkeypatch.setattr(r, "PARTIAL", tmp_path / "sd_businesses.partial.json")
    monkeypatch.setattr(r, "PARTIAL_META", tmp_path / "pull_meta.partial.json")
    monkeypatch.setattr(r, "REFUSED", tmp_path / "PULL_REFUSED.json")
    (tmp_path / "site").mkdir()
    monkeypatch.setattr(r, "MONITOR_SUMMARY", tmp_path / "site" / "monitor_summary.json")
    seen = []
    monkeypatch.setattr(r, "checks", lambda *a, **k: seen.append(k) or (True, ["[ok] everything"]))
    return seen


def test_a_refresh_pulls_exports_monitors_writes_worklists_and_publishes_in_order(isolated):
    run = runner({})
    assert r.main([], run=run) == 0
    assert run.ran == ["fetch_sdfood.py", "export_site.py", "export_site.py --monitor", "export_worklist.py --no-backtest",
                       "publish_city_site.py --wait https://sdfood-city.onrender.com"]
    assert isolated == [{"live": False}], "the checks ran first, without waiting on the live site"


def test_any_no_stops_the_refresh_before_anything_is_pulled(monkeypatch, capsys):
    monkeypatch.setattr(r, "checks", lambda *a, **k: (False, ["[ok] node is installed", "[NO] the code is committed: commit"]))
    run = runner({})
    assert r.main([], run=run) == 2 and run.ran == []
    err = capsys.readouterr().err
    assert "nothing was pulled" in err and "[NO] the code is committed" in err and "[ok] node" not in err
    assert r.main(["--skip-fetch"], run=run) == 2 and run.ran == [], "nor exported"


def test_past_the_sunset_the_refresh_says_to_take_the_site_down(monkeypatch, capsys):
    monkeypatch.setattr(r, "checks", lambda *a, **k: (False, ["[NO] docs/STAFF_APPROVAL.json is complete and in date: the "
                                                              "sunset date 2026-01-01 has passed: take the site down"]))
    run = runner({})
    assert r.main([], run=run) == 2 and run.ran == []
    assert r.DELETE_TASK in capsys.readouterr().err


def test_a_refused_pull_is_final_and_nothing_else_runs(capsys):
    run = runner({"fetch_sdfood.py": 3})
    assert r.main([], run=run) == 3 and len(run.ran) == 1
    err = capsys.readouterr().err
    assert "do not retry" in err and r.DELETE_TASK in err


def test_a_refusal_on_record_stops_every_later_run_before_the_pull(capsys):
    r.REFUSED.write_text(json.dumps({"status": 429, "page": 3}), encoding="utf-8")
    run = runner({})
    assert r.main([], run=run) == 3 and run.ran == []
    err = capsys.readouterr().err
    assert '"status": 429' in err and "written OK" in err and r.DELETE_TASK in err
    r.REFUSED.write_text("not json", encoding="utf-8")
    assert r.main([], run=run) == 3 and run.ran == [], "a file there that does not parse still counts"
    assert r.main(["--skip-fetch", "--no-wait"], run=run) == 0, "a re-export of the pull on disk asks nothing of the County"


def test_a_stale_partial_that_records_a_refusal_is_never_set_aside():
    r.PARTIAL.write_text("[]", encoding="utf-8")
    r.PARTIAL_META.write_text(json.dumps({"started": "2026-01-01", "refused": {"status": 403}}), encoding="utf-8")
    assert r.partial_state(date(2026, 9, 29)) == "stale"
    run = runner({})
    assert r.main([], run=run) == 3 and run.ran == []
    assert r.PARTIAL_META.exists() and r.set_aside_partial() is False and r.PARTIAL_META.exists()
    assert json.loads(r.REFUSED.read_text(encoding="utf-8"))["status"] == 403, "the refusal is copied into PULL_REFUSED.json"
    r.REFUSED.unlink()
    r.PARTIAL_META.rename(r.PARTIAL_META.with_name(r.PARTIAL_META.name + ".stale-20260101T000000"))
    assert r.refusal_on_record()["status"] == 403, "nor does a copy set aside by an older version lose it"
    r.REFUSED.write_text(json.dumps({"status": 401, "page": 1}), encoding="utf-8")
    r.refusal_on_record()
    assert json.loads(r.REFUSED.read_text(encoding="utf-8"))["status"] == 401, "the first refusal on record is never overwritten"


def test_an_incomplete_listing_is_said_plainly(capsys):
    run = runner({"fetch_sdfood.py": 4})
    assert r.main([], run=run) == 4 and len(run.ran) == 1
    assert "ran out before every business appeared" in capsys.readouterr().err


def test_a_failed_export_stops_before_publishing(capsys):
    run = runner({"export_site.py": 1})
    assert r.main([], run=run) == 1 and run.ran == ["fetch_sdfood.py", "export_site.py"]
    assert "--skip-fetch" in capsys.readouterr().err, "a failure after the pull does not cost another pull"


def test_the_monitor_never_blocks_a_refresh_but_a_failure_is_shipped(capsys):
    run = runner({"export_site.py --monitor": 1})
    assert r.main(["--no-wait"], run=run) == 0 and run.ran[-1] == "publish_city_site.py"
    assert "monitor did not run" in capsys.readouterr().err
    assert json.loads(r.MONITOR_SUMMARY.read_text(encoding="utf-8"))["status"] == "failed", \
        "last week's summary is not shipped as this list's"


def test_every_run_prints_the_monitors_headline(capsys):
    r.MONITOR_SUMMARY.write_text(json.dumps({"status": "interim", "runs": 2, "next_window_date": "2026-12-28",
                                             "alerts": ["Band 1's rate is below its expectation."]}), encoding="utf-8")
    assert r.main(["--no-wait"], run=runner({})) == 0
    out = capsys.readouterr().out
    assert "monitor: interim, 2 archived list(s) scored; next window 2026-12-28" in out
    assert "monitor alert: Band 1's rate is below its expectation." in out


def test_a_push_render_did_not_serve_is_not_called_unchanged(capsys):
    run = runner({"publish_city_site.py": 5})
    assert r.main([], run=run) == 5
    err = capsys.readouterr().err
    assert "pushed the new list, but Render did not serve it" in err and "unchanged" not in err
    assert "Do not run the refresh again" in err


def test_repo_and_dir_pass_through_to_the_publish():
    run = runner({})
    assert r.main(["--skip-fetch", "--no-wait", "--repo", "city-org/staff-site", "--dir", "D:/staff-site"], run=run) == 0
    assert run.ran[-1] == "publish_city_site.py --repo city-org/staff-site --dir D:/staff-site"


def test_no_contact_no_pull_but_skip_fetch_needs_none(monkeypatch):
    monkeypatch.delenv("SDFOOD_CONTACT", raising=False)
    assert r.main([], run=runner({})) == 2
    run = runner({})
    assert r.main(["--skip-fetch", "--no-wait"], run=run) == 0 and run.ran[0].startswith("export_site.py")
    assert run.ran[-1] == "publish_city_site.py"


def test_a_recent_partial_resumes_and_a_stale_one_is_set_aside(tmp_path):
    r.PARTIAL.write_text("[]", encoding="utf-8")
    r.PARTIAL_META.write_text(json.dumps({"started": date.today().isoformat()}), encoding="utf-8")
    assert r.partial_state() == "resume"
    run = runner({})
    r.main(["--no-wait"], run=run)
    assert run.ran[0] == "fetch_sdfood.py --resume"
    r.PARTIAL_META.write_text(json.dumps({"started": "2026-01-01"}), encoding="utf-8")
    assert r.partial_state(date(2026, 1, 10)) == "stale"
    run = runner({})
    r.main(["--no-wait"], run=run)
    assert run.ran[0] == "fetch_sdfood.py", "a partial from weeks ago is never mixed into a new list"
    assert not r.PARTIAL.exists() and any(p.name.startswith("sd_businesses.partial.json.stale-") for p in tmp_path.iterdir())


GOOD = {"responsible_adult": {"name": "A", "email": "a@example.org"}, "corrections_contact": {"email": "c@example.org"},
        "sunset": "2027-06-30"}


def test_check_reports_what_a_refresh_needs_and_changes_nothing(monkeypatch):
    monkeypatch.undo()                                    # the real checks(), not the fixture's stand-in
    import publish_city_site as pcs
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    monkeypatch.setattr(pcs, "_json", lambda path, default: GOOD)
    monkeypatch.setattr(r, "refusal_on_record", lambda: None)
    monkeypatch.setattr(r, "partial_state", lambda today=None: "none")
    monkeypatch.setattr(r.shutil, "which", lambda name: f"/usr/bin/{name}")
    ok_sh = lambda cmd: SimpleNamespace(returncode=0, stdout="")
    live = lambda url: {"run": "forward_2026-09-29-x", "expires": "2026-10-12", "refit_needed": True, "monitor_alert": True}
    ok, lines = r.checks(url="https://x", today=date(2026, 9, 29), sh=ok_sh, fetch=live)
    text = "\n".join(lines)
    assert ok and "[ok] the frozen rule docs/rule.json is committed" in text and "[ok] gh is signed in" in text
    assert "expires 2026-10-12 (13 days left); the rule needs a refit; the monitor has an alert" in text
    assert "not yet done: no lawyer has reviewed naming these businesses" in text
    no_rule = lambda cmd: SimpleNamespace(returncode=128 if cmd[:2] == ["git", "show"] else 0,
                                          stdout=" M export_site.py" if cmd[:2] == ["git", "status"] else "")
    ok, lines = r.checks(url="https://x", today=date(2026, 9, 29), sh=no_rule, fetch=live)
    text = "\n".join(lines)
    assert not ok and "[NO] the code is committed" in text and "[NO] the frozen rule" in text
    down = lambda url: (_ for _ in ()).throw(OSError("asleep"))
    assert "not reachable" in "\n".join(r.checks(url="https://x", today=date(2026, 9, 29), sh=ok_sh, fetch=down)[1])
    ok, lines = r.checks(url="https://x", today=date(2026, 9, 29), sh=ok_sh, fetch=down, live=False)
    assert ok and not any("live" in line for line in lines), "before a pull the live site is not read"


def test_check_without_the_github_cli_or_git_says_so_and_does_not_crash(monkeypatch):
    monkeypatch.undo()
    import publish_city_site as pcs
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    monkeypatch.setattr(pcs, "_json", lambda path, default: GOOD)
    monkeypatch.setattr(r, "refusal_on_record", lambda: None)
    monkeypatch.setattr(r, "partial_state", lambda today=None: "none")
    monkeypatch.setattr(r.shutil, "which", lambda name: None if name == "gh" else f"/usr/bin/{name}")
    asked = []
    ok_sh = lambda cmd: asked.append(cmd) or SimpleNamespace(returncode=0, stdout="")
    ok, lines = r.checks(today=date(2026, 9, 29), sh=ok_sh, live=False)
    assert not ok and any(line.startswith("[NO] gh is installed") and "install the GitHub CLI" in line for line in lines)
    assert not any(cmd[0] == "gh" for cmd in asked), "gh auth status is not run without gh"

    def no_git(cmd):
        raise FileNotFoundError(2, "not found", cmd[0])
    ok, lines = r.checks(today=date(2026, 9, 29), sh=no_git, live=False)
    assert not ok and any("[NO] the code is committed" in line and "git is not installed" in line for line in lines)


def test_check_reports_a_refusal_on_record(monkeypatch, tmp_path):
    monkeypatch.undo()
    import publish_city_site as pcs
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    monkeypatch.setattr(pcs, "_json", lambda path, default: GOOD)
    monkeypatch.setattr(r, "REFUSED", tmp_path / "PULL_REFUSED.json")
    monkeypatch.setattr(r, "PARTIAL", tmp_path / "none.json")
    r.REFUSED.write_text(json.dumps({"status": 403}), encoding="utf-8")
    ok, lines = r.checks(today=date(2026, 9, 29), sh=lambda cmd: SimpleNamespace(returncode=0, stdout=""), live=False)
    assert not ok and any(line.startswith("[NO] no refusal of the pull is on record") for line in lines)
    ok, lines = r.checks(True, today=date(2026, 9, 29), sh=lambda cmd: SimpleNamespace(returncode=0, stdout=""), live=False)
    assert not any("refusal" in line for line in lines), "--skip-fetch pulls nothing"
