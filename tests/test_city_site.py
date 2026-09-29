"""city_site/server.mjs: malformed and ambiguous requests are answered, never crash the process and never
slip past the access log; sign-in is a form and a server-side session per person that expires and ends at
sign-out; guessing is slowed per address and user name; the site closes itself past its sunset or without
the staff export; nothing real is cached; the health check says which export is live; downloads are
audited; CSP reports are collected; the address lookup merges, retries and limits its upstream calls."""
import base64
import hashlib
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
SECRET = "s3cret-long-enough-16"
ANA = "ana-token-0123456789"
USERS_ENV = {"SITE_PASSWORD": SECRET, "SITE_USERS": f"ana:{ANA}", "SITE_CONTACT": "Jane Doe"}
META = {"run": "forward_2026-09-20-abcd1234", "expires": "2000-01-01", "inspections_through": "2026-09-19",
        "audience": "staff", "sunset": "2099-12-31", "frozen": {"version": "2026-09-22-aaaaaaaa"},
        "drift": {"refit_needed": True}, "access_approved": True}
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
HTML = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}


# ── a small HTTP client on raw sockets, so every byte of the request is ours ─────────────────────────

def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _raw(port, request: bytes, timeout=5) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
        s.sendall(request)
        chunks = []
        while True:
            try:
                b = s.recv(65536)
            except (socket.timeout, ConnectionResetError):
                break
            if not b:
                break
            chunks.append(b)
        return b"".join(chunks)


class Resp:
    def __init__(self, raw: bytes):
        self.raw = raw
        head, _, self.body = raw.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        self.status = int(lines[0].split()[1]) if lines[0].startswith("HTTP/") else None
        self.headers = {}
        for line in lines[1:]:
            k, _, v = line.partition(":")
            self.headers.setdefault(k.strip().lower(), []).append(v.strip())

    def header(self, name):
        v = self.headers.get(name.lower())
        return v[-1] if v else None

    @property
    def text(self):
        return self.body.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.body)


def _req(port, path, method="GET", headers=None, body=b"", cookie=None, timeout=5):
    hs = dict(headers or {})
    if cookie:
        hs["Cookie"] = f"__Host-s={cookie}"
    if body or method == "POST":
        hs.setdefault("Content-Length", str(len(body)))
    head = f"{method} {path} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n"
    head += "".join(f"{k}: {v}\r\n" for k, v in hs.items())
    return Resp(_raw(port, head.encode("latin-1") + b"\r\n" + body, timeout=timeout))


def _login(port, user, password, nxt="/", headers=None):
    body = urllib.parse.urlencode({"user": user, "password": password, "next": nxt}).encode()
    return _req(port, "/login", "POST", {**FORM, **(headers or {})}, body)


def _cookie(resp):
    sc = resp.header("set-cookie") or ""
    m = re.match(r"__Host-s=([^;]*)", sc)
    return m.group(1) if m else None


def _session(port, user="city", password=SECRET):
    r = _login(port, user, password)
    assert r.status == 303, r.raw[:400]
    return _cookie(r)


def _audit(port, cookie, payload, raw=None, headers=None):
    body = raw if raw is not None else json.dumps(payload).encode()
    return _req(port, "/audit", "POST", {"Content-Type": "application/json", **(headers or {})}, body, cookie=cookie)


# ── the server, against a throwaway dist/ ────────────────────────────────────────────────────────────

_MTIME = [time.time() + 1000]


def _write_meta(dist, meta):
    p = dist / "data" / "meta.json"
    p.write_text(json.dumps(meta), encoding="utf-8")
    _MTIME[0] += 7                                                  # always a new mtime: the server reloads it
    os.utime(p, (_MTIME[0], _MTIME[0]))


