"""
P1.03 — ARCO ERA5T access test for Nepal.

Tests:
  1. ARCO zarr store opens anonymously
  2. Time axis covers all 28 required IC timestamps
     (14 inits × 2 steps: t-6h and t+0h)
  3. Nepal bbox subset (26.0–30.5N, 80.0–88.5E) returns correct shape
  4. t2m values at one IC timestamp are non-NaN and physically plausible
  5. total_precipitation field is present and non-negative after conversion

No full ERA5T dataset download. Fetches one small test slice (19×35 grid,
1 timestamp) for structural validation only.

Outputs:
  results/nepal/validation/p1_arco_test.json
"""

from __future__ import annotations

import csv
import datetime
import json
import pathlib
import warnings

import gcsfs
import numpy as np
import xarray as xr

warnings.filterwarnings("ignore")

ROOT      = pathlib.Path(__file__).parent.parent
CAL_PATH  = ROOT / "config" / "nepal_calendar.csv"
OUT_DIR   = ROOT / "results" / "nepal" / "validation"
OUT_PATH  = OUT_DIR / "p1_arco_test.json"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ARCO_URL = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"

# Nepal domain
LAT_MIN, LAT_MAX = 26.0, 30.5
LON_MIN, LON_MAX = 80.0, 88.5

UTC = datetime.timezone.utc
PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

results = []

def check(name: str, status: str, detail: str = ""):
    results.append({"name": name, "status": status, "detail": detail})
    tag = f"[{status}]"
    print(f"  {tag:<6} {name}" + (f"\n         {detail}" if detail else ""))


# ── 1. Load calendar ──────────────────────────────────────────────────────
print("\n── 1. Loading calendar ──────────────────────────────────────────────────")
required_ic_times: list[datetime.datetime] = []
slugs: list[str] = []

