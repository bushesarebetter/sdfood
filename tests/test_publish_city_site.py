"""publish_city_site.py: the repository whose privacy is checked is the one that is pushed to."""
import json
import subprocess

import pytest

import publish_city_site as pc


@pytest.mark.parametrize("url,repo", [
    ("https://github.com/ChenhaoZhang01/sdfood-city.git", "chenhaozhang01/sdfood-city"),
    ("https://github.com/ChenhaoZhang01/sdfood-city", "chenhaozhang01/sdfood-city"),
    ("https://token@github.com/o/r.git", "o/r"),
    ("git@github.com:o/r.git", "o/r"),
    ("ssh://git@github.com/o/r.git", "o/r"),
])
def test_github_repo_parses_common_remote_forms(url, repo):
    assert pc.github_repo(url) == repo


@pytest.mark.parametrize("url", ["https://gitlab.com/o/r.git", "https://github.com.evil.example/o/r.git",
                                 "https://github.com/o/r/extra", "", "/some/local/path"])
def test_non_github_or_odd_remotes_are_not_parsed(url):
    assert pc.github_repo(url) is None


def test_a_different_origin_is_refused_before_any_visibility_check():
    seen = []
    with pytest.raises(SystemExit, match="other than the one whose privacy was checked"):
        pc.check_target("https://github.com/someone/public-repo.git", "ChenhaoZhang01/sdfood-city",
                        lambda r: seen.append(r) or "PRIVATE")
    assert seen == []


def test_the_checked_repository_is_the_origin_and_must_be_private():
    seen = []
    assert pc.check_target("git@github.com:ChenhaoZhang01/sdfood-city.git", "ChenhaoZhang01/sdfood-city",
                           lambda r: seen.append(r) or "PRIVATE") == "chenhaozhang01/sdfood-city"
    assert seen == ["chenhaozhang01/sdfood-city"]
    with pytest.raises(SystemExit, match="PUBLIC"):
        pc.check_target("https://github.com/o/r.git", "o/r", lambda r: "PUBLIC")
    with pytest.raises(SystemExit, match="not a github.com repository"):
        pc.check_target("https://gitlab.com/o/r.git", "o/r", lambda r: "PRIVATE")


def test_the_staff_marker_matches_the_site_and_never_enters_this_repository():
    import re
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    js = (root / "food-dashboard" / "scripts" / "exportGate.mjs").read_text(encoding="utf-8")
    assert re.search(r'STAFF_MARKER = "([^"]+)"', js).group(1) == pc.STAFF_MARKER
    tracked = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True).stdout.split()
    assert not any(t.endswith(pc.STAFF_MARKER) for t in tracked)


def test_a_pushurl_that_differs_from_the_url_is_refused(tmp_path):
    import subprocess
    repo = tmp_path / "city"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/ChenhaoZhang01/sdfood-city.git"], cwd=repo, check=True)
    assert pc.push_urls(repo) == ["https://github.com/ChenhaoZhang01/sdfood-city.git"]
    subprocess.run(["git", "config", "remote.origin.pushurl", str(tmp_path / "elsewhere.git")], cwd=repo, check=True)
    with pytest.raises(SystemExit, match="not a github.com repository"):
        pc.check_target(pc.push_urls(repo), "ChenhaoZhang01/sdfood-city", lambda r: "PRIVATE")
    subprocess.run(["git", "config", "remote.origin.pushurl", "https://github.com/someone/public.git"], cwd=repo, check=True)
    subprocess.run(["git", "config", "--add", "remote.origin.pushurl", "https://github.com/ChenhaoZhang01/sdfood-city.git"],
                   cwd=repo, check=True)
    with pytest.raises(SystemExit, match="other than the one whose privacy was checked"):
        pc.check_target(pc.push_urls(repo), "ChenhaoZhang01/sdfood-city", lambda r: "PRIVATE")


# ── the staff release's gates ───────────────────────────────────────────────────────────────
from datetime import date

import publish_city_site as pcs

TODAY = date(2026, 9, 29)
GOOD = {"responsible_adult": {"name": "A. Adult", "relationship": "parent", "email": "adult@example.org"},
        "corrections_contact": {"name": "Corrections", "email": "fix@example.org"}, "sunset": "2027-06-30"}
REAL = {"sample": False, "source": {"name": "published results, collected 2026-09-28"}, "expires": "2026-10-10",
        "provenance": {"code_sha": "abc123"}, "inspections_through": "2026-09-26", "places": 10000}


