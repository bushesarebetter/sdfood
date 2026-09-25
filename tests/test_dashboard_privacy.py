"""The public dashboard publishes aggregates only (privacy_gate.py)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import export_dashboard as ed
import privacy_gate as pg

ROOT = Path(__file__).resolve().parents[1]


def test_committed_dashboard_passes_the_gate():
    html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    payload = pg.dashboard_payload(html)
    assert payload is not None and pg.violations(payload) == []
    assert "worklist" not in payload and "summary" in payload
    assert payload["summary"]["facilities"] == payload["stats"]["active_facilities"]


def test_the_old_row_level_worklist_is_rejected():
    row = {"id": "F-00001", "risk": 45.6, "type": "Restaurant Food Facility", "prior_band": "2–4",
           "major_band": "elevated", "due": False, "months_since": 4.9}
    with pytest.raises(ValueError, match="facility-level|row-level"):
        pg.check({"stats": {}, "worklist": [row] * 15647})
    assert any("row-level" in v for v in pg.violations({"x": [{"type": "t", "risk": 1.0}] * 61}))
    assert any("below 11" in v for v in pg.violations({"by_type": [{"type": "Boat", "facilities": 3}]}))


def _frame(n_types=(500, 40, 12, 5, 3)):
    rng = np.random.default_rng(0)
    rows = []
    for k, n in enumerate(n_types):
        for _ in range(n):
            rows.append({"business_type": f"type-{k}", "due_this_month": rng.random() < 0.3,
                         "prior_major_rate": rng.choice([np.nan, 0.0, 0.25, 0.5]), "model_risk": rng.random() * 0.6})
    return pd.DataFrame(rows)


def test_aggregate_pools_rare_types_and_suppresses_small_counts():
    f = _frame()
    s = ed.aggregate(f)
    assert s["facilities"] == len(f) and s["due"] == int(f["due_this_month"].sum())
    types = [r["type"] for r in s["by_type"]]
    assert "type-3" not in types and "type-4" not in types and types[-1] == "Other types"
    other = next(r for r in s["by_type"] if r["type"] == "Other types")
    assert other["facilities"] is None                   # 5 + 3 = 8 facilities: published as "<11"
    for r in s["by_type"] + s["risk_bins"]:
        for k, v in r.items():
            if k not in ("type", "from", "to"):
                assert v is None or v == 0 or v >= pg.MIN_CELL
    assert sum(r["facilities"] or 0 for r in s["risk_bins"]) <= len(f)
    pg.check({"summary": s})


def test_render_refuses_a_row_level_payload(tmp_path):
    with pytest.raises(ValueError):
        ed.render({"stats": {}, "worklist": [{"type": "x"}] * 100}, out=str(tmp_path / "d.html"))
    assert not (tmp_path / "d.html").exists()


def test_render_round_trips_a_clean_payload(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    payload = {"generated": "2026-09-25", "as_of": "2026-09-19", "stats": {"t": {}},
               "summary": ed.aggregate(_frame())}
    out = ed.render(payload, out=str(tmp_path / "d.html"))
    html = Path(out).read_text(encoding="utf-8")
    assert pg.dashboard_payload(html) == json.loads(json.dumps(payload))
    assert "IMG_GAINS" not in html and "data:image/png;base64," in html


def test_a_type_name_cannot_close_the_script_block(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    f = _frame((20,))
    f["business_type"] = "</script><script>alert(1)</script>"
    out = ed.render({"stats": {"t": {}}, "summary": ed.aggregate(f)}, out=str(tmp_path / "d.html"))
    html = Path(out).read_text(encoding="utf-8")
    script = html[html.index("/*__DATA__*/"):]
    assert "</script><script>alert(1)" not in script
    assert pg.dashboard_payload(html)["summary"]["by_type"][0]["type"] == "</script><script>alert(1)</script>"
