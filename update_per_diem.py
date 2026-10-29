#!/usr/bin/env python3
"""Download GSA's continental-US per diem tables into data/per_diem_fy<YYYY>.json.

Run once a year after GSA publishes the new rates (usually mid-August, taking
effect Oct 1), and commit the new file:

    GSA_API_KEY=your-key python3 update_per_diem.py 2027
    GSA_API_KEY=your-key python3 update_per_diem.py 2026 2027

Fiscal year 2027 is Oct 1, 2026 - Sep 30, 2027. A free key comes from the
signup form at https://open.gsa.gov/api/perdiem/ . Without GSA_API_KEY this
falls back to the shared DEMO_KEY, which only allows ~10 requests an hour
(each fiscal year costs 2 requests).
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://api.gsa.gov/travel/perdiem/v2/rates/conus"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
OUT_DIR = Path(__file__).parent / "data"


def fetch(path, key):
    req = urllib.request.Request(f"{BASE}/{path}", headers={"x-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            sys.exit("GSA says the API key is over its rate limit. Wait an hour, or use your own GSA_API_KEY.")
        if e.code == 403:
            sys.exit("GSA rejected the API key (403). Check GSA_API_KEY.")
        raise


def build(fy, key):
    lodging = fetch(f"lodging/{fy}", key)
    zipcodes = fetch(f"zipcodes/{fy}", key)

    rows = []
    for r in lodging:
        rows.append({
            "did": str(r["DID"]),
            "city": (r.get("City") or "").strip(),
            "state": (r.get("State") or "").strip(),
            "county": (r.get("County") or "").strip(),
            "meals": int(float(r["Meals"])),
            "lodging": [int(float(r[m])) for m in MONTHS],
        })

    zips = {str(z["Zip"]).zfill(5): str(z["DID"]) for z in zipcodes}
    return {"fiscal_year": fy, "rows": rows, "zips": zips}


def main():
    years = [int(a) for a in sys.argv[1:]]
    if not years:
        sys.exit(__doc__)
    key = os.environ.get("GSA_API_KEY")
    if not key:
        print("GSA_API_KEY isn't set -- using DEMO_KEY (about 10 requests/hour).", file=sys.stderr)
        key = "DEMO_KEY"

    OUT_DIR.mkdir(exist_ok=True)
    for fy in years:
        data = build(fy, key)
        path = OUT_DIR / f"per_diem_fy{fy}.json"
        path.write_text(json.dumps(data, separators=(",", ":")))
        print(f"FY{fy}: {len(data['rows'])} localities, {len(data['zips'])} ZIP codes -> {path.name} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
