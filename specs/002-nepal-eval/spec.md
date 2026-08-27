# Specification: Aurora 1.5 Inference over Nepal
**Spec ID**: 002-nepal-eval
**Version**: v1.1
**Created**: 2026-08-27
**Revised**: 2026-08-27 (v1.1 — inference-only; evaluation metrics removed)
**Constitution**: `specs/002-nepal-eval/constitution.md` v1.1.0

---

## 1. Objective

Generate and validate Aurora 1.5 weather forecast outputs over Nepal for 14 initialisations
spanning 2026-07-20 through 2026-08-02. The outputs are the deliverable. No forecast
skill metrics are computed.

---

## 2. Model

| Field | Value |
|-------|-------|
| Class | `earth2studio.models.px.Aurora1p5` |
| Package | Earth2Studio 0.17.0 |
| Paper | arXiv:2405.13063 (Bodnar et al., 2024) |
| Checkpoint | `hf://microsoft/aurora@c171214768997594e1a3fc6b8d9bbb489e9d21ab` / `aurora-0.25-v1.5.ckpt` |
| Resolution | 0.25° global; 1h output; 168 AR steps per run |
| Mode | Zero-shot, no post-processing |
| Precipitation patch | `needs_log_untransform=False` for `tp1h` and `sf1h` — MANDATORY |

---

## 3. Initialisations

| Field | Value |
|-------|-------|
| Init dates | 2026-07-20, 21, ..., 31 (12) + 2026-08-01, 02 (2) |
| Total | **14 initialisations** |
| Init time | 00:00 UTC |
| Forecast horizon | 168h (168 × 1h steps) per init |
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
| IC timesteps | t−6h and t+0h for each initialisation |
| IC window | 2026-07-19 18Z through 2026-08-02 00Z |
| ERA5T status | Provisional; ARCO confirmed available through 2026-08-15 |
| Global attribute | `era5t: true` on all IC files |
| Variables fetched | `2m_temperature`, `10m_u_component_of_wind`, `10m_v_component_of_wind`,
                     `mean_sea_level_pressure`, and all other fields Aurora 1.5 requires |

Aurora 1.5 requires global initial condition fields (not a subdomain). The Nepal bbox
extraction applies only to forecast outputs, not to IC fetching.

---

## 5. Domain

### Bounding Box (LOCKED)

| | Value |
|--|-------|
| North | 30.5°N |
| South | 26.0°N |
| West | 80.0°E |
| East | 88.5°E |
| Grid | 19 lat × 35 lon = 665 grid points |
| Lat sequence | 30.5, 30.25, ..., 26.0 (N→S, 19 points) |
| Lon sequence | 80.0, 80.25, ..., 88.5 (W→E, 35 points) |

### Land Mask

- Source: Natural Earth 50m admin-0 (`ADMIN == "Nepal"`)
- Stored: `data/masks/nepal_land_mask.npy` — (19, 35) bool
- Use: land cell count recorded in manifest only; outputs are not masked

---

## 6. Output Variables (LOCKED)

| Stored name | Formula | Unit | Notes |
|-------------|---------|------|-------|
| `t2m_C` | t2m − 273.15 | °C | Direct from Aurora `t2m` |
| `ws_kts` | √(u10m² + v10m²) × 1.9438444 | knots | Wind speed magnitude |
| `wd_deg` | atan2(−u10m, −v10m) mod 360 | ° | Meteorological (from) convention |
| `tp1h_mmhr` | max(0, tp1h × 1000) | mm/hr | Post-patch conversion; clip at 0 |

Additional raw storage:
- `tp1h_raw_mmhr` (optional, pre-clip) may be stored for diagnostic purposes
- `n_neg` global attribute: count of raw tp1h < 0 before clipping

---

## 7. Output File Schema

### Forecast NetCDF: `results/nepal/forecasts/{slug}_aurora.nc`

**Dimensions**:
- `lead_step`: 168 (steps 1 through 168)
- `lat`: 19 (30.5°N to 26.0°N, 0.25° spacing)
- `lon`: 35 (80.0°E to 88.5°E, 0.25° spacing)

**Coordinates**:
- `lat` — float32, degrees north
- `lon` — float32, degrees east
- `lead_hours` — int, {1, 2, ..., 168}
- `valid_time` — datetime64, init_time + lead_hours

**Variables** (all float32, dims lead_step × lat × lon):
- `t2m_C`
- `ws_kts`
- `wd_deg`
- `tp1h_mmhr`

**Global attributes**:
- `init_date`: e.g., "2026-07-20"
- `init_datetime_utc`: e.g., "2026-07-20T00:00:00Z"
- `model`: "Aurora1p5"
- `model_version`: "aurora-0.25-v1.5.ckpt"
- `checkpoint_hash`: "c171214768997594e1a3fc6b8d9bbb489e9d21ab"
- `patch_confirmed`: true
- `era5t_ic`: true
- `n_neg`: integer count of raw tp1h < 0
- `precip_formula`: "tp1h_output * 1000, clipped >= 0"
- `domain`: "26.0N-30.5N, 80.0E-88.5E"
- `spec_id`: "002-nepal-eval"
- `spec_version`: "v1.1"

### IC NetCDF: `results/nepal/era5_ic/{slug}_era5_ic.nc`

