"""deploy_api.py: what it refuses to ship, how it names and deploys an image, that it keeps the
registry package private and the deploy hook secret, that the Dockerfile runs on Render's port, and that an
image ships only once the City has asked, with every hold applied and its sunset inside it."""
import csv
import json
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

import deploy_api as d

ROOT = Path(__file__).resolve().parents[1]
HOOK = "https://api.render.com/deploy/srv-abc123?key=SECRETKEY"


@pytest.fixture()
def export(tmp_path):
    site, worklists = tmp_path / "site", tmp_path / "worklists"
    (site / "place").mkdir(parents=True)
    (worklists / "2026-10").mkdir(parents=True)
    meta = {"mode": "bands", "sample": False, "run": "forward_2026-09-20", "places": 3,
            "inspections_through": "2026-09-19", "expires": "2026-10-03"}
    (site / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (site / "facilities.geojson").write_text("{}", encoding="utf-8")
    (worklists / "2026-10" / "manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "research.json").write_text("{}", encoding="utf-8")
    return site, worklists, tmp_path / "research.json"


def edit_meta(site, **changes):
    meta = json.loads((site / "meta.json").read_text(encoding="utf-8"))
    (site / "meta.json").write_text(json.dumps({**meta, **changes}), encoding="utf-8")


def test_preflight_ships_only_a_real_complete_current_export(export):
    site, worklists, research = export
    ok = lambda **kw: d.preflight(site, worklists, research, today=date(2026, 10, 3), **kw)
    assert ok()["run"] == "forward_2026-09-20"
    with pytest.raises(d.Refused, match="expired on 2026-10-03"):
        d.preflight(site, worklists, research, today=date(2026, 10, 4))
    assert d.preflight(site, worklists, research, today=date(2026, 10, 4), allow_expired=True)
    edit_meta(site, sample=True)
    with pytest.raises(d.Refused, match="invented sample"):
        ok()
    edit_meta(site, sample=False)
    (site / "facilities.geojson").unlink()
    with pytest.raises(d.Refused, match="incomplete"):
        ok()


@pytest.mark.parametrize("missing, why", [("meta", "no export"), ("worklists", "no worklists"), ("research", "missing")])
def test_preflight_names_what_is_missing(export, missing, why):
    site, worklists, research = export
    {"meta": site / "meta.json", "worklists": worklists / "2026-10" / "manifest.json", "research": research}[missing].unlink()
    with pytest.raises(d.Refused, match=why):
        d.preflight(site, worklists, research, today=date(2026, 9, 24))


def test_image_names_and_tags():
    assert d.check_image_name("ghcr.io/someone/sdfood-api") == "ghcr.io/someone/sdfood-api"
    for bad in (None, "", "ghcr.io/SomeOne/sdfood-api", "ghcr.io/someone/sdfood-api:latest",
                "ghcr.io/someone/sdfood-api@sha256:00", "sdfood-api"):
        with pytest.raises(d.Refused):
            d.check_image_name(bad)
    tag = d.build_tag({"run": "forward_2026-09-20"}, now=datetime(2026, 9, 24, 21, 30, tzinfo=timezone.utc))
    assert tag == "forward_2026-09-20-20260924T213000Z"


def test_deploy_hook_is_told_the_exact_image():
    ref = "ghcr.io/someone/sdfood-api@sha256:" + "a" * 64
    url = d.hook_url(HOOK, ref)
    q = parse_qs(urlsplit(url).query)
    assert q == {"key": ["SECRETKEY"], "imgURL": [ref]}
    assert "%2F" in url and "%40" in url and "%3A" in url      # the image reference is URL-encoded
    assert parse_qs(urlsplit(d.hook_url(url, "ghcr.io/someone/x@sha256:b")).query)["imgURL"] == ["ghcr.io/someone/x@sha256:b"]
    with pytest.raises(d.Refused):
        d.hook_url("http://api.render.com/deploy/srv-abc?key=k", ref)


def fake_gh(login, visibility=None, error=None):
    calls = []

    def gh(args):
        calls.append(args)
        if args[:2] == ["api", "user"]:
            return login + "\n"
        if error:
            raise subprocess.CalledProcessError(1, ["gh", *args], stderr=error)
        return f"{visibility}\n"
    gh.calls = calls
    return gh


def test_package_visibility_asks_github_about_the_right_owner():
    gh = fake_gh("SomeOne", "private")
    assert d.package_visibility("ghcr.io/someone/sdfood-api", gh) == "private"
    assert gh.calls[-1][1] == "/user/packages/container/sdfood-api"
    gh = fake_gh("someone", "private")
    d.package_visibility("ghcr.io/city-org/sdfood-api", gh)
    assert gh.calls[-1][1] == "/orgs/city-org/packages/container/sdfood-api"
    assert d.package_visibility("ghcr.io/someone/sdfood-api", fake_gh("someone", error="gh: Not Found (HTTP 404)")) is None
    with pytest.raises(d.Refused, match="read:packages"):
        d.package_visibility("ghcr.io/someone/sdfood-api", fake_gh("someone", error="gh: need read:packages (HTTP 403)"))


def test_only_a_private_package_is_pushed_to_or_deployed():
    img = "ghcr.io/someone/sdfood-api"
    d.ensure_private(img, pushed=False, gh=fake_gh("someone", error="HTTP 404"))    # a new package starts private
    d.ensure_private(img, pushed=True, gh=fake_gh("someone", "private"))
    for pushed in (False, True):
        with pytest.raises(d.Refused, match="is public"):
            d.ensure_private(img, pushed=pushed, gh=fake_gh("someone", "public"))
    with pytest.raises(d.Refused, match="does not list"):
        d.ensure_private(img, pushed=True, gh=fake_gh("someone", error="HTTP 404"))


def served(health, summary_status=401, worklists=(200, [{"month": "2026-10"}])):
    def get(url, headers=None):
        if url.endswith("/health"):
            return 200, health
        if url.endswith("/v1/summary"):
            return summary_status, None
        return worklists
    return get


def test_the_image_is_checked_before_it_is_pushed():
    meta = {"run": "r1", "places": 3}
    good = {"status": "ok", "run": "r1", "places": 3, "build": "b1", "sunset": "2027-06-30", "closed": None}
    d.check_served("http://x", meta, "b1", "k", get=served(good))
    d.check_served("http://x", meta, "b1", "k", get=served(good), release={"sunset": "2027-06-30"})
    for bad, match in [(served({**good, "run": "r0"}), "serves"), (served({**good, "build": None}), "serves"),
                       (served(good, summary_status=200), "without a key"), (served(good, worklists=(200, [])), "no worklists"),
                       (served({"status": "no data"}), "health")]:
        with pytest.raises(d.Refused, match=match):
            d.check_served("http://x", meta, "b1", "k", get=bad)
    with pytest.raises(d.Refused, match="sunset"):     # an image that does not carry the release closes on no date
        d.check_served("http://x", meta, "b1", "k", get=served({**good, "sunset": None}), release={"sunset": "2027-06-30"})


GOOD = {"responsible_adult": {"name": "A. Adult", "email": "a@example.org"},
        "corrections_contact": {"email": "fix@example.org"}, "sunset": "2027-06-30"}
ASKED = {"city_requestor": {"name": "R", "date": "2026-09-01"},
         "trust_determination": {"result": "does not apply", "by": "City Attorney's office", "date": "2026-09-15"}}


@pytest.fixture()
def approved(tmp_path, monkeypatch):
    """docs/STAFF_APPROVAL.json with the City's request and TRUST answer on record, and no holds."""
    import publish_city_site as pcs
    path = tmp_path / "STAFF_APPROVAL.json"
    path.write_text(json.dumps({**GOOD, **ASKED}), encoding="utf-8")
    monkeypatch.setattr(pcs, "APPROVAL", path)
    monkeypatch.setattr(pcs, "HOLDS", tmp_path / "no-holds.json")
    return path


def test_dry_run_prints_the_plan_runs_nothing_and_keeps_the_hook_secret(export, approved, monkeypatch, capsys):
    site, worklists, research = export
    monkeypatch.setattr(d, "SITE", site)
    monkeypatch.setattr(d, "WORKLISTS", worklists)
    monkeypatch.setattr(d, "RESEARCH", research)
    monkeypatch.setenv("RENDER_DEPLOY_HOOK_URL", HOOK)

    def nothing_runs(*a, **k):
        raise AssertionError(f"ran {a}")
    monkeypatch.setattr(subprocess, "run", nothing_runs)
    assert d.main(["--image", "ghcr.io/someone/sdfood-api", "--dry-run", "--allow-expired"]) == 0
    out = capsys.readouterr().out
    assert "docker build --platform linux/amd64 --provenance=false --build-arg SDFOOD_BUILD=forward_2026-09-20-" in out
    assert f"-e PORT={d.RENDER_PORT}" in out and "docker push ghcr.io/someone/sdfood-api:forward_2026-09-20-" in out
    # the service's Image URL names :latest, and Render returns to it on later deploys: it moves after the checks
    assert out.index("docker push ghcr.io/someone/sdfood-api:forward_") < out.index("docker push ghcr.io/someone/sdfood-api:latest")
    assert "imgURL=ghcr.io/someone/sdfood-api@sha256:" in out and "SECRETKEY" not in out
    assert "api_release.json (sunset 2027-06-30, access_approved True, 0 held)" in out
    assert out.index("api_release.json") < out.index("docker build"), "the release is in the image"
    assert not (site / d.RELEASE_FILE).exists(), "a dry run writes nothing"


@pytest.mark.parametrize("build_ok", [True, False])
def test_the_release_record_is_on_disk_only_while_the_image_is_built(export, approved, monkeypatch, build_ok):
    """So an image built by hand later, from a release checked another day, stops at the Dockerfile's COPY."""
    site, worklists, research = export
    for name, value in (("SITE", site), ("WORKLISTS", worklists), ("RESEARCH", research)):
        monkeypatch.setattr(d, name, value)
    seen = []

    def sh(cmd, dry=False, capture=False):
        if cmd[:2] == ["docker", "build"]:
            seen.append(json.loads((site / d.RELEASE_FILE).read_text(encoding="utf-8"))["sunset"])
            if not build_ok:
                raise subprocess.CalledProcessError(1, cmd)
        return ""
    monkeypatch.setattr(d, "sh", sh)
    monkeypatch.setattr(d, "smoke_test", lambda *a, **k: None)
    assert d.main(["--image", "ghcr.io/someone/sdfood-api", "--allow-expired", "--no-push"]) == (0 if build_ok else 1)
    assert seen == ["2027-06-30"], "the build reads the record"
    assert not (site / d.RELEASE_FILE).exists(), "and it is gone afterwards, whether the build went through or not"


def test_the_release_record_is_what_the_image_carries(export, tmp_path):
    site, _, _ = export
    rec = d.release_record({**GOOD, **ASKED}, {"DEH-B", "DEH-A"}, today=date(2026, 9, 29))
    assert rec["sunset"] == "2027-06-30" and rec["access_approved"] is True and rec["held"] == ["DEH-A", "DEH-B"]
    d.write_release(site, rec)
    assert json.loads((site / d.RELEASE_FILE).read_text(encoding="utf-8"))["sunset"] == "2027-06-30"
    assert d.release_record(GOOD, set(), today=date(2026, 9, 29))["access_approved"] is False


def test_deploy_hook_answers():
    ref = "ghcr.io/someone/sdfood-api@sha256:" + "a" * 64
    seen = []
    post = lambda url, method: seen.append((url, method)) or (200, {"deploy": {"id": "dep-1"}})
    d.deploy(HOOK, ref, dry=False, post=post)
    assert seen[0][1] == "POST" and "imgURL=" in seen[0][0]
    d.deploy(HOOK, ref, dry=False, post=lambda url, method: (202, None))     # queued behind a running deploy
    for status in (400, 401, 404, 409, 500):
        with pytest.raises(d.Refused, match=str(status)):
            d.deploy(HOOK, ref, dry=False, post=lambda url, method, s=status: (s, None))


def test_a_real_deploy_needs_the_hook_and_refuses_before_building(export, approved, monkeypatch, capsys):
    site, worklists, research = export
    for name, value in (("SITE", site), ("WORKLISTS", worklists), ("RESEARCH", research)):
        monkeypatch.setattr(d, name, value)
    monkeypatch.delenv("RENDER_DEPLOY_HOOK_URL", raising=False)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("nothing should run"))
    assert d.main(["--image", "ghcr.io/someone/sdfood-api", "--allow-expired"]) == 2
    assert "RENDER_DEPLOY_HOOK_URL" in capsys.readouterr().err


def test_no_image_is_built_before_the_city_has_asked(export, approved, monkeypatch, capsys):
    site, worklists, research = export
    for name, value in (("SITE", site), ("WORKLISTS", worklists), ("RESEARCH", research)):
        monkeypatch.setattr(d, name, value)
    approved.write_text(json.dumps(GOOD), encoding="utf-8")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("nothing should run"))
    assert d.main(["--image", "ghcr.io/someone/sdfood-api", "--allow-expired", "--no-push"]) == 2
    assert "no City request and TRUST answer are on record" in capsys.readouterr().err


