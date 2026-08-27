"""
R4 ERA5 Reference Fetcher — Myanmar bbox via ARCO.

Fetches ERA5 reanalysis for the verification times corresponding to a
given forecast init_time and lead-time grid.

VARIABLE NOTES
--------------
t2m    : 2m temperature (K) from ARCO variable "t2m"
u10m   : 10m eastward wind (m/s)
v10m   : 10m northward wind (m/s)
tp06   : 6h accumulated precipitation (m) from ARCO variable "tp"
         → precip_mmhr = max(0, tp06_m * 1000 / 6)

TEMPORAL NOTE
-------------
Aurora outputs 1h steps; ERA5 tp is 6h accumulations.
This module fetches tp at 6h-multiple lead times only.
For 1h-aligned metrics, use t2m/u10m/v10m at all requested lead times.
For precipitation, metrics are computed at 6h multiples only (6, 12, 24, …).
"""

from __future__ import annotations

import datetime
from typing import Sequence

import numpy as np
import xarray as xr

# Myanmar bbox (from domain.md / constitution)
LAT_MIN, LAT_MAX = 9.0, 29.0
LON_MIN, LON_MAX = 92.0, 102.0

# ERA5 variable names in ARCO
_T2M_VAR  = "t2m"
_U10M_VAR = "u10m"
_V10M_VAR = "v10m"
_TP_VAR   = "tp"  # 6h accumulated precip in metres


def fetch_era5_reference(
    init_time: datetime.datetime,
    lead_hours: Sequence[int],
    *,
    cache: bool = False,
) -> xr.Dataset:
    """
    Fetch ERA5 reference data over Myanmar for specified lead times.

    Parameters
    ----------
    init_time  : tz-aware UTC datetime (forecast initialisation)
    lead_hours : sequence of integer lead times (hours since init_time)
    cache      : whether to enable ARCO disk cache (default False)

    Returns
    -------
    xr.Dataset with dims (lead_time, lat, lon):
        t2m_K      : 2m temperature (K)  — all lead times
        u10m       : 10m eastward wind (m/s) — all lead times
        v10m       : 10m northward wind (m/s) — all lead times
        precip_mmhr: precipitation rate (mm/hr) — 6h-multiple lead times only;
                     NaN for non-6h-multiple lead times
    Coordinates:
        lead_time  : int hours (same as input lead_hours)
        lat        : N→S [29.0, 28.75, ..., 9.0]
        lon        : W→E [92.0, 92.25, ..., 102.0]
        init_time  : np.datetime64 (tz-naive)
        valid_time : (lead_time,) array of np.datetime64 verification times
    Attributes:
        source     : "ERA5 reanalysis via ARCO"
        init_time  : ISO string
    """
    from earth2studio.data import ARCO

    lead_hours = list(lead_hours)
    init_np    = np.datetime64(init_time.replace(tzinfo=None), "ns")

    # Verification datetimes for each lead
    valid_times_dt = [
        init_time + datetime.timedelta(hours=h) for h in lead_hours
    ]

    # ── Fetch t2m / u10m / v10m ─────────────────────────────────────────────
    wind_temp_vars = [_T2M_VAR, _U10M_VAR, _V10M_VAR]
    arco = ARCO(cache=cache)
    da_wtv = arco(valid_times_dt, wind_temp_vars)
    # da_wtv: (time, variable, lat, lon); lat is N→S in ARCO

    mmr_wtv = da_wtv.sel(
        lat=slice(LAT_MAX, LAT_MIN),
        lon=slice(LON_MIN, LON_MAX),
    )

    lat_arr = mmr_wtv.coords["lat"].values.astype(np.float32)
    lon_arr = mmr_wtv.coords["lon"].values.astype(np.float32)
    n_lat   = len(lat_arr)
    n_lon   = len(lon_arr)
    n_lead  = len(lead_hours)

    t2m_K  = np.full((n_lead, n_lat, n_lon), np.nan, dtype=np.float32)
    u10m   = np.full((n_lead, n_lat, n_lon), np.nan, dtype=np.float32)
    v10m   = np.full((n_lead, n_lat, n_lon), np.nan, dtype=np.float32)

    for li, vdt in enumerate(valid_times_dt):
        try:
            t2m_K[li]  = mmr_wtv.isel(time=li).sel(variable=_T2M_VAR).values
            u10m[li]   = mmr_wtv.isel(time=li).sel(variable=_U10M_VAR).values
            v10m[li]   = mmr_wtv.isel(time=li).sel(variable=_V10M_VAR).values
        except Exception as exc:
            import sys
            print(f"[warn] ERA5 fetch failed at lead {lead_hours[li]}h: {exc}",
                  file=sys.stderr)

    # ── Fetch tp (6h accumulation) at 6h-multiple leads only ────────────────
    precip_mmhr = np.full((n_lead, n_lat, n_lon), np.nan, dtype=np.float32)

    tp_lead_idx = [i for i, h in enumerate(lead_hours) if h % 6 == 0]
    tp_valid_dt = [valid_times_dt[i] for i in tp_lead_idx]

    if tp_valid_dt:
        try:
            da_tp   = arco(tp_valid_dt, [_TP_VAR])
            mmr_tp  = da_tp.sel(
                lat=slice(LAT_MAX, LAT_MIN),
                lon=slice(LON_MIN, LON_MAX),
            )
            for rank, li in enumerate(tp_lead_idx):
                tp_m = mmr_tp.isel(time=rank).sel(variable=_TP_VAR).values
                # tp06 is in metres (6h total); convert to mm/hr rate
                precip_mmhr[li] = np.maximum(0.0, tp_m * 1000.0 / 6.0)
        except Exception as exc:
            import sys
            print(f"[warn] ERA5 tp fetch failed: {exc}", file=sys.stderr)

    # ── Build valid_time coordinate ──────────────────────────────────────────
    valid_time_np = np.array(
        [np.datetime64(vdt.replace(tzinfo=None), "ns") for vdt in valid_times_dt]
    )

    ds = xr.Dataset(
        {
            "t2m_K": (
                ["lead_time", "lat", "lon"], t2m_K,
                {"units": "K", "long_name": "2m temperature (ERA5)"},
            ),
            "u10m": (
                ["lead_time", "lat", "lon"], u10m,
                {"units": "m s-1", "long_name": "10m eastward wind (ERA5)"},
            ),
            "v10m": (
                ["lead_time", "lat", "lon"], v10m,
                {"units": "m s-1", "long_name": "10m northward wind (ERA5)"},
            ),
            "precip_mmhr": (
                ["lead_time", "lat", "lon"], precip_mmhr,
                {
                    "units": "mm hr-1",
                    "long_name": "Precipitation rate (ERA5 tp06 ÷ 6, clipped ≥ 0)",
                    "note": "NaN at non-6h-multiple lead times",
                },
            ),
        },
        coords={
            "lead_time":  np.array(lead_hours, dtype=np.int32),
            "lat":        lat_arr,
            "lon":        lon_arr,
            "init_time":  init_np,
            "valid_time": ("lead_time", valid_time_np),
        },
        attrs={
            "source":     "ERA5 reanalysis via ARCO",
            "init_time":  init_time.isoformat(),
            "note":       "ERA5 is a reference reanalysis, not observational ground truth.",
        },
    )
    return ds
