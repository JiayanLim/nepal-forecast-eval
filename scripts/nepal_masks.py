"""
P1.02 — Nepal land mask generator.

Source: Natural Earth 50m admin-0 countries v5.1.1
        data/natural_earth/ne_50m_admin_0_countries.shp
Method: Point-in-polygon test (Shapely) for Nepal polygon (ADMIN == 'Nepal').
        No buffering. No rounding.

Grid: 19 × 35, 0.25° spacing.
  lat: 30.5, 30.25, ..., 26.0 (N→S, 19 points)
  lon: 80.0, 80.25, ..., 88.5 (W→E, 35 points)
  Must match Aurora output extraction bbox exactly.

Outputs:
  data/masks/nepal_land_mask.npy      (19, 35) bool
  data/masks/nepal_mask_provenance.json
"""

from __future__ import annotations

import datetime
import json
import pathlib

import geopandas as gpd
import numpy as np
from shapely.geometry import Point

ROOT      = pathlib.Path(__file__).parent.parent
SHP_PATH  = ROOT / "data" / "natural_earth" / "ne_50m_admin_0_countries.shp"
MASK_DIR  = ROOT / "data" / "masks"
OUT_LAND  = MASK_DIR / "nepal_land_mask.npy"
OUT_PROV  = MASK_DIR / "nepal_mask_provenance.json"

MASK_DIR.mkdir(parents=True, exist_ok=True)

# ── Grid definition (LOCKED — must match Aurora Nepal bbox extraction) ─────
LATS = np.round(np.arange(30.5, 25.99, -0.25), 2).astype(np.float32)  # 19 pts N→S
LONS = np.round(np.arange(80.0, 88.51,  0.25), 2).astype(np.float32)  # 35 pts W→E

assert len(LATS) == 19, f"lat count {len(LATS)} ≠ 19"
assert len(LONS) == 35, f"lon count {len(LONS)} ≠ 35"
assert abs(float(LATS[0])  - 30.5) < 1e-4, f"lat[0] = {LATS[0]} ≠ 30.5"
assert abs(float(LATS[-1]) - 26.0) < 1e-4, f"lat[-1] = {LATS[-1]} ≠ 26.0"
assert abs(float(LONS[0])  - 80.0) < 1e-4, f"lon[0] = {LONS[0]} ≠ 80.0"
assert abs(float(LONS[-1]) - 88.5) < 1e-4, f"lon[-1] = {LONS[-1]} ≠ 88.5"

# ── Load Nepal polygon ─────────────────────────────────────────────────────
print(f"Loading shapefile: {SHP_PATH}")
world = gpd.read_file(SHP_PATH)
nepal_rows = world[world["ADMIN"] == "Nepal"]
if len(nepal_rows) != 1:
    raise ValueError(f"Expected 1 Nepal polygon, found {len(nepal_rows)}")
nepal_geom = nepal_rows.geometry.iloc[0]
print(f"Nepal polygon loaded. Bounds: {nepal_geom.bounds}")

# ── Build land mask ────────────────────────────────────────────────────────
print(f"Building land mask ({len(LATS)} lat × {len(LONS)} lon = {len(LATS)*len(LONS)} cells) …")
mask = np.zeros((len(LATS), len(LONS)), dtype=bool)

for i, lat in enumerate(LATS):
    for j, lon in enumerate(LONS):
        mask[i, j] = nepal_geom.contains(Point(float(lon), float(lat)))

n_land = int(mask.sum())
print(f"Nepal land cells: {n_land} / {mask.size} ({100*n_land/mask.size:.1f}%)")

# Sanity checks
assert n_land > 0, "No land cells found — polygon or grid error"
# Kathmandu should be inside: 85.3E, 27.7N
ktm_lat_idx = int(round((LATS[0] - 27.7) / 0.25))
ktm_lon_idx = int(round((85.3 - LONS[0]) / 0.25))
if 0 <= ktm_lat_idx < 19 and 0 <= ktm_lon_idx < 35:
    if not mask[ktm_lat_idx, ktm_lon_idx]:
        print(f"  WARNING: Kathmandu cell ({ktm_lat_idx},{ktm_lon_idx}) = lat {LATS[ktm_lat_idx]}, "
              f"lon {LONS[ktm_lon_idx]} is NOT in mask. Check grid alignment.")

# ── Save mask ──────────────────────────────────────────────────────────────
np.save(OUT_LAND, mask)
print(f"Saved: {OUT_LAND}")

# ── Provenance ─────────────────────────────────────────────────────────────
provenance = {
    "spec_id":          "002-nepal-eval",
    "spec_version":     "v1.1",
    "generated_utc":    datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "source":           "Natural Earth 50m admin-0 countries v5.1.1",
    "source_file":      str(SHP_PATH.relative_to(ROOT)),
    "filter":           "ADMIN == 'Nepal'",
    "method":           "shapely.geometry.Point.within(nepal_polygon); no buffering",
    "grid": {
        "n_lat":        int(len(LATS)),
        "n_lon":        int(len(LONS)),
        "lat_min":      float(LATS[-1]),
        "lat_max":      float(LATS[0]),
        "lon_min":      float(LONS[0]),
        "lon_max":      float(LONS[-1]),
        "lat_step":     -0.25,
        "lon_step":     0.25,
        "lat_sequence": [float(x) for x in LATS],
        "lon_sequence": [float(x) for x in LONS],
    },
    "n_land_cells":     n_land,
    "n_total_cells":    int(mask.size),
    "land_fraction":    round(n_land / mask.size, 4),
    "output_file":      str(OUT_LAND.relative_to(ROOT)),
    "nepal_polygon_bounds": {
        "minx": nepal_geom.bounds[0],
        "miny": nepal_geom.bounds[1],
        "maxx": nepal_geom.bounds[2],
        "maxy": nepal_geom.bounds[3],
    },
}

with open(OUT_PROV, "w") as f:
    json.dump(provenance, f, indent=2)
print(f"Saved: {OUT_PROV}")

# ── Summary ────────────────────────────────────────────────────────────────
print("\nLand cell distribution by latitude band:")
for band_name, lat_lo, lat_hi in [("HIM (29.0–30.5N)", 29.0, 30.5),
                                   ("HIL (27.0–29.0N)", 27.0, 29.0),
                                   ("TER (26.0–27.0N)", 26.0, 27.0)]:
    band_mask = np.zeros_like(mask)
    for i, lat in enumerate(LATS):
        if lat_lo <= float(lat) <= lat_hi:
            band_mask[i] = mask[i]
    print(f"  {band_name}: {int(band_mask.sum())} cells")
