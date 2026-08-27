"""
P2 — ERA5T Initial Condition Retrieval for Nepal Aurora 1.5 Inference.

Fetches ERA5T surface IC variables from the ARCO zarr store for all 14 Nepal
initialisations (28 timestamps: t−6h and t+0h per init).

Scope:
  Surface variables fetched and stored locally:
    2m_temperature             → t2m_K       (K)
    10m_u_component_of_wind    → u10m_ms     (m/s)
    10m_v_component_of_wind    → v10m_ms     (m/s)
    mean_sea_level_pressure    → msl_Pa      (Pa)
    total_precipitation        → tp1h_mmhr   (mm/hr, after max(0,tp_m×1000))

  Spatial extent: global (721 lat × 1440 lon); ARCO native convention.
  IC convention: two consecutive timesteps (t−6h, t+0h) per initialisation,
    matching the Aurora1p5 input requirement.

  Pressure-level variables verified by name only (not downloaded here).
  Full pressure-level IC fetch is performed on Brev via earth2studio.data.ARCO
  at inference time, consistent with the verified Aurora 1.5 Myanmar workflow.

ERA5T status:
  All timestamps fall in the ERA5T (provisional ERA5) period.
  ERA5T confirmed available in ARCO through 2026-08-15 (P1 gate PASS).

Outputs:
  results/nepal/era5_ic/{slug}_era5_ic.nc            — IC NetCDF per init
  results/nepal/provenance/{slug}_era5_ic_provenance.json
  results/nepal/validation/p2_manifest.json          — retrieval manifest

Design note:
  Files are written atomically (to .tmp then renamed).
  Already-valid files are skipped on re-run (safe to resume).

Project:  002-nepal-eval v1.1
Model:    Aurora1p5 / Earth2Studio 0.17.0
Source:   /Users/limjiayan/nepal-forecast-eval  (not myanmar-forecast-eval)
"""

from __future__ import annotations

import csv
import datetime
import json
import pathlib
import time
import warnings

import gcsfs
import numpy as np
import xarray as xr
import zarr

warnings.filterwarnings("ignore")

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT      = pathlib.Path(__file__).parent.parent
CAL_PATH  = ROOT / "config" / "nepal_calendar.csv"
IC_DIR    = ROOT / "results" / "nepal" / "era5_ic"
PROV_DIR  = ROOT / "results" / "nepal" / "provenance"
VAL_DIR   = ROOT / "results" / "nepal" / "validation"

