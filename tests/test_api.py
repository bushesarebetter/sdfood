"""api/main.py: keys, filters, a place's record, districts, results, worklists, CSV and reload, on a
small export in the contract's shape (docs/FOOD_DATA_CONTRACT.md)."""
import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

import api.main as api

KEY = "test-key-123"


def place(fid, name, district, band=None, points=None, flags=(), kind="restaurant", lon=-117.16, lat=32.72):
    props = {"facility_id": fid, "name": name, "address": f"1 {name} St, SAN DIEGO, CA 92101", "facility_type": kind,
             "council_district": district, "last_visit": {"date": "2026-08-01", "type": "routine"},
             "grade": {"grade": "A", "score": 94, "date": "2026-08-01", "replaced": None}, "flags": list(flags)}
    if band:
        props.update(band=band, points=points)
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    site = tmp_path / "site"
    (site / "place").mkdir(parents=True)
    feats = [place("DEH-1", "Alpha Grill", 3, "1", 40, ["major", "temperature"]),
             place("DEH-2", "Beta Cafe", 3, "2", 30, ["bc"]),
             place("DEH-3", "Gamma Market", 9, None, None, ["closed"], kind="market"),
             place("DEH-4", "Delta Sushi", 9, "1", 45, ["major", "repeat"])]
    (site / "facilities.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    for f in feats:
        p = f["properties"]
        (site / "place" / f"{p['facility_id']}.json").write_text(json.dumps({**p, "business_type": "Restaurant Food Facility",
                                                                              "inspections": [], "violations": []}), encoding="utf-8")
    meta = {"mode": "bands", "run": "forward_2026-09-20", "generated": "2026-09-24", "inspections_through": "2026-09-19",
            "expires": "2999-01-01", "source": {"name": "test"}, "catch_run": {"as_of": "2025-09-01"},
            "grade_context": {"majors_graded_A_share": 0.94},
            "card": {"rule": "Ordered by points.", "items": [{"item": "avg_deficit", "weight": 1}],
                     "bands": [{"band": "1", "min_points": 40, "max_points": 60, "places_now": 2, "rate": 0.48, "interval": [0.4, 0.56]},
                               {"band": "2", "min_points": 25, "max_points": 39, "places_now": 1, "rate": 0.3, "interval": [0.25, 0.35]}],
                     "rest": {"rate": 0.16}}}
    (site / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    wl = tmp_path / "worklists" / "2026-10"
    wl.mkdir(parents=True)
    with open(wl / "district-3.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["facility_id", "name", "address", "business_type", "last_routine_date", "last_routine_score",
                    "mean_routine_score_12m", "due_estimate", "rule_order", "rule_points", "why"])
        w.writerow(["DEH-1", "Alpha Grill", "1 Alpha St", "Restaurant Food Facility", "2025-10-01", "88", "88", "2026-10-05", "1", "40", "lowest mean"])
        w.writerow(["DEH-3", "Gamma Market", "1 Gamma St", "Retail Market with Deli", "2025-09-01", "94", "93.5", "2026-10-09", "2", "", "not scored"])
    (tmp_path / "research.json").write_text(json.dumps({"days_sooner_within_district_month": 6.2}), encoding="utf-8")
    monkeypatch.setenv("SDFOOD_DATA_DIR", str(site))
    monkeypatch.setenv("SDFOOD_WORKLISTS_DIR", str(tmp_path / "worklists"))
    monkeypatch.setenv("SDFOOD_RESEARCH_FILE", str(tmp_path / "research.json"))
    monkeypatch.setenv("SDFOOD_API_KEYS", f"other,{KEY}")
    api.get_store.cache_clear()
    c = TestClient(api.app)
    c.site = site
    yield c
    api.get_store.cache_clear()


H = {"X-API-Key": KEY}


def test_health_and_docs_are_open_but_data_needs_a_key(client, monkeypatch):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/health").json()["build"] is None
    monkeypatch.setenv("SDFOOD_BUILD", "forward_2026-09-20-20260924T213000Z")   # deploy_api.py stamps the image
    assert client.get("/health").json()["build"] == "forward_2026-09-20-20260924T213000Z"
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"] == "San Diego Food Inspection API"
    for path in ("/v1/summary", "/v1/facilities", "/v1/facilities/DEH-1", "/v1/districts", "/v1/worklists", "/v1/results"):
        assert client.get(path).status_code == 401, path
        assert client.get(path, headers={"X-API-Key": "wrong"}).status_code == 401, path
        assert client.get(path, headers=H).status_code == 200, path


def test_no_keys_configured_serves_no_data(client, monkeypatch):
    monkeypatch.setenv("SDFOOD_API_KEYS", "")
    assert client.get("/v1/facilities", headers=H).status_code == 503


def test_facility_filters_search_and_sorting(client):
    get = lambda **q: client.get("/v1/facilities", params=q, headers=H).json()
    assert get()["total"] == 4
    assert [p["facility_id"] for p in get(sort="points")["items"][:2]] == ["DEH-4", "DEH-1"]
    assert {p["facility_id"] for p in get(district=9)["items"]} == {"DEH-3", "DEH-4"}
    assert {p["facility_id"] for p in get(band="1")["items"]} == {"DEH-1", "DEH-4"}
    assert [p["facility_id"] for p in get(kind="market")["items"]] == ["DEH-3"]
    assert [p["facility_id"] for p in get(flag=["major", "repeat"])["items"]] == ["DEH-4"]
    assert [p["facility_id"] for p in get(q="sushi")["items"]] == ["DEH-4"]
    page = get(limit=1, offset=1, sort="name")
    assert page["total"] == 4 and [p["name"] for p in page["items"]] == ["Beta Cafe"]
    assert page["stale"] is False


def test_one_place(client):
    d = client.get("/v1/facilities/DEH-1", headers=H).json()
    assert d["name"] == "Alpha Grill" and d["band"] == "1" and d["business_type"] and "lon" in d
    assert client.get("/v1/facilities/NOPE", headers=H).status_code == 404


def test_districts_and_results(client):
    ds = {d["council_district"]: d for d in client.get("/v1/districts", headers=H).json()}
    assert ds[3]["places"] == 2 and ds[3]["in_bands"] == {"1": 1, "2": 1} and ds[3]["with_major_last_year"] == 1
    assert ds[9]["closed_for_health_hazard_last_year"] == 1
    one = client.get("/v1/districts/9", headers=H).json()
    assert [p["facility_id"] for p in one["in_bands"]] == ["DEH-4"]
    assert client.get("/v1/districts/7", headers=H).status_code == 404
    s = client.get("/v1/summary", headers=H).json()
    assert s["bands"][0]["lift"] == 3.0 and s["rest_rate"] == 0.16
    r = client.get("/v1/results", headers=H).json()
    assert r["bands"][0]["lift_over_other_restaurants"] == 3.0 and r["research"]["days_sooner_within_district_month"] == 6.2


def test_worklists(client):
    months = client.get("/v1/worklists", headers=H).json()
    assert months[0]["month"] == "2026-10" and months[0]["districts"] == [3]
    wl = client.get("/v1/worklists/2026-10/districts/3", headers=H).json()
    assert wl["rows"][0]["facility_id"] == "DEH-1" and wl["rows"][0]["rule_order"] == 1 and wl["rows"][0]["rule_points"] == 40
    assert wl["rows"][1]["rule_points"] is None and wl["rows"][1]["mean_routine_score_12m"] == 93.5
    csv_text = client.get("/v1/worklists/2026-10/districts/3", params={"format": "csv"}, headers=H).text
    assert csv_text.startswith("facility_id,name")
    assert client.get("/v1/worklists/2026-10/districts/5", headers=H).status_code == 404


def test_csv_export_carries_the_run_and_expiry(client):
    r = client.get("/v1/export.csv", params={"district": 3}, headers=H)
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert [x["facility_id"] for x in rows] == ["DEH-1", "DEH-2"]
    assert rows[0]["list_run"] == "forward_2026-09-20" and rows[0]["list_expires"] == "2999-01-01"


def test_stale_data_is_flagged_and_reload_picks_up_changes(client):
    meta = json.loads((client.site / "meta.json").read_text(encoding="utf-8"))
    meta["expires"] = "2000-01-01"
    (client.site / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    assert client.post("/v1/admin/reload", headers=H).json()["status"] == "reloaded"
    r = client.get("/v1/facilities", headers=H)
    assert r.json()["stale"] is True and r.headers["X-Data-Stale"] == "true"
