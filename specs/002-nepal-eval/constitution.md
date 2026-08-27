# Constitution: Aurora 1.5 Inference over Nepal
**Spec ID**: 002-nepal-eval
**Version**: v1.1.0
**Created**: 2026-08-27
**Revised**: 2026-08-27 (v1.1.0 — inference-only scope; evaluation metrics removed)
**Parent constitution**: `specs/001-zero-shot-eval/constitution.md` v2.1.0 (Myanmar)

---

## I. Purpose and Scope

This constitution governs **inference-only** generation of Aurora 1.5 weather forecasts
over Nepal for 14 initialisations spanning 2026-07-20 through 2026-08-02.

**The objective is to produce, validate, and archive Aurora 1.5 forecast outputs over
Nepal. No verification metrics are computed in this project.**

Performance evaluation (MAE, RMSE, ETS, POD, FAR, Frequency Bias, or any other skill
metric) is explicitly out of scope. Metric computation is deferred to a future project.

---

## II. Non-Negotiable Inherited Principles

1. **Single model, frozen**: Aurora 1.5 (`earth2studio.models.px.Aurora1p5`, E2S 0.17.0,
   arXiv:2405.13063). Zero-shot. No fine-tuning, no post-processing, no bias correction.
2. **Precipitation patch is mandatory**: `needs_log_untransform=False` for `tp1h` and
   `sf1h` in `aurora1p5.py` lines 128–129. Verify patch before every inference session.
3. **ERA5T precipitation conversion**: `precip_mmhr = max(0, tp_m × 1000)`. No division.
   ARCO `total_precipitation` is 1-hour accumulated depth in metres ending at timestamp T.
4. **Provenance on every file**: Every output NetCDF carries a sidecar provenance JSON.
   The provenance records: Aurora checkpoint hash, patch confirmation, init datetime,
   ARCO retrieval timestamp, conversion formulae, n_neg.
5. **No overwriting validated outputs**: Once a forecast file passes validation, it is
   read-only. Re-running inference for an existing slug requires explicit flag.
6. **Raw negative precipitation**: clip to zero at storage boundary; preserve raw in
   a separate attribute; record n_neg (count of raw negative tp1h values) in NC attrs.
7. **No metric computation**: MAE, RMSE, bias, CMAE, ETS, POD, FAR, Frequency Bias,
   Pearson r, SEEPS — none of these are computed in this project.

---

## III. Nepal-Specific Deviations from Myanmar Protocol

### DEV-001: ERA5T (Provisional ERA5) Required

**Myanmar**: Stable ERA5 used for verification. ERA5T excluded by ADR-024.

**Nepal**: The evaluation period (2026-07-20 to 2026-08-02) lies beyond the stable ERA5
boundary (~2026-04-30T00:00Z). **ERA5T is used for initial conditions only**.

ERA5T is available via ARCO through 2026-08-15. The Nepal IC window (t−6h through t+0h
for the last init 2026-08-02) ends at 2026-08-02 00Z — within confirmed availability.

All files carrying ERA5T data must include a global attribute `era5t: true` and a
written note that ERA5T is provisional and subject to revision by ECMWF.

### DEV-002: Inference-Only — No Evaluation Metrics

**Myanmar**: Full evaluation pipeline computing MAE, RMSE, bias, Pearson r, CMAE,
precipitation categorical metrics, and block-bootstrap confidence intervals.

**Nepal**: Inference and output validation only. No verification dataset retrieved beyond
IC. No metric of forecast skill is computed. This is a deliberate scope decision.

### DEV-003: No Subregion Analysis

**Myanmar**: Five subregions with mask script and subregion-disaggregated metrics.

**Nepal**: Land mask is generated (required for output spatial bounds documentation),
but no subregion masks are produced and no subregion analysis is performed.

### DEV-004: Machine-Readable Manifest as Primary Deliverable

**Myanmar**: Primary deliverables are computed metric JSON files and figures.

**Nepal**: Primary deliverable is a complete, validated set of 14 Aurora forecast
NetCDF files, with a machine-readable experiment manifest confirming completeness.

---

## IV. Domain Definition (LOCKED)

**Bounding box**: 26.0°N–30.5°N, 80.0°E–88.5°E

**Grid** (0.25° spacing, matching Aurora and ARCO grids):
- Latitude: 30.5, 30.25, ..., 26.0 (N→S) → **19 points**
- Longitude: 80.0, 80.25, ..., 88.5 (W→E) → **35 points**
- Bounding box total: 19 × 35 = **665 grid points**

Note: Aurora inference is always global. The Nepal bbox is applied when extracting
and storing outputs from the full global forecast field.

---

## V. Land Mask

**Source**: Natural Earth 50m admin-0 countries v5.1.1 (`ADMIN == "Nepal"`)
**Method**: Point-in-polygon (Shapely); no buffering
**Purpose**: Used only to record the count of Nepal land cells in the manifest.
  Not used for masking outputs (outputs retain full bounding-box grid).
**Output**: `data/masks/nepal_land_mask.npy` — (19, 35) bool

---

## VI. Initialisations (LOCKED)

| Parameter | Value |
|-----------|-------|
| Init dates | 2026-07-20 through 2026-08-02 (daily, 00Z) |
| Count | **14** |
| IC timesteps per init | t−6h and t+0h |
| Forecast horizon | 168 1h steps (168h = 7 days) |
| ERA5T IC window | 2026-07-19 18Z through 2026-08-02 00Z |
| ERA5T ARCO confirmed | Through 2026-08-15 — IC window fully covered |

---

## VII. Output Variables (LOCKED)

| Variable | Source field | Conversion | Stored name | Unit |
|----------|-------------|------------|-------------|------|
| 2 m temperature | `t2m` | t2m − 273.15 | `t2m_C` | °C |
| 10 m wind speed | `u10m`, `v10m` | √(u²+v²) × 1.9438444 | `ws_kts` | knots |
| 10 m wind direction | `u10m`, `v10m` | atan2(−u, −v) mod 360; meteorological | `wd_deg` | ° |
| Precipitation rate | `tp1h` (patched) | × 1000; clip ≥ 0; preserve raw n_neg | `tp1h_mmhr` | mm/hr |

---

## VIII. Repository and Version Control

**Nepal repository**: A fork of `JiayanLim/myanmar-weather-forecast` on GitHub,
named `nepal-weather-forecast`, owned by `JiayanLim`.

**Remote configuration**:
- `origin` → `JiayanLim/nepal-weather-forecast` (the Nepal fork)
- `upstream` → `JiayanLim/myanmar-weather-forecast` (the Myanmar source)

**Working branch**: `feature/nepal-inference`

**Constraint**: No pushes to `upstream` (Myanmar repo). The Myanmar repository is
read-only from the Nepal project's perspective.

---

## IX. Compute Platform

**Provider**: NVIDIA Brev, A100 80GB, on-demand (NOT spot)
**Environment**: conda `aurora_env`, Earth2Studio 0.17.0, precipitation patch applied
**Expected inference time**: ~309s × 14 ≈ 72 min
**Estimated cost**: ~$10–15 inclusive of setup and transfer

---

## X. Amendment Protocol

Amendments require a new version number and a dated entry below. Locked items
(domain, variables, patch, conversion formulae) cannot be changed without invalidating
previously computed outputs.

### Changelog
- v1.0.0 (2026-08-27): Initial draft; full evaluation scope including Tracks A–E
- v1.1.0 (2026-08-27): Revised to inference-only; removed all metric computation;
  removed Tracks A–E; removed subregion masks; simplified P4 to output validation only

---

*Constitution v1.1.0 — 2026-08-27.*