def test_dockerfile_listens_on_render_port_as_a_non_root_user():
    text = (ROOT / "api" / "Dockerfile").read_text(encoding="utf-8")
    cmd = next(line for line in text.splitlines() if line.startswith("CMD"))
    assert "${PORT:-8000}" in cmd and "0.0.0.0" in cmd and cmd.count("exec uvicorn") == 1
    assert "\nUSER api\n" in text and "ARG SDFOOD_BUILD" in text
    # a package linked to the public repository would share its read access: the image names no source
    assert "org.opencontainers.image.source" not in text
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert ignore.splitlines()[1] == "*" and "data/site/archive/" in ignore   # the archive stays out of the image
    # so do the pilot's frozen worklists, which keep a place's points from before a hold (they are not served)
    assert "data/worklists/*/frozen/" in ignore.splitlines()
    # the sunset is San Diego's date: the image carries the time-zone database the API reads it with
    assert any(line.startswith("tzdata==") for line in (ROOT / "api" / "requirements.txt").read_text(encoding="utf-8").splitlines())
    assert "COPY data/site/ data/site/" in text, "the release record (data/site/api_release.json) goes into the image"
    # named on its own, so a build without the record deploy_api.py writes stops (the API serves nothing without it)
    assert "\nCOPY data/site/api_release.json data/site/api_release.json\n" in text


