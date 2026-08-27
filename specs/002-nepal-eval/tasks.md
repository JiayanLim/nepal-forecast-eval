# Task List: Aurora 1.5 Inference over Nepal

**Project**: `002-nepal-eval`
**Created**: 2026-08-27
**Version**: v1.2
**Revised**: 2026-08-27 (v1.2 — P1/P2 complete; P3 restructured; expanded exclusions)
**Spec**: `specs/002-nepal-eval/spec.md` v1.2
**Plan**: `specs/002-nepal-eval/plan.md` v1.2

Status: `[ ]` open | `[~]` in progress | `[x]` done | `[!]` blocked | `[-]` removed

---

## Phase P0 — Spec Kit and Quality Gate

### P0.01 — Write constitution.md
**Status**: [x] COMPLETE 2026-08-27

### P0.02 — Write spec.md
**Status**: [x] COMPLETE 2026-08-27

### P0.03 — Write plan.md
**Status**: [x] COMPLETE 2026-08-27

### P0.04 — Write tasks.md
**Status**: [x] COMPLETE 2026-08-27

### P0.05 — Create Nepal GitHub repo
**Action**: Created `JiayanLim/nepal-forecast-eval` as new repo (not a fork).
Source: 19 files from `/Users/limjiayan/myanmar-forecast-eval` (Aurora 1.5 pipeline).
Branch: `feature/nepal-inference`. No upstream remote.
**Status**: [x] COMPLETE 2026-08-27 (root commit fb42dbd)

---

## Phase P1 — Local Setup

### P1.01 — Generate Nepal experiment calendar
**Script**: `scripts/nepal_calendar.py`
**Output**: `config/nepal_calendar.csv` — 14 rows (2026-07-20 through 2026-08-02)
**Status**: [x] COMPLETE 2026-08-27

### P1.02 — Generate Nepal land mask
**Script**: `scripts/nepal_masks.py`
**Output**: `data/masks/nepal_land_mask.npy` — (19, 35) bool, 221 land cells
**Status**: [x] COMPLETE 2026-08-27

### P1.03 — ARCO ERA5T access test
**Script**: `scripts/nepal_arco_test.py`
**Output**: `results/nepal/validation/p1_arco_test.json` — 8/8 PASS
**Status**: [x] COMPLETE 2026-08-27

### P1.04 — Create results directory tree
**Status**: [x] COMPLETE 2026-08-27

### P1.05 — Write Nepal experiment config
**Output**: `config/nepal_experiment.json`
**Status**: [x] COMPLETE 2026-08-27

### P1.06 — P1 Gate
**Result**: All criteria PASS. Commit 5b870a0.
**Status**: [x] COMPLETE 2026-08-27

---

## Phase P2 — ERA5T IC Acquisition

ERA5T is used as the **initial condition** for Aurora inference only. It is NOT
training data, fine-tuning data, or verification data.

### P2.01 — Write ERA5T IC retrieval script
**Script**: `scripts/nepal_era5_ic.py`
**Status**: [x] COMPLETE 2026-08-27

### P2.02 — Run ERA5T IC retrieval
**Result**: 14/14 IC NetCDF files, 213.5 MB total, 215.5s wall time
**Status**: [x] COMPLETE 2026-08-27

### P2.03 — Validate IC files
**Result**: All 14 files validated (shape, NaN, attrs). p2_manifest.json PASS.
**Status**: [x] COMPLETE 2026-08-27

### P2.04 — P2 Gate
**Result**: 14/14 PASS. Commit e10a70b.
**Status**: [x] COMPLETE 2026-08-27

---

## Phase P3 — Aurora Inference (Brev A100)

*Blocked on: user creates Brev A100 instance and provides instance name.*

### Stage 1: Brev Environment Validation (P3.01-P3.05)

All must PASS before any inference. STOP after P3.05 for user approval.

### P3.01 — Connect to Brev instance
**Action**: Connect via `brev shell <instance-name>`. Verify Nepal project is cloned
and on `feature/nepal-inference` branch.
**Status**: [ ] GATED

### P3.02 — Verify aurora_env
**Action**: Confirm `CONDA_DEFAULT_ENV == aurora_env`.
**Status**: [ ] GATED

### P3.03 — Verify Earth2Studio version
**Action**: Confirm `earth2studio.__version__ == 0.17.0`.
**Status**: [ ] GATED

