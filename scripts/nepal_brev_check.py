"""
P3.00 — Brev environment validation for Nepal Aurora 1.5 inference.

Checks (items 1–8 from P3 gate):
  1. Working directory is the Nepal project
  2. aurora_env conda environment is active
  3. earth2studio.__version__ == 0.17.0
  4. CUDA/PyTorch sees A100 80 GB
  5. verify_patch() returns True
  6. Aurora1p5.load_default_package() loads the expected checkpoint
  7. Smoke test: 1 init × 2 steps over Nepal bbox
  8. Report all results

Run on Brev A100 instance only. Not for local macOS execution.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import sys
import time

UTC = datetime.timezone.utc

# ── Results accumulator ──────────────────────────────────────────────────────
results = []

def check(name: str, status: str, detail: str = ""):
    results.append({"name": name, "status": status, "detail": detail})
    tag = f"[{status}]"
    print(f"  {tag:<6} {name}" + (f"\n         {detail}" if detail else ""))


def main():
    ROOT = pathlib.Path(__file__).parent.parent
    OUT_DIR = ROOT / "results" / "nepal" / "validation"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH = OUT_DIR / "p3_brev_check.json"

    print(f"\n{'='*70}")
    print("  P3.00 — Brev Environment Validation")
    print(f"{'='*70}\n")

    # ── 1. Working directory is Nepal project ─────────────────────────────
    print("── 1. Project directory ─────────────────────────────────────────")
    spec_path = ROOT / "config" / "nepal_experiment.json"
    if spec_path.exists():
        with open(spec_path) as f:
            spec = json.load(f)
        is_nepal = spec.get("spec_id") == "002-nepal-eval"
        check("Nepal project directory",
              "PASS" if is_nepal else "FAIL",
              f"spec_id={spec.get('spec_id')}, root={ROOT}")
    else:
        check("Nepal project directory", "FAIL",
              f"config/nepal_experiment.json not found at {ROOT}")

    # ── 2. aurora_env active ──────────────────────────────────────────────
    print("\n── 2. Conda environment ─────────────────────────────────────────")
    conda_env = os.environ.get("CONDA_DEFAULT_ENV", "")
    check("aurora_env active",
          "PASS" if conda_env == "aurora_env" else "WARN",
          f"CONDA_DEFAULT_ENV={conda_env or '(not set)'}")

    # ── 3. Earth2Studio version ───────────────────────────────────────────
    print("\n── 3. Earth2Studio version ──────────────────────────────────────")
    try:
        import earth2studio
        e2s_ver = earth2studio.__version__
        check("earth2studio version",
              "PASS" if e2s_ver == "0.17.0" else "FAIL",
              f"version={e2s_ver}")
    except ImportError as e:
        check("earth2studio import", "FAIL", str(e))
        e2s_ver = None

    # ── 4. CUDA / PyTorch / GPU ───────────────────────────────────────────
    print("\n── 4. CUDA / PyTorch / GPU ──────────────────────────────────────")
    try:
        import torch
        cuda_avail = torch.cuda.is_available()
        check("CUDA available", "PASS" if cuda_avail else "FAIL")

        if cuda_avail:
            gpu_name = torch.cuda.get_device_name(0)
            gpu_mem_gb = torch.cuda.get_device_properties(0).total_mem / (1024**3)
            check(f"GPU: {gpu_name}",
                  "PASS" if "A100" in gpu_name else "WARN",
                  f"VRAM: {gpu_mem_gb:.1f} GB")
            check("PyTorch CUDA version",
                  "PASS",
                  f"torch={torch.__version__}, cuda={torch.version.cuda}")
        else:
            gpu_name = "(no GPU)"
            gpu_mem_gb = 0
            check("GPU detection", "FAIL", "No CUDA device found")
    except ImportError as e:
        check("torch import", "FAIL", str(e))
        gpu_name = "(torch not available)"
        gpu_mem_gb = 0

    # ── 5. Precipitation patch ────────────────────────────────────────────
    print("\n── 5. Precipitation patch (verify_patch) ────────────────────────")
    try:
        sys.path.insert(0, str(ROOT))
        from src.pipeline.inference import verify_patch
        patch_ok = verify_patch(raise_on_fail=False)
        check("verify_patch()", "PASS" if patch_ok else "FAIL",
              "needs_log_untransform=False for tp1h/sf1h")
    except Exception as e:
        check("verify_patch()", "FAIL", str(e))
        patch_ok = False

    # ── 6. Checkpoint loading ─────────────────────────────────────────────
    print("\n── 6. Aurora1p5 checkpoint ──────────────────────────────────────")
    checkpoint_ok = False
    try:
        from earth2studio.models.px import Aurora1p5
        t0 = time.perf_counter()
        pkg = Aurora1p5.load_default_package()
        pkg_wall = time.perf_counter() - t0
        check("Aurora1p5.load_default_package()",
              "PASS",
              f"loaded in {pkg_wall:.1f}s")
        checkpoint_ok = True
    except Exception as e:
        check("Aurora1p5 checkpoint", "FAIL", str(e))

    # ── 7. Smoke test: 1 init × 2 steps over Nepal bbox ──────────────────
    print("\n── 7. Smoke test (1 init × 2 steps, Nepal bbox) ─────────────────")
    smoke_ok = False
    smoke_wall = 0
    if checkpoint_ok and patch_ok:
        try:
            from src.pipeline.inference import load_model, run_forecast, DOMAIN_NEPAL

            t0 = time.perf_counter()
            model = load_model(device="cuda")
            load_wall = time.perf_counter() - t0
            check(f"Model loaded to GPU", "PASS", f"{load_wall:.1f}s")

            # Run 2-step forecast from first Nepal init
            smoke_init = datetime.datetime(2026, 7, 20, 0, 0, 0, tzinfo=UTC)
            t0 = time.perf_counter()
            ds = run_forecast(
                init_time=smoke_init,
                model=model,
                device="cuda",
                nsteps=2,
                verbose=True,
                domain=DOMAIN_NEPAL,
            )
            smoke_wall = time.perf_counter() - t0

            # Validate output
            n_lead = ds.sizes.get("lead_time", 0)
            n_lat  = ds.sizes.get("lat", 0)
            n_lon  = ds.sizes.get("lon", 0)
            has_vars = all(v in ds.data_vars for v in ("t2m_K", "u10m", "v10m", "tp1h_raw"))

            expected_lat = 19  # Nepal: 26.0–30.5 at 0.25°
            expected_lon = 35  # Nepal: 80.0–88.5 at 0.25°

            check(f"Smoke test output: lead_time={n_lead}, lat={n_lat}, lon={n_lon}",
                  "PASS" if (n_lead == 2 and n_lat == expected_lat and n_lon == expected_lon and has_vars) else "FAIL",
                  f"Expected (2, {expected_lat}, {expected_lon}), vars present={has_vars}")

            # Check t2m plausibility
            import numpy as np
            t2m_vals = ds["t2m_K"].values
            t2m_min, t2m_max = float(np.nanmin(t2m_vals)), float(np.nanmax(t2m_vals))
            plausible = 240.0 <= t2m_min and t2m_max <= 330.0
            check(f"t2m range: {t2m_min:.1f}–{t2m_max:.1f} K",
                  "PASS" if plausible else "WARN",
                  "Expected 240–330 K for Nepal July")

            check(f"Smoke test wall time: {smoke_wall:.1f}s", "PASS")
            smoke_ok = True

            # Free GPU memory
            del ds, model
            import torch
            torch.cuda.empty_cache()

        except Exception as e:
            import traceback
            check("Smoke test", "FAIL", str(e))
            traceback.print_exc()
    else:
        check("Smoke test", "SKIP",
              f"checkpoint_ok={checkpoint_ok}, patch_ok={patch_ok}")

    # ── 8. Summary ────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    passes = sum(1 for r in results if r["status"] == "PASS")
    warns  = sum(1 for r in results if r["status"] == "WARN")
    fails  = sum(1 for r in results if r["status"] == "FAIL")
    skips  = sum(1 for r in results if r["status"] == "SKIP")
    print(f"  {passes} PASS  {warns} WARN  {fails} FAIL  {skips} SKIP")

    output = {
        "spec_id":          "002-nepal-eval",
        "spec_version":     "v1.1",
        "generated_utc":    datetime.datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "environment": {
            "conda_env":        conda_env,
            "e2s_version":      e2s_ver,
            "gpu":              gpu_name,
            "gpu_vram_gb":      round(gpu_mem_gb, 1),
            "patch_ok":         patch_ok,
            "checkpoint_ok":    checkpoint_ok,
        },
        "smoke_test": {
            "ok":       smoke_ok,
            "wall_s":   round(smoke_wall, 1),
        },
        "overall_status":   "FAIL" if fails else ("WARN" if warns else "PASS"),
        "results":          results,
    }

    with open(OUT_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Written: {OUT_PATH}")
    print(f"{'='*70}")

    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
