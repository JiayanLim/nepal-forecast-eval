# Task List: Aurora 1.5 Inference over Nepal

**Project**: `002-nepal-eval`
**Created**: 2026-08-27
**Version**: v1.1
**Revised**: 2026-08-27 (v1.1 — inference-only; all metric computation and reporting tasks removed)
**Spec**: `specs/002-nepal-eval/spec.md` v1.1
**Plan**: `specs/002-nepal-eval/plan.md` v1.1

Status: `[ ]` open · `[~]` in progress · `[x]` done · `[!]` blocked · `[-]` removed from scope

---

## Phase P0 — Spec Kit and Quality Gate

### P0.01 — Write constitution.md v1.1.0
**Status**: [x] COMPLETE 2026-08-27

### P0.02 — Write spec.md v1.1
**Status**: [x] COMPLETE 2026-08-27

### P0.03 — Write plan.md v1.1
**Status**: [x] COMPLETE 2026-08-27

### P0.04 — Write tasks.md v1.1
**Status**: [x] COMPLETE 2026-08-27

### P0.05 — Fork Myanmar GitHub repo to Nepal repo
**Action**:
```bash
gh repo fork JiayanLim/myanmar-weather-forecast \
    --fork-name nepal-weather-forecast \
    --clone \
    --remote
```
Clone to `/Users/limjiayan/nepal-weather-forecast`.
After clone, configure upstream:
```bash
cd /Users/limjiayan/nepal-weather-forecast
git remote add upstream https://github.com/JiayanLim/myanmar-weather-forecast.git
git remote -v   # verify: origin = fork, upstream = Myanmar
```
Create working branch:
```bash
git checkout -b feature/nepal-inference
```
**Deliverable**: `JiayanLim/nepal-weather-forecast` exists on GitHub; `origin` = fork;
`upstream` = Myanmar repo; branch `feature/nepal-inference` active
**Status**: [x] COMPLETE 2026-08-27

### P0.06 — Add Spec Kit to Nepal repo and push
**Action**: Copy `specs/002-nepal-eval/` into the Nepal repo:
```bash
mkdir -p /Users/limjiayan/nepal-weather-forecast/specs/002-nepal-eval
cp /Users/limjiayan/myanmar-forecast-eval/specs/002-nepal-eval/*.md \
   /Users/limjiayan/nepal-weather-forecast/specs/002-nepal-eval/
cd /Users/limjiayan/nepal-weather-forecast
git add specs/002-nepal-eval/
git commit -m "Add Nepal inference Spec Kit v1.1 (002-nepal-eval)"
git push -u origin feature/nepal-inference
```
**Deliverable**: Spec Kit visible on GitHub at `JiayanLim/nepal-weather-forecast`
on branch `feature/nepal-inference`
**Status**: [x] COMPLETE 2026-08-27

### P0.07 — Author quality gate approval
**Status**: [~] IN PROGRESS — awaiting author review
**Blocking**: All P1–P4 tasks blocked until author approves

---

## Phase P1 — Local Setup

*All tasks blocked on P0.07 author approval.*

### P1.01 — Generate Nepal experiment calendar
**Script**: `scripts/nepal_calendar.py`
**Action**: Write `config/nepal_calendar.csv` with 14 rows.
Columns: `init_date, slug, init_datetime_utc, ic_minus6h_utc, ic_plus0h_utc,
          forecast_end_utc, era5t, valid_scope`
All `era5t` values: `TRUE`.
**Validation**: `wc -l config/nepal_calendar.csv` → 15 (header + 14 rows).
**Status**: [ ]

### P1.02 — Generate Nepal land mask
**Script**: `scripts/nepal_masks.py`
**Mirrors**: `scripts/track_b_b3_masks.py` with:
  - Country: `ADMIN == "Nepal"` (not Myanmar)
  - Grid: lats `np.arange(30.5, 25.75, -0.25)` → 19 pts; lons `np.arange(80.0, 88.75, 0.25)` → 35 pts
  - Output: `data/masks/nepal_land_mask.npy` (19, 35) bool
  - No subregion masks (not needed in inference-only scope)
  - Provenance: `data/masks/nepal_mask_provenance.json`