Stores the ERA5T fields used as Aurora initial conditions (t−6h and t+0h).

**Dimensions**: `ic_step`: 2 (t−6h, t+0h), `lat`: global (720), `lon`: global (1440)
**Coordinates**: `ic_datetime` — datetime64, {init−6h, init+0h}
**Variables**: all Aurora input fields (t2m, u10m, v10m, msl, geopotential levels, etc.)
**Global attributes**: same provenance fields; `era5t: true`

Note: IC files are global (required by Aurora). Forecast files are Nepal-bbox extracted.

---

## 8. Provenance Sidecar JSON

Each NetCDF has a companion: `{slug}_aurora_provenance.json` / `{slug}_era5_ic_provenance.json`

Required fields:
```json
{
  "spec_id": "002-nepal-eval",
  "spec_version": "v1.1",
  "slug": "20260720",
  "init_datetime_utc": "2026-07-20T00:00:00Z",
  "model_class": "earth2studio.models.px.Aurora1p5",
  "e2s_version": "0.17.0",
  "checkpoint": "aurora-0.25-v1.5.ckpt",
  "checkpoint_hash": "c171214768997594e1a3fc6b8d9bbb489e9d21ab",
  "patch_confirmed": true,
  "patch_file": "aurora1p5.py",
  "patch_lines": [128, 129],
  "patch_values": ["needs_log_untransform=False", "needs_log_untransform=False"],
  "era5t_ic": true,
  "arco_path": "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3",
  "ic_timesteps_utc": ["2026-07-19T18:00:00Z", "2026-07-20T00:00:00Z"],
  "n_lead_steps": 168,
  "lead_hours_range": [1, 168],
  "output_domain": "26.0N-30.5N,80.0E-88.5E",
  "output_shape": [168, 19, 35],
  "precip_conversion": "tp1h_output * 1000, clip >= 0",
  "n_neg_tp1h": 0,
  "inference_start_utc": "...",
  "inference_end_utc": "...",
  "wall_seconds": 0,
  "brev_instance_id": "...",
  "git_commit": "..."
}
```

---

## 9. Experiment Manifest

**File**: `results/nepal/manifest.json`

A single machine-readable file summarising the entire experiment:

```json
{
  "spec_id": "002-nepal-eval",
  "spec_version": "v1.1",
  "generated_utc": "...",
  "n_inits": 14,
  "n_complete": 14,
  "n_failed": 0,
  "model": "Aurora1p5",
  "checkpoint_hash": "c171214768997594e1a3fc6b8d9bbb489e9d21ab",
  "patch_confirmed_all": true,
  "era5t_ic_all": true,
  "domain": {"lat_min": 26.0, "lat_max": 30.5, "lon_min": 80.0, "lon_max": 88.5,
             "n_lat": 19, "n_lon": 35, "n_land_cells": null},
  "lead_hours": [1, 2, ..., 168],
  "variables": ["t2m_C", "ws_kts", "wd_deg", "tp1h_mmhr"],
  "initialisations": [
    {
      "slug": "20260720",
      "init_datetime_utc": "2026-07-20T00:00:00Z",
      "forecast_file": "results/nepal/forecasts/20260720_aurora.nc",
      "ic_file": "results/nepal/era5_ic/20260720_era5_ic.nc",
      "provenance_file": "results/nepal/provenance/20260720_aurora_provenance.json",
      "validation_status": "PASS",
      "n_neg_tp1h": 0,
      "file_size_bytes": 0,
      "patch_confirmed": true
    }
    // ... 13 more
  ]
}
```

---

## 10. Validation Checks (Phase P4)

No forecast skill metrics. The following **structural checks** are run on every output file:

| Check | Expected | Fail action |
|-------|----------|-------------|
| File exists and non-empty | True | Flag in manifest as FAIL |
| Shape (lead_step, lat, lon) | (168, 19, 35) | Flag FAIL |
| Lead hours 1–168 | All present, monotone | Flag FAIL |
| All 4 variables present | t2m_C, ws_kts, wd_deg, tp1h_mmhr | Flag FAIL |
| No all-NaN step | True for every lead step | Flag FAIL |
| t2m_C range | −40 to 60 °C | Warn if outside |
| ws_kts range | 0 to 200 kt | Warn if outside |
| tp1h_mmhr range | ≥ 0 mm/hr | Fail if any negative (post-clip) |
| tp1h_mmhr max | < 500 mm/hr | Warn if above (may indicate unpatch) |
| tp1h_mmhr max | > 0.1 mm/hr somewhere across 168 steps | Warn if always zero (may indicate patch failure in opposite direction) |
| patch_confirmed in attrs | true | Flag FAIL |
| Provenance JSON exists | True | Flag FAIL |
| git_commit in provenance | non-empty string | Warn |

A run is PASS only if all FAIL checks pass. Warnings are recorded but do not block PASS.

---

## 11. Out of Scope

The following are explicitly not part of this project:

- MAE, RMSE, bias, Pearson r
- Circular MAE (CMAE)
- ETS, POD, FAR, Frequency Bias, CSI
- SEEPS
- Subregion analysis (TER/HIL/HIM)
- Lead-time error curves
- Spatial error maps
- Nepal vs Myanmar comparison
- Any figures or plots
- Any thesis chapter or report document

---

*Spec v1.1 — 2026-08-27. Locked after author review.*
