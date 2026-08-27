# Task List: Aurora 1.5 Inference over Nepal

**Project**: `002-nepal-eval`
**Created**: 2026-08-27
**Version**: v1.3
**Revised**: 2026-08-27 (v1.3 — P3 COMPLETE; consolidated dataset; findings documented)
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

### Stage 1: Brev Environment Validation (P3.01-P3.05)

### P3.01 — Connect to Brev instance
**Action**: Connected via SSH to lexical-gray-vulture (shadeform@154.54.100.230).
Repo cloned, branch feature/nepal-inference checked out.
**Status**: [x] COMPLETE 2026-08-27

### P3.02 — Verify aurora_env
**Action**: aurora_env conda environment created and activated (Python 3.11).
**Status**: [x] COMPLETE 2026-08-27

### P3.03 — Verify Earth2Studio version
**Action**: earth2studio 0.17.0 confirmed.
**Status**: [x] COMPLETE 2026-08-27

### P3.04 — Verify CUDA/PyTorch/A100
**Action**: A100-SXM4-80GB confirmed, CUDA available, PyTorch 2.6.x.
**Status**: [x] COMPLETE 2026-08-27

### P3.05 — Run environment check and smoke test
**Script**: `scripts/nepal_brev_check.py`
**Result**: 12/12 PASS. 2-step smoke test output (2, 19, 35). p3_brev_check.json written.
User approved checkpoint.
**Status**: [x] COMPLETE 2026-08-27

### Stage 2: Full Inference (P3.06)

### P3.06 — Full 14-init Aurora inference
**Script**: `scripts/nepal_inference.py`
**Result**: 14/14 SUCCESS. Zero failures, zero retries.
Total wall time: 4,020.5s (67.0 min). VRAM peak: 25,740 MB. Storage: 18.7 MB.
**Outputs**:
- `results/nepal/forecasts/{slug}_aurora.nc` × 14
- `results/nepal/provenance/{slug}_aurora_provenance.json` × 14
- `results/nepal/manifest.json`
**Forensic**: Precipitation forensic analysis completed. 32,024 negatives (2.05%)
pre-clip, originating from Aurora NN decoder. Documented in
`results/nepal/validation/precip_forensic_report.json`.
**Status**: [x] COMPLETE 2026-08-27

### Stage 3: Output Validation (P3.07)

### P3.07 — Structural validation of forecast outputs
**Action**: Validated all 14 forecast NC files. Dimensions (168, 19, 35), 4 variables,
no NaN, lead_time 1–168, init_time matches calendar, provenance attributes consistent.
**Result**: 14/14 PASS.
**Output**: `results/nepal/validation/p307_structural_validation.json`
**Status**: [x] COMPLETE 2026-08-27

### P3.08 — Consolidated research dataset
**Action**: Compiled 14 forecast files into single dataset with init_time dimension.
**Output**: `results/nepal/dataset/nepal_aurora1p5_20260720_20260802.nc` (18.27 MB)
**SHA-256**: `fea40f1804d87c10cf1b7f1454c98fc9d1b935f70f0b6fa60ca329d1bc7b59db`
**Manifest**: `results/nepal/dataset/nepal_aurora1p5_dataset_manifest.json`
**Status**: [x] COMPLETE 2026-08-27

### P3.09 — Findings documentation
**Output**: `docs/nepal_aurora1p5_findings.md`
**Status**: [x] COMPLETE 2026-08-27

---

## Phase P4 — Local Validation and Archiving

*Blocked on P3 gate PASS. P3 gate is now PASS.*

### P4.01 — Transfer forecast files to local archive
**Status**: [ ] OPEN

### P4.02 — Local structural validation
**Status**: [ ] OPEN

### P4.03 — Generate final experiment manifest
**Status**: [ ] OPEN

### P4.04 — Commit outputs to git
**Note**: NC files are gitignored. Only scripts, configs, provenance, validation
JSONs, and manifest are committed.
**Status**: [ ] OPEN

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

*Tasks v1.3 — 2026-08-27.*
