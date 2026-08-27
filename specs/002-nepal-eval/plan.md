# Research Plan: Aurora 1.5 Inference over Nepal

**Project**: `002-nepal-eval`
**Created**: 2026-08-27
**Version**: v1.2
**Revised**: 2026-08-27 (v1.2 — P1/P2 complete; P3 split into env gate + inference)
**Spec**: `specs/002-nepal-eval/spec.md` v1.2
**Constitution**: `specs/002-nepal-eval/constitution.md` v1.2.0

---

## Overview

Four active phases. P0-P2 are local (no GPU). P3 is on Brev A100. P4 is local
output validation.

```
P0 (DONE) -> P1 (DONE) -> P2 (DONE) -> P3 (GATED) -> P4 (GATED)
                                          |
                                     Brev A100
                                     ~72 min
                                     ~$10-15
```

No metric computation. No evaluation. No figures. No report.
The final deliverable is 14 validated Aurora forecast NC files + manifest.

This is a zero-shot inference experiment. ERA5T is used as the initial condition only.
No training, fine-tuning, PEFT, or model modification of any kind.

---

## Phase P0 — Spec Kit and Quality Gate

**Status**: COMPLETE

### Deliverables
- [x] constitution.md, spec.md, plan.md, tasks.md
- [x] Repository: `JiayanLim/nepal-forecast-eval` (new, not a fork)
- [x] Branch: `feature/nepal-inference`
- [x] No upstream remote; origin = nepal-forecast-eval

---

## Phase P1 — Local Setup

**Status**: COMPLETE (commit 5b870a0)

### Completed Tasks
- [x] `config/nepal_calendar.csv` — 14 rows (2026-07-20 through 2026-08-02)
- [x] `data/masks/nepal_land_mask.npy` — (19, 35) bool, 221 land cells
- [x] ARCO ERA5T access test — 8/8 PASS (`results/nepal/validation/p1_arco_test.json`)
- [x] `config/nepal_experiment.json` — full domain/model/ERA5T config
- [x] Directory tree created

---

## Phase P2 — ERA5T Initial Condition Acquisition

**Status**: COMPLETE (commit e10a70b)

ERA5T is used as the **initial condition** for Aurora inference. It is NOT training
data, fine-tuning data, or verification data.

### Completed Tasks
- [x] `scripts/nepal_era5_ic.py` — retrieval script
- [x] 14/14 IC NetCDF files retrieved: `results/nepal/era5_ic/{slug}_era5_ic.nc`
- [x] Dims: (ic_step: 2, latitude: 721, longitude: 1440) — global
- [x] Surface vars: t2m_K, u10m_ms, v10m_ms, msl_Pa, tp_raw_m
- [x] 5/5 pressure-level variable names confirmed in ARCO
- [x] 14/14 provenance JSONs written
- [x] Manifest: `results/nepal/validation/p2_manifest.json` — overall_status: PASS
- [x] Total: 213.5 MB, 215.5s wall time

---

## Phase P3 — Aurora Inference (Brev A100)

**Status**: GATED — awaiting Brev instance + environment checkpoint approval

**Prerequisites**:
1. P2 gate PASSED (done)
2. User creates Brev A100 instance via web console
3. User provides instance name to Claude Code
4. Environment validation checkpoint approved by user
5. Full inference explicitly approved by user after checkpoint review

### Stage 1: Environment Validation (P3.01-P3.05)

These must ALL PASS before any forecast inference runs.

**P3.01** — Connect to Brev instance; verify Nepal project directory
**P3.02** — Verify `aurora_env` conda environment active
**P3.03** — Verify `earth2studio.__version__ == 0.17.0`
**P3.04** — Verify CUDA/PyTorch sees A100 80GB
**P3.05** — Run environment check script:
  - `verify_patch()` returns True
  - `Aurora1p5.load_default_package()` loads checkpoint
  - 2-step smoke test over Nepal bbox: output shape (2, 19, 35), t2m plausible
  - Report: GPU model, VRAM, CUDA/PyTorch/E2S versions, patch result, smoke wall time

**GATE**: Stop and report P3 environment checkpoint. Do NOT proceed to P3.06 until
the user explicitly approves after reviewing the checkpoint results.

### Stage 2: Full Inference (P3.06)

**P3.06** — Run all 14 initialisations (168h each)
  - Script: `scripts/nepal_inference.py`
  - E2S fetches IC from ARCO at inference time (consistent with Myanmar workflow)
  - Nepal bbox extracted at each step
  - Unit conversions applied; n_neg recorded
  - Atomic writes (.tmp -> rename); resumable (skips valid files)
  - Outputs: `results/nepal/forecasts/{slug}_aurora.nc` + provenance JSON
  - Final: `results/nepal/manifest.json`

### Stage 3: Output Validation (P3.07)

**P3.07** — Structural validation of all 14 forecast files
  - Shape (168, 19, 35)
  - All 4 variables present
  - patch_confirmed attribute
  - Range checks (t2m_C, ws_kts, tp1h_mmhr)
  - Provenance JSON exists per slug

### Acceptance Criteria
- 14/14 forecast NC files: shape (168, 19, 35), all 4 vars
- 14/14 provenance JSONs complete
- `patch_confirmed: "true"` in every file
- `tp1h_mmhr >= 0` everywhere
- `manifest.json` with n_complete=14, n_failed=0

---

## Phase P4 — Local Validation and Archiving

**Status**: GATED on P3

### Tasks
- [ ] Transfer forecast files from Brev to local archive
- [ ] Run structural validation locally
- [ ] Generate final `results/nepal/manifest.json`
- [ ] Commit scripts and validation outputs to git (NC files gitignored)
- [ ] Confirm deliverable complete

---

## Final Deliverable

```
results/nepal/
  forecasts/          14 x {slug}_aurora.nc        (gitignored)
  era5_ic/            14 x {slug}_era5_ic.nc       (gitignored)
  provenance/         28 x JSON (14 forecast + 14 IC)
  validation/         p1, p2, p3 gate files
  manifest.json       machine-readable experiment manifest

config/               nepal_calendar.csv, nepal_experiment.json
data/masks/           nepal_land_mask.npy, nepal_mask_provenance.json
specs/002-nepal-eval/ constitution.md, spec.md, plan.md, tasks.md
scripts/              all pipeline scripts
```

---

## Budget

| Item | Estimate |
|------|---------|
| Brev A100 inference (~1.2 hrs on-demand) | $7.50 |
| Brev setup/transfer/overhead (~0.5 hrs) | $3.00 |
| **Total estimated** | **~$10.50** |

---

*Plan v1.2 — 2026-08-27.*
