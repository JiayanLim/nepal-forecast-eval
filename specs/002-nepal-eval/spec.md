# Specification: Aurora 1.5 Inference over Nepal
**Spec ID**: 002-nepal-eval
**Version**: v1.2
**Created**: 2026-08-27
**Revised**: 2026-08-27 (v1.2 — P1/P2 complete; ERA5T IC-only explicit; expanded exclusions)
**Constitution**: `specs/002-nepal-eval/constitution.md` v1.2.0

---

## 1. Objective

Generate and validate Aurora 1.5 weather forecast outputs over Nepal for 14 initialisations
spanning 2026-07-20 through 2026-08-02. The outputs are the deliverable. No forecast
skill metrics are computed.

This is a **zero-shot inference experiment**. Aurora 1.5 is used as a pre-trained model
with no modification. ERA5T provides the meteorological initial condition only.

---

## 2. Model

| Field | Value |
|-------|-------|
| Class | `earth2studio.models.px.Aurora1p5` |
| Package | Earth2Studio 0.17.0 |
| Paper | arXiv:2405.13063 (Bodnar et al., 2024) |
| Checkpoint | `hf://microsoft/aurora@c171214768997594e1a3fc6b8d9bbb489e9d21ab` / `aurora-0.25-v1.5.ckpt` |
| Resolution | 0.25 deg global; 1h output; 168 AR steps per run |
| Mode | Zero-shot inference; no training, fine-tuning, PEFT, or post-processing |
| Precipitation patch | `needs_log_untransform=False` for `tp1h` and `sf1h` — MANDATORY |

---

## 3. Initialisations

| Field | Value |
|-------|-------|
| Init dates | 2026-07-20 through 2026-08-02 (daily, 00Z) |
| Total | **14 initialisations** |
| Init time | 00:00 UTC |
| Forecast horizon | 168h (168 x 1h steps) per init |
| Last valid time | 2026-08-09 00Z (from 2026-08-02 init) |

### Calendar slugs
Format: `YYYYMMDD`. `config/nepal_calendar.csv` has 14 rows.

```
20260720, 20260721, 20260722, 20260723, 20260724, 20260725,
20260726, 20260727, 20260728, 20260729, 20260730, 20260731,
20260801, 20260802
```

---

## 4. Initial Conditions

| Field | Value |
|-------|-------|
| Source | ERA5T via ARCO |
| ARCO path | `gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3` |
| IC timesteps | t-6h and t+0h for each initialisation |
| IC window | 2026-07-19 18Z through 2026-08-02 00Z |
| ERA5T status | Provisional; ARCO confirmed available through 2026-08-15 |
| Global attribute | `era5t: "true"` on all IC and forecast files |

**ERA5T role**: ERA5T provides the meteorological initial condition (starting state)
for Aurora inference. It is NOT used for model training, fine-tuning, verification,
or any form of evaluation. This remains a zero-shot inference experiment.

Aurora 1.5 requires global initial condition fields (not a subdomain). The Nepal bbox
extraction applies only to forecast outputs, not to IC fetching.

### Surface IC variables fetched (P2 — COMPLETE)
- `2m_temperature` -> t2m_K (K)
- `10m_u_component_of_wind` -> u10m_ms (m/s)
- `10m_v_component_of_wind` -> v10m_ms (m/s)
- `mean_sea_level_pressure` -> msl_Pa (Pa)
- `total_precipitation` -> tp_raw_m (m)

Pressure-level variables (u, v, t, z, q at 13 levels) verified by name in ARCO;
fetched on Brev at inference time by `earth2studio.data.ARCO`.

---

## 5. Domain

### Bounding Box (LOCKED)

| | Value |
|--|-------|
| North | 30.5 deg N |
| South | 26.0 deg N |
| West | 80.0 deg E |
| East | 88.5 deg E |
| Grid | 19 lat x 35 lon = 665 grid points |
| Lat sequence | 30.5, 30.25, ..., 26.0 (N->S, 19 points) |
| Lon sequence | 80.0, 80.25, ..., 88.5 (W->E, 35 points) |