def test_no_staff_release_without_a_responsible_adult_a_contact_and_a_sunset():
    assert pcs.approval_problems(GOOD, TODAY) == []
    assert "STAFF_APPROVAL.json" in pcs.approval_problems(None, TODAY)[0]
    for broken, why in [({**GOOD, "responsible_adult": {"name": "A"}}, "responsible_adult"),
                        ({**GOOD, "corrections_contact": {"email": "not an email"}}, "corrections_contact"),
                        ({**GOOD, "sunset": "2026-01-01"}, "has passed"), ({**GOOD, "sunset": ""}, "sunset needs"),
                        ({**GOOD, "sunset": "2028-01-01"}, "more than a year away")]:
        assert any(why in p for p in pcs.approval_problems(broken, TODAY)), why
    assert len(pcs.approval_warnings(GOOD)) == 2 and pcs.approval_warnings({**GOOD, "city_requestor": {"name": "x", "date": "2026-10-01"},
                                                                           "trust_determination": {"result": "does not apply"}}) == []


def test_the_export_must_be_complete_fresh_committed_and_not_quietly_smaller():
    assert pcs.export_problems(REAL, None, TODAY) == []
    cases = [({"source": {"name": "x; PARTIAL PULL"}}, "partial pull"), ({"expires": "2026-09-30"}, "expires"),
             ({"provenance": {"code_sha": "abc123-dirty"}}, "uncommitted"), ({"sample": True}, "sample")]
    for change, why in cases:
        assert any(why in p for p in pcs.export_problems({**REAL, **change}, None, TODAY)), why
    live = {"inspections_through": "2026-09-27", "places": 12000}
    got = pcs.export_problems(REAL, live, TODAY)
    assert any("before the live one" in p for p in got) and any("--force" in p for p in got)
    assert not any("--force" in p for p in pcs.export_problems(REAL, {**live, "inspections_through": "2026-09-01"}, TODAY, force=True))


def test_a_hold_takes_effect_at_publish_without_a_rebuild():
    fc = {"features": [{"properties": {"facility_id": "A", "band": "1", "points": 12}},
                       {"properties": {"facility_id": "B", "points": 3}}]}
    details = {"A": {"facility_id": "A", "band": "1", "points": 12, "score_card": [], "estimate": {}, "inspections": [1]}}
    changed = pcs.apply_holds(fc, details, {"A"})
    assert fc["features"][-1]["properties"] == {"facility_id": "A", "on_hold": True}, "and moved to the end"
    assert fc["features"][0]["properties"]["points"] == 3
    assert changed["A"] == {"facility_id": "A", "inspections": [1], "on_hold": True}


def test_the_staff_copy_of_meta_names_who_is_responsible_and_what_the_list_has_not_passed():
    m = pcs.staff_meta(REAL, GOOD, ["no approval"], "tester")
    assert m["audience"] == "staff" and m["contact"]["email"] == "fix@example.org"
    assert m["operator"]["name"] == "A. Adult" and m["review_status"] == ["no approval"] and m["sunset"] == "2027-06-30"


def test_staff_are_told_when_the_operator_is_a_student_author():
    assert pcs.independence_problems(GOOD) == []
    assert pcs.independence_problems({**GOOD, "responsible_adult": {"name": "X", "relationship": "author", "email": "x@example.org"}})
    assert pcs.independence_problems({**GOOD, "responsible_adult": {"name": "Chenhao Zhang", "relationship": "parent", "email": "c@example.org"}})


def test_what_has_not_been_done_is_said_in_plain_words():
    items = pcs.open_items(GOOD)
    assert [i.split(" (")[0] for i in items] == [
        "no City request for access is on record", "no TRUST Ordinance determination is on record",
        "no lawyer has reviewed naming these businesses", "the County has not commented on this list",
        "no business on the list has been told it is on it"]
    done = {**GOOD, "city_requestor": {"name": "R", "date": "2026-10-01"}, "trust_determination": {"result": "does not apply"},
            "legal_review": {"date": "2026-10-02"}, "county_informed": {"date": "2026-10-03"}, "owner_notice": {"date": "2026-10-04"}}
    assert pcs.open_items(done) == []
    assert pcs.access_approved(done) and not pcs.access_approved(GOOD)
    assert not pcs.access_approved({**GOOD, "city_requestor": {"name": "R", "date": "2026-10-01"}}), "the TRUST answer too"
    assert not pcs.access_approved({**done, "city_requestor": {"name": "R"}}), "a request needs its date"
    applies = {**done, "trust_determination": {"result": "applies"}}
    assert not pcs.access_approved(applies), "if TRUST applies, the Council approves first"
    assert "the Council has not approved this use" in pcs.open_items(applies)[0]
    assert pcs.access_approved({**applies, "council_approval": {"date": "2027-01-10"}})
    assert not pcs.access_approved({**done, "trust_determination": {"result": "pending"}}), "only a real answer counts"
    m = pcs.staff_meta(REAL, done, [], "tester")
    assert m["access_approved"] is True and pcs.staff_meta(REAL, GOOD, [], "t")["access_approved"] is False


def test_drift_is_shown_to_staff():
    assert pcs.drift_items({}) == [] and pcs.drift_items({"drift": {"refit_needed": False}}) == []
    got = pcs.drift_items({"drift": {"refit_needed": True, "reasons": ["routine major rate 30.0% against 21.0%"]}})
    assert got and got[0].startswith("the County's record has moved since the rule was frozen: routine major rate")


