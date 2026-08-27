"""
P1.01 — Nepal experiment calendar generator.

Outputs config/nepal_calendar.csv with 14 rows:
  2026-07-20 through 2026-08-02 (daily, 00Z).

Columns:
  init_date          YYYY-MM-DD
  slug               YYYYMMDD
  init_datetime_utc  ISO-8601 00:00:00Z
  ic_minus6h_utc     init - 6h (Aurora requires t-6h IC step)
  ic_plus0h_utc      init + 0h (= init_datetime_utc)
  forecast_end_utc   init + 168h
  era5t              TRUE (all inits require ERA5T; stable ERA5 ends ~2026-04-30)
  valid_scope        TRUE
  notes
"""

from __future__ import annotations

import csv
import datetime
import pathlib

ROOT     = pathlib.Path(__file__).parent.parent
OUT_PATH = ROOT / "config" / "nepal_calendar.csv"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

UTC = datetime.timezone.utc
START = datetime.date(2026, 7, 20)
END   = datetime.date(2026, 8,  2)

FIELDNAMES = [
    "init_date", "slug", "init_datetime_utc",
    "ic_minus6h_utc", "ic_plus0h_utc",
    "forecast_end_utc", "era5t", "valid_scope", "notes",
]

rows = []
d = START
while d <= END:
    init_dt   = datetime.datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=UTC)
    ic_m6     = init_dt - datetime.timedelta(hours=6)
    fc_end    = init_dt + datetime.timedelta(hours=168)
    rows.append({
        "init_date":         d.isoformat(),
        "slug":              d.strftime("%Y%m%d"),
        "init_datetime_utc": init_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ic_minus6h_utc":    ic_m6.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ic_plus0h_utc":     init_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "forecast_end_utc":  fc_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "era5t":             "TRUE",
        "valid_scope":       "TRUE",
        "notes":             "ERA5T IC; within ARCO availability (confirmed through 2026-08-15)",
    })
    d += datetime.timedelta(days=1)

with open(OUT_PATH, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)

print(f"Written: {OUT_PATH}")
print(f"  Rows: {len(rows)}")
print(f"  First: {rows[0]['init_datetime_utc']}")
print(f"  Last:  {rows[-1]['init_datetime_utc']}")
print(f"  Last forecast ends: {rows[-1]['forecast_end_utc']}")
