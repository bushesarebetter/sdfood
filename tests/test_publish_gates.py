"""export_site.py publication gates: placeholder approvals, impossible cost ratios, unsafe ids,
the public operator field, and a publish that never writes into the git-tracked site."""
import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

import export_site as es
from test_export_site import good_approval

ROOT = Path(__file__).resolve().parents[1]
META = {"run": "forward_2026-09-20", "generated": "2026-10-02"}


def probs(today=None, **over):
    return "\n".join(es.check_approval({**good_approval(META, "abc"), **over}, "bands", META, "abc", today=today))


def test_the_reviewers_placeholder_approval_is_refused():
    assert probs() == ""
    assert "not an email" in probs(contact="@")
    assert "responsible_adult.contact" in probs(responsible_adult={"name": "C D", "contact": "x"})
    assert "more than 14 days before" in probs(date="1900-01-01")
    assert "in the future" in probs(today=date(2026, 9, 25))                       # signed 2026-10-01
    assert "legal_review.date` is not a date" in probs(legal_review={"reviewer": "E", "organization": "F", "date": "x", "scope": "all"})
    assert "more than a year before" in probs(county_informed={**good_approval(META, "abc")["county_informed"], "date": "0001-01-01"})
    ind = {"name": "x", "affiliation": "x", "date": "x"}
    assert "independent_reviewer.date` is not a date" in probs(cost_ratio=0.5, independent_reviewer=ind)


@pytest.mark.parametrize("ratio", [0, -0.5, -1, 0.1, 50])
def test_cost_ratios_outside_the_range_are_refused_and_name_nothing(ratio):
    assert "outside 0.25 to 10" in probs(cost_ratio=ratio,
                                         independent_reviewer={"name": "X", "affiliation": "Y", "date": "2026-09-30"})
    rows = [{"band": "1", "interval": [0.3, 0.5]}, {"band": "2", "interval": [0.1, 0.2]}]
    if ratio <= 0:
        assert es.named_bands(rows, ratio) == []            # 0 named every band; -1 divided by zero


def test_unsafe_facility_ids_never_become_file_names(tmp_path):
    fc = {"type": "FeatureCollection", "features": []}
    with pytest.raises(ValueError, match="not safe file names"):
        es.write_export(tmp_path / "out", fc, {"../../escape": {}}, {"run": "r"})
    assert not (tmp_path / "escape.json").exists()
    es.write_export(tmp_path / "ok", fc, {"DEH2024-FFPP-000001": {}}, {"run": "r"})
    assert (tmp_path / "ok" / "place" / "DEH2024-FFPP-000001.json").exists()


def test_publish_stages_outside_git():
    assert es.SITE_DATA == ROOT / "data" / "site-publish"
    ignored = subprocess.run(["git", "check-ignore", "-q", str(es.SITE_DATA / "meta.json")], cwd=ROOT)
    assert ignored.returncode == 0, "the staged real export is git-ignored"
    for f in ("docs/PUBLISH_APPROVAL.json", "docs/notices/forward_2026-09-20.csv", "docs/holds.json"):
        assert subprocess.run(["git", "check-ignore", "-q", f], cwd=ROOT).returncode == 0, f