def _start(where: Path, env_extra, meta=None):
    where.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "city_site" / "server.mjs", where / "server.mjs")
    dist = where / "dist"
    (dist / "data" / "place").mkdir(parents=True, exist_ok=True)
    (dist / "assets").mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text("<!doctype html><title>staff</title>", encoding="utf-8")
    (dist / "sw.js").write_text("self.registration.unregister()", encoding="utf-8")
    (dist / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "data" / "meta.json").write_text(json.dumps(META if meta is None else meta), encoding="utf-8")
    (dist / "data" / "place" / "X.json").write_text('{"facility_id": "X"}', encoding="utf-8")
    port = _free_port()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("SITE_", "SESSION_", "GEOCODE_", "RENDER_"))}
    env.update(PORT=str(port), **env_extra)
    log = open(where / "server.log", "w")
    proc = subprocess.Popen(["node", str(where / "server.mjs")], env=env, stdout=log, stderr=subprocess.STDOUT)
    proc.log_file = log
    for _ in range(200):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            if proc.poll() is not None:
                break
            time.sleep(0.05)
    return port, proc


class Site:
    def __init__(self, where, port, proc):
        self.where, self.port, self.proc, self.dist = where, port, proc, where / "dist"

    def log(self):
        time.sleep(0.2)
        return (self.where / "server.log").read_text()


@pytest.fixture()
def start(tmp_path):
    procs = []

    def go(env=None, meta=None, users=True):
        where = tmp_path / f"site{len(procs)}"
        port, proc = _start(where, {**(USERS_ENV if users else {}), **(env or {})}, meta)
        procs.append(proc)
        return Site(where, port, proc)

    yield go
    for p in procs:
        p.kill()
        p.wait(timeout=10)
        p.log_file.close()


@pytest.fixture()
def site(start):
    return start()


# ── malformed and ambiguous requests ─────────────────────────────────────────────────────────────────

def test_malformed_requests_get_400_and_the_server_stays_up(site):
    port = site.port
    r = _raw(port, b"GET //[ HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")          # unauthenticated, bad URL
    assert r.startswith(b"HTTP/1.1 400")
    c = _session(port)
    assert _req(port, "/%E0%A4%A", cookie=c).status == 400                                 # bad %-escape
    assert _req(port, "/login?next=%E0%A4%A").status == 200                                 # a bad escape in a query
    assert site.proc.poll() is None, "the server process must still be running"
    assert _req(port, "/healthz").status == 200


def test_a_path_is_decoded_once_and_an_ambiguous_one_is_refused(site):
    port = site.port
    c = _session(port)
    for path in ("/assets/..%2fdata%2fmeta.json", "/assets/..%2Fdata%2Fmeta.json", "/data%2fmeta.json", "/data%5cmeta.json",
                 "/data%5Cplace%5CX.json", "/%2e%2e/%2e%2e/etc/passwd", "/..%2f..%2fetc%2fpasswd", "/data/./meta.json",
                 "/data//meta.json", "//data/meta.json", "/data/meta.json%00", "/data/%0ameta.json", "/assets/%5c..%5cdata"):
        for cookie in (c, None):
            r = _req(port, path, cookie=cookie)
            assert r.status == 400 and r.header("cache-control") == "no-store", (path, r.raw[:200])
            assert b"root:" not in r.raw and b"forward_2026" not in r.raw
    # A plain %-escape is fine, and it is judged by what it decodes to: logged, and never stored.
    r = _req(port, "/%64ata/place/X.json", cookie=c)
    assert r.status == 200 and r.header("cache-control") == "no-store" and b'"X"' in r.body
    r = _req(port, "/%61ssets/app-abc123.js", cookie=c)
    assert r.status == 200 and "immutable" in r.header("cache-control")
    # An app page under /assets/ (no such file) is the page, and the page is never stored.
    r = _req(port, "/assets/nothing-here", cookie=c)
    assert r.status == 200 and b"staff" in r.body and r.header("cache-control") == "no-store"
    assert "access user=city /data/place/X.json" in site.log()


# ── sign-in ──────────────────────────────────────────────────────────────────────────────────────────

