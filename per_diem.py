"""Federal (GSA) per diem lookups for the continental US, served from rate
tables saved in data/per_diem_fy<YYYY>.json by update_per_diem.py.

GSA only changes these rates once a year (Oct 1), and PythonAnywhere's free
tier can't reach api.gsa.gov at runtime, so the tables are downloaded once
and looked up locally instead of calling the API on every search.
"""
import datetime
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# Alaska, Hawaii and the territories are priced on GSA's separate non-CONUS
# schedule, which these tables don't include.
NON_CONUS_STATES = {"AK", "HI", "PR", "GU", "VI", "AS", "MP"}
NON_CONUS_ZIP_PREFIXES = ("006", "007", "008", "009", "967", "968", "969", "995", "996", "997", "998", "999")

MONTHS = [
    ("Jan", "January"), ("Feb", "February"), ("Mar", "March"), ("Apr", "April"),
    ("May", "May"), ("Jun", "June"), ("Jul", "July"), ("Aug", "August"),
    ("Sep", "September"), ("Oct", "October"), ("Nov", "November"), ("Dec", "December"),
]

STANDARD_CITY = "standard rate"

_datasets = {}


class PerDiemError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def fiscal_year(d):
    """The federal fiscal year runs Oct 1 - Sep 30 and is named for the
    calendar year it ends in (Oct 29, 2026 falls in FY2027)."""
    return d.year + 1 if d.month >= 10 else d.year


def available_years():
    years = []
    for path in DATA_DIR.glob("per_diem_fy*.json"):
        m = re.fullmatch(r"per_diem_fy(\d{4})\.json", path.name)
        if m:
            years.append(int(m.group(1)))
    return sorted(years)


def _load(fy):
    if fy not in _datasets:
        with open(DATA_DIR / f"per_diem_fy{fy}.json") as f:
            _datasets[fy] = json.load(f)
    return _datasets[fy]


def _pick_year(wanted):
    """The requested fiscal year if we have it, otherwise the closest one we
    do (so the app keeps working past Oct 1 until the tables are refreshed)."""
    years = available_years()
    if not years:
        raise PerDiemError("Per diem rates haven't been loaded into this app yet.", 503)
    return min(years, key=lambda y: (abs(y - wanted), -y))


def _norm_city(s):
    s = (s or "").lower().replace(".", "").replace("'", " ").replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


def _standard_row(data):
    for row in data["rows"]:
        if row["did"] == "0":
            return row
    for row in data["rows"]:
        if _norm_city(row["city"]) == STANDARD_CITY:
            return row
    raise PerDiemError("Per diem rates are missing the standard rate.", 503)


def _parse_query(q):
    q = (q or "").strip()
    if re.fullmatch(r"\d{5}(-\d{4})?", q):
        return "zip", q[:5], None
    m = re.fullmatch(r"(.+?)[\s,]+([A-Za-z]{2})", q)
    if m:
        return "city", m.group(1).strip(), m.group(2).upper()
    raise PerDiemError("Enter a 5-digit ZIP code, or a city and 2-letter state like \"Dayton, OH\".")


def _find_row(data, kind, key, state):
    """Returns (row, matched). matched is False when we fell back to the
    standard rate because the place isn't a specially-priced locality."""
    if kind == "zip":
        # The ZIP table covers every continental ZIP (standard-rate ones map
        # to locality "0"), so a ZIP that's absent isn't a standard-rate
        # place -- it isn't a continental ZIP at all.
        did = data["zips"].get(key)
        if did is None:
            raise PerDiemError(f"Couldn't find ZIP code {key} among continental U.S. ZIP codes.", 404)
        for row in data["rows"]:
            if row["did"] == did:
                return row, True
        return _standard_row(data), False

    # Washington DC is a single locality, whatever the city is called.
    if state == "DC":
        for row in data["rows"]:
            if row["state"] == "DC" and row["did"] != "0":
                return row, True

    wanted = _norm_city(key)
    for row in data["rows"]:
        if row["state"] != state or row["did"] == "0":
            continue
        if wanted in (_norm_city(part) for part in row["city"].split("/")):
            return row, True
    return _standard_row(data), False


def lookup(q, date_str=None):
    try:
        d = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
    except ValueError:
        raise PerDiemError("Date must look like 2026-10-29.")

    kind, key, state = _parse_query(q)
    if kind == "zip" and key.startswith(NON_CONUS_ZIP_PREFIXES):
        raise PerDiemError("Alaska, Hawaii and U.S. territories use GSA's separate non-continental rates, which aren't included here.", 422)
    if kind == "city" and state in NON_CONUS_STATES:
        raise PerDiemError("Alaska, Hawaii and U.S. territories use GSA's separate non-continental rates, which aren't included here.", 422)

    wanted_fy = fiscal_year(d)
    fy = _pick_year(wanted_fy)
    data = _load(fy)
    row, matched = _find_row(data, kind, key, state)

    is_standard = _norm_city(row["city"]) == STANDARD_CITY
    month_idx = d.month - 1
    meals = row["meals"]

    notes = []
    if fy != wanted_fy:
        notes.append(f"Showing FY{fy} rates; FY{wanted_fy} rates haven't been loaded yet.")
    if not matched and kind == "city":
        notes.append(f"{key.title()}, {state} isn't a listed rate area, so the standard rate is shown. Some towns are covered by a larger county or metro rate, so use the place's ZIP code to be sure.")

    return {
        "query": (q or "").strip(),
        "location": "Standard rate" if is_standard else row["city"],
        "county": row.get("county") or "",
        "state": row.get("state") or "",
        "is_standard": is_standard,
        "month": MONTHS[month_idx][1],
        "lodging": row["lodging"][month_idx],
        "meals": meals,
        "first_last_day": round(meals * 0.75, 2),
        "fiscal_year": fy,
        "notes": notes,
        "months": [
            {"short": short, "long": long_name, "lodging": row["lodging"][i]}
            for i, (short, long_name) in enumerate(MONTHS)
        ],
    }