for d in (IC_DIR, PROV_DIR, VAL_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── ARCO configuration ────────────────────────────────────────────────────────
ARCO_URL  = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"

# Surface variables to retrieve (ARCO names → stored names)
SURFACE_VARS = {
    "2m_temperature":             "t2m_K",
    "10m_u_component_of_wind":    "u10m_ms",
    "10m_v_component_of_wind":    "v10m_ms",
    "mean_sea_level_pressure":    "msl_Pa",
    "total_precipitation":        "tp_raw_m",   # stored raw; tp1h_mmhr attr records conversion
}

# Pressure-level variables Aurora1p5 also requires (verified by name; fetched on Brev)
PRESSURE_LEVEL_VARS_AURORA = [
    "u_component_of_wind",     # u at pressure levels
    "v_component_of_wind",     # v at pressure levels
    "temperature",             # t at pressure levels
    "geopotential",            # z at pressure levels
    "specific_humidity",       # q at pressure levels
]

UTC = datetime.timezone.utc


# ── Load calendar ─────────────────────────────────────────────────────────────
def load_calendar() -> list[dict]:
    rows = []
    with open(CAL_PATH) as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


# ── Validate an already-written IC file ──────────────────────────────────────
def validate_ic_file(path: pathlib.Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "does not exist"
    if path.stat().st_size < 1000:
        return False, f"suspiciously small: {path.stat().st_size} bytes"
    try:
        ds = xr.open_dataset(path)
        # Check IC step dimension
        if ds.sizes.get("ic_step") != 2:
            ds.close(); return False, f"ic_step dim={ds.sizes.get('ic_step')}, expected 2"
        # Check spatial dimensions
        if ds.sizes.get("latitude") != 721:
            ds.close(); return False, f"latitude={ds.sizes.get('latitude')}, expected 721"
        if ds.sizes.get("longitude") != 1440:
            ds.close(); return False, f"longitude={ds.sizes.get('longitude')}, expected 1440"
        # Check required variables
        for stored_name in SURFACE_VARS.values():
            if stored_name not in ds.data_vars:
                ds.close(); return False, f"missing variable: {stored_name}"
        # NaN check for t2m and winds
        for vname in ("t2m_K", "u10m_ms", "v10m_ms", "msl_Pa"):
            if np.any(np.isnan(ds[vname].values)):
                ds.close(); return False, f"NaN found in {vname}"
        # Provenance attrs
        if ds.attrs.get("era5t") not in (True, "true", 1):
            ds.close(); return False, "era5t attribute missing or False"
        ds.close()
        return True, "ok"
    except Exception as e:
        return False, str(e)


# ── Fetch surface ICs for one initialisation ──────────────────────────────────
def fetch_one_init(row: dict, arco_ds: xr.Dataset) -> dict:
    """
    Fetch surface IC variables for one init at t−6h and t+0h.
    Returns result dict for the manifest.
    """
    slug      = row["slug"]
    ic_m6_str = row["ic_minus6h_utc"]
    ic_p0_str = row["ic_plus0h_utc"]

    out_path  = IC_DIR   / f"{slug}_era5_ic.nc"
    prov_path = PROV_DIR / f"{slug}_era5_ic_provenance.json"
    tmp_path  = IC_DIR   / f"{slug}_era5_ic.nc.tmp"

    # Resume: skip already-valid files
    ok, reason = validate_ic_file(out_path)
    if ok:
        print(f"  [{slug}] SKIP — already valid ({out_path.stat().st_size/1e6:.1f} MB)")
        return {"slug": slug, "status": "skipped", "reason": "already valid",
                "file": str(out_path)}

    if tmp_path.exists():
        tmp_path.unlink()

    # Parse IC datetimes
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    ic_m6 = datetime.datetime.strptime(ic_m6_str, fmt).replace(tzinfo=UTC)
    ic_p0 = datetime.datetime.strptime(ic_p0_str, fmt).replace(tzinfo=UTC)
    ic_times = [ic_m6, ic_p0]
    ic_np    = [np.datetime64(t.replace(tzinfo=None), "ns") for t in ic_times]

    t_start = time.perf_counter()
    print(f"  [{slug}] fetching  t-6h={ic_m6_str}  t+0h={ic_p0_str} …", flush=True)

    # Fetch all surface vars for both IC steps in one batched call
    try:
        batch = arco_ds[list(SURFACE_VARS.keys())].sel(time=ic_np).compute()
    except Exception as e:
        return {"slug": slug, "status": "failed", "error": f"batch fetch: {e}"}

    wall_s = time.perf_counter() - t_start

    # Build arrays (ic_step, lat, lon)
    data_vars = {}
    for arco_name, stored_name in SURFACE_VARS.items():
        arr = batch[arco_name].values.astype(np.float32)   # (2, 721, 1440)
        data_vars[stored_name] = (["ic_step", "latitude", "longitude"], arr)

    lat_vals = batch.coords["latitude"].values.astype(np.float32)
    lon_vals = batch.coords["longitude"].values.astype(np.float32)

    ds = xr.Dataset(
        data_vars,
        coords={
            "latitude":    lat_vals,         # 721 pts, N→S (90 … -90)
            "longitude":   lon_vals,         # 1440 pts, 0 → 359.75
            "ic_step":     np.array([0, 1], dtype=np.int8),
            "ic_datetime": ("ic_step", np.array(ic_np)),
        },
        attrs={
            "spec_id":           "002-nepal-eval",
            "spec_version":      "v1.1",
            "project":           "nepal-forecast-eval",
            "slug":              slug,
            "init_datetime_utc": ic_p0_str,
            "ic_minus6h_utc":    ic_m6_str,
            "ic_plus0h_utc":     ic_p0_str,
            "era5t":             "true",
            "era5t_note":        "ERA5T (provisional ERA5); period beyond 2026-04-30T00:00Z",
            "arco_url":          ARCO_URL,
            "retrieval_utc":     datetime.datetime.now(UTC).strftime(fmt),
            "retrieval_wall_s":  round(wall_s, 1),
            "spatial_extent":    "global (721 lat × 1440 lon); ARCO native convention",
            "latitude_convention": "N→S; 90.0 to -90.0 in 0.25° steps",
            "longitude_convention": "0.0 to 359.75 in 0.25° steps",
            "tp_conversion":     "tp1h_mmhr = max(0, tp_raw_m * 1000); 1h accumulation in metres",
            "surface_vars_fetched": ", ".join(SURFACE_VARS.keys()),
            "pressure_level_vars_deferred": ", ".join(PRESSURE_LEVEL_VARS_AURORA),
            "pressure_level_note": (
                "Pressure-level IC variables are fetched on Brev at inference time "
                "via earth2studio.data.ARCO(), consistent with Myanmar Aurora workflow."
            ),
            "model":             "earth2studio.models.px.Aurora1p5",
            "e2s_version":       "0.17.0",
            "checkpoint_hash":   "c171214768997594e1a3fc6b8d9bbb489e9d21ab",
        },
    )

    # Write atomically
    encoding = {v: {"dtype": "float32", "zlib": True, "complevel": 4}
                for v in SURFACE_VARS.values()}
    ds.to_netcdf(tmp_path, encoding=encoding)
    tmp_path.rename(out_path)

    file_mb = out_path.stat().st_size / 1e6

    # Validate
    ok, reason = validate_ic_file(out_path)
    if not ok:
        return {"slug": slug, "status": "failed", "error": f"post-write validation: {reason}"}

    # Provenance JSON
    provenance = {
        "spec_id":             "002-nepal-eval",
        "spec_version":        "v1.1",
        "slug":                slug,
        "init_datetime_utc":   ic_p0_str,
        "ic_minus6h_utc":      ic_m6_str,
        "ic_plus0h_utc":       ic_p0_str,
        "era5t":               True,
        "arco_url":            ARCO_URL,
        "retrieval_utc":       ds.attrs["retrieval_utc"],
        "retrieval_wall_s":    round(wall_s, 1),
        "surface_vars": {
            arco_name: {"stored_as": stored_name, "fetched": True}
            for arco_name, stored_name in SURFACE_VARS.items()
        },
        "pressure_level_vars": {
            v: {"fetched": False, "fetch_location": "Brev/aurora_env via earth2studio.data.ARCO"}
            for v in PRESSURE_LEVEL_VARS_AURORA
        },
        "spatial": {
            "n_lat": 721, "n_lon": 1440,
            "lat_range": [float(lat_vals[0]), float(lat_vals[-1])],
            "lon_range": [float(lon_vals[0]), float(lon_vals[-1])],
        },
        "ic_steps": 2,
        "file_path":   str(out_path.relative_to(ROOT)),
        "file_size_mb": round(file_mb, 2),
        "validation":  "PASS",
    }
    with open(prov_path, "w") as f:
        json.dump(provenance, f, indent=2)

    print(f"  [{slug}] OK  {file_mb:.1f} MB  {wall_s:.1f}s")
    return {"slug": slug, "status": "success", "file": str(out_path),
            "file_mb": round(file_mb, 2), "wall_s": round(wall_s, 1)}


# ── Pressure-level variable name check ───────────────────────────────────────
def check_pressure_level_vars(arco_ds: xr.Dataset) -> dict:
    """Verify Aurora pressure-level variable names exist in ARCO (name only; no data fetch)."""
    results = {}
    for vname in PRESSURE_LEVEL_VARS_AURORA:
        results[vname] = vname in arco_ds.data_vars
    return results


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    cal = load_calendar()
    assert len(cal) == 14, f"Expected 14 calendar rows, got {len(cal)}"

    print(f"\n{'═'*70}")
    print("  P2 — Nepal ERA5T IC Retrieval")
    print(f"{'═'*70}")
    print(f"  ARCO: {ARCO_URL}")
    print(f"  Inits: {len(cal)}  IC timestamps: {len(cal)*2}")
    print(f"  Surface vars: {list(SURFACE_VARS.keys())}")
    print(f"  Output: {IC_DIR}")
    print(f"{'═'*70}\n")

    # Open ARCO store once
    print("Opening ARCO store …", flush=True)
    fs    = gcsfs.GCSFileSystem(token="anon")
    store = fs.get_mapper(ARCO_URL)
    arco  = xr.open_zarr(store, consolidated=True)
    print(f"  Opened: {len(arco.data_vars)} variables, "
          f"time axis {arco.dims['time']:,} steps\n", flush=True)

    # Check pressure-level variable availability
    print("Checking pressure-level variable names in ARCO …")
    pl_check = check_pressure_level_vars(arco)
    for vname, present in pl_check.items():
        tag = "OK" if present else "MISSING"
        print(f"  [{tag}] {vname}")
    print()

    # Retrieve ICs
    manifest_entries = []
    n_success = n_skipped = n_failed = 0
    wall_total_start = time.perf_counter()

    for i, row in enumerate(cal):
        print(f"[{i+1:2d}/{len(cal)}] {row['slug']}")
        result = fetch_one_init(row, arco)
        manifest_entries.append(result)
        if result["status"] == "success":
            n_success += 1
        elif result["status"] == "skipped":
            n_skipped += 1
        else:
            n_failed  += 1
            print(f"  ERROR: {result.get('error')}", flush=True)

    wall_total = time.perf_counter() - wall_total_start

    # Total storage
    nc_files = list(IC_DIR.glob("*_era5_ic.nc"))
    total_mb  = sum(f.stat().st_size for f in nc_files) / 1e6

    # P2 manifest
    manifest = {
        "spec_id":          "002-nepal-eval",
        "spec_version":     "v1.1",
        "generated_utc":    datetime.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "arco_url":         ARCO_URL,
        "era5t":            True,
        "n_inits":          len(cal),
        "n_ic_timestamps":  len(cal) * 2,
        "n_success":        n_success,
        "n_skipped":        n_skipped,
        "n_failed":         n_failed,
        "n_complete":       n_success + n_skipped,
        "overall_status":   "PASS" if n_failed == 0 else "FAIL",
        "surface_vars_fetched": list(SURFACE_VARS.keys()),
        "pressure_level_vars_verified_by_name": pl_check,
        "spatial": {"n_lat": 721, "n_lon": 1440,
                    "lat_convention": "N→S (90.0 to -90.0)",
                    "lon_convention": "0.0 to 359.75"},
        "total_ic_files":   len(nc_files),
        "total_size_mb":    round(total_mb, 1),
        "wall_total_s":     round(wall_total, 1),
        "initialisations":  manifest_entries,
    }

    manifest_path = VAL_DIR / "p2_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n{'═'*70}")
    print(f"  P2 COMPLETE")
    print(f"  Success: {n_success}  Skipped: {n_skipped}  Failed: {n_failed}")
    print(f"  Files:   {len(nc_files)} IC NetCDF files")
    print(f"  Storage: {total_mb:.1f} MB")
    print(f"  Wall:    {wall_total:.1f}s ({wall_total/60:.1f} min)")
    print(f"  Manifest: {manifest_path}")
    print(f"{'═'*70}")

    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
