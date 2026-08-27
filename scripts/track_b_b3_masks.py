"""
Track B — B3 Land Mask and Subregion Mask Generation

Sources:
  Land mask : Natural Earth 50m admin-0 countries v5.1.1
              https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_0_countries.zip
  Subregion  : docs/subregions.md (LOCKED 2026-08-15, ADR-019)

Grid: 81×41, 0.25° step, lat 29.0→9.0 (N to S), lon 92.0→102.0 (W to E)
      Identical to Aurora NC and ERA5 verification NC grids.

A grid cell (lat, lon) is assigned to the Myanmar land mask if and only if the
point at (lon, lat) lies within the Myanmar polygon from Natural Earth.
No buffering or rounding is applied.

Subregion assignment:
  Overlap priority CDZ > RKN > NHG > SHN > SLW.
  Land mask applied first; ocean/border points excluded from all subregions.

Outputs:
  data/masks/myanmar_land_mask.npy          (81,41) bool
  data/masks/subregion_masks.npz            one bool (81,41) per subregion
  data/masks/mask_provenance.json           source metadata
"""

from __future__ import annotations
import datetime
import json
import pathlib
import numpy as np
import geopandas as gpd
from shapely.geometry import Point

ROOT       = pathlib.Path(__file__).parent.parent
MASK_DIR   = ROOT / "data" / "masks"
SHP_PATH   = ROOT / "data" / "natural_earth" / "ne_50m_admin_0_countries.shp"
OUT_LAND   = MASK_DIR / "myanmar_land_mask.npy"
OUT_SUB    = MASK_DIR / "subregion_masks.npz"
OUT_PROV   = MASK_DIR / "mask_provenance.json"

# Grid definition (must match Aurora NC and ERA5 NC exactly)
LATS = np.arange(29.0, 8.75, -0.25, dtype=np.float32)  # 29.00, 28.75, ..., 9.00  → 81 pts
LONS = np.arange(92.0, 102.25, 0.25, dtype=np.float32)  # 92.00, 92.25, ..., 102.00 → 41 pts

assert len(LATS) == 81, f"lat count {len(LATS)} ≠ 81"
assert len(LONS) == 41, f"lon count {len(LONS)} ≠ 41"
assert abs(float(LATS[0]) - 29.0)  < 1e-4
assert abs(float(LATS[-1]) - 9.0)  < 1e-4
assert abs(float(LONS[0]) - 92.0)  < 1e-4
assert abs(float(LONS[-1]) - 102.0) < 1e-4

# Subregion bbox definitions (from docs/subregions.md, LOCKED 2026-08-15)
SUBREGION_BBOXES = {
    "CDZ": dict(lat_min=19.25, lat_max=22.75, lon_min=93.75, lon_max=96.25),
    "RKN": dict(lat_min=17.75, lat_max=22.00, lon_min=92.00, lon_max=94.25),
    "NHG": dict(lat_min=23.00, lat_max=29.00, lon_min=92.00, lon_max=102.00),
    "SHN": dict(lat_min=19.00, lat_max=23.00, lon_min=96.50, lon_max=102.00),
    "SLW": dict(lat_min= 9.00, lat_max=19.25, lon_min=92.00, lon_max=102.00),
}
# Priority order: first in list = highest priority
PRIORITY_ORDER = ["CDZ", "RKN", "NHG", "SHN", "SLW"]


def build_land_mask(mmr_geom) -> np.ndarray:
    """Return bool (81,41) — True where grid point is within Myanmar land polygon."""
    mask = np.zeros((81, 41), dtype=bool)
    for i, lat in enumerate(LATS):
        for j, lon in enumerate(LONS):
            mask[i, j] = mmr_geom.contains(Point(float(lon), float(lat)))
    return mask


