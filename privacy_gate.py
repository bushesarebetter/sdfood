"""The gate every public, committed artifact passes: aggregates only, no facility-level rows.

Why it exists: the committed dashboard.html carried one row per active facility (type, model
risk to 0.1, banded history, months since the last visit to 0.1). Its docstring called that
de-identified, but 80% of the 15,647 rows were unique on the fields shown, and SD Food Info
publishes each facility's name and inspection dates, so a row links back to a named business.
docs/PUBLISHING.md already says real exports never enter git; this makes the dashboard obey it.

    python privacy_gate.py dashboard.html      # exit 1 and list the problems if it fails
"""
import json
import re
import sys

#: Keys that only make sense for one facility (or one inspection).
FORBIDDEN_KEYS = {"worklist", "facility_id", "business_id", "custom_id", "inspection_id", "name", "address",
                  "city", "lat", "lng", "lon", "latitude", "longitude", "zip", "months_since", "days_since",
                  "last_visit", "prior_band", "major_band", "due_estimate", "rule_points"}
MAX_RECORDS = 60        # a longer list, or a dict with more keys, is treated as row-level data
MIN_CELL = 11           # published counts below this are suppressed (shown as "<11")
#: Keys whose integer values are counts of facilities or inspections, held to MIN_CELL.
COUNT_KEYS = {"n", "count", "facilities", "due", "with_prior_major", "active", "places", "inspections", "majors"}


def violations(obj, path="$"):
    out = []
    if isinstance(obj, dict):
        if len(obj) > MAX_RECORDS:
            out.append(f"{path}: a mapping of {len(obj)} entries looks like row-level data (max {MAX_RECORDS})")
        for k, v in list(obj.items())[:MAX_RECORDS + 1]:
            if str(k).lower() in FORBIDDEN_KEYS:
                out.append(f"{path}.{k}: facility-level field")
            if (str(k).lower() in COUNT_KEYS and isinstance(v, int) and not isinstance(v, bool)
                    and 0 < v < MIN_CELL):
                out.append(f"{path}.{k}={v}: a published count below {MIN_CELL}")
            out += violations(v, f"{path}.{k}")
    elif isinstance(obj, list):
        if len(obj) > MAX_RECORDS:           # rows, column arrays or tuples: any long list is row-level
            out.append(f"{path}: {len(obj)} entries looks like row-level data (max {MAX_RECORDS})")
        for i, v in enumerate(obj[:MAX_RECORDS + 1]):
            out += violations(v, f"{path}[{i}]")
    return out


def check(payload):
    """Raise ValueError listing every problem; return the payload unchanged if it is clean."""
    v = violations(payload)
    if v:
        raise ValueError("public payload fails the privacy gate:\n  " + "\n  ".join(v[:25]))
    return payload


def dashboard_payload(html):
    """The JSON literal injected after the /*__DATA__*/ marker, or None if there is none."""
    m = re.search(r"/\*__DATA__\*/\s*(\{.*?\});\s*\n", html, re.S)
    return json.loads(m.group(1)) if m else None


def suppress(n):
    """A count as published: exact at MIN_CELL or above, zero as zero, otherwise None ("<11")."""
    n = int(n)
    return n if n == 0 or n >= MIN_CELL else None


if __name__ == "__main__":
    bad = 0
    for path in sys.argv[1:] or ["dashboard.html"]:
        p = dashboard_payload(open(path, encoding="utf-8").read())
        v = violations(p) if p is not None else []
        print(f"{path}: {'ok' if not v else f'{len(v)} problems'}")
        for line in v[:25]:
            print("  " + line)
        bad += bool(v)
    sys.exit(1 if bad else 0)
