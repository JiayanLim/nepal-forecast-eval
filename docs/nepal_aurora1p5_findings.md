# Aurora 1.5 Zero-Shot Forecasts over Nepal — Findings Record

**Project**: 002-nepal-eval
**Version**: v1.0
**Date**: 2026-08-27

---

## 1. Executive Summary

This document records the outcomes of running Aurora 1.5 (Bodnar et al., 2024) over Nepal in a zero-shot geographic inference configuration. No evaluation metrics are computed; this is an inference-only record.

- **14 of 14** daily initialisations completed successfully (2026-07-20 through 2026-08-02, 00Z)
- **168-hour** (7-day) forecast horizon per initialisation
- **0.25° resolution** over Nepal (26.0–30.5°N, 80.0–88.5°E); 19 × 35 = 665 grid cells
- **Four output variables**: 2m temperature (°C), 10m wind speed (kts), 10m wind direction (degrees), precipitation rate (mm/hr)
- **Total runtime**: 67.0 minutes on NVIDIA A100-SXM4-80GB
- **Zero failures, zero retries**

---

## 2. Experiment Design

### Model

Aurora 1.5 (`earth2studio.models.px.Aurora1p5`, Earth2Studio 0.17.0) is a transformer-based global weather forecasting model operating at 0.25° resolution with 1-hour output intervals.

- **Paper**: arXiv:2405.13063 (Bodnar et al., 2024)
- **Checkpoint**: `aurora-0.25-v1.5.ckpt` (hash: `c171214768997594e1a3fc6b8d9bbb489e9d21ab`)
- **Pretraining**: ERA5 (endpoint unspecified)
- **Fine-tuning**: HRES-T0 2016–2021

### Zero-Shot Geographic Inference

Aurora 1.5 was applied to the Nepal domain without any form of adaptation. Specifically:

- No training on Nepal data
- No fine-tuning on Nepal data
- No PEFT, LoRA, or adapter layers
- No calibration or post-processing calibration
- No parameter updates of any kind
- No model selection based on Nepal performance

The model's pretrained weights are applied directly. The only Nepal-specific input is the atmospheric initial condition at each forecast start time.

### Domain

Nepal bounding box: 26.0–30.5°N, 80.0–88.5°E. This region spans the Terai plains (~100m elevation), the Himalayan foothills, and portions of the high Himalaya (>8000m). The domain includes 665 grid cells at 0.25° resolution, of which 221 are land cells within Nepal's administrative boundary.

### Initialisations

14 daily 00Z initialisations from 2026-07-20 through 2026-08-02, covering Nepal's monsoon season. Each initialisation produces a 168-step (7-day) autoregressive forecast.

### Initial Condition Source

ERA5T (provisional ERA5) accessed at runtime via Google's Analysis-Ready, Cloud-Optimized ERA5 (ARCO) dataset. See Section 3 for provenance details.

---

## 3. Data Provenance

### Aurora 1.5 Model Provenance

The Aurora 1.5 checkpoint was pretrained on ERA5 reanalysis data and fine-tuned on HRES-T0 analysis fields from 2016–2021. The model weights are frozen and unmodified throughout this experiment.

### ERA5T Initial Condition Data

ERA5T (provisional ERA5) serves as the atmospheric initial condition. At each forecast start time, Earth2Studio's ARCO data source fetches the full global 0.25° initial state (13 pressure levels × 5 atmospheric variables + 18 surface variables) from Google Cloud Storage.

**ERA5T is NOT used for**: training, fine-tuning, PEFT, calibration, parameter updates, model selection, or verification/evaluation.

### Distinction: P2 Archive vs Runtime ARCO Access

Two separate interactions with ERA5T data occurred:

1. **P2 Local Archive** (Phase 2, pre-inference): 14 NetCDF files (213.5 MB total) containing selected surface variables were retrieved from ARCO and stored locally as provenance records. These files confirm that ERA5T data was available for all 14 initialisation times. **These files are not consumed by the inference pipeline.**

2. **Runtime ARCO Access** (Phase 3, during inference): Earth2Studio's `ARCO()` data source fetches the full global IC directly from the ARCO Zarr store at inference time. This is the data that actually initialises Aurora 1.5 for each forecast. The fetched data is transient (held in GPU memory during the forecast, not stored to disk).

Both access the same underlying dataset: `gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3`.

### Forecast Outputs

The 14 forecast NetCDF files and the consolidated research dataset are Aurora predictions. They do not contain any verification or ground-truth data.

---

## 4. Forecast Dataset

### Consolidated Dataset

