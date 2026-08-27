"""
R4 Unit-conversion transforms for Aurora1p5 forecast outputs.

PRECIPITATION NOTE (Constitution §IX):
    tp1h_raw is in m/hr physical space (patch applied; log_untransform already done once).
    Convert to mm/hr: max(0, tp1h_raw * 1000).
    Do NOT call aurora_log_untransform here or anywhere in this pipeline.
"""

from __future__ import annotations

import numpy as np
import xarray as xr

# Conversion factor: m/s → knots
_MS_TO_KTS = 1.9438444924574


def t2m_to_celsius(t2m_k: np.ndarray) -> np.ndarray:
    """Convert 2m temperature from Kelvin to Celsius."""
    return t2m_k - 273.15


def tp1h_to_mmhr(tp1h_raw: np.ndarray) -> np.ndarray:
    """
    Convert Aurora tp1h (m/hr, physical space) to mm/hr.

    Applies ×1000 conversion and clips negatives to 0.
    Do NOT call aurora_log_untransform — patch already applied upstream.
    """
    return np.maximum(0.0, tp1h_raw * 1000.0)


def uv_to_ws_kts(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """10m wind speed in knots from u (eastward) and v (northward) components (m/s)."""
    return np.sqrt(u ** 2 + v ** 2) * _MS_TO_KTS


def uv_to_wd_deg(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """
    10m wind direction in degrees (meteorological FROM convention).

    Returns values in [0, 360).
    Calm winds (u=0, v=0) return 0.0 by convention.
    """
    return (270.0 - np.degrees(np.arctan2(v, u))) % 360.0


def apply_all(ds: xr.Dataset) -> xr.Dataset:
    """
    Apply all unit conversions to a forecast Dataset.

    Expects variables: t2m_K, u10m, v10m, tp1h_raw
    Adds:  t2m_C, precip_mmhr, ws_kts, wd_deg

    Returns a new Dataset (original variables preserved for auditability).
    """
    t2m_c    = t2m_to_celsius(ds["t2m_K"].values)
    precip   = tp1h_to_mmhr(ds["tp1h_raw"].values)
    ws       = uv_to_ws_kts(ds["u10m"].values, ds["v10m"].values)
    wd       = uv_to_wd_deg(ds["u10m"].values, ds["v10m"].values)

    dims = ["lead_time", "lat", "lon"]
    new_vars = {
        "t2m_C": (
            dims, t2m_c.astype(np.float32),
            {"units": "deg_C", "long_name": "2m temperature"},
        ),
        "precip_mmhr": (
            dims, precip.astype(np.float32),
            {
                "units": "mm hr-1",
                "long_name": "Precipitation rate (clipped to ≥ 0)",
                "source": "tp1h_raw * 1000, clip(0); NO aurora_log_untransform",
            },
        ),
        "ws_kts": (
            dims, ws.astype(np.float32),
            {"units": "kt", "long_name": "10m wind speed"},
        ),
        "wd_deg": (
            dims, wd.astype(np.float32),
            {
                "units": "degrees",
                "long_name": "10m wind direction (FROM, meteorological)",
                "convention": "(270 - atan2(v, u)) % 360",
            },
        ),
    }

    return ds.assign(new_vars)