def test_the_api_has_the_staff_sites_release_gates(export):
    site, worklists, research = export
    good = {**GOOD, **ASKED}
    today = date(2026, 9, 29)
    assert d.release_problems(site, today, approval=good, holds=[], worklists=worklists) == []
    assert any("STAFF_APPROVAL" in p for p in d.release_problems(site, today, approval={}, holds=[], worklists=worklists))
    assert any("has passed" in p for p in d.release_problems(site, today, approval={**good, "sunset": "2026-01-01"}, holds=[],
                                                              worklists=worklists))
    (site / "facilities.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"properties": {"facility_id": "A", "band": "1", "points": 12}},
        {"properties": {"facility_id": "B", "on_hold": True}}]}), encoding="utf-8")
    got = d.release_problems(site, today, approval=good, holds=["A", "B"], worklists=worklists)
    assert got == ["1 place(s) on hold still carry points or a band in " + str(site) + " (A): export again, then deploy"]
    assert d.release_problems(site, today, approval=good, holds=["B"], worklists=worklists) == [], "a hold the export applied passes"


def test_the_api_ships_only_once_the_city_has_asked(export):
    site, worklists, _ = export
    today = date(2026, 9, 29)
    for approval in (GOOD, {**GOOD, "city_requestor": ASKED["city_requestor"]},
                     {**GOOD, **ASKED, "trust_determination": {"result": "does not apply"}}):
        got = d.release_problems(site, today, approval=approval, holds=[], worklists=worklists)
        assert any("no City request and TRUST answer are on record" in p and "every key holder" in p for p in got), approval