A single consolidated NetCDF file combines all 14 forecasts:

- **File**: `results/nepal/dataset/nepal_aurora1p5_20260720_20260802.nc`
- **Size**: 18.27 MB (zlib compressed, complevel=4)
- **SHA-256**: `fea40f1804d87c10cf1b7f1454c98fc9d1b935f70f0b6fa60ca329d1bc7b59db`

### Dimensions

| Dimension | Size | Description |
|-----------|------|-------------|
| `init_time` | 14 | Forecast initialisation times (2026-07-20 through 2026-08-02, daily 00Z) |
| `lead_time` | 168 | Forecast lead times (1h through 168h) |
| `lat` | 19 | Latitude (30.50°N to 26.00°N, 0.25° spacing, N→S) |
| `lon` | 35 | Longitude (80.00°E to 88.50°E, 0.25° spacing, W→E) |

### Variables

| Variable | Units | dtype | Source Conversion |
|----------|-------|-------|-------------------|
| `t2m_C` | °C | float32 | `t2m_K - 273.15` |
| `ws_kts` | knots | float32 | `sqrt(u10m² + v10m²) × 1.9438` |
| `wd_deg` | degrees | float32 | `(270 - atan2(v10m, u10m)) % 360` (meteorological FROM convention) |
| `tp1h_mmhr` | mm/hr | float32 | `max(0, tp1h_raw_m_per_hr × 1000)` |

### Coordinate Conventions

- **Latitude**: North-to-south ordering (30.50, 30.25, ..., 26.00)
- **Longitude**: West-to-east ordering (80.00, 80.25, ..., 88.50)
- **Lead time**: Integer hours, 1 through 168
- **Init time**: datetime64[ns], tz-naive UTC

---

## 5. Structural Validation

All 14 forecast files passed structural validation (P3.07):

| Check | Result |
|-------|--------|
| File count | 14/14 |
| Slug coverage (20260720–20260802) | 14/14 |
| Dimensions (168, 19, 35) | 14/14 |
| Variables (t2m_C, ws_kts, wd_deg, tp1h_mmhr) | 14/14 |
| No NaN values | 14/14 |
| Lead time range 1–168 | 14/14 |
| Coordinate consistency | 14/14 |
| init_time matches calendar | 14/14 |
| model_id = aurora1p5 | 14/14 |
| earth2studio_ver = 0.17.0 | 14/14 |
| patch_confirmed = true | 14/14 |
| era5t_ic = true | 14/14 |

Validation report: `results/nepal/validation/p307_structural_validation.json`

---

## 6. Precipitation Findings

### Negative Raw Precipitation Values

Aurora 1.5 produced negative values in its raw precipitation output (`tp1h`, in m/hr) before the `max(0, ...)` clipping step. This is an observed model-output behaviour, not a pipeline or conversion error.

**Aggregate statistics** (14 initialisations, 1,564,080 total grid-cell-hours):

| Metric | Value |
|--------|-------|
| Total negative values (pre-clip) | 32,024 |
| Percentage negative | 2.05% |
| Per-init range | 521 (0.47%) to 3,745 (3.35%) |
| Maximum final precipitation (post-clip) | 6.10 mm/hr |

### Origin of Negatives

The negative values originate from Aurora 1.5's neural network decoder. The model does not enforce a non-negativity constraint on its precipitation output tensor. The processing chain is:

1. Aurora NN decoder produces `scaled_tp_1h` (internal log-scaled representation)
2. Aurora's internal hook applies `log_untransform` once → physical-space m/hr (may be negative)
3. E2S precipitation patch prevents a second `log_untransform` (which would have been a bug)
4. Pipeline applies `max(0, tp1h_raw × 1000)` → `tp1h_mmhr` in mm/hr

The precipitation patch (E2S 0.17.0, `aurora1p5.py` lines 128–129: `needs_log_untransform=False` for `tp1h` and `sf1h`) was verified active on the inference instance.

### Mitigation

- Negative values are clipped to zero at the unit-conversion boundary
- The count of negative values (`n_neg_tp1h`) is recorded as a provenance attribute in each forecast NetCDF file
- Raw negative values are not preserved in the final dataset; only the clipped `tp1h_mmhr ≥ 0` is stored

### Temporal Pattern

- Negatives do not increase monotonically with lead time
- They cluster at 12-hour and 24-hour lead-time multiples, with intermittent spikes
- Lead h=6 consistently shows 0% negatives across all initialisations
- Lead h=1 shows elevated negatives (~5%), suggesting a first-step adjustment artefact
- Odd-hour leads (36h, 60h, 84h, 108h, 132h, 156h) consistently show near-zero negatives

