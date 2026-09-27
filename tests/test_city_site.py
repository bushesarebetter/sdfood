"""city_site/server.mjs: malformed requests are answered, never crash the process; auth still works."""
import base64
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")


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
                b = s.recv(4096)
            except socket.timeout:
                break
            if not b:
                break
            chunks.append(b)
        return b"".join(chunks)


@pytest.fixture()
def server(tmp_path):
    shutil.copy(ROOT / "city_site" / "server.mjs", tmp_path / "server.mjs")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("<!doctype html><title>staff</title>", encoding="utf-8")
    port = _free_port()
    env = dict(os.environ, SITE_PASSWORD="s3cret", PORT=str(port))
    proc = subprocess.Popen(["node", str(tmp_path / "server.mjs")], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    yield port, proc
    proc.kill()


AUTH = b"Authorization: Basic " + base64.b64encode(b"city:s3cret") + b"\r\n"


def test_malformed_requests_get_400_and_the_server_stays_up(server):
    port, proc = server
    r = _raw(port, b"GET //[ HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")          # unauthenticated, bad URL
    assert r.startswith(b"HTTP/1.1 400")
    r = _raw(port, b"GET /%E0%A4%A HTTP/1.1\r\nHost: x\r\n" + AUTH + b"Connection: close\r\n\r\n")  # bad %-escape
    assert r.startswith(b"HTTP/1.1 400")
    assert proc.poll() is None, "the server process must still be running"
    assert _raw(port, b"GET /healthz HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n").endswith(b"ok")


def test_auth_still_required_and_accepted(server):
    port, _ = server
    assert _raw(port, b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n").startswith(b"HTTP/1.1 401")
    wrong = b"Authorization: Basic " + base64.b64encode(b"city:nope") + b"\r\n"
    assert _raw(port, b"GET / HTTP/1.1\r\nHost: x\r\n" + wrong + b"Connection: close\r\n\r\n").startswith(b"HTTP/1.1 401")
    ok = _raw(port, b"GET / HTTP/1.1\r\nHost: x\r\n" + AUTH + b"Connection: close\r\n\r\n")
    assert ok.startswith(b"HTTP/1.1 200") and b"staff" in ok
    trav = _raw(port, b"GET /..%2f..%2fetc%2fpasswd HTTP/1.1\r\nHost: x\r\n" + AUTH + b"Connection: close\r\n\r\n")
    assert b"root:" not in trav
