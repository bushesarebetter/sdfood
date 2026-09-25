"""San Diego Food Inspection API: an internal service for City of San Diego staff.

It serves what export_site.py writes (data/site/: the index, one file per place, meta.json) and the
monthly worklists export_worklist.py writes (data/worklists/<yyyy-mm>/district-<n>.csv): each
listed restaurant and market's County inspection record, the published scoring rule's points and
band, district summaries and per-district monthly worklists.

    SDFOOD_API_KEYS=key1,key2 uvicorn api.main:app --reload       # http://localhost:8000/docs

Every data endpoint needs an `X-API-Key` header with one of SDFOOD_API_KEYS. The interactive docs
(/docs, /redoc) and /health carry no data and are open. See docs/API.md."""
from __future__ import annotations

import csv
import io
import json
import os
import secrets
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ("major", "closed", "bc", "repeat")


# ── the data ──────────────────────────────────────────────────────────────────────────

class Store:
    """The export on disk, loaded once and reloaded on request. Place files are read on demand."""

    def __init__(self, data_dir: Path, worklists_dir: Path, research_file: Path):
        self.data_dir, self.worklists_dir, self.research_file = data_dir, worklists_dir, research_file
        self.load()

    def load(self):
        meta_path, index_path = self.data_dir / "meta.json", self.data_dir / "facilities.geojson"
        if not meta_path.exists() or not index_path.exists():
            raise RuntimeError(f"no export in {self.data_dir}: run `python export_site.py` first")
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        fc = json.loads(index_path.read_text(encoding="utf-8"))
        self.places = []
        for f in fc["features"]:
            lon, lat = f["geometry"]["coordinates"]
            self.places.append({**f["properties"], "lon": lon, "lat": lat})
        self.by_id = {p["facility_id"]: p for p in self.places}
        self.research = json.loads(self.research_file.read_text(encoding="utf-8")) if self.research_file.exists() else {}
        self.detail.cache_clear()

    @lru_cache(maxsize=2048)
    def detail(self, facility_id: str) -> dict | None:
        if facility_id not in self.by_id:
            return None
        path = self.data_dir / "place" / f"{facility_id}.json"
        if not path.exists():
            return None
        d = json.loads(path.read_text(encoding="utf-8"))
        p = self.by_id[facility_id]
        return {**d, "lon": p["lon"], "lat": p["lat"]}

    @property
    def stale(self) -> bool:
        exp = self.meta.get("expires")
        return bool(exp) and date.today().isoformat() > exp


def _env_path(name, default):
    v = os.environ.get(name)
    return Path(v) if v else ROOT / default


@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store(_env_path("SDFOOD_DATA_DIR", "data/site"), _env_path("SDFOOD_WORKLISTS_DIR", "data/worklists"),
                 _env_path("SDFOOD_RESEARCH_FILE", "data/research_results.json"))


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="One of the keys in SDFOOD_API_KEYS.")


def require_key(key: str | None = Security(api_key_header)):
    keys = [k.strip() for k in os.environ.get("SDFOOD_API_KEYS", "").split(",") if k.strip()]
    if not keys:
        raise HTTPException(503, "No API keys are configured (set SDFOOD_API_KEYS); data is not served without one.")
    if not key or not any(secrets.compare_digest(key, k) for k in keys):
        raise HTTPException(401, "A valid X-API-Key header is required.")
    return key


# ── response shapes (for the docs) ────────────────────────────────────────────────────

class Grade(BaseModel):
    model_config = ConfigDict(extra="allow")
    grade: str = Field(description="The letter on the County's card in the window")
    score: int | None = None
    date: str
    replaced: dict | None = Field(None, description="The routine B or C a re-grade replaced, if any")


