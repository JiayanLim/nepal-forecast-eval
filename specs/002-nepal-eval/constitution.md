# Constitution: Aurora 1.5 Inference over Nepal
**Spec ID**: 002-nepal-eval
**Version**: v1.2.0
**Created**: 2026-08-27
**Revised**: 2026-08-27 (v1.2.0 — P1/P2 complete; P3 restructured; Brev handoff clarified)
**Parent constitution**: `specs/001-zero-shot-eval/constitution.md` v2.1.0 (Myanmar)

---

## I. Purpose and Scope

This constitution governs **inference-only** generation of Aurora 1.5 weather forecasts
over Nepal for 14 initialisations spanning 2026-07-20 through 2026-08-02.

**The objective is to produce, validate, and archive Aurora 1.5 forecast outputs over
Nepal. No verification metrics are computed in this project.**

This is a **zero-shot Aurora 1.5 inference experiment**. The model is used as-is with
no training, fine-tuning, PEFT, bias correction, or post-processing beyond unit
conversion and non-negative clipping of precipitation.

ERA5T is used **exclusively as the initial condition** (meteorological starting state
for the forecast). ERA5T is NOT used for training, fine-tuning, or verification.

---

## II. Non-Negotiable Principles

1. **Single model, frozen**: Aurora 1.5 (`earth2studio.models.px.Aurora1p5`, E2S 0.17.0,
   arXiv:2405.13063). Zero-shot. No fine-tuning, no PEFT, no post-processing, no bias
   correction, no model training of any kind.
2. **Precipitation patch is mandatory**: `needs_log_untransform=False` for `tp1h` and
   `sf1h` in `aurora1p5.py` lines 128–129. Verify patch before every inference session.
3. **ERA5T precipitation conversion**: `precip_mmhr = max(0, tp_m * 1000)`. No division.
   ARCO `total_precipitation` is 1-hour accumulated depth in metres ending at timestamp T.
4. **Provenance on every file**: Every output NetCDF carries a sidecar provenance JSON.
5. **No overwriting validated outputs**: Once a forecast file passes validation, it is
   read-only. Re-running inference for an existing slug requires explicit authorisation.
6. **Raw negative precipitation**: clip to zero at storage boundary; record `n_neg`
   (count of raw negative tp1h values) in NC attrs.
7. **No metric computation whatsoever** (see §III).
8. **ERA5T is IC only**: ERA5T provides the meteorological initial condition for Aurora.
   It is NOT training data, fine-tuning data, or verification data.

---

## III. Out of Scope — Explicit Exclusions

The following are **not part of this project** under any circumstances:

### Evaluation Metrics
- MAE (Mean Absolute Error)
- RMSE (Root Mean Square Error)
- Bias metrics
- CMAE (Circular Mean Absolute Error)
- ETS (Equitable Threat Score)
- POD (Probability of Detection)
- FAR (False Alarm Ratio)
- Frequency Bias
- SEEPS (Stable Equitable Error in Probability Space)
- Pearson r / correlation
- CSI (Critical Success Index)
- Any other forecast skill or verification metric

### Evaluation Frameworks
- Track A (domain-mean lead-time curves)
- Track B (spatial error maps)
- Track C (subregion analysis)
- Track D (precipitation categorical metrics)
- Track E (Nepal vs Myanmar comparison)
- Any other structured evaluation track

### Analysis and Reporting
- Statistical inference
- Block bootstrap confidence intervals
- Any statistical test
- Nepal/Myanmar comparison of any kind
- Figures, plots, or visualisations
- Thesis chapters or sections
- PDF/report generation
- Any written analysis document

### Model Modification
- Model training
- Fine-tuning
- PEFT (Parameter-Efficient Fine-Tuning)
- LoRA, adapters, or any parameter modification
- Ensemble generation
- Post-processing / bias correction

The **only** post-inference work is structural/output/provenance validation.

---

## IV. Nepal-Specific Deviations from Myanmar Protocol

### DEV-001: ERA5T as Initial Condition
**Myanmar**: Stable ERA5 used for IC and verification. ERA5T excluded (ADR-024).
**Nepal**: The evaluation period (2026-07-20 to 2026-08-02) lies beyond the stable ERA5
boundary (~2026-04-30T00:00Z). **ERA5T is used for initial conditions only** — not for
verification (no verification is performed).

