"""publish_city_site.py: the repository whose privacy is checked is the one that is pushed to."""
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
                        ({**GOOD, "sunset": "2026-01-01"}, "has passed"), ({**GOOD, "sunset": ""}, "sunset needs")]:
        assert any(why in p for p in pcs.approval_problems(broken, TODAY)), why
    assert len(pcs.approval_warnings(GOOD)) == 2 and pcs.approval_warnings({**GOOD, "city_requestor": {"name": "x"},
                                                                           "trust_determination": {"date": "2026-10-01"}}) == []


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
    a = fc["features"][0]["properties"]
    assert a == {"facility_id": "A", "on_hold": True} and fc["features"][1]["properties"]["points"] == 3
    assert changed["A"] == {"facility_id": "A", "inspections": [1], "on_hold": True}


def test_the_staff_copy_of_meta_names_who_is_responsible_and_what_the_list_has_not_passed():
    m = pcs.staff_meta(REAL, GOOD, ["no approval"], "tester")
    assert m["audience"] == "staff" and m["contact"]["email"] == "fix@example.org"
    assert m["operator"]["name"] == "A. Adult" and m["review_status"] == ["no approval"] and m["sunset"] == "2027-06-30"


def test_staff_are_told_when_the_operator_is_a_student_author():
    assert pcs.independence_problems(GOOD) == []
    assert pcs.independence_problems({**GOOD, "responsible_adult": {"name": "X", "relationship": "author", "email": "x@example.org"}})
    assert pcs.independence_problems({**GOOD, "responsible_adult": {"name": "Chenhao Zhang", "relationship": "parent", "email": "c@example.org"}})
