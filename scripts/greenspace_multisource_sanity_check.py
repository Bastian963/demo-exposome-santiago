"""Right-sized, single-annotator sanity check for the multi-source green layer.

Two modes:

- ``--select`` (default, offline): pick ~36 stratified Esri scenes from the
  existing 166-scene validation set, deliberately including Santiago's semi-arid
  peri-urban northern fringe (where Dynamic World confuses bare soil / sparse
  vegetation) so the check stresses DW's failure mode rather than only easy
  urban-core scenes. Writes a focused annotation worklist.

- ``--score`` (needs GEE + hand-drawn LabelMe polygons): for each selected scene
  that has a ``vegetation`` label, compute the vegetation *fraction* from the
  labels, OSM, Dynamic World green and Meta canopy over the scene footprint, then
  report each source's MAE vs the labels and the OSM undercount
  (labels - OSM) with a bootstrap 95% CI. This is a single-annotator
  *confirmation* — it quantifies how much green OSM misses and whether DW+canopy
  recover it; it is not the formal inter-annotator approval gate (see
  docs/greenspace_cv_approval_checklist.md).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

VALID_DIR = REPO_ROOT / "data" / "validation" / "greenspace_cv"
SITES_CSV = VALID_DIR / "greenspace_cv_sites.csv"
WORKLIST_CSV = VALID_DIR / "multisource_sanity_worklist.csv"
REPORT_JSON = REPO_ROOT / "data" / "processed" / "santiago_greenspace_multisource_sanity.json"

# Semi-arid / peri-urban RM communes where Dynamic World is weakest (bare soil and
# dry matorral vs. real vegetation). These must be represented in the check.
PERIURBAN_NORTH = {
    "Tiltil", "Til Til", "Colina", "Lampa", "Quilicura", "Huechuraba",
    "Pudahuel", "María Pinto", "Maria Pinto", "Curacaví", "Curacavi",
}


def select_scenes(n_target: int = 36, seed: int = 42) -> pd.DataFrame:
    """Stratified scene selection, guaranteeing peri-urban north coverage."""
    sites = pd.read_csv(SITES_CSV)
    sample = sites[sites["stratum"] != "showcase"].copy()

    # 1) All available peri-urban north scenes (DW failure mode), prefer the
    #    highest OSM-undercount scene per commune.
    peri = sample[sample["comuna"].isin(PERIURBAN_NORTH)]
    peri_pick = (
        peri.sort_values("cv_outside_osm_pct", ascending=False)
        .groupby("comuna", as_index=False)
        .head(1)
    )

    # 2) Fill the rest with the highest OSM-undercount scenes (cv_outside_high),
    #    one per commune, spread across the city.
    remaining = sample[~sample["site_id"].isin(peri_pick["site_id"])]
    outside = (
        remaining[remaining["stratum"] == "cv_outside_high"]
        .sort_values("cv_outside_osm_pct", ascending=False)
        .groupby("comuna", as_index=False)
        .head(1)
    )
    fill = outside.head(max(0, n_target - len(peri_pick)))

    picked = pd.concat([peri_pick, fill], ignore_index=True)
    picked = picked.drop_duplicates("site_id").head(n_target)
    picked = picked.sort_values(["comuna", "site_id"]).reset_index(drop=True)
    return picked[
        ["site_id", "name", "comuna", "lat", "lon", "zoom", "stratum",
         "osm_green_pct", "cv_outside_osm_pct", "image_path", "label_path"]
    ]


def _write_worklist(picked: pd.DataFrame) -> None:
    picked = picked.copy()
    picked["label_present"] = picked["label_path"].map(
        lambda p: _has_polygons(REPO_ROOT / p) if isinstance(p, str) else False
    )
    WORKLIST_CSV.parent.mkdir(parents=True, exist_ok=True)
    picked.to_csv(WORKLIST_CSV, index=False)
    n_peri = picked["comuna"].isin(PERIURBAN_NORTH).sum()
    print(f"Selected {len(picked)} scenes across {picked['comuna'].nunique()} communes "
          f"({n_peri} peri-urban north).")
    print(f"Labeled so far: {int(picked['label_present'].sum())}/{len(picked)}.")
    print(f"Wrote {WORKLIST_CSV.relative_to(REPO_ROOT)}")
    print("Annotate the `vegetation` polygons in LabelMe, then re-run with --score.")


def _has_polygons(label_path: Path) -> bool:
    if not label_path.exists():
        return False
    try:
        data = json.loads(label_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return any(s.get("label") == "vegetation" for s in data.get("shapes", []))


def _label_fraction(label_path: Path) -> float | None:
    """Fraction of the scene image area covered by `vegetation` polygons."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    if not label_path.exists():
        return None
    data = json.loads(label_path.read_text(encoding="utf-8"))
    w = data.get("imageWidth")
    h = data.get("imageHeight")
    if not w or not h:
        return None
    polys = [
        Polygon(s["points"])
        for s in data.get("shapes", [])
        if s.get("label") == "vegetation" and len(s.get("points", [])) >= 3
    ]
    if not polys:
        return 0.0
    area = unary_union([p.buffer(0) for p in polys]).area
    return float(min(1.0, area / (w * h)))


