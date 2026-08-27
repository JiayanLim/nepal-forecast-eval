# Research Plan: Aurora 1.5 Inference over Nepal

**Project**: `002-nepal-eval`
**Created**: 2026-08-27
**Version**: v1.1
**Revised**: 2026-08-27 (v1.1 — inference-only; removed P4 metric computation and P5 reporting)
**Spec**: `specs/002-nepal-eval/spec.md` v1.1
**Constitution**: `specs/002-nepal-eval/constitution.md` v1.1.0
**Status**: P0 IN PROGRESS (quality gate pending author approval)

---

## Overview

Four active phases. Phases P0–P2 are local (no GPU). P3 is on Brev A100. P4 is local
output validation.

```
P0 → P1 → P2 → P3 → P4
                ↑
           Brev A100
           ~72 min
           ~$10–15
```

No metric computation. No evaluation. No figures. No report.
The final deliverable is 14 validated Aurora forecast NC files + manifest.

---

## Phase P0 — Spec Kit and Quality Gate

**Status**: IN PROGRESS — author review pending
**Objective**: Author reviews and approves spec before any code is run or data is fetched.

### Deliverables
- [x] `specs/002-nepal-eval/constitution.md` v1.1.0
- [x] `specs/002-nepal-eval/spec.md` v1.1
- [x] `specs/002-nepal-eval/plan.md` v1.1
- [x] `specs/002-nepal-eval/tasks.md` v1.1
- [ ] Fork of `JiayanLim/myanmar-weather-forecast` → `JiayanLim/nepal-weather-forecast`
- [ ] Branch `feature/nepal-inference` created in fork
- [ ] Author approval of quality gate

### Acceptance Criteria
- [ ] Author explicitly approves 10-item quality gate
- [ ] Nepal GitHub repo exists with correct remote configuration (origin = fork, upstream = Myanmar)
- [ ] Branch `feature/nepal-inference` active
- [ ] No GPU resources provisioned until gate is passed

---

## Phase P1 — Local Setup

**Prerequisite**: P0 gate PASSED
**Objective**: Create Nepal calendar, land mask, directory structure, and ARCO access test.
All tasks run locally; no GPU, no external cost.

### Tasks
1. Generate `config/nepal_calendar.csv` (14 rows, ERA5T flag)
2. Run `scripts/nepal_masks.py` → `data/masks/nepal_land_mask.npy`
3. Run ARCO ERA5T access test → confirm Nepal bbox returns valid data
4. Create `results/nepal/{forecasts,era5_ic,provenance,validation}/` directory tree
5. Write `config/nepal_experiment.json` (domain, grid, n_inits, n_land_cells)

### Acceptance Criteria
- `nepal_calendar.csv` has exactly 14 rows (2026-07-20 through 2026-08-02)
- `nepal_land_mask.npy` shape is (19, 35); sum > 0
- ARCO test: Nepal bbox t2m field at 2026-07-20 00Z is non-NaN, range 270–320 K
- `nepal_experiment.json` exists with correct domain metadata

### Gate: P1
Write `results/nepal/validation/p1_gate.json` — all criteria PASS before continuing.

---

## Phase P2 — ERA5T Initial Condition Acquisition

**Prerequisite**: P1 gate PASSED
**Objective**: Fetch and store the ERA5T fields used as Aurora initial conditions for
all 14 initialisations. This is the model's input data, not verification data.

### What is fetched

For each of 14 slugs: ERA5T at exactly **two timesteps**:
- `init_datetime − 6h` (t−6h)
- `init_datetime + 0h` (t+0h)

Aurora requires these two consecutive IC timesteps. This is the only ERA5T data fetched.

**Important**: Aurora runs on the full global grid. IC fields must be fetched at global
resolution (720 × 1440). Nepal-bbox subsetting applies only to forecast outputs.

### Storage schema

File: `results/nepal/era5_ic/{slug}_era5_ic.nc`
- Dims: `(ic_step: 2, lat: 720, lon: 1440)`
- Variables: all fields required by `Aurora1p5` (t2m, u10m, v10m, msl, geopotential on
  pressure levels, specific humidity, etc. — same fields as Myanmar `r4_full_run.py`)
- Global attrs: `era5t: true`, `slug`, `ic_datetimes_utc`, `arco_path`, `retrieval_utc`

### Provenance

File: `results/nepal/provenance/{slug}_era5_ic_provenance.json`
- ARCO path, retrieval timestamp, ic_datetimes, era5t flag, variable list, shape

### Acceptance Criteria
- 14/14 IC NC files exist and are non-empty
- Shape `(2, 720, 1440)` for each variable
- No all-NaN global fields
- t2m values 200–340 K plausible globally
- Provenance JSON complete for each slug

### Gate: P2
Write `results/nepal/validation/p2_gate.json` — all 14 IC files validated before
Brev session is started.

**Note**: IC files are large (~global ERA5 fields). Estimated storage: ~14 × 2 steps ×
~50 MB per step ≈ ~1.4 GB. Ensure local disk space before running.