**Validation**: `land_mask.sum() > 0`; print cell count.
**Note**: Uses same NE shapefile already at `data/natural_earth/ne_50m_admin_0_countries.shp`.
**Status**: [ ]

### P1.03 — ARCO ERA5T access test
**Script**: `scripts/nepal_arco_test.py`
**Action**:
  - Open ARCO zarr store; select `2m_temperature` at `2026-07-20T00:00:00`
  - Subset lat 26.0–30.5°N, lon 80.0–88.5°E
  - Assert shape `(19, 35)`; assert not all-NaN; assert values in range 270–320 K
  - Print PASS / FAIL with actual min/max
**Status**: [ ]

### P1.04 — Create results directory tree
**Action**:
```bash
mkdir -p results/nepal/{forecasts,era5_ic,provenance,validation}
```
**Status**: [ ]

### P1.05 — Write Nepal experiment config
**File**: `config/nepal_experiment.json`
```json
{
  "spec_id": "002-nepal-eval",
  "spec_version": "v1.1",
  "domain": {"lat_min": 26.0, "lat_max": 30.5, "lon_min": 80.0, "lon_max": 88.5,
             "n_lat": 19, "n_lon": 35},
  "n_inits": 14,
  "init_dates": ["2026-07-20", ..., "2026-08-02"],
  "lead_hours": 168,
  "era5t": true,
  "variables": ["t2m_C", "ws_kts", "wd_deg", "tp1h_mmhr"],
  "n_land_cells": null
}
```
Fill `n_land_cells` after P1.02 completes.
**Status**: [ ]

### P1.06 — P1 Gate Check
**Script**: `scripts/nepal_p1_gate.py`
**Action**: Check all P1 acceptance criteria; write `results/nepal/validation/p1_gate.json`.
**Status**: [ ]

---

## Phase P2 — ERA5T IC Acquisition

*Blocked on P1 gate PASS.*

### P2.01 — Write ERA5T IC retrieval script
**Script**: `scripts/nepal_era5_ic.py`
**Action**: For each of 14 slugs from `nepal_calendar.csv`:
  - Read `ic_minus6h_utc` and `ic_plus0h_utc` from calendar
  - Fetch **all Aurora input variables** from ARCO at both IC timesteps
    (same variable list as Myanmar `r4_full_run.py` IC fetch)
  - Store global fields (720 × 1440): `results/nepal/era5_ic/{slug}_era5_ic.nc`
    - Dims: `(ic_step: 2, lat: 720, lon: 1440)`
    - Coord `ic_datetime`: [t−6h, t+0h]
    - Global attrs: `era5t: true`, `slug`, `arco_path`, `retrieval_utc`, `ic_datetimes_utc`
  - Write `results/nepal/provenance/{slug}_era5_ic_provenance.json`
**Mirrors**: IC fetch portion of `scripts/r4_full_run.py` (Myanmar)
**Status**: [ ]

### P2.02 — Run ERA5T IC retrieval
**Action**: `python scripts/nepal_era5_ic.py`
Expected time: ~5–20 min (14 inits × 2 timesteps × global field download).
Expected disk: ~1–2 GB.
**Status**: [ ]

### P2.03 — Validate IC files
**Script**: `scripts/nepal_era5_ic_validate.py`
**Checks**:
  - 14/14 NC files exist, non-empty
  - Shape `(2, 720, 1440)` for each variable
  - No all-NaN global fields
  - t2m range 200–340 K globally
  - `era5t: true` in global attrs
  - Provenance JSON exists per slug
**Output**: `results/nepal/validation/p2_gate.json`
**Status**: [ ]

### P2.04 — P2 Gate
**Criterion**: `p2_gate.json` shows 14/14 PASS before Brev session started.
**Status**: [ ]

---

## Phase P3 — Aurora Inference (Brev A100)

*Blocked on P2 gate PASS. Requires active Brev A100 session.*