### Land Mask
- Source: Natural Earth 50m admin-0 (`ADMIN == "Nepal"`)
- Stored: `data/masks/nepal_land_mask.npy` — (19, 35) bool, 221 land cells
- Use: land cell count recorded in manifest only; outputs are not masked

---

## 6. Output Variables (LOCKED)

| Stored name | Formula | Unit | Notes |
|-------------|---------|------|-------|
| `t2m_C` | t2m - 273.15 | degC | Direct from Aurora `t2m` |
| `ws_kts` | sqrt(u10m^2 + v10m^2) * 1.9438444 | knots | Wind speed magnitude |
| `wd_deg` | (270 - atan2(v, u)) mod 360 | degrees | Meteorological (from) convention |
| `tp1h_mmhr` | max(0, tp1h * 1000) | mm/hr | Post-patch conversion; clip at 0 |

Global attribute `n_neg_tp1h`: count of raw tp1h < 0 before clipping.

---

## 7. Output File Schema

### Forecast NetCDF: `results/nepal/forecasts/{slug}_aurora.nc`

**Dimensions**: lead_time: 168, lat: 19, lon: 35

**Variables** (all float32):
- `t2m_C`, `ws_kts`, `wd_deg`, `tp1h_mmhr`

**Global attributes**:
- `spec_id`, `spec_version`, `project`, `slug`
- `model_id`: "aurora1p5"
- `earth2studio_ver`: "0.17.0"
- `checkpoint_hash`: "c171214768997594e1a3fc6b8d9bbb489e9d21ab"
- `patch_confirmed`: "true"
- `era5t_ic`: "true"
- `init_datetime_utc`
- `n_steps`, `n_steps_collected`, `wall_clock_s`
- `n_neg_tp1h`
- `domain`, `precip_convention`

### IC NetCDF: `results/nepal/era5_ic/{slug}_era5_ic.nc`

**Dimensions**: ic_step: 2, latitude: 721, longitude: 1440
**Variables**: t2m_K, u10m_ms, v10m_ms, msl_Pa, tp_raw_m
**Global attributes**: era5t, slug, arco_url, retrieval_utc

### Provenance JSON

Each NetCDF has a companion JSON:
- `results/nepal/provenance/{slug}_aurora_provenance.json`
- `results/nepal/provenance/{slug}_era5_ic_provenance.json`

---

## 8. Experiment Manifest

**File**: `results/nepal/manifest.json`

Machine-readable summary of the full experiment: n_inits, n_complete, n_failed,
model info, domain, variables, per-init status.

---

## 9. Validation Checks (Structural Only)

No forecast skill metrics. Structural checks on every output file:

| Check | Expected | Fail action |
|-------|----------|-------------|
| File exists and non-empty | True | FAIL |
| Shape (lead_time, lat, lon) | (168, 19, 35) | FAIL |
| All 4 variables present | t2m_C, ws_kts, wd_deg, tp1h_mmhr | FAIL |
| No all-NaN step | True for every lead step | FAIL |
| t2m_C range | -40 to 60 degC | WARN |
| ws_kts range | 0 to 200 kt | WARN |
| tp1h_mmhr range | >= 0 mm/hr | FAIL |
| tp1h_mmhr max | < 500 mm/hr | WARN |
| patch_confirmed in attrs | "true" | FAIL |
| Provenance JSON exists | True | FAIL |

---

## 10. Out of Scope — Explicit Exclusions

### Evaluation Metrics (NONE computed)
MAE, RMSE, bias, CMAE, ETS, POD, FAR, Frequency Bias, SEEPS, Pearson r, CSI

### Evaluation Frameworks (NONE executed)
Track A, Track B, Track C, Track D, Track E

### Analysis (NONE produced)
Statistical inference, bootstrap CIs, Nepal/Myanmar comparison, figures, plots,
thesis chapters, PDF/report generation

### Model Modification (NONE performed)
Training, fine-tuning, PEFT, LoRA, ensemble generation, post-processing

---

*Spec v1.2 — 2026-08-27. Inference-only.*
