"""
Aurora1p5 Inference Pipeline — configurable bbox extraction.

Runs a single N_STEPS Aurora1p5 forecast and returns an xr.Dataset
containing t2m_K, u10m, v10m, tp1h_raw over the specified bbox.

Supports Myanmar (001-zero-shot-eval) and Nepal (002-nepal-eval) domains
via the `domain` parameter on run_forecast().

PATCH REQUIREMENT (Constitution §IX)
--------------------------------------
Earth2Studio 0.17.0 aurora1p5.py must have needs_log_untransform=False
for ("tp1h", "scaled_tp_1h") and ("sf1h", "scaled_sf_1h").
This module verifies that at import time and raises RuntimeError if absent.

PRECIPITATION CONVENTION
--------------------------
With patch applied:
    tp1h_raw  = Aurora tp1h output (m/hr, physical space — log_untransform
                already applied once by AuroraV1p5._post_unnorm_hook)
    precip_mmhr = max(0, tp1h_raw * 1000)   [mm/hr]

Do NOT call aurora_log_untransform anywhere in this pipeline.
"""

from __future__ import annotations

import datetime
import importlib.util
import sys
from collections import OrderedDict
from typing import Optional

import numpy as np
import torch
import xarray as xr

# ── Domain presets ────────────────────────────────────────────────────────────
DOMAIN_MYANMAR = (9.0, 29.0, 92.0, 102.0)   # (lat_min, lat_max, lon_min, lon_max)
DOMAIN_NEPAL   = (26.0, 30.5, 80.0, 88.5)

N_STEPS = 168
_COLLECT_VARS = {"t2m", "u10m", "v10m", "tp1h"}

# ── Patch verification ────────────────────────────────────────────────────────

def verify_patch(raise_on_fail: bool = True) -> bool:
    """
    Check that the E2S aurora1p5.py precipitation patch is applied.

    Returns True if patch is active; raises RuntimeError (or returns False)
    if the broken needs_log_untransform=True lines are found.
    """
    spec = importlib.util.find_spec("earth2studio.models.px.aurora1p5")
    if spec is None:
        msg = "earth2studio.models.px.aurora1p5 not found — is the environment active?"
        if raise_on_fail:
            raise RuntimeError(msg)
        return False
    src = open(spec.origin).read()
    tp_ok = '"scaled_tp_1h", False),' in src and '"scaled_tp_1h", True),' not in src
    sf_ok = '"scaled_sf_1h", False),' in src and '"scaled_sf_1h", True),' not in src
    if tp_ok and sf_ok:
        return True
    msg = (
        "E2S aurora1p5.py precipitation patch NOT applied. "
        "Needs: '(\"scaled_tp_1h\", False),' and '(\"scaled_sf_1h\", False),' at lines 128-129. "
        "See Constitution §IX and /tmp/patch_tp.py on the Brev instance."
    )
    if raise_on_fail:
        raise RuntimeError(msg)
    return False


# ── Model wrapper ─────────────────────────────────────────────────────────────