with open(CAL_PATH) as f:
    for row in csv.DictReader(f):
        slug = row["slug"]
        slugs.append(slug)
        init_dt   = datetime.datetime.strptime(row["init_datetime_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        ic_minus6 = datetime.datetime.strptime(row["ic_minus6h_utc"],    "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        required_ic_times.extend([ic_minus6, init_dt])

n_required = len(required_ic_times)
check(f"Calendar loaded: {len(slugs)} slugs, {n_required} IC timestamps",
      PASS if len(slugs) == 14 else FAIL,
      f"IC range: {required_ic_times[0].isoformat()} → {required_ic_times[-1].isoformat()}")


# ── 2. Open ARCO store ────────────────────────────────────────────────────
print("\n── 2. Opening ARCO zarr store (anonymous) ───────────────────────────────")
fs = gcsfs.GCSFileSystem(token="anon")
try:
    store = fs.get_mapper(ARCO_URL)
    arco  = xr.open_zarr(store, consolidated=True)
    check("ARCO store opened", PASS, f"Variables: {len(arco.data_vars)}")
except Exception as e:
    check("ARCO store open", FAIL, str(e))
    print("\nFATAL: cannot continue without ARCO access.")
    json.dump({"status": "FAIL", "results": results}, open(OUT_PATH,"w"), indent=2)
    raise SystemExit(1)


# ── 3. Time axis coverage check ───────────────────────────────────────────
print("\n── 3. Checking time axis coverage for all 28 IC timestamps ─────────────")
arco_times = arco.time.values  # numpy datetime64 array

# Convert required times to numpy datetime64 for comparison
req_np = [np.datetime64(t.replace(tzinfo=None), "ns") for t in required_ic_times]

missing = []
present = []
for t_req, t_dt in zip(req_np, required_ic_times):
    if t_req in arco_times:
        present.append(t_dt.isoformat())
    else:
        missing.append(t_dt.isoformat())

if not missing:
    check(f"All {n_required} IC timestamps present in ARCO time axis", PASS,
          f"First: {present[0]}  Last: {present[-1]}")
else:
    check(f"IC timestamps in ARCO", FAIL if len(missing) > 2 else WARN,
          f"Missing {len(missing)}/{n_required}: {missing}")

# Report coverage summary per slug
print("  Per-init IC availability:")
for i, slug in enumerate(slugs):
    t0 = required_ic_times[2*i]    # t-6h
    t1 = required_ic_times[2*i+1]  # t+0h
    t0_ok = np.datetime64(t0.replace(tzinfo=None), "ns") in arco_times
    t1_ok = np.datetime64(t1.replace(tzinfo=None), "ns") in arco_times
    status_str = "OK" if (t0_ok and t1_ok) else ("t-6h MISSING" if not t0_ok else "t+0h MISSING")
    print(f"    {slug}  t-6h {t0.strftime('%Y-%m-%dT%H:%MZ')} {'✓' if t0_ok else '✗'}  "
          f"t+0h {t1.strftime('%Y-%m-%dT%H:%MZ')} {'✓' if t1_ok else '✗'}  → {status_str}")


# ── 4. Fetch one test slice — Nepal bbox at first IC timestamp ────────────
print("\n── 4. Fetching one test slice (t2m, 2026-07-20T00:00Z, Nepal bbox) ──────")
test_time = required_ic_times[1]   # first init t+0h = 2026-07-20T00:00Z
test_np   = np.datetime64(test_time.replace(tzinfo=None), "ns")

try:
    t2m_slice = arco["2m_temperature"].sel(
        time      = test_np,
        latitude  = slice(LAT_MAX, LAT_MIN),   # ARCO is N→S
        longitude = slice(LON_MIN, LON_MAX),
    ).compute()

    shape = t2m_slice.shape
    check(f"t2m slice shape: {shape}", PASS if shape == (19, 35) else FAIL,
          f"Expected (19, 35)")

    vals = t2m_slice.values
    n_nan = int(np.sum(np.isnan(vals)))
    check(f"No NaN in t2m slice ({n_nan} NaN)", PASS if n_nan == 0 else FAIL)

    t2m_min, t2m_max = float(np.nanmin(vals)), float(np.nanmax(vals))
    plausible = (260.0 <= t2m_min) and (t2m_max <= 330.0)
    check(f"t2m range plausible: {t2m_min:.2f}–{t2m_max:.2f} K",
          PASS if plausible else WARN,
          "Expected 260–330 K for Nepal July")

except Exception as e:
    check("t2m test slice fetch", FAIL, str(e))


# ── 5. total_precipitation field available ────────────────────────────────
print("\n── 5. Checking total_precipitation field ────────────────────────────────")
try:
    tp_slice = arco["total_precipitation"].sel(
        time      = test_np,
        latitude  = slice(LAT_MAX, LAT_MIN),
        longitude = slice(LON_MIN, LON_MAX),
    ).compute()

    tp_vals = tp_slice.values
    tp_mm   = np.maximum(0.0, tp_vals * 1000.0)

    check(f"total_precipitation field present: shape {tp_slice.shape}", PASS)
    check(f"tp converted: max = {float(np.nanmax(tp_mm)):.4f} mm/hr",
          PASS if float(np.nanmax(tp_mm)) < 200.0 else WARN,
          "After max(0, tp_m × 1000)")

except Exception as e:
    check("total_precipitation fetch", FAIL, str(e))


# ── Summary ───────────────────────────────────────────────────────────────
print("\n─────────────────────────────────────────────────────────────────────────")
passes = sum(1 for r in results if r["status"] == PASS)
warns  = sum(1 for r in results if r["status"] == WARN)
fails  = sum(1 for r in results if r["status"] == FAIL)
print(f"  {passes} PASS  {warns} WARN  {fails} FAIL")

output = {
    "test_utc":      datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "arco_url":      ARCO_URL,
    "domain":        {"lat_min": LAT_MIN, "lat_max": LAT_MAX,
                      "lon_min": LON_MIN, "lon_max": LON_MAX},
    "n_ic_times_required": n_required,
    "n_ic_times_missing":  len(missing),
    "missing_ic_times":    missing,
    "overall_status":      FAIL if fails else (WARN if warns else PASS),
    "results":             results,
}

with open(OUT_PATH, "w") as f:
    json.dump(output, f, indent=2)
print(f"  Written: {OUT_PATH}")

if fails:
    raise SystemExit(1)