def test_the_sign_in_page_is_a_self_contained_form(site):
    r = _req(site.port, "/login?next=/data/place/X.json")
    assert r.status == 200 and r.header("content-type").startswith("text/html")
    assert r.header("cache-control") == "no-store" and r.header("www-authenticate") is None
    for field in (b'name="user"', b'name="password"', b'type="password"', b'type="hidden" name="next" value="/data/place/X.json"',
                  b'method="post" action="/login"'):
        assert field in r.body, field
    assert b"For access, ask Jane Doe." in r.body
    assert not re.search(rb"(src|href)=", r.body), "no external assets"
    style = re.search(rb"<style>(.*?)</style>", r.body, re.S).group(1)
    sha = base64.b64encode(hashlib.sha256(style).digest()).decode()
    csp = r.header("content-security-policy")
    assert f"style-src 'sha256-{sha}'" in csp and "default-src 'none'" in csp and "form-action 'self'" in csp
    assert _req(site.port, "/login", "HEAD").status == 200


def test_every_person_signs_in_with_their_own_token_and_it_is_logged(site):
    port = site.port
    r = _req(port, "/", headers=HTML)                                         # a page: to the sign-in form
    assert r.status == 303 and r.header("location") == "/login?next=%2F" and r.header("www-authenticate") is None
    r = _req(port, "/data/meta.json?x=1", headers=HTML)
    assert r.status == 303 and r.header("location") == "/login?next=%2Fdata%2Fmeta.json%3Fx%3D1"
    for path in ("/data/meta.json", "/geocode?q=x", "/", "/data/place/X.json"):  # anything else: 401
        r = _req(port, path)
        assert r.status == 401 and r.header("cache-control") == "no-store" and r.header("www-authenticate") is None, path
    basic = "Basic " + base64.b64encode(f"city:{SECRET}".encode()).decode()
    assert _req(port, "/data/meta.json", headers={"Authorization": basic}).status == 401, "Basic auth is gone"

    bad = _login(port, "city", "nope-nope-nope-nope")
    assert bad.status == 401 and b"not right" in bad.body and _cookie(bad) is None
    assert b'value="city"' in bad.body, "the form comes back with the user name"
    assert _login(port, "ana", SECRET).status == 401, "a token belongs to one person"
    assert _login(port, "nobody", SECRET).status == 401
    assert _login(port, "ana", "").status == 401

    ok = _login(port, "ana", ANA, nxt="/data/place/X.json")
    assert ok.status == 303 and ok.header("location") == "/data/place/X.json"
    cookie = _cookie(ok)
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", cookie), "32 random bytes, base64url"
    assert ok.header("set-cookie") == f"__Host-s={cookie}; HttpOnly; Secure; SameSite=Strict; Path=/"
    assert _cookie(_login(port, "ana", ANA)) != cookie, "a new session each time"
    page = _req(port, "/", cookie=cookie)
    assert page.status == 200 and b"staff" in page.body
    assert _req(port, "/data/place/X.json", cookie=cookie).status == 200
    assert _req(port, "/data/place/X.json", cookie="made-up-" + cookie[8:]).status == 401
    signed_in = _req(port, "/login?next=/data/meta.json", cookie=cookie)
    assert signed_in.status == 303 and signed_in.header("location") == "/data/meta.json"
    log = site.log()
    assert "access user=ana /data/place/X.json" in log and "sign-in user=ana" in log
    assert 'sign-in failed user="nobody"' in log


def test_next_is_only_ever_a_path_on_this_site(site):
    port = site.port
    for nxt, want in [("/data/place/X.json?a=1", "/data/place/X.json?a=1"), ("/place/Caf%C3%A9", "/place/Caf%C3%A9"),
                      ("//evil.example/x", "/"), ("/\\evil.example", "/"), ("/\t/evil.example", "/"),
                      ("https://evil.example/", "/"), ("javascript:alert(1)", "/"), ("", "/"), ("evil", "/"),
                      ("/\r\nSet-Cookie: x=1", "/"), ("/logout", "/"), ("/login?next=//evil.example", "/"),
                      ("/.//evil.example", "/"), ("/a/..//evil.example/x", "/"), ("/%2e//evil.example", "/"),
                      ("/./\\evil.example", "/")]:
        r = _login(port, "city", SECRET, nxt=nxt)
        assert r.status == 303 and r.header("location") == want, (nxt, r.header("location"))
    r = _req(port, "/login?next=//evil.example")
    assert b'name="next" value="/"' in r.body
    r = _req(port, "/login?next=/.//evil.example")
    assert b'name="next" value="/"' in r.body, "dot segments cannot turn a path into another site"
    c = _session(port)
    r = _req(port, "/login?next=/a/..//evil.example/x", cookie=c)
    assert r.status == 303 and r.header("location") == "/", "not even for someone already signed in"


