#!/usr/bin/env python3
"""
R3 Benchmark — Aurora1p5 on Brev A100 80GB
Project: 001-zero-shot-eval

Uses earth2studio.run.deterministic for correct API usage.

Run:
  conda activate aurora_env
  export HF_HOME=/data/hf_cache
  export EARTH2STUDIO_CACHE=/data/e2s_cache
  python3 ~/r3_benchmark.py 2>&1 | tee ~/r3_benchmark.log
"""

import sys
import os
import time
import json
import datetime
import traceback
import importlib
import inspect
import threading

import numpy as np
import torch
from collections import OrderedDict

# ── Constants ─────────────────────────────────────────────────────────────────
BREV_ONDEMAND_RATE = 6.21        # USD per hour (Hyperstack A100 80GB)
BENCHMARK_DATES = [
    datetime.datetime(2022, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
    datetime.datetime(2022, 4, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
    datetime.datetime(2022, 7, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
    datetime.datetime(2022, 10, 1, 0, 0, 0, tzinfo=datetime.timezone.utc),
]
N_STEPS = 168
N_INITS_2022 = 122
N_INITS_LONGITUDINAL = 44
N_INITS_TOTAL = 166

MYANMAR_LAT = np.arange(9.0, 29.25, 0.25)
MYANMAR_LON = np.arange(92.0, 102.25, 0.25)

OUTPUT_DIR = "/data/e2s_cache/r3_outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

SEP = "=" * 70

def head(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")

def cost_usd(wall_clock_seconds):
    return wall_clock_seconds / 3600 * BREV_ONDEMAND_RATE

report = {
    "project": "001-zero-shot-eval",
    "benchmark": "R3",
    "date_utc": datetime.datetime.utcnow().isoformat(),
    "instance": "Hyperstack A100 80GB Montreal",
    "rate_usd_per_hr": BREV_ONDEMAND_RATE,
    "passes": [], "fails": [], "warnings": [],
    "date_results": [],
    "precipitation": {},
    "cost_projection": {},
    "verdict": "PENDING",
}

def save_report():
    path = os.path.join(OUTPUT_DIR, "r3_report.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"[report saved -> {path}]")


# ── VRAM monitor thread ───────────────────────────────────────────────────────
class VRAMMonitor(threading.Thread):
    def __init__(self, interval=2.0):
        super().__init__(daemon=True)
        self.interval = interval
        self.peak_mib = 0.0
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            try:
                used = torch.cuda.memory_reserved(0) / 1024**2
                if used > self.peak_mib:
                    self.peak_mib = used
            except Exception:
                pass
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()


# ── Step 1: Environment ───────────────────────────────────────────────────────
head("STEP 1: Environment check")
print(f"torch: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    props = torch.cuda.get_device_properties(0)
    vram_total = props.total_memory / 1024**2
    print(f"GPU: {props.name}, VRAM total: {vram_total:.0f} MiB")
    report["gpu"] = props.name
    report["vram_total_mib"] = vram_total
    if "A100" not in props.name:
        report["warnings"].append(f"Expected A100, got {props.name}")
else:
    report["fails"].append("CUDA not available")
    save_report()
    sys.exit(1)

import earth2studio
print(f"earth2studio: {earth2studio.__version__}")
report["earth2studio_version"] = earth2studio.__version__
if earth2studio.__version__ != "0.17.0":
    report["warnings"].append(f"Expected earth2studio 0.17.0, got {earth2studio.__version__}")


# ── Step 2: aurora_log_untransform ───────────────────────────────────────────
head("STEP 2: Precipitation transform (aurora_log_untransform)")

aurora_log_untransform = None
search_paths = [
    ("earth2studio.models.px.aurora", "aurora_log_untransform"),
    ("earth2studio.models.px", "aurora_log_untransform"),
    ("earth2studio.models.px.aurora", "log_untransform"),
    ("aurora", "aurora_log_untransform"),
    ("aurora.model.aurora", "aurora_log_untransform"),
]
for mod_path, fn_name in search_paths:
    try:
        mod = importlib.import_module(mod_path)
        fn = getattr(mod, fn_name, None)
        if fn is not None:
            aurora_log_untransform = fn
            print(f"Found: {mod_path}.{fn_name}")
            try:
                print("Source:", inspect.getsource(fn))
            except Exception:
                pass
            break
    except ImportError:
        pass

if aurora_log_untransform is None:
    # grep search
    print("Searching installed files...")
    try:
        import subprocess
        e2s_dir = os.path.dirname(earth2studio.__file__)
        aurora_pkg = os.path.dirname(importlib.import_module("aurora").__file__)
        for search_dir in [e2s_dir, aurora_pkg]:
            out = subprocess.check_output(
                ["grep", "-r", "log_untransform", "--include=*.py", "-l", search_dir],
                text=True, stderr=subprocess.DEVNULL
            )
            if out.strip():
                print(f"  Found in: {out.strip()}")
                # Try to grep the actual function
                out2 = subprocess.check_output(
                    ["grep", "-r", "def.*log_untransform", "--include=*.py", search_dir],
                    text=True, stderr=subprocess.DEVNULL
                )
                print(f"  Function defs: {out2.strip()}")
    except Exception as e:
        print(f"  grep error: {e}")
    report["fails"].append("aurora_log_untransform not found")
    report["precipitation"]["untransform_found"] = False
else:
    report["precipitation"]["untransform_found"] = True
    report["passes"].append("aurora_log_untransform found")
    # Forward test
    test_vals = [(-5.0, "dry"), (0.0, "zero"), (0.5, "moderate"), (1.0, "heavy")]
    fwd = []
    print("\nForward test:")
    for v, desc in test_vals:
        try:
            t = torch.tensor([v], dtype=torch.float32)
            out = aurora_log_untransform(t)
            mmhr = float(out.item()) * 1000
            print(f"  untransform({v:+.1f}) = {out.item():.6f} -> {mmhr:.4f} mm/hr  [{desc}]")
            fwd.append({"input": v, "raw": float(out.item()), "mm_per_hr": mmhr})
        except Exception as e:
            print(f"  ERROR: {e}")
    report["precipitation"]["forward_test"] = fwd

save_report()


# ── Step 3: ARCO lexicon ──────────────────────────────────────────────────────
head("STEP 3: ARCO lexicon — tp / tp06 mapping")
try:
    from earth2studio.lexicon import ARCOLexicon
    for v in ["tp", "tp06", "t2m", "u10m", "v10m"]:
        try:
            entry = ARCOLexicon[v]
            print(f"  {v:8s} -> {entry}")
        except KeyError:
            print(f"  {v:8s} -> NOT IN LEXICON")
    tp_entry = ARCOLexicon["tp"]
    tp_zarr = tp_entry[0] if isinstance(tp_entry, (list, tuple)) else str(tp_entry)
    if "total_precipitation" in str(tp_zarr):
        report["passes"].append("ARCO tp -> total_precipitation")
        report["precipitation"]["arco_tp_zarr_field"] = str(tp_zarr)
    else:
        report["warnings"].append(f"tp maps to: {tp_zarr}")
except Exception as e:
    report["warnings"].append(f"Lexicon check error: {e}")

save_report()


# ── Step 4: Model load ────────────────────────────────────────────────────────
head("STEP 4: Aurora1p5 model load")
from earth2studio.models.px import Aurora1p5

torch.cuda.reset_peak_memory_stats(0)
t0 = time.perf_counter()
try:
    pkg = Aurora1p5.load_default_package()
    model = Aurora1p5.load_model(pkg)
    model = model.to("cuda")
    model.eval()
    load_time = time.perf_counter() - t0
    vram_after_load = torch.cuda.memory_reserved(0) / 1024**2
    print(f"Model loaded in {load_time:.1f}s, VRAM reserved: {vram_after_load:.0f} MiB")
    report["model_load_time_s"] = load_time
    report["vram_after_load_mib"] = vram_after_load
    report["passes"].append(f"Aurora1p5 loaded in {load_time:.1f}s")

    ic = model.input_coords()
    input_vars = list(ic.get("variable", []))
    print(f"Input vars ({len(input_vars)}): lead_time={list(ic.get('lead_time', []))}")
    precip_in = [v for v in input_vars if "tp" in str(v).lower()]
    print(f"Precip input vars: {precip_in}")
    report["precipitation"]["aurora_input_vars"] = precip_in

    oc = model.output_coords(ic)
    output_vars = list(oc.get("variable", []))
    precip_out = [v for v in output_vars if "tp" in str(v).lower()]
    print(f"Precip output vars: {precip_out}")
    report["precipitation"]["aurora_output_vars"] = precip_out
    if "tp1h" in output_vars:
        report["passes"].append("Aurora1p5 outputs tp1h")
    else:
        report["warnings"].append(f"tp1h not in output; found: {precip_out}")

except Exception as e:
    print(f"Model load FAILED: {e}")
    traceback.print_exc()
    report["fails"].append(f"Model load failed: {e}")
    save_report()
    sys.exit(1)

save_report()


# ── Step 5: Per-date benchmark ────────────────────────────────────────────────
head("STEP 5: Per-date benchmark (4 dates, 168 steps each)")
from earth2studio.data import ARCO
from earth2studio.io import ZarrBackend
from earth2studio.run import deterministic

arco_ds = ARCO()
benchmark_start = time.perf_counter()

# Myanmar output coords to limit storage
myanmar_output_coords = OrderedDict([
    ("lat", MYANMAR_LAT),
    ("lon", MYANMAR_LON),
])

for date_idx, init_time in enumerate(BENCHMARK_DATES):
    date_str = init_time.strftime("%Y-%m-%dT%H%MZ")
    head(f"  Date {date_idx+1}/4: {date_str}")
    date_result = {
        "date": date_str,
        "season": ["S1-Dry", "S2-PreMonsoon", "S3-Monsoon", "S4-PostMonsoon"][date_idx],
    }

    output_path = os.path.join(OUTPUT_DIR, f"aurora1p5_r3_{init_time.strftime('%Y%m%d_%H%M')}.zarr")

    vram_mon = VRAMMonitor(interval=2.0)
    vram_mon.start()
    torch.cuda.reset_peak_memory_stats(0)
    t_run = time.perf_counter()

    try:
        io = ZarrBackend(output_path)
        deterministic(
            time=[init_time],
            nsteps=N_STEPS,
            prognostic=model,
            data=arco_ds,
            io=io,
            output_coords=myanmar_output_coords,
            device=torch.device("cuda"),
            verbose=True,
        )
        run_time = time.perf_counter() - t_run
        vram_mon.stop()
        vram_peak = vram_mon.peak_mib

        print(f"\nDate {date_idx+1} complete: {run_time:.0f}s ({run_time/60:.1f}min)")
        print(f"VRAM peak: {vram_peak:.0f} MiB")

        date_result["run_time_s"] = run_time
        date_result["vram_peak_mib"] = vram_peak
        date_result["infer_ok"] = True
        date_result["output_path"] = output_path

        # Inspect output for tp1h precipitation
        try:
            import xarray as xr
            ds_out = xr.open_zarr(output_path)
            print(f"Output zarr variables: {list(ds_out.data_vars)}")
            date_result["output_vars"] = list(ds_out.data_vars)
            if "tp1h" in ds_out.data_vars:
                tp_vals = ds_out["tp1h"].values
                tp_min = float(np.nanmin(tp_vals))
                tp_max = float(np.nanmax(tp_vals))
                tp_mean = float(np.nanmean(tp_vals))
                print(f"tp1h (log-space): min={tp_min:.4f}, max={tp_max:.4f}, mean={tp_mean:.4f}")
                date_result.update({"tp1h_log_min": tp_min, "tp1h_log_max": tp_max, "tp1h_log_mean": tp_mean})
                if aurora_log_untransform is not None:
                    tp_t = torch.from_numpy(tp_vals.astype(np.float32))
                    tp_phys = aurora_log_untransform(tp_t).numpy() * 1000
                    phys_min = float(np.nanmin(tp_phys))
                    phys_max = float(np.nanmax(tp_phys))
                    phys_mean = float(np.nanmean(tp_phys))
                    print(f"tp1h (mm/hr): min={phys_min:.4f}, max={phys_max:.4f}, mean={phys_mean:.4f}")
                    date_result.update({"tp1h_mmhr_min": phys_min, "tp1h_mmhr_max": phys_max, "tp1h_mmhr_mean": phys_mean})
                    date_result["tp_physical_range_ok"] = phys_min >= 0 and phys_max < 500
            ds_out.close()
        except Exception as e:
            print(f"Output inspection error: {e}")

        cost = cost_usd(run_time)
        date_result["cost_usd"] = cost
        print(f"Cost for this date: ${cost:.3f}")

        # Budget checkpoint after date 1
        if date_idx == 0:
            elapsed = time.perf_counter() - benchmark_start
            proj_4 = elapsed * 4
            print(f"\n*** BUDGET CHECKPOINT ***")
            print(f"Elapsed: {elapsed:.0f}s | Projected 4-date total: {proj_4/60:.0f}min = ${cost_usd(proj_4):.2f}")
            if cost_usd(proj_4) > 20:
                report["warnings"].append(f"Projected R3 cost ${cost_usd(proj_4):.2f} > $20")

    except torch.cuda.OutOfMemoryError as e:
        run_time = time.perf_counter() - t_run
        vram_mon.stop()
        vram_used = torch.cuda.memory_allocated(0) / 1024**2
        print(f"OOM after {run_time:.1f}s — VRAM used: {vram_used:.0f} MiB")
        date_result.update({"infer_ok": False, "oom": True, "vram_at_oom_mib": vram_used})
        report["fails"].append(f"OOM on {date_str}")
        report["verdict"] = "FAIL-OOM"
        report["date_results"].append(date_result)
        save_report()
        sys.exit(1)

    except Exception as e:
        run_time = time.perf_counter() - t_run
        vram_mon.stop()
        print(f"FAILED after {run_time:.1f}s: {e}")
        traceback.print_exc()
        date_result.update({"infer_ok": False, "run_time_s": run_time, "error": str(e)})
        report["fails"].append(f"Failed on {date_str}: {e}")

    report["date_results"].append(date_result)
    save_report()


# ── Step 6: Cost projection ───────────────────────────────────────────────────
head("STEP 6: Cost projection")
successful = [d for d in report["date_results"] if d.get("infer_ok")]

if successful:
    mean_wall = np.mean([d["run_time_s"] for d in successful])
    r3_cost = cost_usd(sum(d["run_time_s"] for d in successful))
    proj_2022 = cost_usd(mean_wall * N_INITS_2022)
    proj_full = cost_usd(mean_wall * N_INITS_TOTAL)

    print(f"Successful: {len(successful)}/4  Mean per-init: {mean_wall:.0f}s ({mean_wall/60:.1f}min)")
    print(f"R3 actual cost:               ${r3_cost:.2f}")
    print(f"Projected 2022 ({N_INITS_2022} inits):  {mean_wall*N_INITS_2022/3600:.1f}hr = ${proj_2022:.0f}")
    print(f"Projected full ({N_INITS_TOTAL} inits):  {mean_wall*N_INITS_TOTAL/3600:.1f}hr = ${proj_full:.0f}")

    vram_peaks = [d["vram_peak_mib"] for d in successful if d.get("vram_peak_mib")]
    max_vram = max(vram_peaks) if vram_peaks else None

    report["cost_projection"] = {
        "n_successful": len(successful),
        "mean_run_time_s": float(mean_wall),
        "r3_actual_cost_usd": float(r3_cost),
        "proj_2022_hr": float(mean_wall * N_INITS_2022 / 3600),
        "proj_2022_cost_usd": float(proj_2022),
        "proj_full_hr": float(mean_wall * N_INITS_TOTAL / 3600),
        "proj_full_cost_usd": float(proj_full),
        "max_vram_peak_mib": float(max_vram) if max_vram else None,
    }

    if len(successful) == 4:
        report["passes"].append("All 4 benchmark dates completed")
    else:
        report["fails"].append(f"Only {len(successful)}/4 dates succeeded")

    if max_vram:
        print(f"Max VRAM peak: {max_vram:.0f} / {report['vram_total_mib']:.0f} MiB")
        if max_vram < 0.95 * report["vram_total_mib"]:
            report["passes"].append(f"VRAM peak {max_vram:.0f} MiB within limit")
        else:
            report["warnings"].append(f"VRAM peak {max_vram:.0f} MiB close to 80GB limit")

    if proj_full <= 400:
        report["passes"].append(f"Full experiment projected ${proj_full:.0f} within budget")
    else:
        report["warnings"].append(f"Full experiment projected ${proj_full:.0f}")
else:
    print("No successful dates.")
    report["fails"].append("No successful dates")

save_report()


# ── Step 7: Final verdict ─────────────────────────────────────────────────────
head("STEP 7: R3 Verdict")
n_fails = len(report["fails"])
n_passes = len(report["passes"])
n_warn = len(report["warnings"])

for p in report["passes"]: print(f"  [PASS] {p}")
for w in report["warnings"]: print(f"  [WARN] {w}")
for f in report["fails"]: print(f"  [FAIL] {f}")

if report["verdict"] == "PENDING":
    report["verdict"] = "PASS" if n_fails == 0 else "FAIL"

print(f"\n{'='*70}")
print(f"  R3 VERDICT: {report['verdict']}")
print(f"{'='*70}")

save_report()
print("\nDone. Copy r3_report.json and r3_benchmark.log before stopping the instance.")