### P3.01 — Provision Brev A100 instance
**Action**: Launch A100 80GB on-demand via Brev CLI. Confirm `nvidia-smi` shows GPU.
Start tmux session. Set:
```bash
export EARTH2STUDIO_CACHE=/ephemeral/.cache/earth2studio
export HF_HOME=/ephemeral/.cache/huggingface
```
**Status**: [ ]

### P3.02 — Verify precipitation patch
**Action**:
```bash
E2S_PATH=$(python -c "import earth2studio, os; print(os.path.dirname(earth2studio.__file__))")
grep -n "needs_log_untransform" $E2S_PATH/models/px/aurora1p5.py | head -6
```
Expected: lines 128 and 129 both show `False`.
If either shows `True`: apply patch before continuing.
Record patch confirmation in a file: `echo "PATCH_CONFIRMED" > /ephemeral/patch_status.txt`
**Status**: [ ]

### P3.03 — Transfer IC files and calendar to Brev
**Action**: `scp -r results/nepal/era5_ic/ config/nepal_calendar.csv <brev_host>:/ephemeral/nepal/`
Also transfer `scripts/nepal_inference.py`.
**Status**: [ ]

### P3.04 — Write Nepal inference script
**Script**: `scripts/nepal_inference.py`
**Mirrors**: `scripts/r4_full_run.py` with:
  - IC loaded from pre-fetched NC files (not fetched from ARCO on Brev)
  - Aurora runs globally (full 720×1440 grid)
  - After each 1h step: extract Nepal bbox (lat 26.0–30.5, lon 80.0–88.5)
  - Compute t2m_C, ws_kts, wd_deg, tp1h_mmhr (post-patch, clip ≥ 0)
  - Track n_neg (raw tp1h < 0)
  - Accumulate 168 steps; save as `results/nepal/forecasts/{slug}_aurora.nc`
  - Write provenance JSON including: git_commit, brev_instance_id, wall_seconds,
    patch_confirmed, n_neg, checkpoint_hash, e2s_version, ic_file_path
**Note**: IC files are pre-loaded on Brev (not fetched from ARCO during inference).
This keeps P3 self-contained and prevents ARCO network issues from blocking inference.
**Status**: [ ]

### P3.05 — Benchmark test (single init)
**Action**: Run `python scripts/nepal_inference.py --slug 20260720 --test`
Check:
- Wall time < 450s
- Output NC exists, shape (168, 19, 35)
- `tp1h_mmhr.max() > 0.01` and `tp1h_mmhr.max() < 500` (patch sanity check)
- `t2m_C.min() > -40` and `t2m_C.max() < 60`
If any check fails: **STOP**. Do not proceed to full run.
**Status**: [ ]

### P3.06 — Full inference run (all 14 inits)
**Action**: `python scripts/nepal_inference.py` (all 14 inits) in tmux.
Monitor: no zero-byte files, no OOM errors.
**Status**: [ ]

### P3.07 — On-Brev P3 gate check
**Script**: `scripts/nepal_p3_gate.py` (brief check script transferred in P3.03)
**Checks**: 14/14 files exist; shape (168, 19, 35); all 4 vars; non-empty.
**Output**: print PASS/FAIL per slug; write `p3_gate_brev.json`.
**Status**: [ ]

### P3.08 — Transfer forecast outputs to local archive
**Action**:
```bash
scp -r <brev_host>:/ephemeral/nepal/forecasts/ \
    /Users/limjiayan/Downloads/nepal_aurora_archive/forecasts/
scp -r <brev_host>:/ephemeral/nepal/provenance/ \
    /Users/limjiayan/Downloads/nepal_aurora_archive/provenance/
```
Verify: `ls /Users/limjiayan/Downloads/nepal_aurora_archive/forecasts/ | wc -l` → 14
**Status**: [ ]

### P3.09 — Shut down Brev instance
**Action**: Only after local transfer confirmed. Terminate Brev instance.
**Status**: [ ]

---

## Phase P4 — Inference Output Validation

*Blocked on P3 gate PASS and local transfer confirmed.*