def _scene_bbox(lat: float, lon: float, zoom: int, n_tiles: int = 3, tile_px: int = 256):
    """Return the lon/lat bbox of the NxN tile mosaic centered on (lat, lon)."""
    from exposome.greenspace_cv import _deg2tile, _tile2deg

    xf, yf = _deg2tile(lat, lon, zoom)
    half = n_tiles / 2.0
    west, north = _tile2deg(xf - half, yf - half, zoom)
    east, south = _tile2deg(xf + half, yf + half, zoom)
    return west, south, east, north


def score(picked: pd.DataFrame) -> dict:
    import ee
    from exposome import config, gee
    from exposome.greenspace_multisource import build_dynamic_world_masks, build_canopy_image

    cfg = config.load_config("santiago_communes")
    gee.init_gee()
    dw_cfg = cfg["greenspace"]["dynamic_world"]
    canopy_cfg = cfg["greenspace"]["canopy"]

    rows = []
    for r in picked.itertuples():
        label_path = REPO_ROOT / r.label_path
        veg_frac = _label_fraction(label_path)
        if veg_frac is None:
            continue  # not annotated yet
        west, south, east, north = _scene_bbox(r.lat, r.lon, int(r.zoom))
        rect = ee.Geometry.Rectangle([west, south, east, north])
        dw_green = build_dynamic_world_masks(
            rect, dw_cfg["years"], dw_cfg["season_months"], dw_cfg["green_classes"]
        ).select("green")
        canopy = build_canopy_image(
            rect, canopy_cfg["collection"], canopy_cfg["band"], canopy_cfg["min_height_m"]
        ).select("canopy_cover")
        dw_frac = dw_green.reduceRegion(ee.Reducer.mean(), rect, scale=10, maxPixels=1e9, bestEffort=True).get("green").getInfo()
        can_frac = canopy.reduceRegion(ee.Reducer.mean(), rect, scale=5, maxPixels=1e9, bestEffort=True).get("canopy_cover").getInfo()
        rows.append({
            "site_id": r.site_id, "comuna": r.comuna,
            "label_frac": veg_frac,
            "osm_frac": (r.osm_green_pct or 0.0) / 100.0,
            "dw_frac": float(dw_green if dw_frac is None else dw_frac) if dw_frac is not None else 0.0,
            "canopy_frac": 0.0 if can_frac is None else float(can_frac),
        })

    if not rows:
        print("No annotated scenes yet — draw `vegetation` polygons first, then --score.")
        return {}

    df = pd.DataFrame(rows)
    df["dw_plus_canopy_frac"] = np.maximum(df["dw_frac"], df["canopy_frac"])
    rng = np.random.default_rng(0)

    def boot_ci(x: np.ndarray) -> list[float]:
        means = [rng.choice(x, size=len(x), replace=True).mean() for _ in range(2000)]
        return [round(float(np.percentile(means, 2.5)), 4), round(float(np.percentile(means, 97.5)), 4)]

    undercount = (df["label_frac"] - df["osm_frac"]).to_numpy()
    report = {
        "n_scenes": int(len(df)),
        "n_communes": int(df["comuna"].nunique()),
        "osm_undercount_mean": round(float(undercount.mean()), 4),
        "osm_undercount_ci95": boot_ci(undercount),
        "mae_vs_labels": {
            src: round(float((df[f"{src}_frac"] - df["label_frac"]).abs().mean()), 4)
            for src in ["osm", "dw", "canopy", "dw_plus_canopy"]
        },
        "note": "Single-annotator confirmation; not the inter-annotator approval gate.",
    }
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Wrote {REPORT_JSON.relative_to(REPO_ROOT)}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--score", action="store_true", help="Score sources vs labels (needs GEE + annotations)")
    parser.add_argument("--n", type=int, default=36, help="Target number of scenes")
    args = parser.parse_args()

    picked = select_scenes(n_target=args.n)
    _write_worklist(picked)
    if args.score:
        score(picked)


if __name__ == "__main__":
    main()
