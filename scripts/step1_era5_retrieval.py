"""
Step 1 ERA5 Verification Archive Retrieval.

Fetches ERA5 reanalysis from ARCO for all 162 valid initialisations,
9 evaluation lead times each, over Myanmar bbox (9–29°N, 92–102°E).

Precipitation semantics (CONFIRMED 2026-08-22):
  ARCO total_precipitation = 1h accumulated depth in metres, ending at timestamp T.
  Conversion: precip_mmhr = max(0, tp_m × 1000)  [NOT ÷ 6]

Variables retrieved:
  2m_temperature           → t2m_K   (K)
  10m_u_component_of_wind → u10m    (m/s)
  10m_v_component_of_wind → v10m    (m/s)
  total_precipitation      → precip_mmhr (mm/hr = 1h depth in mm)

Storage: era5_verification/{init_slug}.nc
Manifest: era5_verification/manifest.json (written after every init)
Resume safety: skip already-valid files; write to .tmp then rename.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import time
import warnings
from pathlib import Path

import gcsfs
import numpy as np
import xarray as xr
import zarr

warnings.filterwarnings("ignore")

# ── Configuration ─────────────────────────────────────────────────────────────
ARCO_URL = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
LAT_MIN, LAT_MAX = 9.0, 29.0
LON_MIN, LON_MAX = 92.0, 102.0
EVAL_LEADS = [6, 12, 24, 48, 72, 96, 120, 144, 168]

OUT_DIR = Path(__file__).parent.parent / "era5_verification"
MANIFEST_PATH = OUT_DIR / "manifest.json"

# Correct conversion constant (confirmed 2026-08-22)
# tp is 1h accumulation in metres → multiply by 1000 to get mm (= mm/hr for 1h window)
TP_SCALE = 1000.0  # m → mm/hr (for 1h window)

# ── Load 162 valid init slugs from experiment calendar ────────────────────────
def load_inits() -> list[str]:
    cal_path = Path(__file__).parent.parent / "config" / "experiment_calendar.csv"
    import csv
    inits = []
    with open(cal_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["in_valid_scope"].strip().upper() == "TRUE":
                inits.append(row["init_date"])
    return sorted(inits)


# ── Validate an already-written NC file ──────────────────────────────────────
def validate_nc(path: Path) -> tuple[bool, str]:
    """Returns (ok, reason). Checks structure, shape, no-NaN for non-precip."""
    if not path.exists():
        return False, "file does not exist"
    if path.stat().st_size == 0:
        return False, "zero bytes"
    try:
        ds = xr.open_dataset(path)
        # Check dims
        if ds.sizes.get("lead_time") != len(EVAL_LEADS):
            ds.close()
            return False, f"lead_time dim = {ds.sizes.get('lead_time')}, expected {len(EVAL_LEADS)}"
        if ds.sizes.get("lat") != 81:
            ds.close()
            return False, f"lat dim = {ds.sizes.get('lat')}, expected 81"
        if ds.sizes.get("lon") != 41:
            ds.close()
            return False, f"lon dim = {ds.sizes.get('lon')}, expected 41"
        # Check required variables
        for var in ("t2m_K", "u10m", "v10m", "precip_mmhr"):
            if var not in ds:
                ds.close()
                return False, f"missing variable: {var}"
        # Check non-NaN for t2m/wind (precip may be NaN if fetch failed)
        for var in ("t2m_K", "u10m", "v10m"):
            if np.any(np.isnan(ds[var].values)):
                ds.close()
                return False, f"NaN found in {var}"
        ds.close()
        return True, "ok"
    except Exception as e:
        return False, str(e)


# ── Fetch ERA5 for one init ───────────────────────────────────────────────────
def fetch_one_init(
    init_date: str,
    arco_ds: xr.Dataset,
    out_dir: Path,
    retrieval_ts: str,
) -> dict:
    """
    Fetch ERA5 for one init_date (YYYY-MM-DD, 00Z) at all 9 eval leads.
    Returns a result dict suitable for the manifest.
    """
    slug = init_date.replace("-", "") + "_0000"
    out_path = out_dir / f"{slug}.nc"
    tmp_path = out_dir / f"{slug}.nc.tmp"

    # Skip if already valid
    ok, reason = validate_nc(out_path)
    if ok:
        return {"slug": slug, "status": "skipped", "reason": "already valid"}

    # Remove stale tmp
    if tmp_path.exists():
        tmp_path.unlink()

    init_dt = datetime.datetime(int(init_date[:4]), int(init_date[5:7]), int(init_date[8:10]),
                                0, 0, 0, tzinfo=datetime.timezone.utc)
    valid_times = [init_dt + datetime.timedelta(hours=h) for h in EVAL_LEADS]
    valid_np = [np.datetime64(vt.replace(tzinfo=None), "ns") for vt in valid_times]

    n_lead = len(EVAL_LEADS)
    lat_slice = slice(LAT_MAX, LAT_MIN)  # N→S in ARCO
    lon_slice = slice(LON_MIN, LON_MAX)

    t2m_K     = np.full((n_lead, 81, 41), np.nan, dtype=np.float32)
    u10m      = np.full((n_lead, 81, 41), np.nan, dtype=np.float32)
    v10m      = np.full((n_lead, 81, 41), np.nan, dtype=np.float32)
    precip    = np.full((n_lead, 81, 41), np.nan, dtype=np.float32)

    errors = []

    # Batch-fetch all 9 leads at once (7× faster than per-lead fetching)
    try:
        batch = arco_ds[
            ["2m_temperature", "10m_u_component_of_wind",
             "10m_v_component_of_wind", "total_precipitation"]
        ].sel(
            time=np.array(valid_np),
            latitude=lat_slice,
            longitude=lon_slice,
        ).compute()  # force download of all chunks at once

        t2m_K  = batch["2m_temperature"].values.astype(np.float32)
        u10m   = batch["10m_u_component_of_wind"].values.astype(np.float32)
        v10m   = batch["10m_v_component_of_wind"].values.astype(np.float32)
        tp_raw = batch["total_precipitation"].values.astype(np.float64)
        precip = np.maximum(0.0, tp_raw * TP_SCALE).astype(np.float32)

    except Exception as e:
        errors.append(f"batch fetch failed: {e}")
        # Fall back to per-lead fetching
        for li, (vt_np_i, h) in enumerate(zip(valid_np, EVAL_LEADS)):
            try:
                sl = arco_ds.sel(time=vt_np_i, latitude=lat_slice, longitude=lon_slice)
                t2m_K[li]  = sl["2m_temperature"].values.astype(np.float32)
                u10m[li]   = sl["10m_u_component_of_wind"].values.astype(np.float32)
                v10m[li]   = sl["10m_v_component_of_wind"].values.astype(np.float32)
                tp_m = sl["total_precipitation"].values.astype(np.float64)
                precip[li] = np.maximum(0.0, tp_m * TP_SCALE).astype(np.float32)
            except Exception as e2:
                errors.append(f"lead {h}h fallback: {e2}")

    # Retrieve lat/lon from ARCO for coord assignment
    lat_vals = arco_ds.coords["latitude"].sel(latitude=lat_slice).values.astype(np.float32)
    lon_vals = arco_ds.coords["longitude"].sel(longitude=lon_slice).values.astype(np.float32)

    # Build Dataset
    dims = ["lead_time", "lat", "lon"]
    ds_out = xr.Dataset(
        {
            "t2m_K": (dims, t2m_K, {"units": "K", "long_name": "2m temperature (ERA5)"}),
            "u10m":  (dims, u10m,  {"units": "m s-1", "long_name": "10m u-wind (ERA5)"}),
            "v10m":  (dims, v10m,  {"units": "m s-1", "long_name": "10m v-wind (ERA5)"}),
            "precip_mmhr": (
                dims, precip,
                {
                    "units": "mm hr-1",
                    "long_name": "Precipitation (ERA5 1h accum → mm)",
                    "conversion": "total_precipitation_m * 1000; 1h window ending at valid_time",
                    "note": "CORRECT formula (1h, not 6h). R4 pipeline used ÷6 which was wrong.",
                },
            ),
        },
        coords={
            "lead_time": (["lead_time"], np.array(EVAL_LEADS, dtype=np.int32),
                          {"units": "hours", "note": "hours since init_time"}),
            "lat": (["lat"], lat_vals, {"units": "degrees_north"}),
            "lon": (["lon"], lon_vals, {"units": "degrees_east"}),
        },
        attrs={
            "init_time":        init_dt.isoformat(),
            "source":           "ERA5 reanalysis via ARCO",
            "arco_url":         ARCO_URL,
            "retrieval_time":   retrieval_ts,
            "project":          "myanmar-forecast-eval",
            "step1_version":    "2026-08-22",
            "precip_formula":   "max(0, total_precipitation_m * 1000); 1h window ending at valid_time",
            "precip_r4_note":   "R4 pipeline used * 1000 / 6 (wrong by factor 6); corrected here",
            "lat_convention":   "N to S (descending)",
            "lon_convention":   "W to E (ascending)",
            "fetch_errors":     "; ".join(errors) if errors else "none",
        },
    )

    # Write to tmp then rename (atomic)
    try:
        ds_out.to_netcdf(tmp_path)
        ok, reason = validate_nc(tmp_path)
        if ok:
            tmp_path.rename(out_path)
            return {
                "slug": slug,
                "status": "success",
                "size_bytes": out_path.stat().st_size,
                "fetch_errors": errors,
                "valid_time_range": f"{valid_times[0].isoformat()}Z to {valid_times[-1].isoformat()}Z",
            }
        else:
            tmp_path.unlink(missing_ok=True)
            return {"slug": slug, "status": "failed", "reason": f"validation failed: {reason}"}
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        return {"slug": slug, "status": "failed", "reason": str(e)}


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load or initialise manifest
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH) as f:
            manifest = json.load(f)
    else:
        manifest = {"results": {}, "retrieval_started": datetime.datetime.utcnow().isoformat() + "Z"}

    retrieval_ts = datetime.datetime.utcnow().isoformat() + "Z"

    # Load init list
    inits = load_inits()
    print(f"Total valid inits: {len(inits)}")

    # Open ARCO once (lazy)
    print("Opening ARCO dataset...")
    fs = gcsfs.GCSFileSystem(token="anon")
    arco_ds = xr.open_zarr(fs.get_mapper(ARCO_URL), consolidated=True, chunks=None)
    print("ARCO opened.")

    success = skipped = failed = 0
    t0_all = time.time()

    for i, init_date in enumerate(inits):
        slug = init_date.replace("-", "") + "_0000"
        # Fast skip if already marked success in manifest and file is valid
        if manifest["results"].get(slug, {}).get("status") == "success":
            out_path = OUT_DIR / f"{slug}.nc"
            ok, _ = validate_nc(out_path)
            if ok:
                skipped += 1
                if (i + 1) % 20 == 0:
                    print(f"  [{i+1}/{len(inits)}] {slug}: skipped (already valid)")
                continue

        t0 = time.time()
        result = fetch_one_init(init_date, arco_ds, OUT_DIR, retrieval_ts)
        elapsed = time.time() - t0
        result["elapsed_s"] = round(elapsed, 1)
        manifest["results"][slug] = result

        status = result["status"]
        if status == "success":
            success += 1
        elif status == "skipped":
            skipped += 1
        else:
            failed += 1

        print(f"  [{i+1}/{len(inits)}] {slug}: {status} ({elapsed:.1f}s)")

        # Write manifest after every init
        with open(MANIFEST_PATH, "w") as f:
            json.dump(manifest, f, indent=2)

    total_elapsed = time.time() - t0_all
    manifest["retrieval_completed"] = datetime.datetime.utcnow().isoformat() + "Z"
    manifest["summary"] = {
        "total": len(inits),
        "success": success,
        "skipped": skipped,
        "failed": failed,
        "elapsed_s": round(total_elapsed, 1),
    }
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDone: {success} new, {skipped} skipped, {failed} failed in {total_elapsed/60:.1f} min")
    print(f"Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