def _worklist(folder, rows):
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "district-3.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["facility_id", "name", "rule_order", "rule_points", "rule_mean", "why"])
        w.writerows(rows)


def test_a_held_place_that_keeps_its_points_in_a_worklist_the_image_carries_is_refused(export):
    site, worklists, _ = export
    good, today = {**GOOD, **ASKED}, date(2026, 9, 29)
    held_line = "On hold at the owner's request: its points, band and order are withheld while the request is reviewed."
    _worklist(worklists / "2026-10", [["B", "Beta", "2", "", "", held_line], ["C", "Gamma", "1", "12", "88", "12 points"]])
    (site / "facilities.geojson").write_text(json.dumps({"features": [{"properties": {"facility_id": "B", "on_hold": True}}]}),
                                             encoding="utf-8")
    assert d.release_problems(site, today, approval=good, holds=["B"], worklists=worklists) == [], "a hold written in passes"
    for row in (["B", "Beta", "1", "12", "88", "Point rule: 12 points, band 1."], ["B", "Beta", "1", "", "", "band 1"],
                ["B", "Beta", "1", "", "91.5", "x"]):
        _worklist(worklists / "2026-11", [row])
        got = d.release_problems(site, today, approval=good, holds=["B"], worklists=worklists)
        assert any("worklist row(s) of a place on hold" in p and "2026-11/district-3.csv: B" in p for p in got), row
    # the frozen pilot copies are not served, and not scanned
    (worklists / "2026-11" / "district-3.csv").unlink()
    _worklist(worklists / "2026-11" / "frozen" / "20261001T000000Z", [["B", "Beta", "1", "12", "88", "12 points"]])
    assert d.release_problems(site, today, approval=good, holds=["B"], worklists=worklists) == []


def test_an_unreadable_holds_file_is_a_refusal_not_no_holds(export, tmp_path, monkeypatch):
    import publish_city_site as pcs
    site, worklists, _ = export
    holds = tmp_path / "holds.json"
    holds.write_text('{"facility_ids": ["A",]}', encoding="utf-8")
    monkeypatch.setattr(pcs, "HOLDS", holds)
    got = d.release_problems(site, date(2026, 9, 29), approval={**GOOD, **ASKED}, worklists=worklists)
    assert any("cannot be read" in p for p in got)
