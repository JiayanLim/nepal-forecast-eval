"""
P3 — Nepal Aurora 1.5 Inference Runner.

Runs 14 daily 00Z initialisations (2026-07-20 → 2026-08-02) through
Aurora 1.5, each for 168 1h steps (7-day forecast).

Outputs per initialisation:
  results/nepal/forecasts/{slug}_aurora.nc
  results/nepal/provenance/{slug}_aurora_provenance.json

Final manifest:
  results/nepal/manifest.json

Run on Brev A100 instance only. Not for local macOS execution.
Requires: aurora_env, earth2studio 0.17.0, CUDA, verify_patch() True.

Usage:
  python scripts/nepal_inference.py              # run all 14
  python scripts/nepal_inference.py --slug 20260720  # run one
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import pathlib
import sys
import time

import numpy as np
import torch
import xarray as xr

UTC = datetime.timezone.utc

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT      = pathlib.Path(__file__).parent.parent
CAL_PATH  = ROOT / "config" / "nepal_calendar.csv"
FC_DIR    = ROOT / "results" / "nepal" / "forecasts"
PROV_DIR  = ROOT / "results" / "nepal" / "provenance"
MAN_PATH  = ROOT / "results" / "nepal" / "manifest.json"

for d in (FC_DIR, PROV_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── Nepal domain ──────────────────────────────────────────────────────────────
# Must match config/nepal_experiment.json and data/masks/nepal_land_mask.npy
NEPAL_DOMAIN = (26.0, 30.5, 80.0, 88.5)  # (lat_min, lat_max, lon_min, lon_max)
EXPECTED_LAT = 19   # 26.0–30.5 at 0.25°
EXPECTED_LON = 35   # 80.0–88.5 at 0.25°
N_STEPS      = 168

# ── Pipeline imports (deferred to respect BREV-only deps) ─────────────────────
sys.path.insert(0, str(ROOT))


def load_calendar(slug_filter: str | None = None) -> list[dict]:
    rows = []
    with open(CAL_PATH) as f:
        for row in csv.DictReader(f):
            if slug_filter and row["slug"] != slug_filter:
                continue
            rows.append(row)
    return rows


def validate_forecast_file(path: pathlib.Path) -> tuple[bool, str]:
    """Check a written forecast NC file for structural validity."""
    if not path.exists():
        return False, "does not exist"
    if path.stat().st_size < 1000:
        return False, f"suspiciously small: {path.stat().st_size} bytes"
    try:
        ds = xr.open_dataset(path)
        if ds.sizes.get("lead_time") != N_STEPS:
            ds.close(); return False, f"lead_time={ds.sizes.get('lead_time')}, expected {N_STEPS}"
        if ds.sizes.get("lat") != EXPECTED_LAT:
            ds.close(); return False, f"lat={ds.sizes.get('lat')}, expected {EXPECTED_LAT}"
        if ds.sizes.get("lon") != EXPECTED_LON:
            ds.close(); return False, f"lon={ds.sizes.get('lon')}, expected {EXPECTED_LON}"
        for vname in ("t2m_C", "ws_kts", "wd_deg", "tp1h_mmhr"):
            if vname not in ds.data_vars:
                ds.close(); return False, f"missing variable: {vname}"
        if not ds.attrs.get("patch_confirmed"):
            ds.close(); return False, "patch_confirmed attribute missing"
        ds.close()
        return True, "ok"
    except Exception as e:
        return False, str(e)


def run_one_init(row: dict, model, device: str = "cuda") -> dict:
    """Run a single forecast initialisation and save outputs."""
    from src.pipeline.inference import run_forecast, DOMAIN_NEPAL
    from src.pipeline.transforms import (
        t2m_to_celsius, tp1h_to_mmhr, uv_to_ws_kts, uv_to_wd_deg,
    )

    slug      = row["slug"]
    init_str  = row["init_datetime_utc"]
    fmt       = "%Y-%m-%dT%H:%M:%SZ"
    init_time = datetime.datetime.strptime(init_str, fmt).replace(tzinfo=UTC)

    out_path  = FC_DIR   / f"{slug}_aurora.nc"
    prov_path = PROV_DIR / f"{slug}_aurora_provenance.json"
    tmp_path  = FC_DIR   / f"{slug}_aurora.nc.tmp"

    # Resume: skip already-valid files
    ok, reason = validate_forecast_file(out_path)
    if ok:
        mb = out_path.stat().st_size / 1e6
        print(f"  [{slug}] SKIP — already valid ({mb:.1f} MB)")
        return {"slug": slug, "status": "skipped", "file": str(out_path)}

    if tmp_path.exists():
        tmp_path.unlink()

    print(f"  [{slug}] running {N_STEPS}-step forecast from {init_str} …", flush=True)

    t_start = time.perf_counter()

    # Run Aurora forecast — E2S fetches IC from ARCO internally
    raw_ds = run_forecast(
        init_time=init_time,
        model=model,
        device=device,
        nsteps=N_STEPS,
        verbose=True,
        domain=DOMAIN_NEPAL,
    )

    wall_s = time.perf_counter() - t_start
    print(f"  [{slug}] inference done in {wall_s:.1f}s", flush=True)

    # Unit conversions
    t2m_C     = t2m_to_celsius(raw_ds["t2m_K"].values).astype(np.float32)
    ws_kts    = uv_to_ws_kts(raw_ds["u10m"].values, raw_ds["v10m"].values).astype(np.float32)
    wd_deg    = uv_to_wd_deg(raw_ds["u10m"].values, raw_ds["v10m"].values).astype(np.float32)
    tp1h_raw  = raw_ds["tp1h_raw"].values
    tp1h_mmhr = tp1h_to_mmhr(tp1h_raw).astype(np.float32)

    # Count negatives in raw tp1h before clipping
    n_neg = int(np.sum(tp1h_raw < 0))

    # Build output dataset (schema from spec)
    dims = ["lead_time", "lat", "lon"]
    ds = xr.Dataset(
        {
            "t2m_C": (dims, t2m_C,
                      {"units": "degC", "long_name": "2m temperature"}),
            "ws_kts": (dims, ws_kts,
                       {"units": "knots", "long_name": "10m wind speed"}),
            "wd_deg": (dims, wd_deg,
                       {"units": "degrees",
                        "long_name": "10m wind direction (FROM, meteorological)",
                        "convention": "(270 - atan2(v, u)) % 360"}),
            "tp1h_mmhr": (dims, tp1h_mmhr,
                          {"units": "mm/hr",
                           "long_name": "Precipitation rate (clipped >= 0)",
                           "source": "tp1h_raw * 1000, clip(0)"}),
        },
        coords={
            "lead_time": raw_ds.coords["lead_time"],
            "lat":       raw_ds.coords["lat"],
            "lon":       raw_ds.coords["lon"],
            "init_time": raw_ds.coords["init_time"],
        },
        attrs={
            "spec_id":           "002-nepal-eval",
            "spec_version":      "v1.1",
            "project":           "nepal-forecast-eval",
            "model_id":          "aurora1p5",
            "earth2studio_ver":  "0.17.0",
            "checkpoint_hash":   "c171214768997594e1a3fc6b8d9bbb489e9d21ab",
            "patch_confirmed":   "true",
            "init_datetime_utc": init_str,
            "slug":              slug,
            "n_steps":           N_STEPS,
            "n_steps_collected": int(raw_ds.sizes["lead_time"]),
            "wall_clock_s":      round(wall_s, 1),
            "era5t_ic":          "true",
            "domain":            f"Nepal ({NEPAL_DOMAIN[0]}-{NEPAL_DOMAIN[1]}N, "
                                 f"{NEPAL_DOMAIN[2]}-{NEPAL_DOMAIN[3]}E)",
            "n_neg_tp1h":        n_neg,
            "precip_convention": (
                "tp1h_mmhr = max(0, tp1h_raw * 1000). "
                "Aurora tp1h is in m/hr physical space (E2S patch applied). "
                "Do NOT call aurora_log_untransform."
            ),
        },
    )

    # Atomic write
    encoding = {v: {"dtype": "float32", "zlib": True, "complevel": 4}
                for v in ds.data_vars}
    ds.to_netcdf(tmp_path, encoding=encoding)
    tmp_path.rename(out_path)

    file_mb = out_path.stat().st_size / 1e6

    # Validate
    ok, reason = validate_forecast_file(out_path)
    if not ok:
        return {"slug": slug, "status": "failed",
                "error": f"post-write validation: {reason}"}

    # Provenance JSON
    provenance = {
        "spec_id":             "002-nepal-eval",
        "spec_version":        "v1.1",
        "slug":                slug,
        "init_datetime_utc":   init_str,
        "model_id":            "aurora1p5",
        "earth2studio_ver":    "0.17.0",
        "checkpoint_hash":     "c171214768997594e1a3fc6b8d9bbb489e9d21ab",
        "patch_confirmed":     True,
        "era5t_ic":            True,
        "domain":              {"lat_min": NEPAL_DOMAIN[0], "lat_max": NEPAL_DOMAIN[1],
                                "lon_min": NEPAL_DOMAIN[2], "lon_max": NEPAL_DOMAIN[3]},
        "n_steps":             N_STEPS,
        "n_steps_collected":   int(raw_ds.sizes["lead_time"]),
        "wall_clock_s":        round(wall_s, 1),
        "n_neg_tp1h":          n_neg,
        "output_dims":         {"lead_time": N_STEPS, "lat": EXPECTED_LAT, "lon": EXPECTED_LON},
        "variables":           ["t2m_C", "ws_kts", "wd_deg", "tp1h_mmhr"],
        "file_path":           str(out_path.relative_to(ROOT)),
        "file_size_mb":        round(file_mb, 2),
        "generated_utc":       datetime.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(prov_path, "w") as f:
        json.dump(provenance, f, indent=2)

    print(f"  [{slug}] OK  {file_mb:.1f} MB  {wall_s:.1f}s  n_neg={n_neg}")

    # Free intermediate memory
    del raw_ds, ds
    return {"slug": slug, "status": "success", "file": str(out_path),
            "file_mb": round(file_mb, 2), "wall_s": round(wall_s, 1),
            "n_neg_tp1h": n_neg}


def main():
    parser = argparse.ArgumentParser(description="P3 Nepal Aurora 1.5 Inference")
    parser.add_argument("--slug", type=str, default=None,
                        help="Run single init by slug (e.g. 20260720)")
    args = parser.parse_args()

    cal = load_calendar(slug_filter=args.slug)
    if not cal:
        print(f"ERROR: no calendar rows match slug={args.slug}")
        return 1

    print(f"\n{'='*70}")
    print(f"  P3 — Nepal Aurora 1.5 Inference")
    print(f"{'='*70}")
    print(f"  Inits: {len(cal)}  Steps/init: {N_STEPS}")
    print(f"  Domain: Nepal {NEPAL_DOMAIN}")
    print(f"  Output: {FC_DIR}")
    print(f"{'='*70}\n")

    # Pre-flight checks
    from src.pipeline.inference import verify_patch, load_model
    verify_patch(raise_on_fail=True)
    print("  Patch verified: OK")

    print("  Loading Aurora1p5 model …", flush=True)
    t0 = time.perf_counter()
    model = load_model(device="cuda")
    print(f"  Model loaded in {time.perf_counter() - t0:.1f}s\n")

    # Run forecasts
    manifest_entries = []
    n_success = n_skipped = n_failed = 0
    wall_total_start = time.perf_counter()

    for i, row in enumerate(cal):
        print(f"[{i+1:2d}/{len(cal)}] {row['slug']}")
        result = run_one_init(row, model, device="cuda")
        manifest_entries.append(result)
        if result["status"] == "success":
            n_success += 1
        elif result["status"] == "skipped":
            n_skipped += 1
        else:
            n_failed += 1
            print(f"  ERROR: {result.get('error')}", flush=True)

        # Periodic GPU memory cleanup
        torch.cuda.empty_cache()

    wall_total = time.perf_counter() - wall_total_start

    # Storage summary
    nc_files = list(FC_DIR.glob("*_aurora.nc"))
    total_mb = sum(f.stat().st_size for f in nc_files) / 1e6

    # VRAM high-water mark
    vram_peak_mb = 0
    if torch.cuda.is_available():
        vram_peak_mb = torch.cuda.max_memory_allocated() / (1024**2)

    # Manifest
    manifest = {
        "spec_id":          "002-nepal-eval",
        "spec_version":     "v1.1",
        "generated_utc":    datetime.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_id":         "aurora1p5",
        "earth2studio_ver": "0.17.0",
        "checkpoint_hash":  "c171214768997594e1a3fc6b8d9bbb489e9d21ab",
        "domain":           {"lat_min": NEPAL_DOMAIN[0], "lat_max": NEPAL_DOMAIN[1],
                             "lon_min": NEPAL_DOMAIN[2], "lon_max": NEPAL_DOMAIN[3]},
        "n_inits":          len(cal),
        "n_steps_per_init": N_STEPS,
        "n_success":        n_success,
        "n_skipped":        n_skipped,
        "n_failed":         n_failed,
        "n_complete":       n_success + n_skipped,
        "overall_status":   "PASS" if n_failed == 0 else "FAIL",
        "total_forecast_files": len(nc_files),
        "total_size_mb":    round(total_mb, 1),
        "wall_total_s":     round(wall_total, 1),
        "wall_total_min":   round(wall_total / 60, 1),
        "vram_peak_mb":     round(vram_peak_mb, 0),
        "initialisations":  manifest_entries,
    }

    with open(MAN_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n{'='*70}")
    print(f"  P3 COMPLETE")
    print(f"  Success: {n_success}  Skipped: {n_skipped}  Failed: {n_failed}")
    print(f"  Files:   {len(nc_files)} forecast NetCDF files")
    print(f"  Storage: {total_mb:.1f} MB")
    print(f"  Wall:    {wall_total:.1f}s ({wall_total/60:.1f} min)")
    print(f"  VRAM peak: {vram_peak_mb:.0f} MB")
    print(f"  Manifest: {MAN_PATH}")
    print(f"{'='*70}")

    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
