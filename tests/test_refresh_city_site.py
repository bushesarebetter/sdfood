"""refresh_city_site.py: the steps run in order, stop at the first failure, a refused pull is final,
a stale partial pull is set aside, and --check changes nothing."""
import json
from datetime import date
from types import SimpleNamespace

import refresh_city_site as r


def runner(codes):
    ran = []

    def run(cmd, cwd=None):
        name = " ".join(cmd[1:3]) if cmd[1:3] == ["export_site.py", "--monitor"] else cmd[1]
        ran.append(" ".join(cmd[1:]))
        return SimpleNamespace(returncode=codes.get(name, 0))
    run.ran = ran
    return run


def test_a_refresh_pulls_exports_monitors_writes_worklists_and_publishes_in_order(monkeypatch, tmp_path):
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    monkeypatch.setattr(r, "PARTIAL", tmp_path / "none.json")
    run = runner({})
    assert r.main([], run=run) == 0
    assert run.ran == ["fetch_sdfood.py", "export_site.py", "export_site.py --monitor", "export_worklist.py --no-backtest",
                       "publish_city_site.py --wait https://sdfood-city.onrender.com"]


def test_a_refused_pull_is_final_and_nothing_else_runs(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    monkeypatch.setattr(r, "PARTIAL", tmp_path / "none.json")
    run = runner({"fetch_sdfood.py": 3})
    assert r.main([], run=run) == 3 and len(run.ran) == 1
    assert "do not retry" in capsys.readouterr().err


def test_an_incomplete_listing_is_said_plainly(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    monkeypatch.setattr(r, "PARTIAL", tmp_path / "none.json")
    run = runner({"fetch_sdfood.py": 4})
    assert r.main([], run=run) == 4 and len(run.ran) == 1
    assert "ran out before every business appeared" in capsys.readouterr().err


def test_a_failed_export_stops_before_publishing(monkeypatch, tmp_path):
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    monkeypatch.setattr(r, "PARTIAL", tmp_path / "none.json")
    run = runner({"export_site.py": 1})
    assert r.main([], run=run) == 1 and run.ran == ["fetch_sdfood.py", "export_site.py"]


def test_the_monitor_never_blocks_a_refresh(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    monkeypatch.setattr(r, "PARTIAL", tmp_path / "none.json")
    run = runner({"export_site.py --monitor": 1})
    assert r.main(["--no-wait"], run=run) == 0 and run.ran[-1] == "publish_city_site.py"
    assert "monitor did not run" in capsys.readouterr().err


def test_no_contact_no_pull_but_skip_fetch_needs_none(monkeypatch):
    monkeypatch.delenv("SDFOOD_CONTACT", raising=False)
    assert r.main([], run=runner({})) == 2
    run = runner({})
    assert r.main(["--skip-fetch", "--no-wait"], run=run) == 0 and run.ran[0].startswith("export_site.py")
    assert run.ran[-1] == "publish_city_site.py"


def test_a_recent_partial_resumes_and_a_stale_one_is_set_aside(monkeypatch, tmp_path):
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    partial, meta = tmp_path / "sd_businesses.partial.json", tmp_path / "pull_meta.partial.json"
    monkeypatch.setattr(r, "PARTIAL", partial)
    monkeypatch.setattr(r, "PARTIAL_META", meta)
    partial.write_text("[]", encoding="utf-8")
    meta.write_text(json.dumps({"started": date.today().isoformat()}), encoding="utf-8")
    assert r.partial_state() == "resume"
    run = runner({})
    r.main(["--no-wait"], run=run)
    assert run.ran[0] == "fetch_sdfood.py --resume"
    meta.write_text(json.dumps({"started": "2026-01-01"}), encoding="utf-8")
    assert r.partial_state(date(2026, 1, 10)) == "stale"
    run = runner({})
    r.main(["--no-wait"], run=run)
    assert run.ran[0] == "fetch_sdfood.py", "a partial from weeks ago is never mixed into a new list"
    assert not partial.exists() and any(p.name.startswith("sd_businesses.partial.json.stale-") for p in tmp_path.iterdir())


def test_check_reports_what_a_refresh_needs_and_changes_nothing(monkeypatch, tmp_path):
    import publish_city_site as pcs
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    monkeypatch.setattr(r, "PARTIAL", tmp_path / "none.json")
    good = {"responsible_adult": {"name": "A", "email": "a@example.org"}, "corrections_contact": {"email": "c@example.org"},
            "sunset": "2027-06-30"}
    monkeypatch.setattr(pcs, "_json", lambda path, default: good)
    ok_sh = lambda cmd: SimpleNamespace(returncode=0, stdout="")
    live = lambda url: {"run": "forward_2026-09-29-x", "expires": "2026-10-12", "refit_needed": True}
    ok, lines = r.checks(url="https://x", today=date(2026, 9, 29), sh=ok_sh, fetch=live)
    text = "\n".join(lines)
    assert ok and "[ok] the frozen rule docs/rule.json is committed" in text
    assert "expires 2026-10-12 (13 days left); the rule needs a refit" in text
    assert "not yet done: no lawyer has reviewed naming these businesses" in text
    no_rule = lambda cmd: SimpleNamespace(returncode=128 if cmd[:2] == ["git", "show"] else 0,
                                          stdout=" M export_site.py" if cmd[:2] == ["git", "status"] else "")
    ok, lines = r.checks(url="https://x", today=date(2026, 9, 29), sh=no_rule, fetch=live)
    text = "\n".join(lines)
    assert not ok and "[NO] the code is committed" in text and "[NO] the frozen rule" in text
    down = lambda url: (_ for _ in ()).throw(OSError("asleep"))
    assert "not reachable" in "\n".join(r.checks(url="https://x", today=date(2026, 9, 29), sh=ok_sh, fetch=down)[1])
