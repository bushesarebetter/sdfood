"""publish_city_site.py: the repository whose privacy is checked is the one that is pushed to; the staff
release's gates (a dated, attributed City request and TRUST answer), holds read strictly and checked,
ops/ with every archived list, a site copied from HEAD, and a record naming both commits."""
import json
import re
import shutil
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
ASKED = {"city_requestor": {"name": "R", "date": "2026-09-01"},
         "trust_determination": {"result": "does not apply", "by": "City Attorney's office", "date": "2026-09-15"}}


def test_no_staff_release_without_a_responsible_adult_a_contact_and_a_sunset():
    assert pcs.approval_problems(GOOD, TODAY) == []
    assert "STAFF_APPROVAL.json" in pcs.approval_problems(None, TODAY)[0]
    for broken, why in [({**GOOD, "responsible_adult": {"name": "A"}}, "responsible_adult"),
                        ({**GOOD, "corrections_contact": {"email": "not an email"}}, "corrections_contact"),
                        ({**GOOD, "sunset": "2026-01-01"}, "has passed"), ({**GOOD, "sunset": ""}, "sunset needs"),
                        ({**GOOD, "sunset": "2028-01-01"}, "more than a year away")]:
        assert any(why in p for p in pcs.approval_problems(broken, TODAY)), why
    assert len(pcs.approval_warnings(GOOD, TODAY)) == 2 and pcs.approval_warnings({**GOOD, **ASKED}, TODAY) == []


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
                       {"properties": {"facility_id": "B", "points": 3}},
                       {"properties": {"facility_id": "C"}}]}
    details = {"A": {"facility_id": "A", "band": "1", "points": 12, "score_card": [], "estimate": {}, "inspections": [1]},
               "C": {"facility_id": "C", "inspections": []}}
    changed = pcs.apply_holds(fc, details, {"A", "C"})
    assert [f["properties"] for f in fc["features"][-2:]] == [{"facility_id": "A", "on_hold": True},
                                                             {"facility_id": "C", "on_hold": True}], "and moved to the end"
    assert fc["features"][0]["properties"]["points"] == 3
    assert changed["A"] == {"facility_id": "A", "inspections": [1], "on_hold": True}
    assert pcs.hold_problems(fc, changed, {"A", "C"}) == [], "a held place without points is marked on hold too"
    assert pcs.hold_problems(fc, {"A": changed["A"]}, {"A", "C"}) == ["C: it has no place file"]
    unapplied = {"features": [{"properties": {"facility_id": "A", "band": "1", "points": 12}}]}
    assert pcs.hold_problems(unapplied, details, {"A"}) == ["A: the list still carries its points or band",
                                                            "A: its place file still carries its points or band"]


def test_the_holds_file_is_read_strictly(tmp_path):
    f = tmp_path / "holds.json"
    assert pcs.read_holds(f) == (set(), None), "no file: nothing on hold"
    f.write_text(json.dumps({"facility_ids": [" DEH2022-FFPP-000001 ", "DEH2022-FFPP-000002"]}), encoding="utf-8")
    assert pcs.load_holds_strict(f) == {"DEH2022-FFPP-000001", "DEH2022-FFPP-000002"}
    for text in ('{"facility_ids": ["DEH2022-FFPP-000001",]}', '{"facility_ids": "DEH2022-FFPP-000001"}',
                 '{"facility_ids": [1]}', '{"facility_ids": [""]}', '["DEH2022-FFPP-000001"]', '{}'):
        f.write_text(text, encoding="utf-8")
        held, problem = pcs.read_holds(f)
        assert held == set() and problem and "facility_ids" in problem, text
        with pytest.raises(SystemExit, match="would release every hold"):
            pcs.load_holds_strict(f)
    assert pcs.hold_matches({"deh2022-ffpp-000001", "GONE"}, {"DEH2022-FFPP-000001"}) == (
        ["GONE", "deh2022-ffpp-000001"], {"deh2022-ffpp-000001": "DEH2022-FFPP-000001"})
    # the example the docs point to is in the format every loader reads
    assert pcs.read_holds(pcs.ROOT / "docs" / "holds.example.json") == ({"DEH2022-FFPP-000001"}, None)


def test_the_staff_copy_of_meta_names_who_is_responsible_and_what_the_list_has_not_passed():
    m = pcs.staff_meta(REAL, GOOD, ["no approval"], "tester", TODAY)
    assert m["audience"] == "staff" and m["contact"]["email"] == "fix@example.org"
    assert m["operator"]["name"] == "A. Adult" and m["review_status"] == ["no approval"] and m["sunset"] == "2027-06-30"
    assert "monitor" not in m
    summary = {"status": "interim", "runs": 2, "alerts": [], "next_window_date": "2026-12-28"}
    assert pcs.staff_meta(REAL, GOOD, [], "tester", TODAY, summary)["monitor"] == summary


