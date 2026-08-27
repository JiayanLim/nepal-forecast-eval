#!/usr/bin/env python3
"""
R4 Full Experiment — 165-initialisation run (2026-08-01 deferred).

Schedule:
  122 × 2022 primary   (every 3 days 00Z, 2022-01-01 → 2022-12-30)
   43 × longitudinal   (1st of month 00Z, 2023-01-01 → 2026-07-01)
  ─────
  165 total this run   (2026-08-01 checked separately before adding)

Features:
  - Patch verified at startup; aborts immediately if missing
  - Resumable: skips dates with existing NetCDF output
  - Per-date failure is caught and logged; run continues
  - Machine-readable master progress file updated after every date
  - Final manifest printed at completion

Usage (on Brev, inside tmux session 'r4full'):
    conda activate aurora_env
    export EARTH2STUDIO_CACHE=/data/e2s_cache
    export HF_HOME=/data/hf_cache
    cd /home/shadeform/myanmar-forecast-eval
    python scripts/r4_full_run.py 2>&1 | tee /data/r4_full_run.log

Resuming after interruption:
    Same command — completed dates are skipped automatically.

Adding 2026-08-01 after availability check:
    python scripts/r4_full_run.py --add-aug2026
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Output paths (ephemeral disk — 738 GB, avoids filling 97 GB root) ────────
FC_DIR      = Path("/ephemeral/forecasts/aurora1p5")
MET_DIR     = Path("/ephemeral/metrics/r4_full")
LOG_DIR     = Path("/ephemeral/logs/r4_full")
PROGRESS_F  = Path("/ephemeral/r4_full_progress.json")

EVAL_LEAD_HOURS = [6, 12, 24, 48, 72, 96, 120, 144, 168]
DEVICE          = "cuda"


# ── Schedule ──────────────────────────────────────────────────────────────────

def _build_schedule(include_aug2026: bool = False) -> list[datetime.datetime]:
    UTC = datetime.timezone.utc
    dates: list[datetime.datetime] = []

    # 122 primary 2022 (every 3 days)
    d = datetime.date(2022, 1, 1)
    while d <= datetime.date(2022, 12, 31):
        dates.append(datetime.datetime(d.year, d.month, d.day, tzinfo=UTC))
        d += datetime.timedelta(days=3)

    # 43 longitudinal (2023-01-01 → 2026-07-01); 2026-08-01 deferred
    for year in [2023, 2024, 2025]:
        for month in range(1, 13):
            dates.append(datetime.datetime(year, month, 1, tzinfo=UTC))
    # 2026: Jan–Jul (7 months) = 7 dates
    for month in range(1, 8):
        dates.append(datetime.datetime(2026, month, 1, tzinfo=UTC))

    if include_aug2026:
        dates.append(datetime.datetime(2026, 8, 1, tzinfo=UTC))

    # Deduplicate and sort (should already be unique)
    seen = set()
    out = []
    for dt in dates:
        key = dt.date().isoformat()
        if key not in seen:
            seen.add(key)
            out.append(dt)
    out.sort()
    return out


def _slug(dt: datetime.datetime) -> str:
    return dt.strftime("%Y%m%d_%H%M")


# ── Progress tracking ─────────────────────────────────────────────────────────

def _load_progress() -> dict:
    if PROGRESS_F.exists():
        try:
            return json.loads(PROGRESS_F.read_text())
        except Exception:
            pass
    return {}


def _save_progress(progress: dict) -> None:
    PROGRESS_F.parent.mkdir(parents=True, exist_ok=True)
    tmp = PROGRESS_F.with_suffix(".tmp")
    tmp.write_text(json.dumps(progress, indent=2, default=str))
    tmp.replace(PROGRESS_F)


def _update_date_status(
    progress: dict,
    slug: str,
    *,
    status: str,          # "running"|"success"|"failed"|"skipped"
    start_time: float | None = None,
    end_time: float | None = None,
    runtime_s: float | None = None,
    fc_path: str | None = None,
    met_path: str | None = None,
    error: str | None = None,
) -> None:
    entry = progress.get(slug, {})
    entry["slug"]      = slug
    entry["status"]    = status
    if start_time  is not None: entry["start_time"]  = datetime.datetime.utcfromtimestamp(start_time).isoformat() + "Z"
    if end_time    is not None: entry["end_time"]    = datetime.datetime.utcfromtimestamp(end_time).isoformat() + "Z"
    if runtime_s   is not None: entry["runtime_s"]  = round(runtime_s, 1)
    if fc_path     is not None: entry["fc_path"]    = str(fc_path)
    if met_path    is not None: entry["met_path"]   = str(met_path)
    if error       is not None: entry["error"]      = error
    progress[slug] = entry


# ── Single-date runner ────────────────────────────────────────────────────────

def _run_one(
    init_time: datetime.datetime,
    model,
    progress: dict,
) -> str:
    """Run one initialisation. Returns 'success'|'failed'|'skipped'."""
    from src.pipeline.inference  import run_forecast
    from src.pipeline.transforms import apply_all
    from src.pipeline.era5_ref   import fetch_era5_reference
    from src.pipeline.metrics_runner import compute_metrics

    slug     = _slug(init_time)
    fc_path  = FC_DIR  / f"{slug}.nc"
    met_path = MET_DIR / f"{slug}.json"
    log_path = LOG_DIR / f"{slug}.txt"

    FC_DIR.mkdir(parents=True, exist_ok=True)
    MET_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Resume check
    if fc_path.exists() and met_path.exists():
        prev = progress.get(slug, {})
        if prev.get("status") == "success":
            print(f"  [skip] {slug} — already completed")
            _update_date_status(progress, slug, status="skipped",
                                fc_path=fc_path, met_path=met_path)
            return "skipped"

    t_start = time.time()
    _update_date_status(progress, slug, status="running", start_time=t_start)
    _save_progress(progress)

    log_lines: list[str] = [f"=== {slug} started {datetime.datetime.utcnow().isoformat()}Z ==="]

    try:
        # ── Forecast ─────────────────────────────────────────────────────────
        import xarray as xr
        if fc_path.exists():
            print(f"  [load] forecast from disk: {fc_path}")
            ds = xr.open_dataset(fc_path)
            if "precip_mmhr" not in ds.data_vars:
                ds = apply_all(ds)
        else:
            print(f"  [run]  Aurora1p5 forecast {init_time.isoformat()} …", flush=True)
            ds = run_forecast(init_time, model, device=DEVICE, nsteps=168, verbose=True)
            ds = apply_all(ds)
            ds.to_netcdf(fc_path, mode="w")
            fc_wall = round(time.time() - t_start, 1)
            log_lines.append(f"forecast_wall_s={fc_wall}")
            print(f"  [ok]   saved {fc_path} ({fc_wall}s)", flush=True)

        # ── ERA5 reference ────────────────────────────────────────────────────
        all_leads = [int(h) for h in ds.coords["lead_time"].values]
        print(f"  [era5] fetching reference …", flush=True)
        era5_ds = fetch_era5_reference(init_time, all_leads)

        # ── Metrics ───────────────────────────────────────────────────────────
        print(f"  [met]  computing metrics …", flush=True)
        metrics = compute_metrics(
            forecast_ds=ds,
            era5_ds=era5_ds,
            init_time_iso=init_time.isoformat(),
            eval_lead_hours=EVAL_LEAD_HOURS,
        )
        with open(met_path, "w") as fh:
            json.dump(metrics, fh, indent=2, default=str)
        print(f"  [ok]   saved {met_path}", flush=True)

        t_end    = time.time()
        runtime  = t_end - t_start
        log_lines.append(f"total_wall_s={round(runtime,1)}  status=success")
        log_path.write_text("\n".join(log_lines))
        _update_date_status(progress, slug, status="success",
                            start_time=t_start, end_time=t_end,
                            runtime_s=runtime, fc_path=fc_path, met_path=met_path)
        return "success"

    except Exception as exc:
        t_end   = time.time()
        runtime = t_end - t_start
        tb      = traceback.format_exc()
        msg     = f"{type(exc).__name__}: {exc}"
        print(f"  [ERR]  {slug}: {msg}", file=sys.stderr, flush=True)
        log_lines.append(f"ERROR: {tb}")
        log_path.write_text("\n".join(log_lines))
        _update_date_status(progress, slug, status="failed",
                            start_time=t_start, end_time=t_end,
                            runtime_s=runtime, error=msg)
        return "failed"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="R4 full 165-init experiment")
    parser.add_argument("--add-aug2026", action="store_true",
                        help="Include 2026-08-01 (run availability check first)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print schedule only; do not run inference")
    args = parser.parse_args()

    schedule = _build_schedule(include_aug2026=args.add_aug2026)
    n_total  = len(schedule)

    print(f"\n{'═'*70}")
    print(f"  R4 FULL EXPERIMENT")
    print(f"{'═'*70}")
    print(f"  Schedule : {n_total} initialisations")
    print(f"  First    : {schedule[0].isoformat()}")
    print(f"  Last     : {schedule[-1].isoformat()}")
    print(f"  Device   : {DEVICE}")
    print(f"  FC dir   : {FC_DIR}")
    print(f"  Met dir  : {MET_DIR}")
    print(f"  Progress : {PROGRESS_F}")
    print(f"  Log dir  : {LOG_DIR}")
    print(f"{'═'*70}\n")

    if args.dry_run:
        print("DRY RUN — schedule only:")
        for i, dt in enumerate(schedule):
            print(f"  {i+1:3d}. {dt.date().isoformat()}")
        return 0

    # ── Patch verification (fail immediately if absent) ───────────────────────
    print("Verifying Aurora1p5 patch …", flush=True)
    from src.pipeline.inference import verify_patch
    try:
        verify_patch(raise_on_fail=True)
        print("  PASS — patch active (scaled_tp_1h / scaled_sf_1h: False)\n", flush=True)
    except RuntimeError as e:
        print(f"\n  ABORT — patch NOT applied: {e}", file=sys.stderr)
        return 2

    # ── Load model once ───────────────────────────────────────────────────────
    print("Loading Aurora1p5 model …", flush=True)
    from src.pipeline.inference import load_model
    model = load_model(device=DEVICE)
    print("  Model loaded.\n", flush=True)

    # ── Load progress ─────────────────────────────────────────────────────────
    progress = _load_progress()
    wall_start = time.time()

    n_success = n_failed = n_skipped = 0
    failed_slugs: list[str] = []

    for idx, init_time in enumerate(schedule):
        slug = _slug(init_time)
        print(f"\n{'─'*70}")
        print(f"  [{idx+1:3d}/{n_total}]  {init_time.date().isoformat()}  ({slug})")
        print(f"  Progress so far: {n_success} ok / {n_failed} failed / {n_skipped} skipped")
        print("─"*70, flush=True)

        result = _run_one(init_time, model, progress)
        _save_progress(progress)

        if result == "success":
            n_success += 1
        elif result == "failed":
            n_failed  += 1
            failed_slugs.append(slug)
            # Systemic failure guard: abort if ≥5 consecutive failures
            recent = list(progress.values())[-10:]
            consecutive_fails = 0
            for r in reversed(recent):
                if r.get("status") == "failed":
                    consecutive_fails += 1
                else:
                    break
            if consecutive_fails >= 5:
                print(f"\n  ABORT — {consecutive_fails} consecutive failures detected. "
                      f"Likely systemic problem. Stopping.", file=sys.stderr)
                break
        elif result == "skipped":
            n_skipped += 1

    total_wall = time.time() - wall_start

    # ── Final manifest ────────────────────────────────────────────────────────
    n_missing = n_total - n_success - n_failed - n_skipped
    # Storage
    nc_bytes  = sum(f.stat().st_size for f in FC_DIR.glob("*.nc"))  if FC_DIR.exists()  else 0
    met_bytes = sum(f.stat().st_size for f in MET_DIR.glob("*.json")) if MET_DIR.exists() else 0
    total_gb  = (nc_bytes + met_bytes) / 1e9

    gpu_cost  = (total_wall / 3600) * 6.21  # $6.21/hr A100

    print(f"\n{'═'*70}")
    print(f"  R4 FULL EXPERIMENT — COMPLETE")
    print(f"{'═'*70}")
    print(f"  Total scheduled   : {n_total}")
    print(f"  Successful        : {n_success}")
    print(f"  Failed            : {n_failed}")
    print(f"  Skipped/resumed   : {n_skipped}")
    print(f"  Missing           : {n_missing}")
    print(f"  Total wall time   : {total_wall/3600:.2f} h  ({total_wall:.0f} s)")
    print(f"  Est. GPU cost     : ${gpu_cost:.2f} (at $6.21/hr)")
    print(f"  Total storage     : {total_gb:.2f} GB")
    if failed_slugs:
        print(f"\n  FAILED dates ({len(failed_slugs)}):")
        for s in failed_slugs:
            print(f"    {s}")
    print(f"\n  SEEPS note: synthetic climatology only — not for scientific reporting.")
    print(f"  Progress file: {PROGRESS_F}")
    print(f"{'═'*70}")

    # Save final manifest
    manifest = {
        "experiment":    "R4_full_165init",
        "completed_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "total_scheduled": n_total,
        "successful":    n_success,
        "failed":        n_failed,
        "skipped":       n_skipped,
        "missing":       n_missing,
        "failed_slugs":  failed_slugs,
        "total_wall_s":  round(total_wall, 1),
        "total_wall_h":  round(total_wall/3600, 3),
        "gpu_cost_usd":  round(gpu_cost, 2),
        "storage_gb":    round(total_gb, 3),
    }
    manifest_path = Path("/data/r4_full_manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"  Manifest: {manifest_path}")

    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