class Facility(BaseModel):
    model_config = ConfigDict(extra="allow")
    facility_id: str = Field(description="The County's permit record id; the key for every lookup")
    name: str
    address: str
    facility_type: str = Field(description="restaurant, limited (limited-preparation food service) or market")
    council_district: int | None
    last_visit: dict | None
    grade: Grade | None
    flags: list[str] = Field(description="Record facts from the 12 months before the last visit: major, closed, bc, "
                                         "repeat, and a theme key for each theme with a major violation")
    band: str | None = Field(None, description="The published rule's band, when the place is in one")
    points: int | None = None
    lon: float
    lat: float


class FacilityPage(BaseModel):
    total: int
    offset: int
    limit: int
    stale: bool = Field(description="True once the data is past its expiry date: refresh the export")
    items: list[Facility]


class BandStat(BaseModel):
    band: str
    min_points: int | None
    max_points: int | None
    places_now: int
    rate: float | None = Field(description="Share that had a major violation at their next routine inspection, in the backtest")
    lift: float | None = Field(description="That rate divided by the rate for restaurants below the bands")


class Summary(BaseModel):
    model_config = ConfigDict(extra="allow")
    run: str
    mode: str
    generated: str
    inspections_through: str
    expires: str | None
    stale: bool
    places: int
    source: dict
    rule: str | None
    rule_items: list[dict]
    bands: list[BandStat]
    rest_rate: float | None


class District(BaseModel):
    council_district: int
    places: int
    in_bands: dict[str, int]
    with_major_last_year: int
    closed_for_health_hazard_last_year: int
    b_or_c_last_year: int


class WorklistRow(BaseModel):
    model_config = ConfigDict(extra="allow")
    facility_id: str
    name: str
    rule_order: int