def test_the_monitor_summary_ships_as_meta_monitor_and_a_missing_one_says_so(tmp_path):
    got = pcs.monitor_summary(tmp_path)
    assert got["status"] == "failed" and got["alerts"] == ["The monitor has not run for this list."]
    summary = {"status": "complete", "runs": 3, "alerts": ["a sentence"], "next_window_date": None}
    (tmp_path / "monitor_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    assert pcs.monitor_summary(tmp_path) == summary
    for bad in ('{"status": "fine", "runs": 1, "alerts": []}', "{not json", "[]", '{"status": "interim", "runs": -1, "alerts": []}',
                '{"status": "interim", "runs": 1, "alerts": [""]}', '{"status": "interim", "runs": 1, "alerts": "x"}',
                '{"status": "interim", "runs": 1, "alerts": [], "next_window_date": "soon"}'):
        (tmp_path / "monitor_summary.json").write_text(bad, encoding="utf-8")
        assert pcs.monitor_summary(tmp_path)["alerts"] == ["The monitor wrote a summary that cannot be read."], bad


def test_every_summary_the_monitor_or_the_refresh_writes_ships_unchanged(tmp_path, monkeypatch):
    """The hand-off: export_site.monitor_summary (every status it gives), export_site.main's summary when
    --monitor errors, and refresh_city_site.monitor_failed are each shipped as they are, never read as a
    summary that cannot be read."""
    import export_site as es
    import refresh_city_site as rcs
    runs = [
        [],
        [{"run": "forward_2026-09-29-aaaaaaaa", "complete": False, "window_days": None}],
        [{"run": "forward_2026-06-01-bbbbbbbb", "complete": False, "window_days": 90,
          "city": {"bands": {"1": {"labelled": 200, "positives": 40, "rate": 0.2, "interval": [0.15, 0.25], "expected": 0.31}}}}],
        [{"run": "forward_2025-06-01-dddddddd", "complete": True, "window_days": 365,
          "city": {"bands": {}, "observed_over_expected": {"observed": 80, "expected": 100.0, "ratio": 0.8},
                   "band_1_minus_persistence": [-9.0, -1.0]}}],
    ]
    shipped = []
    for r in runs:
        es.write_monitor_summary(tmp_path, es.monitor_summary(r))
        want = json.loads((tmp_path / "monitor_summary.json").read_text(encoding="utf-8"))
        assert pcs.monitor_summary(tmp_path) == want
        shipped.append(want["status"])
    assert shipped == ["too early", "too early", "interim", "complete"]
    (tmp_path / "monitor_summary.json").write_text(json.dumps({"status": "failed", "runs": 0, "next_window_date": None,
                                                               "alerts": ["The monitor did not run (ValueError)."]}), encoding="utf-8")
    assert pcs.monitor_summary(tmp_path)["alerts"] == ["The monitor did not run (ValueError)."], "export_site.main's"
    rcs.monitor_failed(tmp_path / "monitor_summary.json")
    assert pcs.monitor_summary(tmp_path) == {"status": "failed", "runs": 0, "alerts": ["The monitor did not run for this list."],
                                            "next_window_date": None}, "refresh_city_site's"


def test_a_monitor_summary_for_another_record_or_rule_ships_as_failed(tmp_path):
    """`python export_site.py && python publish_city_site.py` leaves the previous run's summary on disk: the
    publish matches its stamps to the export it ships, and never passes an earlier run's off as current."""
    import export_site as es
    meta = {"inspections_through": "2026-09-27", "frozen": {"version": "2026-09-01-5f50107e"}}
    es.write_monitor_summary(tmp_path, es.monitor_summary([], version="2026-09-01-5f50107e", through="2026-09-27"))
    fresh = json.loads((tmp_path / "monitor_summary.json").read_text(encoding="utf-8"))
    assert pcs.monitor_summary(tmp_path, meta=meta) == fresh, "stamped for this export: shipped as it is"
    assert pcs.monitor_summary(tmp_path) == fresh, "no export to match: shipped as it is"
    for summary, why in [({**fresh, "inspections_through": "2026-09-20"}, "scored the record through 2026-09-20, and this list is the record through 2026-09-27"),
                         ({**fresh, "rule_version": "2026-06-01-aaaaaaaa"}, "read alerts for rule version 2026-06-01-aaaaaaaa"),
                         ({**fresh, "rule_version": None}, "read alerts for rule version none"),
                         ({k: v for k, v in fresh.items() if k not in ("inspections_through", "rule_version")},
                          "does not say which record it scored")]:
        (tmp_path / "monitor_summary.json").write_text(json.dumps(summary), encoding="utf-8")
        got = pcs.monitor_summary(tmp_path, meta=meta)
        assert got["status"] == "failed" and got["runs"] == 0 and got["next_window_date"] is None, summary
        assert got["alerts"][0].startswith("The monitor did not run for this list: its summary ") and why in got["alerts"][0], got
        assert "--monitor" in got["alerts"][0] and "\u2014" not in got["alerts"][0]
    failed = {"status": "failed", "runs": 0, "alerts": ["The monitor did not run (ValueError)."], "next_window_date": None}
    (tmp_path / "monitor_summary.json").write_text(json.dumps(failed), encoding="utf-8")
    assert pcs.monitor_summary(tmp_path, meta=meta) == failed, "a failed run's own sentence is kept"
    src = (pcs.ROOT / "publish_city_site.py").read_text(encoding="utf-8")
    assert "monitor_summary(meta=meta)" in src, "the publish matches the summary to the export it ships"


def test_staff_are_told_when_the_operator_is_a_student_author():
    assert pcs.independence_problems(GOOD) == []
    assert pcs.independence_problems({**GOOD, "responsible_adult": {"name": "X", "relationship": "author", "email": "x@example.org"}})
    assert pcs.independence_problems({**GOOD, "responsible_adult": {"name": "Chenhao Zhang", "relationship": "parent", "email": "c@example.org"}})


def test_what_has_not_been_done_is_said_in_plain_words():
    items = pcs.open_items(GOOD, TODAY)
    assert [i.split(" (")[0] for i in items] == [
        "no City request for access is on record", "no TRUST Ordinance determination is on record",
        "no lawyer has reviewed naming these businesses", "the County has not commented on this list",
        "no business on the list has been told it is on it"]
    done = {**GOOD, **ASKED, "legal_review": {"date": "2026-09-02"}, "county_informed": {"date": "2026-09-03"},
            "owner_notice": {"date": "2026-09-04"}}
    assert pcs.open_items(done, TODAY) == []
    assert pcs.access_approved(done, TODAY) and not pcs.access_approved(GOOD, TODAY)
    assert pcs.access_approved(done, TODAY) is True and pcs.access_approved(GOOD, TODAY) is False
    assert not pcs.access_approved({**GOOD, "city_requestor": ASKED["city_requestor"]}, TODAY), "the TRUST answer too"
    assert not pcs.access_approved({**done, "city_requestor": {"name": "R"}}, TODAY), "a request needs its date"
    applies = {**done, "trust_determination": {**ASKED["trust_determination"], "result": "applies"}}
    assert not pcs.access_approved(applies, TODAY), "if TRUST applies, the Council approves first"
    assert "the Council has not approved this use" in pcs.open_items(applies, TODAY)[0]
    assert pcs.access_approved({**applies, "council_approval": {"date": "2026-09-20", "resolution": "R-2026-001"}}, TODAY)
    assert not pcs.access_approved({**done, "trust_determination": {**ASKED["trust_determination"], "result": "pending"}}, TODAY), \
        "only a real answer counts"
    m = pcs.staff_meta(REAL, done, [], "tester", TODAY)
    assert m["access_approved"] is True and pcs.staff_meta(REAL, GOOD, [], "t", TODAY)["access_approved"] is False


@pytest.mark.parametrize("change, why", [
    ({"city_requestor": {"name": "x", "date": "soon"}}, "city_requestor.date 'soon' is not a date"),
    ({"city_requestor": {"name": "x", "date": "2099-01-01"}}, "city_requestor.date 2099-01-01 is after today"),
    ({"city_requestor": {"name": "x", "date": "2026-02-30"}}, "is not a date"),
    ({"city_requestor": {"name": "", "date": "2026-09-01"}}, "city_requestor.name is empty"),
    ({"trust_determination": {"result": "Does Not Apply"}}, "trust_determination.by is empty"),
    ({"trust_determination": {"result": "does not apply", "by": "x", "date": "tbd"}}, "trust_determination.date 'tbd'"),
    ({"trust_determination": {"result": "maybe", "by": "x", "date": "2026-09-01"}}, "result 'maybe' is not one of"),
])
def test_an_entry_that_is_undated_unattributed_or_still_to_come_is_not_approval(change, why):
    a = {**GOOD, **ASKED, **change}
    assert pcs.access_approved(a, TODAY) is False
    assert any(why in w for w in pcs.approval_warnings(a, TODAY)), pcs.approval_warnings(a, TODAY)
    assert any("filled in but not counted" in w for w in pcs.entry_problems(a, TODAY))
    assert not any("filled in" in i for i in pcs.open_items(a, TODAY)), "staff read plain words, not the operator's fix"


def test_a_scheduled_council_vote_is_not_an_approval():
    applies = {**GOOD, **ASKED, "trust_determination": {**ASKED["trust_determination"], "result": "applies"}}
    for council, why in [({"date": "2027-01-10", "resolution": "R-1"}, "after today"),
                         ({"date": "tbd", "resolution": "R-1"}, "'tbd' is not a date"),
                         ({"date": "2026-09-20"}, "council_approval.resolution is empty")]:
        a = {**applies, "council_approval": council}
        assert not pcs.access_approved(a, TODAY), council
        assert any(why in w for w in pcs.approval_warnings(a, TODAY)), (council, pcs.approval_warnings(a, TODAY))
    assert pcs.access_approved({**applies, "council_approval": {"date": "2026-09-29", "resolution": "R-1"}}, TODAY), \
        "the day itself counts"


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


def _live(tmp_path, monkeypatch, held_ids, applied=None, asked=None):
    """A private checkout with a live list of A and B (both band 1), docs/holds.json holding `held_ids`,
    ops/holds_applied.json (every id a publish has held on its list) holding `applied`, and ops/holds.json
    (what the last publish was asked to hold) holding `asked`."""
    out = tmp_path / "city"
    data = out / "public" / "data"
    (data / "place").mkdir(parents=True)
    fc = {"type": "FeatureCollection", "features": [{"properties": {"facility_id": "DEH-A", "band": "1", "points": 12}},
                                                    {"properties": {"facility_id": "DEH-B", "band": "1", "points": 9}}]}
    (data / "facilities.geojson").write_text(json.dumps(fc), encoding="utf-8")
    for fid in ("DEH-A", "DEH-B"):
        (data / "place" / f"{fid}.json").write_text(json.dumps({"facility_id": fid, "band": "1", "points": 9, "inspections": []}))
    (data / "meta.json").write_text(json.dumps({"run": "forward_2026-09-29-x", "expires": "2026-09-30"}), encoding="utf-8")
    for name, ids in ((pcs.APPLIED, applied), ("holds.json", asked)):
        if ids is not None:
            (out / "ops").mkdir(exist_ok=True)
            (out / "ops" / name).write_text(json.dumps({"facility_ids": ids}), encoding="utf-8")
    _git("init", "-q", "-b", "main", cwd=out)
    holds = tmp_path / "holds.json"
    holds.write_text(held_ids if isinstance(held_ids, str) else json.dumps({"facility_ids": held_ids}), encoding="utf-8")
    monkeypatch.setattr(pcs, "HOLDS", holds)
    monkeypatch.setattr(pcs, "check_target", lambda *a, **k: "o/r")
    pushed = []
    monkeypatch.setattr(pcs, "commit_and_push", lambda o, msg: pushed.append(msg) or "f" * 40)
    return out, data, pushed


def test_holds_only_changes_nothing_but_the_held_places(tmp_path, monkeypatch, capsys):
    out, data, pushed = _live(tmp_path, monkeypatch, ["DEH-A"])
    commit, meta, held, newly, on_list = pcs.holds_only(out, GOOD, TODAY, "o/r")
    assert held == {"DEH-A"} and newly == on_list == ["DEH-A"] and pushed
    assert "holds only (1 of 1 held ids on the list, 1 newly held)" in pushed[0]
    assert "held now: DEH-A" in capsys.readouterr().out
    shipped = json.loads((data / "facilities.geojson").read_text(encoding="utf-8"))["features"]
    assert shipped[-1]["properties"] == {"facility_id": "DEH-A", "on_hold": True} and shipped[0]["properties"]["band"] == "1"
    assert json.loads((data / "place" / "DEH-A.json").read_text())["on_hold"] is True
    assert "band" in json.loads((data / "place" / "DEH-B.json").read_text())
    log = [json.loads(line) for line in (out / "DEPLOYS.jsonl").read_text(encoding="utf-8").splitlines()]
    assert log[-1]["holds_only"] is True and log[-1]["held"] == ["DEH-A"] and log[-1]["newly_held"] == ["DEH-A"]
    assert log[-1]["held_on_list"] == ["DEH-A"] and pcs.applied_holds(out) == {"DEH-A"}, "what took effect is recorded"
    # an export 1 day from expiry could not be published; a hold still goes out
    with pytest.raises(SystemExit, match="sunset"):
        pcs.holds_only(out, {**GOOD, "sunset": "2026-01-01"}, TODAY, "o/r")


def test_holds_only_with_nothing_new_records_and_pushes_nothing(tmp_path, monkeypatch):
    out, data, pushed = _live(tmp_path, monkeypatch, ["DEH-A"])
    pcs.holds_only(out, GOOD, TODAY, "o/r")
    _git("add", "-A", cwd=out)
    _git("-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-q", "-m", "x", cwd=out)
    pushed.clear()
    commit, _, _, newly, _ = pcs.holds_only(out, GOOD, TODAY, "o/r")
    assert commit is None and newly == [] and pushed == []
    assert len((out / "DEPLOYS.jsonl").read_text(encoding="utf-8").splitlines()) == 1


@pytest.mark.parametrize("held, match", [
    (["deh-a"], "did you mean DEH-A"),                                   # the wrong case
    (["DEH-Z"], "DEH-Z is not on the live list"),                         # a typo
    ('{"facility_ids": "DEH-A"}', "not in the holds format"),             # a string, not a list
    ('{"facility_ids": ["DEH-A"],}', "cannot be read"),                   # not JSON
])
def test_holds_only_refuses_a_hold_that_would_not_apply_before_changing_anything(tmp_path, monkeypatch, held, match):
    out, data, pushed = _live(tmp_path, monkeypatch, held)
    before = {p.name: p.read_bytes() for p in (data / "place").iterdir()} | {"fc": (data / "facilities.geojson").read_bytes()}
    with pytest.raises(SystemExit, match=match):
        pcs.holds_only(out, GOOD, TODAY, "o/r")
    after = {p.name: p.read_bytes() for p in (data / "place").iterdir()} | {"fc": (data / "facilities.geojson").read_bytes()}
    assert after == before and pushed == [] and not (out / "DEPLOYS.jsonl").exists()


def test_holds_only_lets_an_old_hold_off_the_list_pass_with_a_warning(tmp_path, monkeypatch, capsys):
    out, data, pushed = _live(tmp_path, monkeypatch, ["DEH-GONE", "DEH-B"], applied=["DEH-GONE"])
    commit, _, held, newly, on_list = pcs.holds_only(out, GOOD, TODAY, "o/r")
    assert commit and newly == on_list == ["DEH-B"]
    assert "DEH-GONE is held and no longer on the list (a publish held it before" in capsys.readouterr().out
    assert "holds only (1 of 2 held ids on the list, 1 newly held)" in pushed[0]
    assert pcs.applied_holds(out) == {"DEH-GONE", "DEH-B"}, "the record only grows"


def test_holds_only_refuses_an_id_no_publish_applied_even_one_asked_for_before(tmp_path, monkeypatch):
    """ops/holds.json is what was asked for: a typo in it never became a hold, so it never passes as an old one."""
    out, data, pushed = _live(tmp_path, monkeypatch, ["DEH-TYPO", "DEH-B"], applied=["DEH-A"], asked=["DEH-TYPO"])
    before = (data / "facilities.geojson").read_bytes()
    with pytest.raises(SystemExit, match="DEH-TYPO is not on the live list, and no publish has held it"):
        pcs.holds_only(out, GOOD, TODAY, "o/r")
    assert (data / "facilities.geojson").read_bytes() == before and pushed == []
    # with no record at all (an unreadable one included), nothing off the list passes as an earlier hold
    (out / "ops" / pcs.APPLIED).write_text("{not json", encoding="utf-8")
    assert pcs.applied_holds(out) == set()
    with pytest.raises(SystemExit, match="NOT APPLIED"):
        pcs.holds_only(out, GOOD, TODAY, "o/r")


def test_holds_only_refuses_a_held_place_without_its_place_file(tmp_path, monkeypatch):
    out, data, pushed = _live(tmp_path, monkeypatch, ["DEH-B"])
    (data / "place" / "DEH-B.json").unlink()
    with pytest.raises(SystemExit, match="DEH-B: it has no place file"):
        pcs.holds_only(out, GOOD, TODAY, "o/r")
    assert pushed == []


def _ops_env(tmp_path, monkeypatch, runs=("forward_2026-09-29-aaaa",), register=None):
    site = tmp_path / "site"
    for run_name in runs:
        d = site / "archive" / run_name
        d.mkdir(parents=True)
        (d / "ranking.csv.gz").write_bytes(run_name.encode())
        (d / "meta.json").write_text("{}", encoding="utf-8")
        (d / "manifest.json").write_text("{}", encoding="utf-8")
    for name in ("monitor.json", "monitor_summary.json"):
        (site / name).write_text("{}", encoding="utf-8")
    import hashlib
    reg = tmp_path / "REGISTERED.json"
    regs = [{"run": r, "ranking_sha256": hashlib.sha256(r.encode()).hexdigest()} for r in (register or [])]
    reg.write_text(json.dumps({"registrations": regs}), encoding="utf-8")
    monkeypatch.setattr(pcs, "SITE", site)
    monkeypatch.setattr(pcs, "REGISTERED", reg)
    for name in ("rule.json", "pull_meta.json", "STAFF_APPROVAL.json", "holds.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pcs, "FROZEN", tmp_path / "rule.json")
    monkeypatch.setattr(pcs, "PULL_META", tmp_path / "pull_meta.json")
    monkeypatch.setattr(pcs, "APPROVAL", tmp_path / "STAFF_APPROVAL.json")
    monkeypatch.setattr(pcs, "HOLDS", tmp_path / "holds.json")
    out = tmp_path / "city"
    out.mkdir()
    return site, out


def test_ops_holds_what_it_takes_to_rebuild_the_site(tmp_path, monkeypatch):
    site, out = _ops_env(tmp_path, monkeypatch, runs=("forward_2026-09-20", "forward_2026-09-29-aaaa"),
                         register=["forward_2026-09-29-aaaa"])
    pcs.write_ops(out)
    got = sorted(p.name for p in (out / "ops").iterdir())
    assert got == ["README.md", "STAFF_APPROVAL.json", "archive", "holds.json", "monitor.json", "monitor_summary.json",
                   "pull_meta.json", "rule.json", "source.tar.gz"]
    assert sorted(p.name for p in (out / "ops" / "archive").iterdir()) == ["forward_2026-09-20", "forward_2026-09-29-aaaa"], \
        "every archived list, not only the registered one: the monitor scores them all"
    assert (out / "ops" / "archive" / "forward_2026-09-29-aaaa" / "ranking.csv.gz").read_bytes() == b"forward_2026-09-29-aaaa"
    import tarfile
    with tarfile.open(out / "ops" / "source.tar.gz") as t:
        names = t.getnames()
    assert "export_site.py" in names and "publish_city_site.py" in names
    # write-once: a run already in ops/ is never overwritten, and it survives a later publish
    (site / "archive" / "forward_2026-09-20" / "ranking.csv.gz").write_bytes(b"changed")
    pcs.write_ops(out)
    assert (out / "ops" / "archive" / "forward_2026-09-20" / "ranking.csv.gz").read_bytes() == b"forward_2026-09-20"
    assert "ops" in pcs.KEEP, "a full publish keeps ops/ (and its archive) in the checkout"


def test_ops_keeps_the_source_of_the_list_when_another_commit_built_it(tmp_path, monkeypatch):
    site, out = _ops_env(tmp_path, monkeypatch)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=pcs.ROOT, capture_output=True, text=True).stdout.strip()
    parent = subprocess.run(["git", "rev-parse", "HEAD~1"], cwd=pcs.ROOT, capture_output=True, text=True).stdout.strip()
    pcs.write_ops(out, head, parent)
    assert (out / "ops" / "export_source.tar.gz").exists()
    pcs.write_ops(out, head, head)
    assert not (out / "ops" / "export_source.tar.gz").exists(), "one commit: one archive"
    pcs.write_ops(out, head, "0" * 40)
    assert not (out / "ops" / "export_source.tar.gz").exists(), "an unknown commit is a warning, not a crash"


@pytest.mark.parametrize("tamper, match", [("missing", "is missing"), ("changed", "hash differs")])
def test_a_registered_run_without_its_archive_stops_the_publish(tmp_path, monkeypatch, tamper, match):
    site, out = _ops_env(tmp_path, monkeypatch, register=["forward_2026-09-29-aaaa"])
    ranking = site / "archive" / "forward_2026-09-29-aaaa" / "ranking.csv.gz"
    if tamper == "missing":
        ranking.unlink()
    else:
        ranking.write_bytes(b"not the registered file")
    assert match in pcs.archive_problems([site / "archive"])[0]
    with pytest.raises(SystemExit, match=match):
        pcs.write_ops(out)
    # a copy already in the private repository's ops/archive/ is enough (a new machine, before the restore)
    good = out / "ops" / "archive" / "forward_2026-09-29-aaaa"
    shutil.rmtree(good, ignore_errors=True)
    good.mkdir(parents=True)
    (good / "ranking.csv.gz").write_bytes(b"forward_2026-09-29-aaaa")
    (good / "manifest.json").write_text("{}", encoding="utf-8")
    assert pcs.archive_problems([site / "archive", out / "ops" / "archive"]) == []
    pcs.write_ops(out)


def test_the_site_is_copied_from_head_not_from_disk():
    files = pcs.site_code("HEAD")
    head = subprocess.run(["git", "show", "HEAD:city_site/server.mjs"], cwd=pcs.ROOT, capture_output=True).stdout
    assert files["city_site/server.mjs"] == head
    assert "food-dashboard/package.json" in files and "city_site/watch.yml" in files


def test_write_site_code_leaves_out_the_sample_data(tmp_path):
    files = {"food-dashboard/package.json": b"{}", "food-dashboard/src/App.jsx": b"x", "food-dashboard/public/data/meta.json": b"s",
             "food-dashboard/public/robots.txt": b"r", "city_site/server.mjs": b"srv", "city_site/render.yaml": b"r",
             "city_site/watch.yml": b"w"}
    pcs.write_site_code(tmp_path, files)
    assert (tmp_path / "src" / "App.jsx").read_bytes() == b"x" and (tmp_path / "public" / "robots.txt").exists()
    assert not (tmp_path / "public" / "data").exists()
    assert (tmp_path / "server.mjs").read_bytes() == b"srv" and (tmp_path / ".github" / "workflows" / "watch.yml").exists()


def _full_publish_env(tmp_path, monkeypatch, dirty=False):
    """main() on a small export, every git and network step stood in for."""
    site = tmp_path / "site"
    (site / "place").mkdir(parents=True)
    meta = {**REAL, "run": "forward_2026-09-29-x", "mode": "record", "provenance": {"code_sha": "e" * 40}}
    (site / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    fc = {"type": "FeatureCollection", "features": [{"properties": {"facility_id": "DEH-A", "band": "1", "points": 9}}]}
    (site / "facilities.geojson").write_text(json.dumps(fc), encoding="utf-8")
    (site / "place" / "DEH-A.json").write_text(json.dumps({"facility_id": "DEH-A", "band": "1", "points": 9}), encoding="utf-8")
    approval = tmp_path / "STAFF_APPROVAL.json"
    approval.write_text(json.dumps(GOOD), encoding="utf-8")
    out = tmp_path / "city"
    for name, value in (("SITE", site), ("APPROVAL", approval), ("HOLDS", tmp_path / "no-holds.json"),
                        ("REGISTERED", tmp_path / "no-registrations.json"), ("DEPLOY_LOG", tmp_path / "deploys.jsonl")):
        monkeypatch.setattr(pcs, name, value)
    touched = []
    monkeypatch.setattr(pcs.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(pcs, "head_commit", lambda: "a" * 40)
    monkeypatch.setattr(pcs, "tree_problems", lambda: ["1 tracked file(s) have uncommitted changes: commit or stash first"]
                        if dirty else [])
    monkeypatch.setattr(pcs, "frozen_problems", lambda meta: [])
    monkeypatch.setattr(pcs, "unpushed_warning", lambda: None)
    monkeypatch.setattr(pcs, "review_status", lambda meta, today: [])
    monkeypatch.setattr(pcs, "owner_route_problem", lambda approval: None)
    monkeypatch.setattr(pcs, "site_code", lambda commit: {"city_site/server.mjs": b"s", "city_site/render.yaml": b"r",
                                                          "city_site/watch.yml": b"w", "food-dashboard/package.json": b"{}"})

    def checkout(o, repo):
        touched.append("checkout")
        o.mkdir(exist_ok=True)
        _git("init", "-q", "-b", "main", cwd=o)
        _git("remote", "add", "origin", "https://github.com/o/r.git", cwd=o)
    monkeypatch.setattr(pcs, "ensure_checkout", checkout)
    monkeypatch.setattr(pcs, "check_target", lambda *a, **k: "o/r")
    monkeypatch.setattr(pcs, "write_ops", lambda o, commit, export_commit: touched.append(("ops", commit, export_commit)))
    monkeypatch.setattr(pcs, "commit_and_push", lambda o, msg: touched.append(("push", msg)) or "c" * 40)
    return out, touched


def test_a_full_publish_from_a_dirty_tree_is_refused_before_the_checkout_is_touched(tmp_path, monkeypatch):
    out, touched = _full_publish_env(tmp_path, monkeypatch, dirty=True)
    with pytest.raises(SystemExit, match="commit or stash first"):
        pcs.main(["--dir", str(out)])
    assert touched == [] and not out.exists()


def test_a_full_publish_records_both_commits_and_ships_the_monitor(tmp_path, monkeypatch):
    out, touched = _full_publish_env(tmp_path, monkeypatch)
    assert pcs.main(["--dir", str(out)]) == 0
    assert ("ops", "a" * 40, "e" * 40) in touched
    push = next(t for t in touched if isinstance(t, tuple) and t[0] == "push")[1]
    assert f"site from sdfood@{'a' * 7}, list from sdfood@{'e' * 7}" in push
    record = json.loads((out / "DEPLOYS.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["site_code_sha"] == "a" * 40 and record["export_code_sha"] == "e" * 40 and record["monitor"] == "failed"
    local = json.loads(pcs.DEPLOY_LOG.read_text(encoding="utf-8").splitlines()[-1])
    assert local["site_code_sha"] == "a" * 40 and local["export_code_sha"] == "e" * 40
    shipped = json.loads((out / "public" / "data" / "meta.json").read_text(encoding="utf-8"))
    assert shipped["monitor"]["status"] == "failed" and shipped["access_approved"] is False
    assert (out / "server.mjs").read_bytes() == b"s"


def test_a_full_publish_refuses_a_held_id_in_the_wrong_case(tmp_path, monkeypatch):
    out, touched = _full_publish_env(tmp_path, monkeypatch)
    pcs.HOLDS.write_text(json.dumps({"facility_ids": ["deh-a"]}), encoding="utf-8")
    with pytest.raises(SystemExit, match="did you mean DEH-A"):
        pcs.main(["--dir", str(out)])
    assert touched == []


def test_a_full_publish_says_only_what_it_knows_of_a_held_id_off_its_list(tmp_path, monkeypatch, capsys):
    """A new list may have lost a place, or the id may be a typo: the warning says which, from the record of
    what publishes held, and the record gains what this publish held."""
    out, touched = _full_publish_env(tmp_path, monkeypatch)
    pcs.HOLDS.write_text(json.dumps({"facility_ids": ["DEH-A", "DEH-GONE", "DEH-TYPO"]}), encoding="utf-8")
    (out / "ops").mkdir(parents=True)
    (out / "ops" / pcs.APPLIED).write_text(json.dumps({"facility_ids": ["DEH-GONE"]}), encoding="utf-8")
    assert pcs.main(["--dir", str(out)]) == 0
    said = capsys.readouterr().out
    assert "DEH-GONE is held and no longer on the list (a publish held it before" in said
    assert "DEH-TYPO is held and not on the list, and no publish has held it before: check the id" in said
    assert "it left the list after it was held" not in said, "never a reason it cannot know"
    assert pcs.applied_holds(out) == {"DEH-A", "DEH-GONE"}, "the record gains the place held now, never the typo"
    record = json.loads((out / "DEPLOYS.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert record["held"] == ["DEH-A", "DEH-GONE", "DEH-TYPO"] and record["held_on_list"] == ["DEH-A"]


def test_the_public_sites_owner_route_is_checked_and_its_absence_shown_to_staff(tmp_path, monkeypatch):
    page = '<script type="module" crossorigin src="/assets/index-ab12.js"></script><link rel="modulepreload" href="/assets/react-cd34.js">'
    placeholder = 'e?"email "+e:"email the authors (the address appears here once the site\u2019s operator sets it)"'
    built = 'href:`mailto:${t}`;' + placeholder + ';ownerContact:"FIX@example.org"'
    unset = 'href:`mailto:${t}`;' + placeholder + ';ownerContact:null'

    def site(bundle):
        files = {"https://sdfood.onrender.com/": page, "https://sdfood.onrender.com/assets/index-ab12.js": bundle,
                 "https://sdfood.onrender.com/assets/react-cd34.js": "react"}
        return lambda url: files[url]
    assert pcs.owner_route_problem(GOOD, fetch=site(built)) is None, "the address built in, beside the placeholder"
    assert pcs.owner_route_problem(GOOD, fetch=site(unset)) == pcs.OWNER_ROUTE_ITEM
    other = {**GOOD, "corrections_contact": {"email": "new@example.org"}}
    assert pcs.owner_route_problem(other, fetch=site(built)) == pcs.OWNER_ROUTE_ITEM, "a contact changed and not rebuilt"
    down = lambda url: (_ for _ in ()).throw(OSError("unreachable"))
    unread = pcs.owner_route_problem(GOOD, fetch=down)
    assert "could not be read" in unread
    # staff read these lines on every page: the site's copy rules hold for them (food-dashboard/tests/copy.test.mjs)
    banned = re.compile(r"\bfail(?:s|ed|ing|ure|ures)?\b|\brisk\b|\bclean\b|\bcaught\b|\bmiss(?:es|ed)\b|\u2014", re.I)
    assert not banned.search(pcs.OWNER_ROUTE_ITEM) and not banned.search(unread)
    # a publish tells staff, as an open item, and the operator, as a warning; it never refuses for it
    out, touched = _full_publish_env(tmp_path, monkeypatch)
    monkeypatch.setattr(pcs, "owner_route_problem", lambda approval: pcs.OWNER_ROUTE_ITEM)
    assert pcs.main(["--dir", str(out)]) == 0
    shipped = json.loads((out / "public" / "data" / "meta.json").read_text(encoding="utf-8"))
    assert pcs.OWNER_ROUTE_ITEM in shipped["review_status"]


def test_publish_needs_the_github_cli(tmp_path, monkeypatch):
    out, touched = _full_publish_env(tmp_path, monkeypatch)
    monkeypatch.setattr(pcs.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit, match="GitHub CLI"):
        pcs.main(["--dir", str(out)])
    assert touched == []


def test_a_push_that_is_not_served_in_time_has_its_own_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(pcs, "wait_live", lambda url, commit: None)
    assert pcs.wait_or_say("https://x", "c" * 40, lambda h: "live") == pcs.EXIT_NOT_SERVED == 5
    assert "pushed ccccccc, but https://x did not serve it" in capsys.readouterr().err
    monkeypatch.setattr(pcs, "wait_live", lambda url, commit: {"run": "r"})
    assert pcs.wait_or_say("https://x", "c" * 40, lambda h: f"live {h['run']}") == 0


def test_a_missing_checkout_is_cloned_not_started_afresh(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pcs.subprocess, "run", lambda cmd, **k: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(pcs, "run", lambda cmd, cwd: calls.append(cmd) or "")
    pcs.ensure_checkout(tmp_path / "city", "o/r")
    assert ["git", "clone", "-q", "https://github.com/o/r.git", str(tmp_path / "city")] in calls
    assert not any(c[:2] == ["git", "init"] for c in calls), "the deploy history is kept"


def test_the_docstring_names_every_sign_in_setting():
    for key in ("SITE_USERS", "SITE_OPERATORS", "SITE_PASSWORD", "SITE_USER", "SITE_CONTACT"):
        assert key in pcs.__doc__, key
    assert "shared" not in pcs.__doc__.split("On Render")[1]


def test_the_approval_example_asks_for_what_the_predicate_counts():
    ex = json.loads((pcs.ROOT / "docs" / "STAFF_APPROVAL.example.json").read_text(encoding="utf-8"))
    assert {"name", "date"} <= set(ex["city_requestor"]) and {"result", "by", "date"} <= set(ex["trust_determination"])
    assert {"resolution", "date"} <= set(ex["council_approval"])
    assert "on or before the day of publishing" in ex["_read_me"] and "a vote still to come is not an approval" in \
        ex["council_approval"]["_note"]
    assert pcs.access_approved(ex, TODAY) is False, "the empty example approves nothing"