### Spatial Pattern

- Negatives concentrate at specific high-elevation grid cells and domain-edge cells
- Highest concentration: (28.25°N, 81.25°E) with 29.0 average zero-steps per init (mid-western Nepal, Himalayan foothills)
- Multiple low-elevation Terai cells show zero negatives across all 14 initialisations
- The NW corner cell (30.50°N, 80.00°E) has zero negatives in every init

### Note on Interpretation

The negative precipitation values are documented as an observed behaviour of Aurora 1.5's autoregressive decoder output. They are not described as "expected" in the Aurora paper (arXiv:2405.13063). The spatial and temporal clustering suggests they are associated with regions and times where the model's predicted precipitation magnitude is near zero and the sign becomes numerically ambiguous. The same behaviour was observed in the Myanmar inference experiment (001-zero-shot-eval).

---

## 7. Computational Performance

| Metric | Value |
|--------|-------|
| GPU | NVIDIA A100-SXM4-80GB |
| Peak VRAM | 25,740 MB (32% of 80 GB) |
| Total wall time | 4,020.5s (67.0 min) |
| Mean per-init runtime | 287.0s |
| Min per-init runtime | 283.2s (20260720) |
| Max per-init runtime | 294.0s (20260723) |
| Std dev | 3.2s |
| Earth2Studio version | 0.17.0 |
| PyTorch | 2.6.x (CUDA) |
| Conda environment | aurora_env (Python 3.11) |

---

## 8. Zero-Shot Interpretation

This experiment applies Aurora 1.5 to Nepal in a strictly zero-shot configuration. ERA5T provides the atmospheric initial state (temperature, humidity, wind, pressure, geopotential, and surface fields at 13 pressure levels) at each forecast start time. This initial condition is the only Nepal-specific input to the model.

Aurora 1.5's parameters were not updated, adapted, or selected based on any Nepal data. The model's ability to produce forecasts over Nepal derives entirely from its pretraining on global ERA5 reanalysis and fine-tuning on global HRES-T0 analysis fields (2016–2021). Nepal was included in the global training domain at 0.25° resolution, but no region-specific weighting, masking, or adaptation was applied.

---

## 9. Limitations

- **No forecast skill has been established.** This experiment produces Aurora 1.5 predictions but does not include independent verification against observations, reanalysis, or other reference data. No MAE, RMSE, bias, categorical skill scores, or other evaluation metrics have been computed.
- **ERA5T is provisional.** ERA5T data may be revised when final ERA5 is released for July–August 2026. The initial conditions used here reflect the ERA5T version available on 2026-08-27.
- **14 initialisations.** The sample size (n=14) is insufficient for robust statistical inference about forecast performance.
- **Monsoon season only.** All initialisations fall within Nepal's monsoon season (July–August). Seasonal representativeness is limited.
- **Precipitation non-negativity.** 2.05% of raw precipitation cells were negative and clipped to zero. The impact on forecast quality, if any, is not assessed here.
- **Aurora model disambiguation.** This study uses Aurora 1.5 from arXiv:2405.13063 (Bodnar et al., 2024), pretrained on ERA5 and fine-tuned on HRES-T0 2016–2021. This is distinct from a later Aurora model (July 2026 ensemble paper, fine-tuned on HRES 2018–2023).

---

## 10. Reproducibility

| Item | Value |
|------|-------|
| Repository | `JiayanLim/nepal-forecast-eval` |
| Branch | `feature/nepal-inference` |
| Model checkpoint | `aurora-0.25-v1.5.ckpt` |
| Checkpoint hash | `c171214768997594e1a3fc6b8d9bbb489e9d21ab` |
| Earth2Studio | 0.17.0 |
| Precipitation patch | `aurora1p5.py` lines 128–129: `needs_log_untransform=False` |
| ARCO date patch | `arco.py` line 82: `ARCO_TIME_STOP = datetime(2026, 8, 15)` |
| Inference script | `scripts/nepal_inference.py` |
| Validation script | `scripts/nepal_brev_check.py` |
| Brev instance | lexical-gray-vulture (A100-SXM4-80GB) |
| Consolidated dataset | `results/nepal/dataset/nepal_aurora1p5_20260720_20260802.nc` |
| Dataset SHA-256 | `fea40f1804d87c10cf1b7f1454c98fc9d1b935f70f0b6fa60ca329d1bc7b59db` |
| Dataset manifest | `results/nepal/dataset/nepal_aurora1p5_dataset_manifest.json` |

---

*Findings record v1.0 — 2026-08-27.*