# ── the app ───────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="San Diego Food Inspection API",
    version="1.0.0",
    description=(
        "For City of San Diego staff: every listed restaurant and market in the City with the County's inspection "
        "record, the published scoring rule's points and band, council-district summaries, and monthly worklists.\n\n"
        "Send your key in the `X-API-Key` header (the **Authorize** button above). Data: the County of San Diego's "
        "published inspection results (SD Food Info) and SANDAG council districts. Independent student project by "
        "Chenhao Zhang and Ayan Pendharkar; not affiliated with or endorsed by the County of San Diego."
    ),
    openapi_tags=[
        {"name": "facilities", "description": "Search and look up places"},
        {"name": "districts", "description": "Council-district summaries"},
        {"name": "worklists", "description": "Monthly worklists per council district"},
        {"name": "results", "description": "The rule and what it has shown"},
        {"name": "service", "description": "Health and reload"},
    ],
)
_origins = [o.strip() for o in os.environ.get("SDFOOD_CORS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["GET", "POST"], allow_headers=["X-API-Key"])


@app.middleware("http")
async def stale_header(request: Request, call_next):
    response = await call_next(request)
    try:
        if get_store().stale:
            response.headers["X-Data-Stale"] = "true"
    except RuntimeError:
        pass
    return response


def _filter(store: Store, district, band, kind, flag, q):
    items = store.places
    if district:
        items = [p for p in items if p.get("council_district") in district]
    if band:
        items = [p for p in items if p.get("band") in band]
    if kind:
        items = [p for p in items if p.get("facility_type") in kind]
    if flag:
        items = [p for p in items if all(f in (p.get("flags") or []) for f in flag)]
    if q:
        terms = q.lower().split()
        items = [p for p in items if all(t in f"{p['name']} {p['address']}".lower() for t in terms)]
    return items


def _sort(items, sort):
    if sort == "points":
        return sorted(items, key=lambda p: (-(p.get("points") or -1), p["name"]))
    if sort == "band":
        return sorted(items, key=lambda p: (int(p["band"]) if p.get("band") else 99, p["name"]))
    return sorted(items, key=lambda p: p["name"])


@app.get("/health", tags=["service"], summary="Is the service up, and which export and image is it serving?")
def health():
    build = os.environ.get("SDFOOD_BUILD") or None  # stamped into the image by deploy_api.py
    try:
        s = get_store()
        return {"status": "ok", "run": s.meta.get("run"), "inspections_through": s.meta.get("inspections_through"),
                "stale": s.stale, "places": len(s.places), "build": build}
    except RuntimeError as e:
        return {"status": "no data", "detail": str(e), "build": build}


@app.get("/v1/summary", response_model=Summary, tags=["results"], dependencies=[Depends(require_key)],
         summary="The export, the published rule and its bands")
def summary():
    s = get_store()
    m, card = s.meta, s.meta.get("card") or {}
    rest = (card.get("rest") or {}).get("rate")
    bands = [BandStat(band=b["band"], min_points=b.get("min_points"), max_points=b.get("max_points"),
                      places_now=b.get("places_now", 0), rate=b.get("rate"),
                      lift=round(b["rate"] / rest, 2) if b.get("rate") and rest else None) for b in card.get("bands", [])]
    return Summary(run=m["run"], mode=m.get("mode", "bands"), generated=m["generated"],
                   inspections_through=m["inspections_through"], expires=m.get("expires"), stale=s.stale,
                   places=len(s.places), source=m.get("source", {}), rule=card.get("rule"),
                   rule_items=card.get("items", []), bands=bands, rest_rate=rest)


@app.get("/v1/results", tags=["results"], dependencies=[Depends(require_key)],
         summary="Headline results, as the City would quote them")
def results():
    """The published rule's band rates and lift over other restaurants (backtest), and the research
    model's head start within a district's month, when data/research_results.json is present."""
    s = get_store()
    card = s.meta.get("card") or {}
    rest = (card.get("rest") or {}).get("rate")
    out = {"backtest_as_of": (s.meta.get("catch_run") or {}).get("as_of"),
           "bands": [{"band": b["band"], "rate": b.get("rate"), "interval": b.get("interval"),
                      "lift_over_other_restaurants": round(b["rate"] / rest, 2) if b.get("rate") and rest else None}
                     for b in card.get("bands", [])],
           "other_restaurants_rate": rest,
           "grade_context": s.meta.get("grade_context")}
    if s.research:
        out["research"] = s.research
    return out


@app.get("/v1/facilities", response_model=FacilityPage, tags=["facilities"], dependencies=[Depends(require_key)],
         summary="Search and filter places")
def facilities(district: list[int] | None = Query(None, description="Council district(s), 1-9"),
               band: list[str] | None = Query(None, description="Band(s), e.g. 1"),
               kind: list[Literal["restaurant", "limited", "market"]] | None = Query(None),
               flag: list[str] | None = Query(None, description=f"Record facts, all required: {', '.join(FLAGS)} or a theme key"),
               q: str | None = Query(None, description="Words in the name or address"),
               sort: Literal["name", "band", "points"] = "band",
               limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    s = get_store()
    items = _sort(_filter(s, district, band, kind, flag, q), sort)
    return FacilityPage(total=len(items), offset=offset, limit=limit, stale=s.stale, items=items[offset:offset + limit])


@app.get("/v1/facilities/{facility_id}", tags=["facilities"], dependencies=[Depends(require_key)],
         summary="One place: its full County record and, if banded, its points worksheet")
def facility(facility_id: str):
    d = get_store().detail(facility_id)
    if d is None:
        raise HTTPException(404, f"{facility_id} is not in this export")
    return d


@app.get("/v1/export.csv", tags=["facilities"], dependencies=[Depends(require_key)], response_class=PlainTextResponse,
         summary="The filtered list as CSV")
def export_csv(district: list[int] | None = Query(None), band: list[str] | None = Query(None),
               kind: list[Literal["restaurant", "limited", "market"]] | None = Query(None),
               flag: list[str] | None = Query(None), q: str | None = None):
    s = get_store()
    cols = ["facility_id", "name", "address", "facility_type", "council_district", "band", "points", "grade",
            "grade_date", "last_visit_date", "last_visit_type", "flags", "lon", "lat"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols + ["list_run", "list_expires"])
    for p in _sort(_filter(s, district, band, kind, flag, q), "band"):
        g, lv = p.get("grade") or {}, p.get("last_visit") or {}
        w.writerow([p["facility_id"], p["name"], p["address"], p["facility_type"], p.get("council_district"),
                    p.get("band") or "", p.get("points") if p.get("points") is not None else "", g.get("grade", ""),
                    g.get("date", ""), lv.get("date", ""), lv.get("type", ""), " ".join(p.get("flags") or []),
                    p["lon"], p["lat"], s.meta["run"], s.meta.get("expires") or ""])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="sd-food-{s.meta["run"]}.csv"'})


def _district_summary(s: Store, n: int) -> District:
    items = [p for p in s.places if p.get("council_district") == n]
    in_bands: dict[str, int] = {}
    for p in items:
        if p.get("band"):
            in_bands[p["band"]] = in_bands.get(p["band"], 0) + 1
    has = lambda f: sum(f in (p.get("flags") or []) for p in items)
    return District(council_district=n, places=len(items), in_bands=dict(sorted(in_bands.items())),
                    with_major_last_year=has("major"), closed_for_health_hazard_last_year=has("closed"),
                    b_or_c_last_year=has("bc"))


@app.get("/v1/districts", response_model=list[District], tags=["districts"], dependencies=[Depends(require_key)],
         summary="Every council district at a glance")
def districts():
    s = get_store()
    ns = sorted({p["council_district"] for p in s.places if p.get("council_district")})
    return [_district_summary(s, n) for n in ns]


@app.get("/v1/districts/{n}", tags=["districts"], dependencies=[Depends(require_key)],
         summary="One council district: its summary and its places in bands")
def district(n: int):
    s = get_store()
    if not any(p.get("council_district") == n for p in s.places):
        raise HTTPException(404, f"no places in council district {n}")
    banded = _sort([p for p in s.places if p.get("council_district") == n and p.get("band")], "band")
    return {"summary": _district_summary(s, n), "in_bands": banded}


def _worklist_path(s: Store, month: str, n: int) -> Path:
    return s.worklists_dir / month / f"district-{n}.csv"


@app.get("/v1/worklists", tags=["worklists"], dependencies=[Depends(require_key)],
         summary="Months with worklists")
def worklists():
    s = get_store()
    if not s.worklists_dir.exists():
        return []
    out = []
    for d in sorted(p for p in s.worklists_dir.iterdir() if p.is_dir()):
        man = d / "manifest.json"
        out.append({"month": d.name, "districts": sorted(int(f.stem.split("-")[1]) for f in d.glob("district-*.csv")),
                    "manifest": json.loads(man.read_text(encoding="utf-8")) if man.exists() else None})
    return out


@app.get("/v1/worklists/{month}/districts/{n}", tags=["worklists"], dependencies=[Depends(require_key)],
         summary="A council district's worklist for a month (JSON, or CSV with format=csv)")
def worklist(month: str, n: int, format: Literal["json", "csv"] = "json"):
    s = get_store()
    path = _worklist_path(s, month, n)
    if not path.exists():
        raise HTTPException(404, f"no worklist for district {n} in {month} (run `python export_worklist.py`)")
    text = path.read_text(encoding="utf-8")
    if format == "csv":
        return Response(text, media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="worklist-{month}-district-{n}.csv"'})
    rows = list(csv.DictReader(io.StringIO(text)))
    for r in rows:                           # numbers as numbers, blanks as null
        for k in ("rule_order", "rule_points", "last_routine_score", "mean_routine_score_12m"):
            v = (r.get(k) or "").strip()
            if k in r:
                try:
                    r[k] = int(v) if v.lstrip("-").isdigit() else float(v) if v else None
                except ValueError:
                    pass
    return {"month": month, "council_district": n, "rows": rows}


@app.post("/v1/admin/reload", tags=["service"], dependencies=[Depends(require_key)],
          summary="Reload the export and worklists from disk after a refresh")
def reload():
    s = get_store()
    s.load()
    return {"status": "reloaded", "run": s.meta.get("run"), "places": len(s.places)}