def test_sign_in_takes_only_a_small_same_site_form(site):
    port = site.port
    big = urllib.parse.urlencode({"user": "city", "password": SECRET, "next": "/" + "a" * 5000}).encode()
    r = _req(port, "/login", "POST", FORM, big)
    assert r.status == 413 and _cookie(r) is None
    json_body = json.dumps({"user": "city", "password": SECRET}).encode()
    assert _req(port, "/login", "POST", {"Content-Type": "application/json"}, json_body).status == 415
    r = _login(port, "city", SECRET, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status == 403 and _cookie(r) is None
    assert _login(port, "city", SECRET, headers={"Sec-Fetch-Site": "same-origin"}).status == 303
    r = _login(port, "city", SECRET, headers={"Origin": "https://evil.example"})
    assert r.status == 403 and _cookie(r) is None, "an older browser sends Origin, not Sec-Fetch-Site"
    assert _login(port, "city", SECRET, headers={"Origin": "null"}).status == 403
    assert _login(port, "city", SECRET, headers={"Origin": "http://x"}).status == 303, "this site's own origin"
    assert _req(port, "/login", "PUT").status == 405


def test_a_session_ends_after_its_idle_limit_and_its_absolute_limit(start):
    s = start({"SESSION_IDLE_MS": "600", "SESSION_MAX_MS": "2500"})
    c = _session(s.port)
    for _ in range(3):                                  # used every 0.25 s: it stays alive
        time.sleep(0.25)
        assert _req(s.port, "/data/meta.json", cookie=c).status == 200
    time.sleep(0.9)                                     # idle longer than 0.6 s (1.65 s in all): it has ended
    assert _req(s.port, "/data/meta.json", cookie=c).status == 401
    assert _req(s.port, "/", headers=HTML, cookie=c).status == 303

    c, began, seen = _session(s.port), time.monotonic(), []
    while time.monotonic() - began < 3.2:               # never idle, yet it ends after 2.5 s in all
        time.sleep(0.2)
        seen.append((time.monotonic() - began, _req(s.port, "/data/meta.json", cookie=c).status))
    assert all(code == 200 for t, code in seen if t < 2.3), seen
    assert seen[-1][1] == 401, seen


def test_sign_out_ends_the_session_and_clears_the_site(site):
    port = site.port
    c = _session(port)
    assert _req(port, "/data/meta.json", cookie=c).status == 200
    ask = _req(port, "/logout", cookie=c)
    assert ask.status == 200 and b'method="post" action="/logout"' in ask.body, "a link from anywhere only asks"
    assert _req(port, "/data/meta.json", cookie=c).status == 200, "asking does not sign out"
    assert _req(port, "/logout", "POST", {"Sec-Fetch-Site": "cross-site"}, cookie=c).status == 403
    assert _req(port, "/data/meta.json", cookie=c).status == 200, "another site cannot sign anyone out"
    out = _req(port, "/logout", "POST", cookie=c)
    assert out.status == 303 and out.header("location") == "/login?out=1"
    assert out.headers["set-cookie"] == ["__Host-s=; Max-Age=0; HttpOnly; Secure; SameSite=Strict; Path=/",
                                         "s=; Max-Age=0; Path=/; HttpOnly; Secure; SameSite=Strict"]
    assert out.header("clear-site-data") == '"cache", "storage"' and out.header("cache-control") == "no-store"
    assert out.header("www-authenticate") is None
    assert _req(port, "/data/meta.json", cookie=c).status == 401, "the session is gone on the server, not just the cookie"
    assert b"You are signed out." in _req(port, "/login?out=1").body
    c2 = _session(port)
    assert _req(port, "/logout", "POST", cookie=c2).status == 303
    assert _req(port, "/data/meta.json", cookie=c2).status == 401
    assert _req(port, "/logout", "POST").status == 303, "signing out without a session is harmless"
    assert "sign-out user=city" in site.log()


# ── slowing guessing ─────────────────────────────────────────────────────────────────────────────────

def test_guessing_is_slowed_per_address_and_user_name(site):
    port = site.port
    for _ in range(10):
        assert _login(port, "ana", "wrong-guess-wrong-guess").status == 401
    blocked = _login(port, "ana", ANA)
    assert blocked.status == 429 and blocked.header("retry-after") == "900", "blocked even with the right password"
    assert _cookie(blocked) is None
    assert _login(port, "city", SECRET).status == 303, "another person at the same address still signs in"
    assert _login(port, "ana", ANA, headers={"CF-Connecting-IP": "203.0.113.9"}).status == 303, "ana from elsewhere"
    # X-Forwarded-For is anyone's to write: changing it does not change who is counted.
    for i in range(10):
        assert _login(port, "city", "wrong-guess-wrong-guess", headers={"X-Forwarded-For": f"198.51.100.{i}"}).status == 401
    assert _login(port, "city", SECRET, headers={"X-Forwarded-For": "192.0.2.1"}).status == 429


def test_past_300_failures_in_all_every_sign_in_answer_waits(site):
    port = site.port
    began = time.monotonic()
    for i in range(301):                                # one failure each for 301 names: no key is blocked
        assert _login(port, f"guess{i}", "wrong-guess-wrong-guess").status == 401
    assert time.monotonic() - began < 30
    t = time.monotonic()
    assert _login(port, "guess-more", "wrong-guess-wrong-guess", ).status == 401
    assert time.monotonic() - t >= 1.8, "a failure past the budget waits about 2 s"
    t = time.monotonic()
    assert _login(port, "city", SECRET).status == 303
    assert time.monotonic() - t >= 1.8, "so does a success: a quick answer would give the password away"


def test_a_weak_password_refuses_to_start(tmp_path):
    port, proc = _start(tmp_path, {"SITE_PASSWORD": "short"})
    proc.wait(timeout=10)
    proc.log_file.close()
    assert proc.returncode == 1 and "shorter than 16" in (tmp_path / "server.log").read_text()


# ── what is stored, and the headers ──────────────────────────────────────────────────────────────────

def test_nothing_real_is_cached_and_every_response_has_the_security_headers(site):
    port = site.port
    sw = _req(port, "/sw.js")                           # before sign-in: a self-removing worker reaches every browser
    assert sw.status == 200 and sw.header("cache-control") == "no-store"
    c = _session(port)
    data = _req(port, "/data/meta.json", cookie=c)
    assert data.status == 200 and data.header("cache-control") == "no-store"
    for r in (data, _req(port, "/"), _req(port, "/login"), _req(port, "/healthz"), _req(port, "/%2e%2e/x")):
        for h, v in (("strict-transport-security", None), ("x-frame-options", "DENY"), ("x-content-type-options", "nosniff"),
                     ("content-security-policy-report-only", None)):
            assert r.header(h) and (v is None or r.header(h) == v), (h, r.raw[:120])
    assert _req(port, "/", "POST", cookie=c).status == 405
    assert _req(port, "/data/meta.json", "DELETE", cookie=c).status == 405


def test_the_csp_would_not_break_the_map_and_reports_come_back(site):
    csp = _req(site.port, "/healthz").header("content-security-policy-report-only")
    d = {part.split()[0]: part.split()[1:] for part in (p.strip() for p in csp.split(";")) if part}
    for src in ("'unsafe-eval'", "blob:", "https://*.googleapis.com", "https://*.gstatic.com", "https://*.google.com",
                "https://*.ggpht.com", "https://*.googleusercontent.com"):
        assert src in d["script-src"], src
    assert "https://*.google.com" in d["frame-src"]
    for src in ("https://*.googleusercontent.com", "https://*.gstatic.com", "https://*.googleapis.com", "data:"):
        assert src in d["img-src"], src
    for src in ("https://*.googleapis.com", "https://*.google.com", "https://*.gstatic.com"):
        assert src in d["connect-src"], src
    assert d["report-uri"] == ["/csp-report"]

    port = site.port
    report = {"csp-report": {"document-uri": "https://site/", "violated-directive": "script-src-elem",
                             "effective-directive": "script-src-elem", "blocked-uri": "https://evil.example/x.js"}}
    r = _req(port, "/csp-report", "POST", {"Content-Type": "application/csp-report"}, json.dumps(report).encode())
    assert r.status == 204, "no sign-in needed"
    api = [{"type": "csp-violation", "body": {"effectiveDirective": "img-src", "blockedURL": "https://tiles.example/1\n2.png"}}]
    assert _req(port, "/csp-report", "POST", {"Content-Type": "application/reports+json"}, json.dumps(api).encode()).status == 204
    assert _req(port, "/csp-report", "POST", {"Content-Type": "application/csp-report"}, b"{not json").status == 400
    assert _req(port, "/csp-report", "POST", {"Content-Type": "application/csp-report"}, b'{"x": 1}').status == 400
    big = json.dumps({"csp-report": {"blocked-uri": "x" * 9000}}).encode()
    assert _req(port, "/csp-report", "POST", {"Content-Type": "application/csp-report"}, big).status == 413
    assert _req(port, "/csp-report").status == 405
    codes = [_req(port, "/csp-report", "POST", {"Content-Type": "application/csp-report"}, json.dumps(report).encode()).status
             for _ in range(20)]
    assert 429 in codes, "reports are rate-limited"
    log = site.log()
    assert "csp-report directive=script-src-elem blocked=https://evil.example/x.js" in log
    assert "csp-report directive=img-src blocked=https://tiles.example/12.png" in log, "one line, whatever was sent"


# ── the runtime gate and the health check ────────────────────────────────────────────────────────────

def test_the_health_check_says_which_export_and_rule_are_live(site):
    h = _req(site.port, "/healthz").json()
    assert h["ok"] and h["run"] == "forward_2026-09-20-abcd1234" and h["stale"] is True and len(h["server"]) == 12
    assert h["inspections_through"] == "2026-09-19" and h["expires"] == "2000-01-01" and h["source"] is None
    assert h["sunset"] == "2099-12-31" and h["closed"] is None and h["refit_needed"] is True
    assert h["rule_version"] == "2026-09-22-aaaaaaaa" and h["access_approved"] is True
    _write_meta(site.dist, {k: v for k, v in META.items() if k not in ("frozen", "drift", "access_approved")})
    h = _req(site.port, "/healthz").json()
    assert h["refit_needed"] is False and h["rule_version"] is None and h["access_approved"] is False
    _write_meta(site.dist, {**META, "frozen": None, "drift": None, "access_approved": "yes"})
    h = _req(site.port, "/healthz").json()
    assert h["refit_needed"] is False and h["rule_version"] is None and h["access_approved"] is True


def test_the_site_closes_itself_past_its_sunset_or_without_the_staff_export(site):
    port = site.port
    c = _session(port)
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()     # the site's dates are San Diego's
    for meta, why in [({**META, "sunset": "2020-01-01"}, b"its sunset date, 2020-01-01, has passed"),
                      ({**META, "audience": "public"}, b'audience is not &#34;staff&#34;'),
                      ({k: v for k, v in META.items() if k != "audience"}, b"not the staff copy"),
                      ({k: v for k, v in META.items() if k != "sunset"}, b"has no sunset date")]:
        _write_meta(site.dist, meta)
        for path, cookie in (("/", c), ("/data/meta.json", c), ("/data/meta.json", None), ("/geocode?q=x", c),
                             ("/assets/app-abc123.js", c)):
            r = _req(port, path, cookie=cookie)
            assert r.status == 503 and r.header("cache-control") == "no-store", (meta, path, r.raw[:200])
            assert b"This site is closed: " in r.body and why in r.body, r.body
        assert _audit(port, c, {"event": "csv"}).status == 503
        assert _req(port, "/healthz").json()["closed"], "the health check says so"
        assert _req(port, "/login").status == 200 and _req(port, "/sw.js").status == 200
        assert _req(port, "/logout", "POST").status == 303
        assert _req(port, "/csp-report", "POST", {"Content-Type": "application/csp-report"},
                    b'{"csp-report": {"violated-directive": "img-src"}}').status == 204
    _write_meta(site.dist, {**META, "sunset": today})
    assert _req(port, "/data/meta.json", cookie=c).status == 200, "open through the sunset day itself"
    assert _req(port, "/healthz").json()["closed"] is None


# ── the download audit ───────────────────────────────────────────────────────────────────────────────

def test_downloads_and_prints_are_audited_strictly(site):
    port = site.port
    assert _audit(port, None, {"event": "csv"}).status == 401, "only for a signed-in person"
    c = _session(port, "ana", ANA)
    assert _audit(port, c, {"event": "csv", "rows": 12, "name": "District 3\u0007 worklist\n"}).status == 204
    assert _audit(port, c, {"event": "print"}).status == 204
    assert _audit(port, c, {"event": "csv", "name": "x" * 120}).status == 204
    assert _req(port, "/audit", "POST", {"Content-Type": "text/plain;charset=UTF-8"}, b'{"event":"print","rows":0}',
                cookie=c).status == 204, "navigator.sendBeacon sends a string as text/plain"
    for bad in ({"event": "delete"}, {"event": "CSV"}, {}, {"event": "csv", "rows": -1}, {"event": "csv", "rows": 1.5},
                {"event": "csv", "rows": "5"}, {"event": "csv", "rows": None}, {"event": "csv", "name": 5},
                {"event": "csv", "name": "x" * 121}, {"event": "csv", "extra": 1}, ["csv"], "csv", None):
        assert _audit(port, c, bad).status == 400, bad
    assert _audit(port, c, None, raw=b"{not json").status == 400
    assert _audit(port, c, None, raw=json.dumps({"event": "csv", "name": "x" * 3000}).encode()).status == 413
    assert _audit(port, c, {"event": "csv"}, headers={"Sec-Fetch-Site": "cross-site"}).status == 403
    assert _req(port, "/audit", cookie=c).status == 405
    log = site.log()
    assert 'audit user=ana event=csv rows=12 name="District 3 worklist"' in log
    assert "audit user=ana event=print rows=- name=-" in log
    assert "audit user=ana event=print rows=0 name=-" in log
    assert log.count("audit user=") == 4


# ── the address lookup ───────────────────────────────────────────────────────────────────────────────

class _Geocoders(http.server.BaseHTTPRequestHandler):
    """Both geocoders, invented: Nominatim finds only places with "park" in them; the Census finds nothing."""

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(u.query)
        srv = self.server
        with srv.lock:
            srv.calls.append((u.path, (q.get("q") or q.get("address") or [""])[0]))
        if u.path == "/search":
            time.sleep(srv.osm_delay)
            text = q["q"][0]
            body = [{"lat": "32.73", "lon": "-117.15", "display_name": text}] if "park" in text.lower() else []
        else:
            time.sleep(srv.census_delay)
            body = {"result": {"addressMatches": []}}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture()
def geocoders():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Geocoders)
    srv.lock, srv.calls, srv.osm_delay, srv.census_delay = threading.Lock(), [], 0.0, 0.0
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def _parallel(port, paths, cookie, timeout=15):
    out = [None] * len(paths)

    def one(i):
        out[i] = _req(port, paths[i], cookie=cookie, timeout=timeout).status

    threads = [threading.Thread(target=one, args=(i,)) for i in range(len(paths))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def test_address_lookups_in_flight_are_merged_and_a_miss_is_kept_briefly(start, geocoders):
    geocoders.osm_delay = 0.5
    s = start({"GEOCODE_UPSTREAM": f"http://127.0.0.1:{geocoders.server_address[1]}", "GEOCODE_FAIL_MS": "2500"})
    c = _session(s.port)
    assert _parallel(s.port, ["/geocode?q=Balboa%20Park"] * 3 + ["/geocode?q=balboa%20%20PARK"], c) == [200] * 4
    searched = [" ".join(q.lower().split()) for p, q in geocoders.calls if p == "/search"]
    assert searched == ["balboa park"], "one upstream call for four lookups"
    assert _req(s.port, "/geocode?q=Balboa%20Park", cookie=c).status == 200 and len(geocoders.calls) == 1, "a hit is kept"

    assert _req(s.port, "/geocode?q=Nowhere%20Street", cookie=c).status == 404
    calls = len(geocoders.calls)
    assert calls == 3, geocoders.calls                                  # Nominatim, then the Census
    assert _req(s.port, "/geocode?q=Nowhere%20Street", cookie=c).status == 404
    assert len(geocoders.calls) == calls, "a miss is kept for a while"
    time.sleep(2.7)
    assert _req(s.port, "/geocode?q=Nowhere%20Street", cookie=c).status == 404
    assert len(geocoders.calls) == calls + 2, "and then asked again, not kept forever"


def test_at_most_two_census_lookups_run_at_once(start, geocoders):
    geocoders.census_delay = 3.0
    s = start({"GEOCODE_UPSTREAM": f"http://127.0.0.1:{geocoders.server_address[1]}"})
    c = _session(s.port)
    # Nominatim takes one a second (1.1 s apart); each miss then waits 3 s on the Census. The third
    # lookup reaches the Census while the first two are still there.
    paths = [f"/geocode?q=Nowhere%20{i}" for i in range(3)]
    codes = _parallel(s.port, paths, c)
    assert sorted(codes) == [404, 404, 503], codes
    assert sum(1 for p, _ in geocoders.calls if p != "/search") == 2
    before = len(geocoders.calls)
    assert _req(s.port, paths[codes.index(503)], cookie=c).status == 404
    assert len(geocoders.calls) == before + 2, "busy is not remembered as a miss: it is looked up again"


def test_before_the_city_asks_only_the_operator_sees_the_named_list(start):
    """Until a City request and a TRUST determination are on record, a City sign-in issued early sees
    why, not the list; the operator's own sign-in (SITE_OPERATORS, by default the shared one) builds
    and checks it."""
    s = start(meta={**META, "access_approved": False})
    op, ana = _session(s.port), _session(s.port, "ana", ANA)
    assert _req(s.port, "/data/place/X.json", cookie=op).status == 200, "the operator"
    for path in ("/data/place/X.json", "/", "/geocode?q=x"):
        r = _req(s.port, path, cookie=ana)
        assert r.status == 503 and b"withheld until the City has recorded a request" in r.body, path
    assert _req(s.port, "/data/meta.json", cookie=ana).status == 200, "the app can still say why"
    assert _req(s.port, "/healthz").json()["named_list"] == "operators only"
    assert "withheld user=ana" in s.log()
    s2 = start(env={"SITE_OPERATORS": "ana"}, meta={**META, "access_approved": False})
    assert _req(s2.port, "/data/place/X.json", cookie=_session(s2.port, "ana", ANA)).status == 200
    assert _req(s2.port, "/data/place/X.json", cookie=_session(s2.port)).status == 503, "the shared sign-in is not an operator then"
    _write_meta(s.dist, {**META, "access_approved": True})
    assert _req(s.port, "/data/place/X.json", cookie=ana).status == 200, "once recorded, every signed-in person"