def test_a_bands_list_applies_the_committed_frozen_rule():
    bands = {"mode": "bands", "frozen": {"version": "2026-09-29-abcd1234"}}
    committed = lambda v: (lambda path: None if v is None else json.dumps({"version": v}))
    assert pcs.frozen_problems({"mode": "record"}, show=committed(None)) == []
    assert "no frozen rule" in pcs.frozen_problems({"mode": "bands"}, show=committed("x"))[0]
    assert "not committed" in pcs.frozen_problems(bands, show=committed(None))[0]
    assert "committed docs/rule.json is 2026-01-01-00000000" in pcs.frozen_problems(bands, show=committed("2026-01-01-00000000"))[0]
    assert pcs.frozen_problems(bands, show=committed("2026-09-29-abcd1234")) == []


def _git(*a, cwd):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)


def test_holds_only_changes_nothing_but_the_held_places(tmp_path, monkeypatch):
    out = tmp_path / "city"
    data = out / "public" / "data"
    (data / "place").mkdir(parents=True)
    fc = {"type": "FeatureCollection", "features": [{"properties": {"facility_id": "A", "band": "1", "points": 12}},
                                                    {"properties": {"facility_id": "B", "band": "1", "points": 9}}]}
    (data / "facilities.geojson").write_text(json.dumps(fc), encoding="utf-8")
    for fid in "AB":
        (data / "place" / f"{fid}.json").write_text(json.dumps({"facility_id": fid, "band": "1", "points": 9, "inspections": []}))
    (data / "meta.json").write_text(json.dumps({"run": "forward_2026-09-29-x", "expires": "2026-09-30"}), encoding="utf-8")
    _git("init", "-q", "-b", "main", cwd=out)
    holds = tmp_path / "holds.json"
    holds.write_text(json.dumps({"facility_ids": ["A"]}), encoding="utf-8")
    monkeypatch.setattr(pcs, "HOLDS", holds)
    monkeypatch.setattr(pcs, "check_target", lambda *a, **k: "o/r")
    pushed = []
    monkeypatch.setattr(pcs, "commit_and_push", lambda o, msg: pushed.append(msg) or "f" * 40)
    commit, meta, held = pcs.holds_only(out, GOOD, TODAY, "o/r")
    assert held == {"A"} and pushed and "holds only (1 held)" in pushed[0]
    shipped = json.loads((data / "facilities.geojson").read_text(encoding="utf-8"))["features"]
    assert shipped[-1]["properties"] == {"facility_id": "A", "on_hold": True} and shipped[0]["properties"]["band"] == "1"
    assert json.loads((data / "place" / "A.json").read_text())["on_hold"] is True
    assert "band" in json.loads((data / "place" / "B.json").read_text())
    log = [json.loads(line) for line in (out / "DEPLOYS.jsonl").read_text(encoding="utf-8").splitlines()]
    assert log[-1]["holds_only"] is True and log[-1]["held"] == ["A"]
    # an export 1 day from expiry could not be published; a hold still goes out
    with pytest.raises(SystemExit, match="sunset"):
        pcs.holds_only(out, {**GOOD, "sunset": "2026-01-01"}, TODAY, "o/r")


def test_ops_holds_what_it_takes_to_rebuild_the_site(tmp_path, monkeypatch):
    out = tmp_path / "city"
    out.mkdir()
    for name in ("rule.json", "pull_meta.json", "STAFF_APPROVAL.json", "holds.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pcs, "FROZEN", tmp_path / "rule.json")
    monkeypatch.setattr(pcs, "PULL_META", tmp_path / "pull_meta.json")
    monkeypatch.setattr(pcs, "APPROVAL", tmp_path / "STAFF_APPROVAL.json")
    monkeypatch.setattr(pcs, "HOLDS", tmp_path / "holds.json")
    pcs.write_ops(out)
    got = sorted(p.name for p in (out / "ops").iterdir())
    assert got == ["README.md", "STAFF_APPROVAL.json", "holds.json", "pull_meta.json", "rule.json", "source.tar.gz"]
    import tarfile
    with tarfile.open(out / "ops" / "source.tar.gz") as t:
        names = t.getnames()
    assert "export_site.py" in names and "publish_city_site.py" in names


def test_a_missing_checkout_is_cloned_not_started_afresh(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pcs.subprocess, "run", lambda cmd, **k: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(pcs, "run", lambda cmd, cwd: calls.append(cmd) or "")
    pcs.ensure_checkout(tmp_path / "city", "o/r")
    assert ["git", "clone", "-q", "https://github.com/o/r.git", str(tmp_path / "city")] in calls
    assert not any(c[:2] == ["git", "init"] for c in calls), "the deploy history is kept"