class _BboxCollector:
    """
    Wraps Aurora1p5 and overrides create_iterator to extract a regional bbox
    at each step. Collects t2m, u10m, v10m, tp1h per lead time.

    Uses object.__setattr__ to avoid __getattr__ delegation for internal
    attributes. Delegates everything else to the inner model.
    """

    def __init__(
        self,
        inner,
        lat_mask: np.ndarray,
        lon_mask: np.ndarray,
        aurora_n_lat: int,
        aurora_n_lon: int,
        aurora_lat_is_sn: bool,
    ) -> None:
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_lat_mask", lat_mask)
        object.__setattr__(self, "_lon_mask", lon_mask)
        object.__setattr__(self, "_aurora_n_lat", aurora_n_lat)
        object.__setattr__(self, "_aurora_n_lon", aurora_n_lon)
        object.__setattr__(self, "_aurora_lat_is_sn", aurora_lat_is_sn)
        # records: list of dicts {lead_h: int, var: np.ndarray(n_lat, n_lon)}
        object.__setattr__(self, "records", [])

    def create_iterator(self, x, coords):
        """Intercept E2S create_iterator; collect regional bbox at each step."""
        for x_out, c_out in self._inner.create_iterator(x, coords):
            try:
                self._collect_step(x_out, c_out)
            except Exception as exc:
                import traceback as _tb
                print(f"[warn] collector step error: {exc}", file=sys.stderr)
                _tb.print_exc(file=sys.stderr)
            yield x_out, c_out

    def _collect_step(self, x_out, c_out) -> None:
        x_np = x_out.detach().cpu().float().numpy()
        ck = list(c_out.keys())

        var_list = list(c_out.get("variable", []))
        lt_arr   = list(c_out.get("lead_time", [None]))
        lt_dim   = ck.index("lead_time") if "lead_time" in ck else None
        var_dim  = ck.index("variable")  if "variable"  in ck else None

        # Remaining coord keys (for lat/lon axis mapping within slab)
        rem = [k for k in ck if k not in ("lead_time", "variable")]
        lat_di = rem.index("lat") if "lat" in rem else None
        lon_di = rem.index("lon") if "lon" in rem else None

        n_lt = x_np.shape[lt_dim] if lt_dim is not None else 1

        for lt_i in range(n_lt):
            lt = lt_arr[lt_i] if lt_i < len(lt_arr) else None
            try:
                lt_h = int(lt.total_seconds() / 3600)
            except Exception:
                try:
                    lt_h = int(lt / np.timedelta64(1, "h"))
                except Exception:
                    lt_h = None

            rec: dict = {"lead_h": lt_h}

            for vname in _COLLECT_VARS:
                if vname not in var_list:
                    continue
                vi = var_list.index(vname)

                # Build index into x_np: use integer for lead_time and variable dims
                idx = [slice(None)] * x_np.ndim
                if lt_dim is not None:
                    idx[lt_dim] = lt_i
                if var_dim is not None:
                    idx[var_dim] = vi
                slab = x_np[tuple(idx)]  # shape: (batch?, lat, lon) in rem order

                # Compress lat to bbox range (only if global size)
                if lat_di is not None and slab.shape[lat_di] == self._aurora_n_lat:
                    slab = np.compress(self._lat_mask, slab, axis=lat_di)
                # Compress lon to bbox range
                if lon_di is not None and slab.shape[lon_di] == self._aurora_n_lon:
                    slab = np.compress(self._lon_mask, slab, axis=lon_di)

                # Squeeze all non-lat/lon dims (batch size=1)
                while slab.ndim > 2:
                    slab = slab[0]

                # Aurora lat is S→N; flip to N→S for consistency with schema
                if self._aurora_lat_is_sn and lat_di is not None:
                    slab = np.flip(slab, axis=0).copy()

                rec[vname] = slab

            self.records.append(rec)

    # Delegation — must return self from device/mode calls so E2S doesn't unwrap
    def to(self, *a, **kw):
        self._inner.to(*a, **kw)
        return self

    def cuda(self, device=None):
        self._inner.cuda(device)
        return self

    def cpu(self):
        self._inner.cpu()
        return self

    def eval(self):
        self._inner.eval()
        return self

    def train(self, mode=True):
        self._inner.train(mode)
        return self

    def __getattr__(self, name):
        return getattr(self._inner, name)


# ── Public API ────────────────────────────────────────────────────────────────

def load_model(device: str = "cuda"):
    """Load Aurora1p5 from cached checkpoint. Verifies patch first."""
    verify_patch()
    from earth2studio.models.px import Aurora1p5
    pkg = Aurora1p5.load_default_package()
    model = Aurora1p5.load_model(pkg).to(device).eval()
    return model


