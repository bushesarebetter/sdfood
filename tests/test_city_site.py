"""city_site/server.mjs: malformed requests are answered, never crash the process; sign-in works per
person and slows guessing; sign-out clears the browser; nothing real is cached; the health check says
which export is live; security headers are on every response."""
import base64
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
SECRET = "s3cret-long-enough-16"
ANA = "ana-token-0123456789"


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _raw(port, request: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
        s.sendall(request)
        chunks = []
        while True:
            try:
                b = s.recv(65536)
            except socket.timeout:
                break
            if not b:
                break
            chunks.append(b)
        return b"".join(chunks)


def _get(port, path, auth=None, extra=b"", method=b"GET"):
    head = method + b" " + path.encode() + b" HTTP/1.1\r\nHost: x\r\nConnection: close\r\n" + extra
    if auth:
        head += b"Authorization: Basic " + base64.b64encode(auth.encode()) + b"\r\n"
    return _raw(port, head + b"\r\n")


def _start(tmp_path, env_extra):
    shutil.copy(ROOT / "city_site" / "server.mjs", tmp_path / "server.mjs")
    dist = tmp_path / "dist"
    (dist / "data" / "place").mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text("<!doctype html><title>staff</title>", encoding="utf-8")
    (dist / "sw.js").write_text("self.registration.unregister()", encoding="utf-8")
    (dist / "data" / "meta.json").write_text(json.dumps({"run": "forward_2026-09-20-abcd1234", "expires": "2000-01-01",
                                                         "inspections_through": "2026-09-19"}), encoding="utf-8")
    (dist / "data" / "place" / "X.json").write_text('{"facility_id": "X"}', encoding="utf-8")
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("SITE_")}
    env.update(PORT=str(port), **env_extra)
    log = open(tmp_path / "server.log", "w")
    proc = subprocess.Popen(["node", str(tmp_path / "server.mjs")], env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            if proc.poll() is not None:
                break
            time.sleep(0.05)
    return port, proc


@pytest.fixture()
def server(tmp_path):
    port, proc = _start(tmp_path, {"SITE_PASSWORD": SECRET, "SITE_USERS": f"ana:{ANA}", "SITE_CONTACT": "Jane Doe"})
    yield port, proc, tmp_path
    proc.kill()


def test_malformed_requests_get_400_and_the_server_stays_up(server):
    port, proc, _ = server
    r = _raw(port, b"GET //[ HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")          # unauthenticated, bad URL
    assert r.startswith(b"HTTP/1.1 400")
    r = _get(port, "/%E0%A4%A", auth=f"city:{SECRET}")                                     # bad %-escape
    assert r.startswith(b"HTTP/1.1 400")
    assert proc.poll() is None, "the server process must still be running"
    assert _get(port, "/healthz").startswith(b"HTTP/1.1 200")


def test_every_person_signs_in_with_their_own_token_and_it_is_logged(server):
    port, _, tmp = server
    assert _get(port, "/").startswith(b"HTTP/1.1 401")
    assert b"ask Jane Doe" in _get(port, "/")
    assert _get(port, "/", auth="city:nope").startswith(b"HTTP/1.1 401")
    assert _get(port, "/", auth=f"ana:{SECRET}").startswith(b"HTTP/1.1 401"), "a token belongs to one person"
    ok = _get(port, "/", auth=f"city:{SECRET}")
    assert ok.startswith(b"HTTP/1.1 200") and b"staff" in ok
    assert _get(port, "/data/place/X.json", auth=f"ana:{ANA}").startswith(b"HTTP/1.1 200")
    trav = _get(port, "/..%2f..%2fetc%2fpasswd", auth=f"city:{SECRET}")
    assert b"root:" not in trav
    time.sleep(0.2)
    assert "access user=ana /data/place/X.json" in (tmp / "server.log").read_text()


def test_password_guessing_is_slowed_per_client(server):
    port, _, _ = server
    for _ in range(10):
        assert _get(port, "/", auth="city:wrong-guess").startswith(b"HTTP/1.1 401")
    assert _get(port, "/", auth=f"city:{SECRET}").startswith(b"HTTP/1.1 429"), "blocked even with the right password"


def test_a_weak_password_refuses_to_start(tmp_path):
    port, proc = _start(tmp_path, {"SITE_PASSWORD": "short"})
    proc.wait(timeout=10)
    assert proc.returncode == 1 and "shorter than 16" in (tmp_path / "server.log").read_text()


def test_sign_out_clears_the_site_and_nothing_real_is_cached(server):
    port, _, _ = server
    out = _get(port, "/logout")
    assert out.startswith(b"HTTP/1.1 401") and b"Clear-Site-Data" in out and b"WWW-Authenticate" not in out
    sw = _get(port, "/sw.js")                                 # before sign-in: a self-removing worker reaches every browser
    assert sw.startswith(b"HTTP/1.1 200") and b"no-store" in sw
    data = _get(port, "/data/meta.json", auth=f"city:{SECRET}")
    assert data.startswith(b"HTTP/1.1 200") and b"Cache-Control: no-store" in data
    for h in (b"Strict-Transport-Security", b"X-Frame-Options: DENY", b"X-Content-Type-Options: nosniff",
              b"Content-Security-Policy-Report-Only"):
        assert h in data and h in _get(port, "/"), h
    assert _get(port, "/", auth=f"city:{SECRET}", method=b"POST").startswith(b"HTTP/1.1 405")


def test_the_health_check_says_which_export_is_live(server):
    port, _, _ = server
    body = _get(port, "/healthz").split(b"\r\n\r\n", 1)[1]
    h = json.loads(body)
    assert h["ok"] and h["run"] == "forward_2026-09-20-abcd1234" and h["stale"] is True and len(h["server"]) == 12
