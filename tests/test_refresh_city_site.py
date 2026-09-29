"""refresh_city_site.py: the steps run in order, stop at the first failure, and a refused pull is final."""
from types import SimpleNamespace

import refresh_city_site as r


def runner(codes):
    ran = []

    def run(cmd, cwd=None):
        name = cmd[1]
        ran.append(" ".join(cmd[1:]))
        return SimpleNamespace(returncode=codes.get(name, 0))
    run.ran = ran
    return run


def test_a_refresh_pulls_exports_writes_worklists_and_publishes_in_order(monkeypatch):
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    run = runner({})
    assert r.main([], run=run) == 0
    assert [c.split()[0] for c in run.ran] == ["fetch_sdfood.py", "export_site.py", "export_worklist.py", "publish_city_site.py"]
    assert run.ran[-1].endswith("--wait https://sdfood-city.onrender.com")


def test_a_refused_pull_is_final_and_nothing_else_runs(monkeypatch, capsys):
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    run = runner({"fetch_sdfood.py": 3})
    assert r.main([], run=run) == 3 and len(run.ran) == 1
    assert "do not retry" in capsys.readouterr().err


def test_a_failed_export_stops_before_publishing(monkeypatch):
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    run = runner({"export_site.py": 1})
    assert r.main([], run=run) == 1 and [c.split()[0] for c in run.ran] == ["fetch_sdfood.py", "export_site.py"]


def test_no_contact_no_pull_but_skip_fetch_needs_none(monkeypatch):
    monkeypatch.delenv("SDFOOD_CONTACT", raising=False)
    assert r.main([], run=runner({})) == 2
    run = runner({})
    assert r.main(["--skip-fetch", "--no-wait"], run=run) == 0 and run.ran[0].startswith("export_site.py")
    assert run.ran[-1] == "publish_city_site.py"