### P4.01 — Write output validation script
**Script**: `scripts/nepal_validate_outputs.py`
**Action**: For each of 14 slugs, run all structural checks from spec.md §10:
  - File exists, non-empty
  - Shape (168, 19, 35)
  - Lead hours 1–168 present and monotone
  - All 4 variables present
  - No all-NaN step
  - Range checks (t2m_C, ws_kts, tp1h_mmhr)
  - tp1h_mmhr ≥ 0 everywhere (post-clip)
  - `patch_confirmed: true` in global attrs
  - Provenance JSON exists and valid
**Output per slug**: dict with each check name → "PASS" / "WARN" / "FAIL"
**Status**: [ ]

### P4.02 — Run validation
**Action**: `python scripts/nepal_validate_outputs.py`
**Output**: `results/nepal/validation/p4_checks.json` — 14 entries, one per slug.
Print summary table: check name × slug → PASS/WARN/FAIL.
**Status**: [ ]

### P4.03 — Generate experiment manifest
**Script**: `scripts/nepal_manifest.py`
**Action**: Read `p4_checks.json`, `nepal_calendar.csv`, each provenance JSON.
Assemble `results/nepal/manifest.json` (schema in spec.md §9).
Compute:
  - `n_complete`: slugs with zero FAIL checks
  - `n_failed`: slugs with ≥1 FAIL check
  - `patch_confirmed_all`: True only if all provenance JSONs have `patch_confirmed: true`
  - `n_land_cells`: from `nepal_land_mask.npy` (loaded from local)
**Status**: [ ]

### P4.04 — Final manifest check
**Action**: Print manifest summary. Verify:
  - `n_complete == 14`
  - `n_failed == 0`
  - `patch_confirmed_all == true`
If any FAIL: investigate the failing slug; document in task notes here.
**Status**: [ ]

### P4.05 — Commit final outputs to Nepal repo
**Action**: In `/Users/limjiayan/nepal-weather-forecast`:
  - Copy: `config/nepal_calendar.csv`, `config/nepal_experiment.json`
  - Copy: `results/nepal/manifest.json`
  - Copy: `results/nepal/validation/` (all gate JSONs)
  - Copy: `data/masks/nepal_land_mask.npy`, `nepal_mask_provenance.json`
  - Copy: all scripts (`scripts/nepal_*.py`)
  - **Do NOT commit**: forecast NC files, IC NC files (too large for GitHub)
  - Add `results/nepal/forecasts/` and `results/nepal/era5_ic/` to `.gitignore`
  - Commit and push to `feature/nepal-inference`
**Status**: [ ]

---

## Removed from Scope (v1.1)

The following tasks were in v1.0 and have been removed. They are preserved here for
the record and can be re-activated in a future metric-computation project.

| Removed Task | Original Phase | Reason Removed |
|---|---|---|
| Track A domain-mean lead-time curves | P4 | Metric computation out of scope |
| Track B spatial error maps | P4 | Metric computation out of scope |
| Track C subregion analysis | P4 | Metric computation out of scope |
| Track D precipitation categorical metrics | P4 | Metric computation out of scope |
| Track E Nepal vs Myanmar comparison | P4 | Removed entirely (no metrics basis) |
| Lead-time curve plots | P5 | Depends on removed metrics |
| Spatial maps plot | P5 | Depends on removed metrics |
| Precipitation categorical plot | P5 | Depends on removed metrics |
| Nepal evaluation report (md + pdf) | P5 | Depends on removed metrics |
| Block bootstrap (not applicable) | — | n=14 always insufficient |
| SEEPS computation | — | No climatology for Nepal domain |

---

## Files Reused from Myanmar Pipeline

| Myanmar file | Nepal usage |
|---|---|
| `data/natural_earth/ne_50m_admin_0_countries.shp` | Extract Nepal polygon for land mask |
| `scripts/track_b_b3_masks.py` | Mirror → `scripts/nepal_masks.py` |
| `scripts/r4_full_run.py` | Mirror → `scripts/nepal_inference.py` (IC load + inference) |
| `src/metrics/` | NOT used in inference-only scope |

---

*Tasks v1.1 — 2026-08-27.*