def run_forecast(
    init_time: datetime.datetime,
    model,
    device: str = "cuda",
    nsteps: int = N_STEPS,
    verbose: bool = True,
    domain: tuple[float, float, float, float] = DOMAIN_MYANMAR,
) -> xr.Dataset:
    """
    Run Aurora1p5 forecast. Returns xr.Dataset over the specified bbox.

    Parameters
    ----------
    init_time : tz-aware UTC datetime
    model     : loaded Aurora1p5 (from load_model)
    device    : "cuda" or "cpu"
    nsteps    : number of 1h steps (default 168 = 7 days)
    verbose   : show E2S progress bar
    domain    : (lat_min, lat_max, lon_min, lon_max) bounding box

    Returns
    -------
    xr.Dataset with dims (lead_time, lat, lon):
        t2m_K       : 2m temperature (K)
        u10m        : 10m eastward wind (m/s)
        v10m        : 10m northward wind (m/s)
        tp1h_raw    : tp1h from E2S, physical m/hr (patch applied)
    Coordinates:
        lead_time   : int, hours since init_time (1 … nsteps)
        lat         : float, N→S
        lon         : float, W→E
        init_time   : np.datetime64 (tz-naive)
    Attributes include patch_status and provenance.
    """
    import time as _time
    from earth2studio.data import ARCO
    from earth2studio.run import deterministic

    verify_patch()

    # E2S ARCO has a hard-coded ARCO_TIME_STOP (default 2025-12-31) that
    # rejects ERA5T dates. The zarr store's valid_time_stop attr extends it
    # after async init, but validation runs before init. Override here for
    # ERA5T dates confirmed available via P1/P2 gate (through 2026-08-15).
    arco_cutoff = datetime.datetime(2026, 8, 15)
    init_naive = init_time.replace(tzinfo=None) if init_time.tzinfo else init_time
    if init_naive > ARCO.ARCO_TIME_STOP:
        ARCO.ARCO_TIME_STOP = arco_cutoff

    lat_min, lat_max, lon_min, lon_max = domain

    # Determine Aurora grid from output_coords
    in_c  = model.input_coords()
    out_c = model.output_coords(in_c)
    aurora_lat = np.array(out_c["lat"])
    aurora_lon = np.array(out_c["lon"])

    lat_is_sn = bool(aurora_lat[0] < aurora_lat[-1])  # True → S→N ordering
    lat_mask  = (aurora_lat >= lat_min) & (aurora_lat <= lat_max)
    lon_mask  = (aurora_lon >= lon_min) & (aurora_lon <= lon_max)

    # lat_arr for the output dataset (N→S)
    lat_arr = aurora_lat[lat_mask]
    if lat_is_sn:
        lat_arr = lat_arr[::-1].copy()
    lon_arr = aurora_lon[lon_mask]

    # Wrap model with bbox collector
    collector = _BboxCollector(
        inner=model,
        lat_mask=lat_mask,
        lon_mask=lon_mask,
        aurora_n_lat=len(aurora_lat),
        aurora_n_lon=len(aurora_lon),
        aurora_lat_is_sn=lat_is_sn,
    )

    # NullIO — no disk writes during inference
    class _NullIO:
        def write(self, *a, **kw):   pass
        def add_array(self, *a, **kw): pass
        def __call__(self, *a, **kw): pass
        def close(self):              pass

    t_start = _time.perf_counter()
    deterministic(
        time=[init_time],
        nsteps=nsteps,
        prognostic=collector,
        data=ARCO(),
        io=_NullIO(),
        output_coords=OrderedDict(),
        device=torch.device(device),
        verbose=verbose,
    )
    wall_s = _time.perf_counter() - t_start

    # Build dataset from collected records
    recs = [r for r in collector.records if r.get("lead_h") and r["lead_h"] > 0]
    recs.sort(key=lambda r: r["lead_h"])

    if not recs:
        raise RuntimeError(
            "No steps collected. The collector did not intercept create_iterator. "
            "Check that the model wrapper is correct."
        )

    lead_hours = [r["lead_h"] for r in recs]

    def _stack(varname: str) -> np.ndarray:
        return np.stack(
            [r[varname] for r in recs if varname in r],
            axis=0,
        ).astype(np.float32)

    t2m_K    = _stack("t2m")
    u10m     = _stack("u10m")
    v10m     = _stack("v10m")
    tp1h_raw = _stack("tp1h")

    init_np = np.datetime64(init_time.replace(tzinfo=None), "ns")

    ds = xr.Dataset(
        {
            "t2m_K": (
                ["lead_time", "lat", "lon"], t2m_K,
                {"units": "K", "long_name": "2m temperature"},
            ),
            "u10m": (
                ["lead_time", "lat", "lon"], u10m,
                {"units": "m s-1", "long_name": "10m eastward wind"},
            ),
            "v10m": (
                ["lead_time", "lat", "lon"], v10m,
                {"units": "m s-1", "long_name": "10m northward wind"},
            ),
            "tp1h_raw": (
                ["lead_time", "lat", "lon"], tp1h_raw,
                {
                    "units": "m hr-1",
                    "long_name": (
                        "Aurora tp1h, physical space (patch applied — "
                        "log_untransform applied once internally)"
                    ),
                },
            ),
        },
        coords={
            "lead_time": np.array(lead_hours, dtype=np.int32),
            "lat":       lat_arr.astype(np.float32),
            "lon":       lon_arr.astype(np.float32),
            "init_time": init_np,
        },
        attrs={
            "model_id":           "aurora1p5",
            "earth2studio_ver":   "0.17.0",
            "init_time":          init_time.isoformat(),
            "n_steps":            nsteps,
            "n_steps_collected":  len(recs),
            "wall_clock_s":       round(wall_s, 1),
            "patch_status":       "R3.P3 applied — needs_log_untransform=False for tp1h/sf1h",
            "precip_convention":  (
                "tp1h_raw is in m/hr physical space. "
                "Convert to mm/hr: max(0, tp1h_raw * 1000). "
                "Do NOT call aurora_log_untransform."
            ),
            "domain":             f"({lat_min}, {lat_max}, {lon_min}, {lon_max})",
            "lat_convention":     f"N→S [{lat_max}, ..., {lat_min}]",
            "lon_convention":     f"W→E [{lon_min}, ..., {lon_max}]",
        },
    )
    return ds