---

## Phase P3 — Aurora Inference (Brev A100)

**Prerequisite**: P2 gate PASSED; Brev instance active
**Objective**: Run Aurora 1.5 inference for all 14 initialisations; store forecast
outputs as NetCDF; write provenance for each.

### Pre-flight checklist

- [ ] Precipitation patch confirmed: `aurora1p5.py` lines 128–129 both `needs_log_untransform=False`
- [ ] `EARTH2STUDIO_CACHE` → `/ephemeral`; `HF_HOME` → `/ephemeral`
- [ ] Aurora checkpoint cached or downloaded
- [ ] tmux session active before launching
- [ ] IC files transferred to Brev from local machine

### Inference procedure (per init)

1. Load IC from `{slug}_era5_ic.nc` (already fetched in P2; avoids ARCO fetch on Brev)
2. Run `Aurora1p5.create_iterator(x, coords)`; iterate 168 steps
3. At each step: extract Nepal bbox (lat 26.0–30.5°N, lon 80.0–88.5°E)
4. Compute: `t2m_C`, `ws_kts`, `wd_deg`, `tp1h_mmhr` (post-patch, post-clip)
5. Record `n_neg` (raw tp1h < 0 count)
6. Accumulate 168 steps; save `results/nepal/forecasts/{slug}_aurora.nc`
7. Write `results/nepal/provenance/{slug}_aurora_provenance.json`
   including `git_commit`, `brev_instance_id`, `wall_seconds`, `patch_confirmed`

### Benchmark test before full run

Run inference for slug `20260720` only. Verify:
- Wall time < 450s
- `tp1h_mmhr` max value > 0.01 mm/hr (confirms patch applied; if max is ~0.00001, patch missing)
- `tp1h_mmhr` max value < 500 mm/hr (confirms not a runaway value)
- Output NC shape `(168, 19, 35)`

If benchmark fails: STOP. Fix the issue. Do not proceed to full run.

### Full run

After benchmark PASS: run all 14 inits sequentially in tmux.
Monitor for zero-byte files and OOM errors.

### Transfer and archive

After all 14 NC files confirmed on Brev:
1. Download to local: `/Users/limjiayan/Downloads/nepal_aurora_archive/`
2. Confirm file count (14) and total size before shutting down Brev
3. Shut down Brev instance

### Acceptance Criteria
- 14/14 forecast NC files: non-empty, shape `(168, 19, 35)`, all 4 variables present
- 14/14 provenance JSON files complete
- `patch_confirmed: true` in every provenance JSON
- `tp1h_mmhr` values physically plausible (see §10 spec validation table)
- Local archive transfer confirmed before Brev shutdown

### Gate: P3
Write `results/nepal/validation/p3_gate.json` — 14/14 files validated on Brev before transfer.

---

## Phase P4 — Inference Output Validation

**Prerequisite**: P3 gate PASSED; all files transferred to local machine
**Objective**: Run structural validation checks against every forecast file;
generate the experiment manifest; confirm the deliverable is complete.

No metrics computed. No ERA5T verification data fetched beyond P2 IC files.

### Tasks

1. Run `scripts/nepal_validate_outputs.py` — executes all checks from spec.md §10
   against each of 14 forecast NC files
2. Aggregate results into `results/nepal/validation/p4_checks.json`
   (one entry per slug, each check result pass/warn/fail)
3. Generate `results/nepal/manifest.json` — complete experiment manifest
   (see spec.md §9 for required fields)
4. Final human-readable summary: print counts of PASS / WARN / FAIL per check

### Acceptance Criteria
- All 14 slugs: zero FAIL checks
- Manifest `n_complete == 14`, `n_failed == 0`
- `manifest.json` passes JSON schema validation (all required keys present)
- `patch_confirmed_all == true` in manifest

### Gate: P4 (Final Gate)
`results/nepal/manifest.json` exists with `n_complete: 14`, `n_failed: 0`.
This is the project completion criterion.

---

## Final Deliverable

```
results/nepal/
  forecasts/          14 × {slug}_aurora.nc
  era5_ic/            14 × {slug}_era5_ic.nc
  provenance/         28 × JSON files (14 forecast + 14 IC)
  validation/         p1_gate.json, p2_gate.json, p3_gate.json, p4_checks.json
  manifest.json       machine-readable experiment manifest

config/
  nepal_calendar.csv
  nepal_experiment.json

data/masks/
  nepal_land_mask.npy
  nepal_mask_provenance.json

specs/002-nepal-eval/
  constitution.md, spec.md, plan.md, tasks.md
```

---

## Budget

| Item | Estimate |
|------|---------|
| Brev A100 inference (~1.2 hrs on-demand) | $7.50 |
| Brev setup/transfer/overhead (~0.5 hrs) | $3.00 |
| **Total estimated** | **~$10.50** |

---

*Plan v1.1 — 2026-08-27.*
