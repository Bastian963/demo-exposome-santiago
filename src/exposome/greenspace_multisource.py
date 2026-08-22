"""Multi-source greenspace layer: Dynamic World (10 m) + Meta canopy (1 m).

This layer complements the OSM accessibility layer (`greenspace_access`) and the
Landsat coverage layer (`greenspace_coverage`) with two peer-reviewed global
products that each close a different gap in what single sources miss:

- **Dynamic World V1** (10 m, near-real-time LULC): total vegetated cover
  including lawns and informal/low green that OSM never maps. Cover is measured
  as the *argmax fractional cover* of a peak-season median-probability composite
  (the Dynamic World convention), not a sum of probabilities.
- **Meta/WRI Global Canopy Height** (1 m): street-tree canopy that OSM omits and
  that Dynamic World's 10 m argmax misses in dense blocks (a street tree is
  rarely the dominant class of a 10 m pixel). Reliable only when aggregated
  (>=30 m); here it is always reduced to commune / grid-cell means.

The scientific spine — each source captures a distinct, measurable slice of urban
green — is what makes the reconciliation defensible rather than "three green
numbers". See docs/greenspace_multisource_methodology.md.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ee
import geopandas as gpd
import pandas as pd
from tqdm import tqdm

from . import boundaries, config, gee
from .cache import CacheIdentity, CacheStore, spatial_fingerprint


# Dynamic World V1 class band order (index == class value in the ``label`` band).
DW_CLASSES = [
    "water",
    "trees",
    "grass",
    "flooded_vegetation",
    "crops",
    "shrub_and_scrub",
    "built",
    "bare",
    "snow_and_ice",
]
_DW_INDEX = {name: i for i, name in enumerate(DW_CLASSES)}


def _season_filter(season_months: list[int]) -> ee.Filter:
    """Build a month filter that correctly handles a wrap-around season.

    ``ee.Filter.calendarRange(start, end)`` does not wrap when ``start > end``
    (e.g. Oct->Mar), so a Southern-Hemisphere spring-summer season is expressed
    as an OR of contiguous month ranges.
    """
    months = sorted(set(season_months))
    if not months or months == list(range(1, 13)):
        return ee.Filter.calendarRange(1, 12, "month")
    # Split into contiguous runs, then OR them (handles the Dec->Jan wrap).
    runs: list[list[int]] = []
    for m in months:
        if runs and m == runs[-1][-1] + 1:
            runs[-1].append(m)
        else:
            runs.append([m])
    # Merge a run ending in December with a run starting in January (wrap).
    if len(runs) >= 2 and runs[0][0] == 1 and runs[-1][-1] == 12:
        filters = [ee.Filter.calendarRange(runs[-1][0], 12, "month"),
                   ee.Filter.calendarRange(1, runs[0][-1], "month")]
        for run in runs[1:-1]:
            filters.append(ee.Filter.calendarRange(run[0], run[-1], "month"))
    else:
        filters = [ee.Filter.calendarRange(run[0], run[-1], "month") for run in runs]
    return filters[0] if len(filters) == 1 else ee.Filter.Or(*filters)


def build_dynamic_world_masks(
    roi: ee.Geometry,
    years: list[int],
    season_months: list[int],
    green_classes: list[str],
) -> ee.Image:
    """Peak-season Dynamic World argmax cover masks (green / tree / grass).

    Returns an image with binary bands ``green``, ``tree`` and ``grass`` whose
    zonal means give the fractional cover of each class.

    Cover is the *argmax fractional cover* of a peak-season mean-probability
    composite (the Dynamic World convention): a pixel is green if the strongest
    green-class probability exceeds every non-green-class probability. This is
    computed with cheap per-band ``max`` reducers on a single mean image rather
    than a per-pixel ``arrayArgmax`` over the stack, which times out GEE at
    regional scale.
    """
    start_date = f"{min(years)}-01-01"
    end_date = f"{max(years) + 1}-01-01"
    collection = (
        ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
        .filterBounds(roi)
        .filterDate(start_date, end_date)
        .filter(_season_filter(season_months))
    )
    mean_prob = collection.select(DW_CLASSES).mean()

    non_green = [c for c in DW_CLASSES if c not in green_classes]
    green_max = mean_prob.select(green_classes).reduce(ee.Reducer.max())
    non_green_max = mean_prob.select(non_green).reduce(ee.Reducer.max())
    green = green_max.gt(non_green_max).rename("green")

    def _class_dominant(cls: str) -> ee.Image:
        others = [c for c in DW_CLASSES if c != cls]
        others_max = mean_prob.select(others).reduce(ee.Reducer.max())
        return mean_prob.select(cls).gt(others_max)

    tree = _class_dominant("trees").rename("tree")
    grass = _class_dominant("grass").rename("grass")
    return green.addBands([tree, grass]).clip(roi)


def build_canopy_image(
    roi: ee.Geometry,
    collection_id: str,
    band: str,
    min_height_m: float,
) -> ee.Image:
    """Meta/WRI canopy-height mosaic as cover mask + height bands.

    ``band`` (``cover_code``) is canopy height in integer metres: 0 == no
    canopy, >=1 == tree height. ``canopy_cover`` is the mask ``height >=
    min_height_m``; its zonal mean is the tree-canopy cover fraction.
    """
    # ``mosaic()`` has no reliable default projection when the source is a
    # tiled ImageCollection.  ``reduceResolution`` rejects that image even
    # though each source tile has a valid native grid.  Keep one source tile's
    # projection as the default before deriving the 30 m canopy fraction; this
    # preserves a provider grid rather than inventing a study or commune grid.
    collection = ee.ImageCollection(collection_id).filterBounds(roi).select(band)
    source = ee.Image(collection.first()).select(band)
    canopy = collection.mosaic().setDefaultProjection(source.projection()).select(band)
    cover = canopy.gte(min_height_m).rename("canopy_cover")
    height = canopy.toFloat().rename("canopy_height")
    return cover.addBands(height).clip(roi)


def _zonal_means(
    image: ee.Image,
    regions: ee.FeatureCollection,
    scale: int,
    *,
    tile_scale: int = 16,
) -> dict[str, dict[str, Any]]:
    """Zonal mean of every band over each region, keyed by the ``name`` field."""
    stats = image.reduceRegions(
        collection=regions,
        reducer=ee.Reducer.mean(),
        scale=scale,
        crs="EPSG:4326",
        tileScale=tile_scale,
    )
    rows = gee.fc_to_dicts(stats)
    return {r["name"]: r for r in rows if "name" in r}


def _checkpointed_zonal_means(
    *,
    image: ee.Image,
    communes: "gpd.GeoDataFrame",
    scale: int,
    store: CacheStore,
    required_columns: list[str],
    label: str,
) -> dict[str, dict[str, Any]]:
    """Reduce one spatial unit at a time and checkpoint each valid result.

    A single ``reduceRegions`` call for an entire large study area can exceed
    Earth Engine's interactive deadline.  Per-unit reductions are smaller and,
    importantly, survive an interruption or a provider timeout: the validated
    partial cache is read before the next attempt.
    """
    checkpoint = store.load_checkpoint_csv("zonal", required_columns=required_columns)
    stats: dict[str, dict[str, Any]] = {}
    if checkpoint.hit and checkpoint.frame is not None:
        stats = {
            str(row["name"]): row
            for row in checkpoint.frame.to_dict("records")
            if "name" in row
        }
        tqdm.write(f"  [{label}] {checkpoint.reason}; resuming {len(stats)}/{len(communes)} units …")

    ordered = communes.assign(_name=communes["name"].astype(str)).sort_values("_name")
    pending = ordered.loc[~ordered["_name"].isin(stats)]
    progress = tqdm(
        total=len(communes),
        initial=len(stats),
        desc=f"  [{label}] GEE zones",
        unit="unit",
    )
    try:
        for name, row in pending.set_index("_name", drop=False).iterrows():
            region = gpd.GeoDataFrame([row], geometry="geometry", crs=communes.crs)
            region_fc = gee.gdf_to_feature_collection(region.drop(columns="_name"))
            fetched = _zonal_means(image, region_fc, scale, tile_scale=16)
            value = fetched.get(str(name))
            if value is None:
                raise ValueError(f"{label} returned no zonal result for {name!r}")
            stats[str(name)] = value
            frame = pd.DataFrame(list(stats.values())).sort_values("name")
            store.checkpoint_csv("zonal", frame, completed_keys=stats)
            progress.update(1)
    finally:
        progress.close()

    frame = pd.DataFrame(list(stats.values())).sort_values("name")
    store.write_csv_atomic("zonal", frame, completed_keys=stats)
    return stats


def _write_multisource_figure(gdf: "gpd.GeoDataFrame", out_path: Path) -> None:
    """Diagnostic map: Dynamic World green cover % and canopy cover %."""
    import matplotlib.pyplot as plt

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    plots = [
        ("green_total_pct", "Cobertura verde Dynamic World (%)", "Greens", "%"),
        ("canopy_cover_pct", "Cobertura de dosel Meta 1 m (%)", "YlGn", "%"),
    ]
    for ax, (column, title, cmap, label) in zip(axes, plots, strict=True):
        gdf.plot(
            column=column,
            ax=ax,
            cmap=cmap,
            legend=True,
            legend_kwds={"label": label, "shrink": 0.65},
            edgecolor="white",
            linewidth=0.3,
        )
        ax.set_title(title, fontsize=12)
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _write_multisource_metadata(
    path: Path,
    *,
    city: str,
    dw_cfg: dict,
    canopy_cfg: dict,
    dw_scale: int,
    canopy_sample_scale: int,
    n_communes: int,
    expected_units: int | None,
    geographic_unit: str,
    outputs: list[str],
    methodology_doc: str,
    figure: str,
    cache_fingerprints: dict[str, str],
) -> None:
    """Write enriched JSON metadata for the multi-source greenspace layer."""
    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "geographic_unit": geographic_unit,
        "expected_communes": expected_units if expected_units is not None else n_communes,
        "expected_units": expected_units if expected_units is not None else n_communes,
        "n_communes": n_communes,
        "source": {
            "provider": "Google Earth Engine",
            "collections": [
                dw_cfg["collection"],
                canopy_cfg["collection"],
            ],
            "resolution_m": {"dynamic_world_native": 10, "canopy_native": 1},
            "gee_project": gee.get_gee_project(),
        },
        "dynamic_world": {
            "collection": dw_cfg["collection"],
            "years": dw_cfg["years"],
            "season_months": dw_cfg["season_months"],
            "green_classes": dw_cfg["green_classes"],
            "cover_definition": "argmax of peak-season mean class probabilities (Dynamic World convention): green = strongest green-class prob exceeds every non-green-class prob; fractional cover per zone",
            "native_scale_meters": 10,
            "commune_reduce_scale_meters": dw_scale,
        },
        "canopy": {
            "collection": canopy_cfg["collection"],
            "band": canopy_cfg["band"],
            "band_semantics": "canopy height in integer metres (0 == no canopy)",
            "min_height_m": canopy_cfg["min_height_m"],
            "native_resolution_m": 1,
            "sample_scale_meters": canopy_sample_scale,
        },
        "cache_fingerprints": cache_fingerprints,
        "columns": {
            "name": {"unit": "spatial-unit name", "description": "Configured spatial-unit label"},
            "area_km2": {"unit": "km²", "description": "Spatial-unit area in square kilometres"},
            "green_total_pct": {"unit": "percent [0,100]", "description": f"Dynamic World fractional cover of {dw_cfg['green_classes']} (argmax composite)"},
            "tree_pct": {"unit": "percent [0,100]", "description": "Dynamic World fractional cover of the 'trees' class"},
            "grass_pct": {"unit": "percent [0,100]", "description": "Dynamic World fractional cover of the 'grass' class"},
            "canopy_cover_pct": {"unit": "percent [0,100]", "description": f"Meta 1 m tree-canopy cover (height >= {canopy_cfg['min_height_m']} m), aggregated to commune"},
            "canopy_mean_height_m": {"unit": "metres", "description": "Mean Meta canopy height over commune (0 counted as no canopy)"},
        },
        "complement_note": (
            "Each source closes a distinct gap: OSM = designated parks; Dynamic "
            "World = total green incl. lawns/informal; Meta canopy = street trees "
            "that OSM and the 10 m argmax both miss in dense blocks."
        ),
        "limitations": [
            "Dynamic World argmax at 10 m assigns each pixel a single class, so isolated street trees smaller than the dominant land cover are not counted as green (this is why the 1 m canopy layer is included).",
            "Meta canopy is reliable only when aggregated (>=30 m); no per-pixel (1 m) claim is made — values are commune/grid-cell means.",
            "Dynamic World can confuse bare soil and sparse/dry vegetation in semi-arid peri-urban terrain (Santiago's northern fringe); shrub_and_scrub inclusion is a modelling choice validated in the annotation sanity-check.",
            "Single peak-season (Oct-Mar) snapshot of the configured year(s); inter-annual variability not captured.",
        ],
        "methodology_doc": methodology_doc,
        "diagnostic_figure": figure,
        "outputs": outputs,
    }
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


def build_greenspace_multisource_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    figures_dir: Path = Path("figures"),
    years: list[int] | None = None,
) -> tuple[Path, Path]:
    """Build the multi-source greenspace layer and write CSV + GeoJSON."""
    cfg = config.load_config(city)

    cache_dir = Path(cache_dir)
    out_dir = Path(out_dir)
    figures_dir = Path(figures_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"Building multi-source greenspace layer for {city}")

    cache_path = cache_dir / f"{city}_communes.geojson"
    communes = boundaries.get_communes(cfg, cache_path=cache_path)

    green_cfg = cfg["greenspace"]
    dw_cfg = green_cfg["dynamic_world"]
    if years is not None:
        dw_cfg["years"] = [int(value) for value in years]
    canopy_cfg = green_cfg["canopy"]
    dw_scale = int(dw_cfg["commune_scale_meters"])
    canopy_sample_scale = int(canopy_cfg["sample_scale_meters"])

    spatial_key = spatial_fingerprint(
        communes,
        id_column="spatial_id" if "spatial_id" in communes.columns else "name",
    )
    identities = {
        "dynamic_world": CacheIdentity(
            layer_id="greenspace_multisource",
            operation="dynamic_world_zonal",
            parameters={
                "collection": dw_cfg["collection"],
                "probability_bands": DW_CLASSES,
                "years": dw_cfg["years"],
                "season_months": dw_cfg["season_months"],
                "green_classes": dw_cfg["green_classes"],
                "classification": "mean_probability_argmax",
                "output_bands": ["green", "tree", "grass"],
                "scale_meters": dw_scale,
                "crs": "EPSG:4326",
                "tile_scale": 16,
                "execution": "per_spatial_unit_checkpointed",
                "reducer": "mean",
            },
            spatial_fingerprint=spatial_key,
            algorithm_version="3",
        ),
        "canopy": CacheIdentity(
            layer_id="greenspace_multisource",
            operation="canopy_zonal",
            parameters={
                "collection": canopy_cfg["collection"],
                "band": canopy_cfg["band"],
                "mosaic": True,
                "min_height_m": canopy_cfg["min_height_m"],
                "output_bands": ["canopy_cover", "canopy_height"],
                "scale_meters": canopy_sample_scale,
                "crs": "EPSG:4326",
                "tile_scale": 16,
                "execution": "per_spatial_unit_checkpointed",
                "reducer": "mean",
            },
            spatial_fingerprint=spatial_key,
            algorithm_version="3",
        ),
    }
    stores = {name: CacheStore(cache_dir, identity) for name, identity in identities.items()}
    expected_names = communes["name"].astype(str).tolist()
    dw_record = stores["dynamic_world"].load_csv(
        "zonal",
        required_columns=["name", "green", "tree", "grass"],
        expected_completed_keys=expected_names,
    )
    canopy_record = stores["canopy"].load_csv(
        "zonal",
        required_columns=["name", "canopy_cover", "canopy_height"],
        expected_completed_keys=expected_names,
    )
    progress = tqdm(total=2, desc=f"greenspace_multisource [{city}]", unit="step")

    regions_fc: ee.FeatureCollection | None = None
    roi: ee.Geometry | None = None
    if not (dw_record.hit and canopy_record.hit):
        gee.init_gee()
        regions_fc = gee.gdf_to_feature_collection(communes)
        roi = regions_fc.geometry().bounds()

    if dw_record.hit:
        tqdm.write(f"  [dynamic_world] {dw_record.reason} …")
        assert dw_record.frame is not None
        dw_stats = {row["name"]: row for row in dw_record.frame.to_dict("records")}
    else:
        tqdm.write(
            f"  [dynamic_world] cache miss ({dw_record.reason}); "
            "fetching zonal cover fractions from GEE …"
        )
        assert regions_fc is not None and roi is not None
        dw_image = build_dynamic_world_masks(
            roi=roi,
            years=dw_cfg["years"],
            season_months=dw_cfg["season_months"],
            green_classes=dw_cfg["green_classes"],
        )
        dw_stats = _checkpointed_zonal_means(
            image=dw_image,
            communes=communes,
            scale=dw_scale,
            store=stores["dynamic_world"],
            required_columns=["name", "green", "tree", "grass"],
            label="dynamic_world",
        )
    progress.update(1)

    if canopy_record.hit:
        tqdm.write(f"  [canopy] {canopy_record.reason} …")
        assert canopy_record.frame is not None
        canopy_stats = {row["name"]: row for row in canopy_record.frame.to_dict("records")}
    else:
        tqdm.write(
            f"  [canopy] cache miss ({canopy_record.reason}); "
            "fetching zonal canopy statistics from GEE …"
        )
        assert regions_fc is not None and roi is not None
        canopy_image = build_canopy_image(
            roi=roi,
            collection_id=canopy_cfg["collection"],
            band=canopy_cfg["band"],
            min_height_m=canopy_cfg["min_height_m"],
        )
        canopy_stats = _checkpointed_zonal_means(
            image=canopy_image,
            communes=communes,
            scale=canopy_sample_scale,
            store=stores["canopy"],
            required_columns=["name", "canopy_cover", "canopy_height"],
            label="canopy",
        )
    progress.update(1)
    progress.close()

    has_spatial_id = "spatial_id" in communes.columns and "spatial_name" in communes.columns
    base_cols = (["spatial_id", "spatial_name"] if has_spatial_id else []) + ["name", "area_km2", "geometry"]
    result = communes[base_cols].copy()
    result["green_total_pct"] = result["name"].map(lambda n: dw_stats.get(n, {}).get("green"))
    result["tree_pct"] = result["name"].map(lambda n: dw_stats.get(n, {}).get("tree"))
    result["grass_pct"] = result["name"].map(lambda n: dw_stats.get(n, {}).get("grass"))
    result["canopy_cover_pct"] = result["name"].map(
        lambda n: canopy_stats.get(n, {}).get("canopy_cover")
    )
    result["canopy_mean_height_m"] = result["name"].map(
        lambda n: canopy_stats.get(n, {}).get("canopy_height")
    )

    for col in ["green_total_pct", "tree_pct", "grass_pct", "canopy_cover_pct"]:
        result[col] = (result[col] * 100).round(2)
    result["canopy_mean_height_m"] = result["canopy_mean_height_m"].round(3)

    # Validate output contract (mirrors greenspace_coverage).
    expected = cfg["expected_communes"]
    if len(result) != expected:
        raise ValueError(f"Expected {expected} communes, got {len(result)}")
    if result["name"].duplicated().any():
        dupes = result.loc[result["name"].duplicated(), "name"].tolist()
        raise ValueError(f"Duplicate commune names: {dupes}")
    numeric_cols = [c for c in result.columns if c not in ("name", "geometry", "spatial_id", "spatial_name")]
    if result[numeric_cols].isna().any().any():
        missing = result[numeric_cols].columns[result[numeric_cols].isna().any()].tolist()
        raise ValueError(f"Missing values in output columns: {missing}")
    pct_cols = ["green_total_pct", "tree_pct", "grass_pct", "canopy_cover_pct"]
    out_of_range = [c for c in pct_cols if not result[c].between(0, 100).all()]
    if out_of_range:
        raise ValueError(f"Percent columns out of [0,100]: {out_of_range}")

    result_geo = result.to_crs(cfg["crs"]["geographic"])

    base_name = f"{city}_greenspace_multisource"
    csv_path = out_dir / f"{base_name}.csv"
    geojson_path = out_dir / f"{base_name}.geojson"
    metadata_path = out_dir / f"{base_name}_metadata.json"
    figure_path = figures_dir / f"greenspace_multisource_{city}_2panel.png"

    result.drop(columns="geometry").to_csv(csv_path, index=False)
    result_geo.to_file(geojson_path, driver="GeoJSON")

    _write_multisource_figure(result_geo, figure_path)
    _write_multisource_metadata(
        metadata_path,
        city=city,
        dw_cfg=dw_cfg,
        canopy_cfg=canopy_cfg,
        dw_scale=dw_scale,
        canopy_sample_scale=canopy_sample_scale,
        n_communes=int(len(result)),
        expected_units=int(cfg.get("expected_units", cfg.get("expected_communes", len(result)))),
        geographic_unit=str(cfg.get("spatial_unit_type", "spatial_unit")),
        outputs=[csv_path.name, geojson_path.name, metadata_path.name],
        methodology_doc="docs/greenspace_multisource_methodology.md",
        figure=figure_path.as_posix(),
        cache_fingerprints={name: identity.digest for name, identity in identities.items()},
    )

    print(f"Wrote {csv_path.name}: {len(result)} rows x {result.drop(columns='geometry').shape[1]} columns")
    print(f"Wrote {geojson_path.name}")
    print(f"Wrote {metadata_path.name}")
    print(f"Wrote {figure_path.name}")

    return csv_path, geojson_path
