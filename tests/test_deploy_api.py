"""deploy_api.py: what it refuses to ship, how it names and deploys an image, that it keeps the
registry package private and the deploy hook secret, and that the Dockerfile runs on Render's port."""
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
    good = {"status": "ok", "run": "r1", "places": 3, "build": "b1"}
    d.check_served("http://x", meta, "b1", "k", get=served(good))
    for bad, match in [(served({**good, "run": "r0"}), "serves"), (served({**good, "build": None}), "serves"),
                       (served(good, summary_status=200), "without a key"), (served(good, worklists=(200, [])), "no worklists"),
                       (served({"status": "no data"}), "health")]:
        with pytest.raises(d.Refused, match=match):
            d.check_served("http://x", meta, "b1", "k", get=bad)


def test_dry_run_prints_the_plan_runs_nothing_and_keeps_the_hook_secret(export, monkeypatch, capsys):
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


def test_a_real_deploy_needs_the_hook_and_refuses_before_building(export, monkeypatch, capsys):
    site, worklists, research = export
    for name, value in (("SITE", site), ("WORKLISTS", worklists), ("RESEARCH", research)):
        monkeypatch.setattr(d, name, value)
    monkeypatch.delenv("RENDER_DEPLOY_HOOK_URL", raising=False)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("nothing should run"))
    assert d.main(["--image", "ghcr.io/someone/sdfood-api", "--allow-expired"]) == 2
    assert "RENDER_DEPLOY_HOOK_URL" in capsys.readouterr().err


def test_dockerfile_listens_on_render_port_as_a_non_root_user():
    text = (ROOT / "api" / "Dockerfile").read_text(encoding="utf-8")
    cmd = next(line for line in text.splitlines() if line.startswith("CMD"))
    assert "${PORT:-8000}" in cmd and "0.0.0.0" in cmd and cmd.count("exec uvicorn") == 1
    assert "\nUSER api\n" in text and "ARG SDFOOD_BUILD" in text
    # a package linked to the public repository would share its read access: the image names no source
    assert "org.opencontainers.image.source" not in text
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert ignore.splitlines()[1] == "*" and "data/site/archive/" in ignore   # the archive stays out of the image