### DEV-002: Inference-Only — No Evaluation Metrics
**Myanmar**: Full evaluation pipeline (MAE, RMSE, ETS, POD, FAR, etc.).
**Nepal**: Inference and output validation only. No verification dataset. No metrics.

### DEV-003: No Subregion Analysis
**Myanmar**: Five subregions with disaggregated metrics.
**Nepal**: Land mask generated for documentation only. No subregion analysis.

### DEV-004: Machine-Readable Manifest as Primary Deliverable
**Myanmar**: Computed metric JSON files and figures.
**Nepal**: 14 validated Aurora forecast NetCDF files + experiment manifest.

---

## V. Domain Definition (LOCKED)

**Bounding box**: 26.0°N–30.5°N, 80.0°E–88.5°E

**Grid** (0.25° spacing, matching Aurora and ARCO grids):
- Latitude: 30.5, 30.25, ..., 26.0 (N→S) — **19 points**
- Longitude: 80.0, 80.25, ..., 88.5 (W→E) — **35 points**
- Bounding box total: 19 × 35 = **665 grid points**

Aurora inference is always global. The Nepal bbox is applied when extracting
and storing outputs from the full global forecast field.

---

## VI. Land Mask

**Source**: Natural Earth 50m admin-0 countries v5.1.1 (`ADMIN == "Nepal"`)
**Method**: Point-in-polygon (Shapely); no buffering
**Purpose**: Land cell count recorded in manifest. Outputs retain full bbox grid.
**Output**: `data/masks/nepal_land_mask.npy` — (19, 35) bool, 221 land cells

---

## VII. Initialisations (LOCKED)

| Parameter | Value |
|-----------|-------|
| Init dates | 2026-07-20 through 2026-08-02 (daily, 00Z) |
| Count | **14** |
| IC timesteps per init | t-6h and t+0h |
| Forecast horizon | 168 1h steps (168h = 7 days) |
| ERA5T IC window | 2026-07-19 18Z through 2026-08-02 00Z |
| ERA5T ARCO confirmed | Through 2026-08-15 — IC window fully covered |

---

## VIII. Output Variables (LOCKED)

| Variable | Source field | Conversion | Stored name | Unit |
|----------|-------------|------------|-------------|------|
| 2m temperature | `t2m` | t2m - 273.15 | `t2m_C` | degC |
| 10m wind speed | `u10m`, `v10m` | sqrt(u^2+v^2) * 1.9438444 | `ws_kts` | knots |
| 10m wind direction | `u10m`, `v10m` | atan2(-u, -v) mod 360 | `wd_deg` | degrees |
| Precipitation rate | `tp1h` (patched) | * 1000; clip >= 0 | `tp1h_mmhr` | mm/hr |

---

## IX. Repository and Version Control

**Repository**: `JiayanLim/nepal-forecast-eval` on GitHub
**Local path**: `/Users/limjiayan/nepal-forecast-eval`
**Working branch**: `feature/nepal-inference`
**Source**: Created from `myanmar-forecast-eval` Aurora 1.5 pipeline source (19 files)
**Remote**: `origin` -> `JiayanLim/nepal-forecast-eval`. No upstream remote.

**Isolation constraints**:
- Do NOT modify `myanmar-forecast-eval`
- Do NOT modify `myanmar-weather-forecast`
- Do NOT modify `nepal-weather-forecast`

---

## X. Compute Platform

**Provider**: NVIDIA Brev / Hyperstack Montreal
**GPU**: A100 80GB, on-demand (NOT spot)
**Environment**: conda `aurora_env`, Earth2Studio 0.17.0, precipitation patch applied
**Instance management**: User creates/destroys via Brev web console. Claude Code does NOT
provision, create, stop, or delete Brev instances.
**Expected inference time**: ~309s * 14 ~ 72 min
**Estimated cost**: ~$10-15

---

## XI. Amendment Protocol

Amendments require a new version number and a dated entry below.

### Changelog
- v1.0.0 (2026-08-27): Initial draft; full evaluation scope including Tracks A-E
- v1.1.0 (2026-08-27): Revised to inference-only; removed all metric computation
- v1.2.0 (2026-08-27): P1/P2 complete; updated repo info (nepal-forecast-eval, not fork);
  P3 restructured into environment gate + inference; explicit ERA5T-as-IC-only;
  expanded out-of-scope list; Brev instance management clarified

---

*Constitution v1.2.0 — 2026-08-27.*
