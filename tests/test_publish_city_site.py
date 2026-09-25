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