### P3.04 — Verify CUDA/PyTorch/A100
**Action**: Confirm `torch.cuda.is_available()`, `torch.cuda.get_device_name(0)`
contains "A100", VRAM >= 75 GB.
**Status**: [ ] GATED

### P3.05 — Run environment check and smoke test
**Script**: `scripts/nepal_brev_check.py`
**Checks**:
1. Nepal project directory (spec_id == 002-nepal-eval)
2. aurora_env active
3. E2S == 0.17.0
4. CUDA/A100/VRAM
5. `verify_patch()` returns True
6. `Aurora1p5.load_default_package()` loads checkpoint
7. 2-step smoke test: output shape (2, 19, 35), t2m plausible
8. Full report to `results/nepal/validation/p3_brev_check.json`
**GATE**: STOP and report checkpoint. Do NOT proceed to P3.06 until user approves.
**Status**: [ ] GATED

### Stage 2: Full Inference (P3.06)

**P3.06 — Full 14-init Aurora inference**
*Blocked on: P3.05 checkpoint approved by user.*
**Script**: `scripts/nepal_inference.py`
**Action**: Run all 14 inits (168h each) sequentially in tmux.
E2S fetches IC from ARCO at inference time. Nepal bbox extracted per step.
Resumable (skips valid files). Atomic writes.
**Outputs**:
- `results/nepal/forecasts/{slug}_aurora.nc` x 14
- `results/nepal/provenance/{slug}_aurora_provenance.json` x 14
- `results/nepal/manifest.json`
**Status**: [ ] GATED

### Stage 3: Output Validation (P3.07)

**P3.07 — Structural validation of forecast outputs**
**Action**: Validate all 14 forecast NC files against spec section 9 checks.
Shape (168, 19, 35), 4 vars, patch_confirmed, range checks.
**Status**: [ ] GATED

---

## Phase P4 — Local Validation and Archiving

*Blocked on P3 gate PASS.*

### P4.01 — Transfer forecast files to local archive
**Status**: [ ] GATED

### P4.02 — Local structural validation
**Status**: [ ] GATED

### P4.03 — Generate final experiment manifest
**Status**: [ ] GATED

### P4.04 — Commit outputs to git
**Note**: NC files are gitignored. Only scripts, configs, provenance, validation
JSONs, and manifest are committed.
**Status**: [ ] GATED

---

## Out of Scope (Explicit Exclusions)

The following are NOT part of this project. Preserved for reference.

### Evaluation Metrics — NOT computed
| Metric | Status | Reason |
|--------|--------|--------|
| MAE | [-] removed | Inference-only scope |
| RMSE | [-] removed | Inference-only scope |
| Bias | [-] removed | Inference-only scope |
| CMAE | [-] removed | Inference-only scope |
| ETS | [-] removed | Inference-only scope |
| POD | [-] removed | Inference-only scope |
| FAR | [-] removed | Inference-only scope |
| Frequency Bias | [-] removed | Inference-only scope |
| SEEPS | [-] removed | Inference-only scope |
| Pearson r | [-] removed | Inference-only scope |
| CSI | [-] removed | Inference-only scope |

### Evaluation Tracks — NOT executed
| Track | Status | Reason |
|-------|--------|--------|
| Track A (domain-mean lead-time curves) | [-] removed | Depends on metrics |
| Track B (spatial error maps) | [-] removed | Depends on metrics |
| Track C (subregion analysis) | [-] removed | Depends on metrics |
| Track D (precipitation categorical) | [-] removed | Depends on metrics |
| Track E (Nepal vs Myanmar comparison) | [-] removed | No metrics basis |

### Other Exclusions
| Item | Status | Reason |
|------|--------|--------|
| Statistical inference | [-] removed | No metrics to test |
| Bootstrap CIs | [-] removed | n=14 insufficient; no metrics |
| Nepal/Myanmar comparison | [-] removed | Out of scope |
| Figures/plots | [-] removed | No metrics to visualise |
| Thesis chapters | [-] removed | Not part of Nepal project |
| PDF/report generation | [-] removed | Not part of Nepal project |
| Model training | [-] removed | Zero-shot only |
| Fine-tuning | [-] removed | Zero-shot only |
| PEFT/LoRA | [-] removed | Zero-shot only |

---

*Tasks v1.2 — 2026-08-27.*