def build_subregion_masks(land_mask: np.ndarray) -> dict[str, np.ndarray]:
    """
    Build one bool (81,41) mask per subregion.
    Rules:
      1. Grid point must be in Myanmar land mask.
      2. Grid point must satisfy the subregion bbox.
      3. Overlap priority CDZ > RKN > NHG > SHN > SLW:
         a point already assigned to a higher-priority subregion is excluded
         from all lower-priority ones.
    """
    lat2d, lon2d = np.meshgrid(LATS, LONS, indexing="ij")  # (81, 41)

    assigned = np.zeros((81, 41), dtype=bool)  # True = already taken by a higher-priority subregion
    masks: dict[str, np.ndarray] = {}

    for sreg in PRIORITY_ORDER:
        bb = SUBREGION_BBOXES[sreg]
        bbox_mask = (
            (lat2d >= bb["lat_min"] - 1e-6) & (lat2d <= bb["lat_max"] + 1e-6) &
            (lon2d >= bb["lon_min"] - 1e-6) & (lon2d <= bb["lon_max"] + 1e-6)
        )
        sreg_mask = land_mask & bbox_mask & ~assigned
        masks[sreg] = sreg_mask
        assigned |= sreg_mask

    return masks


def main():
    MASK_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading Natural Earth 50m countries …")
    world = gpd.read_file(SHP_PATH)
    mmr_row = world[world["ISO_A3"] == "MMR"]
    if mmr_row.empty:
        raise RuntimeError("Myanmar (ISO_A3=MMR) not found in shapefile")
    mmr_geom = mmr_row.geometry.iloc[0]
    print(f"Myanmar polygon loaded. Geometry type: {mmr_geom.geom_type}")
    print(f"Myanmar bounds: {mmr_geom.bounds}")

    print("Building 81×41 land mask (point-in-polygon for 3,321 grid points) …")
    land_mask = build_land_mask(mmr_geom)
    n_land = int(land_mask.sum())
    print(f"  Land mask: {n_land} / 3321 grid points are Myanmar land")
    if n_land < 500 or n_land > 3000:
        raise ValueError(f"Myanmar land point count {n_land} outside plausible range 500–3000")

    np.save(OUT_LAND, land_mask)
    print(f"  Saved: {OUT_LAND}")

    print("Building subregion masks with priority CDZ > RKN > NHG > SHN > SLW …")
    sub_masks = build_subregion_masks(land_mask)
    counts = {sr: int(sub_masks[sr].sum()) for sr in PRIORITY_ORDER}
    total_assigned = sum(counts.values())
    for sr, n in counts.items():
        print(f"  {sr}: {n} land grid points")
    print(f"  Total assigned: {total_assigned} / {n_land} land points")
    if total_assigned != n_land:
        # Remaining points are Myanmar land but outside all 5 subregion bboxes
        unassigned = n_land - total_assigned
        print(f"  Unassigned land points: {unassigned} (outside all 5 subregion bboxes)")

    np.savez(OUT_SUB, **{sr: sub_masks[sr] for sr in PRIORITY_ORDER})
    print(f"  Saved: {OUT_SUB}")

    prov = {
        "generated": datetime.datetime.now(datetime.UTC).isoformat(),
        "land_mask": {
            "source": "Natural Earth",
            "dataset": "ne_50m_admin_0_countries",
            "version": "5.1.1",
            "url": "https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_0_countries.zip",
            "filter": "ISO_A3 == 'MMR'",
            "crs": "EPSG:4326",
            "rasterisation": "point-in-polygon (shapely.geometry.Point.within) at grid-cell centres",
            "no_buffer": True,
            "grid": {
                "shape": [81, 41],
                "lat": "29.00 to 9.00 step -0.25 (N to S)",
                "lon": "92.00 to 102.00 step +0.25 (W to E)",
            },
            "n_land_points": n_land,
            "output": str(OUT_LAND.relative_to(ROOT)),
        },
        "subregions": {
            "source_doc": "docs/subregions.md",
            "locked": "2026-08-15",
            "adr": "ADR-019",
            "priority_order": PRIORITY_ORDER,
            "bboxes": SUBREGION_BBOXES,
            "overlap_rule": "CDZ > RKN > NHG > SHN > SLW; a point assigned to higher-priority subregion is excluded from lower-priority",
            "land_mask_applied": True,
            "n_points": counts,
            "total_assigned": total_assigned,
            "unassigned_land": n_land - total_assigned,
            "output": str(OUT_SUB.relative_to(ROOT)),
        },
    }
    with open(OUT_PROV, "w") as f:
        json.dump(prov, f, indent=2)
    print(f"  Provenance: {OUT_PROV}")
    print("\nMask generation complete.")
    return land_mask, sub_masks, counts


if __name__ == "__main__":
    main()
